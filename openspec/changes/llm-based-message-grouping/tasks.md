## 1. Stage 1: LLM grouping

- [x] 1.1 Create `app/modules/apartment_agent/group_via_llm.py` with `llm_group_messages(messages: list[dict], model=None) -> list[ListingGroup]` function. Build the Stage 1 prompt as a system+user message. Use `client.beta.chat.completions.parse(response_format=ListingGroupBatch)` with a Pydantic model `ListingGroupBatch` containing `listings: list[ListingGroup]` where `ListingGroup` has `source_message_ids`, `text`, `image_urls`, `status_hint`. Handle empty response and parse errors gracefully.
- [x] 1.2 Add `ListingGroup` and `ListingGroupBatch` Pydantic models to `app/modules/apartment_agent/schemas.py` (or new `group_schemas.py`).
- [x] 1.3 Add batch splitting logic: sort messages by timestamp, partition on 30-minute gaps, cap each batch at 100 messages.
- [x] 1.4 Write `ListingGroupBatch` → `list[dict]` converter so existing `extract_batch` can consume the output without changes.

## 2. Default villa config

- [x] 2.1 Create `app/modules/apartment_agent/default_config.py` with `DEFAULT_VILLA` dict containing: `commission_percent: 12`, `amenities: ["bếp ga", "phòng tắm riêng", "wifi", "máy lạnh"]`, `type: "apartment"`, `listing_status: "available"`.
- [x] 2.2 Add `merge_with_defaults(listing: dict) -> dict` utility in `default_config.py` — LLM output merged with defaults, LLM wins on conflicts.
- [x] 2.3 Wire `merge_with_defaults()` into `extractor.py` stage 2 flow and into `sync.py` `_build_insert_payload`.

## 3. Stage 2: Extraction update

- [x] 3.1 Update `extractor.py` `SYSTEM_PROMPT` (Stage 2): change context from "raw Zalo message" to "pre-grouped listing text with image URLs". The prompt now receives a single listing object (not a confusing multi-message blob). Add instruction to use provided fields and leave unknown fields as `null` so defaults can fill them.
- [x] 3.2 Ensure `extract_listing()` accepts both old dict format and new `ListingGroup`-derived format for backward compatibility during rollout.

## 4. Pipeline integration

- [x] 4.1 Replace `group_messages()` call in `extract_only` (pipeline.py) with `llm_group_messages()` call. Handle the case where `window_minutes` was passed — translate to batch window param.
- [x] 4.2 Same replacement in `extract_only_streaming`, `process_messages`, `preview_only`.
- [x] 4.3 Add feature flag check in pipeline: `if settings.llm_grouping_enabled: llm_group_messages(...) else: group_messages(...)`. Default `True` in config.
- [x] 4.4 Update `pipeline.py` to handle status_hint — when not null/available, call GoDaNang lookup + status update instead of insert.

## 5. Status update logic

- [x] 5.1 Add `find_existing_by_title_or_district_area(status_hint_record) -> dict | None` in `sync.py` — fuzzy match against GoDaNang villas table on title similarity or district+area proximity. (Reused existing `find_existing_villa` for this purpose.)
- [x] 5.2 Add `update_listing_status(villa_id, new_status) -> bool` in `sync.py` — PATCH the GoDaNang record's `listing_status` field.
- [x] 5.3 Wire status update path into `pipeline.py::process_messages`: when `status_hint` is not null/available, skip extraction (no stage 2 needed), call find → update. Log `status_update_confirmed: True/False`.

## 6. Cleanup

- [ ] 6.1 Remove `grouping.py` from `app/modules/apartment_agent/`.
- [ ] 6.2 Remove `message_group_max_size`, `message_group_time_fallback_minutes`, and `message_group_window_minutes` fields from `config.py`.
- [ ] 6.3 Remove `MessageGroup` model usage from `router.py`, `pipeline.py`, and `schemas.py`. Any response field referencing `MessageGroup` is removed or changed to `ListingGroup`.
- [ ] 6.4 Remove `MessageGroup`, `_classify_content_type`, `_content_type_pair_label`, `_group_type_summary`, `_content_type_pair_label_from_group` imports across the codebase.
- [ ] 6.5 Update `router.py` request/response schemas: `TestExtractRequest` and `PreviewRequest` no longer accept `window_minutes`; response `TestExtractListing` drops `source_message_ids` field (replaced by `ListingGroup.source_message_ids` in grouping step).

## 7. Tests

- [ ] 7.1 Remove `tests/test_apartment_agent_grouping.py` (33 cases — heuristic grouper no longer exists).
- [ ] 7.2 Add `tests/test_apartment_agent_llm_grouping.py` with mocked OpenAI responses: test text+phone merge, text+image merge, multi-listing split, non-listing exclusion, status detection, empty batch, batch split at 100 messages.
- [ ] 7.3 Add `tests/test_apartment_agent_default_config.py`: test merge LLM overrides default, default fills missing, DEFAULT_VILLA is importable.
- [ ] 7.4 Add `tests/test_apartment_agent_status_update.py`: test status update finds existing, status update not found, normal listing unaffected.
- [ ] 7.5 Update existing pipeline tests (`test_apartment_agent_pipeline.py`) for new call signatures (no `window_minutes`, LLM-mocked grouping).
- [ ] 7.6 Run `pytest tests/test_apartment_agent*.py -v` — all tests pass.

## 8. Verification

- [ ] 8.1 Restart backend; in FE Agent tab, run test against `Elite24 Apartment`. Confirm grouping log shows LLM-based grouping (not heuristic pairs histogram). Confirm groups correctly merge text+follow-up and text+image.
- [ ] 8.2 Post a status-change message ("căn X bán rồi") and confirm the GoDaNang record is updated, not duplicated.
- [ ] 8.3 Verify default config fields (commission, amenities) appear in upserted villa records.
