"""Sync apartment listings to GoDaNang Supabase."""

from __future__ import annotations

import asyncio
import hashlib
import re
import unicodedata

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
        parts.append(f"Diện tích: {listing.area_sqm}m²")
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
        "status": "active",
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


async def insert_batch(dedup_results: list[DedupResult]) -> list[SyncResult]:
    """Insert non-duplicate apartments with configurable delay."""
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

        result = await insert_apartment(dr.listing)
        results.append(result)

        if delay_s > 0:
            await asyncio.sleep(delay_s)

    return results
