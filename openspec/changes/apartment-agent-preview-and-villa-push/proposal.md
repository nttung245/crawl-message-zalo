## Why

The Agent tab in the Zalo crawler is the only path that pushes new apartment
listings into the GoDaNang website, but it is currently held together by ad-hoc
endpoints, an opaque `Internal Server Error` 500 from `/test-extract`, no
notification when a crawl job finishes, no preview before pushing, and a
spec/code drift in the GoDaNang `villas` column mapping that has been stale
across two OpenSpec revisions. Operators cannot tell whether a 500 means a
missing `LLM_API_KEY`, a bad LLM response, or a GoDaNang Supabase outage, and
they cannot inspect or filter the listings before they hit the public site.

This change makes the Agent tab production-safe: every error has a typed
cause, every crawl surfaces a message/image count, every extracted listing
is reviewable before it is written, and the column mapping used to upsert
into GoDaNang is documented, verified against the live `villas` table, and
gated by a classifier so non-listing messages never reach the public feed.

## What Changes

- Add a typed error envelope to the apartment-agent routes so missing config
  (`LLM_API_KEY`, `GODANANG_SUPABASE_URL`, `GODANANG_SUPABASE_SERVICE_KEY`)
  returns a clean 400/500 JSON listing the exact missing env var instead of
  an opaque `Internal Server Error`.
- Guard the FE `requestJson` helper and the raw `fetch` in
  `ZaloAgentTestPanel` so any non-JSON response surfaces a friendly toast
  with the URL and status, mirroring the pattern already used by the
  LinkedIn service helper.
- Mount the already-built `ZaloCrawlProgressPanel` in the Crawl tab and add
  `toast.success` / `toast.info` notifications in the crawler flow hook so
  operators see "Đã tạo N job" and per-job "Tin nhắn: N / Ảnh: M" without
  having to switch tabs.
- Add an LLM text-classifier step (`is_apartment_listing`) ahead of
  extraction so the LLM only does the expensive schema-parse work for
  messages that look like apartment listings, and so non-listing chat
  never reaches the preview or the GoDaNang push.
- Add `POST /api/apartment-agent/preview` that runs the classifier +
  extractor and returns, per listing, the **exact** JSON payload that
  `sync._build_insert_payload` will POST to GoDaNang — without writing.
  The Agent tab renders one card per listing with a "Gửi cái này" /
  "Bỏ qua" toggle and a "Gửi N cái đã chọn" button that calls the
  existing villa-sync endpoint with a `listing_ids` filter. This is the
  human-in-the-loop gate the user asked for.
- Add route-level pytest coverage for `/test-extract` happy/error/config
  paths and an end-to-end smoke test that mocks the LLM and the GoDaNang
  REST client, drives the full chain, and asserts the POSTed body matches
  the live `villas` table columns.
- Verify the GoDaNang `villas` table schema with a one-off
  `select column_name, data_type from information_schema.columns` query
  against the GoDaNang Supabase project, then document the canonical
  column mapping as a new spec and supersede the stale
  `zalo-apartment-filter-pipeline/specs/godanang-villas-sync/spec.md`.
- Mark `zalo-apartment-filter-pipeline` and `zalo-to-godanang-villa-sync`
  as superseded by this change in their respective proposal.md files
  (do not archive — leave for the user to archive after this change
  ships).

## Capabilities

### New Capabilities

- `apartment-agent-classifier`: A `is_apartment_listing(message_text) ->
  ClassificationResult` LLM step that gates extraction. Returns
  `{is_listing: bool, reason: str, confidence: float}`. Lives in
  `app/modules/apartment_agent/classifier.py`, schema in
  `app/modules/apartment_agent/schemas.py:ClassificationResult`. The
  classifier prompt is small and deterministic; uses the same LLM
  client as extraction.
