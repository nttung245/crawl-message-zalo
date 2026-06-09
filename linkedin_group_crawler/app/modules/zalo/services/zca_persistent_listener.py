from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import asyncio
import json
import os

from loguru import logger

from app.modules.zalo.schemas.message import Message
from app.modules.zalo.services.supabase_service import (
    is_supabase_configured,
    save_listener_messages,
)
from app.modules.zalo.config import settings
from app.modules.zalo.services.zca_api_bridge import list_zca_groups, get_zca_group_history, list_zca_friends
from app.modules.zalo.services.zca_auth_store import list_zca_auth_users, load_zca_auth


_CACHE_LIMIT_PER_GROUP = 1000
_RESTART_BACKOFFS = [3, 8, 20, 45, 90]
_STARTUP_SYNC_GROUP_LIMIT = 12
_STARTUP_SYNC_MESSAGE_COUNT = 80
_STARTUP_SYNC_TIMEOUT_MS = 25000

# Marker cho biết cookie/session Zalo đã hết hạn — không cố restart vô ích nữa.
_AUTH_EXPIRED_MARKERS = (
    "đăng nhập thất bại",
    "logincookie",
    "login failed",
    "session expired",
    "not logged in",
    "invalid cookie",
    "cookie expired",
)


def _looks_like_auth_expired(text: Optional[str]) -> bool:
    lowered = (text or "").lower()
    return any(marker in lowered for marker in _AUTH_EXPIRED_MARKERS)


def _backend_root() -> Path:
    return Path(__file__).resolve().parents[4]


def _listener_script_path() -> Path:
    return _backend_root() / "scripts" / "zca_persistent_listener.js"


def _now_iso() -> str:
    return datetime.utcnow().isoformat()


def _timestamp_ms(value: Any) -> int:
    if value is None:
        return 0

    try:
        text = str(value).strip()
        if not text:
            return 0

        if text.isdigit():
            number = int(text)
            return number * 1000 if number < 10_000_000_000 else number

        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return int(parsed.timestamp() * 1000)
    except Exception:
        return 0


def _message_timestamp_ms(message: Message) -> int:
    return _timestamp_ms(message.timestamp) or _timestamp_ms(message.time_text)


def _sort_messages_old_to_new(messages: List[Message]) -> List[Message]:
    return sorted(
        messages,
        key=lambda message: (
            _message_timestamp_ms(message),
            str(message.message_id or ""),
        ),
    )


def _sort_messages_new_to_old(messages: List[Message]) -> List[Message]:
    return sorted(
        messages,
        key=lambda message: (
            _message_timestamp_ms(message),
            str(message.message_id or ""),
        ),
        reverse=True,
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
    )


@dataclass
class ListenerState:
    user_id: str
    auth: Optional[Dict[str, Any]] = None
    task: Optional[asyncio.Task] = None
    proc: Any = None
    desired: bool = False
    connected: bool = False
    pid: Optional[int] = None
    last_event_at: Optional[str] = None
    last_error: Optional[str] = None
    messages_seen: int = 0
    restart_attempt: int = 0
    auth_expired: bool = False
    group_names: Dict[str, str] = field(default_factory=dict)
    reconnect_sync_task: Optional[asyncio.Task] = None


