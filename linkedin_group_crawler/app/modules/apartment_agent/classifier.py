"""Classifier step: determine if a Zalo message is an apartment listing."""

from __future__ import annotations

from loguru import logger

from app.modules.apartment_agent.config import settings
from app.modules.apartment_agent.schemas import ClassificationResult

CLASSIFIER_SYSTEM_PROMPT = (
    "You are a classifier that determines whether a message is an apartment or room "
    "listing for rent or sale in Da Nang, Vietnam.\n\n"
    "Return ONLY valid JSON matching this schema:\n"
    '{\n  "is_listing": bool,\n  "reason": string,\n  "confidence": float (0.0-1.0)\n}\n\n'
    "A listing MUST mention at least one of: price, area, bedrooms, district, contact info. "
    "Generic chat, greetings, questions about the area, stickers, or reactions are NOT listings."
)


async def is_apartment_listing(message_text: str, message_id: str = "") -> ClassificationResult:
    """Classify whether a message is an apartment listing.

    Uses the same OpenAI-compatible client as extractor.py, with temperature=0
    and a small prompt. When APARTMENT_AGENT_CLASSIFIER_ENABLED is false (default),
    returns is_listing=True with reason="classifier_disabled" to preserve existing behavior.
    """
    if not settings.classifier_enabled:
        return ClassificationResult(
            is_listing=True,
            reason="classifier_disabled",
            confidence=1.0,
        )

    try:
        from app.modules.apartment_agent.extractor import _get_client

        client = _get_client()
        response = await client.chat.completions.create(
            model=settings.llm_model,
            messages=[
                {"role": "system", "content": CLASSIFIER_SYSTEM_PROMPT},
                {"role": "user", "content": message_text},
            ],
            temperature=0,
            max_tokens=150,
        )

        raw = response.choices[0].message.content or ""
        import json

        data = json.loads(raw.strip())
        return ClassificationResult(
            is_listing=bool(data.get("is_listing", False)),
            reason=str(data.get("reason", "")),
            confidence=float(data.get("confidence", 0.0)),
        )
    except Exception as exc:
        logger.error("Classifier failed for message {}: {}", message_id, exc)
        return ClassificationResult(
            is_listing=False,
            reason=f"classifier_error: {exc}",
            confidence=0.0,
        )


async def classify_batch(
    messages: list[dict],
    concurrency: int | None = None,
) -> list[ClassificationResult]:
    """Classify multiple messages with controlled concurrency."""
    import asyncio

    sem = asyncio.Semaphore(concurrency or settings.batch_concurrency)

    async def _classify(msg: dict) -> ClassificationResult:
        async with sem:
            return await is_apartment_listing(
                message_text=msg["text"],
                message_id=str(msg.get("id", "")),
            )

    results = await asyncio.gather(*[_classify(m) for m in messages])
    return list(results)
