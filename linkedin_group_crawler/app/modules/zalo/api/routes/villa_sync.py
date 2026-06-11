"""API endpoint for syncing Zalo crawl data to GoDaNang villas table."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from loguru import logger

from app.modules.apartment_agent.config import validate_settings

router = APIRouter(prefix="/api/zalo", tags=["villa-sync"])


class VillaSyncRequest(BaseModel):
    """Request to trigger villa sync."""

    user_id: str = Field(default="default", description="Zalo user ID to sync messages for")
    dry_run: bool = Field(default=False, description="If true, return planned changes without executing")


class VillaSyncResponse(BaseModel):
    """Response after villa sync."""

    total_messages_processed: int = 0
    apartments_found: int = 0
    new_villas_created: int = 0
    villas_updated: int = 0
    villas_marked_rented: int = 0
    errors: list[str] = Field(default_factory=list)
    dry_run: bool = False


@router.post("/villa-sync", response_model=VillaSyncResponse)
async def villa_sync_endpoint(req: VillaSyncRequest) -> VillaSyncResponse:
    """Trigger incremental sync from Zalo messages to GoDaNang villas table.

    Flow: Fetch new messages -> LLM extraction -> dedup by address+room ->
    POST new villas / PUT existing (skip images) -> mark rented as inactive.

    Set dry_run=true to preview changes without executing.
    """
    missing = validate_settings()
    if missing:
        raise HTTPException(
            status_code=500,
            detail=f"Missing required settings: {', '.join(missing)}",
        )

    from app.modules.zalo.services.villa_sync_service import sync_villas

    try:
        logger.info(f"VillaSync API: starting sync (user_id={req.user_id}, dry_run={req.dry_run})")
        summary = await sync_villas(
            user_id=req.user_id,
            dry_run=req.dry_run,
        )
        return VillaSyncResponse(
            **summary.to_dict(),
            dry_run=req.dry_run,
        )
    except Exception as exc:
        logger.error(f"VillaSync API: sync failed: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Sync failed: {exc}",
        )