class ZcaPersistentListenerManager:
    def __init__(self) -> None:
        self._states: Dict[str, ListenerState] = {}
        self._lock = asyncio.Lock()
        self._cache: Dict[Tuple[str, str], Dict[str, Message]] = {}

    async def start_listener(
        self,
        user_id: str,
        auth: Dict[str, Any],
        *,
        force_restart: bool = False,
    ) -> Dict[str, Any]:
        async with self._lock:
            state = self._states.get(user_id)
            if state and state.task and not state.task.done() and not force_restart:
                return self.status(user_id)
            if state and force_restart:
                await self._stop_state(state)

            state = self._states.get(user_id) or ListenerState(user_id=user_id)
            state.auth = auth
            state.desired = True
            state.connected = False
            state.last_error = None
            state.auth_expired = False
            state.restart_attempt = 0
            self._states[user_id] = state
            state.task = asyncio.create_task(self._run_supervised(state))
            return self.status(user_id)

    async def restart_listener(self, user_id: str) -> Dict[str, Any]:
        auth = await load_zca_auth(user_id)
        if not auth:
            raise RuntimeError(f"No persisted ZCA auth for user={user_id}")
        return await self.start_listener(user_id, auth, force_restart=True)

    async def stop_listener(self, user_id: str) -> Dict[str, Any]:
        async with self._lock:
            state = self._states.get(user_id)
            if not state:
                return self.status(user_id)
            await self._stop_state(state)
            return self.status(user_id)

    async def start_persisted_listeners(self) -> None:
        for user_id in await list_zca_auth_users():
            auth = await load_zca_auth(user_id)
            if not auth:
                continue
            try:
                await self.start_listener(user_id, auth)
            except Exception as exc:
                logger.warning(f"Could not start persisted ZCA listener for user={user_id}: {exc}")

    async def shutdown(self) -> None:
        async with self._lock:
            states = list(self._states.values())
        for state in states:
            await self._stop_state(state)

    def status(self, user_id: str) -> Dict[str, Any]:
        state = self._states.get(user_id)
        if not state:
            return {
                "user_id": user_id,
                "running": False,
                "connected": False,
                "pid": None,
                "last_event_at": None,
                "last_error": None,
                "messages_seen": 0,
                "auth_expired": False,
            }
        running = bool(state.proc and state.proc.returncode is None)
        return {
            "user_id": user_id,
            "running": running,
            "connected": state.connected,
            "pid": state.pid if running else None,
            "last_event_at": state.last_event_at,
            "last_error": state.last_error,
            "messages_seen": state.messages_seen,
            "auth_expired": state.auth_expired,
        }

    def get_cached_messages(self, user_id: str, group_id: str, limit: int = 500) -> List[Message]:
        cache = self._cache.get((user_id, group_id)) or {}
        if not cache:
            return []
        safe_limit = max(1, min(int(limit or 500), _CACHE_LIMIT_PER_GROUP))
        return list(cache.values())[-safe_limit:]

    def _recent_group_ids_for_user(self, user_id: str, limit: int = 5) -> List[str]:
        group_stats: List[Tuple[int, int, str]] = []

        for (cached_user_id, group_id), cache in self._cache.items():
            if cached_user_id != user_id or not cache:
                continue

            messages = _sort_messages_new_to_old(list(cache.values()))
            if not messages:
                continue

            last_message = messages[0]
            timestamp_value = _message_timestamp_ms(last_message)
            group_stats.append((timestamp_value, len(cache), group_id))

        group_stats.sort(key=lambda item: (item[0], item[1]), reverse=True)
        return [group_id for _ts, _count, group_id in group_stats[: max(1, int(limit))]]

    async def _sync_recent_groups_after_connect(self, state: ListenerState) -> None:
        if state.reconnect_sync_task and not state.reconnect_sync_task.done():
            return

        async def _run() -> None:
            try:
                cached_group_ids = self._recent_group_ids_for_user(state.user_id, limit=8)
                known_group_ids = [
                    str(group_id).strip()
                    for group_id in state.group_names.keys()
                    if str(group_id).strip()
                ]

                group_ids = list(dict.fromkeys([*cached_group_ids, *known_group_ids]))[:
                    _STARTUP_SYNC_GROUP_LIMIT
                ]

                if not group_ids:
                    logger.info(f"ZCA listener startup sync skipped user={state.user_id}: no known groups")
                    return

                logger.info(f"ZCA listener startup sync user={state.user_id} groups={group_ids}")

                for group_id in group_ids:
                    try:
                        # Ưu tiên getGroupChatHistory vì nó lấy đúng lịch sử của 1 group cụ thể.
                        messages = await get_zca_group_history(
                            state.auth or {},
                            group_id,
                            count=_STARTUP_SYNC_MESSAGE_COUNT,
                        )

                        messages = _sort_messages_old_to_new(messages)

                        if messages:
                            await self._record_messages(
                                state,
                                [
                                    {
                                        "thread_id": group_id,
                                        "message_id": message.message_id,
                                        "sender_id": message.sender_id,
                                        "sender_name": message.sender_name,
                                        "timestamp": message.timestamp,
                                        "time_text": message.time_text,
                                        "type": message.type,
                                        "content": message.content,
                                        "image_urls": message.image_urls,
                                        "reply_to_id": message.reply_to_id,
                                        "is_deleted": message.is_deleted,
                                        "is_sent": message.is_sent,
                                    }
                                    for message in messages
                                ],
                                increment_unread=False,
                            )
                            logger.info(
                                f"ZCA listener startup sync saved user={state.user_id} "
                                f"group={group_id} messages={len(messages)}"
                            )
                        else:
                            logger.info(
                                f"ZCA listener startup sync empty user={state.user_id} group={group_id}"
                            )
                    except Exception as exc:
                        logger.warning(
                            f"Startup sync failed for user={state.user_id} group={group_id}: {exc}"
                        )
            finally:
                state.reconnect_sync_task = None

        state.reconnect_sync_task = asyncio.create_task(_run())

    async def _stop_state(self, state: ListenerState) -> None:
        state.desired = False
        state.connected = False
        proc = state.proc
        if proc and proc.returncode is None:
            try:
                proc.terminate()
                await asyncio.wait_for(proc.wait(), timeout=8)
            except asyncio.TimeoutError:
                try:
                    proc.kill()
                except ProcessLookupError:
                    pass
            except ProcessLookupError:
                pass
            except Exception as exc:
                logger.warning(f"Could not stop ZCA listener for user={state.user_id}: {exc}")
        if state.task and not state.task.done():
            state.task.cancel()
            try:
                await state.task
            except asyncio.CancelledError:
                pass
        state.proc = None
        state.pid = None

    async def _run_supervised(self, state: ListenerState) -> None:
        while state.desired:
            try:
                await self._run_once(state)
                if not state.desired:
                    return
                state.last_error = "listener_exited"
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                state.connected = False
                state.last_error = f"{type(exc).__name__}: {exc}"
                logger.warning(f"ZCA listener crashed for user={state.user_id}: {exc}")
                if _looks_like_auth_expired(str(exc)):
                    state.auth_expired = True

            # Cookie hết hạn: dừng hẳn, không restart vô ích. Chờ user đăng nhập lại bằng QR.
            if state.auth_expired:
                state.desired = False
                logger.warning(
                    f"ZCA session expired for user={state.user_id} — stopping listener until re-login (QR)"
                )
                return

            state.restart_attempt += 1
            delay = _RESTART_BACKOFFS[min(state.restart_attempt - 1, len(_RESTART_BACKOFFS) - 1)]
            logger.warning(f"Restarting ZCA listener for user={state.user_id} in {delay}s")
            await asyncio.sleep(delay)

    async def _run_once(self, state: ListenerState) -> None:
        if not state.auth:
            raise RuntimeError("missing_zca_auth")
        script = _listener_script_path()
        if not script.exists():
            raise RuntimeError(f"ZCA persistent listener helper not found: {script}")

        await self._refresh_group_names(state)

        proc = await asyncio.create_subprocess_exec(
            "node",
            str(script),
            "--user-id",
            state.user_id,
            "--old-message-interval-ms",
            str(int(getattr(settings, "zca_old_message_interval_ms", 60000))),
            cwd=str(_backend_root()),
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env={**os.environ},
        )
        state.proc = proc
        state.pid = proc.pid
        state.last_event_at = _now_iso()
        state.last_error = None
        logger.info(f"Started ZCA persistent listener user={state.user_id} pid={proc.pid}")

        if proc.stdin:
            proc.stdin.write(json.dumps({"auth": state.auth, "user_id": state.user_id}).encode("utf-8"))
            await proc.stdin.drain()
            proc.stdin.close()

        stderr_task = asyncio.create_task(self._read_stderr(state, proc))
        try:
            if not proc.stdout:
                raise RuntimeError("listener_stdout_missing")
            while state.desired:
                line = await proc.stdout.readline()
                if not line:
                    break
                await self._handle_event(state, line.decode("utf-8", errors="replace").strip())
            await proc.wait()
        finally:
            stderr_task.cancel()
            try:
                await stderr_task
            except asyncio.CancelledError:
                pass
            state.connected = False
            state.pid = None
            state.proc = None

    async def _read_stderr(self, state: ListenerState, proc: Any) -> None:
        if not proc.stderr:
            return
        while True:
            line = await proc.stderr.readline()
            if not line:
                return
            logger.warning(
                "ZCA listener stderr user={}: {}",
                state.user_id,
                line.decode("utf-8", errors="replace").strip()[:1000],
            )

    async def _refresh_group_names(self, state: ListenerState) -> None:
        try:
            groups = await list_zca_groups(state.auth or {})
            try:
                friends = await list_zca_friends(state.auth or {})
            except Exception as e:
                logger.warning(f"Could not load ZCA friends for listener name preload: {e}")
                friends = []
            
            state.group_names = {
                chat.group_id: chat.name
                for chat in (groups + friends)
                if chat.group_id
            }

            logger.info(f"Loaded {len(state.group_names)} ZCA group/friend names for listener user={state.user_id}")
        except Exception as exc:
            logger.warning(f"Could not preload ZCA group/friend names for listener user={state.user_id}: {exc}")

    async def _handle_event(self, state: ListenerState, raw_line: str) -> None:
        if not raw_line:
            return
        try:
            event = json.loads(raw_line)
        except json.JSONDecodeError:
            logger.warning(f"Invalid ZCA listener JSON for user={state.user_id}: {raw_line[:500]}")
            return

        state.last_event_at = _now_iso()
        event_name = event.get("event")
        if event_name in {"ready", "starting", "old_messages_requested"}:
            return
        if event_name == "connected":
            state.connected = True
            state.restart_attempt = 0
            state.last_error = None
            logger.info(f"ZCA listener connected user={state.user_id} pid={state.pid}")
            await self._sync_recent_groups_after_connect(state)
            return
        if event_name in {"disconnected", "closed", "stopping"}:
            state.connected = False
            return
        if event_name in {"error", "fatal"}:
            detail = event.get("error_detail") or event.get("error") or event
            state.last_error = json.dumps(detail, ensure_ascii=False)[:1000]
            if _looks_like_auth_expired(state.last_error):
                state.auth_expired = True
            logger.warning(f"ZCA listener event error user={state.user_id}: {state.last_error}")
            return
        if event_name == "message":
            await self._record_messages(state, [event.get("message") or {}])
            return
        if event_name == "old_messages":
            await self._record_messages(state, event.get("messages") or [], increment_unread=False)

    async def _record_messages(self, state: ListenerState, rows: List[Dict[str, Any]], *, increment_unread: bool = True) -> None:
        grouped: Dict[str, List[Message]] = {}

        for row in rows:
            group_id = str(row.get("thread_id") or row.get("group_id") or "").strip()
            if not group_id:
                continue

            message = _to_message(row)
            if not message.message_id:
                continue

            cache = self._cache.setdefault((state.user_id, group_id), {})

            if message.message_id not in cache:
                state.messages_seen += 1

            cache[message.message_id] = message

            # Giữ cache theo timestamp, không phụ thuộc thứ tự insert.
            sorted_cache_messages = _sort_messages_old_to_new(list(cache.values()))
            if len(sorted_cache_messages) > _CACHE_LIMIT_PER_GROUP:
                sorted_cache_messages = sorted_cache_messages[-_CACHE_LIMIT_PER_GROUP:]

            self._cache[(state.user_id, group_id)] = {
                item.message_id: item
                for item in sorted_cache_messages
                if item.message_id
            }

            grouped.setdefault(group_id, []).append(message)

        if not grouped:
            return

        # Luôn sort tin nhắn cũ -> mới trước khi lưu DB/Supabase.
        for group_id in list(grouped.keys()):
            grouped[group_id] = _sort_messages_old_to_new(grouped[group_id])

        if not is_supabase_configured():
            return

        for group_id, messages in grouped.items():
            group_name = state.group_names.get(group_id) or f"Conversation {group_id}"

            try:
                await save_listener_messages(state.user_id, group_id, group_name, messages, increment_unread=increment_unread)
            except Exception as exc:
                state.last_error = f"save_listener_messages_failed:{type(exc).__name__}: {exc}"
                logger.warning(
                    f"Could not save listener messages user={state.user_id} group={group_id}: {exc}"
                )


_MANAGER = ZcaPersistentListenerManager()


async def start_listener(user_id: str, auth: Dict[str, Any], *, force_restart: bool = False) -> Dict[str, Any]:
    return await _MANAGER.start_listener(user_id, auth, force_restart=force_restart)


async def restart_listener(user_id: str) -> Dict[str, Any]:
    return await _MANAGER.restart_listener(user_id)


async def stop_listener(user_id: str) -> Dict[str, Any]:
    return await _MANAGER.stop_listener(user_id)


async def start_persisted_listeners() -> None:
    await _MANAGER.start_persisted_listeners()


async def shutdown_persistent_listeners() -> None:
    await _MANAGER.shutdown()


def get_listener_status(user_id: str) -> Dict[str, Any]:
    return _MANAGER.status(user_id)


def get_cached_messages(user_id: str, group_id: str, limit: int = 500) -> List[Message]:
    return _MANAGER.get_cached_messages(user_id, group_id, limit)
