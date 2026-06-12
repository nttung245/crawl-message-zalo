"""Pipeline orchestration: group → extract → dedup → sync."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from loguru import logger

from app.modules.apartment_agent.config import settings
from app.modules.apartment_agent.dedup import check_duplicate, fetch_existing_apartments
from app.modules.apartment_agent.extractor import extract_batch, extract_batch_with_progress
from app.modules.apartment_agent.group_via_llm import llm_group_messages_batched
from app.modules.apartment_agent.schemas import (
    ExtractionStatus,
    PipelineResult,
    SyncResult,
    SyncStatus,
)
from app.modules.apartment_agent.sync import insert_apartment


async def _group_messages(
    messages: list[dict],
    window_minutes: int | None = None,
) -> list[dict]:
    """Group *messages* using the active strategy (LLM or heuristic fallback).

    Returns ``list[dict]`` with keys ``id``, ``text``, ``image_urls``,
    ``source_message_ids``, and (LLM path only) ``status_hint``.
    """
    if window_minutes is not None:
        bw = window_minutes
    else:
        bw = 30

    if settings.llm_grouping_enabled:
        return await llm_group_messages_batched(
            messages, batch_window_minutes=bw
        )

    from app.modules.apartment_agent.grouping import group_messages

    _tf = window_minutes if window_minutes is not None else 1
    groups = group_messages(messages, max_messages_per_group=4, time_fallback_minutes=_tf)
    return [g.model_dump() for g in groups]


async def extract_only(
    messages: list[dict],
    run_classifier: bool = False,
    window_minutes: int | None = None,
) -> "TestExtractResponse":
    """Run only the extraction step (no dedup/sync) for testing.

    Args:
        messages: List of dicts with 'id', 'text', 'image_urls', and
            (when grouping is desired) sender_id, sender_name,
            timestamp_text, created_at, type, is_deleted.
        run_classifier: If True, run the classifier first and skip
            non-listing messages before extraction.
        window_minutes: Override the grouping window / batch window.
            None = use default (30 min for LLM, env for heuristic).

    Returns:
        TestExtractResponse with per-message extraction outcomes.
    """
    from app.modules.apartment_agent.router import TestExtractListing, TestExtractResponse, TestExtractResult

    group_dicts = await _group_messages(messages, window_minutes)

    result = TestExtractResponse(total=len(messages))
    group_map = {str(g["id"]): g for g in group_dicts}

    # Optional classifier gate
    messages_to_extract = group_dicts
    if run_classifier:
        from app.modules.apartment_agent.classifier import classify_batch

        classifications = await classify_batch(group_dicts)
        messages_to_extract = [
            m
            for m, c in zip(group_dicts, classifications)
            if c.is_listing
        ]
        result.not_listing += len(group_dicts) - len(messages_to_extract)

    logger.info(
        f"Test extract: extracting {len(messages_to_extract)} groups "
        f"(from {len(messages)} raw messages, {len(group_dicts)} groups, "
        f"classifier filtered {len(group_dicts) - len(messages_to_extract)})"
    )
    extractions = await extract_batch(messages_to_extract)

    for ext in extractions:
        group = group_map.get(ext.raw_message_id)
        raw_text = (group.get("text") if group else "") or ""
        source_ids = group.get("source_message_ids", []) if group else []
        if ext.status == ExtractionStatus.NOT_LISTING:
            result.not_listing += 1
            result.results.append(
                TestExtractResult(
                    raw_message_id=ext.raw_message_id,
                    raw_text=raw_text,
                    status="not_listing",
                    source_message_ids=source_ids,
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
                    source_message_ids=source_ids,
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
                    source_message_ids=source_ids,
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
            source_message_ids=source_ids,
        )
        result.results.append(
            TestExtractResult(
                raw_message_id=ext.raw_message_id,
                raw_text=raw_text,
                status="extracted",
                listing=test_listing,
                source_message_ids=source_ids,
            )
        )

    logger.info(
        f"Test extract complete: {result.extracted} extracted, "
        f"{result.not_listing} not_listing, {result.failed} failed"
    )
    return result


async def extract_only_streaming(
    messages: list[dict],
    run_classifier: bool = False,
    window_minutes: int | None = None,
) -> AsyncGenerator[dict, None]:
    from app.modules.apartment_agent.router import TestExtractListing, TestExtractResponse, TestExtractResult

    group_dicts = await _group_messages(messages, window_minutes)

    result = TestExtractResponse(total=len(messages))
    group_map = {str(g["id"]): g for g in group_dicts}

    messages_to_extract = group_dicts
    if run_classifier:
        from app.modules.apartment_agent.classifier import classify_batch

        classifications = await classify_batch(group_dicts)
        messages_to_extract = [
            m
            for m, c in zip(group_dicts, classifications)
            if c.is_listing
        ]
        result.not_listing += len(group_dicts) - len(messages_to_extract)

    logger.info(
        f"Test extract streaming: extracting {len(messages_to_extract)} groups "
        f"(from {len(messages)} raw messages, {len(group_dicts)} groups, "
        f"classifier filtered {len(group_dicts) - len(messages_to_extract)})"
    )

    async for completed, total, ext in extract_batch_with_progress(messages_to_extract):
        group = group_map.get(ext.raw_message_id)
        raw_text = (group.get("text") if group else "") or ""
        source_ids = group.get("source_message_ids", []) if group else []
        if ext.status == ExtractionStatus.NOT_LISTING:
            result.not_listing += 1
            result.results.append(
                TestExtractResult(
                    raw_message_id=ext.raw_message_id,
                    raw_text=raw_text,
                    status="not_listing",
                    source_message_ids=source_ids,
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
                    source_message_ids=source_ids,
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
                    source_message_ids=source_ids,
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
            source_message_ids=source_ids,
        )
        result.results.append(
            TestExtractResult(
                raw_message_id=ext.raw_message_id,
                raw_text=raw_text,
                status="extracted",
                listing=test_listing,
                source_message_ids=source_ids,
            )
        )

        yield {
            "type": "progress",
            "completed": completed,
            "total": total,
            "extracted": result.extracted,
            "not_listing": result.not_listing,
            "failed": result.failed,
        }

    logger.info(
        f"Test extract streaming complete: {result.extracted} extracted, "
        f"{result.not_listing} not_listing, {result.failed} failed"
    )

    yield {
        "type": "result",
        "total": result.total,
        "extracted": result.extracted,
        "not_listing": result.not_listing,
        "failed": result.failed,
        "results": [r.model_dump() for r in result.results],
    }


async def process_messages(
    messages: list[dict],
    window_minutes: int | None = None,
) -> PipelineResult:
    """Run the full pipeline: group → extract → dedup → sync.

    Args:
        messages: List of dicts with 'id', 'text', 'image_urls', and
            (when grouping is desired) sender_id, sender_name,
            timestamp_text, created_at, type, is_deleted.
        window_minutes: Override the grouping / batch window.

    Returns:
        PipelineResult with per-message outcomes and aggregate counts.
    """
    group_dicts = await _group_messages(messages, window_minutes)

    result = PipelineResult(total_processed=len(messages))

    # Separate status-update items (no extraction needed) from normal listings
    extract_groups: list[dict] = []
    status_update_groups: list[dict] = []
    for g in group_dicts:
        hint = g.get("status_hint")
        if hint and hint != "available":
            status_update_groups.append(g)
        else:
            extract_groups.append(g)

    # ── Handle status updates ──────────────────────────────────────────
    if status_update_groups:
        from app.modules.apartment_agent.sync import (
            find_existing_villa,
            update_listing_status,
        )

        for g in status_update_groups:
            gid = str(g.get("id", ""))
            hint = g["status_hint"]
            title = (g.get("text") or "")[:80]

            existing = await find_existing_villa("", title)
            if existing:
                ok = await update_listing_status(existing["id"], hint)
                if ok:
                    result.extracted += 1
                    result.results.append(
                        SyncResult(
                            message_id=gid,
                            extraction_status=ExtractionStatus.SUCCESS,
                            sync_status=SyncStatus.UPDATED,
                            apartment_id=existing["id"],
                        )
                    )
                    logger.info(
                        f"Status update: villa={existing['id']} → '{hint}' "
                        f"for msg={gid}"
                    )
                else:
                    result.failed += 1
                    result.results.append(
                        SyncResult(
                            message_id=gid,
                            extraction_status=ExtractionStatus.SUCCESS,
                            sync_status=SyncStatus.FAILED,
                            error_message=f"Status update failed: villa={existing['id']}",
                        )
                    )
            else:
                logger.warning(
                    f"Status update: no existing villa for '{title}' msg={gid}"
                )
                result.results.append(
                    SyncResult(
                        message_id=gid,
                        extraction_status=ExtractionStatus.NOT_LISTING,
                        sync_status=SyncStatus.SKIPPED_NOT_LISTING,
                        error_message="status_update_no_match",
                    )
                )

    if not extract_groups:
        logger.info(
            f"Pipeline: no extraction groups — "
            f"{len(status_update_groups)} status updates processed"
        )
        return result

    # ── Step 1: Extract ────────────────────────────────────────────────
    logger.info(
        f"Pipeline: extracting {len(extract_groups)} groups "
        f"(from {len(messages)} raw messages, "
        f"{len(status_update_groups)} status updates skipped)"
    )
    extractions = await extract_batch(extract_groups)
    group_map = {str(g["id"]): g for g in extract_groups}

    for ext in extractions:
        group = group_map.get(ext.raw_message_id)
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
    seen_classified = 0
    would_insert = 0
    would_update = 0
    would_skip = 0

    for tr in test_result.results:
        if tr.status == "extracted" and tr.listing:
            seen_classified += 1
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
                    source_message_ids=tr.source_message_ids,
                )
            )
        elif tr.status == "not_listing":
            seen_classified += 1
        else:
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
