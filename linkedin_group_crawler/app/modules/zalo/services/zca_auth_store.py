from __future__ import annotations

import asyncio
import json
import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from app.modules.zalo.config import settings
from app.modules.zalo.schemas.session import SessionData
from app.modules.zalo.services.session_store import save_session


_STORE_LOCKS: Dict[str, asyncio.Lock] = {}


def _normalize_user_id(user_id: str) -> str:
    raw = (user_id or "default").strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw or "default"


def _store_path(user_id: str) -> Path:
    safe_user_id = _normalize_user_id(user_id)
    return Path(settings.zca_auth_store_dir).expanduser().resolve() / f"{safe_user_id}.json"


def _lock_for(user_id: str) -> asyncio.Lock:
    safe_user_id = _normalize_user_id(user_id)
    lock = _STORE_LOCKS.get(safe_user_id)
    if lock is None:
        lock = asyncio.Lock()
        _STORE_LOCKS[safe_user_id] = lock
    return lock


async def save_zca_auth(user_id: str, auth: Dict[str, Any]) -> None:
    if not isinstance(auth, dict) or not auth:
        return

    path = _store_path(user_id)
    async with _lock_for(user_id):
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(".tmp")
        tmp_path.write_text(json.dumps(auth, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(tmp_path, 0o600)
        except Exception:
            pass
        tmp_path.replace(path)
    logger.info(f"Saved ZCA auth for user={_normalize_user_id(user_id)} to {path}")


async def load_zca_auth(user_id: str) -> Optional[Dict[str, Any]]:
    path = _store_path(user_id)
    async with _lock_for(user_id):
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning(f"Could not read ZCA auth for user={_normalize_user_id(user_id)}: {exc}")
            return None
        if not isinstance(data, dict) or not data:
            return None
        return data


async def list_zca_auth_users() -> List[str]:
    root = Path(settings.zca_auth_store_dir).expanduser().resolve()
    if not root.exists():
        return []

    users: List[str] = []
    for path in sorted(root.glob("*.json")):
        user_id = _normalize_user_id(path.stem)
        if user_id and user_id not in users:
            users.append(user_id)
    return users


async def delete_zca_auth(user_id: str) -> bool:
    path = _store_path(user_id)
    async with _lock_for(user_id):
        if not path.exists():
            return False
        try:
            path.unlink()
            logger.info(f"Deleted ZCA auth for user={_normalize_user_id(user_id)}")
            return True
        except FileNotFoundError:
            return False
        except Exception as exc:
            logger.warning(f"Could not delete ZCA auth for user={_normalize_user_id(user_id)}: {exc}")
            return False


async def ensure_session_zca_auth(session: SessionData) -> Optional[Dict[str, Any]]:
    if session.zca_auth:
        return session.zca_auth

    # If the session is actively waiting for scan or has expired, don't restore old credentials
    if session.status in {"waiting_scan", "qr_expired", "session_expired"}:
        return None

    auth = await load_zca_auth(session.user_id)
    if not auth:
        return None

    session.zca_auth = auth
    session.status = "confirmed"
    session.qr_base64 = None
    session.qr_signature = None
    await save_session(session)
    logger.info(f"Loaded persisted ZCA auth into session={session.session_id} user={session.user_id}")
    return auth
