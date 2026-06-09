"""Session storage abstraction layer.

Zalo sessions contain live Playwright Browser/Context/Page objects. Those
objects cannot be serialized safely into Redis, so the supported production
mode is a single Uvicorn worker with in-process session storage and a
persistent Chromium profile mounted on disk.
"""

from typing import Dict, Optional, Set
import asyncio
import os
from datetime import datetime, timedelta

from loguru import logger

from app.modules.zalo.schemas.session import SessionData


# ⚠️  ARCHITECTURAL WARNING — SINGLE WORKER ONLY (unless Redis is configured)
# Default in-process storage (session_store, session_locks) should only be used
# for single-worker deployments.
#
# Cấu hình khởi động đúng (in-memory, single worker):
#   uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
#
# Cấu hình khởi động đúng (Redis, multi-worker):

# Default in-memory storage (single-worker only)
session_store: Dict[str, SessionData] = {}
session_locks: Dict[str, asyncio.Lock] = {}
profile_locks: Dict[str, asyncio.Lock] = {}

# Redis-backed store is behind a feature flag because live Playwright objects
# are not serializable. Keep ZALO_SESSION_STORE=memory for production.
_redis_store = None


async def initialize_session_store() -> None:
    """Initialize session store backend (memory or Redis based on env config).

    Called from app lifespan startup.
    """
    global _redis_store

    redis_enabled = (os.getenv("ZALO_SESSION_STORE") or "").strip().lower() == "redis"
    redis_url = (os.getenv("REDIS_URL") or "").strip()
    if redis_enabled:
        raise RuntimeError(
            "ZALO_SESSION_STORE=redis is not supported for Zalo Playwright sessions. "
            "Use ZALO_SESSION_STORE=memory and run exactly one Uvicorn worker."
        )
    else:
        if redis_url:
            logger.warning(
                "REDIS_URL is set but ignored for Zalo. Zalo Playwright sessions "
                "use in-memory storage; run exactly one Uvicorn worker."
            )
        logger.info(
            "Using in-memory session store (single-worker only). "
            "Run Uvicorn with --workers 1 for Zalo."
        )


async def shutdown_session_store() -> None:
    """Shutdown session store (close Redis connections if applicable)."""
    global _redis_store
    if _redis_store:
        await _redis_store.disconnect()
        _redis_store = None


def _is_redis_enabled() -> bool:
    """Check if Redis backend is active."""
    return _redis_store is not None


async def get_session(session_id: str) -> Optional[SessionData]:
    """Get session from store (memory or Redis)."""
    if _is_redis_enabled():
        return await _redis_store.get_session(session_id)
    return session_store.get(session_id)


async def touch_session(session_id: str) -> None:
    """Update last_used timestamp."""
    if _is_redis_enabled():
        await _redis_store.touch_session(session_id)
    else:
        session = session_store.get(session_id)
        if session:
            session.last_used = datetime.utcnow()


async def save_session(session: SessionData, ttl_hours: int = 8) -> None:
    """Save session to store (memory or Redis)."""
    if _is_redis_enabled():
        await _redis_store.save_session(session, ttl_hours=ttl_hours)
    else:
        session_store[session.session_id] = session
        session_locks.setdefault(session.session_id, asyncio.Lock())


async def get_session_lock(session_id: str) -> asyncio.Lock:
    """Get lock for session."""
    if _is_redis_enabled():
        return await _redis_store.get_session_lock(session_id)
    return session_locks.setdefault(session_id, asyncio.Lock())


async def get_profile_lock(user_id: str) -> asyncio.Lock:
    """Get lock for user profile."""
    if _is_redis_enabled():
        return await _redis_store.get_profile_lock(user_id)
    return profile_locks.setdefault(user_id, asyncio.Lock())


async def get_latest_waiting_session(
    user_id: str,
    max_age_seconds: int = 120,
) -> Optional[SessionData]:
    """Get latest waiting/qr_expired session for user."""
    if _is_redis_enabled():
        return await _redis_store.get_latest_waiting_session(user_id, max_age_seconds)

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


