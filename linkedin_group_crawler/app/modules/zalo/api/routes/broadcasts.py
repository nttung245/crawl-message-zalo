import asyncio
import re

from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger

from app.modules.zalo.api.security import verify_zalo_api_key
from app.modules.zalo.config import settings
from app.modules.zalo.crawler.broadcast_sender import send_broadcast_to_targets
from app.modules.zalo.crawler.qr_login import check_login_status
from app.modules.zalo.schemas.broadcast import (
    ZaloBroadcastPreviewItem,
    ZaloBroadcastPreviewResponse,
    ZaloBroadcastRequest,
    ZaloBroadcastResponse,
    ZaloBroadcastStatusResponse,
)
from app.modules.zalo.services.session_store import (
    get_latest_session_for_user,
    get_session_lock,
    save_session,
)
from app.modules.zalo.services.browser_operation_lock import zalo_browser_operation_lock
from app.modules.zalo.services.supabase_service import (
    SupabaseNotConfigured,
    add_broadcast_log,
    create_broadcast_campaign,
    fetch_messages_by_ids,
    get_broadcast_status,
    update_campaign_status,
)

router = APIRouter(
    prefix="/api/zalo/broadcasts",
    tags=["zalo-broadcasts"],
    dependencies=[Depends(verify_zalo_api_key)],
)

_BROADCAST_WORKER_LOCK = zalo_browser_operation_lock


def _normalize_user_id(value: str | None) -> str:
    raw = (value or "default").strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw or "default"


def _asset_count(message: dict) -> int:
    return sum(
        1
        for asset in message.get("assets") or []
        if asset.get("status") == "uploaded" and (asset.get("storage_url") or asset.get("storage_path"))
    )


def _asset_preview_urls(message: dict) -> list[str]:
    urls: list[str] = []
    for asset in message.get("assets") or []:
        if asset.get("status") != "uploaded":
            continue
        storage_url = asset.get("storage_url")
        if storage_url:
            urls.append(storage_url)
    return urls


def _build_preview(messages: list[dict], target_count: int, content_mode: str) -> ZaloBroadcastPreviewResponse:
    items: list[ZaloBroadcastPreviewItem] = []
    warnings: list[str] = []
    for message in messages:
        image_count = _asset_count(message)
        image_urls = _asset_preview_urls(message)
        send_text = content_mode in {"text", "both"} and bool((message.get("content") or "").strip())
        send_images = content_mode in {"image", "both"} and image_count > 0
        item_warnings: list[str] = []
        if content_mode == "image" and image_count == 0:
            item_warnings.append("Tin này không có ảnh đã lưu được trong Supabase Storage")
        if content_mode == "text" and not send_text:
            item_warnings.append("Tin này không có nội dung text")
        if content_mode == "both" and not (send_text or send_images):
            item_warnings.append("Tin nay khong co text hoac anh de gui")
        items.append(
            ZaloBroadcastPreviewItem(
                message_id=message["id"],
                content=message.get("content"),
                image_count=image_count,
                image_urls=image_urls,
                send_text=send_text,
                send_images=send_images,
                warnings=item_warnings,
            )
        )
    if target_count == 0:
        warnings.append("Chưa chọn group đích")
    if not messages:
        warnings.append("Chưa chọn tin nhắn")
    return ZaloBroadcastPreviewResponse(
        target_count=target_count,
        message_count=len(messages),
        items=items,
        warnings=warnings,
    )


@router.post("/preview", response_model=ZaloBroadcastPreviewResponse)
async def preview_broadcast(
    body: ZaloBroadcastRequest,
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    user_id = _normalize_user_id(body.user_id or x_user_id)
    try:
        messages = await fetch_messages_by_ids(user_id, body.message_ids)
        return _build_preview(messages, len(body.targets), body.content_mode)
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to build broadcast preview: {exc}")


@router.post("", response_model=ZaloBroadcastResponse)
async def create_broadcast(
    body: ZaloBroadcastRequest,
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    user_id = _normalize_user_id(body.user_id or x_user_id)
    if not body.message_ids:
        raise HTTPException(status_code=400, detail="message_ids is required")
    if not body.targets:
        raise HTTPException(status_code=400, detail="targets is required")

    session = await get_latest_session_for_user(user_id, preferred_statuses={"confirmed"})
    if not session:
        raise HTTPException(status_code=401, detail="No confirmed Zalo session found, please login first")
    live_status = await check_login_status(session.page)
    session.status = live_status
    await save_session(session)
    if live_status != "confirmed":
        raise HTTPException(status_code=403, detail=f"Login not completed yet (status={live_status})")

    try:
        messages = await fetch_messages_by_ids(user_id, body.message_ids)
        if len(messages) != len(set(body.message_ids)):
            raise HTTPException(status_code=400, detail="Some selected messages were not found")

        campaign_id = await create_broadcast_campaign(
            user_id,
            body.content_mode,
            body.message_ids,
            [target.model_dump() for target in body.targets],
        )
        asyncio.create_task(
            _run_broadcast(
                campaign_id,
                user_id,
                session.session_id,
                messages,
                [target.model_dump() for target in body.targets],
                body.content_mode,
            )
        )
        return ZaloBroadcastResponse(campaign_id=campaign_id, status="queued")
    except HTTPException:
        raise
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create broadcast: {exc}")


@router.get("/{campaign_id}", response_model=ZaloBroadcastStatusResponse)
async def get_broadcast(campaign_id: str):
    try:
        return await get_broadcast_status(campaign_id)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Broadcast {campaign_id} not found")
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to get broadcast: {exc}")


async def _run_broadcast(
    campaign_id: str,
    user_id: str,
    session_id: str,
    messages: list[dict],
    targets: list[dict],
    content_mode: str,
) -> None:
    try:
        async with _BROADCAST_WORKER_LOCK:
            await update_campaign_status(campaign_id, "running")
            session = await get_latest_session_for_user(user_id, preferred_statuses={"confirmed"})
            # session_id is authoritative; fallback above is only for stale stores.
            if not session or session.session_id != session_id:
                from app.modules.zalo.services.session_store import get_session

                session = await get_session(session_id)
            if not session:
                raise RuntimeError("Zalo session expired before broadcast started")
            session_lock = await get_session_lock(session.session_id)
            async with session_lock:
                live_status = await check_login_status(session.page)
                session.status = live_status
                await save_session(session)
                if live_status != "confirmed":
                    raise RuntimeError(f"Login not completed yet (status={live_status})")
                await send_broadcast_to_targets(
                    session.page,
                    campaign_id,
                    messages,
                    targets,
                    content_mode,
                    settings.broadcast_delay_seconds,
                    settings.broadcast_composer_timeout_seconds,
                    add_broadcast_log,
                )
            await update_campaign_status(campaign_id, "completed")
    except Exception as exc:
        logger.error(f"Broadcast campaign {campaign_id} failed: {exc}")
        try:
            await add_broadcast_log(campaign_id, "", "failed", str(exc))
            await update_campaign_status(campaign_id, "failed", str(exc))
        except Exception:
            logger.exception(f"Could not mark broadcast campaign {campaign_id} as failed")
