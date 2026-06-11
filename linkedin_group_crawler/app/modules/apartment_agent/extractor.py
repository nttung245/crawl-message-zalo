"""LLM-based apartment listing extraction from raw Zalo messages."""

from __future__ import annotations

import asyncio
from typing import Optional

from openai import AsyncOpenAI
from loguru import logger

from app.modules.apartment_agent.config import settings
from app.modules.apartment_agent.schemas import (
    ApartmentListing,
    ExtractionResult,
    ExtractionStatus,
)

SYSTEM_PROMPT = """You are a Vietnamese real estate data extractor. Analyze Zalo group chat messages and extract structured apartment listing data.

Rules:
- Only extract messages that are apartment FOR RENT or FOR SALE listings in Da Nang, Vietnam.
- Ignore spam, general chat, service advertisements (cleaning, moving, etc.), and non-apartment listings.
- Extract price in VND. Convert shorthand: "8tr" = 8000000, "3.2 tỷ" = 3200000000, "500k" = 500000.
- Extract area in square meters from patterns like "70m2", "70 m2", "70m²".
- Extract bedrooms from "2PN", "2 phòng ngủ", "2 phòng", "2BR".
- Da Nang districts: Hải Châu, Thanh Khê, Sơn Trà, Ngũ Hành Sơn, Liên Chiểu, Cẩm Lệ, Hòa Vang, Hoàng Sa.
- Infer district from landmarks if not explicit (e.g., "gần biển Mỹ Khê" → Ngũ Hành Sơn).
- Extract phone numbers (Vietnamese format: 0xx, +84xx).
- Extract contact name from patterns like "Liên hệ Anh Tuấn", "A Tuấn", "Chị Mai".
- Set is_apartment_listing=false if the message is NOT an apartment listing.

Rented/Occupied status detection (is_rented):
- Set is_rented=true when the message contains cues indicating the unit is already occupied/rented: "đã cho thuê", "có người ở", "đã có khách", "đã thuê", "đã có người thuê".
- Set is_rented=false when the message indicates availability: "cho thuê", "cần thuê", "còn trống", "chưa có người", "phòng trống", "cần cho thuê".
- Default to is_rented=false if the status is ambiguous or not mentioned.

Address extraction (address):
- Combine street address + floor number + room number into a canonical format: "123 Nguyễn Văn Linh, Tầng 5, Phòng 502".
- Look for patterns: street name + number ("123 Nguyễn Văn Linh"), floor ("tầng 5", "lầu 5", "T5"), room ("phòng 502", "P502", "căn 502").
- If multiple address components are found, combine them in order: street, floor, room.
- Set address to null if no specific address/room information is found in the message.

Title formatting rules (title):
- Produce a short, professional listing title in the form "<Project> <Unit>" or "<Project> <Type>".
- STRIP leading all-caps prefixes: "CHO THUÊ", "CẦN CHO THUÊ", "BÁN", "CẦN BÁN", "CHO THUÊ GẤP", "PHÒNG TRỌ", etc.
- STRIP emoji and trailing marketing fluff ("👇", "📞", "liên hệ ngay", "giá rẻ", "view đẹp", etc.).
- Use Title Case (capitalize first letter of each word). Keep Vietnamese diacritics.
- Detect the project / building name first (e.g. "Sunshine Riverside", "Monarchy", "FPT City", "The Ocean Villa", "Đà Nẵng Plaza").
- Detect the unit code in patterns: "căn 1205", "P502", "phòng 502", "tầng 5", "T5", or a bare 3+ digit number.
- If a project AND unit are both present: "Sunshine Riverside A1205", "Monarchy Bạch Đằng 2001", "FPT City 801".
- If only the project: "Sunshine Riverside" (do NOT fabricate a unit).
- If only a type/district: "Căn hộ Hải Châu" (use the most specific available).
- If nothing useful is found: leave title as the cleanest substring of the original first line.

Return ONLY valid JSON matching the schema. Do not add extra fields or explanation."""


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=60.0,
        max_retries=2,
    )


async def extract_listing(
    message_text: str,
    message_id: str = "",
    image_urls: Optional[list[str]] = None,
) -> ExtractionResult:
    """Extract structured apartment data from a single Zalo message.

    Args:
        message_text: The plain-text body of the Zalo message.
        message_id: Stable identifier used for tracing and for the LLM to reference.
        image_urls: Optional list of Supabase Storage URLs (or any image URLs) that
            the crawler already downloaded. They are appended to the user message
            as additional context so the LLM can reason about unit count, view
            cues, and decor style. They are NEVER passed to a vision model — the
            current deployment uses text-only LLMs.
    """
    user_content: str = message_text
    if image_urls:
        # Cap appended URL list length defensively in case the caller passes a huge list.
        joined = "\n".join(image_urls[:50])
        user_content = (
            f"{message_text}\n\n--- Attached image URLs ({len(image_urls)}) ---\n{joined}"
        )

    try:
        client = _get_client()
        response = await client.beta.chat.completions.parse(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ],
            response_format=ApartmentListing,
        )

        listing = response.choices[0].message.parsed
        if listing is None:
            return ExtractionResult(
                raw_message_id=message_id,
                status=ExtractionStatus.EXTRACTION_FAILED,
                error_message="LLM returned null parsed result",
            )

        if not listing.is_apartment_listing:
            return ExtractionResult(
                raw_message_id=message_id,
                status=ExtractionStatus.NOT_LISTING,
                listing=listing,
            )

        return ExtractionResult(
            raw_message_id=message_id,
            status=ExtractionStatus.SUCCESS,
            listing=listing,
        )

    except BaseException as exc:
        # Catch BaseException (not just Exception) so CancelledError and other
        # asyncio base exceptions are surfaced as EXTRACTION_FAILED with a clear
        # message, instead of bubbling up as an unhandled 500.
        if isinstance(exc, Exception):
            logger.exception(
                f"Extraction failed for message {message_id}: {exc}"
            )
        else:
            # asyncio.CancelledError and friends — re-raise after logging so
            # task cancellation still propagates correctly.
            logger.warning(
                f"Extraction interrupted for message {message_id}: "
                f"{type(exc).__name__}: {exc}"
            )
            raise
        return ExtractionResult(
            raw_message_id=message_id,
            status=ExtractionStatus.EXTRACTION_FAILED,
            error_message=str(exc) or type(exc).__name__,
        )


async def extract_batch(
    messages: list[dict],
    concurrency: Optional[int] = None,
) -> list[ExtractionResult]:
    """Process multiple messages with controlled concurrency.

    Args:
        messages: List of dicts. Each dict supports:
            - 'id': stable message identifier (required)
            - 'text': message body (required)
            - 'image_urls': optional list of Supabase Storage URLs
        concurrency: Max concurrent LLM calls. Defaults to config.
    """
    sem = asyncio.Semaphore(concurrency or settings.batch_concurrency)

    async def _process(msg: dict) -> ExtractionResult:
        async with sem:
            return await extract_listing(
                message_text=msg["text"],
                message_id=str(msg.get("id", "")),
                image_urls=msg.get("image_urls"),
            )

    results = await asyncio.gather(*[_process(m) for m in messages])
    return list(results)
