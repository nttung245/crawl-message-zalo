from __future__ import annotations

from typing import Any, Awaitable, Callable, Dict, List, Optional
import asyncio
import os
import tempfile

from loguru import logger

from app.modules.zalo.services.supabase_service import download_asset_bytes
from app.modules.zalo.services.zca_api_bridge import send_zca_images, send_zca_message


def _uploaded_assets(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [
        asset
        for asset in (message.get("assets") or [])
        if asset.get("status") == "uploaded" and asset.get("storage_path")
    ]


async def _asset_to_temp_file(asset: Dict[str, Any]) -> str:
    content, _content_type, ext = await download_asset_bytes(asset["storage_path"])
    fd, path = tempfile.mkstemp(prefix="zalo-zca-send-", suffix=ext or ".jpg")
    with os.fdopen(fd, "wb") as tmp:
        tmp.write(content)
    return path


async def send_zca_broadcast_to_targets(
    auth: Dict[str, Any],
    user_id: str,
    campaign_id: str,
    messages: List[Dict[str, Any]],
    targets: List[Dict[str, Any]],
    content_mode: str,
    delay_seconds: float,
    log_callback: Callable[[str, str, str, Optional[str], Optional[str]], Awaitable[None]],
) -> None:
    for target in targets:
        group_name = target["group_name"]
        group_id = target.get("group_id")
        
        if not group_id and group_name:
            # Try to resolve group_id from Supabase zalo_groups by name
            try:
                from app.modules.zalo.services.supabase_service import _rest
                rows = await _rest(
                    "GET",
                    "zalo_groups",
                    params={
                        "select": "group_id",
                        "user_id": f"eq.{user_id}",
                        "group_name": f"eq.{group_name}",
                        "limit": "1"
                    }
                )
                if rows and rows[0].get("group_id"):
                    group_id = rows[0]["group_id"]
                else:
                    # Case-insensitive check
                    rows = await _rest(
                        "GET",
                        "zalo_groups",
                        params={
                            "select": "group_id",
                            "user_id": f"eq.{user_id}",
                            "group_name": f"ilike.{group_name}",
                            "limit": "1"
                        }
                    )
                    if rows and rows[0].get("group_id"):
                        group_id = rows[0]["group_id"]
            except Exception as e:
                logger.warning(f"Could not resolve group_id from name '{group_name}' in Supabase: {e}")

        if not group_id:
            await log_callback(campaign_id, group_name, "failed", "Missing group_id for ZCA send", None)
            continue

        thread_type = 1 if group_id.startswith("g") else 0
        await log_callback(campaign_id, group_name, "opened", f"Using ZCA API target (thread_type={thread_type})")
        for message in messages:
            message_id = message["id"]
            send_text = content_mode in {"text", "both"} and bool((message.get("content") or "").strip())
            send_images = content_mode in {"image", "both"}
            temp_files: List[str] = []
            try:
                if send_text:
                    await send_zca_message(auth, group_id, message["content"], thread_type=thread_type)
                    await log_callback(campaign_id, group_name, "sent", "Text sent by ZCA API", message_id)
                    await asyncio.sleep(max(0.5, delay_seconds))

                if send_images:
                    assets = _uploaded_assets(message)
                    if assets:
                        for asset in assets:
                            temp_files.append(await _asset_to_temp_file(asset))
                        await send_zca_images(auth, group_id, temp_files, thread_type=thread_type)
                        await log_callback(campaign_id, group_name, "sent", "Images sent by ZCA API", message_id)
                        await asyncio.sleep(max(0.5, delay_seconds))

                if not send_text and not (send_images and temp_files):
                    await log_callback(campaign_id, group_name, "skipped", "No selected content to send", message_id)
            except Exception as exc:
                logger.warning(f"ZCA broadcast failed for message {message_id} to {group_name}: {exc}")
                await log_callback(campaign_id, group_name, "failed", str(exc), message_id)
            finally:
                for path in temp_files:
                    try:
                        os.remove(path)
                    except OSError:
                        pass
