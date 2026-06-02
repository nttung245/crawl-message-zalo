from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.modules.zalo.api.security import verify_zalo_api_key
from app.modules.zalo.config import settings
from app.modules.zalo.services.supabase_service import (
    SupabaseNotConfigured,
    cleanup_expired_assets,
)

router = APIRouter(
    prefix="/api/zalo/maintenance",
    tags=["zalo-maintenance"],
    dependencies=[Depends(verify_zalo_api_key)],
)


class CleanupAssetsRequest(BaseModel):
    retention_days: int | None = Field(default=None, ge=1, le=365)
    limit: int | None = Field(default=None, ge=1, le=1000)


class CleanupAssetsResponse(BaseModel):
    retention_days: int
    limit: int
    cutoff: str
    scanned: int
    deleted_storage_objects: int
    expired_assets: int
    failed: list[dict]


@router.post("/cleanup-assets", response_model=CleanupAssetsResponse)
async def cleanup_assets(body: CleanupAssetsRequest | None = None):
    retention_days = (
        body.retention_days
        if body and body.retention_days is not None
        else settings.asset_retention_days
    )
    limit = (
        body.limit
        if body and body.limit is not None
        else settings.asset_cleanup_batch_size
    )

    try:
        result = await cleanup_expired_assets(retention_days=retention_days, limit=limit)
        return {
            "retention_days": retention_days,
            "limit": limit,
            **result,
        }
    except SupabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to cleanup Zalo assets: {exc}")
