## 1. Setup and verification

- [x] 1.1 Verify GoDaNang `villas` table columns by running a read-only query against the GoDaNang Supabase project: `select column_name, data_type, is_nullable from information_schema.columns where table_schema = 'public' and table_name = 'villas' order by ordinal_position;`. Paste the result into `openspec/changes/apartment-agent-preview-and-villa-push/specs/apartment-agent-villa-column-mapping/spec.md` under a new `## Verified Columns` section.
- [x] 1.2 Add `APARTMENT_AGENT_CLASSIFIER_ENABLED` and `LLM_BASE_URL` to `linkedin_group_crawler/.env.example` (both fields exist on the settings class but are undocumented).
- [x] 1.3 Mark `openspec/changes/zalo-apartment-filter-pipeline/proposal.md` and `openspec/changes/zalo-to-godanang-villa-sync/proposal.md` as superseded by adding a "**Status: SUPERSEDED by apartment-agent-preview-and-villa-push**" banner at the top of each.

## 2. Subunit 1: Error safety (one commit)

Spec: `apartment-agent-error-safety`.

- [x] 2.1 Add `ApartmentAgentError` Pydantic model to `app/modules/apartment_agent/schemas.py` with `kind`, `message`, `missing`, `status`, `request_id` fields.
- [x] 2.2 Call `validate_settings()` in `test_extract_endpoint` and return typed envelope. Same for `/process` and `/process-all` (convert to typed envelope).
- [x] 2.3 Extend `app/main.py` global exception handler: detect ApartmentAgentError envelope from HTTPException detail; add `request_id` to every 500 response body + log line.
- [x] 2.4 In `linkedin-crawler-ui/services/zaloCrawlerService.ts::requestJson`, wrap `await response.json()` in try/catch mirroring `linkedinCrawlerService.ts:76-83`. Add the same guard to the raw `fetch` in `ZaloAgentTestPanel.tsx::handleGenerateFake`.
- [x] 2.5 In the FE error mapping, detect `error.kind === "missing_config"` and render "Thiếu <missing.join(', ')> trong .env — xem .env.example" with the `request_id` in a collapsible.
- [x] 2.6 Commit: `fix(zalo-agent): typed error envelope + FE requestJson guard`. Verify by hitting `/api/apartment-agent/test-extract` with no `LLM_API_KEY` and confirming the response is HTTP 400 with `kind=missing_config` and a non-empty `missing` array.

## 3. Subunit 2: Crawl completion feedback (one commit)

Spec: `zalo-crawl-completion-feedback`.

- [x] 3.1 In `components/features/zalo/dashboard/ZaloCrawlerConfigCard.tsx`, mount `<ZaloCrawlProgressPanel jobs={flow.jobs} summary={flow.summary} />` after the group list.
- [x] 3.2 In `hooks/useZaloCrawlerFlow.ts::launchRows`, add `toast.success("Đã tạo ${succeededCount} job crawl", { description: "Theo dõi tiến độ ngay bên dưới." })` immediately after the success count is computed. One call per batch, not per job.
- [x] 3.3 In the SSE handler in `useZaloCrawlerFlow.ts` that already updates `job.progress`, add `toast.info("Job ${short_id}: ${messages} tin nhắn, ${images} ảnh")` on `status="completed"`. Cap visible toasts at the most recent 5, auto-dismiss after 3s.
- [x] 3.4 Commit: `feat(zalo-crawl): show message+image counts + toasts on completion`. Verify with `gstack browse` on the running dev stack: click Crawl on a real group, watch the big-number cards increment and a toast appear.

## 4. Subunit 3: Route-level tests (one commit)

Spec: `apartment-agent-error-safety` (the test surface is part of error safety).

- [x] 4.1 Add `linkedin_group_crawler/tests/test_apartment_agent_route.py` with `TestClient(app)` and `unittest.mock.patch` on `app.modules.apartment_agent.extractor._get_client`.
- [x] 4.2 Test cases: 400 (no `texts` and no `group_name`); 200 with `texts` (mocked LLM returns a valid `ApartmentListing`); 200 with `group_name` returning 0 rows; 500 with LLM raise (response is still JSON with `status="failed"` row); 400 with missing env (`validate_settings` returns non-empty `missing`).
- [x] 4.3 Commit: `test(apartment-agent): cover /test-extract happy + error + config paths`. Verify with `pytest linkedin_group_crawler/tests/test_apartment_agent_route.py -v` (all 5 cases pass).

## 5. Subunit 4: Classifier + preview + push UI (one commit per layer, two commits total)

Specs: `apartment-agent-classifier`, `apartment-agent-preview`.

