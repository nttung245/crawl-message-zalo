"""Unit tests for the apartment agent image + title flow.

Covers:
- `image_filter.filter_image_urls` — drop blanks, drop non-image
  extensions, dedupe, cap at 200.
- `image_filter.extract_image_urls_from_assets` — accept PostgREST
  join shapes (None, list, dict), prefer storage_url, fall back to
  source_url, filter by status.
- `extract_listing` accepts `image_urls` and threads them into the
  user message.
- The system prompt contains the new title rules.
- `_build_update_payload` keeps `images` only when the listing has
  any (so manual GoDaNang edits are not blanked out).
"""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.modules.apartment_agent.config import settings as _aa_settings
from app.modules.apartment_agent.extractor import (
    SYSTEM_PROMPT,
    _get_client,
    extract_listing,
)
from app.modules.apartment_agent.image_filter import (
    MAX_IMAGE_URLS_PER_MESSAGE,
    extract_image_urls_from_assets,
    filter_image_urls,
)
from app.modules.apartment_agent.schemas import (
    ApartmentListing,
    ExtractionResult,
    ExtractionStatus,
    ListingType,
)
from app.modules.apartment_agent.sync import (
    _build_insert_payload,
    _build_update_payload,
)


# ── image_filter.filter_image_urls ─────────────────────────────────────


class TestFilterImageUrls:
    def test_drops_blanks(self):
        assert filter_image_urls(["", None, "https://x.test/a.png"]) == [
            "https://x.test/a.png"
        ]

    def test_drops_non_http(self):
        urls = [
            "ftp://x.test/a.png",
            "javascript:alert(1)",
            "//cdn.x/a.png",  # protocol-relative
            "/local/path.png",
        ]
        assert filter_image_urls(urls) == []

    def test_drops_known_non_image_extensions(self):
        urls = [
            "https://x.test/clip.mp4",
            "https://x.test/clip.MOV",
            "https://x.test/file.pdf",
        ]
        assert filter_image_urls(urls) == []

    def test_keeps_image_extensions(self):
        urls = [
            "https://x.test/a.jpg",
            "https://x.test/b.JPEG",
            "https://x.test/c.png",
            "https://x.test/d.webp",
        ]
        assert filter_image_urls(urls) == urls

    def test_keeps_extensionless_storage_urls(self):
        # Supabase signed URLs often have no extension — keep them.
        url = "https://abc.supabase.co/storage/v1/object/sign/zalo-assets/foo?token=xyz"
        assert filter_image_urls([url]) == [url]

    def test_dedupes_preserving_order(self):
        urls = [
            "https://x.test/a.png",
            "https://x.test/b.png",
            "https://x.test/a.png",
            "https://x.test/c.png",
            "https://x.test/b.png",
        ]
        assert filter_image_urls(urls) == [
            "https://x.test/a.png",
            "https://x.test/b.png",
            "https://x.test/c.png",
        ]

    def test_caps_at_max(self):
        # MAX is 200; with 250 inputs we expect exactly 200, in order.
        urls = [f"https://x.test/img_{i:03d}.png" for i in range(250)]
        out = filter_image_urls(urls)
        assert len(out) == MAX_IMAGE_URLS_PER_MESSAGE
        assert out[0] == "https://x.test/img_000.png"
        assert out[-1] == f"https://x.test/img_{MAX_IMAGE_URLS_PER_MESSAGE - 1:03d}.png"

    def test_handles_iterable_not_list(self):
        # Generators should be acceptable.
        gen = (u for u in ["https://x.test/a.png", "https://x.test/b.png"])
        assert filter_image_urls(gen) == [
            "https://x.test/a.png",
            "https://x.test/b.png",
        ]


# ── image_filter.extract_image_urls_from_assets ────────────────────────


def _asset(
    storage_url: str | None = None,
    source_url: str | None = None,
    status: str = "uploaded",
) -> dict:
    return {
        "storage_url": storage_url,
        "source_url": source_url,
        "status": status,
    }


