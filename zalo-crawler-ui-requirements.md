# Zalo Crawler UI Feature Requirements (Based on Current Backend + LinkedIn UI Pattern)

## 1) Feature Overview

Build a new Zalo crawler UI flow that:
- starts a crawl session
- shows QR login and login status
- collects multiple group names dynamically
- runs crawl jobs
- shows realtime progress/status per group
- shows final results grouped by group name
- confirms Google Sheets write outcome

Scope of this document is UI requirement and implementation planning only.

---

## 2) Current Project Architecture Notes

Current `D:\crawl-zalo` is backend-focused (FastAPI + Playwright + Google Sheets) with no production frontend module yet.

Relevant backend structure:
- `app/main.py`: app bootstrap + router registration + health endpoint
- `app/api/routes/auth.py`: Zalo auth/init/status/refresh/logout
- `app/api/routes/crawler.py`: crawl job creation and async execution
- `app/api/routes/jobs.py`: job tracking endpoints
- `app/crawler/*`: browser, QR flow, group open, scroll, parse messages
- `app/services/gsheet_service.py`: writes parsed messages to Google Sheets tab
- `app/models/*`: `SessionData`, `JobData`, `Message`

State persistence is in-memory for sessions/jobs:
- restart server => session/job state lost

---

## 3) Backend API and Data Flow Understanding

### 3.1 Auth APIs (prefix `/api/zalo/auth`)

1. `POST /api/zalo/auth/init`
- Output:
  - `session_id: string`
  - `qr_base64: string` (data URL PNG)
  - `status: "waiting_scan"`
  - `expires_in: number`

2. `GET /api/zalo/auth/status/{session_id}`
- Output:
  - `session_id`
  - `status` in:
    - `waiting_scan`
    - `confirmed`
    - `qr_expired`

3. `POST /api/zalo/auth/refresh-qr/{session_id}`
- Output:
  - `qr_base64`
  - `status: "waiting_scan"`

4. `DELETE /api/zalo/auth/session/{session_id}`
- Output:
  - `message`

### 3.2 Crawl APIs

1. `POST /api/zalo/crawl`
- Header required:
  - `X-Session-ID: <session_id>`
- Request body:
  - `group_name: string`
  - `sheet_tab?: string` (optional; currently defaults to `group_name` in backend)
- Output:
  - `job_id`
  - `status: "running"`
  - `sheet_url`

2. `GET /api/zalo/jobs/{job_id}`
- Output model `JobData`:
  - `job_id`
  - `group_id`
  - `group_name`
  - `sheet_id`
  - `sheet_tab`
  - `status: "running" | "completed" | "failed"`
  - `progress.messages_collected`
  - `progress.images_found`
  - `progress.oldest_message_date`
  - `started_at`
  - `completed_at?`
  - `error?`
  - `sheet_url`

3. `GET /api/zalo/jobs`
- Output list of `JobData`

### 3.3 Message Output Contract (Google Sheets)

Current Google Sheet row columns:
- `#`
- `sender`
- `time_text`
- `is_sent`
- `content`

Backend writes to:
- spreadsheet id from `ZALO_DEFAULT_SHEET_ID` env
- worksheet/tab = `sheet_tab` (or fallback `group_name`)

### 3.4 Container Connectivity (Backend <-> UI)

Current backend container setup (from `docker-compose.yml`):
- service: `api`
- container name: `crawl-zalo-api`
- exposed host port: `8000`
- backend CORS env: `CORS_ORIGINS=http://localhost:3000`

Required connection rules for UI implementation:
- Local UI (running on host): use backend base URL `http://localhost:8000`
- UI in Docker (same compose network): use backend service URL `http://api:8000`
- All UI API calls must target `/api/zalo/*` endpoints
- `X-Session-ID` header must be preserved across crawl calls after QR login

Environment contract for UI app:
- `NEXT_PUBLIC_ZALO_API_BASE_URL` (or equivalent) must be environment-driven
- Do not hardcode hostnames in components/hooks
- Do not expose API base URL as a user-editable field in the UI
- Read API base URL from `.env` only (build/runtime env), not from form inputs/local UI settings
- Keep API base configuration isolated in a dedicated Zalo service file

Deployment notes:
- If UI domain changes, backend `CORS_ORIGINS` must be updated accordingly
- For reverse proxy setup (Nginx/Traefik), keep `/api/zalo/*` path mapping stable
- Health check endpoint for integration validation: `GET /api/zalo/health`

---

## 4) LinkedIn UI Pattern to Match

Reference project:
- `D:\Golang\scraper-linkedin\linkedin-crawler-ui`

Patterns to mirror:
- Dashboard shell + sidebar + content sections
- Card-based form block for crawler config
- Modal overlay style for picker/success dialogs
- Consistent design tokens and class naming (spacing/color/typography)
- Inline status banners (success/error/info)
- Action buttons with disabled/loading states
- Table/list result sections with pagination/collapse behavior

Do not introduce a separate visual language for Zalo.

---

## 5) Target UI/UX Flow

1. User opens Zalo crawler page in dashboard area
2. Clicks `Start Crawl`
3. UI calls `POST /api/zalo/auth/init`
4. QR modal appears with `qr_base64`
5. UI polls `GET /api/zalo/auth/status/{session_id}`
6. On `confirmed`:
- close/advance QR stage
- show multi-group input stage
7. User adds/removes group rows dynamically and confirms
8. For each group:
- UI calls `POST /api/zalo/crawl` with same `X-Session-ID`
- receives `job_id`
9. UI polls `GET /api/zalo/jobs/{job_id}` per active group
10. Realtime panel updates:
- current group being crawled
- per-group status
- overall progress bar
- collected messages/images counters
11. On completion:
- show Sheets success link per group (or error detail)
12. Final result view:
- grouped sections by group name
- collapsible groups
- message timeline/chat-like readability

