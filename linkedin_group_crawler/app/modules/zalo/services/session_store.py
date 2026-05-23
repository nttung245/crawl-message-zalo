import asyncio
from datetime import datetime, timedelta
from typing import Dict, Optional

from loguru import logger

from app.modules.zalo.schemas.session import SessionData


session_store: Dict[str, SessionData] = {}
session_locks: Dict[str, asyncio.Lock] = {}
profile_locks: Dict[str, asyncio.Lock] = {}


def get_session(session_id: str) -> Optional[SessionData]:
    session = session_store.get(session_id)
    if session:
        session.last_used = datetime.utcnow()
    return session


def save_session(session: SessionData) -> None:
    session_store[session.session_id] = session
    session_locks.setdefault(session.session_id, asyncio.Lock())


def get_session_lock(session_id: str) -> asyncio.Lock:
    return session_locks.setdefault(session_id, asyncio.Lock())


def get_profile_lock(user_id: str) -> asyncio.Lock:
    return profile_locks.setdefault(user_id, asyncio.Lock())


def get_latest_waiting_session(user_id: str, max_age_seconds: int = 120) -> Optional[SessionData]:
    now = datetime.utcnow()
    candidates = [
        session
        for session in session_store.values()
        if session.user_id == user_id
        if session.status in {"waiting_scan", "qr_expired"}
        and (now - session.created_at).total_seconds() <= max_age_seconds
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda s: s.created_at, reverse=True)
    latest = candidates[0]
    latest.last_used = now
    return latest


def get_latest_session_for_user(
    user_id: str,
    preferred_statuses: Optional[set[str]] = None,
) -> Optional[SessionData]:
    candidates = [
        session
        for session in session_store.values()
        if session.user_id == user_id
        and (preferred_statuses is None or session.status in preferred_statuses)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda s: (s.last_used, s.created_at), reverse=True)
    latest = candidates[0]
    latest.last_used = datetime.utcnow()
    return latest


async def delete_session(session_id: str) -> None:
    session = session_store.pop(session_id, None)
    session_locks.pop(session_id, None)
    if session:
        try:
            await session.context.close()
        except Exception as e:
            logger.warning(f"Error closing context for session {session_id}: {e}")
        try:
            if session.browser:
                await session.browser.close()
        except Exception as e:
            logger.warning(f"Error closing browser for session {session_id}: {e}")


async def delete_sessions_for_user(user_id: str) -> int:
    target_ids = [sid for sid, sess in session_store.items() if sess.user_id == user_id]
    for sid in target_ids:
        await delete_session(sid)
    return len(target_ids)


async def cleanup_expired_sessions(ttl_hours: int) -> None:
    cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
    expired = [sid for sid, s in list(session_store.items()) if s.last_used < cutoff]
    for sid in expired:
        logger.info(f"Cleaning up expired session: {sid}")
        await delete_session(sid)

