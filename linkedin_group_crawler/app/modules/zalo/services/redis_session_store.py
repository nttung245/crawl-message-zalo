"""Redis-backed session store for multi-worker/multi-replica deployments.

Replaces in-process session storage with Redis, enabling horizontal scaling.
Requires Redis server to be running and accessible via REDIS_URL environment variable.

Features:
- Session data persisted in Redis (survives worker restarts)
- Distributed locks using Redis (shared across workers)
- TTL-based expiration (Redis automatically cleans up old sessions)
- Backward compatible interface with in-memory session store
"""

from typing import Dict, Optional, Set
import asyncio
import json
from datetime import datetime, timedelta

import redis.asyncio as redis
from loguru import logger

from app.modules.zalo.schemas.session import SessionData


class RedisSessionStore:
    """Redis-backed session store for production deployments."""

    SESSION_KEY_PREFIX = "zalo:session:"
    LOCK_KEY_PREFIX = "zalo:lock:"
    PROFILE_LOCK_KEY_PREFIX = "zalo:profile_lock:"
    DEFAULT_LOCK_TIMEOUT_SEC = 30

    def __init__(self, redis_url: str):
        """Initialize Redis connection.

        Args:
            redis_url: Redis connection URL (e.g., 'redis://localhost:6379/0')
        """
        self.redis_url = redis_url
        self.redis_client: Optional[redis.Redis] = None
        self._local_locks: Dict[str, asyncio.Lock] = {}

    async def connect(self) -> None:
        """Establish Redis connection."""
        try:
            self.redis_client = await redis.from_url(self.redis_url)
            await self.redis_client.ping()
            logger.info(f"Connected to Redis at {self.redis_url}")
        except Exception as exc:
            logger.error(f"Failed to connect to Redis: {exc}")
            raise

    async def disconnect(self) -> None:
        """Close Redis connection."""
        if self.redis_client:
            await self.redis_client.close()

    def _session_key(self, session_id: str) -> str:
        return f"{self.SESSION_KEY_PREFIX}{session_id}"

    def _lock_key(self, session_id: str) -> str:
        return f"{self.LOCK_KEY_PREFIX}{session_id}"

    def _profile_lock_key(self, user_id: str) -> str:
        return f"{self.PROFILE_LOCK_KEY_PREFIX}{user_id}"

    async def get_session(self, session_id: str) -> Optional[SessionData]:
        """Retrieve session from Redis (no side effects, pure read)."""
        if not self.redis_client:
            return None

        try:
            data = await self.redis_client.get(self._session_key(session_id))
            if data:
                return SessionData.model_validate_json(data)
        except Exception as exc:
            logger.warning(f"Error retrieving session {session_id}: {exc}")

        return None

    async def touch_session(self, session_id: str) -> None:
        """Update last_used timestamp for session."""
        session = await self.get_session(session_id)
        if session:
            session.last_used = datetime.utcnow()
            await self.save_session(session)

    async def save_session(self, session: SessionData, ttl_hours: int = 8) -> None:
        """Save session to Redis with TTL."""
        if not self.redis_client:
            return

        try:
            key = self._session_key(session.session_id)
            data = session.model_dump_json()
            ttl_seconds = ttl_hours * 3600
            await self.redis_client.setex(key, ttl_seconds, data)
        except Exception as exc:
            logger.error(f"Error saving session {session.session_id}: {exc}")

    async def get_session_lock(self, session_id: str) -> asyncio.Lock:
        """Get or create a lock for the session.

        For Redis deployments, this returns a local lock that works within a single worker.
        For distributed locking across workers, use Redis-native locks (redlock, etc.).
        """
        if session_id not in self._local_locks:
            self._local_locks[session_id] = asyncio.Lock()
        return self._local_locks[session_id]

    async def get_profile_lock(self, user_id: str) -> asyncio.Lock:
        """Get or create a lock for the user profile.

        Note: Local asyncio locks do not work across workers. For production,
        implement distributed locks using Redis (e.g., redlock-py, aioredlock).
        """
        if user_id not in self._local_locks:
            self._local_locks[user_id] = asyncio.Lock()
        return self._local_locks[user_id]

    async def delete_session(self, session_id: str) -> None:
        """Delete session from Redis and close resources."""
        session = await self.get_session(session_id)

        if not self.redis_client:
            return

        try:
            key = self._session_key(session_id)
            await self.redis_client.delete(key)

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
        except Exception as exc:
            logger.error(f"Error deleting session {session_id}: {exc}")

    async def delete_sessions_for_user(self, user_id: str) -> int:
        """Delete all sessions for a user."""
        if not self.redis_client:
            return 0

        try:
            # Scan for all session keys matching this user
            pattern = f"{self.SESSION_KEY_PREFIX}*"
            deleted_count = 0

            async for key in self.redis_client.scan_iter(match=pattern):
                data = await self.redis_client.get(key)
                if data:
                    session = SessionData.model_validate_json(data)
                    if session.user_id == user_id:
                        await self.delete_session(session.session_id)
                        deleted_count += 1

            return deleted_count
        except Exception as exc:
            logger.error(f"Error deleting sessions for user {user_id}: {exc}")
            return 0

    async def get_latest_waiting_session(
        self,
        user_id: str,
        max_age_seconds: int = 120,
    ) -> Optional[SessionData]:
        """Get latest waiting/qr_expired session for user."""
        if not self.redis_client:
            return None

        try:
            now = datetime.utcnow()
            candidates = []

            async for key in self.redis_client.scan_iter(
                match=f"{self.SESSION_KEY_PREFIX}*"
            ):
                data = await self.redis_client.get(key)
                if data:
                    session = SessionData.model_validate_json(data)
                    if (
                        session.user_id == user_id
                        and session.status in {"waiting_scan", "qr_expired"}
                        and (now - session.created_at).total_seconds() <= max_age_seconds
                    ):
                        candidates.append(session)

            if not candidates:
                return None

            candidates.sort(key=lambda s: s.created_at, reverse=True)
            latest = candidates[0]
            latest.last_used = now
            await self.save_session(latest)
            return latest
        except Exception as exc:
            logger.warning(f"Error getting latest waiting session: {exc}")
            return None

    async def get_latest_session_for_user(
        self,
        user_id: str,
        preferred_statuses: Optional[Set[str]] = None,
    ) -> Optional[SessionData]:
        """Get latest session for user with optional status filter."""
        if not self.redis_client:
            return None

        try:
            candidates = []

            async for key in self.redis_client.scan_iter(
                match=f"{self.SESSION_KEY_PREFIX}*"
            ):
                data = await self.redis_client.get(key)
                if data:
                    session = SessionData.model_validate_json(data)
                    if session.user_id == user_id and (
                        preferred_statuses is None
                        or session.status in preferred_statuses
                    ):
                        candidates.append(session)

            if not candidates:
                return None

            candidates.sort(
                key=lambda s: (s.last_used, s.created_at),
                reverse=True,
            )
            latest = candidates[0]
            latest.last_used = datetime.utcnow()
            await self.save_session(latest)
            return latest
        except Exception as exc:
            logger.warning(f"Error getting latest session for user: {exc}")
            return None

    async def cleanup_expired_sessions(self, ttl_hours: int) -> None:
        """Clean up expired sessions from Redis.

        Redis handles TTL automatically via key expiration, so this is mainly
        for explicit cleanup and browser resource management.
        """
        if not self.redis_client:
            return

        try:
            cutoff = datetime.utcnow() - timedelta(hours=ttl_hours)
            cleaned = 0

            async for key in self.redis_client.scan_iter(
                match=f"{self.SESSION_KEY_PREFIX}*"
            ):
                data = await self.redis_client.get(key)
                if data:
                    session = SessionData.model_validate_json(data)
                    if session.last_used < cutoff:
                        await self.delete_session(session.session_id)
                        cleaned += 1

            if cleaned > 0:
                logger.info(f"Cleaned up {cleaned} expired sessions")
        except Exception as exc:
            logger.error(f"Error during cleanup: {exc}")

    async def start_cleanup_scheduler(
        self,
        ttl_hours: int,
        interval_seconds: int = 3600,
    ) -> None:
        """Background task for periodic session cleanup."""
        logger.info(
            f"Redis session cleanup scheduler started (TTL={ttl_hours}h, interval={interval_seconds}s)"
        )
        while True:
            await asyncio.sleep(interval_seconds)
            try:
                await self.cleanup_expired_sessions(ttl_hours)
            except Exception as exc:
                logger.warning(f"Session cleanup failed: {exc}")
