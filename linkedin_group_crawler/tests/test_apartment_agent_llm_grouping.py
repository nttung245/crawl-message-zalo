"""Unit tests for LLM-based message grouping (Stage 1)."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.modules.apartment_agent.group_via_llm import (
    _parse_datetime,
    convert_group_batch_to_dicts,
    llm_group_messages,
    llm_group_messages_batched,
    split_batches,
)
from app.modules.apartment_agent.schemas import ListingGroup, ListingGroupBatch


def _msg(
    id_: str = "m1",
    text: str = "Sunshine Riverside 2PN 8tr",
    sender_id: str | None = "uid_1",
    sender_name: str | None = "Anh Tuấn",
    timestamp_text: str | None = None,
    created_at: str | None = None,
    type_: str = "text",
    image_urls: list[str] | None = None,
) -> dict:
    now = datetime.now()
    ts = timestamp_text or now.strftime("%d/%m/%Y %H:%M")
    ca = created_at if created_at is not None else ("" if timestamp_text else now.isoformat())
    return {
        "id": id_,
        "text": text,
        "sender_id": sender_id,
        "sender_name": sender_name,
        "timestamp_text": ts,
        "created_at": ca,
        "type": type_,
        "is_deleted": False,
        "image_urls": image_urls or [],
    }


def _ts_after(minutes: float) -> str:
    dt = datetime.now() + timedelta(minutes=minutes)
    return dt.strftime("%d/%m/%Y %H:%M")


# ── _parse_datetime ──────────────────────────────────────────────


class TestParseDatetime:
    def test_iso_created_at(self):
        dt = _parse_datetime({"created_at": "2026-06-12T14:35:00+00:00"})
        assert dt is not None
        assert dt.hour == 14 and dt.minute == 35

    def test_iso_with_z(self):
        dt = _parse_datetime({"created_at": "2026-06-12T14:35:00Z"})
        assert dt is not None
        assert dt.hour == 14 and dt.minute == 35

    def test_timestamp_text_full(self):
        dt = _parse_datetime({"timestamp_text": "12/06/2026 14:35"})
        assert dt is not None
        assert dt.hour == 14 and dt.minute == 35

    def test_timestamp_text_time_only(self):
        dt = _parse_datetime({"timestamp_text": "14:35"})
        assert dt is not None
        assert dt.hour == 14 and dt.minute == 35

    def test_empty_returns_none(self):
        assert _parse_datetime({}) is None
        assert _parse_datetime({"timestamp_text": ""}) is None


# ── split_batches ────────────────────────────────────────────────


class TestSplitBatches:
    def test_empty_input(self):
        assert split_batches([], batch_window_minutes=30) == []

    def test_single_message(self):
        m = _msg("m1")
        batches = split_batches([m], batch_window_minutes=30, max_batch_size=100)
        assert len(batches) == 1
        assert len(batches[0]) == 1

    def test_splits_on_time_gap(self):
        a = _msg("m1", timestamp_text=_ts_after(0))
        b = _msg("m2", timestamp_text=_ts_after(45))
        batches = split_batches([a, b], batch_window_minutes=30, max_batch_size=100)
        assert len(batches) == 2

    def test_keeps_within_window(self):
        a = _msg("m1", timestamp_text=_ts_after(0))
        b = _msg("m2", timestamp_text=_ts_after(15))
        batches = split_batches([a, b], batch_window_minutes=30, max_batch_size=100)
        assert len(batches) == 1

    def test_splits_on_size_cap(self):
        msgs = [_msg(f"m{i}", timestamp_text=_ts_after(i * 0.1)) for i in range(10)]
        batches = split_batches(msgs, batch_window_minutes=30, max_batch_size=3)
        assert len(batches) == 4  # 10 messages / 3 = 4 batches
        assert all(len(b) <= 3 for b in batches)


# ── convert_group_batch_to_dicts ─────────────────────────────────


class TestConvertGroupBatch:
    def test_basic_conversion(self):
        batch = ListingGroupBatch(
            listings=[
                ListingGroup(
                    source_message_ids=["m1", "m2"],
                    text="Listing text",
                    image_urls=["https://img.jpg"],
                    status_hint="available",
                ),
            ]
        )
        result = convert_group_batch_to_dicts(batch)
        assert len(result) == 1
        assert result[0]["id"] == "m1"
        assert result[0]["text"] == "Listing text"
        assert result[0]["image_urls"] == ["https://img.jpg"]
        assert result[0]["status_hint"] == "available"
        assert result[0]["source_message_ids"] == ["m1", "m2"]

    def test_empty_batch(self):
        batch = ListingGroupBatch(listings=[])
        assert convert_group_batch_to_dicts(batch) == []


# ── llm_group_messages (mocked) ──────────────────────────────────


class TestLlmGroupMessages:
    @pytest.mark.asyncio
    async def test_text_plus_follow_up_merged(self):
        messages = [
            _msg("m1", text="Cho thuê căn hộ Sunshine 2PN 8tr"),
            _msg("m2", text="Liên hệ 0905123456", timestamp_text=_ts_after(2)),
        ]
        expected_batch = ListingGroupBatch(
            listings=[
                ListingGroup(
                    source_message_ids=["m1", "m2"],
                    text="Cho thuê căn hộ Sunshine 2PN 8tr\n\nLiên hệ 0905123456",
                    image_urls=[],
                    status_hint="available",
                ),
            ]
        )
        with patch(
            "app.modules.apartment_agent.group_via_llm._get_client"
        ) as mock_client:
            mock_parsed = MagicMock()
            mock_parsed.parsed = expected_batch
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=mock_parsed)]
            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                return_value=mock_response
            )

            result = await llm_group_messages(messages)
            assert len(result) == 1
            assert result[0]["source_message_ids"] == ["m1", "m2"]

    @pytest.mark.asyncio
    async def test_empty_response_returns_empty_list(self):
        batch = ListingGroupBatch(listings=[])
        with patch(
            "app.modules.apartment_agent.group_via_llm._get_client"
        ) as mock_client:
            mock_parsed = MagicMock()
            mock_parsed.parsed = batch
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=mock_parsed)]
            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                return_value=mock_response
            )

            result = await llm_group_messages([])
            assert result == []

    @pytest.mark.asyncio
    async def test_llm_error_returns_empty_list(self):
        with patch(
            "app.modules.apartment_agent.group_via_llm._get_client"
        ) as mock_client:
            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                side_effect=Exception("API error")
            )

            result = await llm_group_messages([_msg("m1")])
            assert result == []

    @pytest.mark.asyncio
    async def test_status_detection(self):
        messages = [
            _msg("m1", text="căn trên bán rồi nhé"),
        ]
        expected_batch = ListingGroupBatch(
            listings=[
                ListingGroup(
                    source_message_ids=["m1"],
                    text="căn trên bán rồi nhé",
                    image_urls=[],
                    status_hint="sold",
                ),
            ]
        )
        with patch(
            "app.modules.apartment_agent.group_via_llm._get_client"
        ) as mock_client:
            mock_parsed = MagicMock()
            mock_parsed.parsed = expected_batch
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=mock_parsed)]
            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                return_value=mock_response
            )

            result = await llm_group_messages(messages)
            assert len(result) == 1
            assert result[0]["status_hint"] == "sold"


class TestLlmGroupMessagesBatched:
    @pytest.mark.asyncio
    async def test_single_batch(self):
        messages = [_msg("m1"), _msg("m2", timestamp_text=_ts_after(5))]
        expected_batch = ListingGroupBatch(
            listings=[
                ListingGroup(
                    source_message_ids=["m1", "m2"],
                    text="Two messages",
                    image_urls=[],
                    status_hint=None,
                ),
            ]
        )
        with patch(
            "app.modules.apartment_agent.group_via_llm._get_client"
        ) as mock_client:
            mock_parsed = MagicMock()
            mock_parsed.parsed = expected_batch
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=mock_parsed)]
            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                return_value=mock_response
            )

            result = await llm_group_messages_batched(
                messages, batch_window_minutes=30, max_batch_size=100
            )
            assert len(result) == 1
            assert result[0]["source_message_ids"] == ["m1", "m2"]