async def get_latest_session_for_user(
    user_id: str,
    preferred_statuses: Optional[Set[str]] = None,
) -> Optional[SessionData]:
    """Get latest session for user with optional status filter."""
    if _is_redis_enabled():
        return await _redis_store.get_latest_session_for_user(user_id, preferred_statuses)

    candidates = [
        session
        for session in session_store.values()
        if session.user_id == user_id
        and (preferred_statuses is None or session.status in preferred_statuses)
    ]
    if not candidates:
        return None
    def _session_priority(session: SessionData) -> int:
        if session.status == "confirmed" and getattr(session, "zca_auth", None):
            return 3
        if session.status == "confirmed":
            return 2
        if session.status == "waiting_scan":
            return 1
        return 0

    candidates.sort(key=lambda s: (_session_priority(s), s.last_used, s.created_at), reverse=True)
    latest = candidates[0]
    latest.last_used = datetime.utcnow()
    return latest


async def get_latest_browser_session_for_user(
    user_id: str,
    preferred_statuses: Optional[Set[str]] = None,
) -> Optional[SessionData]:
    """Get latest session that has a live Playwright page for UI fallback."""
    if _is_redis_enabled():
        # Redis-backed Zalo sessions are intentionally unsupported because live
        # Playwright objects cannot be serialized.
        return None

    candidates = [
        session
        for session in session_store.values()
        if session.user_id == user_id
        and session.page is not None
        and (preferred_statuses is None or session.status in preferred_statuses)
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda s: (s.last_used, s.created_at), reverse=True)
    latest = candidates[0]
    latest.last_used = datetime.utcnow()
    return latest


async def delete_session(session_id: str) -> None:
    """Delete session and close resources."""
    if _is_redis_enabled():
        await _redis_store.delete_session(session_id)
    else:
        session = session_store.pop(session_id, None)
        session_locks.pop(session_id, None)
        if session:
            proc = getattr(session, "qr_process", None)
            if proc:
                try:
                    proc.terminate()
                except Exception as e:
                    logger.warning(f"Error terminating QR process for session {session_id}: {e}")
            try:
                if session.context:
                    await session.context.close()
            except Exception as e:
                logger.warning(f"Error closing context for session {session_id}: {e}")
            try:
                if session.browser:
                    await session.browser.close()
            except Exception as e:
                logger.warning(f"Error closing browser for session {session_id}: {e}")


async def delete_sessions_for_user(user_id: str) -> int:
    """Delete all sessions for user."""
    if _is_redis_enabled():
        return await _redis_store.delete_sessions_for_user(user_id)

    target_ids = [sid for sid, sess in session_store.items() if sess.user_id == user_id]
    for sid in target_ids:
        await delete_session(sid)
    return len(target_ids)


async def cleanup_expired_sessions(ttl_hours: int) -> None:
    """Clean up expired sessions."""
    if _is_redis_enabled():
        await _redis_store.cleanup_expired_sessions(ttl_hours)
    else:
        cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
        expired = [sid for sid, s in list(session_store.items()) if s.last_used < cutoff]
        for sid in expired:
            logger.info(f"Cleaning up expired session: {sid}")
            await delete_session(sid)


async def start_cleanup_scheduler(ttl_hours: int, interval_seconds: int = 3600) -> None:
    """Background task for periodic session cleanup.

    FIX L-6: cleanup_expired_sessions() is now properly called from lifespan.
    """
    if _is_redis_enabled():
        await _redis_store.start_cleanup_scheduler(ttl_hours, interval_seconds)
    else:
        logger.info(
            f"Session cleanup scheduler started (TTL={ttl_hours}h, interval={interval_seconds}s)"
        )
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await cleanup_expired_sessions(ttl_hours)
            except Exception as exc:
                logger.warning(f"Session cleanup failed: {exc}")
