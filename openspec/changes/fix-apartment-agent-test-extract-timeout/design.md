## Context

The "Agent Test" → "Chọn nhóm đã crawl" flow in the Zalo crawler is
the only path operators use to validate LLM extraction on real
crawled data, and it is also the precursor to the "preview-then-push"
flow that the previous `apartment-agent-preview-and-villa-push`
change shipped. Today it returns `API 500: phản hồi không phải JSON`
whenever a real group is selected. Reproduction on the running
dev stack (recorded in `openspec/changes/fix-apartment-agent-test-extract-timeout/proposal.md`):

- `POST /api/apartment-agent/test-extract` directly against
  `127.0.0.1:8000` returns valid JSON in 30–180 s depending on the
  message count.
- The same call routed through the Next.js dev rewrite proxy
  (`http://10.30.194.50:3000/minhhoang-scraper/api/apartment-agent/test-extract`)
  returns `Internal Server Error` (plain text) at exactly 30 s;
  the FE `requestJson` guard sees the non-JSON body and renders
  the user-visible toast.

A second, related gap: the operator wants the agent to "detect
text and images clearly". The LLM is text-only and will stay that
way — we are NOT adding a vision model call (no 10× LLM cost, no
new `image_url` content parts, no pHash dedup). The change
focuses on three things the agent can already do but currently
does not surface:

1. **Image count visibility** — every result row already has
   `listing.image_count` and `listing.images` (router.py:57-58),
   but the FE only shows the count, not an explicit "no images
   attached" placeholder when the count is zero. Operators today
   have to read the count to know whether the model had any
   visual context.
2. **URL hygiene** — the image filter at
   `app/modules/apartment_agent/image_filter.py:61-131` already
   keeps a denylist of `.mp4`/`.pdf`/etc., but `.bin` (which
   appeared in the most recent crawl as a mis-classified
   attachment — see backend.log line 339) and `.zip`/`.rar` slip
   through. The model wastes prompt tokens on these.
3. **Timeout contract** — the test-extract endpoint has no
   wall-clock budget. A 50-message batch can hold the Next.js
   dev-proxy socket open past 30 s and die with `ECONNRESET`.

The previous change (`apartment-agent-preview-and-villa-push`)
shipped a typed error envelope and a `requestJson` non-JSON
guard, so the failure is now reported cleanly — but the failure
itself was not addressed. The two open tasks from that change
(5.7 browse-verification and 7.4 manual staging run) could not
pass precisely because of the 30 s proxy timeout.

Stakeholders: the Zalo crawler operator (uses the Agent tab
daily), the apartment-agent module maintainers, the FE panel
author, and indirectly the GoDaNang website visitors (no
listing reaches GoDaNang until Agent Test works).

## Goals / Non-Goals

**Goals:**
- Make `POST /api/apartment-agent/test-extract` succeed end-to-end
  for a real crawled group within the dev-proxy 30 s budget.
- Make image presence visible: every result row reports
  `image_count`, the FE renders a clear "no images attached"
  placeholder when the count is zero, and obvious non-image URLs
  (`.bin`, `.zip`, `.rar`) are dropped from the LLM prompt.
- Surface partial-success state in the FE so the operator can
  distinguish "Agent is still working" from "Agent crashed".
- Keep the change additive: no breaking API change, no schema
  rewrite, no GoDaNang write contract change, no new LLM
  provider call, no new Python or npm dep.

**Non-Goals:**
- Replacing the LLM provider. We still call the configured
  `LLM_BASE_URL` (shopaikey) with the text-only `LLM_MODEL`.
- Adding OpenAI vision. The model still only sees URLs as text.
  "Detect images" means "know images exist" — count them, list
  them in the prompt, and filter obvious non-image URLs — not
  "see the pixels".
- Caching the image list on the FE. The agent re-queries Supabase
  on every call; we do not memoize.
- Perceptual-hash dedup. The same photo uploaded twice shows up
  as two URLs in the prompt and the LLM extracts them as two
  listings. This is a real cost but is out of scope for the
  user's request; the dedup would require either a Supabase
  schema change (store the pHash on `zalo_message_assets`) or
  HTTP GETs to Supabase Storage to pHash on the fly, both of
  which are bigger than the user's ask.
