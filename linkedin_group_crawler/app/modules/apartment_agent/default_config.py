"""Default configuration for GoDaNang villa fields.

Values here are merged with LLM-extracted output — the LLM only fills
fields it can determine from the message text; defaults fill the rest.
Changing a default does NOT invalidate the LLM's output cache.
"""

from __future__ import annotations

from app.modules.apartment_agent.schemas import ApartmentListing

# Fields that exist on ApartmentListing model — defaults merge into the listing.
_LISTING_FIELDS = {"amenities"}

# Fields that go directly into the GoDaNang villas payload — merge happens
# at sync time in _build_insert_payload / _build_update_payload.
DEFAULT_VILLA: dict = {
    "commission_percent": 12,
    "amenities": ["bếp ga", "phòng tắm riêng", "wifi", "máy lạnh"],
    "type": "apartment",
    "listing_status": "available",
}


def merge_with_defaults(listing: ApartmentListing) -> ApartmentListing:
    """Fill missing ``ApartmentListing`` fields from ``DEFAULT_VILLA``.

    LLM-extracted values take priority — defaults only apply when the
    corresponding field on *listing* is ``None`` or an empty list.
    Only fields that exist on the ``ApartmentListing`` model are merged;
    GoDaNang-only fields (``commission_percent``, etc.) are applied at
    the sync layer.
    """
    data = listing.model_dump(exclude_none=False)
    for key in _LISTING_FIELDS:
        default_val = DEFAULT_VILLA.get(key)
        if default_val is None:
            continue
        existing = data.get(key)
        if existing is None:
            data[key] = default_val
        elif isinstance(existing, list) and not existing:
            data[key] = default_val
    return ApartmentListing(**data)
