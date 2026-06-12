## Why

The "Agent Test" → "Chọn nhóm đã crawl" flow in the Zalo crawler currently
returns `API 500: phản hồi không phải JSON` whenever the user picks a real
crawled group, so the Agent tab is effectively dead for its primary use case.
The earlier `apartment-agent-preview-and-villa-push` change shipped a typed
error envelope and a `requestJson` non-JSON guard, but the underlying latency
bug was not addressed — the 500 still fires, just with a friendlier toast.

The chain that produces the 500 is reproducible end-to-end on the running
dev stack:

1. The crawl at `03:12:07` saved 20 messages with 7 images for
   `Elite24 Apartment` into Supabase.
2. The user clicks "Chọn nhóm đã crawl" and "🚀 Test Agent". The FE POSTs
   `{"group_name":"Elite24 Apartment"}` to
   `…/minhhoang-scraper/api/apartment-agent/test-extract`, which is
   rewritten by `next.config.js` to `http://127.0.0.1:8000/api/apartment-agent/test-extract`.
3. The backend endpoint fetches up to **50 messages** (see
   `router.py:292`) and fans out to the LLM with
   `APARTMENT_AGENT_BATCH_CONCURRENCY=5` (default from
   `app/modules/apartment_agent/config.py`). With the LLM at
   `https://api.shopaikey.com/v1`, a 50-message batch routinely takes
   30–180 s.
4. The Next.js dev-server rewrite proxy (`next.config.js:30`) does not
   propagate the upstream response for that long — it closes the socket
   at the 30 s mark and emits `ECONNRESET` ("socket hang up" — see
   `/tmp/frontend.log` after each retry).
5. Next.js then returns plain-text `Internal Server Error` (HTML) to
   the FE. The FE's `requestJson` guard catches the `await
   response.json()` failure and renders `API 500: phản hồi không phải
   JSON (…/api/apartment-agent/test-extract)` — exactly the user-facing
   message.

A second, related gap: the user wants the agent to "detect text and
images clearly". Today the agent already has image *URLs* in hand
(the same `storage_url` values the crawl uploaded to Supabase
Storage — see `app/modules/zalo/services/supabase_service.py:761-839`)
and the LLM prompt does include them as a newline-separated list
(`app/modules/apartment_agent/extractor.py:80-89`), but:

- the image URLs are not surfaced as a per-message *count* on the
  response — operators cannot tell from `TestExtractResponse` which
  messages had 0 / 3 / 12 images attached, so they cannot tell
  whether the LLM had visual evidence to work with;
- the URL list goes into the prompt as a single trailing block, not
  inline next to the message body, so the LLM has to do its own
  matching;
- non-image URLs (e.g. a mis-crawled `.bin` payload — see
  `81d09421-...ef00ae2a4fb94b2abd4a6bd4b02f0e6f.bin` in the most
  recent crawl log) sneak through `image_filter.py`'s suffix check
  and bloat the prompt with garbage.

This change is **explicitly NOT a vision-LLM change**. We do not
call OpenAI vision; the model still only sees URLs as text. The
change is about making sure the agent *knows* images are present,
*exposes* that count, *filters* obvious non-image URLs out, and
*fits inside the dev-proxy timeout* so the FE never sees a 500.

The crawl → agent handoff for images is a one-way street, not a
re-download from Zalo. The end-to-end flow is:

1. **Crawl time** — `app/modules/zalo/services/supabase_service.py::save_message_assets`
   (line 761) downloads each image CDN URL from Zalo
   (`_download_image`, line 805), uploads the bytes to Supabase Storage
   under the path `<user_id>/<job_id_or_manual>/<message_uuid>-<random_hex>.<ext>`
   (line 808-812), and writes a row to `zalo_message_assets` with
   `storage_url` (the public Supabase Storage URL — see the public
   bucket URL at supabase_service.py:119) and `status="uploaded"`.
2. **Crawl completion log** — the operator-visible summary at
   supabase_service.py:438 (`images_uploaded=7 images_failed=0`) is
   the source of the "Tin nhắn: 20 / Ảnh: 7" toast the user just
   mentioned.
3. **Agent time** — `app/modules/apartment_agent/router.py::test_extract_endpoint`
   (line 286) re-queries `zalo_messages` with a PostgREST join
   `assets:zalo_message_assets(storage_url,status)`, and the
   `extract_image_urls_from_assets` helper (image_filter.py:153)
   turns each joined row's `storage_url` into a string in the
   per-message `image_urls` list. The agent never re-fetches from
   the Zalo CDN; the agent never re-uploads to Supabase. The
   `storage_url` values are the exact URLs the agent ships to the
   LLM as text context.

## What Changes

- Cap the `/test-extract` fan-out to fit inside the 30 s dev-proxy
  window: reduce the default `limit` from 50 to **20 messages**, run
  the LLM with `concurrency=10` for that path, and add a
  per-request hard timeout (configurable, default 25 s) that returns
  a `TestExtractResponse` with `status="failed"` and
  `error_message="timed out"` for any message whose LLM call is still
  in flight at the cut-off, rather than letting the proxy die.
  The `/preview` path keeps its 200-message limit but also opts into
  the same per-request timeout and concurrency settings so a stale
  preview does not freeze the FE for minutes.
- Bypass the Next.js dev proxy for the apartment-agent routes by
  pointing the FE at the backend directly. Today
  `NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL` is set to the FE's own
  origin (with `basePath`), forcing every long call through the dev
  proxy. The FE's `lib/env.ts` already accepts
  `NEXT_PUBLIC_ZALO_API_BASE_URL`; switching that env var to
  `http://127.0.0.1:8000` (or `http://<vps>:8000` in staging/prod)
  keeps the rewrite path for the routes that need it (SSE auth
  events) but routes the slow LLM calls straight to FastAPI. Document
  this in `AGENTS.md` so the next agent does not regress it.
