"""Unit tests for apartment agent extractor."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.modules.apartment_agent.schemas import (
    ApartmentListing,
    ExtractionResult,
    ExtractionStatus,
    ListingType,
)


@pytest.fixture
def sample_rental_message():
    return {
        "id": "msg_001",
        "text": "Cho thuê apartment 2PN Hải Châu, 70m2, 8tr/tháng, full nội thất. LH Anh Tuấn: 0905123456",
    }


@pytest.fixture
def sample_sale_message():
    return {
        "id": "msg_002",
        "text": "Bán apartment Monarchy 3PN, 120m2, 3.2 tỷ, view biển. LH 0905123456",
    }


@pytest.fixture
def sample_non_listing_message():
    return {
        "id": "msg_003",
        "text": "Chào mọi mình, hôm nay thời tiết đẹp nhỉ!",
    }


@pytest.fixture
def mock_listing_rental():
    return ApartmentListing(
        is_apartment_listing=True,
        title="Cho thuê apartment 2PN Hải Châu",
        price=8000000.0,
        area_sqm=70.0,
        bedrooms=2,
        district="Hải Châu",
        listing_type=ListingType.RENT,
        contact_name="Anh Tuấn",
        contact_phone="0905123456",
        amenities=["full nội thất"],
    )


@pytest.fixture
def mock_listing_not():
    return ApartmentListing(
        is_apartment_listing=False,
    )


class TestExtractListing:
    """Test single message extraction."""

    @pytest.mark.asyncio
    async def test_extract_rental_listing(self, sample_rental_message, mock_listing_rental):
        """Extract structured data from a rental apartment message."""
        with patch("app.modules.apartment_agent.extractor._get_client") as mock_client:
            mock_parsed = MagicMock()
            mock_parsed.parsed = mock_listing_rental
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=mock_parsed)]
            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                return_value=mock_response
            )

            from app.modules.apartment_agent.extractor import extract_listing

            result = await extract_listing(
                sample_rental_message["text"], sample_rental_message["id"]
            )

            assert result.status == ExtractionStatus.SUCCESS
            assert result.listing is not None
            assert result.listing.is_apartment_listing is True
            assert result.listing.price == 8000000.0
            assert result.listing.bedrooms == 2
            assert result.listing.district == "Hải Châu"

    @pytest.mark.asyncio
    async def test_extract_non_listing(self, sample_non_listing_message, mock_listing_not):
        """Skip messages that are not apartment listings."""
        with patch("app.modules.apartment_agent.extractor._get_client") as mock_client:
            mock_parsed = MagicMock()
            mock_parsed.parsed = mock_listing_not
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=mock_parsed)]
            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                return_value=mock_response
            )

            from app.modules.apartment_agent.extractor import extract_listing

            result = await extract_listing(
                sample_non_listing_message["text"], sample_non_listing_message["id"]
            )

            assert result.status == ExtractionStatus.NOT_LISTING
            assert result.listing is not None
            assert result.listing.is_apartment_listing is False

    @pytest.mark.asyncio
    async def test_extract_llm_error(self, sample_rental_message):
        """Handle LLM errors gracefully."""
        with patch("app.modules.apartment_agent.extractor._get_client") as mock_client:
            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                side_effect=Exception("API rate limit")
            )

            from app.modules.apartment_agent.extractor import extract_listing

            result = await extract_listing(
                sample_rental_message["text"], sample_rental_message["id"]
            )

            assert result.status == ExtractionStatus.EXTRACTION_FAILED
            assert "API rate limit" in result.error_message

    @pytest.mark.asyncio
    async def test_extract_null_parsed(self, sample_rental_message):
        """Handle LLM returning null parsed result."""
        with patch("app.modules.apartment_agent.extractor._get_client") as mock_client:
            mock_parsed = MagicMock()
            mock_parsed.parsed = None
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=mock_parsed)]
            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                return_value=mock_response
            )

            from app.modules.apartment_agent.extractor import extract_listing

            result = await extract_listing(
                sample_rental_message["text"], sample_rental_message["id"]
            )

            assert result.status == ExtractionStatus.EXTRACTION_FAILED


class TestExtractBatch:
    """Test batch extraction with concurrency control."""

    @pytest.mark.asyncio
    async def test_batch_preserves_order(self, mock_listing_rental, mock_listing_not):
        """Batch results preserve input order."""
        messages = [
            {"id": "msg_001", "text": "Cho thuê apartment 2PN"},
            {"id": "msg_002", "text": "Hello world"},
            {"id": "msg_003", "text": "Cho thuê apartment 3PN"},
        ]

        with patch("app.modules.apartment_agent.extractor._get_client") as mock_client:
            # Return different results for each call
            results_sequence = []
            for listing in [mock_listing_rental, mock_listing_not, mock_listing_rental]:
                mock_parsed = MagicMock()
                mock_parsed.parsed = listing
                mock_response = MagicMock()
                mock_response.choices = [MagicMock(message=mock_parsed)]
                results_sequence.append(mock_response)

            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                side_effect=results_sequence
            )

            from app.modules.apartment_agent.extractor import extract_batch

            results = await extract_batch(messages, concurrency=2)

            assert len(results) == 3
            assert results[0].raw_message_id == "msg_001"
            assert results[1].raw_message_id == "msg_002"
            assert results[2].raw_message_id == "msg_003"
