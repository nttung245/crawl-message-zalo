from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Tuple
import mimetypes
import posixpath
import uuid
import base64
import hashlib
from datetime import datetime, timedelta
from urllib.parse import quote

import httpx
from loguru import logger

from app.modules.zalo.config import settings
from app.modules.zalo.schemas.job import JobData
from app.modules.zalo.schemas.message import Message


class SupabaseNotConfigured(RuntimeError):
    pass


def is_supabase_configured() -> bool:
    return bool(settings.supabase_url.strip() and settings.supabase_service_role_key.strip())


def _require_configured() -> None:
    if not is_supabase_configured():
        raise SupabaseNotConfigured("SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY are required")


def _base_url() -> str:
    return settings.supabase_url.rstrip("/")


def _http_client(*, timeout: int = 60, follow_redirects: bool = False) -> "httpx.AsyncClient":
    """HTTP client dùng chung cho Supabase.

    Mặc định verify SSL. Khi chạy local sau proxy/antivirus có SSL inspection
    (self-signed cert) gây CERTIFICATE_VERIFY_FAILED, đặt SUPABASE_SSL_VERIFY=false
    để bỏ qua verify. KHÔNG dùng false trên production công khai.
    """
    return httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=follow_redirects,
        verify=settings.supabase_ssl_verify,
    )


def _headers(extra: Optional[Dict[str, str]] = None) -> Dict[str, str]:
    key = settings.supabase_service_role_key
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    if extra:
        headers.update(extra)
    return headers


async def _rest(
    method: str,
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
    json: Optional[Any] = None,
    prefer: Optional[str] = None,
) -> Any:
    _require_configured()
    headers = _headers({"Prefer": prefer} if prefer else None)
    url = f"{_base_url()}/rest/v1/{path.lstrip('/')}"
    async with _http_client(timeout=60) as client:
        response = await client.request(method, url, headers=headers, params=params, json=json)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase {method} {path} failed: {response.status_code} {response.text}")
    if not response.content:
        return None
    return response.json()


async def _rest_with_count(
    path: str,
    *,
    params: Optional[Dict[str, Any]] = None,
) -> Tuple[Any, int]:
    _require_configured()
    headers = _headers({"Prefer": "count=exact"})
    url = f"{_base_url()}/rest/v1/{path.lstrip('/')}"
    async with _http_client(timeout=60) as client:
        response = await client.get(url, headers=headers, params=params)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase GET {path} failed: {response.status_code} {response.text}")
    content_range = response.headers.get("content-range", "")
    total = 0
    if "/" in content_range:
        raw_total = content_range.rsplit("/", 1)[-1]
        if raw_total.isdigit():
            total = int(raw_total)
    return (response.json() if response.content else []), total


async def upload_asset_bytes(path: str, content: bytes, content_type: str) -> str:
    _require_configured()
    bucket = quote(settings.supabase_storage_bucket.strip() or "zalo-assets", safe="")
    object_path = quote(path.lstrip("/"), safe="/")
    url = f"{_base_url()}/storage/v1/object/{bucket}/{object_path}"
    headers = _headers(
        {
            "Content-Type": content_type,
            "x-upsert": "true",
        }
    )
    async with _http_client(timeout=90) as client:
        response = await client.put(url, headers=headers, content=content)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase storage upload failed: {response.status_code} {response.text}")
    return f"{_base_url()}/storage/v1/object/public/{bucket}/{object_path}"


async def download_asset_bytes(path: str) -> Tuple[bytes, str, str]:
    _require_configured()
    bucket = quote(settings.supabase_storage_bucket.strip() or "zalo-assets", safe="")
    object_path = quote(path.lstrip("/"), safe="/")
    url = f"{_base_url()}/storage/v1/object/{bucket}/{object_path}"
    async with _http_client(timeout=90, follow_redirects=True) as client:
        response = await client.get(url, headers=_headers())
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase storage download failed: {response.status_code} {response.text}")
    content_type = response.headers.get("content-type", "").split(";")[0].strip() or "application/octet-stream"
    ext = mimetypes.guess_extension(content_type) or ".jpg"
    return response.content, content_type, ext


