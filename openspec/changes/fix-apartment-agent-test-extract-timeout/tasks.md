## 1. Setup and verification

- [ ] 1.1 Verify the failure is reproducible on the running dev stack. Hit `POST http://127.0.0.1:8000/api/apartment-agent/test-extract` directly with `{"group_name":"Elite24 Apartment"}` and confirm a 200 JSON response. Then hit `http://127.0.0.1:3000/minhhoang-scraper/api/apartment-agent/test-extract` and capture the `Internal Server Error` + `Failed to proxy ... ECONNRESET` lines. Paste both transcripts into `openspec/changes/fix-apartment-agent-test-extract-timeout/probe.md` so the next agent has a baseline.
- [ ] 1.2 Add `APARTMENT_AGENT_TEST_EXTRACT_LIMIT`, `APARTMENT_AGENT_TEST_EXTRACT_TIMEOUT_S`, and `APARTMENT_AGENT_PREVIEW_TIMEOUT_S` to `linkedin_group_crawler/.env.example` (with safe defaults: test-extract limit 20, timeouts 25/120). Also document `NEXT_PUBLIC_ZALO_API_BASE_URL` in `linkedin-crawler-ui/.env.example` (none exists yet — create it) as the recommended way to bypass the Next.js dev-proxy 30 s timeout.
- [ ] 1.3 No new Python or npm deps for this change. The image filter is a string-only operation; vision is explicitly out of scope per the user's clarification.

## 2. Subunit 1: Pipeline timeout + progress block (one commit)

Spec: `apartment-agent-pipeline-timeout`.