class TestExtractImageUrlsFromAssets:
    def test_none_returns_empty(self):
        assert extract_image_urls_from_assets(None) == []

    def test_empty_list_returns_empty(self):
        assert extract_image_urls_from_assets([]) == []

    def test_prefers_storage_over_source(self):
        assets = [
            _asset(
                storage_url="https://cdn/a.png",
                source_url="https://origin/a.png",
            )
        ]
        assert extract_image_urls_from_assets(assets) == ["https://cdn/a.png"]

    def test_falls_back_to_source_when_no_storage(self):
        assets = [
            _asset(storage_url=None, source_url="https://origin/b.png"),
        ]
        assert extract_image_urls_from_assets(assets) == ["https://origin/b.png"]

    def test_drops_pending_and_failed_assets(self):
        assets = [
            _asset(storage_url="https://cdn/ok.png", status="uploaded"),
            _asset(storage_url="https://cdn/pending.png", status="pending"),
            _asset(storage_url="https://cdn/failed.png", status="failed"),
        ]
        assert extract_image_urls_from_assets(assets) == ["https://cdn/ok.png"]

    def test_handles_single_dict(self):
        # Some PostgREST joins return a single dict, not a list, for
        # 0..1 relationships. Accept it.
        out = extract_image_urls_from_assets(
            _asset(storage_url="https://cdn/single.png")
        )
        assert out == ["https://cdn/single.png"]

    def test_drops_non_image_extensions(self):
        assets = [
            _asset(storage_url="https://cdn/img.png"),
            _asset(storage_url="https://cdn/clip.mp4"),
        ]
        assert extract_image_urls_from_assets(assets) == ["https://cdn/img.png"]

    def test_mixed_real_world_shape(self):
        assets = [
            _asset(
                storage_url="https://abc.supabase.co/storage/v1/object/public/zalo-assets/u1/j1/msg1-1.png",
                status="uploaded",
            ),
            _asset(
                storage_url="https://abc.supabase.co/storage/v1/object/public/zalo-assets/u1/j1/msg1-2.png",
                status="uploaded",
            ),
            _asset(
                storage_url="https://abc.supabase.co/storage/v1/object/public/zalo-assets/u1/j1/msg1-3.png",
                status="uploaded",
            ),
        ]
        out = extract_image_urls_from_assets(assets)
        assert len(out) == 3
        for url in out:
            assert url.startswith("https://abc.supabase.co/")


# ── extract_listing accepts image_urls ────────────────────────────────


@pytest.fixture
def sample_message_with_images():
    return {
        "id": "msg_001",
        "text": "CHO THUÊ CĂN HỘ SUNSHINE RIVERSIDE căn 1205, 12tr/tháng",
        "image_urls": [
            "https://cdn/a.png",
            "https://cdn/b.png",
        ],
    }


@pytest.fixture
def expected_title_listing():
    return ApartmentListing(
        is_apartment_listing=True,
        title="Sunshine Riverside 1205",
        price=12000000.0,
        area_sqm=72.0,
        bedrooms=2,
        district="Hải Châu",
        listing_type=ListingType.RENT,
    )


class TestExtractListingWithImages:
    @pytest.mark.asyncio
    async def test_image_urls_threaded_into_user_message(
        self, sample_message_with_images, expected_title_listing
    ):
        captured: dict = {}

        async def fake_parse(*args, **kwargs):
            # Capture the messages arg.
            captured["messages"] = kwargs.get("messages") or args[1] if len(args) > 1 else kwargs.get("messages")
            mock_parsed = MagicMock()
            mock_parsed.parsed = expected_title_listing
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=mock_parsed)]
            return mock_response

        with patch("app.modules.apartment_agent.extractor._get_client") as mock_client:
            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                side_effect=fake_parse
            )

            result = await extract_listing(
                message_text=sample_message_with_images["text"],
                message_id=sample_message_with_images["id"],
                image_urls=sample_message_with_images["image_urls"],
            )

        assert result.status == ExtractionStatus.SUCCESS
        assert result.listing is not None
        assert result.listing.title == "Sunshine Riverside 1205"

        # Verify the URLs landed in the user message.
        user_message = captured["messages"][1]["content"]
        assert "https://cdn/a.png" in user_message
        assert "https://cdn/b.png" in user_message
        assert sample_message_with_images["text"] in user_message

    @pytest.mark.asyncio
    async def test_no_image_urls_keeps_plain_message(
        self, expected_title_listing
    ):
        captured: dict = {}

        async def fake_parse(*args, **kwargs):
            captured["messages"] = kwargs.get("messages") or (
                args[1] if len(args) > 1 else kwargs.get("messages")
            )
            mock_parsed = MagicMock()
            mock_parsed.parsed = expected_title_listing
            mock_response = MagicMock()
            mock_response.choices = [MagicMock(message=mock_parsed)]
            return mock_response

        with patch("app.modules.apartment_agent.extractor._get_client") as mock_client:
            mock_client.return_value.beta.chat.completions.parse = AsyncMock(
                side_effect=fake_parse
            )

            await extract_listing(
                message_text="CHO THUÊ CĂN HỘ SUNSHINE RIVERSIDE căn 1205",
                message_id="msg_002",
                image_urls=None,
            )

        user_message = captured["messages"][1]["content"]
        assert "Attached image URLs" not in user_message

    @pytest.mark.asyncio
    async def test_openai_client_has_timeout(self):
        """The client must be constructed with a finite timeout so a
        hung LLM provider does not leak as a 500."""
        with patch.object(_aa_settings, "llm_api_key", "sk-test-dummy"):
            client = _get_client()
        # The AsyncOpenAI client stores timeout on .timeout in seconds
        # for v1.x. We accept either float or httpx.Timeout.
        timeout = client.timeout
        # httpx.Timeout has connect/read/write/pool — accept any of
        # these being non-None.
        if hasattr(timeout, "connect"):
            assert timeout.connect is not None
        else:
            assert timeout is not None and timeout > 0


