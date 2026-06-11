from typing import List, Optional, Set
import asyncio

import gspread
from fastapi import APIRouter, Depends, Header, HTTPException
from loguru import logger
from pydantic import BaseModel, Field

from app.modules.zalo.config import settings
from app.modules.zalo.crawler.group_parser import collect_group_debug_info, parse_groups, wait_for_group_list_ready
from app.modules.zalo.crawler.scroll_handler import verify_group_for_crawl, wait_for_message_sync
from app.modules.zalo.schemas.group import Group
from app.modules.zalo.services.debug_artifacts import save_page_artifacts
from app.modules.zalo.services.gsheet_service import list_crawled_groups
from app.modules.zalo.services.supabase_service import is_supabase_configured, list_saved_groups, upsert_groups
from app.modules.zalo.services.session_store import get_latest_session_for_user, get_session, get_session_lock
from app.modules.zalo.services.browser_operation_lock import zalo_browser_operation_lock
from app.modules.zalo.services.session_browser import ensure_session_browser_ready
from app.modules.zalo.services.zca_auth_store import ensure_session_zca_auth
from app.modules.zalo.services.zca_api_bridge import list_zca_groups, list_zca_friends
from app.modules.zalo.api.security import verify_zalo_api_key

router = APIRouter(
    prefix="/api/groups",
    tags=["groups"],
    dependencies=[Depends(verify_zalo_api_key)],
)
zalo_groups_router = APIRouter(
    prefix="/api/zalo/groups",
    tags=["zalo-groups"],
    dependencies=[Depends(verify_zalo_api_key)],
)


class VerifyGroupItem(BaseModel):
    group_name: str = Field(..., min_length=1)
    group_id: Optional[str] = None
    sheet_tab: Optional[str] = None


class VerifyGroupsRequest(BaseModel):
    groups: List[VerifyGroupItem]


class VerifiedGroupItem(BaseModel):
    group_name: str
    group_id: Optional[str] = None
    sheet_tab: Optional[str] = None
    current_title: Optional[str] = None
    member_count: Optional[int] = None
    message_count: int = 0
    warnings: List[str] = []


class RejectedGroupItem(BaseModel):
    group_name: str
    group_id: Optional[str] = None
    reason: str
    detail: str
    current_title: Optional[str] = None
    member_count: Optional[int] = None
    warnings: List[str] = []


class VerifyGroupsResponse(BaseModel):
    verified: List[VerifiedGroupItem]
    rejected: List[RejectedGroupItem]


async def _live_group_fallback(user_id: str, session, selector_counts: Optional[dict], reason: str) -> List[Group]:
    if is_supabase_configured():
        try:
            saved_groups = await list_saved_groups(user_id)
            if saved_groups:
                logger.warning(
                    f"Live Zalo group suggestions unavailable ({reason}); returning {len(saved_groups)} saved groups"
                )
                return [
                    Group(
                        group_id=item.get("group_name") or item.get("sheet_tab") or "saved",
                        name=item.get("group_name") or item.get("sheet_tab") or "Saved group",
                        avatar_url=None,
                        last_message=f"{item.get('message_count', 0)} tin da luu",
                        unread_count=0,
                    )
                    for item in saved_groups
                ]
        except Exception as exc:
            logger.warning(f"Could not load saved group fallback: {exc}")

    try:
        debug_info = await collect_group_debug_info(session.page)
        debug_info["session_id"] = session.session_id
        debug_info["wait_selector_counts"] = selector_counts or {}
        debug_info["reason"] = reason
        artifacts = await save_page_artifacts(
            session.page,
            f"groups-{session.session_id}",
            metadata=debug_info,
        )
        logger.warning(
            "Returning empty Zalo group suggestions for session {}. reason={} url={} title={} artifacts={}",
            session.session_id,
            reason,
            debug_info["url"],
            debug_info["title"],
            artifacts,
        )
    except Exception as exc:
        logger.warning(f"Could not save live group debug artifacts: {exc}")

    return []


async def _get_confirmed_session_for_user(user_id: str, session_id: Optional[str]):
    session = await get_session(session_id) if session_id else None
    if not session:
        session = await get_latest_session_for_user(user_id, preferred_statuses={"confirmed"})
    if not session:
        raise HTTPException(status_code=401, detail="No confirmed session found, please login first")
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    try:
        live_status = await ensure_session_browser_ready(session)
    except Exception as exc:
        logger.error(f"Failed to ensure browser ready for session {session.session_id}: {exc}")
        raise HTTPException(
            status_code=503,
            detail=f"Browser initialization failed: {exc}. Please try again or restart the session.",
        )
    if live_status != "confirmed":
        raise HTTPException(
            status_code=403,
            detail=f"Login not completed yet (status={live_status})",
        )
    return session


