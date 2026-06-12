# Crawl Message Zalo — Agent Guide

Multi-platform social media crawler. **Zalo** (Vietnamese messenger) is the primary focus; LinkedIn is legacy; Facebook is optional. Backend = Python/FastAPI + Playwright + `zca-js`. Frontend = Next.js 16 (App Router, standalone output, hardcoded `basePath: "/minhhoang-scraper"`).

## Things you will get wrong without this file

- **Backend port is 8000, not 8101.** `linkedin-crawler-ui/next.config.js` rewrites `/api/:path*` → `http://127.0.0.1:8000/api/:path*`; `linkedin-crawler-ui/lib/env.ts` falls back to `http://localhost:8000`. The number 8101 in old notes is stale.
- **Next.js 16 here is not the Next.js you know.** `linkedin-crawler-ui/AGENTS.md` and `rule/nextjs-typescript-coding-standards.md` carry the warnings. Read `linkedin-crawler-ui/node_modules/next/dist/docs/` before writing any FE code.
- **Frontend `basePath: "/minhhoang-scraper"`** is hardcoded in `linkedin-crawler-ui/next.config.js`. All routes are prefixed. The `.env.local` file's `NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL` must point to the backend server directly (port 8000), NOT include the basePath.
- **Port 3000 is often taken** by another project. Use port 3111 instead for dev. CORS allows 3000, 3111, and 10.30.50.29:{3111,8111}.
- **ZCA (`zca-js`) is the default Zalo login path.** `ZALO_QR_LOGIN_MODE=zca` triggers a Node.js bridge (`scripts/zca_*.js` + backend's own `package.json` with `zca-js` + `image-size`). Run `npm install` in `linkedin_group_crawler/`.
- **Two worker modes selected by env var:**
  - **Direct (default):** single FastAPI process owns Playwright browser.
  - **Proxy:** set `ZALO_BROWSER_SERVICE_URL=http://zalo-browser:8000` — multi-worker Uvicorn routes to a separate single-worker `zalo-browser` container. Use `docker-compose.zalo-multi.yml`.
- **Facebook module is optional** — guarded in `app/main.py:66-72`; server starts without it.
- **Apartment Agent** (`app/modules/apartment_agent/`) extracts listings via LLM and upserts to **GoDaNang's** `villas` Supabase table (not this project's DB). Has an opt-in `APARTMENT_AGENT_CLASSIFIER_ENABLED` text classifier, `POST /preview` endpoint, `ApartmentAgentError` envelope, and a preview-then-push UI in the Agent tab.
- **Apartment-agent message grouper** uses content-type boundaries (text-after-text = new listing), not time-window merging. Env: `AGENT_MESSAGE_GROUP_MAX_SIZE=4` (hard cap), `AGENT_MESSAGE_GROUP_TIME_FALLBACK_MINUTES=1` (time gap fallback). Legacy `AGENT_MESSAGE_GROUP_WINDOW_MINUTES` is an alias for `time_fallback_minutes` with a deprecation warning.
- **Spec-driven changes use OpenSpec.** Skills: `.opencode/skills/openspec-*` (also symlinked in `.claude/skills/`). Active changes in `openspec/changes/`, archived in `openspec/changes/archive/`. For non-trivial work, write a proposal first.
- **No `ecosystem.config.js`** exists. Use Docker Compose for production (`ZALO_VPS_DEPLOY.md`).
- **`components/nguyen/`** in the frontend is a developer's working folder — be careful with bulk operations there.
- **`useZaloCrawlerFlow.ts` returns a memoized `flow` object.** When adding state, add it to both the object body AND the `useMemo` dep array at the bottom. Missing deps cause stale closures.

## Layout

