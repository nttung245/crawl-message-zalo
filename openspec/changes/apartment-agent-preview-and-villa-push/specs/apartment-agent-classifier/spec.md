# apartment-agent-classifier Specification

## Purpose
Defines the text-classifier step that runs before LLM extraction so that
non-listing messages (casual chat, stickers, reactions, off-topic) never
consume the schema-parse budget and never reach the Agent preview or
the GoDaNang push.

## Requirements

### Requirement: Classifier function exists and is callable
The system SHALL provide `app/modules/apartment_agent/classifier.py::is_apartment_listing(message_text: str) -> ClassificationResult`. The function MUST use the same OpenAI-compatible LLM client as `extractor.py` and MUST run under the same `asyncio.Semaphore(settings.batch_concurrency)` gate.

#### Scenario: Classifier classifies an obvious listing
- **WHEN** `is_apartment_listing("Căn hộ 2PN full nội thất, 65m2, Sơn Trà, 8tr/tháng, liên hệ 0905.xxx")` is called
- **THEN** it returns `ClassificationResult(is_listing=True, confidence>=0.8, reason="mentions area, price, contact")`

#### Scenario: Classifier rejects a sticker/greeting
- **WHEN** `is_apartment_listing("[sticker] Chúc mọi người buổi tối vui vẻ")` is called
- **THEN** it returns `ClassificationResult(is_listing=False, confidence>=0.95, reason="non-listing chat")`

#### Scenario: Classifier LLM call fails
- **WHEN** the underlying LLM call raises (auth error, rate limit, network)
- **THEN** the function returns `ClassificationResult(is_listing=False, confidence=0, reason="classifier_error: <message>")` and logs the full error at ERROR level

### Requirement: Classifier result is preserved in pipeline
The pipeline function `extract_only` and the new `preview_only` MUST each return a `classifications` array of `ClassificationResult` in lockstep with the `extractions` array, so the FE can show "rejected by classifier" badges alongside extraction results.

#### Scenario: Mixed batch with 5 listings and 3 chats
- **WHEN** `preview_only` is called with 8 messages
- **THEN** the response has `classifications.length == 8` and `listings.length == 5` and the 3 rejected messages have a `classifications[i].is_listing=False` entry

### Requirement: Classifier prompt is small and stable
The classifier system prompt MUST be ≤ 200 tokens and MUST NOT be temperature-1 (use `temperature=0`). The prompt MUST instruct the model to return ONLY the JSON schema fields, no explanation.

#### Scenario: Prompt size guard
- **WHEN** `extract_listing` is instrumented with a token counter
- **THEN** the classifier prompt contributes ≤ 200 input tokens

### Requirement: Classifier is opt-in via env flag
The system SHALL gate the classifier behind `APARTMENT_AGENT_CLASSIFIER_ENABLED=true`. When the flag is `false` (default during rollout), `is_apartment_listing` returns `ClassificationResult(is_listing=True, confidence=1.0, reason="classifier_disabled")` so existing behavior is preserved.

#### Scenario: Default deployment with flag unset
- **WHEN** `APARTMENT_AGENT_CLASSIFIER_ENABLED` is not in `.env`
- **THEN** every classification returns `is_listing=True` and the pipeline runs as it does today

#### Scenario: Opt-in deployment
- **WHEN** `APARTMENT_AGENT_CLASSIFIER_ENABLED=true` is set
- **THEN** the classifier actually runs and may reject messages