- `apartment-agent-preview`: `POST /api/apartment-agent/preview` that
  runs the classifier + extractor over a list of message ids or a
  group_name, and returns the per-listing payloads that the villa-sync
  endpoint would write — without writing. The Agent tab renders a
  "Bản xem trước (chưa gửi GoDaNang)" panel with one card per
  classified listing. No data is written to GoDaNang until the user
  explicitly clicks "Gửi N cái đã chọn".
- `apartment-agent-villa-column-mapping`: Documents the canonical
  mapping from `ApartmentListing` (LLM output) to GoDaNang `villas`
  table columns. The mapping is verified by querying
  `information_schema.columns` against the live GoDaNang project and
  asserting that every column the code writes to actually exists. The
  spec supersedes the stale `godanang-villas-sync` delta in the
  in-flight `zalo-apartment-filter-pipeline` change.
- `apartment-agent-error-safety`: Typed error envelope for the
  apartment-agent routes (`MissingConfigError`, `LlmAuthError`,
  `LlmSchemaError`, `GodanangRestError`, `PreviewOnlyError`) plus a
  hardened FE `requestJson` that surfaces non-JSON responses as
  friendly toasts. The `/test-extract` route MUST call
  `validate_settings()` before doing any LLM work.
- `zalo-crawl-completion-feedback`: Crawl button shows
  `toast.success("Đã tạo N job crawl")` immediately, then
  `toast.info("Job ${id}: ${messages} tin nhắn, ${images} ảnh")` per
  job completion driven by the existing SSE event stream. The
  `ZaloCrawlProgressPanel` (already built, currently un-mounted) is
  rendered inside `ZaloCrawlerConfigCard` so the operator can see the
  big-number cards and per-group breakdown without leaving the tab.

### Modified Capabilities

None. No requirement-level spec in `openspec/specs/` is being changed
by this work. (The `zalo-apartment-filter-pipeline` change carries an
in-flight `godanang-villas-sync` delta that is now superseded; that
will be archived as part of this change's tasks.)

## Impact

- **Backend**:
  - `app/modules/apartment_agent/`: new `classifier.py`, expanded
    `schemas.py` (`ClassificationResult`, error envelope types), new
    `/preview` route, hardened `/test-extract` route (config
    validation), expanded `pipeline.py` (classifier-first ordering).
  - `app/modules/zalo/api/routes/villa_sync.py`: accept optional
    `listing_ids` filter so preview-then-push can target a subset.
  - `app/main.py`: optional — wire the typed error envelope into the
    global exception handler so 500s from this module return a
    structured body with `request_id` and `kind`.
- **Frontend**:
  - `services/zaloCrawlerService.ts`: try/catch around
    `response.json()` (mirror the LinkedIn service helper).
  - `components/features/zalo/dashboard/ZaloAgentTestPanel.tsx`:
    raw `fetch` in `handleGenerateFake` gets the same try/catch;
    add a "Bản xem trước" panel; per-listing toggle + "Gửi N cái đã
    chọn" button.
  - `components/features/zalo/dashboard/ZaloCrawlerConfigCard.tsx`:
    mount `<ZaloCrawlProgressPanel>` and add toast calls.
  - `hooks/useZaloCrawlerFlow.ts`: emit `toast.success` /
    `toast.info` driven by `job.progress` updates.
- **OpenSpec**:
  - `openspec/changes/zalo-apartment-filter-pipeline/proposal.md`:
    marked superseded; tasks remain for archival.
  - `openspec/changes/zalo-to-godanang-villa-sync/proposal.md`:
    marked superseded; tasks remain for archival.
- **Dependencies**: no new npm/pip dependencies. The classifier
  reuses the existing LLM client; the preview endpoint reuses the
  existing extract pipeline.
- **External systems**:
  - One read-only SQL query against the GoDaNang Supabase project
    (`information_schema.columns` on `villas`) to verify the column
    mapping.
  - One manual e2e run against staging GoDaNang to confirm the
    existing realtime channel in the GoDaNang FE picks up a row
    inserted by the preview-then-push flow.
- **Breaking changes**: none for the public API. The new
  `listing_ids` parameter on `POST /api/zalo/villa-sync` is optional
  and additive.
