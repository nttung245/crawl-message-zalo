from __future__ import annotations

import mimetypes
import posixpath
import uuid
import base64
import hashlib
from datetime import datetime, timedelta
from typing import Any, Iterable
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


def _headers(extra: dict[str, str] | None = None) -> dict[str, str]:
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
    params: dict[str, Any] | None = None,
    json: Any | None = None,
    prefer: str | None = None,
) -> Any:
    _require_configured()
    headers = _headers({"Prefer": prefer} if prefer else None)
    url = f"{_base_url()}/rest/v1/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=60) as client:
        response = await client.request(method, url, headers=headers, params=params, json=json)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase {method} {path} failed: {response.status_code} {response.text}")
    if not response.content:
        return None
    return response.json()


async def _rest_with_count(
    path: str,
    *,
    params: dict[str, Any] | None = None,
) -> tuple[Any, int]:
    _require_configured()
    headers = _headers({"Prefer": "count=exact"})
    url = f"{_base_url()}/rest/v1/{path.lstrip('/')}"
    async with httpx.AsyncClient(timeout=60) as client:
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
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.put(url, headers=headers, content=content)
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase storage upload failed: {response.status_code} {response.text}")
    return f"{_base_url()}/storage/v1/object/public/{bucket}/{object_path}"


async def download_asset_bytes(path: str) -> tuple[bytes, str, str]:
    _require_configured()
    bucket = quote(settings.supabase_storage_bucket.strip() or "zalo-assets", safe="")
    object_path = quote(path.lstrip("/"), safe="/")
    url = f"{_base_url()}/storage/v1/object/{bucket}/{object_path}"
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        response = await client.get(url, headers=_headers())
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase storage download failed: {response.status_code} {response.text}")
    content_type = response.headers.get("content-type", "").split(";")[0].strip() or "application/octet-stream"
    ext = mimetypes.guess_extension(content_type) or ".jpg"
    return response.content, content_type, ext


async def delete_storage_objects(paths: list[str]) -> None:
    if not paths:
        return
    _require_configured()
    bucket = quote(settings.supabase_storage_bucket.strip() or "zalo-assets", safe="")
    url = f"{_base_url()}/storage/v1/object/{bucket}"
    headers = _headers()
    async with httpx.AsyncClient(timeout=90) as client:
        response = await client.request(
            "DELETE",
            url,
            headers=headers,
            json={"prefixes": paths},
        )
    if response.status_code >= 400:
        raise RuntimeError(f"Supabase storage delete failed: {response.status_code} {response.text}")


async def _download_image(source_url: str) -> tuple[bytes, str, str]:
    if source_url.startswith("data:image/"):
        header, _, payload = source_url.partition(",")
        if not payload or ";base64" not in header:
            raise RuntimeError("Unsupported data URL image format")
        content_type = header.removeprefix("data:").split(";")[0] or "image/jpeg"
        ext = mimetypes.guess_extension(content_type) or ".jpg"
        return base64.b64decode(payload), content_type, ext

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        response = await client.get(source_url)
    if response.status_code >= 400:
        raise RuntimeError(f"Image download failed: HTTP {response.status_code}")
    content_type = response.headers.get("content-type", "").split(";")[0].strip() or "application/octet-stream"
    ext = mimetypes.guess_extension(content_type) or ".jpg"
    return response.content, content_type, ext


def _message_payload(user_id: str, job: JobData, group_id: str, group_name: str, msg: Message) -> dict[str, Any]:
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


async def upsert_zalo_user(
    user_id: str,
    *,
    status: str,
    assigned_worker_id: str | None = None,
    display_name: str | None = None,
) -> None:
    if not is_supabase_configured():
        return

    now = datetime.utcnow().isoformat()
    payload: dict[str, Any] = {
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
        params={"on_conflict": "job_id"},
        prefer="resolution=merge-duplicates",
    )


async def upsert_group(user_id: str, group_id: str, group_name: str) -> None:
    await _rest(
        "POST",
        "zalo_groups",
        json=[
            {
                "user_id": user_id,
                "group_id": group_id,
                "group_name": group_name,
                "updated_at": datetime.utcnow().isoformat(),
            }
        ],
        params={"on_conflict": "user_id,group_id"},
        prefer="resolution=merge-duplicates",
    )


