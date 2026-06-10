"""Unit tests for apartment agent sync module."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.modules.apartment_agent.schemas import (
    ApartmentListing,
    DedupResult,
    ListingType,
    SyncStatus,
)
from app.modules.apartment_agent.sync import (
    _format_price_label,
    _generate_slug,
    _build_insert_payload,
    insert_apartment,
    insert_batch,
)


class TestSlugGeneration:
    """Test URL-safe slug generation from Vietnamese titles."""

    def test_basic_slug(self):
        slug = _generate_slug("Cho thuê apartment 2PN Hải Châu")
        assert "cho-thue" in slug
        assert "apartment" in slug
        assert len(slug) > 10

    def test_slug_uniqueness(self):
        """Same title produces same slug (deterministic)."""
        s1 = _generate_slug("Apartment Hải Châu")
        s2 = _generate_slug("Apartment Hải Châu")
        assert s1 == s2

    def test_different_titles_different_slugs(self):
        s1 = _generate_slug("Apartment Hải Châu 2PN")
        s2 = _generate_slug("Apartment Sơn Trà 3PN")
        assert s1 != s2


class TestPriceFormatting:
    """Test Vietnamese price label formatting."""

    def test_rental_price(self):
        label = _format_price_label(8000000, "rent")
        assert "8.000.000" in label
        assert "tháng" in label

    def test_sale_price(self):
        label = _format_price_label(3200000000, "sale")
        assert "3.200.000.000" in label
        assert "đ" in label


class TestBuildInsertPayload:
    """Test mapping extracted data to GoDaNang schema."""

    def test_complete_payload(self):
        listing = ApartmentListing(
            is_apartment_listing=True,
            title="Cho thuê apartment 2PN Hải Châu",
            price=8000000.0,
            area_sqm=70.0,
            bedrooms=2,
            district="Hải Châu",
            listing_type=ListingType.RENT,
            contact_name="Anh Tuấn",
            contact_phone="0905123456",
            amenities=["nội thất", "wifi"],
        )
        payload = _build_insert_payload(listing)

        assert payload["type"] == "apartment"
        assert payload["name"] == "Cho thuê apartment 2PN Hải Châu"
        assert payload["area"] == "Hải Châu"
        assert payload["capacity"] == 4  # bedrooms * 2
        assert payload["price"] == 8000000
        assert "8.000.000" in payload["price_label"]
        assert payload["amenities"] == ["nội thất", "wifi"]
        assert payload["status"] == "active"
        assert "slug" in payload

    def test_missing_optional_fields(self):
        listing = ApartmentListing(
            is_apartment_listing=True,
            title="Apartment test",
        )
        payload = _build_insert_payload(listing)

        assert payload["price"] == 0
        assert payload["price_label"] == ""
        assert payload["amenities"] == []
        assert payload["images"] == []
        assert payload["capacity"] == 2  # default 1 bedroom * 2


class TestInsertApartment:
    """Test Supabase insert with mocked HTTP client."""

    @pytest.mark.asyncio
    async def test_successful_insert(self):
        listing = ApartmentListing(
            is_apartment_listing=True,
            title="Test apartment",
            price=5000000.0,
            district="Hải Châu",
            listing_type=ListingType.RENT,
        )

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = [{"id": 42}]
        mock_response.raise_for_status = MagicMock()

        with patch("app.modules.apartment_agent.sync.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            result = await insert_apartment(listing)

            assert result.sync_status == SyncStatus.INSERTED
            assert result.apartment_id == 42

    @pytest.mark.asyncio
    async def test_failed_insert(self):
        listing = ApartmentListing(
            is_apartment_listing=True,
            title="Test apartment",
        )

        with patch("app.modules.apartment_agent.sync.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                side_effect=Exception("Connection refused")
            )

            result = await insert_apartment(listing)

            assert result.sync_status == SyncStatus.FAILED
            assert "Connection refused" in result.error_message


class TestInsertBatch:
    """Test batch insert with delay."""

    @pytest.mark.asyncio
    async def test_skips_duplicates(self):
        dedup_results = [
            DedupResult(
                listing=ApartmentListing(is_apartment_listing=True, title="Dup"),
                is_duplicate=True,
            ),
            DedupResult(
                listing=ApartmentListing(is_apartment_listing=True, title="New"),
                is_duplicate=False,
            ),
        ]

        mock_response = MagicMock()
        mock_response.status_code = 201
        mock_response.json.return_value = [{"id": 1}]
        mock_response.raise_for_status = MagicMock()

        with patch("app.modules.apartment_agent.sync.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.post = AsyncMock(
                return_value=mock_response
            )

            with patch("app.modules.apartment_agent.sync.settings") as mock_settings:
                mock_settings.insert_delay_ms = 0  # No delay in tests
                mock_settings.godanang_supabase_url = "https://test.supabase.co"
                mock_settings.godanang_supabase_service_key = "test-key"

                results = await insert_batch(dedup_results)

            assert len(results) == 2
            assert results[0].sync_status == SyncStatus.SKIPPED_DUPLICATE
            assert results[1].sync_status == SyncStatus.INSERTED
