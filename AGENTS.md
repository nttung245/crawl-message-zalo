# Crawl Message Zalo — Agent Guide

Multi-platform social media crawler. **Zalo** (Vietnamese messenger) is the primary focus; LinkedIn is legacy; Facebook is optional. Backend = Python/FastAPI + Playwright + `zca-js`. Frontend = Next.js 16 (App Router, standalone output, hardcoded `basePath: "/minhhoang-scraper"`).

## Things you will get wrong without this file

- **Backend port is 8000, not 8101.** `linkedin-crawler-ui/next.config.js` rewrites `/api/:path*` → `http://127.0.0.1:8000/api/:path*`; `linkedin-crawler-ui/lib/env.ts` falls back to `http://localhost:8000`. The number 8101 in old notes is stale.
- **Next.js 16 here is not the Next.js you know.** `linkedin-crawler-ui/AGENTS.md` and `rule/nextjs-typescript-coding-standards.md` carry the warnings. Read `linkedin-crawler-ui/node_modules/next/dist/docs/` before writing any FE code — APIs, conventions, and file structure all differ from training data.
- **Frontend `basePath: "/minhhoang-scraper"`** is hardcoded in `linkedin-crawler-ui/next.config.js`. All routes are prefixed; `NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL` in `.env.local` already includes the basePath.
- **ZCA (`zca-js`) is the default Zalo login path.** `ZALO_QR_LOGIN_MODE=zca` triggers a Node.js bridge (`linkedin_group_crawler/scripts/zca_*.js` + the backend's own `package.json` with `zca-js` + `image-size`). The Playwright QR path still works but is no longer the default. Backend ships its own `package.json` — run `npm install` in `linkedin_group_crawler/` too.
- **Two worker modes are selected by env var, not config file.**
  - **Direct mode (default)**: single FastAPI process owns the Playwright browser. Single container, single worker.
  - **Proxy mode**: set `ZALO_BROWSER_SERVICE_URL=http://zalo-browser:8000` — `zalo-api` runs multi-worker Uvicorn and routes to a separate `zalo-browser` container. The browser **MUST stay single-worker** (live Playwright objects). Use `docker-compose.zalo-multi.yml`. See `app/main.py:252-266` for the router branch.
- **Facebook module is optional.** `app/main.py:66-72` guards the import in `try/except`; if it fails, the rest of the server still starts and the rest of the API still works.
- **Apartment Agent is a real module** (`app/modules/apartment_agent/`): LLM-based extraction that upserts to **GoDaNang's** `villas` Supabase table, not this project's. Routers wired in `app/main.py:288-290` (`apartment_agent`, `villa_sync`). Config keys live under `GODANANG_*` and `APARTMENT_AGENT_*` in `app/core/config.py` / `.env.example`. Has an opt-in `APARTMENT_AGENT_CLASSIFIER_ENABLED` text classifier (`classifier.py`), a `POST /preview` endpoint that returns per-listing payloads without writing, a typed `ApartmentAgentError` envelope for config-validation errors, and a preview-then-push UI in the FE Agent tab.
- **Spec-driven changes use OpenSpec.** Skills: `.claude/skills/openspec-{propose,apply,archive,sync,explore}/`. Slash commands: `.claude/commands/opsx/*.md`. Active changes in `openspec/changes/`, archived in `openspec/changes/archive/`. For non-trivial work, write a proposal first.
- **Frontend dev port is 3000, not 3101.** `package.json` has bare `"dev": "next dev"` (no `-p` flag). CORS allows 3000, 3111, and 10.30.50.29:{3111,8111}.
- **No `ecosystem.config.js` exists in this repo.** The old "PM2" section is aspirational. Use Docker Compose for production (`ZALO_VPS_DEPLOY.md`).
- **`components/nguyen/`** in the frontend is a developer's working folder — be careful with bulk operations there.

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
    shared/services/                    # google_sheet_service, n8n_webhook_service
  scripts/
    zca_*.js                            # Node bridges to zca-js
    run_api_windows.py                  # Windows ProactorEventLoop launcher
    start_local_stack.ps1               # Boots API + cloudflared tunnel
    start_zalo_vnc.sh                   # Used by docker-compose.zalo-vnc.yml
  tests/                                # 19 pytest files (LinkedIn + apartment_agent)
  package.json                          # ⚠ zca-js + image-size (run `npm install`)
  ZALO_VPS_DEPLOY.md                    # Canonical deploy runbook
  .env.example                          # Backend env template (137 lines)
  supabase_zalo_schema.sql              # Run in Supabase SQL editor before first crawl

linkedin-crawler-ui/                    # Frontend (Next.js 16, React 19, TS)
  app/(dashboard)/                      # zalo-crawl, crawl-data, Interaction,
                                        # quan-ly-nhom, chien-dich, tai-khoan, admin
  components/features/{zalo,linkedin,facebook,accounts,campaigns,dashboard,auth,nguyen}
  hooks/{useZaloCrawlerFlow.ts,useDashboardCrawler.ts,useEngagementTaskQueue.ts}
  lib/env.ts                            # API_BASE_URL + API_KEY resolution (see below)
  scripts/copy-standalone-assets.mjs    # Runs as `postbuild` after `next build`
  AGENTS.md                             # ⚠ Read first — "This is NOT the Next.js you know"
  rule/nextjs-typescript-coding-standards.md

openspec/                               # Spec-driven change workflow
  changes/                              # Active: zalo-apartment-filter-pipeline,
                                        #         zalo-to-godanang-villa-sync
  changes/archive/2026-06-09-fix-zalo-broadcast-bugs/
  specs/                                # zalo-broadcast-target-fixes,
                                        # zalo-campaign-soft-warnings,
                                        # zalo-worker-selector-fix

.claude/skills/                         # openspec-* + global gstack skills
```

## Dev commands

### Backend (from `linkedin_group_crawler/`)
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install                                     # for zca-js + image-size
playwright install chromium
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
pytest                                            # all 19 tests
pytest tests/test_health.py                      # single test
pytest tests/test_apartment_agent_dedup.py -v    # one suite
```

Windows: `python scripts/run_api_windows.py --port 8000` (sets `ProactorEventLoop` required by Playwright on Windows). The `linkedin_group_crawler/app/main.py:12-13` branch also patches the loop policy automatically.

### Frontend (from `linkedin-crawler-ui/`)
```bash
npm install
npm run dev                # next dev — default port 3000
npm run build              # runs `postbuild` → scripts/copy-standalone-assets.mjs
npm run start:standalone   # node .next/standalone/server.js (after build)
npm run check              # type-check && lint — use before commit
```

## Frontend env resolution

`linkedin-crawler-ui/lib/env.ts`:
- `API_BASE_URL` = `NEXT_PUBLIC_ZALO_API_BASE_URL` → `NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL` → `http://localhost:8000`
- `API_KEY` = `NEXT_PUBLIC_ZALO_API_KEY` → `NEXT_PUBLIC_LINKEDIN_CRAWLER_API_KEY` → `""`

All Zalo calls send `x-api-key`; backend `app/modules/zalo/api/security.py::verify_zalo_api_key` checks it. The legacy name is kept for back-compat — use the new `NEXT_PUBLIC_ZALO_*` form in fresh code.

## Backend env (must set in `linkedin_group_crawler/.env`)

Copy from `.env.example`. Required for Zalo to start:
`API_KEY`, `ZALO_GOOGLE_CREDENTIALS_PATH`, `ZALO_DEFAULT_SHEET_ID`, `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY`, `GOOGLE_SERVICE_ACCOUNT_JSON`, `GOOGLE_SPREADSHEET_ID`. Run `supabase_zalo_schema.sql` in Supabase SQL editor before the first crawl.

Common knobs: `HEADLESS`, `PLAYWRIGHT_POOL_SIZE` (1 recommended), `PLAYWRIGHT_WARMUP_ON_STARTUP` (`true` warms up Chromium in background; `/health` is fast either way), `LINKEDIN_AUTO_LOGIN_BEFORE_ENGAGEMENT`, reaction timing constants, `APARTMENT_AGENT_CLASSIFIER_ENABLED` (opt-in text classifier for apartment agent).

## Docker / deploy

All compose files live in `linkedin_group_crawler/`. Canonical runbook: `ZALO_VPS_DEPLOY.md`.

| Compose file | Mode |
|---|---|
| `docker-compose.zalo-prod.yml` | `zalo-browser` (headed Chromium under Xvfb) + `zalo-api` (4 workers). **Default production mode.** |
| `docker-compose.zalo-vnc.yml` | Adds x11vnc + noVNC for manual login rescue. Use only when QR scan fails. |
| `docker-compose.zalo-multi.yml` | `zalo-api` (4 workers, stateless proxy) → `zalo-browser` (1 worker). Set `ZALO_API_WORKERS=4`. Point clients at `zalo-api:8000`. |
| `docker-compose.zalo-multiaccount.yml` | Multi-account per `X-User-ID` (profile stored under `storage/chromium-profile/<user-id>`). |
| `docker-compose.zalo-multiaccount-rescue.yml` | Multi-account + noVNC. |

Health check: `curl -s http://127.0.0.1:8000/health`. Authenticated smoke: `curl -H "x-api-key: $API_KEY" http://127.0.0.1:8000/api/zalo/auth/current-status`.

## Multi-worker / session model

- Zalo Playwright sessions are live browser objects — **must** run in a single process. `app/modules/zalo/services/worker_pool.py::is_zalo_browser_proxy_configured()` reads `ZALO_BROWSER_SERVICE_URL`; the branch in `app/main.py:252-266` decides direct vs proxy routers.
- LinkedIn uses Redis-backed session storage (`REDIS_URL`) when multi-worker. Zalo ignores Redis and uses `ZALO_SESSION_STORE=memory` — do not switch Zalo to Redis.
- LinkedIn sets `LINKEDIN_ENGAGEMENT_PASSWORDS_JSON` or `LINKEDIN_DEFAULT_ENGAGEMENT_PASSWORD` so reaction/comment flows can auto-relogin.

## CORS

`app/main.py::_cors_origins()` allows by default: `http://localhost:3000`, `http://127.0.0.1:3000`, `http://localhost:3111`, `http://127.0.0.1:3111`, `http://10.30.50.29:3111`, `http://10.30.50.29:8111`. Add more via `CORS_ORIGINS` or `ZALO_CORS_ORIGINS` (comma-separated env).

## Testing

- 20 tests under `linkedin_group_crawler/tests/`, all pytest. Pattern: `from fastapi.testclient import TestClient; from app.main import app`.
- 5 new `test_apartment_agent_*.py` cover the apartment agent pipeline.
- No Zalo-specific tests yet. No frontend tests configured.
- `pytest` order is not enforced — run individual files when iterating on a module.

## Conventions

- Backend: async FastAPI + Pydantic 2 + Loguru. Global `Settings` is a dataclass in `app/core/config.py`; Zalo has its own pydantic-settings in `app/modules/zalo/config.py` (with `AliasChoices` so env keys work with or without `ZALO_` prefix).
- Frontend: React 19 hooks + Zod + sonner. No Redux/Zustand. SSE for auth and job progress.
- Storage paths under `linkedin_group_crawler/storage/`: `session/`, `sessions/`, `chromium-profile/`, `runtime/` (logs + n8n URL state), `linkedin_state.json`. All gitignored.
- Branch / PR: no documented model. For non-trivial work, write an OpenSpec proposal first.

## Reference docs in this repo

- `linkedin_group_crawler/README.md` — original LinkedIn-focused README.
- `linkedin_group_crawler/HUONG_DAN_CHAY.txt` — Vietnamese run guide.
- `linkedin_group_crawler/ZALO_VPS_DEPLOY.md` — deploy runbook (canonical).
- `linkedin_group_crawler/app/modules/zalo/zalo-manual-login-mode.md` — noVNC rescue flow.
- `linkedin-crawler-ui/AGENTS.md` — Next.js 16 warnings (read first).
- `linkedin-crawler-ui/rule/nextjs-typescript-coding-standards.md` — FE coding standards (Vietnamese).
- `CRAWL_DATA_LINKEDIN_MAP.md` — LinkedIn data architecture (40 KB; legacy but referenced).
- `zalo-crawler-ui-requirements.md` — Zalo FE requirements.
- `openspec/changes/*/proposal.md` — current in-flight specs.