- [x] 5.1 Add `app/modules/apartment_agent/classifier.py::is_apartment_listing` and `ClassificationResult` schema. Use the same OpenAI client, `temperature=0`, prompt ≤ 200 tokens. Gate behind `APARTMENT_AGENT_CLASSIFIER_ENABLED` (default off, opt-in).
- [x] 5.2 Wire the classifier into `pipeline.py::extract_only` and the new `preview_only` so each returns `classifications` in lockstep with `extractions`. Commit: `feat(apartment-agent): text classifier step`.
- [x] 5.3 Add `POST /api/apartment-agent/preview` in `router.py`. Accepts `{texts}` or `{group_name, limit}`. Runs classifier + extractor, returns per-listing `payload` (literal output of `_build_insert_payload` / `_build_update_payload`) with `operation` from a `find_existing_villa` read. No write calls.
- [x] 5.4 Extend `villa_sync_service.sync_villas` to accept an optional `listing_ids: list[str]` filter. If provided, only sync those. Commit: `feat(apartment-agent): preview endpoint + listing_ids filter`.
- [x] 5.5 In `ZaloAgentTestPanel.tsx`, add a "Bản xem trước (chưa gửi GoDaNang)" section after the test result. Per-listing card with title/district/area/price/price_label, `<pre>` payload block, operation badge, and a per-card "Gửi" / "Bỏ qua" toggle (default on for `INSERT`, off for `UPDATE`/`SKIP`).
- [x] 5.6 Footer with `Gửi N cái đã chọn` button calling `villaSync({listing_ids})`. Disable when N=0, show progress bar while sending, flip cards to "Đã gửi" with the returned `villa_id` on completion. Commit: `feat(apartment-agent): preview-then-push UI`.
- [ ] 5.7 Verify with `gstack browse`: paste 2 fake listing texts, click "Test Agent", see 2 preview cards with INSERT badges, toggle 1 off, click "Gửi 1 cái đã chọn", watch the card flip to "Đã gửi" and a success toast.

## 6. Subunit 5: Spec alignment (one commit)

Spec: `apartment-agent-villa-column-mapping`.

- [ ] 6.1 Add `## Verified Columns` section to `apartment-agent-villa-column-mapping/spec.md` with the result from task 1.1.
- [ ] 6.2 In `openspec/changes/zalo-apartment-filter-pipeline/specs/godanang-villas-sync/spec.md`, prepend a banner: `> **SUPERSEDED** by apartment-agent-villa-column-mapping (see openspec/changes/apartment-agent-preview-and-villa-push/specs/apartment-agent-villa-column-mapping/spec.md)`.
- [ ] 6.3 Commit: `docs(openspec): align godanang-villas-sync spec with implementation`. Verify with `openspec validate apartment-agent-preview-and-villa-push --strict` (or the project's equivalent).

## 7. Subunit 6: End-to-end smoke test (one commit)

Specs: `apartment-agent-villa-column-mapping`, `apartment-agent-preview`, `apartment-agent-error-safety`.

- [ ] 7.1 Add `linkedin_group_crawler/tests/test_apartment_agent_e2e.py` that drives the full chain via `TestClient`: `POST /api/apartment-agent/preview` → assert per-listing `payload` matches `_build_insert_payload` byte-for-byte → mock `httpx.AsyncClient` to intercept `POST https://<godanang>/rest/v1/villas` → assert request body equals preview payload.
- [ ] 7.2 Re-run the `information_schema.columns` query (or a `select <each column>` smoke) inside the test setup and assert every key in `_build_insert_payload` exists in the result. This locks the column mapping at test time.
- [ ] 7.3 Commit: `test(apartment-agent): e2e crawl→extract→sync golden path`. Verify with `pytest linkedin_group_crawler/tests/test_apartment_agent_e2e.py -v` (passes; the test fails loudly if any key is missing from the verified-columns list).
- [ ] 7.4 Manual staging run: trigger a real crawl on a known group with one listing, run the preview, send to GoDaNang staging, and confirm the GoDaNang FE's existing realtime channel picks up the new row. Record the run in the PR description.

## 8. Wrap up

- [ ] 8.1 Run `pytest linkedin_group_crawler/tests/` to confirm all 4 new test files plus the existing 19 tests pass.
- [ ] 8.2 Run `npm run check` (or the project's equivalent) in `linkedin-crawler-ui/` to confirm typecheck and lint pass.
- [ ] 8.3 Update `AGENTS.md` "CORS" and "Conventions" sections to mention the new `APARTMENT_AGENT_CLASSIFIER_ENABLED` env var and the `apartment-agent-error-safety` envelope.
- [ ] 8.4 Open a single PR that contains the 6 commits in order. The user will archive `zalo-apartment-filter-pipeline` and `zalo-to-godanang-villa-sync` after the PR merges.