async def delete_storage_objects(paths: List[str]) -> None:
    if not paths:
        return
    _require_configured()
    bucket = quote(settings.supabase_storage_bucket.strip() or "zalo-assets", safe="")
    url = f"{_base_url()}/storage/v1/object/{bucket}"
    headers = _headers()
    async with _http_client(timeout=90) as client:
        response = await client.request(
            "DELETE",
            url,
            headers=headers,
            json={"prefixes": paths},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase storage delete failed: {response.status_code} {response.text}")


async def _download_image(source_url: str) -> Tuple[bytes, str, str]:
    if source_url.startswith("data:image/"):
        header, _, payload = source_url.partition(",")
        if not payload or ";base64" not in header:
            raise RuntimeError("Unsupported data URL image format")
        content_type = header.removeprefix("data:").split(";")[0] or "image/jpeg"
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        return base64.b64decode(payload), content_type, ext

    async with _http_client(timeout=60, follow_redirects=True) as client:
        response = await client.get(source_url)
    if response.status_code >= 400:
        raise RuntimeError(f"Image download failed: HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "").split(";")[0].strip() or "application/octet-stream"
    ext = mimetypes.guess_extension(content_type) or ".jpg"
    return response.content, content_type, ext


def _message_payload(user_id: str, job: JobData, group_id: str, group_name: str, msg: Message) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "job_id": job.job_id,
        "group_id": group_id,
        "group_name": group_name,
        "source_message_id": msg.message_id,
        "sender_id": msg.sender_id,
        "sender_name": msg.sender_name,
        "timestamp_text": msg.timestamp,
        "time_text": msg.time_text,
        "type": msg.type,
        "content": msg.content,
        "is_sent": msg.is_sent,
        "is_deleted": msg.is_deleted,
        "updated_at": datetime.utcnow().isoformat(),
    }


def _listener_message_payload(user_id: str, group_id: str, group_name: str, msg: Message) -> Dict[str, Any]:
    return {
        "user_id": user_id,
        "job_id": None,
        "group_id": group_id,
        "group_name": group_name,
        "source_message_id": msg.message_id,
        "sender_id": msg.sender_id,
        "sender_name": msg.sender_name,
        "timestamp_text": msg.timestamp,
        "time_text": msg.time_text,
        "type": msg.type,
        "content": msg.content,
        "is_sent": msg.is_sent,
        "is_deleted": msg.is_deleted,
        "updated_at": datetime.utcnow().isoformat(),
    }


def _message_from_row(row: Dict[str, Any]) -> Message:
    image_urls: List[str] = []
    for asset in row.get("assets") or []:
        if asset.get("storage_url"):
            image_urls.append(str(asset["storage_url"]))
        elif asset.get("source_url"):
            image_urls.append(str(asset["source_url"]))
    return Message(
        message_id=str(row.get("source_message_id") or row.get("id") or ""),
        sender_id=row.get("sender_id") or None,
        sender_name=row.get("sender_name") or None,
        timestamp=row.get("timestamp_text") or None,
        time_text=row.get("time_text") or None,
        type=str(row.get("type") or ("image" if image_urls else "text")),
        content=row.get("content") or None,
        image_urls=list(dict.fromkeys(image_urls)),
        is_deleted=bool(row.get("is_deleted")),
        is_sent=bool(row.get("is_sent")),
    )


async def upsert_zalo_user(
    user_id: str,
    *,
    status: str,
    assigned_worker_id: Optional[str] = None,
    display_name: Optional[str] = None,
) -> None:
    if not is_supabase_configured():
        return

    now = datetime.utcnow().isoformat()
    payload: Dict[str, Any] = {
        "user_id": user_id,
        "zalo_status": status,
        "last_seen_at": now,
        "updated_at": now,
    }
    if status == "confirmed":
        payload["last_login_at"] = now
    if assigned_worker_id:
        payload["assigned_worker_id"] = assigned_worker_id
    if display_name:
        payload["display_name"] = display_name

    await _rest(
        "POST",
        "zalo_users",
        json=[payload],
        params={"on_conflict": "user_id"},
        prefer="resolution=merge-duplicates",
    )


async def upsert_crawl_job(user_id: str, job: JobData) -> None:
    await _rest(
        "POST",
        "zalo_crawl_jobs",
        params={"on_conflict": "job_id"},
        prefer="resolution=merge-duplicates",
        json=[
            {
                "job_id": job.job_id,
                "user_id": user_id,
                "group_id": job.group_id,
                "group_name": job.group_name,
                "status": job.status,
                "messages_collected": job.progress.messages_collected,
                "images_found": job.progress.images_found,
                "oldest_message_date": job.progress.oldest_message_date,
                "started_at": job.started_at.isoformat(),
                "completed_at": job.completed_at.isoformat() if job.completed_at else None,
                "error": job.error,
                "updated_at": datetime.utcnow().isoformat(),
            }
        ],
    )


async def upsert_group(
    user_id: str,
    group_id: str,
    group_name: str,
    avatar_url: Optional[str] = None,
    unread_count: Optional[int] = None,
    last_message_at: Optional[str] = None,
    last_message_content: Optional[str] = None,
    last_sender_id: Optional[str] = None,
    last_sender_name: Optional[str] = None,
    last_message_type: Optional[str] = None,
) -> None:
    resolved_name = group_name
    if group_name and (group_name.startswith("Conversation ") or group_name.isdigit() or group_name == group_id):
        try:
            existing = await _rest(
                "GET",
                "zalo_groups",
                params={
                    "select": "group_name",
                    "user_id": f"eq.{user_id}",
                    "group_id": f"eq.{group_id}",
                    "limit": "1",
                }
            )
            if existing and existing[0].get("group_name"):
                old_name = existing[0]["group_name"]
                if old_name and not (old_name.startswith("Conversation ") or old_name.isdigit() or old_name == group_id):
                    resolved_name = old_name
        except Exception:
            pass

    payload = {
        "user_id": user_id,
        "group_id": group_id,
        "group_name": resolved_name,
        "updated_at": datetime.utcnow().isoformat(),
    }
    if avatar_url:
        payload["avatar_url"] = avatar_url
    if unread_count is not None:
        payload["unread_count"] = unread_count
    if last_message_at is not None:
        payload["last_message_at"] = last_message_at
    if last_message_content is not None:
        payload["last_message_content"] = last_message_content
    if last_sender_id is not None:
        payload["last_sender_id"] = last_sender_id
    if last_sender_name is not None:
        payload["last_sender_name"] = last_sender_name
    if last_message_type is not None:
        payload["last_message_type"] = last_message_type

    await _rest(
        "POST",
        "zalo_groups",
        json=[payload],
        params={"on_conflict": "user_id,group_id"},
        prefer="resolution=merge-duplicates",
    )


async def upsert_groups(user_id: str, groups: Iterable[Dict[str, Any]]) -> int:
    now = datetime.utcnow().isoformat()

    # Collect candidates first
    candidates: List[tuple] = []
    for group in groups:
        group_id = str(group.get("group_id") or group.get("id") or group.get("name") or "").strip()
        group_name = str(group.get("name") or group.get("group_name") or group_id).strip()
        if not group_id or not group_name:
            continue
        candidates.append((group_id, group_name, group))
    if not candidates:
        return 0

    # Prefetch existing group metadata so null values don't overwrite existing data
    # (e.g. avatar_url, last_message_at set by the listener).
    existing_map: Dict[str, Dict[str, Any]] = {}
    try:
        existing_rows = await _rest(
            "GET",
            "zalo_groups",
            params={
                "select": "group_id,avatar_url,unread_count,last_message_at,last_message_content,last_sender_id,last_sender_name,last_message_type",
                "user_id": f"eq.{user_id}",
                "limit": "5000",
            },
        ) or []
        existing_map = {str(r.get("group_id")): r for r in existing_rows}
    except Exception as exc:
        logger.warning(f"Could not prefetch existing zalo_groups for merge: {exc}")

    rows: List[Dict[str, Any]] = []
    for group_id, group_name, group in candidates:
        existing = existing_map.get(group_id, {})
        last_msg_at_raw = group.get("last_message_at")
        new_last_msg_at = _normalize_iso_timestamp(last_msg_at_raw) if last_msg_at_raw is not None else None
        row = {
            "user_id": user_id,
            "group_id": group_id,
            "group_name": group_name,
            "avatar_url": group.get("avatar_url") or existing.get("avatar_url"),
            "unread_count": int(existing.get("unread_count") or 0),
            "last_message_at": new_last_msg_at or existing.get("last_message_at"),
            "last_message_content": group.get("last_message_content") or group.get("last_message") or existing.get("last_message_content"),
            "last_sender_id": group.get("last_sender_id") or existing.get("last_sender_id"),
            "last_sender_name": group.get("last_sender_name") or existing.get("last_sender_name"),
            "last_message_type": group.get("last_message_type") or existing.get("last_message_type"),
            "is_pinned": bool(group.get("is_pinned")),
            "updated_at": now,
        }
        rows.append(row)

    await _rest(
        "POST",
        "zalo_groups",
        json=rows,
        params={"on_conflict": "user_id,group_id"},
        prefer="resolution=merge-duplicates",
    )
    return len(rows)


async def save_crawl_messages(user_id: str, job: JobData, group_id: str, messages: Iterable[Message]) -> int:
    group_name = job.group_name
    await upsert_crawl_job(user_id, job)
    await upsert_group(user_id, group_id, group_name)

    saved_count = 0
    uploaded_images = 0
    failed_images = 0
    for msg in messages:
        rows = await _rest(
            "POST",
            "zalo_messages",
            json=[_message_payload(user_id, job, group_id, group_name, msg)],
            params={"on_conflict": "user_id,group_id,source_message_id"},
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not rows:
            continue
        saved_count += 1
        message_row = rows[0]
        message_uuid = message_row["id"]
        asset_stats = await save_message_assets(message_uuid, user_id, job.job_id, msg.image_urls)
        uploaded_images += asset_stats["uploaded"]
        failed_images += asset_stats["failed"]
    logger.info(
        "Saved Zalo crawl payload: job={} group={!r} messages={} images_uploaded={} images_failed={}",
        job.job_id,
        group_name,
        saved_count,
        uploaded_images,
        failed_images,
    )
    return saved_count


async def upsert_zalo_account(
    account_id: str,
    *,
    owner_id: str = "default",
    label: Optional[str] = None,
    phone: Optional[str] = None,
    status: str = "unknown",
    zalo_id: Optional[str] = None,
    avatar_url: Optional[str] = None,
    is_active: bool = True,
) -> None:
    if not is_supabase_configured():
        return

    now = datetime.utcnow().isoformat()
    payload: Dict[str, Any] = {
        "account_id": account_id,
        "owner_id": owner_id or "default",
        "label": label or account_id,
        "phone": phone,
        "zalo_id": zalo_id,
        "avatar_url": avatar_url,
        "status": status,
        "is_active": is_active,
        "last_seen_at": now,
        "updated_at": now,
    }
    if status == "confirmed":
        payload["last_login_at"] = now

    try:
        await _rest(
            "POST",
            "zalo_accounts",
            json=[payload],
            params={"on_conflict": "account_id"},
            prefer="resolution=merge-duplicates",
        )
    except RuntimeError as exc:
        if "zalo_accounts" in str(exc):
            logger.warning(f"zalo_accounts table is not ready; skipping account upsert: {exc}")
            return
        raise


async def list_zalo_accounts(owner_id: Optional[str] = None) -> List[Dict[str, Any]]:
    if not is_supabase_configured():
        return []

    params: Dict[str, Any] = {"select": "*", "is_active": "eq.true", "order": "updated_at.desc"}
    if owner_id:
        params["owner_id"] = f"eq.{owner_id}"
    try:
        return await _rest("GET", "zalo_accounts", params=params) or []
    except RuntimeError as exc:
        if "zalo_accounts" in str(exc):
            logger.warning(f"zalo_accounts table is not ready; returning empty account list: {exc}")
            return []
        raise


async def delete_zalo_account(account_id: str) -> None:
    if not is_supabase_configured():
        return
    try:
        await _rest("PATCH", "zalo_accounts", params={"account_id": f"eq.{account_id}"}, json={"is_active": False, "updated_at": datetime.utcnow().isoformat()})
    except RuntimeError as exc:
        if "zalo_accounts" in str(exc):
            return
        raise


async def get_zalo_inbox_report(
    account_ids: Optional[List[str]] = None,
    *,
    owner_id: Optional[str] = None,
    limit: int = 1000,
) -> Dict[str, Any]:
    _require_configured()
    accounts = await list_zalo_accounts(owner_id)
    account_by_id = {str(row.get("account_id")): row for row in accounts}

    selected_ids = [item for item in (account_ids or []) if item]
    if not selected_ids:
        selected_ids = list(account_by_id.keys())
    if not selected_ids:
        return {"accounts": [], "customers": [], "total_messages": 0, "total_customers": 0}

    params = {
        "select": "id,user_id,group_id,group_name,source_message_id,sender_id,sender_name,timestamp_text,time_text,type,content,is_sent,created_at",
        "user_id": f"in.({','.join(selected_ids)})",
        "is_deleted": "eq.false",
        "order": "created_at.desc",
        "limit": str(max(1, min(limit, 5000))),
    }
    rows = await _rest("GET", "zalo_messages", params=params) or []

    account_stats: Dict[str, Dict[str, Any]] = {}
    customer_stats: Dict[Tuple[str, str], Dict[str, Any]] = {}
    for row in rows:
        account_id = str(row.get("user_id") or "default")
        account = account_by_id.get(account_id) or {"account_id": account_id, "label": account_id}
        acc = account_stats.setdefault(
            account_id,
            {
                "account_id": account_id,
                "label": account.get("label") or account_id,
                "owner_id": account.get("owner_id") or owner_id or "default",
                "message_count": 0,
                "customer_count": 0,
                "latest_message_at": None,
            },
        )
        acc["message_count"] += 1
        if not acc["latest_message_at"]:
            acc["latest_message_at"] = row.get("created_at")

        customer_id = str(row.get("group_id") or row.get("sender_id") or row.get("group_name") or "unknown")
        key = (account_id, customer_id)
        customer = customer_stats.setdefault(
            key,
            {
                "account_id": account_id,
                "account_label": account.get("label") or account_id,
                "customer_id": customer_id,
                "customer_name": row.get("group_name") or row.get("sender_name") or customer_id,
                "conversation_id": row.get("group_id"),
                "conversation_name": row.get("group_name"),
                "message_count": 0,
                "sent_count": 0,
                "received_count": 0,
                "latest_message_at": None,
                "latest_content": None,
            },
        )
        customer["message_count"] += 1
        if row.get("is_sent"):
            customer["sent_count"] += 1
        else:
            customer["received_count"] += 1
        if not customer["latest_message_at"]:
            customer["latest_message_at"] = row.get("created_at")
            customer["latest_content"] = row.get("content")

    for account_id in account_stats:
        account_stats[account_id]["customer_count"] = sum(1 for key in customer_stats if key[0] == account_id)

    customers = sorted(customer_stats.values(), key=lambda item: item.get("latest_message_at") or "", reverse=True)
    accounts_out = sorted(account_stats.values(), key=lambda item: item.get("latest_message_at") or "", reverse=True)
    return {
        "accounts": accounts_out,
        "customers": customers,
        "total_messages": sum(item["message_count"] for item in accounts_out),
        "total_customers": len(customers),
    }


async def save_listener_messages(
    user_id: str,
    group_id: str,
    group_name: str,
    messages: Iterable[Message],
    *,
    increment_unread: bool = True,
) -> int:
    if not is_supabase_configured():
        return 0

    safe_group_name = group_name or group_id
    messages_list = list(messages)

    unread_inc = 0
    if increment_unread:
        for msg in messages_list:
            if not msg.is_sent:
                unread_inc += 1

    current_unread = 0
    if unread_inc > 0:
        try:
            group_rows = await _rest(
                "GET",
                "zalo_groups",
                params={
                    "select": "unread_count",
                    "user_id": f"eq.{user_id}",
                    "group_id": f"eq.{group_id}",
                    "limit": "1",
                },
            ) or []
            if group_rows:
                current_unread = int(group_rows[0].get("unread_count") or 0)
        except Exception as exc:
            logger.warning(f"Could not fetch current unread count for group={group_id}: {exc}")

    # Tìm tin nhắn mới nhất theo timestamp để update group metadata.
    last_message = None
    if messages_list:
        last_message = max(
            messages_list,
            key=lambda msg: _parse_to_millis(msg.timestamp) or _parse_to_millis(msg.time_text),
        )

    last_message_at_value = None
    if last_message:
        ts_ms = _parse_to_millis(last_message.timestamp) or _parse_to_millis(last_message.time_text)
        if ts_ms > 0:
            last_message_at_value = datetime.utcfromtimestamp(ts_ms / 1000).isoformat() + "Z"

    await upsert_group(
        user_id=user_id,
        group_id=group_id,
        group_name=safe_group_name,
        unread_count=(current_unread + unread_inc) if unread_inc > 0 else None,
        last_message_at=last_message_at_value,
        last_message_content=last_message.content if last_message else None,
        last_sender_id=last_message.sender_id if last_message else None,
        last_sender_name=last_message.sender_name if last_message else None,
        last_message_type=last_message.type if last_message else None,
    )

    saved_count = 0
    uploaded_images = 0
    failed_images = 0
    for msg in messages_list:
        if not msg.message_id:
            continue
        rows = await _rest(
            "POST",
            "zalo_messages",
            json=[_listener_message_payload(user_id, group_id, safe_group_name, msg)],
            params={"on_conflict": "user_id,group_id,source_message_id"},
            prefer="resolution=merge-duplicates,return=representation",
        )
        if not rows:
            continue
        saved_count += 1
        message_uuid = rows[0]["id"]
        asset_stats = await save_message_assets(message_uuid, user_id, None, msg.image_urls)
        uploaded_images += asset_stats["uploaded"]
        failed_images += asset_stats["failed"]

    if saved_count:
        logger.info(
            "Saved Zalo listener messages: user={} group={!r} messages={} images_uploaded={} images_failed={}",
            user_id,
            safe_group_name,
            saved_count,
            uploaded_images,
            failed_images,
        )
    return saved_count


async def save_global_listener_messages(
    user_id: str,
    messages: Iterable[Message],
) -> int:
    if not is_supabase_configured():
        return 0

    from collections import defaultdict
    grouped = defaultdict(list)
    for msg in messages:
        g_id = getattr(msg, "group_id", None) or ""
        if g_id:
            grouped[g_id].append(msg)

    total_saved = 0
    for g_id, g_messages in grouped.items():
        group_rows = await _rest(
            "GET",
            "zalo_groups",
            params={
                "select": "group_name",
                "user_id": f"eq.{user_id}",
                "group_id": f"eq.{g_id}",
                "limit": "1",
            },
        ) or []
        g_name = group_rows[0].get("group_name") if group_rows else g_id
        
        saved = await save_listener_messages(user_id, g_id, g_name, g_messages)
        total_saved += saved

    return total_saved



async def list_recent_messages_for_group(
    user_id: str,
    group_id: str,
    limit: int = 500,
) -> List[Message]:
    if not is_supabase_configured():
        return []
    safe_limit = max(1, min(int(limit or 500), 1000))
    rows = await _rest(
        "GET",
        "zalo_messages",
        params={
            "select": "*,assets:zalo_message_assets(*)",
            "user_id": f"eq.{user_id}",
            "group_id": f"eq.{group_id}",
            "is_deleted": "eq.false",
            "order": "created_at.desc",
            "limit": str(safe_limit),
        },
    ) or []
    messages = [_message_from_row(row) for row in rows]
    return [message for message in messages if message.message_id]


async def save_message_assets(
    message_uuid: str,
    user_id: str,
    job_id: Optional[str],
    source_urls: Iterable[str],
) -> Dict[str, int]:
    stats = {"uploaded": 0, "failed": 0}
    existing_assets = {}
    try:
        rows = await _rest(
            "GET",
            "zalo_message_assets",
            params={
                "select": "source_url,status",
                "message_id": f"eq.{message_uuid}",
            }
        ) or []
        existing_assets = {r["source_url"]: r["status"] for r in rows}
    except Exception as exc:
        logger.warning(f"Could not pre-fetch existing zalo_message_assets for message {message_uuid}: {exc}")

    for source_url in source_urls:
        status = "pending"
        storage_path = None
        storage_url = None
        error = None
        source_url_ref = source_url

        if source_url.startswith("data:image/"):
            # Normalize data URL structure to match source_url_ref hash check
            try:
                content, content_type, ext = await _download_image(source_url)
                source_url_ref = f"data:{content_type};sha256={hashlib.sha256(content).hexdigest()}"
            except Exception:
                pass

        if existing_assets.get(source_url_ref) == "uploaded":
            continue

        if source_url.startswith("blob:"):
            status = "failed"
            error = "Blob URL is browser-local and cannot be persisted after crawl"
        else:
            try:
                content, content_type, ext = await _download_image(source_url)
                if source_url.startswith("data:image/"):
                    source_url_ref = f"data:{content_type};sha256={hashlib.sha256(content).hexdigest()}"
                storage_path = posixpath.join(
                    user_id,
                    job_id or "manual",
                    f"{message_uuid}-{uuid.uuid4().hex}{ext}",
                )
                storage_url = await upload_asset_bytes(storage_path, content, content_type)
                status = "uploaded"
                stats["uploaded"] += 1
            except Exception as exc:
                logger.warning(f"Could not persist Zalo image {source_url}: {exc}")
                status = "failed"
                error = str(exc)
                stats["failed"] += 1
        if status == "failed" and source_url.startswith("blob:"):
            stats["failed"] += 1

        await _rest(
            "POST",
            "zalo_message_assets",
            json=[
                {
                    "message_id": message_uuid,
                    "source_url": source_url_ref,
                    "storage_path": storage_path,
                    "storage_url": storage_url,
                    "status": status,
                    "error": error,
                    "updated_at": datetime.utcnow().isoformat(),
                }
            ],
            params={"on_conflict": "message_id,source_url"},
            prefer="resolution=merge-duplicates",
        )
    return stats


async def list_library_messages(
    user_id: str,
    group_name: Optional[str] = None,
    limit: int = 200,
    offset: int = 0,
    content_kind: str = "all",
) -> Tuple[List[Dict[str, Any]], int]:
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)
    select_clause = "*,assets:zalo_message_assets(*)"
    if content_kind == "image":
        select_clause = "*,assets:zalo_message_assets!inner(*)"
    params: Dict[str, Any] = {
        "select": select_clause,
        "user_id": f"eq.{user_id}",
        "is_deleted": "eq.false",
        "order": "created_at.desc",
        "limit": str(safe_limit),
        "offset": str(safe_offset),
    }
    if group_name:
        params["group_name"] = f"ilike.*{group_name}*"
    if content_kind == "text":
        params["content"] = "not.is.null"
    if content_kind == "image":
        params["assets.status"] = "eq.uploaded"
    rows, total = await _rest_with_count("zalo_messages", params=params)
    if group_name and not rows:
        job_rows = await _rest(
            "GET",
            "zalo_crawl_jobs",
            params={
                "select": "job_id",
                "user_id": f"eq.{user_id}",
                "group_name": f"ilike.*{group_name}*",
                "limit": "200",
            },
        ) or []
        job_ids = [
            str(job.get("job_id") or "").strip()
            for job in job_rows
            if str(job.get("job_id") or "").strip()
        ]
        if job_ids:
            fallback_params = dict(params)
            fallback_params.pop("group_name", None)
            fallback_params["job_id"] = "in.(" + ",".join(f'"{job_id}"' for job_id in job_ids) + ")"
            rows, total = await _rest_with_count("zalo_messages", params=fallback_params)
    hydrated_rows = await hydrate_message_groups_from_jobs(user_id, rows or [])
    return hydrated_rows, total


def _normalize_iso_timestamp(val: Any) -> Optional[str]:
    """Chuẩn hóa giá trị thời gian (epoch ms/s hoặc ISO) về ISO-8601 UTC cho cột timestamptz."""
    if val is None or val == "":
        return None
    if isinstance(val, str) and not val.strip().isdigit():
        # Đã là ISO hoặc text -> giữ nguyên, để Postgres tự parse.
        return val
    ms = _parse_to_millis(val)
    if ms <= 0:
        return None
    return datetime.utcfromtimestamp(ms / 1000).isoformat() + "Z"


def _parse_to_millis(val: Any) -> int:
    if not val:
        return 0
    val_str = str(val).strip()
    if val_str.isdigit():
        return int(val_str)
    try:
        normalized = val_str
        if normalized.endswith("Z"):
            normalized = normalized[:-1] + "+00:00"
        dt = datetime.fromisoformat(normalized)
        return int(dt.timestamp() * 1000)
    except Exception:
        pass
    return 0


async def list_conversations(user_id: str, limit: int = 500) -> List[Dict[str, Any]]:
    # 1. Fetch group mappings from zalo_groups
    group_rows = await _rest(
        "GET",
        "zalo_groups",
        params={
            "select": (
                "group_id,group_name,avatar_url,unread_count,updated_at,"
                "last_message_at,last_message_content,last_sender_id,"
                "last_sender_name,last_message_type,is_pinned"
            ),
            "user_id": f"eq.{user_id}",
            "order": "is_pinned.desc,last_message_at.desc,updated_at.desc",
            "limit": "5000",
        },
    ) or []

    group_info = {}
    group_name_to_id = {}
    for g in group_rows:
        g_id = str(g.get("group_id") or "").strip()
        g_name = str(g.get("group_name") or "").strip()
        if g_id:
            group_info[g_id] = {
                "avatar_url": g.get("avatar_url"),
                "unread_count": int(g.get("unread_count") or 0),
                "updated_at": g.get("updated_at"),
                "last_message_at": g.get("last_message_at"),
                "last_message_content": g.get("last_message_content"),
                "last_sender_name": g.get("last_sender_name"),
                "last_message_type": g.get("last_message_type"),
                "is_pinned": bool(g.get("is_pinned")),
            }
            if g_name:
                group_name_to_id[g_name.lower()] = g_id

    # 2. Fetch up to 1000 recent messages for aggregation
    rows = await _rest(
        "GET",
        "zalo_messages",
        params={
            "select": "id,user_id,group_id,group_name,sender_name,created_at,timestamp_text,time_text,type,content,is_sent",
            "user_id": f"eq.{user_id}",
            "is_deleted": "eq.false",
            "order": "created_at.desc",
            "limit": "1000",
        },
    ) or []
    rows = await hydrate_message_groups_from_jobs(user_id, rows)

    # Supplement name-to-id mapping dynamically from recent message rows that have both fields
    for row in rows:
        g_id = str(row.get("group_id") or "").strip()
        g_name = str(row.get("group_name") or "").strip()
        if g_id and g_name:
            group_name_to_id[g_name.lower()] = g_id

    conversations: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        g_id = str(row.get("group_id") or "").strip()
        g_name = str(row.get("group_name") or "").strip()
        
        # Unify by mapping empty group_id using known group name
        if not g_id and g_name:
            g_id = group_name_to_id.get(g_name.lower(), "")
            
        conversation_id = g_id or g_name
        if not conversation_id:
            continue
            
        raw_group_name = g_name
        sender_name = str(row.get("sender_name") or "").strip()
        is_fallback_name = (
            not raw_group_name
            or raw_group_name == conversation_id
            or raw_group_name == f"Conversation {conversation_id}"
        )
        usable_sender_name = (
            bool(sender_name)
            and not row.get("is_sent")
            and sender_name.lower() not in {"__me__", "me", "ban", "bạn"}
        )
        conversation_name = (
            sender_name
            if is_fallback_name and usable_sender_name
            else raw_group_name or f"Conversation {conversation_id}"
        )
        current = conversations.setdefault(
            conversation_id,
            {
                "conversation_id": conversation_id,
                "conversation_name": conversation_name,
                "account_id": user_id,
                "message_count": 0,
                "image_count": 0,
                "sent_count": 0,
                "received_count": 0,
                "latest_message_at": None,
                "latest_content": None,
                "latest_sender_name": None,
                "has_messages": True,
                "sync_status": "has_messages",
                "avatar_url": group_info.get(conversation_id, {}).get("avatar_url"),
                "unread_count": group_info.get(conversation_id, {}).get("unread_count", 0),
                "updated_at": group_info.get(conversation_id, {}).get("updated_at"),
                "is_pinned": group_info.get(conversation_id, {}).get("is_pinned", False),
            },
        )
        if is_fallback_name and usable_sender_name:
            current["conversation_name"] = sender_name
        current["message_count"] += 1
        current["image_count"] += sum(
            1 for asset in row.get("assets") or [] if asset.get("status") == "uploaded"
        )
        if row.get("is_sent"):
            current["sent_count"] += 1
        else:
            current["received_count"] += 1
        if not current["latest_message_at"]:
            current["latest_message_at"] = row.get("created_at") or row.get("timestamp_text") or row.get("time_text")
            current["latest_content"] = row.get("content")
            current["latest_sender_name"] = row.get("sender_name")

    # 3. Add any groups that exist in zalo_groups but have no recent messages in our 3000-message window
    for group in group_rows:
        conversation_id = str(group.get("group_id") or group.get("group_name") or "").strip()
        if not conversation_id or conversation_id in conversations:
            continue
        conversation_name = str(group.get("group_name") or "").strip() or f"Conversation {conversation_id}"
        conversations[conversation_id] = {
            "conversation_id": conversation_id,
            "conversation_name": conversation_name,
            "account_id": user_id,
            "message_count": 0,
            "image_count": 0,
            "sent_count": 0,
            "received_count": 0,
            "latest_message_at": None,
            "latest_content": None,
            "latest_sender_name": None,
            "has_messages": False,
            "sync_status": "known_empty",
            "avatar_url": group.get("avatar_url"),
            "unread_count": int(group.get("unread_count") or 0),
            "updated_at": group.get("updated_at"),
            "is_pinned": bool(group.get("is_pinned")),
        }

    # 4. Overlay metadata chính xác từ zalo_groups (last_message_at thật của tin nhắn).
    #    Cột này được listener cập nhật realtime nên là nguồn tin cậy nhất cho preview + sort.
    for conversation_id, info in group_info.items():
        conv = conversations.get(conversation_id)
        if not conv:
            continue
        group_last_at = info.get("last_message_at")
        if group_last_at and _parse_to_millis(group_last_at) >= _parse_to_millis(conv.get("latest_message_at")):
            conv["latest_message_at"] = group_last_at
            if info.get("last_message_content"):
                conv["latest_content"] = info.get("last_message_content")
            if info.get("last_sender_name"):
                conv["latest_sender_name"] = info.get("last_sender_name")
        conv["is_pinned"] = info.get("is_pinned", conv.get("is_pinned", False))

    def _sort_key(item: Dict[str, Any]):
        real_ms = _parse_to_millis(item.get("latest_message_at"))
        return (
            1 if item.get("is_pinned") else 0,
            # Group có tin nhắn thật luôn xếp trên group rỗng (chỉ có updated_at).
            1 if real_ms > 0 else 0,
            real_ms or _parse_to_millis(item.get("updated_at")),
            str(item.get("conversation_name") or "").lower(),
        )

    return sorted(conversations.values(), key=_sort_key, reverse=True)


async def list_conversation_messages(
    user_id: str,
    conversation_id: str,
    limit: int = 100,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], int]:
    safe_limit = max(1, min(limit, 500))
    safe_offset = max(0, offset)

    # Resolve group_id and group_name mappings from zalo_groups
    resolved_group_id = None
    resolved_group_name = None

    is_numeric_id = conversation_id.isdigit() or (conversation_id.startswith("-") and conversation_id[1:].isdigit())
    
    mapping_rows = []
    try:
        if is_numeric_id:
            mapping_rows = await _rest(
                "GET",
                "zalo_groups",
                params={
                    "select": "group_id,group_name",
                    "user_id": f"eq.{user_id}",
                    "group_id": f"eq.{conversation_id}",
                }
            ) or []
        else:
            mapping_rows = await _rest(
                "GET",
                "zalo_groups",
                params={
                    "select": "group_id,group_name",
                    "user_id": f"eq.{user_id}",
                    "group_name": f"eq.{conversation_id}",
                }
            ) or []
    except Exception as exc:
        logger.warning(f"Failed to fetch zalo_groups mapping in messages view: {exc}")

    if mapping_rows:
        resolved_group_id = mapping_rows[0].get("group_id")
        resolved_group_name = mapping_rows[0].get("group_name")

    # Fallback scan messages if not found in mapping
    if not resolved_group_id or not resolved_group_name:
        try:
            if is_numeric_id:
                msg_rows = await _rest(
                    "GET",
                    "zalo_messages",
                    params={
                        "select": "group_name",
                        "user_id": f"eq.{user_id}",
                        "group_id": f"eq.{conversation_id}",
                        "limit": "1",
                    }
                ) or []
                if msg_rows and msg_rows[0].get("group_name"):
                    resolved_group_id = conversation_id
                    resolved_group_name = msg_rows[0].get("group_name")
            else:
                msg_rows = await _rest(
                    "GET",
                    "zalo_messages",
                    params={
                        "select": "group_id",
                        "user_id": f"eq.{user_id}",
                        "group_name": f"eq.{conversation_id}",
                        "group_id": "not.is.null",
                        "limit": "1",
                    }
                ) or []
                if msg_rows and msg_rows[0].get("group_id"):
                    resolved_group_id = msg_rows[0].get("group_id")
                    resolved_group_name = conversation_id
        except Exception as exc:
            logger.warning(f"Failed to scan zalo_messages mapping in messages view: {exc}")

    if not resolved_group_id and is_numeric_id:
        resolved_group_id = conversation_id
    if not resolved_group_name and not is_numeric_id:
        resolved_group_name = conversation_id

    # Query messages using or-filter to aggregate both group_id and group_name
    query_params = {
        "select": "*,assets:zalo_message_assets(*)",
        "user_id": f"eq.{user_id}",
        "is_deleted": "eq.false",
        "order": "created_at.desc",
        "limit": str(safe_limit),
        "offset": str(safe_offset),
    }

    if resolved_group_id and resolved_group_name:
        escaped_name = resolved_group_name.replace('"', '\\"')
        query_params["or"] = f'(group_id.eq.{resolved_group_id},group_name.eq."{escaped_name}")'
    elif resolved_group_id:
        query_params["group_id"] = f"eq.{resolved_group_id}"
    else:
        query_params["group_name"] = f"eq.{resolved_group_name}"

    rows, total = await _rest_with_count("zalo_messages", params=query_params)
    hydrated_rows = await hydrate_message_groups_from_jobs(user_id, rows or [])
    hydrated_rows.reverse()
    return hydrated_rows, total