# ── system prompt has the new title rules ─────────────────────────────


class TestSystemPrompt:
    def test_title_rules_present(self):
        # The prompt must mention the new title rules so the LLM is
        # nudged toward producing a clean '<Project> <Unit>' name.
        assert "Title formatting rules" in SYSTEM_PROMPT
        assert "STRIP leading all-caps prefixes" in SYSTEM_PROMPT
        assert "Sunshine Riverside" in SYSTEM_PROMPT  # example project
        assert "1205" in SYSTEM_PROMPT  # example unit

    def test_existing_address_rules_preserved(self):
        # We must not have regressed the address extraction rules.
        assert "Address extraction" in SYSTEM_PROMPT
        assert "T\u1ea7ng" in SYSTEM_PROMPT or "t\u1ea7ng" in SYSTEM_PROMPT


# ── _build_update_payload image policy ────────────────────────────────


def _sample_listing(**overrides) -> ApartmentListing:
    base = dict(
        is_apartment_listing=True,
        title="Sunshine Riverside 1205",
        price=12000000.0,
        area_sqm=72.0,
        bedrooms=2,
        district="Hải Châu",
        listing_type=ListingType.RENT,
    )
    base.update(overrides)
    return ApartmentListing(**base)


class TestUpdatePayloadImages:
    def test_update_strips_images_when_listing_has_none(self):
        listing = _sample_listing(images=[])
        payload = _build_update_payload(listing)
        assert "images" not in payload

    def test_update_keeps_images_when_listing_has_some(self):
        listing = _sample_listing(
            images=["https://cdn/a.png", "https://cdn/b.png"]
        )
        payload = _build_update_payload(listing)
        assert payload["images"] == [
            "https://cdn/a.png",
            "https://cdn/b.png",
        ]

    def test_insert_always_keeps_images(self):
        listing = _sample_listing(images=[])
        payload = _build_insert_payload(listing)
        # Insert path may set []; the column still goes in the body.
        assert "images" in payload
        assert payload["images"] == []


# ── extract_batch threads image_urls through ──────────────────────────


class TestExtractBatchImageUrls:
    @pytest.mark.asyncio
    async def test_batch_threads_image_urls_per_message(self):
        # Minimal mock: extract_listing is patched so we only verify
        # that extract_batch forwards each message's image_urls.
        captured: list[dict] = []

        async def fake_extract(
            message_text: str,
            message_id: str = "",
            image_urls=None,
        ):
            captured.append(
                {"id": message_id, "text": message_text, "image_urls": image_urls}
            )
            return ExtractionResult(
                raw_message_id=message_id,
                status=ExtractionStatus.NOT_LISTING,
                listing=ApartmentListing(is_apartment_listing=False),
            )

        with patch(
            "app.modules.apartment_agent.extractor.extract_listing",
            AsyncMock(side_effect=fake_extract),
        ):
            from app.modules.apartment_agent.extractor import extract_batch

            messages = [
                {
                    "id": "m1",
                    "text": "msg 1",
                    "image_urls": ["https://cdn/1.png"],
                },
                {"id": "m2", "text": "msg 2"},  # no image_urls key
                {
                    "id": "m3",
                    "text": "msg 3",
                    "image_urls": ["https://cdn/3a.png", "https://cdn/3b.png"],
                },
            ]
            results = await extract_batch(messages, concurrency=2)

        assert len(captured) == 3
        assert captured[0]["image_urls"] == ["https://cdn/1.png"]
        assert captured[1]["image_urls"] is None
        assert captured[2]["image_urls"] == [
            "https://cdn/3a.png",
            "https://cdn/3b.png",
        ]
        assert len(results) == 3
