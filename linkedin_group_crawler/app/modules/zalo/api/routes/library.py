import re
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, Query

from app.modules.zalo.api.security import verify_zalo_api_key
from app.modules.zalo.schemas.library import (
    ZaloLibraryBulkDeleteRequest,
    ZaloLibraryBulkDeleteResponse,
    ZaloLibraryListResponse,
    ZaloLibraryMessage,
    ZaloLibraryMessageCreate,
    ZaloLibraryMessageUpdate,
)
from app.modules.zalo.services.supabase_service import (
    SupabaseNotConfigured,
    bulk_delete_library_messages,
    create_library_message,
    list_library_messages,
    update_library_message,
)

router = APIRouter(
    prefix="/api/zalo/library",
    tags=["zalo-library"],
    dependencies=[Depends(verify_zalo_api_key)],
)


def _normalize_user_id(value: str | None) -> str:
    raw = (value or "default").strip().lower()
    raw = re.sub(r"[^a-z0-9._-]+", "-", raw).strip("-._")
    return raw or "default"


@router.get("/messages", response_model=ZaloLibraryListResponse)
async def get_messages(
    x_user_id: str = Header("default", alias="X-User-ID"),
    group_name: Optional[str] = Query(None),
    limit: int = Query(200, ge=1, le=1000),
):
    try:
        rows = await list_library_messages(_normalize_user_id(x_user_id), group_name=group_name, limit=limit)
        return {"messages": [ZaloLibraryMessage(**row) for row in rows]}
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to list Zalo messages: {exc}")


@router.post("/messages", response_model=ZaloLibraryMessage)
async def create_message(
    body: ZaloLibraryMessageCreate,
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    try:
        row = await create_library_message(
            _normalize_user_id(x_user_id),
            body.model_dump(exclude={"asset_urls"}),
            body.asset_urls,
        )
        return ZaloLibraryMessage(**row)
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to create Zalo message: {exc}")


@router.post("/messages/bulk-delete", response_model=ZaloLibraryBulkDeleteResponse)
async def bulk_delete_messages(
    body: ZaloLibraryBulkDeleteRequest,
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    try:
        deleted_count = await bulk_delete_library_messages(
            _normalize_user_id(x_user_id),
            message_ids=body.message_ids,
            group_name=body.group_name,
            delete_all_matching=body.delete_all_matching,
        )
        return {"deleted_count": deleted_count}
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to bulk delete Zalo messages: {exc}")


@router.patch("/messages/{message_id}", response_model=ZaloLibraryMessage)
async def update_message(
    message_id: str,
    body: ZaloLibraryMessageUpdate,
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    try:
        row = await update_library_message(
            _normalize_user_id(x_user_id),
            message_id,
            body.model_dump(exclude_unset=True),
        )
        return ZaloLibraryMessage(**row)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to update Zalo message: {exc}")


@router.delete("/messages/{message_id}", response_model=ZaloLibraryMessage)
async def delete_message(
    message_id: str,
    x_user_id: str = Header("default", alias="X-User-ID"),
):
    try:
        row = await update_library_message(
            _normalize_user_id(x_user_id),
            message_id,
            {"is_deleted": True},
        )
        return ZaloLibraryMessage(**row)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to delete Zalo message: {exc}")