- Changing the GoDaNang `villas` column mapping. The
  `apartment-agent-villa-column-mapping` spec from the previous
  change still applies.

## Decisions

### 1. Cap `/test-extract` at 20 messages and add a per-request budget

The endpoint's current default `limit=50` (see
`router.py:292`) cannot fit inside the 30 s Next.js dev proxy
window when each LLM call takes ~2 s. We lower the default to
20 and run the test-extract path with `concurrency=10`. The
endpoint gets a 25 s wall-clock budget; any in-flight LLM call
at the cut-off is cancelled and emitted as a
`status="failed", error_message="timed out"` row.

**Alternatives considered:**
- *Increase the Next.js dev proxy timeout* (it is hard-coded at
  30 s in Turbopack). Rejected: would mask the same failure in
  staging/prod where long calls also exceed reasonable user
  expectations.
- *Stream the response (Server-Sent Events)*. Rejected for this
  iteration — it would require the FE to add an EventSource
  consumer, and the `progress` block already gives us
  partial-success visibility.
- *Move the endpoint behind a Celery / background job and
  return a job id*. Rejected: the operator wants to see results
  in seconds, not minutes, and the Agent tab is already
  sync-by-design.

### 2. Route slow calls straight to FastAPI, not through the dev proxy

`lib/env.ts` already accepts `NEXT_PUBLIC_ZALO_API_BASE_URL` as
the first-preference env var. The previous change set
`NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL` to the FE's own origin
(with `basePath`), which forces every apartment-agent POST
through the rewrite proxy. We document and recommend
`NEXT_PUBLIC_ZALO_API_BASE_URL=http://127.0.0.1:8000` in the FE
`.env.local` so the slow calls bypass the proxy. The SSE-auth
event stream stays on the rewrite path because it is genuinely
long-lived.

**Alternatives considered:**
- *Disable the rewrite entirely for `/api/apartment-agent/*`*.
  Rejected: SSE events use the same `/api/` prefix and we want
  one routing path.
- *Add a 60 s timeout to the Next.js rewrite*. Rejected: the
  default is not configurable in Turbopack; would require
  ejecting to a custom server.

### 3. Image presence is a response-shape change, not a model change

The `listing.image_count` and `listing.images` fields already
exist on `TestExtractListing` (router.py:57-58). The change is:

- tighten the `_has_image_suffix` denylist in `image_filter.py`
  to include `.bin`, `.zip`, `.rar`,
- log a DEBUG line when the 50-URL cap kicks in (currently
  silent),
- render a "không có ảnh đính kèm" placeholder in `ResultCard`
  when `image_count === 0`.

**Alternatives considered:**
- *Perceptual-hash dedup of the URL list* (down to 8 images per
  message, opt-in). Rejected: requires either a Supabase
  schema migration to store pHash on `zalo_message_assets`, or
  HTTP GETs against Supabase Storage to pHash on the fly. Both
  are bigger than the user's "know images exist" ask, and both
  are deferred to a follow-up change.
- *OpenAI vision call per image*. Rejected: out of scope per
  the user ("the agent just needs to know images are there — not
  see them"). Vision would also 10× the LLM cost and require a
  model name the configured `LLM_BASE_URL` may not support.
- *Add a "photos detected: N" badge to each result row*. This
  is the same as the `image_count` field that already exists;
  we are just making its *zero* case visible.

### 4. Add a `progress` block to the response shape

Both `TestExtractResponse` and `PreviewResponse` get a `progress`
field (`{total, processed, in_flight, timed_out, truncated}`).
This is additive — the existing `total`, `extracted`,
`not_listing`, `failed`, `results` fields keep their semantics.
The FE renders a thin progress bar from this block and shows
"Đã xử lý X / Y — Z timeout" when `timed_out > 0` so the
operator can re-run with a smaller limit if they want full
results.

**Alternatives considered:**
- *Emit progress via SSE*. Rejected: the previous change's
  preview-then-push flow is already JSON-by-design; mixing
  modes per endpoint complicates the FE.
- *Drop the failed rows on timeout*. Rejected: the operator
  wants to see which messages were dropped, not just the count.

## Risks / Trade-offs

- **[Risk]** Lowering the default `limit` from 50 to 20 means
  the Agent tab no longer shows the full history for a
  50-message group. → *Mitigation*: the FE group selector
  already displays `group_name (N tin)`; we add a sub-line
  "(đã cào: 20 hiển thị tối đa — bấm 'Xem tất cả' để
  paginate)" so the operator knows the cap. A follow-up
  change can add pagination if the user requests it.

