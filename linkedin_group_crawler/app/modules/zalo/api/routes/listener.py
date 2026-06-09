from typing import Optional
import re

from fastapi import APIRouter, Depends, Header, HTTPException

from app.modules.zalo.api.security import verify_zalo_api_key
from app.modules.zalo.services.zca_persistent_listener import (
    get_listener_status,
    restart_listener,
)


router = APIRouter(
    prefix="/api/zalo/listener",
    tags=["zalo-listener"],
    dependencies=[Depends(verify_zalo_api_key)],
)


def _normalize_user_id(value: Optional[str]) -> str:
    raw = (value or "default").strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw or "default"


@router.get("/status")
async def listener_status(x_user_id: str = Header("default", alias="X-User-ID")):
    return get_listener_status(_normalize_user_id(x_user_id))


@router.post("/restart")
async def restart_persistent_listener(x_user_id: str = Header("default", alias="X-User-ID")):
    user_id = _normalize_user_id(x_user_id)
    try:
        return await restart_listener(user_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
