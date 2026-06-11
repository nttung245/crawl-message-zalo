"""Sync apartment listings to GoDaNang Supabase."""

from __future__ import annotations

import asyncio
import hashlib
import re
import unicodedata
from typing import Optional

import httpx
from loguru import logger

from app.modules.apartment_agent.config import settings
from app.modules.apartment_agent.schemas import (
    ApartmentListing,
    DedupResult,
    ExtractionStatus,
    SyncResult,
    SyncStatus,
)


def _generate_slug(title: str) -> str:
    """Generate a URL-safe slug from Vietnamese title."""
    # Normalize unicode
    slug = unicodedata.normalize("NFD", title)
    # Remove diacritics
    slug = "".join(c for c in slug if unicodedata.category(c) != "Mn")
    # Lowercase and clean
    slug = slug.lower().strip()
    slug = re.sub(r"[^a-z0-9\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug).strip("-")
    # Truncate and add hash for uniqueness
    short_hash = hashlib.md5(title.encode()).hexdigest()[:6]
    return f"{slug[:50]}-{short_hash}"


def _format_price_label(price: float, listing_type: str) -> str:
    """Format price as Vietnamese currency label."""
    if listing_type == "rent":
        return f"{int(price):,}đ/tháng".replace(",", ".")
    return f"{int(price):,}đ".replace(",", ".")


def _build_insert_payload(listing: ApartmentListing) -> dict:
    """Map extracted listing to GoDaNang villas table schema."""
    slug = _generate_slug(listing.title)
    price_label = ""
    if listing.price and listing.listing_type:
        price_label = _format_price_label(listing.price, listing.listing_type.value)

    # Capacity = bedrooms * 2 (rough estimate)
    capacity = (listing.bedrooms or 1) * 2

    # Build description from listing info
    parts = []
    if listing.title:
        parts.append(listing.title)
    if listing.area_sqm:
        area_sqm = listing.area_sqm
        # Strip trailing .0 for whole numbers (50.0 → 50)
        area_str = str(area_sqm).rstrip("0").rstrip(".") if isinstance(area_sqm, float) else str(area_sqm)
        parts.append(f"Diện tích: {area_str}m²")
    if listing.bedrooms:
        parts.append(f"{listing.bedrooms} phòng ngủ")
    if listing.contact_name or listing.contact_phone:
        contact = f"Liên hệ: {listing.contact_name or ''}"
        if listing.contact_phone:
            contact += f" - {listing.contact_phone}"
        parts.append(contact.strip(" -"))
    description = "\n".join(parts)

    return {
        "slug": slug,
        "name": listing.title,
        "type": "apartment",
        "area": listing.district or "",
        "capacity": capacity,
        "price": int(listing.price) if listing.price else 0,
        "price_label": price_label,
        "description": description,
        "amenities": listing.amenities or [],
        "images": listing.images or [],
        "status": "inactive" if listing.is_rented else "active",
    }


async def insert_apartment(listing: ApartmentListing) -> SyncResult:
    """Insert a single apartment into GoDaNang Supabase."""
    url = f"{settings.godanang_supabase_url}/rest/v1/villas"
    headers = {
        "apikey": settings.godanang_supabase_service_key,
        "Authorization": f"Bearer {settings.godanang_supabase_service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    payload = _build_insert_payload(listing)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.post(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            apt_id = data[0]["id"] if data else None

            logger.info(f"Sync: INSERTED id={apt_id} title='{listing.title}'")
            return SyncResult(
                message_id="",
                extraction_status=ExtractionStatus.SUCCESS,
                sync_status=SyncStatus.INSERTED,
                apartment_id=apt_id,
            )
    except Exception as exc:
        logger.error(f"Sync: FAILED title='{listing.title}': {exc}")
        return SyncResult(
            message_id="",
            extraction_status=ExtractionStatus.SUCCESS,
            sync_status=SyncStatus.FAILED,
            error_message=str(exc),
        )



def _extract_room_identifier(title: str) -> Optional[str]:
    """Extract room/floor identifier from listing title.

    Examples: 'Phong 502' -> '502', 'Tang 5' -> '5', 'P.301' -> '301'
    """
    # Match common Vietnamese room/floor patterns
    patterns = [
        r"[Pp](?:hong|\.)\s*(\d+)",    # Phong 502, P.301
        r"[Tt](?:ang|\.)\s*(\d+)",     # Tang 5, T.3
        r"(?:Room|Unit)\s*(\d+)",       # Room 502, Unit 301
        r"#\s*(\d+)",                   # #502
        r"(\d{3,})",                    # bare 3+ digit number like 502
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return match.group(1)
    return None


def _build_update_payload(listing: ApartmentListing) -> dict:
    """Build payload for update (PUT).

    If the listing carries a non-empty `images` list, the new images
    replace the existing ones (used by the preview-then-push flow when
    the user has explicitly approved a refresh). If `images` is empty
    (the default for incremental sync), the field is omitted from the
    PUT body so we never blank out a manually-curated image list on
    GoDaNang.
    """
    payload = _build_insert_payload(listing)
    if not listing.images:
        payload.pop("images", None)
    return payload


async def update_apartment(apt_id: int, listing: ApartmentListing) -> SyncResult:
    """Update an existing apartment in GoDaNang Supabase via PUT."""
    url = f"{settings.godanang_supabase_url}/rest/v1/villas?id=eq.{apt_id}"
    headers = {
        "apikey": settings.godanang_supabase_service_key,
        "Authorization": f"Bearer {settings.godanang_supabase_service_key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation",
    }
    payload = _build_update_payload(listing)

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.put(url, json=payload, headers=headers, timeout=30)
            resp.raise_for_status()

            logger.info(f"Sync: UPDATED id={apt_id} title='{listing.title}'")
            return SyncResult(
                message_id="",
                extraction_status=ExtractionStatus.SUCCESS,
                sync_status=SyncStatus.UPDATED,
                apartment_id=apt_id,
            )
    except Exception as exc:
        logger.error(f"Sync: UPDATE FAILED id={apt_id} title='{listing.title}': {exc}")
        return SyncResult(
            message_id="",
            extraction_status=ExtractionStatus.SUCCESS,
            sync_status=SyncStatus.FAILED,
            error_message=str(exc),
        )


async def find_existing_villa(address: str, name: str) -> Optional[dict]:
    """Query GoDaNang villas table for an existing villa matching by name and slug.

    Matching strategy (Option A):
    - Extract room_id from title (e.g., 'Phong 502' -> '502')
    - Generate slug from title, use prefix (before hash) for fuzzy matching
    - Query by name + slug instead of description (which may be empty)

    Returns the matching villa dict (id, images, description, slug, name) or None.
    """
    if not name:
        return None

    room_id = _extract_room_identifier(name)
    slug = _generate_slug(name)
    # Use slug prefix (before the 6-char hash suffix) for matching
    slug_prefix = slug.rsplit("-", 1)[0] if "-" in slug else slug

    if not room_id and not slug_prefix:
        logger.debug(f"find_existing_villa: no room_id or slug from '{name}'")
        return None

    url = f"{settings.godanang_supabase_url}/rest/v1/villas"
    headers = {
        "apikey": settings.godanang_supabase_service_key,
        "Authorization": f"Bearer {settings.godanang_supabase_service_key}",
        "Content-Type": "application/json",
    }
    params: dict[str, str] = {
        "select": "id,images,description,slug,name",
        "limit": "1",
    }

    # Match by room_id in name AND slug prefix for title similarity
    if room_id and slug_prefix:
        params["name"] = f"ilike.%{room_id}%"
        params["slug"] = f"ilike.%{slug_prefix}%"
    elif slug_prefix:
        params["slug"] = f"ilike.%{slug_prefix}%"

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data:
                logger.debug(
                    f"find_existing_villa: found id={data[0].get('id')} "
                    f"for name='{name}' room='{room_id}' slug_prefix='{slug_prefix}'"
                )
                return data[0]
            return None
    except Exception as exc:
        logger.error(f"find_existing_villa: query failed for name='{name}': {exc}")
        return None


async def fetch_latest_villa_timestamp(safety_window_seconds: int = 300) -> Optional[str]:
    """Fetch the MAX(created_at) from GoDaNang villas table.

    Returns the timestamp string minus a small safety window (default
    5 minutes). The safety window prevents a race where a villa is
    inserted concurrently between the timestamp fetch and the message
    fetch — without it, a message that was just processed by another
    worker could be re-fetched and double-inserted.

    Returns None if the table is empty.
    """
    raw = await _fetch_latest_villa_timestamp_raw()
    if not raw:
        return None
    # Subtract the safety window so a concurrent write at `raw` is
    # still considered "already processed". The downstream consumer
    # uses this as a strict `> ts` filter, so a slightly older cutoff
    # is the safe direction.
    try:
        from datetime import datetime, timedelta, timezone

        ts = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        safe = ts - timedelta(seconds=safety_window_seconds)
        return safe.astimezone(timezone.utc).isoformat()
    except Exception:
        return raw


async def _fetch_latest_villa_timestamp_raw() -> Optional[str]:
    url = f"{settings.godanang_supabase_url}/rest/v1/villas"
    headers = {
        "apikey": settings.godanang_supabase_service_key,
        "Authorization": f"Bearer {settings.godanang_supabase_service_key}",
        "Content-Type": "application/json",
    }
    params = {
        "select": "created_at",
        "order": "created_at.desc",
        "limit": "1",
    }

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(url, params=params, headers=headers, timeout=30)
            resp.raise_for_status()
            data = resp.json()
            if data and data[0].get("created_at"):
                return data[0]["created_at"]
            return None
    except Exception as exc:
        logger.error(f"fetch_latest_villa_timestamp: query failed: {exc}")
        return None



async def insert_batch(
    dedup_results: list[DedupResult],
    update_existing: bool = True,
) -> list[SyncResult]:
    """Insert or update non-duplicate apartments with configurable delay.

    When *update_existing* is True, each listing is first checked against the
    existing villas table.  If a match is found the record is updated via PUT;
    otherwise a new row is inserted.
    """
    delay_s = settings.insert_delay_ms / 1000.0
    results: list[SyncResult] = []

    for dr in dedup_results:
        if dr.is_duplicate:
            results.append(
                SyncResult(
                    message_id="",
                    extraction_status=ExtractionStatus.SUCCESS,
                    is_duplicate=True,
                    sync_status=SyncStatus.SKIPPED_DUPLICATE,
                )
            )
            continue

        if update_existing:
            address = dr.listing.address or ""
            existing = await find_existing_villa(address, dr.listing.title)
            if existing:
                apt_id = existing["id"]
                result = await update_apartment(apt_id, dr.listing)
                results.append(result)
                if delay_s > 0:
                    await asyncio.sleep(delay_s)
                continue

        result = await insert_apartment(dr.listing)
        results.append(result)

        if delay_s > 0:
            await asyncio.sleep(delay_s)

    return results
