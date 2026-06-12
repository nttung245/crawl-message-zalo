## 1. Content-type classifier and config plumbing

- [ ] 1.1 Add `_classify_content_type(msg) -> Literal["text_only", "image_only", "mixed"]` to `app/modules/apartment_agent/grouping.py`. Treats `mixed` as `text_only` for boundary decisions. Pure function, no I/O.
- [ ] 1.2 Add `message_group_max_size: int = 4` and `message_group_time_fallback_minutes: int = 1` fields to `ApartmentAgentSettings` in `app/modules/apartment_agent/config.py`. Use `pydantic_settings.AliasChoices` to read both the new env vars (`AGENT_MESSAGE_GROUP_MAX_SIZE`, `AGENT_MESSAGE_GROUP_TIME_FALLBACK_MINUTES`) and the legacy `AGENT_MESSAGE_GROUP_WINDOW_MINUTES` (alias → `time_fallback_minutes`) for one release.
- [ ] 1.3 Add a one-shot deprecation warning in `ApartmentAgentSettings.model_post_init` (or the existing settings init path) when the legacy env var is set but the new one is not. Log once per process.

## 2. Group walk rewrite

- [ ] 2.1 Refactor `group_messages(messages, window_minutes=3)` to `group_messages(messages, *, max_messages_per_group=4, time_fallback_minutes=1)`. Drop the `window_minutes` positional parameter — keyword-only. Keep `window_minutes=0` as a deprecated kwarg that maps to `time_fallback_minutes=0` for one release, with a `DeprecationWarning` if non-zero.
- [ ] 2.2 Implement the new boundary walk: for each message in sorted order, decide `(append | close-and-start | skip-and-close | singleton)` based on the boundary precedence documented in design D2. Keep the existing skip/sender-change/missing-identity rules unchanged.
- [ ] 2.3 Add the content-type pair label to the `_build_group` output: e.g. `text+3img`, `2img`, `text`, `mixed`, `image`. Store on the `MessageGroup` as a new `content_type_pair: str` field (additive, no breaking change).
- [ ] 2.4 Enrich the existing `group_messages:187` observability log to include the per-pair histogram: `pairs={"text+3img": 2, "2img": 1, "text": 0}` (or `{}` for empty input).

## 3. Pipeline integration

- [ ] 3.1 In `app/modules/apartment_agent/pipeline.py::extract_only`, replace `group_messages(messages, window_minutes)` with `group_messages(messages, max_messages_per_group=settings.message_group_max_size, time_fallback_minutes=settings.message_group_time_fallback_minutes)`.
- [ ] 3.2 Same change in `extract_only_streaming`, `process_messages`, and `preview_only`.
- [ ] 3.3 In `app/modules/apartment_agent/router.py::test_extract_endpoint`, accept an optional `window_minutes: int | None = None` in the request body (default behavior unchanged). When set, pass it as `time_fallback_minutes` to the pipeline. Same for `preview_endpoint`. Document in the OpenAPI summary.

## 4. Tests

- [ ] 4.1 Audit `tests/test_apartment_agent_grouping.py` (33 existing cases). For any case that asserted a 4+ message time-only group, add an explicit `max_messages_per_group=99` override to preserve its original intent. Document the override in a code comment.
- [ ] 4.2 Add `test_text_then_image_pair` — 1 text + 1 image from the same sender within 1 min = 1 group of 2.
- [ ] 4.3 Add `test_image_then_text_pair` — 1 image + 1 text from the same sender within 1 min = 1 group of 2.
- [ ] 4.4 Add `test_text_text_boundary` — 2 text messages, same sender, 30s apart = 2 groups.
- [ ] 4.5 Add `test_text_image_text_boundary` — text + image + text, same sender, 30s apart = 2 groups (the second text starts a new listing after the image).
- [ ] 4.6 Add `test_image_album_capped` — 5 images, same sender, within window, with `max_messages_per_group=4` = 2 groups (4 images, then 1 image).
- [ ] 4.7 Add `test_cap_does_not_split_text_image_pair` — 1 text + 3 images = 1 group of 4; 1 text + 5 images = 2 groups (1+3, then 2).
- [ ] 4.8 Add `test_time_fallback_boundary` — 1 text + 1 image, 90s apart, with `time_fallback_minutes=1` = 2 groups.
- [ ] 4.9 Add `test_content_type_pair_field` — assert the new `content_type_pair` field is `"text+3img"`, `"2img"`, `"text"`, `"image"`, `"mixed"` for the corresponding group shapes.
- [ ] 4.10 Add `test_log_includes_pairs_histogram` — capture `caplog` and assert the new `pairs={...}` substring is in the log line.
- [ ] 4.11 Add `test_legacy_window_minutes_kwarg` — `group_messages(messages, window_minutes=2)` still works and emits `DeprecationWarning`.

## 5. Config and docs

- [ ] 5.1 In `linkedin_group_crawler/.env.example`, add a new section for apartment-agent grouping with both new env vars (`AGENT_MESSAGE_GROUP_MAX_SIZE=4`, `AGENT_MESSAGE_GROUP_TIME_FALLBACK_MINUTES=1`). Mark `AGENT_MESSAGE_GROUP_WINDOW_MINUTES` as legacy with a comment pointing to the new names.
- [ ] 5.2 In the project-root `AGENTS.md` "Apartment agent timeout env" section, add a short subsection "Apartment agent grouping env" listing the three env vars (the two new + the legacy alias) with one-line summaries and the recommended dev defaults.
- [ ] 5.3 In the same file, add a bullet to the "Things you will get wrong" section: "Apartment-agent grouper default 3-min time window merges 20 same-sender messages into one listing. Set `AGENT_MESSAGE_GROUP_MAX_SIZE=4` to cap group size and rely on the content-type boundary (text-after-image starts a new group) instead."

## 6. Verification

- [ ] 6.1 Run `pytest linkedin_group_crawler/tests/test_apartment_agent_grouping.py -v` — all existing 33 + 9 new = 42 cases pass.
- [ ] 6.2 Run `pytest linkedin_group_crawler/tests/test_apartment_agent*.py -v` — no regressions in the apartment-agent module.
- [ ] 6.3 Restart backend; in the FE Agent tab, run a "Test Agent" against `Elite24 Apartment`. Confirm the new log line shows `pairs={text+Nimg: ...}` with at least 2 distinct keys, and `max_group ≤ 4`. Confirm the result rows have smaller `source_message_ids.length` than before.
- [ ] 6.4 Tail the backend log for the deprecation warning. If a deploy still has `AGENT_MESSAGE_GROUP_WINDOW_MINUTES=3` set without the new vars, the warning should fire once per process.
- [ ] 6.5 Archive the older `apartment-agent-group-messages-by-sender-time` change via `openspec archive apartment-agent-group-messages-by-sender-time` once this change ships and the user confirms the Agent tab works end-to-end.
