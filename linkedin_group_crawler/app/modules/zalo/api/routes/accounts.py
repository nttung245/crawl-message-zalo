from typing import List, Optional
import re

from fastapi import APIRouter, Depends, Header, HTTPException, Query
from loguru import logger
from pydantic import BaseModel, Field

from app.modules.zalo.api.security import verify_zalo_api_key
from app.modules.zalo.services.zca_auth_store import delete_zca_auth, list_zca_auth_users
from app.modules.zalo.services.zca_persistent_listener import get_listener_status, restart_listener, stop_listener
from app.modules.zalo.services.session_store import delete_sessions_for_user, get_profile_lock
from app.modules.zalo.crawler.browser import clear_user_profile_data
from app.modules.zalo.services.supabase_service import (
    SupabaseNotConfigured,
    delete_zalo_account,
    get_zalo_inbox_report,
    list_zalo_accounts,
    upsert_zalo_account,
)


router = APIRouter(
    prefix="/api/zalo/accounts",
    tags=["zalo-accounts"],
    dependencies=[Depends(verify_zalo_api_key)],
)


def _normalize_id(value: Optional[str], default: str = "default") -> str:
    raw = (value or default).strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw or default


class ZaloAccountCreate(BaseModel):
    account_id: Optional[str] = None
    owner_id: str = "default"
    label: str = Field(min_length=1)
    phone: Optional[str] = None


class ZaloAccountUpdate(BaseModel):
    owner_id: Optional[str] = None
    label: Optional[str] = None
    phone: Optional[str] = None
    status: Optional[str] = None


@router.get("")
async def list_accounts(
    owner_id: Optional[str] = Query(None),
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    owner = _normalize_id(owner_id or x_user_id)
    db_accounts = await list_zalo_accounts(owner)
    auth_users = set(await list_zca_auth_users())
    by_id = {str(row.get("account_id")): dict(row) for row in db_accounts if row.get("account_id")}

    for auth_user in auth_users:
        by_id.setdefault(
            auth_user,
            {
                "account_id": auth_user,
                "owner_id": owner,
                "label": auth_user,
                "status": "confirmed",
                "is_active": True,
            },
        )

    accounts = []
    for account in by_id.values():
        account_id = str(account.get("account_id") or "")
        if not account_id:
            continue
        listener = get_listener_status(account_id)
        account["has_auth"] = account_id in auth_users
        account["listener"] = listener
        if listener.get("auth_expired"):
            account["status"] = "session_expired"
        elif account["has_auth"] and account.get("status") in {None, "", "unknown", "not_logged_in"}:
            account["status"] = "confirmed"
        accounts.append(account)

    accounts.sort(key=lambda item: (not bool(item.get("has_auth")), str(item.get("label") or item.get("account_id"))))
    return {"owner_id": owner, "accounts": accounts}


@router.post("")
async def create_account(body: ZaloAccountCreate):
    account_id = _normalize_id(body.account_id or body.label)
    owner_id = _normalize_id(body.owner_id)
    try:
        await upsert_zalo_account(
            account_id,
            owner_id=owner_id,
            label=body.label.strip(),
            phone=body.phone,
            status="not_logged_in",
        )
    except SupabaseNotConfigured:
        pass
    return {
        "account_id": account_id,
        "owner_id": owner_id,
        "label": body.label.strip(),
        "phone": body.phone,
        "status": "not_logged_in",
        "has_auth": False,
        "listener": get_listener_status(account_id),
    }


@router.patch("/{account_id}")
async def update_account(account_id: str, body: ZaloAccountUpdate):
    safe_account_id = _normalize_id(account_id)
    try:
        await upsert_zalo_account(
            safe_account_id,
            owner_id=_normalize_id(body.owner_id) if body.owner_id else "default",
            label=body.label or safe_account_id,
            phone=body.phone,
            status=body.status or "unknown",
        )
    except SupabaseNotConfigured:
        pass
    return {"account_id": safe_account_id, "updated": True}


@router.delete("/{account_id}")
async def remove_account(account_id: str, delete_auth: bool = Query(False)):
    safe_account_id = _normalize_id(account_id)
    await stop_listener(safe_account_id)
    
    sessions_removed = 0
    profile_cleared = False
    
    if delete_auth:
        await delete_zca_auth(safe_account_id)
        sessions_removed = await delete_sessions_for_user(safe_account_id)
        try:
            profile_lock = await get_profile_lock(safe_account_id)
            async with profile_lock:
                profile_cleared = clear_user_profile_data(safe_account_id)
        except Exception as exc:
            logger.warning(f"Failed to clear profile data for user={safe_account_id} after deletion: {exc}")
            
    await delete_zalo_account(safe_account_id)
    return {
        "account_id": safe_account_id,
        "deleted": True,
        "auth_deleted": delete_auth,
        "sessions_removed": sessions_removed,
        "profile_cleared": profile_cleared,
    }


@router.post("/{account_id}/listener/restart")
async def restart_account_listener(account_id: str):
    safe_account_id = _normalize_id(account_id)
    try:
        return await restart_listener(safe_account_id)
    except RuntimeError as exc:
        raise HTTPException(status_code=404, detail=str(exc))


@router.get("/inbox-report")
async def inbox_report(
    owner_id: Optional[str] = Query(None),
    account_id: List[str] = Query(default=[]),
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    try:
        return await get_zalo_inbox_report(
            [_normalize_id(item) for item in account_id],
            owner_id=_normalize_id(owner_id or x_user_id),
        )
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to build inbox report: {exc}")