- Surface the image-presence signal in the response shape. Add a
  per-message `image_count: int` and a flat list of `images: list[str]`
  (already in `TestExtractListing`) — the LLM never "sees" the
  pixels, but the operator can see at a glance "this message had 4
  images attached and the model had those URLs in its prompt" by
  looking at the existing `ResultCard` thumbnails. Tighten the
  image filter to drop non-image suffixes (the recent crawl's
  `.bin` payload is the canonical example — see
  `image_filter.py:_IMAGE_SUFFIXES` for the current allowlist and
  add `.bin`, `.zip`, `.rar` to the denylist). Keep the URL cap
  (50 per message) as a defensive ceiling but log a warning when
  we hit it, so the operator knows the model was prompt-starved.
- Render the image count in the Agent tab so "Agent Test" results
  make it obvious which messages had photos attached. The existing
  `ResultCard` already shows `image_count` and an `images.length > 0`
  thumbnail strip (`ZaloAgentTestPanel.tsx:756-804`); add a small
  "(không có ảnh đính kèm)" placeholder for `image_count == 0` so
  the absence of images is *visible* — currently the absence of a
  thumbnail strip can be misread as "the model forgot to show me the
  images" when in fact there were no images to show.
- Surface the timeout / partial-success state in the FE so the
  user can tell "Agent is still working" from "Agent crashed". Add
  a `progress: { processed, total, in_flight, timed_out }` block
  to `TestExtractResponse` and render a thin progress bar in
  `ZaloAgentTestPanel`; if the response is a partial
  (`timed_out > 0`), show "Đã xử lý X / Y — Z timeout, bấm 'Chạy
  lại' để tiếp tục" instead of an error toast.

## Capabilities

### New Capabilities