async def upsert_groups(user_id: str, groups: Iterable[dict[str, Any]]) -> int:
    rows: list[dict[str, Any]] = []
    now = datetime.utcnow().isoformat()
    for group in groups:
        group_id = str(group.get("group_id") or group.get("id") or group.get("name") or "").strip()
        group_name = str(group.get("name") or group.get("group_name") or group_id).strip()
        if not group_id or not group_name:
            continue
        rows.append(
            {
                "user_id": user_id,
                "group_id": group_id,
                "group_name": group_name,
                "updated_at": now,
            }
        )
    if not rows:
        return 0
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


async def save_message_assets(
    message_uuid: str,
    user_id: str,
    job_id: str | None,
    source_urls: Iterable[str],
) -> dict[str, int]:
    stats = {"uploaded": 0, "failed": 0}
    for source_url in source_urls:
        status = "pending"
        storage_path = None
        storage_url = None
        error = None
        source_url_ref = source_url
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
    group_name: str | None = None,
    limit: int = 200,
    offset: int = 0,
    content_kind: str = "all",
) -> tuple[list[dict[str, Any]], int]:
    safe_limit = max(1, min(limit, 1000))
    safe_offset = max(0, offset)
    select_clause = "*,assets:zalo_message_assets(*)"
    if content_kind == "image":
        select_clause = "*,assets:zalo_message_assets!inner(*)"
    params: dict[str, Any] = {
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


def group_summaries_from_message_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    groups_by_name: dict[str, dict[str, Any]] = {}
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
    groups_by_name: dict[str, dict[str, Any]],
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
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
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

    hydrated: list[dict[str, Any]] = []
    for row in rows:
        next_row = dict(row)
        if not str(next_row.get("group_name") or "").strip():
            job = jobs_by_id.get(str(next_row.get("job_id") or ""))
            if job:
                next_row["group_name"] = job.get("group_name") or next_row.get("group_name")
                next_row["group_id"] = next_row.get("group_id") or job.get("group_id")
        hydrated.append(next_row)
    return hydrated


async def list_library_group_summaries(user_id: str = "default") -> list[dict[str, Any]]:
    groups_by_name: dict[str, dict[str, Any]] = {}

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


async def _message_group_counts(user_id: str = "default") -> dict[str, dict[str, Any]]:
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


async def list_saved_groups(user_id: str = "default") -> list[dict[str, Any]]:
    groups_by_name: dict[str, dict[str, Any]] = {}
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


async def cleanup_expired_assets(retention_days: int, limit: int) -> dict[str, Any]:
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
    failed: list[dict[str, Any]] = []

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
    message_ids: list[str],
    *,
    include_deleted: bool = False,
) -> list[dict[str, Any]]:
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


async def create_library_message(user_id: str, payload: dict[str, Any], asset_urls: list[str]) -> dict[str, Any]:
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


async def update_library_message(user_id: str, message_id: str, payload: dict[str, Any]) -> dict[str, Any]:
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
    message_ids: list[str] | None = None,
    group_name: str | None = None,
    delete_all_matching: bool = False,
) -> int:
    payload = {"is_deleted": True, "updated_at": datetime.utcnow().isoformat()}
    params: dict[str, Any] = {"user_id": f"eq.{user_id}", "is_deleted": "eq.false"}
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
    message_ids: list[str],
    targets: list[dict[str, Any]],
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


async def update_campaign_status(campaign_id: str, status: str, error: str | None = None) -> None:
    payload: dict[str, Any] = {"status": status, "updated_at": datetime.utcnow().isoformat()}
    if status in {"completed", "failed"}:
        payload["completed_at"] = datetime.utcnow().isoformat()
    if error:
        payload["error"] = error
    await _rest("PATCH", "zalo_broadcast_campaigns", params={"id": f"eq.{campaign_id}"}, json=payload)


async def add_broadcast_log(
    campaign_id: str,
    group_name: str,
    status: str,
    detail: str | None = None,
    message_id: str | None = None,
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


async def get_broadcast_status(campaign_id: str) -> dict[str, Any]:
    campaigns = await _rest("GET", "zalo_broadcast_campaigns", params={"id": f"eq.{campaign_id}"}) or []
    if not campaigns:
        raise KeyError(campaign_id)
    targets = await _rest("GET", "zalo_broadcast_targets", params={"campaign_id": f"eq.{campaign_id}", "order": "created_at.asc"}) or []
    items = await _rest("GET", "zalo_broadcast_items", params={"campaign_id": f"eq.{campaign_id}", "order": "position.asc"}) or []
    logs = await _rest("GET", "zalo_broadcast_logs", params={"campaign_id": f"eq.{campaign_id}", "order": "created_at.asc"}) or []
    return {"campaign": campaigns[0], "targets": targets, "items": items, "logs": logs}
