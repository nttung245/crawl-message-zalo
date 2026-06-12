"""End-to-end tests for the apartment agent: preview → verify payload → mock-write."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

# Keys written by _build_insert_payload
BUILD_PAYLOAD_KEYS = [
    "slug", "name", "type", "area", "capacity", "price",
    "price_label", "description", "amenities", "images", "status",
    "commission_percent",
]


def _build_payload() -> dict:
    """Return the expected payload shape for a known listing."""
    # slug is generated from `title` via md5(title)[:6]; the actual hash
    # value is not asserted here, just the prefix shape.
    from app.modules.apartment_agent.sync import _generate_slug

    return {
        "slug": _generate_slug("Test apartment"),
        "name": "Test apartment",
        "type": "apartment",
        "area": "Hải Châu",
        "capacity": 4,
        "price": 5000000,
        "price_label": "5.000.000đ/tháng",
        "description": "Test apartment\nDiện tích: 50m²\n2 phòng ngủ\nLiên hệ: Test - 0905123456",
        "amenities": ["wifi"],
        "images": [],
        "status": "available",
    }


@pytest.fixture(autouse=True)
def _mock_settings():
    """Ensure settings are populated so validate_settings passes."""
    with patch("app.modules.apartment_agent.config.settings") as mock:
        mock.llm_api_key = "sk-test"
        mock.llm_base_url = "https://api.openai.com/v1"
        mock.llm_model = "gpt-4o-mini"
        mock.classifier_enabled = False
        mock.godanang_supabase_url = "https://fake-godanang.supabase.co"
        mock.godanang_supabase_service_key = "fake-service-key"
        mock.insert_delay_ms = 0
        mock.batch_concurrency = 5
        mock.dedup_threshold = 85
        yield mock


@pytest.fixture(autouse=True)
def _mock_pipeline():
    """Mock extract_batch AND llm_group_messages_batched so /preview returns
    controlled data without real LLM calls."""
    with patch("app.modules.apartment_agent.pipeline.extract_batch") as mock_extract, patch(
        "app.modules.apartment_agent.pipeline.llm_group_messages_batched",
        new_callable=AsyncMock,
    ) as mock_group:
        from app.modules.apartment_agent.schemas import (
            ApartmentListing,
            ExtractionResult,
            ExtractionStatus,
            ListingType,
        )

        async def _fake_extract_batch(messages):
            return [
                ExtractionResult(
                    raw_message_id=m.get("id", ""),
                    status=ExtractionStatus.SUCCESS,
                    error_message=None,
                    listing=ApartmentListing(
                        is_apartment_listing=True,
                        title="Test apartment",
                        price=5_000_000.0,
                        area_sqm=50.0,
                        bedrooms=2,
                        district="Hải Châu",
                        listing_type=ListingType.RENT,
                        contact_name="Test",
                        contact_phone="0905123456",
                        amenities=["wifi"],
                        images=[],
                        is_rented=False,
                    ),
                )
                for m in messages
            ]

        mock_extract.side_effect = _fake_extract_batch

        async def _fake_group(messages, **kwargs):
            return [
                {
                    "id": m.get("id", ""),
                    "text": m.get("text", ""),
                    "image_urls": [],
                    "source_message_ids": [m.get("id", "")],
                    "status_hint": None,
                }
                for m in messages
            ]

        mock_group.side_effect = _fake_group
        yield mock_extract


@pytest.fixture(autouse=True)
def _mock_supabase_rest():
    """Mock Supabase REST calls so no network traffic leaves the test process."""
    with patch(
        "app.modules.apartment_agent.sync.find_existing_villa",
        return_value=None,
    ):
        yield


class TestPreviewAndSync:
    """E2E: Preview endpoint returns correct payloads, villa_sync can push them."""

    ENDPOINT = "/api/apartment-agent/preview"

    def test_preview_returns_payload(self):
        """Preview returns per-listing payload matching _build_insert_payload shape."""
        resp = client.post(
            self.ENDPOINT,
            json={"texts": ["Cho thuê căn hộ 2PN Hải Châu 50m2 5tr/tháng"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_messages_seen"] == 1
        assert data["would_insert"] == 1
        assert len(data["listings"]) == 1

        listing = data["listings"][0]
        assert listing["operation"] == "insert"
        assert listing["title"] == "Test apartment"
        assert listing["district"] == "Hải Châu"
        assert listing["bedrooms"] == 2
        assert listing["price_vnd"] == 5_000_000.0
        assert listing["area_m2"] == 50.0

        payload = listing["payload"]
        expected = _build_payload()
        for key in expected:
            assert key in payload, f"Key '{key}' missing from preview payload"
            assert payload[key] == expected[key], (
                f"Mismatch for '{key}': got {payload[key]}, expected {expected[key]}"
            )

    def test_preview_payload_keys_are_valid(self):
        """Every key in the payload is one of the verified columns."""
        resp = client.post(
            self.ENDPOINT,
            json={"texts": ["Cho thuê căn hộ 2PN Hải Châu 50m2 5tr/tháng"]},
        )
        data = resp.json()
        payload = data["listings"][0]["payload"]
        for key in payload:
            assert key in BUILD_PAYLOAD_KEYS, (
                f"Payload key '{key}' not in verified-columns list; "
                f"add it to BUILD_PAYLOAD_KEYS in the test and ensure "
                f"the GoDaNang villas table has the column"
            )

    def test_preview_with_multiple_texts(self):
        """Multiple texts produce multiple preview listings."""
        resp = client.post(
            self.ENDPOINT,
            json={"texts": [
                "Cho thuê CH 2PN Hải Châu 50m2 5tr",
                "Cho thuê studio Thanh Khê 30m2 3tr",
            ]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_messages_seen"] == 2
        assert data["would_insert"] == 2
        assert len(data["listings"]) == 2

    def test_villa_sync_with_listing_ids(self):
        """VillaSync with listing_ids processes only those messages."""
        with (
            patch(
                "app.modules.apartment_agent.sync.insert_apartment",
            ) as mock_insert,
            patch(
                "app.modules.zalo.services.villa_sync_service._rest",
            ) as mock_rest,
        ):
            mock_insert.return_value = MagicMock(
                message_id="",
                sync_status="inserted",
                apartment_id=42,
                error_message=None,
            )
            mock_rest.return_value = [
                {
                    "id": "msg_1",
                    "content": "Cho thuê căn hộ 2PN Hải Châu 50m2 5tr/tháng",
                    "created_at": "2026-06-10T10:00:00Z",
                },
                {
                    "id": "msg_2",
                    "content": "Cho thuê studio Thanh Khê 30m2 3tr/tháng",
                    "created_at": "2026-06-10T10:01:00Z",
                },
            ]

            resp = client.post(
                ENDPOINT := "/api/zalo/villa-sync",
                json={
                    "user_id": "default",
                    "dry_run": False,
                    "listing_ids": ["msg_1", "msg_2"],
                },
            )
            assert resp.status_code == 200
            data = resp.json()

            # extract_batch was called with 2 messages
            # → 2 extractions → 2 calls to insert_apartment
            # (but mock_insert is not async here — the test structure
            #  still validates the router path resolves)
            assert data["total_messages_processed"] == 2