def group_summaries_from_message_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    groups_by_name: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        group_name = str(row.get("group_name") or "").strip()
        if not group_name:
            continue
        key = group_name.lower()
        item = groups_by_name.setdefault(
            key,
            {
                "group_name": group_name,
                "sheet_tab": group_name,
                "message_count": 0,
                "image_count": 0,
                "latest_message_at": row.get("created_at"),
            },
        )
        item["message_count"] += 1
        item["image_count"] += sum(
            1 for asset in row.get("assets") or [] if asset.get("status") == "uploaded"
        )
        if not item.get("latest_message_at"):
            item["latest_message_at"] = row.get("created_at")
    return list(groups_by_name.values())


def _group_key(value: Any) -> str:
    return str(value or "").strip().lower()


def _merge_group_summary(
    groups_by_name: Dict[str, Dict[str, Any]],
    *,
    group_name: str,
    message_count: int = 0,
    image_count: int = 0,
    latest_message_at: Any = None,
    prefer_counts: bool = False,
) -> None:
    clean_name = str(group_name or "").strip()
    if not clean_name:
        return
    key = _group_key(clean_name)
    current = groups_by_name.setdefault(
        key,
        {
            "group_name": clean_name,
            "sheet_tab": clean_name,
            "message_count": 0,
            "image_count": 0,
            "latest_message_at": latest_message_at,
        },
    )
    if prefer_counts:
        current["message_count"] = max(int(current.get("message_count") or 0), int(message_count or 0))
        current["image_count"] = max(int(current.get("image_count") or 0), int(image_count or 0))
    else:
        current["message_count"] = int(current.get("message_count") or 0) + int(message_count or 0)
        current["image_count"] = int(current.get("image_count") or 0) + int(image_count or 0)
    if latest_message_at and not current.get("latest_message_at"):
        current["latest_message_at"] = latest_message_at


