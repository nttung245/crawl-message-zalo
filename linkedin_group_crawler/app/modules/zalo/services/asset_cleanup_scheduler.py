from __future__ import annotations

import asyncio

from loguru import logger

from app.modules.zalo.config import settings
from app.modules.zalo.services.supabase_service import (
    SupabaseNotConfigured,
    cleanup_expired_assets,
    is_supabase_configured,
)


async def start_asset_cleanup_scheduler(interval_seconds: int = 24 * 3600) -> None:
    await asyncio.sleep(60)
    while True:
        try:
            if is_supabase_configured():
                result = await cleanup_expired_assets(
                    retention_days=settings.asset_retention_days,
                    limit=settings.asset_cleanup_batch_size,
                )
                logger.info(
                    "Zalo asset cleanup finished: scanned={} expired={} deleted={}",
                    result.get("scanned"),
                    result.get("expired_assets"),
                    result.get("deleted_storage_objects"),
                )
            else:
                logger.info("Zalo asset cleanup skipped: Supabase is not configured")
        except SupabaseNotConfigured:
            logger.info("Zalo asset cleanup skipped: Supabase is not configured")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(f"Zalo asset cleanup failed: {exc}")

        await asyncio.sleep(interval_seconds)