---

## 6) Component Breakdown (New Files First)

Proposed new UI modules (do not modify existing shared logic without approval):

- `components/features/zalo/dashboard/ZaloCrawlerPageContent.tsx`
- `components/features/zalo/dashboard/ZaloCrawlerConfigCard.tsx`
- `components/features/zalo/dashboard/ZaloQrLoginModal.tsx`
- `components/features/zalo/dashboard/ZaloGroupInputList.tsx`
- `components/features/zalo/dashboard/ZaloCrawlProgressPanel.tsx`
- `components/features/zalo/dashboard/ZaloCrawlResultSection.tsx`
- `components/features/zalo/dashboard/ZaloGroupResultCollapse.tsx`
- `components/features/zalo/dashboard/ZaloMessageTimeline.tsx`

State + orchestration:
- `hooks/useZaloCrawlerFlow.ts`

API layer:
- `services/zaloCrawlerService.ts`
- `types/zalo-api.ts`

Routing/page entry (new page only):
- `app/(dashboard)/zalo-crawl/page.tsx`

---

## 7) State Management Plan

Use a single orchestration hook (LinkedIn pattern):
- Auth session state:
  - `sessionId`
  - `qrBase64`
  - `authStatus`
  - `qrExpired`
- Group input state:
  - dynamic `groupRows[]` with add/remove/update
- Crawl execution state:
  - `jobsByGroup: Record<groupName, JobState>`
  - `activeJobIds[]`
  - derived overall progress
- UI state:
  - modal open/close
  - loading flags per action
  - error/success banners

Performance guardrails:
- stable interval refs with cleanup in `useEffect`
- avoid setting state when payload unchanged
- memoize derived maps/lists for result rendering

---

## 8) Loading / Error / Timeout Handling

### Loading states
- `init session` loading
- `qr refresh` loading
- `auth polling` indicator
- `crawl start` per group loading
- `job polling` per group + global progress

### Error states
- auth init failed (503, network, browser issues)
- qr polling failed temporarily (retry quietly + warning banner)
- login not completed (403 with status)
- crawl job failed (`status=failed`, `error` field)
- sheet write failures (surface backend message and sheet info)

### Timeout rules (UI)
- QR status polling timeout window (configurable; e.g. 2-5 min visible guidance)
- Job polling max idle window (if unchanged too long, mark as stalled warning)
- Explicit retry actions for:
  - refresh QR
  - restart crawl for failed group

---

## 9) Realtime Polling Strategy

Auth polling:
- interval: 2s
- stop on:
  - `confirmed`
  - modal close/cancel
  - component unmount

Job polling:
- interval: 2-3s per active job (or batched by cycling job ids)
- stop on:
  - `completed`
  - `failed`
  - component unmount

Anti-flicker for QR:
- only replace `<img src>` when `qr_base64` changes
- keep previous QR displayed until new QR is fully ready
- no rapid unmount/remount of modal image node

Cleanup requirements:
- all intervals stored in refs and cleared on unmount/state transition

---

## 10) Final Result UX Requirement

Result area must include:
- group-level cards/sections
- each group collapsible
- summary chips:
  - status
  - messages count
  - images count
  - oldest date (if any)
- sheet link + tab name
- clear error block if group failed

Message timeline:
- left-aligned readable chat style
- sender + `time_text` + content block
- preserve multiline content
- optional image link list in-message content

---

## 11) Responsive Behavior

Desktop:
- config card + progress/result stacked sections (dashboard conventions)

Tablet/mobile:
- full-width cards
- modal fit viewport with safe paddings
- group rows and timeline collapse naturally
- avoid horizontal scroll except explicitly in dense table fallback

---

## 12) Implementation Phases (Incremental)

### Phase 1: API typing + service layer
- create `types/zalo-api.ts`
- create `services/zaloCrawlerService.ts`
- no shared service edits

### Phase 2: Core orchestration hook
- implement `useZaloCrawlerFlow.ts`
- handle auth + session + polling + multi-group jobs

### Phase 3: UI shell and flow
- add page and core sections
- add QR modal and group input dynamic rows

### Phase 4: Realtime progress + result rendering
- progress bars + statuses + per-group job detail
- collapsible grouped results + timeline layout

### Phase 5: UX hardening
- edge-case errors
- timeout messaging
- retry paths
- loading polish without architecture changes

---

## 13) Non-Goals / Restricted Modifications

Without explicit approval, DO NOT:
- modify existing backend routes/contracts
- modify existing shared UI components/hooks/services
- refactor global design tokens/theme/layout
- change or override existing CSS classes/styles in ways that can impact current screens
- change existing API base configs
- introduce breaking behavior in dashboard navigation

Preferred strategy:
- add new files/components first
- keep existing CSS class names, spacing patterns, and visual behavior stable
- use new scoped components/styles for Zalo feature instead of editing current shared styles
- wire through isolated feature entry points
- keep current architecture conventions

---

## 14) Future Extensibility Notes

Future enhancements that should remain compatible:
- batch crawl queue (many groups with concurrency limits)
- persisted session/job state (DB/Redis instead of in-memory)
- server-sent events/websocket for push progress (replace polling)
- message filters/search/export in result view
- cross-platform crawler tab (LinkedIn/Facebook/Zalo in one shared flow shell)

---

## 15) Acceptance Criteria (UI-level)

- User can complete QR login and see explicit success state
- User can add/remove multiple group names and start crawl
- User sees realtime per-group + overall crawl progress
- User can identify success/failed groups clearly
- Final view shows grouped message results in readable timeline layout
- Google Sheet write result (and link/tab) is clearly visible
- No source-breaking changes to existing code paths without prior approval
