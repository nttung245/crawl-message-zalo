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

Return ONLY valid JSON matching the schema. Do not add extra fields or explanation."""


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(api_key=settings.llm_api_key, base_url=settings.llm_base_url)


async def extract_listing(message_text: str, message_id: str = "") -> ExtractionResult:
    """Extract structured apartment data from a single Zalo message."""
    try:
        client = _get_client()
        response = await client.beta.chat.completions.parse(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message_text},
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

    except Exception as exc:
        logger.error(f"Extraction failed for message {message_id}: {exc}")
        return ExtractionResult(
            raw_message_id=message_id,
            status=ExtractionStatus.EXTRACTION_FAILED,
            error_message=str(exc),
        )


async def extract_batch(
    messages: list[dict],
    concurrency: Optional[int] = None,
) -> list[ExtractionResult]:
    """Process multiple messages with controlled concurrency.

    Args:
        messages: List of dicts with 'id' and 'text' keys.
        concurrency: Max concurrent LLM calls. Defaults to config.
    """
    sem = asyncio.Semaphore(concurrency or settings.batch_concurrency)

    async def _process(msg: dict) -> ExtractionResult:
        async with sem:
            return await extract_listing(
                message_text=msg["text"],
                message_id=str(msg.get("id", "")),
            )

    results = await asyncio.gather(*[_process(m) for m in messages])
    return list(results)