```
linkedin_group_crawler/                 # Backend (Python/FastAPI)
  app/
    main.py                             # Entrypoint, lifespan, router registration, CORS
    core/                               # config.py (Settings dataclass), playwright_browser_pool, logger
    modules/
      zalo/                             # PRIMARY
        api/routes/                     # auth, crawler, jobs, groups, library, broadcasts,
                                        # maintenance, listener, accounts, conversations, villa_sync
        services/                       # session_store, job_store, supabase_service,
                                        # gsheet_service, worker_pool, zca_persistent_listener
        crawler/                        # browser, qr_login, scroll_handler, message_parser, group_parser
        zalo-manual-login-mode.md       # noVNC rescue flow
        config.py                       # pydantic-settings (ZALO_* env)
      linkedin/                         # Legacy. router + jobs.
      facebook/                         # Optional, guarded import in main.py
      apartment_agent/                  # LLM extraction → GoDaNang villas table
        grouping.py                     # Content-type-aware message grouper
        extractor.py                    # LLM listing extraction
        classifier.py                   # Opt-in text classifier gate
        sync.py                         # GoDaNang Supabase upsert
        config.py                       # pydantic-settings (GODANANG_*, APARTMENT_AGENT_*)
    shared/services/                    # google_sheet_service, n8n_webhook_service
  scripts/
    zca_*.js                            # Node bridges to zca-js
    run_api_windows.py                  # Windows ProactorEventLoop launcher
  tests/                                # 24 pytest files total (8 apartment_agent, rest LinkedIn)
  package.json                          # ⚠ zca-js + image-size (run `npm install`)
  ZALO_VPS_DEPLOY.md                    # Canonical deploy runbook
  .env.example                          # Backend env template
  supabase_zalo_schema.sql              # Run in Supabase SQL editor before first crawl

linkedin-crawler-ui/                    # Frontend (Next.js 16, React 19, TS)
  app/(dashboard)/                      # zalo-crawl, crawl-data, Interaction,
                                        # quan-ly-nhom, chien-dich, tai-khoan, admin
  components/features/{zalo,linkedin,facebook,accounts,campaigns,dashboard,auth,nguyen}
  hooks/useZaloCrawlerFlow.ts           # Central state hook — flow object is useMemo'd
  lib/env.ts                            # API_BASE_URL + API_KEY resolution
  AGENTS.md                             # ⚠ Read first — Next.js 16 warnings
  rule/nextjs-typescript-coding-standards.md

openspec/                               # Spec-driven change workflow
  changes/                              # Active changes
  changes/archive/                      # Completed / superseded changes
  specs/                                # Main specs
```

## Dev commands

### Backend (from `linkedin_group_crawler/`)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install                                     # for zca-js + image-size
playwright install chromium
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pytest                                          # 24 test files
pytest tests/test_apartment_agent_grouping.py -v  # 23 cases
pytest tests/test_apartment_agent*.py -v        # 96+ tests (8 files)
```

### Frontend (from `linkedin-crawler-ui/`)
```bash
npm install
npm run dev                # next dev — use --port 3111 if 3000 is taken
npm run build              # runs postbuild → scripts/copy-standalone-assets.mjs
npm run check              # type-check && lint — run before commit
```

## Frontend env resolution

`linkedin-crawler-ui/lib/env.ts`:
- `API_BASE_URL` = `NEXT_PUBLIC_ZALO_API_BASE_URL` → `NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL` → `http://localhost:8000`
- `API_KEY` = `NEXT_PUBLIC_ZALO_API_KEY` → `NEXT_PUBLIC_LINKEDIN_CRAWLER_API_KEY` → `""`

`NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL` must point to the backend directly (port 8000), NOT include the basePath `/minhhoang-scraper`. The frontend appends its own basePath automatically.

## Backend env (set in `linkedin_group_crawler/.env`)

Copy from `.env.example`. Required: `API_KEY`, `ZALO_GOOGLE_CREDENTIALS_PATH`, `ZALO_DEFAULT_SHEET_ID`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SPREADSHEET_ID`. Run `supabase_zalo_schema.sql` first.

## Testing

- 24 files in `linkedin_group_crawler/tests/`, all pytest with `TestClient` from `app.main`.
- 8 `test_apartment_agent_*.py` files: grouping, pipeline, extractor, dedup, sync, route, E2E, assets.
- No Zalo-specific tests yet. No frontend tests.

## Docker / deploy

All compose files in `linkedin_group_crawler/`. Runbook: `ZALO_VPS_DEPLOY.md`. Zalo Playwright sessions **must** run in a single process — proxy mode separates `zalo-api` (multi-worker) from `zalo-browser` (single).

## Reference docs

- `ZALO_VPS_DEPLOY.md` — deploy runbook (canonical)
- `linkedin-crawler-ui/AGENTS.md` — Next.js 16 warnings
- `app/modules/zalo/zalo-manual-login-mode.md` — noVNC rescue flow
- `openspec/changes/*/proposal.md` — in-flight specs
