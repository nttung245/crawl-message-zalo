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
def default_group_dicts():
    """Default LLM group output — each sample message becomes its own group."""
    return [
        {
            "id": "msg_001",
            "text": "Cho thuê apartment 2PN Hải Châu, 70m2, 8tr/tháng. LH 0905123456",
            "image_urls": [],
            "source_message_ids": ["msg_001"],
            "status_hint": None,
        },
        {
            "id": "msg_002",
            "text": "Chào mọi người, hôm nay trời đẹp",
            "image_urls": [],
            "source_message_ids": ["msg_002"],
            "status_hint": None,
        },
        {
            "id": "msg_003",
            "text": "Bán apartment Monarchy 3PN, 120m2, 3.2 tỷ",
            "image_urls": [],
            "source_message_ids": ["msg_003"],
            "status_hint": None,
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
    async def test_full_pipeline(
        self, sample_messages, default_group_dicts, mock_extract_results
    ):
        """Pipeline processes messages through all stages."""
        with patch(
            "app.modules.apartment_agent.pipeline.llm_group_messages_batched",
            new_callable=AsyncMock,
        ) as mock_group, patch(
            "app.modules.apartment_agent.pipeline.extract_batch",
            new_callable=AsyncMock,
        ) as mock_extract, patch(
            "app.modules.apartment_agent.pipeline.fetch_existing_apartments",
            new_callable=AsyncMock,
        ) as mock_fetch, patch(
            "app.modules.apartment_agent.pipeline.insert_apartment",
            new_callable=AsyncMock,
        ) as mock_insert:

            mock_group.return_value = default_group_dicts
            mock_extract.return_value = mock_extract_results
            mock_fetch.return_value = []

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

            not_listing = [
                r
                for r in result.results
                if r.sync_status == SyncStatus.SKIPPED_NOT_LISTING
            ]
            assert len(not_listing) == 1

    @pytest.mark.asyncio
    async def test_pipeline_with_duplicate(
        self, sample_messages, default_group_dicts, mock_extract_results
    ):
        """Pipeline skips duplicate listings."""
        with patch(
            "app.modules.apartment_agent.pipeline.llm_group_messages_batched",
            new_callable=AsyncMock,
        ) as mock_group, patch(
            "app.modules.apartment_agent.pipeline.extract_batch",
            new_callable=AsyncMock,
        ) as mock_extract, patch(
            "app.modules.apartment_agent.pipeline.fetch_existing_apartments",
            new_callable=AsyncMock,
        ) as mock_fetch, patch(
            "app.modules.apartment_agent.pipeline.insert_apartment",
            new_callable=AsyncMock,
        ) as mock_insert:

            mock_group.return_value = default_group_dicts[:2]
            mock_extract.return_value = mock_extract_results[:2]

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
            assert result.inserted == 0

    @pytest.mark.asyncio
    async def test_pipeline_handles_extraction_failure(
        self, sample_messages, default_group_dicts
    ):
        """Pipeline continues when one extraction fails."""
        with patch(
            "app.modules.apartment_agent.pipeline.llm_group_messages_batched",
            new_callable=AsyncMock,
        ) as mock_group, patch(
            "app.modules.apartment_agent.pipeline.extract_batch",
            new_callable=AsyncMock,
        ) as mock_extract, patch(
            "app.modules.apartment_agent.pipeline.fetch_existing_apartments",
            new_callable=AsyncMock,
        ) as mock_fetch:

            mock_group.return_value = default_group_dicts[:1]
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

    @pytest.mark.asyncio
    async def test_status_update_skips_extraction(self):
        """A group with status_hint != available is routed to status update."""
        messages = [
            {"id": "m1", "text": "Căn Sunshine A1205 bán rồi", "sender_id": "uid_1"},
        ]
        groups_with_status = [
            {
                "id": "m1",
                "text": "Căn Sunshine A1205 bán rồi",
                "image_urls": [],
                "source_message_ids": ["m1"],
                "status_hint": "sold",
            },
        ]

        with patch(
            "app.modules.apartment_agent.pipeline.llm_group_messages_batched",
            new_callable=AsyncMock,
        ) as mock_group, patch(
            "app.modules.apartment_agent.sync.find_existing_villa",
            new_callable=AsyncMock,
        ) as mock_find, patch(
            "app.modules.apartment_agent.sync.update_listing_status",
            new_callable=AsyncMock,
        ) as mock_update, patch(
            "app.modules.apartment_agent.pipeline.extract_batch",
            new_callable=AsyncMock,
        ) as mock_extract:

            mock_group.return_value = groups_with_status
            mock_find.return_value = {"id": 42, "name": "Sunshine A1205"}
            mock_update.return_value = True

            from app.modules.apartment_agent.pipeline import process_messages

            result = await process_messages(messages)

            # Status update path was taken — no extraction called
            mock_extract.assert_not_called()
            assert result.extracted == 1
            assert result.results[0].sync_status == SyncStatus.UPDATED
            assert result.results[0].apartment_id == 42


@pytest.mark.asyncio
async def test_text_plus_image_pair_yields_one_listing():
    """Two messages from same sender (text + image) within window → one extraction."""
    from app.modules.apartment_agent.pipeline import extract_only

    now = "12/06/2026 14:35"
    messages = [
        {
            "id": "m1",
            "text": "Sunshine Riverside 2PN 8tr",
            "sender_id": "uid_1",
            "sender_name": "Anh Tuấn",
            "timestamp_text": now,
            "created_at": "2026-06-12T14:35:00Z",
            "type": "text",
            "is_deleted": False,
            "image_urls": [],
        },
        {
            "id": "m2",
            "text": "",
            "sender_id": "uid_1",
            "sender_name": "Anh Tuấn",
            "timestamp_text": "12/06/2026 14:36",
            "created_at": "2026-06-12T14:36:00Z",
            "type": "image",
            "is_deleted": False,
            "image_urls": [
                "https://cdn.zalo.me/img1.jpg",
                "https://cdn.zalo.me/img2.jpg",
            ],
        },
    ]

    with patch(
        "app.modules.apartment_agent.pipeline.llm_group_messages_batched",
        new_callable=AsyncMock,
    ) as mock_group, patch(
        "app.modules.apartment_agent.pipeline.extract_batch",
        new_callable=AsyncMock,
    ) as mock_extract:
        mock_group.return_value = [
            {
                "id": "m1",
                "text": "Sunshine Riverside 2PN 8tr\n\n",
                "image_urls": [
                    "https://cdn.zalo.me/img1.jpg",
                    "https://cdn.zalo.me/img2.jpg",
                ],
                "source_message_ids": ["m1", "m2"],
                "status_hint": None,
            },
        ]
        mock_extract.return_value = [
            ExtractionResult(
                raw_message_id="m1",
                status=ExtractionStatus.SUCCESS,
                listing=ApartmentListing(
                    is_apartment_listing=True,
                    title="Sunshine Riverside",
                    price=8000000.0,
                    area_sqm=70.0,
                    bedrooms=2,
                    district="Hải Châu",
                    listing_type=ListingType.RENT,
                ),
            ),
        ]

        result = await extract_only(messages)

        assert result.total == 2
        assert result.extracted == 1
        assert len(result.results) == 1
        r = result.results[0]
        assert r.raw_message_id == "m1"
        assert r.source_message_ids == ["m1", "m2"]
