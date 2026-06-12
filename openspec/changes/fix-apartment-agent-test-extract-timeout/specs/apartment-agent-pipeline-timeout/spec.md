## ADDED Requirements

### Requirement: Test-extract endpoint completes within the dev-proxy budget

The `POST /api/apartment-agent/test-extract` endpoint MUST complete
its response within a configurable wall-clock budget (default 25 s)
so that the Next.js dev-server rewrite proxy
(`next.config.js:30`) does not close the upstream socket at its
30 s cap and return a non-JSON `Internal Server Error` to the FE.

The endpoint MUST default to fetching at most 20 messages when the
caller does not pass a `limit`, and MUST run LLM calls with
concurrency 10 for the test-extract path. Both defaults are
overridable via the request body for power users.

#### Scenario: 20-message batch, LLM is fast
- **WHEN** the caller posts `{"group_name": "Elite24 Apartment"}` and the upstream crawl saved 20 messages
- **THEN** the endpoint fetches at most 20 messages (the others are silently truncated, with `progress.truncated=true` on the response)
- **AND** the response is JSON
- **AND** the `results` array length is at most 20
- **AND** `progress.processed + progress.timed_out == results.length`

#### Scenario: 20-message batch, one LLM call exceeds the budget
- **WHEN** the 25 s budget elapses while at least one LLM call is still in flight
- **THEN** the in-flight LLM call is cancelled (`asyncio.wait_for` raises `TimeoutError`)
- **AND** the response is JSON
- **AND** the cancelled call's row in `results` has `status="failed"` and `error_message="timed out"`
- **AND** the response's `progress.timed_out` is at least 1

#### Scenario: Caller passes an explicit `limit`
- **WHEN** the caller posts `{"group_name": "Elite24 Apartment", "limit": 5}`
- **THEN** the endpoint fetches at most 5 messages
- **AND** the response's `progress.truncated=true` if the upstream table has more than 5 matching rows

#### Scenario: All 20 messages have already been processed
- **WHEN** the upstream table has fewer than 20 messages for the group
- **THEN** the endpoint fetches whatever is available
- **AND** `progress.total` equals the number of rows actually fetched
- **AND** `progress.truncated=false`

### Requirement: Preview endpoint applies the same timeout contract

The `POST /api/apartment-agent/preview` endpoint MUST also obey a
configurable wall-clock budget (default 120 s) and MUST cap the
fetched message count at 200 by default. A request that exceeds
the budget MUST return a JSON body whose `preview` summary shows
`would_skip += progress.timed_out` so the FE can tell the user
"Đã xem trước X / Y — Z timeout".

#### Scenario: 200-message batch, all fast
- **WHEN** the caller posts `{"group_name": "Elite24 Apartment"}` and 200 messages are available
- **THEN** the endpoint fetches at most 200 messages
- **AND** the response is JSON
- **AND** the FE renders the full preview list without any timeout warning

#### Scenario: 200-message batch, one chunk exceeds the budget
- **WHEN** the 120 s budget elapses while at least one LLM call is still in flight
- **THEN** the in-flight call is cancelled
- **AND** the response is JSON
- **AND** the cancelled listing does NOT appear in `preview.listings`
- **AND** `progress.timed_out >= 1` in the response

### Requirement: Progress block is part of the response

Both `TestExtractResponse` and `PreviewResponse` MUST include a
`progress` block with the following fields: `total` (rows fetched),
`processed` (rows with a terminal status), `in_flight` (rows whose
LLM call was still running when the response was returned — always
0 in practice because we wait, but the field is reserved for
future SSE progress), `timed_out` (rows cancelled by the budget),
`truncated` (true when the fetch was capped by `limit`). The
block is additive; existing fields stay.

#### Scenario: Response shape is additive
- **WHEN** the FE receives a 200 from `/test-extract`
- **THEN** `result.progress` is an object with `total`, `processed`, `in_flight`, `timed_out`, `truncated` fields
- **AND** `result.total`, `result.extracted`, `result.not_listing`, `result.failed`, `result.results` are still present with the same semantics

### Requirement: FE routes long calls straight to FastAPI, not through the dev proxy

The FE's `services/zaloCrawlerService.ts` MUST read an explicit
`NEXT_PUBLIC_ZALO_API_BASE_URL` env var and use it as the base for
the apartment-agent POST endpoints (`/api/apartment-agent/*`),
bypassing the Next.js rewrite proxy that times out at 30 s. When
the env var is unset, the FE MUST fall back to the existing
`NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL` (which points at the FE
origin and triggers the rewrite) for back-compat with the dev
sandbox, and the rewrite path remains in use.

#### Scenario: Env var set to the FastAPI origin
- **WHEN** `NEXT_PUBLIC_ZALO_API_BASE_URL=http://127.0.0.1:8000` is in the FE `.env.local`
- **THEN** the apartment-agent POSTs are issued to `http://127.0.0.1:8000/api/apartment-agent/*`
- **AND** the response does NOT pass through the Next.js dev proxy
- **AND** the 30 s proxy timeout cannot kill a slow LLM call

#### Scenario: Env var unset (back-compat)
- **WHEN** `NEXT_PUBLIC_ZALO_API_BASE_URL` is unset
- **THEN** the FE falls back to `NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL`
- **AND** apartment-agent POSTs are rewritten by `next.config.js:30` exactly as today
- **AND** the slow-LLM 500 risk is documented in the FE toast message ("Yêu cầu quá thời gian — bật NEXT_PUBLIC_ZALO_API_BASE_URL để bỏ qua proxy")
