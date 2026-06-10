"""Pipeline orchestration: extract → dedup → sync."""

from __future__ import annotations

from loguru import logger

from app.modules.apartment_agent.dedup import check_duplicate, fetch_existing_apartments
from app.modules.apartment_agent.extractor import extract_batch
from app.modules.apartment_agent.schemas import (
    ExtractionStatus,
    PipelineResult,
    SyncResult,
    SyncStatus,
)
from app.modules.apartment_agent.sync import insert_apartment



async def extract_only(messages: list[dict]) -> "TestExtractResponse":
    """Run only the extraction step (no dedup/sync) for testing.

    Args:
        messages: List of dicts with 'id' and 'text' keys.

    Returns:
        TestExtractResponse with per-message extraction outcomes.
    """
    from app.modules.apartment_agent.router import TestExtractListing, TestExtractResponse, TestExtractResult

    result = TestExtractResponse(total=len(messages))
    message_map = {str(m.get("id", "")): m for m in messages}

    logger.info(f"Test extract: extracting {len(messages)} messages")
    extractions = await extract_batch(messages)

    for ext in extractions:
        raw_text = message_map.get(ext.raw_message_id, {}).get("text", "")
        if ext.status == ExtractionStatus.NOT_LISTING:
            result.not_listing += 1
            result.results.append(
                TestExtractResult(
                    raw_message_id=ext.raw_message_id,
                    raw_text=raw_text,
                    status="not_listing",
                )
            )
            continue

        if ext.status == ExtractionStatus.EXTRACTION_FAILED:
            result.failed += 1
            result.results.append(
                TestExtractResult(
                    raw_message_id=ext.raw_message_id,
                    raw_text=raw_text,
                    status="failed",
                    error_message=ext.error_message,
                )
            )
            continue

        listing = ext.listing
        if listing is None:
            result.failed += 1
            result.results.append(
                TestExtractResult(
                    raw_message_id=ext.raw_message_id,
                    raw_text=raw_text,
                    status="failed",
                    error_message="No listing data after extraction",
                )
            )
            continue

        result.extracted += 1
        test_listing = TestExtractListing(
            apartment_name=listing.title or None,
            district=listing.district,
            address=None,
            bedrooms=listing.bedrooms,
            price_vnd=listing.price,
            area_m2=listing.area_sqm,
            contact_phone=listing.contact_phone,
            contact_zalo=None,
            image_count=len(listing.images),
            images=listing.images,
            raw_text=raw_text,
        )
        result.results.append(
            TestExtractResult(
                raw_message_id=ext.raw_message_id,
                raw_text=raw_text,
                status="extracted",
                listing=test_listing,
            )
        )

    logger.info(
        f"Test extract complete: {result.extracted} extracted, "
        f"{result.not_listing} not_listing, {result.failed} failed"
    )
    return result


async def process_messages(messages: list[dict]) -> PipelineResult:
    """Run the full pipeline: extract → dedup → sync.

    Args:
        messages: List of dicts with 'id' and 'text' keys.

    Returns:
        PipelineResult with per-message outcomes and aggregate counts.
    """
    result = PipelineResult(total_processed=len(messages))

    # Step 1: Extract
    logger.info(f"Pipeline: extracting {len(messages)} messages")
    extractions = await extract_batch(messages)
    message_map = {str(m.get("id", "")): m for m in messages}

    for ext in extractions:
        msg_id = ext.raw_message_id

        if ext.status == ExtractionStatus.NOT_LISTING:
            result.results.append(
                SyncResult(
                    message_id=msg_id,
                    extraction_status=ext.status,
                    sync_status=SyncStatus.SKIPPED_NOT_LISTING,
                )
            )
            continue

        if ext.status == ExtractionStatus.EXTRACTION_FAILED:
            result.failed += 1
            result.results.append(
                SyncResult(
                    message_id=msg_id,
                    extraction_status=ext.status,
                    sync_status=SyncStatus.FAILED,
                    error_message=ext.error_message,
                )
            )
            continue

        # Step 2: Dedup
        listing = ext.listing
        if listing is None:
            result.failed += 1
            result.results.append(
                SyncResult(
                    message_id=msg_id,
                    extraction_status=ext.status,
                    sync_status=SyncStatus.FAILED,
                    error_message="No listing data after extraction",
                )
            )
            continue

        result.extracted += 1

        try:
            existing = await fetch_existing_apartments(district=listing.district)
            dedup = check_duplicate(listing, existing)
        except Exception as exc:
            logger.error(f"Pipeline: dedup failed for {msg_id}: {exc}")
            result.failed += 1
            result.results.append(
                SyncResult(
                    message_id=msg_id,
                    extraction_status=ext.status,
                    sync_status=SyncStatus.FAILED,
                    error_message=f"Dedup error: {exc}",
                )
            )
            continue

        if dedup.is_duplicate:
            result.duplicates += 1
            result.results.append(
                SyncResult(
                    message_id=msg_id,
                    extraction_status=ext.status,
                    is_duplicate=True,
                    sync_status=SyncStatus.SKIPPED_DUPLICATE,
                )
            )
            continue

        # Step 3: Sync
        try:
            sync_result = await insert_apartment(listing)
            sync_result.message_id = msg_id
            sync_result.extraction_status = ext.status
            result.results.append(sync_result)

            if sync_result.sync_status == SyncStatus.INSERTED:
                result.inserted += 1
            else:
                result.failed += 1
        except Exception as exc:
            logger.error(f"Pipeline: sync failed for {msg_id}: {exc}")
            result.failed += 1
            result.results.append(
                SyncResult(
                    message_id=msg_id,
                    extraction_status=ext.status,
                    sync_status=SyncStatus.FAILED,
                    error_message=f"Sync error: {exc}",
                )
            )

    logger.info(
        f"Pipeline complete: {result.extracted} extracted, "
        f"{result.duplicates} duplicates, {result.inserted} inserted, "
        f"{result.failed} failed"
    )
    return result
