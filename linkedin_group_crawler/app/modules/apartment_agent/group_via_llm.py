"""LLM-based message grouping for apartment agent (Stage 1).

Replaces the heuristic content-type boundary walk in ``grouping.py`` with
a single LLM call per batch that understands natural message flow.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from openai import AsyncOpenAI
from loguru import logger

from app.modules.apartment_agent.config import settings
from app.modules.apartment_agent.schemas import ListingGroupBatch

STAGE_1_SYSTEM_PROMPT = """You are analyzing Zalo group chat messages about Vietnamese apartment listings in Da Nang. Your task is to group messages into logical apartment listing records.

Rules:
- Messages from the same sender within a short timeframe about the same apartment belong to ONE listing.
- Text messages followed by image-only messages (photos of the apartment) belong to the SAME listing.
- Text messages followed by follow-up text messages about the same listing (e.g. "Liên hệ 0905...") belong to the SAME listing.
- A single message describing multiple apartments should be SPLIT into multiple listing entries, each with the same source_message_ids.
- Casual chat messages ("ăn cơm chưa?", "cảm ơn", stickers) should be EXCLUDED — they don't belong to any listing.
- Detect status changes: if a message says an apartment is "bán rồi" / "đã cọc" / "đã cho thuê" / "tạm giữ" / "rút", set status_hint to "sold", "deposited", "on_hold", or "withdrawn".
- For normal active listings, set status_hint to "available" or leave null.

For each apartment listing you identify, provide:
- source_message_ids: list of original message IDs that belong to this listing
- text: merged body text from all messages (join with \\n\\n)
- image_urls: all image URLs from all messages in the listing
- status_hint: null, "available", "sold", "deposited", "on_hold", or "withdrawn"
"""


def _parse_datetime(msg: dict) -> datetime | None:
    raw = (msg.get("created_at") or "").strip()
    if raw:
        try:
            if raw.endswith("Z"):
                raw = raw[:-1] + "+00:00"
            return datetime.fromisoformat(raw).replace(tzinfo=None)
        except (ValueError, TypeError):
            pass
    raw = (msg.get("timestamp_text") or "").strip()
    if raw:
        for fmt in ("%d/%m/%Y %H:%M", "%H:%M"):
            try:
                return datetime.strptime(raw, fmt)
            except ValueError:
                pass
    return None


def split_batches(
    messages: list[dict],
    batch_window_minutes: int = 30,
    max_batch_size: int = 100,
) -> list[list[dict]]:
    """Sort messages by timestamp and partition into time-windowed batches.

    Each batch fits within *batch_window_minutes* and is capped at
    *max_batch_size* messages.  Messages without a parseable timestamp
    are attached to the last batch or placed as a singleton.
    """
    if not messages:
        return []

    sorted_msgs = sorted(
        messages,
        key=lambda m: (_parse_datetime(m) or datetime(1970, 1, 1, tzinfo=timezone.utc)).timestamp(),
    )

    batches: list[list[dict]] = []
    current: list[dict] = []
    current_start: datetime | None = None

    for msg in sorted_msgs:
        ts = _parse_datetime(msg)
        if ts is None:
            if current:
                current.append(msg)
            else:
                current = [msg]
                current_start = None
            continue

        if current_start is None:
            current_start = ts

        gap = (ts - current_start).total_seconds() / 60.0
        if gap > batch_window_minutes or len(current) >= max_batch_size:
            if current:
                batches.append(current)
            current = [msg]
            current_start = ts
        else:
            current.append(msg)

    if current:
        batches.append(current)
    return batches


def convert_group_batch_to_dicts(batch: ListingGroupBatch) -> list[dict]:
    """Convert ``ListingGroupBatch`` → ``list[dict]`` for downstream consumption.

    The output dicts match the shape expected by ``extract_batch()``:
    ``id``, ``text``, ``image_urls``, plus ``source_message_ids`` and
    ``status_hint`` for pipeline routing.
    """
    result = []
    for listing in batch.listings:
        result.append(
            {
                "id": listing.source_message_ids[0] if listing.source_message_ids else "",
                "text": listing.text,
                "image_urls": listing.image_urls,
                "source_message_ids": listing.source_message_ids,
                "status_hint": listing.status_hint,
            }
        )
    return result


def _get_client() -> AsyncOpenAI:
    return AsyncOpenAI(
        api_key=settings.llm_api_key,
        base_url=settings.llm_base_url,
        timeout=60.0,
        max_retries=2,
    )


async def llm_group_messages(
    messages: list[dict],
    model: str | None = None,
    batch_window_minutes: int = 30,
) -> list[dict]:
    """Run Stage 1 LLM grouping on a batch of Zalo messages.

    Returns a ``list[dict]`` where each dict represents one apartment listing
    with keys ``id``, ``text``, ``image_urls``, ``source_message_ids``, and
    ``status_hint``.  Returns an empty list on failure (logged).
    """
    model = model or settings.llm_model

    sorted_msgs = sorted(
        messages,
        key=lambda m: (_parse_datetime(m) or datetime(1970, 1, 1, tzinfo=timezone.utc)).timestamp(),
    )

    input_messages = [
        {
            "id": str(m.get("id", "")),
            "text": m.get("text") or "",
            "sender_name": m.get("sender_name") or "",
            "timestamp_text": m.get("timestamp_text") or "",
            "image_urls": m.get("image_urls") or [],
            "type": m.get("type") or "",
        }
        for m in sorted_msgs
    ]

    if not input_messages:
        return []

    client = _get_client()
    try:
        response = await client.beta.chat.completions.parse(
            model=model,
            messages=[
                {"role": "system", "content": STAGE_1_SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": (
                        f"Group these {len(input_messages)} Zalo messages into "
                        f"apartment listings:\n\n"
                        f"{json.dumps(input_messages, ensure_ascii=False, indent=2)}"
                    ),
                },
            ],
            response_format=ListingGroupBatch,
        )

        parsed = response.choices[0].message.parsed
        if parsed is None or not parsed.listings:
            logger.info("LLM grouping returned no listings")
            return []

        logger.info(
            f"LLM grouping: {len(input_messages)} messages → {len(parsed.listings)} listings"
        )
        for listing in parsed.listings:
            n = len(listing.source_message_ids)
            extra = f" status={listing.status_hint}" if listing.status_hint else ""
            logger.debug(
                f"  Listing: {n} msgs{extra}  text='{listing.text[:80]}...'"
            )

        return convert_group_batch_to_dicts(parsed)

    except Exception as exc:
        logger.error(f"LLM grouping failed: {exc}")
        return []


async def llm_group_messages_batched(
    messages: list[dict],
    model: str | None = None,
    batch_window_minutes: int = 30,
    max_batch_size: int = 100,
) -> list[dict]:
    """Split *messages* into batches (time window + size cap) and run
    ``llm_group_messages`` on each, then flatten the results.

    This is the primary entry point for the pipeline.
    """
    batches = split_batches(messages, batch_window_minutes, max_batch_size)
    logger.info(
        f"LLM grouping: {len(messages)} messages split into {len(batches)} batches "
        f"(window={batch_window_minutes}m, cap={max_batch_size})"
    )

    all_listings: list[dict] = []
    for i, batch in enumerate(batches):
        listings = await llm_group_messages(batch, model=model)
        all_listings.extend(listings)
        logger.debug(f"  Batch {i + 1}/{len(batches)}: {len(batch)} msgs → {len(listings)} listings")

    return all_listings