- [ ] 2.1 In `app/modules/apartment_agent/config.py`, add the new settings fields to the `Settings` class: `test_extract_limit: int = 20`, `test_extract_timeout_s: float = 25.0`, `preview_timeout_s: float = 120.0`. Wire them to the new env vars via `Field(default=..., alias=...)` (or the project's existing `AliasChoices` pattern — see the `ZALO_*` keys). Do NOT add `vision_*` fields — the user explicitly does not want vision.
- [ ] 2.2 In `app/modules/apartment_agent/router.py`, update `test_extract_endpoint` to: accept an optional `limit: int = None` in `TestExtractRequest`; resolve the effective limit via `limit or settings.test_extract_limit`; pass that to the Supabase `_rest` call; run `extract_only(messages, concurrency=10)` wrapped in `asyncio.wait_for(..., timeout=settings.test_extract_timeout_s)`; on `TimeoutError`, synthesize a `TestExtractResult(status="failed", error_message="timed out")` row for every message that does not yet have a terminal status and return the partial response.
- [ ] 2.3 Add a `ProgressBlock` Pydantic model to `schemas.py` with `total: int = 0, processed: int = 0, in_flight: int = 0, timed_out: int = 0, truncated: bool = False`. Embed it in both `TestExtractResponse` and `PreviewResponse` as `progress: ProgressBlock = Field(default_factory=ProgressBlock)`. Set `progress.total = len(messages)`, `progress.truncated = (limit < full_table_count)`, `progress.timed_out = timed_out_count` in the endpoints.
- [ ] 2.4 In `preview_endpoint`, do the same `wait_for` wrap with `settings.preview_timeout_s`. The preview's `progress.timed_out` MUST equal the number of listings that were going to be added to `result.listings` but were cancelled.
- [ ] 2.5 In `services/zaloCrawlerService.ts`, extend the `testAgentExtract` and `previewAgentExtract` request types to include an optional `limit: number` (no-op when omitted). Leave the `120000` / `300000` ms timeouts as-is for now (the BE budget is the new gate).
- [ ] 2.6 Commit: `feat(apartment-agent): pipeline timeout + progress block`. Verify by `curl -H "x-api-key: $API_KEY" -X POST http://127.0.0.1:8000/api/apartment-agent/test-extract -d '{"group_name":"Elite24 Apartment"}' -H 'Content-Type: application/json'` and confirm the response is a JSON object whose `progress` block has the expected shape and whose `total` field matches `results.length`.

## 3. Subunit 2: Image filter denylist + cap logging (one commit)

Spec: `apartment-agent-image-presence` (the URL-hygiene half).

- [ ] 3.1 In `app/modules/apartment_agent/image_filter.py`, extend the `_bad_suffixes` denylist (currently at lines 87-97) to include `.bin`, `.zip`, `.rar`. Verify the recent `Elite24 Apartment` crawl's `.bin` URL (from the most recent backend.log) would now be dropped.
- [ ] 3.2 In the same module, in `filter_image_urls`, add a DEBUG log line when the `MAX_IMAGE_URLS_PER_MESSAGE = 200` cap is hit (line 129). The log MUST include the message id (passed in as a new `message_id: str | None = None` kwarg) and the dropped count. The function signature changes to `filter_image_urls(urls, *, message_id=None)` — additive kwarg, all existing callers continue to work.
- [ ] 3.3 Update the three call sites in `router.py` (`test_extract_endpoint`, `preview_endpoint`) and `pipeline.py::process_messages` to pass `message_id=row["id"]` so the new log line is useful.
- [ ] 3.4 Add `linkedin_group_crawler/tests/test_apartment_agent_image_filter.py` with cases: (a) `.bin` URL is dropped; (b) `.zip` URL is dropped; (c) `.rar` URL is dropped; (d) `.pdf` URL is still dropped (regression); (e) `.jpg` URL is kept (regression); (f) extensionless URL is kept (regression — Supabase signed-URL style); (g) 201 URLs → cap fires + DEBUG log line is emitted (use `caplog`).
- [ ] 3.5 Commit: `feat(apartment-agent): drop .bin/.zip/.rar URLs from LLM prompt`. Verify with `pytest linkedin_group_crawler/tests/test_apartment_agent_image_filter.py -v` (all 7 cases pass) and `pytest linkedin_group_crawler/tests/test_apartment_agent_assets.py -v` (existing tests still pass — the `message_id` kwarg is additive).

## 4. Subunit 3: FE "no images attached" placeholder (one commit)

Spec: `apartment-agent-image-presence` (the FE half).

- [ ] 4.1 In `components/features/zalo/dashboard/ZaloAgentTestPanel.tsx::ResultCard` (lines 706-807), add a render branch after the field grid: when `item.listing.image_count === 0`, render a `<p class="text-body-xs text-on-surface-variant mt-xs italic">không có ảnh đính kèm</p>`. When `image_count >= 1`, the existing thumbnail strip renders as today. The `Field` for "Ảnh" already shows the count, so no change there.
- [ ] 4.2 Above the existing `Results Summary` block (around line 574), add a thin progress bar component (inline `ProgressBar` that takes `{total, processed, timed_out}` and renders a determinate bar with a label "Đã xử lý X / Y — Z timeout"). Render it only when `result.progress` is present and `result.progress.total > 0`. When `timed_out > 0`, append the message " — bấm 'Chạy lại' để tiếp tục" to the label.
- [ ] 4.3 In `linkedin-crawler-ui/.env.local`, add a commented `NEXT_PUBLIC_ZALO_API_BASE_URL=http://127.0.0.1:8000` line at the top, with a comment: "Bật để bypass Next.js dev-proxy 30 s timeout cho apartment-agent POST. SSE auth events vẫn dùng rewrite path." Do NOT make it the default in `.env.example` — it's an opt-in per-developer choice.
- [ ] 4.4 Commit: `feat(apartment-agent): FE "no images" placeholder + progress bar`. Verify with `npm run check` (or the project's equivalent typecheck + lint) and a `gstack browse` run on the dev stack: pick `Elite24 Apartment`, click "Test Agent", watch the bar fill, see the "không có ảnh đính kèm" line on messages that had 0 images and thumbnails on the rest.

## 5. Subunit 4: AGENTS.md + runbook update (one commit)

- [ ] 5.1 In the project-root `AGENTS.md`, under the "Dev commands" / "Backend env" section, add a short subsection titled "Apartment agent timeout env" that lists the three new env vars (`APARTMENT_AGENT_TEST_EXTRACT_LIMIT`, `APARTMENT_AGENT_TEST_EXTRACT_TIMEOUT_S`, `APARTMENT_AGENT_PREVIEW_TIMEOUT_S`) and the `NEXT_PUBLIC_ZALO_API_BASE_URL` env var, with one-line summaries and the recommended dev defaults.
- [ ] 5.2 In the same file's "Things you will get wrong without this file" section (if it still exists), add a bullet: "Apartment-agent POSTs take >30 s when a real crawled group is selected — the Next.js dev rewrite proxy (`next.config.js:30`) returns `Internal Server Error` at the 30 s mark, and the FE `requestJson` guard sees the non-JSON body. Set `NEXT_PUBLIC_ZALO_API_BASE_URL=http://127.0.0.1:8000` to bypass the proxy, or use the Agent tab's capped 20-message default."
- [ ] 5.3 In the same file, remove the now-stale bullets about `APARTMENT_AGENT_VISION_ENABLED` / `LLM_VISION_MODEL` if any change in the previous `apartment-agent-preview-and-villa-push` referenced them — the user explicitly does not want vision. (Verify with `grep -n -i 'vision\|LLM_VISION' AGENTS.md`; if clean, skip this step.)
- [ ] 5.4 Commit: `docs(apartment-agent): timeout env + dev-proxy gotcha`. Verify with `grep -n "APARTMENT_AGENT_TEST_EXTRACT\|NEXT_PUBLIC_ZALO_API_BASE_URL" AGENTS.md` — both must appear.

## 6. Wrap up

- [ ] 6.1 Run `pytest linkedin_group_crawler/tests/` to confirm all 7 existing test files plus the 1 new test file from Subunit 2 pass. (Existing files: `test_apartment_agent_assets.py`, `test_apartment_agent_dedup.py`, `test_apartment_agent_e2e.py`, `test_apartment_agent_extractor.py`, `test_apartment_agent_pipeline.py`, `test_apartment_agent_route.py`, `test_apartment_agent_sync.py`. New: `test_apartment_agent_image_filter.py`.)
- [ ] 6.2 Run `npm run check` in `linkedin-crawler-ui/` and confirm zero new TypeScript or lint errors. (Same 7 pre-existing errors in `ZaloBroadcastPanel.tsx` and `ZaloLiveGroupPicker.tsx` noted by the previous change are out of scope.)
- [ ] 6.3 Open a single PR that contains the 4 commits in order. Title: `fix(apartment-agent): test-extract timeout + image-presence UX`. Body links to the OpenSpec change and includes the `probe.md` transcript from task 1.1.
- [ ] 6.4 Mark task 5.7 of the previous `apartment-agent-preview-and-villa-push` change as done (it was pending the manual browse-verification run, which is now possible because the 500 is fixed). Also close task 7.4 of that change (manual staging run) — leave it for the user to perform the real GoDaNang FE realtime channel check.
- [ ] 6.5 Archive `fix-apartment-agent-test-extract-timeout` via `openspec archive fix-apartment-agent-test-extract-timeout` only after the PR is merged and the user has confirmed the Agent tab works end-to-end.
