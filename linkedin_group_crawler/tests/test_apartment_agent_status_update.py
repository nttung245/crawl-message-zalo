"""Unit tests for listing status update logic."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.apartment_agent.schemas import ExtractionStatus, SyncStatus
from app.modules.apartment_agent.sync import update_listing_status


class TestUpdateListingStatus:
    @pytest.mark.asyncio
    async def test_successful_status_update(self):
        with patch("app.modules.apartment_agent.sync.httpx.AsyncClient") as mock_client:
            mock_resp = MagicMock()
            mock_resp.raise_for_status = MagicMock()
            mock_client.return_value.__aenter__.return_value.patch = AsyncMock(
                return_value=mock_resp
            )

            ok = await update_listing_status(villa_id=42, new_status="sold")
            assert ok is True

    @pytest.mark.asyncio
    async def test_failed_status_update(self):
        with patch("app.modules.apartment_agent.sync.httpx.AsyncClient") as mock_client:
            mock_client.return_value.__aenter__.return_value.patch = AsyncMock(
                side_effect=Exception("Connection refused")
            )

            ok = await update_listing_status(villa_id=42, new_status="sold")
            assert ok is False
