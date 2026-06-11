"""Pipeline orchestration: extract → dedup → sync."""

from __future__ import annotations

from loguru import logger

from app.modules.apartment_agent.dedup import check_duplicate, fetch_existing_apartments
from app.modules.apartment_agent.extractor import extract_batch
from app.modules.apartment_agent.schemas import (
    ClassificationResult,
    ExtractionStatus,
    PipelineResult,
    SyncResult,
    SyncStatus,
)
from app.modules.apartment_agent.sync import insert_apartment



async def extract_only(
    messages: list[dict],
    run_classifier: bool = False,
) -> "TestExtractResponse":
    """Run only the extraction step (no dedup/sync) for testing.

    Args:
        messages: List of dicts with 'id' and 'text' keys.
        run_classifier: If True, run the classifier first and skip
            non-listing messages before extraction.

    Returns:
        TestExtractResponse with per-message extraction outcomes.
    """
    from app.modules.apartment_agent.router import TestExtractListing, TestExtractResponse, TestExtractResult

    result = TestExtractResponse(total=len(messages))
    message_map = {str(m.get("id", "")): m for m in messages}

    # Optional classifier gate
    messages_to_extract = messages
    if run_classifier:
        from app.modules.apartment_agent.classifier import classify_batch

        classifications = await classify_batch(messages)
        messages_to_extract = [
            m
            for m, c in zip(messages, classifications)
            if c.is_listing
        ]
        result.not_listing += len(messages) - len(messages_to_extract)

    logger.info(
        f"Test extract: extracting {len(messages_to_extract)} messages "
        f"(classifier filtered {len(messages) - len(messages_to_extract)})"
    )
    extractions = await extract_batch(messages_to_extract)

    for ext in extractions:
        raw_text = message_map.get(ext.raw_message_id, {}).get("text", "") or ""
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
            contact_name=listing.contact_name or None,
            contact_phone=listing.contact_phone,
            contact_zalo=None,
            listing_type=listing.listing_type.value
            if listing.listing_type
            else None,
            is_rented=listing.is_rented,
            amenities=list(listing.amenities or []),
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


async def preview_only(
    messages: list[dict],
) -> "PreviewResponse":
    """Run classifier + extractor + dedup-read, returning payloads without writing.

    Args:
        messages: List of dicts with 'id' and 'text' keys.

    Returns:
        PreviewResponse with classifications, per-listing payloads, and summary.
    """
    from app.modules.apartment_agent.router import PreviewListing, PreviewResponse
    from app.modules.apartment_agent.sync import (
        _build_insert_payload,
        _build_update_payload,
        find_existing_villa,
    )

    test_result = await extract_only(messages, run_classifier=True)
    listings: list[PreviewListing] = []
    classifications: list[ClassificationResult] = []
    seen_classified = 0
    would_insert = 0
    would_update = 0
    would_skip = 0

    # Collect classifications from the extract path
    for tr in test_result.results:
        if tr.status == "extracted" and tr.listing:
            seen_classified += 1
            # Rebuild a full ApartmentListing from the TestExtractListing
            # so the sync layer's _build_insert_payload sees the same
            # shape (listing_type, is_rented, amenities) the LLM
            # originally produced.
            from app.modules.apartment_agent.schemas import (
                ApartmentListing,
                ListingType,
            )

            apt = ApartmentListing(
                is_apartment_listing=True,
                title=tr.listing.apartment_name or "",
                price=tr.listing.price_vnd,
                area_sqm=tr.listing.area_m2,
                bedrooms=tr.listing.bedrooms,
                district=tr.listing.district,
                images=tr.listing.images,
                listing_type=ListingType(tr.listing.listing_type)
                if tr.listing.listing_type
                in {lt.value for lt in ListingType}
                else None,
                is_rented=tr.listing.is_rented,
                amenities=list(tr.listing.amenities or []),
                contact_name=tr.listing.contact_name or "",
                contact_phone=tr.listing.contact_phone or "",
            )
            existing = await find_existing_villa(
                address=tr.listing.address or "",
                name=tr.listing.apartment_name or "",
            )
            if existing:
                operation = "update"
                existing_id = existing.get("id")
                payload = _build_update_payload(apt)
                would_update += 1
            else:
                operation = "insert"
                existing_id = None
                payload = _build_insert_payload(apt)
                would_insert += 1

            listings.append(
                PreviewListing(
                    raw_message_id=tr.raw_message_id,
                    raw_text=tr.raw_text,
                    title=apt.title,
                    district=apt.district,
                    bedrooms=apt.bedrooms,
                    price_vnd=apt.price,
                    area_m2=apt.area_sqm,
                    image_count=len(apt.images),
                    payload=payload,
                    operation=operation,
                    existing_villa_id=str(existing_id) if existing_id else None,
                )
            )
        elif tr.status == "not_listing":
            seen_classified += 1
        else:
            # failed extraction counts as seen
            seen_classified += 1

    result = PreviewResponse(
        total_messages_seen=test_result.total,
        classified_listing=seen_classified,
        extracted_ok=len(listings),
        would_insert=would_insert,
        would_update=would_update,
        would_skip=would_skip,
        listings=listings,
    )
    logger.info(
        f"Preview: {result.total_messages_seen} seen, "
        f"{result.classified_listing} classified, "
        f"{result.extracted_ok} extracted, "
        f"{result.would_insert} insert / {result.would_update} update / {result.would_skip} skip"
    )
    return result
