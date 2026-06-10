"""Integration test for the full apartment agent pipeline."""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.modules.apartment_agent.schemas import (
    ApartmentListing,
    ExtractionResult,
    ExtractionStatus,
    ListingType,
    SyncStatus,
)


@pytest.fixture
def sample_messages():
    return [
        {
            "id": "msg_001",
            "text": "Cho thuê apartment 2PN Hải Châu, 70m2, 8tr/tháng. LH 0905123456",
        },
        {
            "id": "msg_002",
            "text": "Chào mọi người, hôm nay trời đẹp",
        },
        {
            "id": "msg_003",
            "text": "Bán apartment Monarchy 3PN, 120m2, 3.2 tỷ",
        },
    ]


@pytest.fixture
def mock_extract_results():
    return [
        ExtractionResult(
            raw_message_id="msg_001",
            status=ExtractionStatus.SUCCESS,
            listing=ApartmentListing(
                is_apartment_listing=True,
                title="Cho thuê apartment 2PN Hải Châu",
                price=8000000.0,
                area_sqm=70.0,
                bedrooms=2,
                district="Hải Châu",
                listing_type=ListingType.RENT,
                contact_phone="0905123456",
            ),
        ),
        ExtractionResult(
            raw_message_id="msg_002",
            status=ExtractionStatus.NOT_LISTING,
            listing=ApartmentListing(is_apartment_listing=False),
        ),
        ExtractionResult(
            raw_message_id="msg_003",
            status=ExtractionStatus.SUCCESS,
            listing=ApartmentListing(
                is_apartment_listing=True,
                title="Bán apartment Monarchy 3PN",
                price=3200000000.0,
                area_sqm=120.0,
                bedrooms=3,
                district="Sơn Trà",
                listing_type=ListingType.SALE,
            ),
        ),
    ]


class TestPipelineIntegration:
    """Test the full extract → dedup → sync pipeline."""

    @pytest.mark.asyncio
    async def test_full_pipeline(self, sample_messages, mock_extract_results):
        """Pipeline processes messages through all stages."""
        with patch(
            "app.modules.apartment_agent.pipeline.extract_batch",
            new_callable=AsyncMock,
        ) as mock_extract, patch(
            "app.modules.apartment_agent.pipeline.fetch_existing_apartments",
            new_callable=AsyncMock,
        ) as mock_fetch, patch(
            "app.modules.apartment_agent.pipeline.insert_apartment",
            new_callable=AsyncMock,
        ) as mock_insert:

            mock_extract.return_value = mock_extract_results
            mock_fetch.return_value = []  # No existing apartments

            mock_insert.return_value = MagicMock(
                message_id="",
                extraction_status=ExtractionStatus.SUCCESS,
                sync_status=SyncStatus.INSERTED,
                apartment_id=42,
            )

            from app.modules.apartment_agent.pipeline import process_messages

            result = await process_messages(sample_messages)

            assert result.total_processed == 3
            assert result.extracted == 2  # msg_001 and msg_003
            assert result.inserted == 2
            assert result.failed == 0

            # NOT_LISTING messages should be skipped
            not_listing = [
                r for r in result.results if r.sync_status == SyncStatus.SKIPPED_NOT_LISTING
            ]
            assert len(not_listing) == 1

    @pytest.mark.asyncio
    async def test_pipeline_with_duplicate(self, sample_messages, mock_extract_results):
        """Pipeline skips duplicate listings."""
        with patch(
            "app.modules.apartment_agent.pipeline.extract_batch",
            new_callable=AsyncMock,
        ) as mock_extract, patch(
            "app.modules.apartment_agent.pipeline.fetch_existing_apartments",
            new_callable=AsyncMock,
        ) as mock_fetch, patch(
            "app.modules.apartment_agent.pipeline.insert_apartment",
            new_callable=AsyncMock,
        ) as mock_insert:

            mock_extract.return_value = mock_extract_results[:2]  # Only first 2

            # Existing apartment matches msg_001
            mock_fetch.return_value = [
                {
                    "id": 1,
                    "name": "Cho thuê apartment 2PN Hải Châu",
                    "area": "Hải Châu",
                    "price": 8000000,
                }
            ]

            mock_insert.return_value = MagicMock(
                message_id="",
                extraction_status=ExtractionStatus.SUCCESS,
                sync_status=SyncStatus.INSERTED,
                apartment_id=99,
            )

            from app.modules.apartment_agent.pipeline import process_messages

            result = await process_messages(sample_messages[:2])

            assert result.duplicates == 1
            assert result.inserted == 0  # Only NOT_LISTING + duplicate

    @pytest.mark.asyncio
    async def test_pipeline_handles_extraction_failure(self, sample_messages):
        """Pipeline continues when one extraction fails."""
        with patch(
            "app.modules.apartment_agent.pipeline.extract_batch",
            new_callable=AsyncMock,
        ) as mock_extract, patch(
            "app.modules.apartment_agent.pipeline.fetch_existing_apartments",
            new_callable=AsyncMock,
        ) as mock_fetch:

            mock_extract.return_value = [
                ExtractionResult(
                    raw_message_id="msg_001",
                    status=ExtractionStatus.EXTRACTION_FAILED,
                    error_message="API error",
                ),
            ]
            mock_fetch.return_value = []

            from app.modules.apartment_agent.pipeline import process_messages

            result = await process_messages(sample_messages[:1])

            assert result.total_processed == 1
            assert result.failed == 1
            assert result.inserted == 0