- **[Risk]** Per-request timeout cancels LLM calls that were
  about to return a good result. → *Mitigation*: the failed
  row is recorded with `error_message="timed out"` and the
  operator can re-run with a smaller `limit`. The cost of
  one wasted LLM call is small (~2 s) compared to the
  alternative (a 500 that hides the cause).

- **[Risk]** Bypassing the dev proxy for the apartment-agent
  routes breaks CORS. → *Mitigation*: `app/main.py::_cors_origins()`
  already allows `http://localhost:3000` and `http://127.0.0.1:3000`
  (see AGENTS.md), which covers the typical FE → BE path.
  Production runs both services behind the same reverse proxy
  in `ZALO_VPS_DEPLOY.md`.

- **[Risk]** Filtering `.bin`/`.zip`/`.rar` URLs could drop a
  legitimate listing photo if the crawler ever stores images
  with those suffixes. → *Mitigation*: the crawler writes
  images with the *content-type*-derived extension in
  `save_message_assets` (supabase_service.py:811), which is
  always an image type for successful crawls. The `.bin`
  payload in the recent crawl is a content-type mismatch the
  crawler already flagged as `status="uploaded"` because the
  download succeeded — the agent now correctly identifies it
  as not-an-image.

- **[Risk]** The Next.js rewrite path is still used for
  `/api/zalo/auth/events` (SSE). If a future change routes the
  apartment-agent POSTs through the rewrite by mistake, the
  30 s timeout reappears. → *Mitigation*: the FE service helper
  has a `// DIRECT: bypasses Next.js dev rewrite proxy` comment
  at the call site, and a pytest test in
  `tests/test_apartment_agent_route.py` mocks the LLM to
  finish in < 1 s, so any regression that re-routes the call
  through the proxy would be caught by the existing 5 s test
  timeout.

## Migration Plan

1. Land the env-var doc change in `AGENTS.md` first
   (one-liner: "Set `NEXT_PUBLIC_ZALO_API_BASE_URL=http://127.0.0.1:8000`
   in `.env.local` to bypass the 30 s Next.js dev-proxy timeout
   on long LLM calls"). This unblocks the operator immediately
   without touching code.

2. Land the BE pipeline-timeout + progress-block change
   (Subunit 1 in tasks.md). Verify with the existing
   `test_apartment_agent_route.py` — the new shape is additive
   so no test changes.

3. Land the image filter denylist expansion + per-message
   `image_count` test (Subunit 2). Verify with a new
   `test_apartment_agent_image_filter.py` covering the
   `.bin`/`.zip`/`.rar` drop and the 50-URL cap log.

4. Land the FE "no images attached" placeholder (Subunit 3).
   Verify with `gstack browse` on the running dev stack:
   pick a real group, click Test Agent, see the placeholder on
   zero-image messages and thumbnails on the rest.

5. Rollback: each subunit is one commit, so `git revert` per
   commit is a clean rollback. The env-var doc change is
   trivially reverted by deleting the line.

## Open Questions

- *Should the per-message 50-URL cap be lowered?* Today's
  cap is generous; in practice no Zalo message has more than
  ~15 attachments. We keep 50 as a defensive ceiling and
  start logging when we hit it, so we can collect real data
  before deciding.

- *Should the dedup step (now deferred) be tackled as a
  follow-up change?* Likely yes — the same photo uploaded
  twice is a real cost on long-running crawls. The
  implementation would either store pHash on
  `zalo_message_assets` at upload time (Supabase migration
  + backfill) or pHash on the fly at agent time (HTTP GETs
  to Supabase Storage with a 5 s budget). The trade-off is
  storage cost vs. round-trip cost; we can decide once we
  know how many real duplicates the Elite24 Apartment
  crawl actually has.

- *Should `ResultCard` also surface the raw count of
  attachments that were dropped by the image filter?* Today
  it surfaces `image_count` (the kept count) but not the
  "5 dropped" number. We could add a debug-toggle that
  shows it. Deferred.