- `apartment-agent-pipeline-timeout`: Per-request timeout and
  concurrency controls on the test-extract and preview endpoints
  so a 50-message batch cannot hold a Next.js dev-proxy socket
  open past 30 s. Exposes a `progress` block on the response and
  emits partial `TestExtractResult` rows with `status="failed"`
  and `error_message="timed out"` for any LLM call still in flight
  at the cut-off. Defaults: 20 messages / 10 concurrency / 25 s
  for test-extract; 200 messages / 10 concurrency / 120 s for
  preview.
- `apartment-agent-image-presence`: The agent endpoint surfaces
  per-message image count and a clear "no images attached" state
  in the FE, and the image filter drops obvious non-image
  suffixes (`.bin`, `.zip`, `.rar`) from the URL list before
  shipping to the LLM. The LLM is still text-only — the model
  sees a list of URLs, not pixels.

### Modified Capabilities

None. No existing spec in `openspec/specs/` needs a delta — the
behaviour change is contained to the apartment-agent module and
its FE panel. The previous `apartment-agent-preview-and-villa-push`
change still applies.

## Impact

- **Backend**:
  - `app/modules/apartment_agent/router.py`: `test_extract_endpoint`
    and `preview_endpoint` get a `limit` cap (20 / 200), a
    `timeout_s` parameter, a per-message `asyncio.wait_for` guard,
    and a `progress` block in the response shape. The
    `image_filter.extract_image_urls_from_assets` import site
    inside the group-name branch moves up to the module top
    (it is already imported twice — once in each endpoint, once in
    `/process`).
  - `app/modules/apartment_agent/config.py`: add `test_extract_limit`,
    `test_extract_timeout_s`, `preview_timeout_s` fields with
    `Field(default=...)`. No `image_*` or `vision_*` settings — the
    image filter is a deterministic URL-cleanup step, not a model
    choice.
  - `app/modules/apartment_agent/image_filter.py`: extend the
    `_bad_suffixes` denylist (currently at
    `image_filter.py:87-97`) to include `.bin`, `.zip`, `.rar`.
    Add a debug log line when the 50-URL cap kicks in (currently
    silent — see `image_filter.py:129`).
  - `app/modules/apartment_agent/schemas.py`: `ProgressBlock`
    (additive). `TestExtractListing.image_count` and `.images`
    already exist (router.py:57-58); no schema change needed for
    the image-presence surface.
- **Frontend**:
  - `services/zaloCrawlerService.ts`: `testAgentExtract` /
    `previewAgentExtract` request types gain an optional
    `limit: number`. No behaviour change when omitted.
  - `components/features/zalo/dashboard/ZaloAgentTestPanel.tsx`:
    `ResultCard` renders a "không có ảnh đính kèm" placeholder when
    `item.listing.image_count === 0` (currently the absence of a
    thumbnail strip is silent). Add a thin `ProgressBar` above the
    results summary when `result.progress` is present.
- **OpenSpec**: this change does not touch the
  `apartment-agent-preview-and-villa-push` artifacts. The
  in-flight `zalo-apartment-filter-pipeline` and
  `zalo-to-godanang-villa-sync` are still superseded by that
  earlier change; this one is a follow-up, not a replacement.
- **Dependencies**: no new Python or npm deps. The image filter
  is a string-only operation.
- **External systems**: no changes. The agent still calls the
  configured `LLM_BASE_URL` with the existing text-only LLM
  (`LLM_MODEL`). No new env vars are required for the image
  feature — it is a deterministic URL-cleanup step.
- **Breaking changes**: none. The new `progress` block is
  additive. The lowered `/test-extract` `limit` (50 → 20) is a
  *response-shape change* in the sense that fewer rows come back,
  but the rows themselves are identical and the new
  `progress.timed_out` count makes the truncation visible.
  The `.bin`/`.zip`/`.rar` filter is a pure drop — anything
  previously mis-shipped as an "image URL" is now correctly
  identified as not-an-image. The `images` list on the response
  was always present; we only add a UI hint when it is empty.
