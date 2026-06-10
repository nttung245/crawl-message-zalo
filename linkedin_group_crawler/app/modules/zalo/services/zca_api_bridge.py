from __future__ import annotations

from typing import Any, Dict, List, Optional
import asyncio
import json
import os
from pathlib import Path

from loguru import logger

from app.modules.zalo.schemas.group import Group
from app.modules.zalo.schemas.message import Message


class ZcaAuthExpiredError(RuntimeError):
    """Cookie/session ZCA đã hết hạn hoặc bị Zalo vô hiệu hóa — cần đăng nhập lại bằng QR."""


# Các chuỗi lỗi từ zca-js cho biết phiên đăng nhập đã hỏng.
_AUTH_EXPIRED_MARKERS = (
    "đăng nhập thất bại",
    "logincookie",
    "login failed",
    "not logged in",
    "session expired",
    "zpw_enk",
    "invalid cookie",
    "cookie expired",
    "401",
)


def _looks_like_auth_expired(detail_text: str) -> bool:
    lowered = (detail_text or "").lower()
    return any(marker in lowered for marker in _AUTH_EXPIRED_MARKERS)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[4]


def zca_api_script_path() -> Path:
    return _backend_root() / "scripts" / "zca_api_bridge.js"


async def _run_zca_command(
    command: str,
    auth: Dict[str, Any],
    *,
    args: Optional[List[str]] = None,
    payload: Optional[Dict[str, Any]] = None,
    timeout_seconds: int = 120,
) -> Dict[str, Any]:
    script = zca_api_script_path()
    if not script.exists():
        raise RuntimeError(f"ZCA API helper not found: {script}")

    input_payload = {"auth": auth}
    if payload:
        input_payload.update(payload)

    proc = await asyncio.create_subprocess_exec(
        "node",
        str(script),
        command,
        *(args or []),
        cwd=str(_backend_root()),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ},
    )
    stdout, stderr = await asyncio.wait_for(
        proc.communicate(json.dumps(input_payload).encode("utf-8")),
        timeout=timeout_seconds,
    )
    stderr_text = stderr.decode("utf-8", errors="replace").strip()
    if stderr_text:
        logger.warning(f"ZCA API helper stderr: {stderr_text[:1000]}")

    lines = [
        line.strip()
        for line in stdout.decode("utf-8", errors="replace").splitlines()
        if line.strip()
    ]
    if not lines:
        raise RuntimeError(f"ZCA API helper returned no output for {command}")

    try:
        result = json.loads(lines[-1])
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"ZCA API helper returned invalid JSON: {lines[-1][:500]}") from exc

    if proc.returncode != 0 or not result.get("ok"):
        detail = result.get("error_detail") or result.get("error") or stderr_text
        if isinstance(detail, (dict, list)):
            detail_text = json.dumps(detail, ensure_ascii=False)
        else:
            detail_text = str(detail or f"ZCA command failed: {command}")
        if _looks_like_auth_expired(detail_text):
            raise ZcaAuthExpiredError(detail_text)
        raise RuntimeError(detail_text)

    return result


def _to_group(row: Dict[str, Any]) -> Group:
    return Group(
        group_id=str(row.get("group_id") or row.get("id") or row.get("name") or ""),
        name=str(row.get("name") or row.get("group_name") or row.get("group_id") or ""),
        avatar_url=row.get("avatar_url"),
        last_message=row.get("last_message"),
        last_message_at=str(row["last_message_at"]) if row.get("last_message_at") else None,
        last_sender_id=str(row["last_sender_id"]) if row.get("last_sender_id") else None,
        last_sender_name=row.get("last_sender_name") or None,
        last_message_type=row.get("last_message_type") or None,
        unread_count=int(row.get("unread_count") or 0),
        is_pinned=bool(row.get("is_pinned") or row.get("pinned") or False),
    )


