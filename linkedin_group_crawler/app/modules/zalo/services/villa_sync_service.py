"""Villa sync service: incremental sync from Zalo messages to GoDaNang villas table."""

from __future__ import annotations

import asyncio
from typing import Optional

from loguru import logger

from app.modules.apartment_agent.config import settings as agent_settings
from app.modules.apartment_agent.extractor import extract_batch
from app.modules.apartment_agent.schemas import (
    ExtractionStatus,
    SyncStatus,
)
from app.modules.apartment_agent.sync import (
    fetch_latest_villa_timestamp,
    find_existing_villa,
    insert_apartment,
    update_apartment,
)
from app.modules.zalo.services.supabase_service import _rest


class VillaSyncSummary:
    """Summary of a villa sync run."""

    def __init__(self) -> None:
        self.total_messages_processed: int = 0
        self.apartments_found: int = 0
        self.new_villas_created: int = 0
        self.villas_updated: int = 0
        self.villas_marked_rented: int = 0
        self.errors: list[str] = []

    def to_dict(self) -> dict:
        return {
            "total_messages_processed": self.total_messages_processed,
            "apartments_found": self.apartments_found,
            "new_villas_created": self.new_villas_created,
            "villas_updated": self.villas_updated,
            "villas_marked_rented": self.villas_marked_rented,
            "errors": self.errors,
        }


async def fetch_incremental_messages(
    user_id: str = "default",
    limit: int = 200,
) -> list[dict]:
    """Fetch Zalo messages newer than the latest villa in GoDaNang.

    Returns list of dicts with 'id', 'text', 'timestamp' keys.
    """
    latest_ts = await fetch_latest_villa_timestamp()

    params: dict = {
        "select": "id,content,timestamp_text,created_at",
        "user_id": f"eq.{user_id}",
        "order": "created_at.desc",
        "limit": str(limit),
        "content": "not.is.null",
    }

    if latest_ts:
        logger.info(f"VillaSync: fetching messages newer than {latest_ts}")
        params["created_at"] = f"gt.{latest_ts}"
    else:
        logger.info("VillaSync: no existing villas, fetching most recent messages")

    try:
        rows = await _rest("GET", "zalo_messages", params=params) or []
        messages = []
        for row in rows:
            content = row.get("content", "")
            if content and content.strip():
                messages.append({
                    "id": row["id"],
                    "text": content,
                    "timestamp": row.get("created_at", ""),
                })
        logger.info(f"VillaSync: fetched {len(messages)} messages for processing")
        return messages
    except Exception as exc:
        logger.error(f"VillaSync: failed to fetch messages: {exc}")
        raise


async def sync_villas(
    user_id: str = "default",
    dry_run: bool = False,
    batch_size: int = 20,
    delay_between_batches: float = 1.0,
    listing_ids: Optional[list[str]] = None,
) -> VillaSyncSummary:
    """Run the full villa sync pipeline.

    1. Fetch incremental Zalo messages (newer than latest villa)
    2. Extract apartment data via LLM (batch processing)
    3. Dedup: find existing villas by address+room
    4. POST new / PUT existing (skip images on update)
    5. Mark rented villas as inactive

    When listing_ids is provided, only sync those specific messages
    instead of the incremental fetch.
    """
    summary = VillaSyncSummary()

    # Step 1: Fetch messages
    if listing_ids:
        messages = []
        for mid in listing_ids:
            try:
                rows = await _rest(
                    "GET",
                    "zalo_messages",
                    params={"select": "id,content", "id": f"eq.{mid}"},
                ) or []
                if rows:
                    content = rows[0].get("content", "")
                    if content and content.strip():
                        messages.append({
                            "id": rows[0]["id"],
                            "text": content,
                            "timestamp": rows[0].get("created_at", ""),
                        })
            except Exception as exc:
                summary.errors.append(f"Failed to fetch listing {mid}: {exc}")
    else:
        try:
            messages = await fetch_incremental_messages(user_id)
        except Exception as exc:
            summary.errors.append(f"Failed to fetch messages: {exc}")
            return summary

    if not messages:
        logger.info("VillaSync: no new messages to process")
        return summary

    summary.total_messages_processed = len(messages)

    # Step 2: Process in batches
    for i in range(0, len(messages), batch_size):
        batch = messages[i : i + batch_size]
        logger.info(f"VillaSync: processing batch {i // batch_size + 1} ({len(batch)} messages)")

        try:
            extractions = await extract_batch(batch)
        except Exception as exc:
            err_msg = f"LLM extraction failed for batch {i // batch_size + 1}: {exc}"
            logger.error(err_msg)
            summary.errors.append(err_msg)
            continue

        for ext in extractions:
            if ext.status == ExtractionStatus.NOT_LISTING:
                continue

            if ext.status == ExtractionStatus.EXTRACTION_FAILED:
                summary.errors.append(f"Extraction failed for {ext.raw_message_id}: {ext.error_message}")
                continue

            listing = ext.listing
            if listing is None:
                continue

            summary.apartments_found += 1

            # Track rented status
            if listing.is_rented:
                summary.villas_marked_rented += 1

            if dry_run:
                logger.info(f"VillaSync [DRY RUN]: would process '{listing.title}' (rented={listing.is_rented})")
                continue

            # Step 3: Dedup — find existing villa by address+room
            address = listing.address or ""
            existing = await find_existing_villa(address, listing.title)

            try:
                if existing:
                    # Step 4b: UPDATE existing villa (skip images)
                    apt_id = existing["id"]
                    result = await update_apartment(apt_id, listing)
                    if result.sync_status == SyncStatus.UPDATED:
                        summary.villas_updated += 1
                        logger.info(f"VillaSync: UPDATED id={apt_id} title='{listing.title}'")
                    else:
                        summary.errors.append(f"Update failed for id={apt_id}: {result.error_message}")
                else:
                    # Step 4a: INSERT new villa (with images)
                    result = await insert_apartment(listing)
                    if result.sync_status == SyncStatus.INSERTED:
                        summary.new_villas_created += 1
                        logger.info(f"VillaSync: INSERTED id={result.apartment_id} title='{listing.title}'")
                    else:
                        summary.errors.append(f"Insert failed for '{listing.title}': {result.error_message}")
            except Exception as exc:
                err_msg = f"Sync operation failed for '{listing.title}': {exc}"
                logger.error(err_msg)
                summary.errors.append(err_msg)

        # Delay between batches
        if i + batch_size < len(messages) and delay_between_batches > 0:
            await asyncio.sleep(delay_between_batches)

    logger.info(
        f"VillaSync complete: processed={summary.total_messages_processed}, "
        f"found={summary.apartments_found}, created={summary.new_villas_created}, "
        f"updated={summary.villas_updated}, rented={summary.villas_marked_rented}, "
        f"errors={len(summary.errors)}"
    )
    return summary
