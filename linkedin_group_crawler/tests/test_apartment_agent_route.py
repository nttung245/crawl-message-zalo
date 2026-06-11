"""Route-level tests for the apartment agent endpoints."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from app.main import app
from app.modules.apartment_agent.schemas import (
    ApartmentListing,
    ExtractionResult,
    ExtractionStatus,
    ListingType,
)


client = TestClient(app)


def _make_listing(text="Test apartment") -> ApartmentListing:
    return ApartmentListing(
        is_apartment_listing=True,
        title=text,
        price=5000000.0,
        area_sqm=50.0,
        bedrooms=2,
        district="Hải Châu",
        listing_type=ListingType.RENT,
        contact_name="Test",
        contact_phone="0905123456",
        amenities=["wifi"],
        images=[],
        is_rented=False,
    )


def _make_extraction_result(
    message_id: str = "text_0",
    status: ExtractionStatus = ExtractionStatus.SUCCESS,
    listing: ApartmentListing | None = None,
    error: str | None = None,
) -> ExtractionResult:
    return ExtractionResult(
        raw_message_id=message_id,
        status=status,
        listing=listing or _make_listing(),
        error_message=error,
    )


class TestTestExtract:
    """Tests for POST /api/apartment-agent/test-extract."""

    ENDPOINT = "/api/apartment-agent/test-extract"

    def test_400_no_input(self):
        """Neither texts nor group_name provided."""
        resp = client.post(self.ENDPOINT, json={})
        assert resp.status_code == 400
        data = resp.json()
        assert "detail" in data

    @patch("app.modules.apartment_agent.pipeline.extract_only")
    def test_200_with_texts(self, mock_extract_only):
        """Full extraction with text input."""
        mock_extract_only.return_value = MagicMock(
            total=1,
            extracted=1,
            not_listing=0,
            failed=0,
            results=[
                MagicMock(
                    raw_message_id="text_0",
                    raw_text="Test apartment 2PN",
                    status="extracted",
                    listing=MagicMock(
                        apartment_name="Test apartment",
                        district="Hải Châu",
                        bedrooms=2,
                        price_vnd=5000000.0,
                        area_m2=50.0,
                        contact_phone="0905123456",
                        contact_zalo=None,
                        image_count=0,
                        images=[],
                        raw_text="Test apartment 2PN",
                    ),
                    error_message=None,
                )
            ],
        )
        resp = client.post(
            self.ENDPOINT,
            json={"texts": ["Test apartment 2PN Hải Châu 50m2 5tr"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["extracted"] == 1

    @patch("app.modules.apartment_agent.pipeline.extract_only")
    def test_200_with_group_name_empty(self, mock_extract_only):
        """Group name lookup returns zero messages."""
        mock_extract_only.return_value = MagicMock(
            total=0, extracted=0, not_listing=0, failed=0, results=[]
        )
        resp = client.post(
            self.ENDPOINT,
            json={"group_name": "Không tồn tại"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 0

    @patch("app.modules.apartment_agent.pipeline.extract_only")
    def test_200_with_llm_error(self, mock_extract_only):
        """LLM extraction fails for all messages — still returns JSON with failed rows."""
        mock_extract_only.return_value = MagicMock(
            total=1,
            extracted=0,
            not_listing=0,
            failed=1,
            results=[
                MagicMock(
                    raw_message_id="text_0",
                    raw_text="Bad text",
                    status="failed",
                    listing=None,
                    error_message="LLM error",
                )
            ],
        )
        resp = client.post(
            self.ENDPOINT,
            json={"texts": ["Bad text"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1
        assert data["results"][0]["status"] == "failed"

    @patch("app.modules.apartment_agent.config.settings")
    def test_400_missing_env(self, mock_settings):
        """Missing env var triggers missing_config error envelope."""
        mock_settings.godanang_supabase_url = ""
        mock_settings.godanang_supabase_service_key = ""
        mock_settings.llm_api_key = ""

        resp = client.post(self.ENDPOINT, json={"texts": ["test"]})
        assert resp.status_code == 400
        data = resp.json()
        detail = data.get("detail", {})
        assert detail.get("kind") == "missing_config"
        assert "LLM_API_KEY" in detail.get("missing", [])
