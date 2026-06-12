## 1. Grouper module (pure function)

- [x] 1.1 Add `app/modules/apartment_agent/grouping.py` with `MessageGroup` Pydantic model and `group_messages(messages, window_minutes) -> list[MessageGroup]` signature
- [x] 1.2 Implement timestamp parsing: try `timestamp_text` (formats: "DD/MM/YYYY HH:MM", "HH:MM", "DD/MM HH:MM"), fall back to `created_at` (ISO-8601), return `None` if neither parses
- [x] 1.3 Implement sender identity normalization: `(sender_id or sender_name).strip().lower()`, returning `None` if both empty
- [x] 1.4 Implement walk: sort by parsed timestamp ASC, then for each message, decide add-to-current / close-and-start-new / skip; collect groups
- [x] 1.5 Implement `MessageGroup` construction: first id → `id`; chronological ids → `source_message_ids`; `\n\n`-joined non-empty text bodies; first-seen-order deduped image URLs; first-message sender/timestamp fields
- [x] 1.6 Implement edge cases: singleton for no-sender, singleton for no-timestamp, skip-and-close on `is_deleted=True` / `type in {sticker, system}`, `window_minutes=0` returns singletons, `window_minutes>60` is capped at 60 with a single warning
- [x] 1.7 Add a module-level `logger.info` line with `count, groups, max_group, multi_groups` for observability

## 2. Config and schema plumbing

- [x] 2.1 Add `message_group_window_minutes: int = 3` to `ApartmentAgentSettings` in `app/modules/apartment_agent/config.py`
- [x] 2.2 Add `AGENT_MESSAGE_GROUP_WINDOW_MINUTES=3` to `.env.example` with a comment
- [x] 2.3 Add `MessageGroup` model to `app/modules/apartment_agent/schemas.py` (re-export from `grouping.py` is fine)
- [x] 2.4 Add `source_message_ids: list[str] = Field(default_factory=list)` to `TestExtractListing` and `PreviewListing` in `router.py`

## 3. Pipeline integration

- [x] 3.1 In `extract_only` (`pipeline.py:22`), call `group_messages(messages, settings.message_group_window_minutes)` before `extract_batch`; pass grouped records downstream; collect `source_message_ids` into the response when the group has >1 message
- [x] 3.2 In `extract_only_streaming` (`pipeline.py:134`), same change: group before iterating; emit per-group progress events
- [x] 3.3 In `process_messages` (`pipeline.py:251`), same change: group before extraction
- [x] 3.4 In `preview_only` (`pipeline.py:367`), same change: group before extraction; populate `source_message_ids` on each `PreviewListing`
- [x] 3.5 In `router.py`, ensure the `texts=[...]` path (lines 281-285 and 392-396) still passes through to `group_messages` but with `window_minutes=0` so each text is a singleton — OR short-circuit and skip the grouper entirely. Choose the explicit skip (cleaner: no wasted call)

## 4. Frontend type and UI updates

- [x] 4.1 In `types/zalo-api.ts`, add `source_message_ids: string[]` to `AgentTestListing` and `AgentPreviewListing`
- [x] 4.2 In `ZaloAgentTestPanel.tsx`, when rendering a result/preview listing, show a small "Grouped from N messages" badge (with N=`source_message_ids.length`) when `length > 1`

## 5. Tests

- [x] 5.1 Create `tests/test_apartment_agent_grouping.py` with 33 test cases (all sync, no async needed)
- [x] 5.2 In `tests/test_apartment_agent_pipeline.py` (existing), add `test_text_plus_image_pair_yields_one_listing` that mocks `extract_listing` and asserts two input messages (text + image) produce one `TestExtractResult` with `source_message_ids` containing both ids

## 6. Verification

- [x] 6.1 Run `pytest tests/test_apartment_agent_grouping.py -v` and `pytest tests/test_apartment_agent*.py -v` — **96 passed**, 0 regressions
- [x] 6.2 Run `npm run check` from `linkedin-crawler-ui/` — no new TS errors (only pre-existing errors in unrelated files)
- [ ] 6.3 Restart backend; in the FE Agent tab, run a "Test Extract" against a real crawled group that has a text+image pair; verify the progress bar shows fewer groups than messages and the result row has the "Grouped from N" badge
- [ ] 6.4 Tail backend log; confirm the new group-size log line appears with `multi_groups > 0`
