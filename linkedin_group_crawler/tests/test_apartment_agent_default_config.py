"""Unit tests for default villa configuration."""

from app.modules.apartment_agent.default_config import DEFAULT_VILLA, merge_with_defaults
from app.modules.apartment_agent.schemas import ApartmentListing


class TestDefaultVilla:
    def test_importable_no_side_effects(self):
        """DEFAULT_VILLA is a plain dict — no network or I/O."""
        assert isinstance(DEFAULT_VILLA, dict)
        assert DEFAULT_VILLA["commission_percent"] == 12
        assert "bếp ga" in DEFAULT_VILLA["amenities"]
        assert DEFAULT_VILLA["type"] == "apartment"
        assert DEFAULT_VILLA["listing_status"] == "available"

    def test_merge_fills_empty_amenities(self):
        listing = ApartmentListing(
            is_apartment_listing=True,
            title="Test",
            amenities=[],
        )
        merged = merge_with_defaults(listing)
        assert merged.amenities == ["bếp ga", "phòng tắm riêng", "wifi", "máy lạnh"]

    def test_merge_preserves_llm_amenities(self):
        listing = ApartmentListing(
            is_apartment_listing=True,
            title="Test",
            amenities=["hồ bơi", "wifi"],
        )
        merged = merge_with_defaults(listing)
        assert merged.amenities == ["hồ bơi", "wifi"]

    def test_merge_all_missing_only_title_price(self):
        listing = ApartmentListing(
            is_apartment_listing=True,
            title="Sunshine Riverside A1205",
            price=8000000.0,
        )
        merged = merge_with_defaults(listing)
        assert merged.title == "Sunshine Riverside A1205"
        assert merged.price == 8000000.0
        # amenities filled from defaults
        assert merged.amenities == ["bếp ga", "phòng tắm riêng", "wifi", "máy lạnh"]

    def test_merge_does_not_touch_non_listing_fields(self):
        """commission_percent, type, listing_status are NOT on ApartmentListing."""
        listing = ApartmentListing(is_apartment_listing=True, title="Test")
        merged = merge_with_defaults(listing)
        # These fields don't exist on ApartmentListing
        assert not hasattr(merged, "commission_percent")
        assert not hasattr(merged, "listing_status")
