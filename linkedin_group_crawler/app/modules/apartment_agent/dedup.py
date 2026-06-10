"""Deduplication logic for apartment listings."""

from __future__ import annotations

from typing import Optional

import httpx
from loguru import logger
from thefuzz import fuzz

from app.modules.apartment_agent.config import settings
from app.modules.apartment_agent.schemas import ApartmentListing, DedupResult


async def fetch_existing_apartments(district: Optional[str] = None) -> list[dict]:
    """Fetch existing apartments from GoDaNang Supabase villas table."""
    url = f"{settings.godanang_supabase_url}/rest/v1/villas"
    params = {"type": "eq.apartment", "select": "id,name,area,price,description"}
    if district:
        params["area"] = f"eq.{district}"

    headers = {
        "apikey": settings.godanang_supabase_service_key,
        "Authorization": f"Bearer {settings.godanang_supabase_service_key}",
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()


def check_duplicate(
    listing: ApartmentListing,
    existing_apartments: list[dict],
    threshold: Optional[int] = None,
) -> DedupResult:
    """Check if a listing is a duplicate of an existing apartment.

    Uses fuzzy token_sort_ratio on title. If similarity is borderline
    (80-threshold), cross-checks area and price as secondary signals.
    """
    thresh = threshold or settings.dedup_threshold
    best_score = 0.0
    best_match: Optional[dict] = None

    for apt in existing_apartments:
        existing_title = apt.get("name", "")
        score = fuzz.token_sort_ratio(listing.title.lower(), existing_title.lower())

        if score > best_score:
            best_score = score
            best_match = apt

    # Clear duplicate above threshold
    if best_score >= thresh:
        logger.info(
            f"Dedup: DUPLICATE title='{listing.title}' "
            f"matched='{best_match.get('name', '')}' score={best_score}"
        )
        return DedupResult(
            listing=listing,
            is_duplicate=True,
            matched_existing_id=best_match.get("id") if best_match else None,
            similarity_score=best_score,
        )

    # Borderline range (80-threshold): cross-check area + price
    if 80 <= best_score < thresh and best_match:
        area_match = (
            listing.area_sqm is None
            or best_match.get("area") is None
            or listing.area_sqm == best_match.get("area")
        )
        price_match = (
            listing.price is None
            or best_match.get("price") is None
            or listing.price == best_match.get("price")
        )

        if area_match and price_match:
            logger.info(
                f"Dedup: DUPLICATE (borderline) title='{listing.title}' "
                f"matched='{best_match.get('name', '')}' score={best_score}"
            )
            return DedupResult(
                listing=listing,
                is_duplicate=True,
                matched_existing_id=best_match.get("id"),
                similarity_score=best_score,
            )

    logger.info(f"Dedup: NEW listing='{listing.title}' best_score={best_score}")
    return DedupResult(
        listing=listing,
        is_duplicate=False,
        similarity_score=best_score,
    )