@router.get("", response_model=List[Group])
async def list_groups(
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    user_id = (x_user_id or "default").strip() or "default"
    session = await get_session(x_session_id) if x_session_id else None
    if not session:
        session = await get_latest_session_for_user(user_id, preferred_statuses={"confirmed"})
    if not session:
        raise HTTPException(status_code=401, detail="No confirmed session found, please login first")
    if session.user_id != user_id:
        raise HTTPException(status_code=403, detail="Session does not belong to current user")

    zca_auth = await ensure_session_zca_auth(session)
    if zca_auth:
        try:
            groups = await list_zca_groups(zca_auth)
            try:
                friends = await list_zca_friends(zca_auth)
            except Exception as e:
                logger.warning(f"Could not load ZCA friends in list_groups: {e}")
                friends = []
            all_chats = groups + friends
            if all_chats:
                if is_supabase_configured():
                    try:
                        cached_count = await upsert_groups(
                            user_id,
                            [chat.model_dump() for chat in all_chats],
                        )
                        logger.info(f"Cached {cached_count} ZCA chats for user_id={user_id}")
                    except Exception as exc:
                        logger.warning(f"Could not cache ZCA chats for user_id={user_id}: {exc}")
                logger.info(f"Returning {len(all_chats)} ZCA chats for user_id={user_id}; browser fallback skipped")
                return all_chats
            logger.warning("ZCA list_zca_groups returned empty; falling back to Playwright group parser")
        except Exception as exc:
            logger.warning(f"ZCA list_zca_groups failed; falling back to Playwright group parser: {exc}")

    selector_counts = {}
    try:
        live_status = await ensure_session_browser_ready(session)
        if live_status != "confirmed":
            raise HTTPException(
                status_code=403,
                detail=f"Login not completed yet (status={live_status})",
            )
        async with zalo_browser_operation_lock:
            session_lock = await get_session_lock(session.session_id)
            async with session_lock:
                groups: List[Group] = []
                for attempt in range(1, 3):
                    try:
                        await wait_for_message_sync(session.page, timeout_ms=90000 if attempt == 1 else 30000)
                        if attempt > 1:
                            logger.warning("Retrying live group suggestions after Zalo navigation/parser failure")
                            await session.page.goto("https://chat.zalo.me", wait_until="domcontentloaded", timeout=60000)
                            await session.page.wait_for_timeout(3000)
                            await wait_for_message_sync(session.page, timeout_ms=30000)
                        selector_counts = await wait_for_group_list_ready(session.page, timeout_ms=30000)
                        groups = await parse_groups(session.page)
                        break
                    except Exception as parse_exc:
                        logger.warning(f"Live group parse attempt {attempt} failed: {parse_exc}")
                        if attempt >= 2:
                            return await _live_group_fallback(
                                user_id,
                                session,
                                selector_counts,
                                f"live_parse_failed: {parse_exc}",
                            )
                if not groups:
                    logger.warning("First live group parse returned empty; retrying after reload/recovery")
                    try:
                        await session.page.goto("https://chat.zalo.me", wait_until="domcontentloaded", timeout=60000)
                        await session.page.wait_for_timeout(3000)
                        await wait_for_message_sync(session.page, timeout_ms=30000)
                        selector_counts = await wait_for_group_list_ready(session.page, timeout_ms=30000)
                        groups = await parse_groups(session.page)
                    except Exception as retry_exc:
                        logger.warning(f"Live group retry failed: {retry_exc}")
                if not groups:
                    if is_supabase_configured():
                        saved_groups = await list_saved_groups(user_id)
                        if saved_groups:
                            logger.warning(
                                f"Live Zalo group list unavailable; returning {len(saved_groups)} saved crawled groups"
                            )
                            return [
                                Group(
                                    group_id=item.get("group_name") or item.get("sheet_tab") or "saved",
                                    name=item.get("group_name") or item.get("sheet_tab") or "Saved group",
                                    avatar_url=None,
                                    last_message=f"{item.get('message_count', 0)} tin da luu",
                                    unread_count=0,
                                )
                                for item in saved_groups
                            ]
                    debug_info = await collect_group_debug_info(session.page)
                    debug_info["session_id"] = session.session_id
                    debug_info["wait_selector_counts"] = selector_counts

                    artifacts = await save_page_artifacts(
                        session.page,
                        f"groups-{session.session_id}",
                        metadata=debug_info,
                    )

                    logger.error(
                        "Group list is empty for session {}. url={} title={} artifacts={}",
                        session.session_id,
                        debug_info["url"],
                        debug_info["title"],
                        artifacts,
                    )
                    return await _live_group_fallback(
                        user_id,
                        session,
                        selector_counts,
                        "live_group_suggestions_empty",
                    )
                if is_supabase_configured():
                    try:
                        cached_count = await upsert_groups(
                            user_id,
                            [group.model_dump() for group in groups],
                        )
                        logger.info(f"Cached {cached_count} Zalo live groups for user_id={user_id}")
                    except Exception as exc:
                        logger.warning(f"Could not cache live Zalo groups for user_id={user_id}: {exc}")
                return groups
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to parse groups for session {session.session_id}: {e}")
        return await _live_group_fallback(
            user_id,
            session,
            selector_counts,
            f"unexpected_live_group_error: {e}",
        )


@zalo_groups_router.post("/verify", response_model=VerifyGroupsResponse)
async def verify_groups_for_crawl(
    body: VerifyGroupsRequest,
    x_session_id: Optional[str] = Header(None, alias="X-Session-ID"),
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    user_id = (x_user_id or "default").strip() or "default"
    session = await _get_confirmed_session_for_user(user_id, x_session_id)
    session_lock = await get_session_lock(session.session_id)

    verified: List[VerifiedGroupItem] = []
    rejected: List[RejectedGroupItem] = []
    seen: Set[str] = set()

    zca_auth = await ensure_session_zca_auth(session)
    zca_groups_by_name = {}
    if zca_auth:
        try:
            zca_groups = await list_zca_groups(zca_auth)
            for g in zca_groups:
                norm_name = " ".join(g.name.split()).lower()
                zca_groups_by_name[norm_name] = g
        except Exception as e:
            logger.warning(f"Failed to load ZCA groups for verification: {e}")

    async with zalo_browser_operation_lock:
        async with session_lock:
            for item in body.groups:
                group_name = " ".join(item.group_name.split())
                if not group_name:
                    continue
                key = group_name.lower()
                if key in seen:
                    rejected.append(
                        RejectedGroupItem(
                            group_name=group_name,
                            group_id=item.group_id,
                            reason="duplicate",
                            detail="Ten nhom bi trung trong danh sach kiem tra.",
                        )
                    )
                    continue
                seen.add(key)

                matched_group = None
                if zca_groups_by_name:
                    if key in zca_groups_by_name:
                        matched_group = zca_groups_by_name[key]
                    else:
                        matches = [g for n, g in zca_groups_by_name.items() if key in n]
                        if len(matches) == 1:
                            matched_group = matches[0]
                        elif len(matches) > 1:
                            rejected.append(
                                RejectedGroupItem(
                                    group_name=group_name,
                                    group_id=item.group_id,
                                    reason="ambiguous",
                                    detail=f"Có {len(matches)} nhóm chứa từ khoá '{group_name}', vui lòng nhập tên chính xác hơn.",
                                )
                            )
                            continue

                if matched_group:
                    verified.append(
                        VerifiedGroupItem(
                            group_name=matched_group.name,
                            group_id=matched_group.group_id,
                            sheet_tab=item.sheet_tab or matched_group.name,
                            current_title=matched_group.name,
                            member_count=None,
                            message_count=0,
                            warnings=[],
                        )
                    )
                    continue

                if not session.page:
                    rejected.append(
                        RejectedGroupItem(
                            group_name=group_name,
                            group_id=item.group_id,
                            reason="not_found",
                            detail="Khong tim thay nhom Zalo qua API. Trinh duyet khong kha dung.",
                            current_title=None,
                            member_count=None,
                            warnings=[],
                        )
                    )
                    continue

                result = await verify_group_for_crawl(
                    session.page,
                    group_name=group_name,
                    group_id=item.group_id,
                )
                warnings = list(result.get("warnings") or [])
                if result.get("ok"):
                    verified.append(
                        VerifiedGroupItem(
                            group_name=group_name,
                            group_id=result.get("resolved_group_id") or item.group_id or group_name,
                            sheet_tab=item.sheet_tab or group_name,
                            current_title=result.get("current_title"),
                            member_count=result.get("member_count"),
                            message_count=int(result.get("message_count") or 0),
                            warnings=warnings,
                        )
                    )
                else:
                    rejected.append(
                        RejectedGroupItem(
                            group_name=group_name,
                            group_id=item.group_id,
                            reason=str(result.get("reason") or "not_found"),
                            detail=str(result.get("detail") or "Khong xac minh duoc nhom Zalo."),
                            current_title=result.get("current_title"),
                            member_count=result.get("member_count"),
                            warnings=warnings,
                        )
                    )

    return VerifyGroupsResponse(verified=verified, rejected=rejected)


@zalo_groups_router.get("/crawled")
async def list_crawled_groups_from_sheet(x_user_id: str = Header("default", alias="X-User-ID")):
    if not settings.write_google_sheet:
        if not is_supabase_configured():
            return {
                "sheet_id": "",
                "sheet_url": "",
                "total_groups": 0,
                "groups": [],
            }
        groups = await list_saved_groups((x_user_id or "default").strip() or "default")
        return {
            "sheet_id": "",
            "sheet_url": "",
            "total_groups": len(groups),
            "groups": groups,
        }

    sheet_id = settings.default_sheet_id.strip()
    if not sheet_id:
        raise HTTPException(
            status_code=500,
            detail="ZALO_DEFAULT_SHEET_ID is missing in backend env",
        )

    try:
        groups = await asyncio.to_thread(
            list_crawled_groups,
            settings.google_credentials_path,
            sheet_id,
        )
        return {
            "sheet_id": sheet_id,
            "sheet_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}",
            "total_groups": len(groups),
            "groups": groups,
        }
    except gspread.exceptions.SpreadsheetNotFound:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Google Sheet {sheet_id} not found or service account has no access. "
                "Hay share file Google Sheet cho service account."
            ),
        )
    except Exception as e:
        logger.error(f"Failed to list crawled groups from sheet {sheet_id}: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to list crawled groups: {e}")