def _to_message(row: Dict[str, Any]) -> Message:
    return Message(
        message_id=str(row.get("message_id") or ""),
        sender_id=row.get("sender_id") or None,
        sender_name=row.get("sender_name") or None,
        timestamp=row.get("timestamp") or None,
        time_text=row.get("time_text") or None,
        type=str(row.get("type") or "text"),
        content=row.get("content") or None,
        image_urls=[str(url) for url in (row.get("image_urls") or []) if url],
        reply_to_id=row.get("reply_to_id") or None,
        is_deleted=bool(row.get("is_deleted")),
        is_sent=bool(row.get("is_sent")),
        group_id=row.get("group_id") or None,
    )


async def list_zca_groups(auth: Dict[str, Any]) -> List[Group]:
    result = await _run_zca_command("list-groups", auth, timeout_seconds=120)
    groups = [_to_group(row) for row in result.get("groups") or []]
    return [group for group in groups if group.group_id and group.name]


async def list_zca_friends(auth: Dict[str, Any]) -> List[Group]:
    result = await _run_zca_command("list-friends", auth, timeout_seconds=120)
    friends = [_to_group(row) for row in result.get("friends") or []]
    return [friend for friend in friends if friend.group_id and friend.name]


async def get_zca_group_history(
    auth: Dict[str, Any],
    group_id: str,
    *,
    count: int = 500,
) -> List[Message]:
    result = await _run_zca_command(
        "group-history",
        auth,
        args=["--group-id", group_id, "--count", str(count)],
        timeout_seconds=180,
    )
    messages = [_to_message(row) for row in result.get("messages") or []]
    return [message for message in messages if message.message_id]


async def get_zca_group_related_ids(
    auth: Dict[str, Any],
    group_id: str,
) -> List[str]:
    result = await _run_zca_command(
        "group-related-ids",
        auth,
        args=["--group-id", group_id],
        timeout_seconds=90,
    )
    ids: List[str] = []
    for value in result.get("ids") or []:
        text = str(value or "").strip()
        if text and text.isdigit() and len(text) >= 6 and text not in ids:
            ids.append(text)
    return ids


async def sync_zca_group_old_messages(
    auth: Dict[str, Any],
    group_id: Optional[str] = None,
    *,
    thread_type: int = 1,
    count: int = 500,
    timeout_ms: int = 35000,
) -> List[Message]:
    args = [
        "--type",
        str(thread_type),
        "--count",
        str(count),
        "--timeout",
        str(timeout_ms),
    ]
    if group_id:
        args.extend(["--thread-id", group_id])

    result = await _run_zca_command(
        "sync-old-messages",
        auth,
        args=args,
        timeout_seconds=max(30, int(timeout_ms / 1000) + 10),
    )
    messages = [_to_message(row) for row in result.get("messages") or []]
    if not messages and result.get("diagnostics"):
        logger.warning(
            "ZCA listener sync returned no messages for requested group/global; "
            f"diagnostics={json.dumps(result.get('diagnostics'), ensure_ascii=False)[:1000]}"
        )
    return [message for message in messages if message.message_id]


async def send_zca_message(
    auth: Dict[str, Any],
    thread_id: str,
    text: str,
    *,
    thread_type: int = 1,
) -> Dict[str, Any]:
    return await _run_zca_command(
        "send-message",
        auth,
        args=["--thread-id", thread_id, "--type", str(thread_type), "--text", text],
        timeout_seconds=90,
    )


async def send_zca_images(
    auth: Dict[str, Any],
    thread_id: str,
    file_paths: List[str],
    *,
    text: str = "",
    thread_type: int = 1,
) -> Dict[str, Any]:
    return await _run_zca_command(
        "send-images",
        auth,
        args=["--thread-id", thread_id, "--type", str(thread_type)],
        payload={"file_paths": file_paths, "text": text},
        timeout_seconds=180,
    )


async def remove_zca_unread_mark(
    auth: Dict[str, Any],
    thread_id: str,
    *,
    thread_type: int = 1,
) -> Dict[str, Any]:
    return await _run_zca_command(
        "remove-unread",
        auth,
        args=["--thread-id", thread_id, "--type", str(thread_type)],
        timeout_seconds=30,
    )
