## Why

The current heuristic grouper (`grouping.py`, 412 lines) uses hardcoded content-type boundary rules (text+text=split, text+image=merge, size cap=4, time fallback=1min). It gets ~60-70% of cases right but fails on common real-world patterns: follow-up messages ("LH 0905...") split from their listing, 10-image albums cut at message 4, and it has zero understanding of message semantics. The LLM extractor already runs per group — we can give it more context and let it do the grouping too, removing 412 lines of fragile heuristic code entirely.

## What Changes

- **BREAKING**: Remove `grouping.py` entirely. The content-type boundary walk, `_classify_content_type`, `_group_type_summary`, `_content_type_pair_label`, and the `MessageGroup` pydantic model are deleted.
- **BREAKING**: Remove `ApartmentAgentSettings.message_group_max_size`, `message_group_time_fallback_minutes`, and the legacy `message_group_window_minutes` alias from `config.py`.
- **New**: LLM-based message grouping — one prompt per batch of messages that returns an array of listings, each with `source_message_ids`, `text`, `image_urls`, and `status_hint`.
- **New**: Default villa configuration (`default_config.py`) with defaults for commission (12%), amenities (`["bếp ga", "phòng tắm", "wifi"]`), and other GoDaNang villa fields.
- **Modified**: `extractor.py` — stage 2 prompt refactored to accept the output of stage 1 (structured listing objects) and produce GoDaNang villa schema directly.
- **Modified**: `pipeline.py` — replace `group_messages()` call with LLM grouping call; `preview_only`, `extract_only`, `extract_only_streaming`, `process_messages` all updated.
- **Modified**: `router.py` and schemas — request/response shapes adapt to new grouping output (no more `MessageGroup`).
- **New**: Status detection — LLM identifies listing lifecycle states (available, sold, deposited, on_hold, withdrawn) and updates existing records instead of creating new ones.

## Capabilities

### New Capabilities
- `llm-message-grouping`: LLM-based classification of raw Zalo messages into logical apartment listings, replacing heuristic grouping entirely
- `villa-default-config`: Centralized default configuration for GoDaNang villa fields (commission, amenities, listing attributes)
- `listing-status-detection`: LLM-based detection of listing lifecycle states (sold, deposited, on_hold, withdrawn) from message text

### Modified Capabilities
<!-- No existing apartment-agent specs at openspec/specs/ — these are new capabilities -->

## Impact

- **Code removed**: `grouping.py` (~412 lines), related config fields (`message_group_max_size`, `message_group_time_fallback_minutes`, legacy alias)
- **Code added**: `group_via_llm.py` (~80 lines), `default_config.py` (~40 lines)
- **Code modified**: `pipeline.py` (4 call sites), `extractor.py` (stage 2 prompt), `router.py` (schemas), `config.py` (remove grouping env vars)
- **Tests**: `test_apartment_agent_grouping.py` (~33 cases) becomes irrelevant (heuristic removed); ~11 new LLM-mocked tests needed for grouping + extraction
- **Cost**: 1 LLM call per batch (batch max ~50 messages / 30-min window) for grouping, + N concurrent calls for extraction (same as today)
- **Dependencies**: No new packages needed — same `openai` library already in use
- **Rollback**: Revert to `apartment-agent-image-text-pairing` archive if needed; old grouper code preserved in git history