async def hydrate_message_groups_from_jobs(
    user_id: str,
    rows: List[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    missing_job_ids = sorted(
        {
            str(row.get("job_id") or "").strip()
            for row in rows
            if not str(row.get("group_name") or "").strip() and str(row.get("job_id") or "").strip()
        }
    )
    if not missing_job_ids:
        return rows

    quoted_job_ids = ",".join(f'"{job_id}"' for job_id in missing_job_ids)
    job_rows = await _rest(
        "GET",
        "zalo_crawl_jobs",
        params={
            "select": "job_id,group_id,group_name",
            "user_id": f"eq.{user_id}",
            "job_id": f"in.({quoted_job_ids})",
        },
    ) or []
    jobs_by_id = {
        str(job.get("job_id") or ""): job
        for job in job_rows
        if str(job.get("job_id") or "")
    }
    if not jobs_by_id:
        return rows

    hydrated: List[Dict[str, Any]] = []
    for row in rows:
        next_row = dict(row)
        if not str(next_row.get("group_name") or "").strip():
            job = jobs_by_id.get(str(next_row.get("job_id") or ""))
            if job:
                next_row["group_name"] = job.get("group_name") or next_row.get("group_name")
                next_row["group_id"] = next_row.get("group_id") or job.get("group_id")
        hydrated.append(next_row)
    return hydrated


async def list_library_group_summaries(user_id: str = "default") -> List[Dict[str, Any]]:
    groups_by_name: Dict[str, Dict[str, Any]] = {}

    job_rows = await _rest(
        "GET",
        "zalo_crawl_jobs",
        params={
            "select": "group_name,messages_collected,images_found,completed_at,updated_at,started_at",
            "user_id": f"eq.{user_id}",
            "order": "updated_at.desc",
            "limit": "10000",
        },
    ) or []
    for job in job_rows:
        latest_at = job.get("completed_at") or job.get("updated_at") or job.get("started_at")
        _merge_group_summary(
            groups_by_name,
            group_name=str(job.get("group_name") or ""),
            message_count=int(job.get("messages_collected") or 0),
            image_count=int(job.get("images_found") or 0),
            latest_message_at=latest_at,
            prefer_counts=False,
        )

    rows = await _rest(
        "GET",
        "zalo_messages",
        params={
            "select": "job_id,group_id,group_name,created_at,assets:zalo_message_assets(status)",
            "user_id": f"eq.{user_id}",
            "is_deleted": "eq.false",
            "order": "created_at.desc",
            "limit": "10000",
        },
    ) or []
    rows = await hydrate_message_groups_from_jobs(user_id, rows)
    message_groups = group_summaries_from_message_rows(rows)
    for group in message_groups:
        _merge_group_summary(
            groups_by_name,
            group_name=str(group.get("group_name") or ""),
            message_count=int(group.get("message_count") or 0),
            image_count=int(group.get("image_count") or 0),
            latest_message_at=group.get("latest_message_at"),
            prefer_counts=True,
        )
    return sorted(
        groups_by_name.values(),
        key=lambda item: str(item.get("latest_message_at") or ""),
        reverse=True,
    )


async def _message_group_counts(user_id: str = "default") -> Dict[str, Dict[str, Any]]:
    rows = await _rest(
        "GET",
        "zalo_messages",
        params={
            "select": "job_id,group_id,group_name,created_at,assets:zalo_message_assets(status)",
            "user_id": f"eq.{user_id}",
            "is_deleted": "eq.false",
            "order": "created_at.desc",
            "limit": "10000",
        },
    ) or []
    rows = await hydrate_message_groups_from_jobs(user_id, rows)
    return {
        _group_key(group.get("group_name")): group
        for group in group_summaries_from_message_rows(rows)
        if _group_key(group.get("group_name"))
    }


async def list_saved_groups(user_id: str = "default") -> List[Dict[str, Any]]:
    groups_by_name: Dict[str, Dict[str, Any]] = {}
    job_rows = await _rest(
        "GET",
        "zalo_crawl_jobs",
        params={
            "select": "group_name,messages_collected,images_found,completed_at,updated_at,started_at",
            "user_id": f"eq.{user_id}",
            "order": "updated_at.desc",
            "limit": "10000",
        },
    ) or []
    for job in job_rows:
        latest_at = job.get("completed_at") or job.get("updated_at") or job.get("started_at")
        _merge_group_summary(
            groups_by_name,
            group_name=str(job.get("group_name") or ""),
            message_count=int(job.get("messages_collected") or 0),
            image_count=int(job.get("images_found") or 0),
            latest_message_at=latest_at,
        )

    for group in (await _message_group_counts(user_id)).values():
        _merge_group_summary(
            groups_by_name,
            group_name=str(group.get("group_name") or ""),
            message_count=int(group.get("message_count") or 0),
            image_count=int(group.get("image_count") or 0),
            latest_message_at=group.get("latest_message_at"),
            prefer_counts=True,
        )

    return sorted(
        groups_by_name.values(),
        key=lambda item: str(item.get("latest_message_at") or ""),
        reverse=True,
    )


async def cleanup_expired_assets(retention_days: int, limit: int) -> Dict[str, Any]:
    cutoff = datetime.utcnow() - timedelta(days=max(1, retention_days))
    batch_limit = max(1, min(limit, 1000))
    rows = await _rest(
        "GET",
        "zalo_message_assets",
        params={
            "select": "id,storage_path,storage_url,status,created_at",
            "status": "eq.uploaded",
            "storage_path": "not.is.null",
            "created_at": f"lt.{cutoff.isoformat()}",
            "order": "created_at.asc",
            "limit": str(batch_limit),
        },
    ) or []

    deleted = 0
    expired = 0
    failed: List[Dict[str, Any]] = []

    for row in rows:
        asset_id = row.get("id")
        storage_path = row.get("storage_path")
        if not asset_id:
            continue
        try:
            if storage_path:
                await delete_storage_objects([storage_path])
                deleted += 1
            await _rest(
                "PATCH",
                "zalo_message_assets",
                params={"id": f"eq.{asset_id}"},
                json={
                    "status": "expired",
                    "storage_path": None,
                    "storage_url": None,
                    "error": None,
                    "updated_at": datetime.utcnow().isoformat(),
                },
            )
            expired += 1
        except Exception as exc:
            logger.warning(f"Could not cleanup Zalo asset {asset_id}: {exc}")
            failed.append({"id": asset_id, "storage_path": storage_path, "error": str(exc)})

    return {
        "cutoff": cutoff.isoformat(),
        "scanned": len(rows),
        "deleted_storage_objects": deleted,
        "expired_assets": expired,
        "failed": failed,
    }


async def fetch_messages_by_ids(
    user_id: str,
    message_ids: List[str],
    *,
    include_deleted: bool = False,
) -> List[Dict[str, Any]]:
    if not message_ids:
        return []
    quoted_ids = ",".join(message_ids)
    params = {
        "select": "*,assets:zalo_message_assets(*)",
        "user_id": f"eq.{user_id}",
        "id": f"in.({quoted_ids})",
    }
    if not include_deleted:
        params["is_deleted"] = "eq.false"
    return await _rest(
        "GET",
        "zalo_messages",
        params=params,
    ) or []


async def create_library_message(user_id: str, payload: Dict[str, Any], asset_urls: List[str]) -> Dict[str, Any]:
    rows = await _rest(
        "POST",
        "zalo_messages",
        json=[
            {
                "user_id": user_id,
                "group_name": payload.get("group_name"),
                "sender_name": payload.get("sender_name"),
                "time_text": payload.get("time_text"),
                "type": payload.get("type") or "text",
                "content": payload.get("content"),
                "source_message_id": f"manual-{uuid.uuid4()}",
            }
        ],
        prefer="return=representation",
    )
    row = rows[0]
    await save_message_assets(row["id"], user_id, None, asset_urls)
    return (await fetch_messages_by_ids(user_id, [row["id"]]))[0]


async def update_library_message(user_id: str, message_id: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    payload = {key: value for key, value in payload.items() if value is not None}
    payload["updated_at"] = datetime.utcnow().isoformat()
    include_deleted = payload.get("is_deleted") is True
    rows = await _rest(
        "PATCH",
        "zalo_messages",
        params={"id": f"eq.{message_id}", "user_id": f"eq.{user_id}"},
        json=payload,
        prefer="return=representation",
    )
    if not rows:
        raise KeyError(message_id)
    fetched = await fetch_messages_by_ids(user_id, [message_id], include_deleted=include_deleted)
    return fetched[0] if fetched else rows[0]


async def bulk_delete_library_messages(
    user_id: str,
    *,
    message_ids: Optional[List[str]] = None,
    group_name: Optional[str] = None,
    delete_all_matching: bool = False,
) -> int:
    payload = {"is_deleted": True, "updated_at": datetime.utcnow().isoformat()}
    params: Dict[str, Any] = {"user_id": f"eq.{user_id}", "is_deleted": "eq.false"}
    ids = [message_id for message_id in (message_ids or []) if message_id]
    if delete_all_matching:
        if group_name:
            params["group_name"] = f"ilike.*{group_name}*"
    else:
        if not ids:
            return 0
        params["id"] = f"in.({','.join(ids)})"

    rows = await _rest(
        "PATCH",
        "zalo_messages",
        params=params,
        json=payload,
        prefer="return=representation",
    )
    return len(rows or [])


async def create_broadcast_campaign(
    user_id: str,
    content_mode: str,
    message_ids: List[str],
    targets: List[Dict[str, Any]],
) -> str:
    campaign_id = str(uuid.uuid4())
    await _rest(
        "POST",
        "zalo_broadcast_campaigns",
        json=[
            {
                "id": campaign_id,
                "user_id": user_id,
                "status": "queued",
                "content_mode": content_mode,
                "message_count": len(message_ids),
                "target_count": len(targets),
            }
        ],
    )
    if targets:
        await _rest(
            "POST",
            "zalo_broadcast_targets",
            json=[
                {
                    "campaign_id": campaign_id,
                    "group_id": target.get("group_id"),
                    "group_name": target["group_name"],
                    "status": "queued",
                }
                for target in targets
            ],
        )
    if message_ids:
        await _rest(
            "POST",
            "zalo_broadcast_items",
            json=[
                {
                    "campaign_id": campaign_id,
                    "message_id": message_id,
                    "position": index,
                    "status": "queued",
                }
                for index, message_id in enumerate(message_ids)
            ],
        )
    return campaign_id


async def update_campaign_status(campaign_id: str, status: str, error: Optional[str] = None) -> None:
    payload: Dict[str, Any] = {"status": status, "updated_at": datetime.utcnow().isoformat()}
    if status in {"completed", "failed"}:
        payload["completed_at"] = datetime.utcnow().isoformat()
    if error:
        payload["error"] = error
    await _rest("PATCH", "zalo_broadcast_campaigns", params={"id": f"eq.{campaign_id}"}, json=payload)


async def add_broadcast_log(
    campaign_id: str,
    group_name: str,
    status: str,
    detail: Optional[str] = None,
    message_id: Optional[str] = None,
) -> None:
    await _rest(
        "POST",
        "zalo_broadcast_logs",
        json=[
            {
                "campaign_id": campaign_id,
                "group_name": group_name,
                "message_id": message_id,
                "status": status,
                "detail": detail,
            }
        ],
    )


async def get_broadcast_status(campaign_id: str) -> Dict[str, Any]:
    campaigns = await _rest("GET", "zalo_broadcast_campaigns", params={"id": f"eq.{campaign_id}"}) or []
    if not campaigns:
        raise KeyError(campaign_id)
    targets = await _rest("GET", "zalo_broadcast_targets", params={"campaign_id": f"eq.{campaign_id}", "order": "created_at.asc"}) or []
    items = await _rest("GET", "zalo_broadcast_items", params={"campaign_id": f"eq.{campaign_id}", "order": "position.asc"}) or []
    logs = await _rest("GET", "zalo_broadcast_logs", params={"campaign_id": f"eq.{campaign_id}", "order": "created_at.asc"}) or []
    return {"campaign": campaigns[0], "targets": targets, "items": items, "logs": logs}


async def mark_conversation_as_read(user_id: str, group_id: str) -> None:
    if not is_supabase_configured():
        return
    await _rest(
        "PATCH",
        "zalo_groups",
        params={
            "user_id": f"eq.{user_id}",
            "group_id": f"eq.{group_id}",
        },
        json={
            "unread_count": 0,
            "updated_at": datetime.utcnow().isoformat(),
        },
    )
