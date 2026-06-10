# Crawl Message Zalo — Agent Guide

## Project Overview

Multi-platform social media crawler and automation monorepo. Originally a LinkedIn group scraper, now primarily focused on **Zalo** (Vietnamese messaging platform) with Facebook capabilities.

**Core capabilities:**
- Zalo Web login via QR code scanning (Playwright-driven)
- Group chat message crawling (text + images)
- Persistence to Supabase (PostgreSQL + Storage) and Google Sheets
- Real-time web dashboard for crawl session management
- Broadcast campaigns to Zalo groups from crawled message library
- LinkedIn group crawling, engagement, KPI tracking
- Facebook crawling (in progress)

## Tech Stack

### Backend (`linkedin_group_crawler/`)
- **Python 3.8+** with FastAPI 0.110.0 + Uvicorn 0.27.0
- **Playwright** 1.60.0 + `playwright-stealth` for browser automation
- **Pydantic** 2.5.3 + `pydantic-settings` for config/models
- **Supabase** via REST API (httpx, no SDK)
- **Google Sheets API** via `gspread` + `google-api-python-client`
- **Redis** 5.0.1 (optional, multi-worker session storage)
- **Loguru** for structured logging
- **n8n webhooks** for workflow automation

### Frontend (`linkedin-crawler-ui/`)
- **Next.js** 16.2.6 (App Router, standalone output)
- **React** 19.2.4 + TypeScript 5
- **Tailwind CSS** 4
- **Zod** 4.4.3 + `react-hook-form` for form validation
- **sonner** for toast notifications

### Infrastructure
- Docker with multiple compose variants (prod, VNC rescue, multi-worker)
- PM2 for production process management
- Express.js reverse proxy for unified URL routing
- noVNC / x11vnc / Xvfb for headless browser debugging

## Project Structure

```
crawl-message-zalo/
├── linkedin_group_crawler/          # BACKEND (Python/FastAPI)
│   ├── app/
│   │   ├── main.py                  # FastAPI entrypoint, router registration
│   │   ├── core/                    # Config, logger, browser pool, utils
│   │   ├── modules/
│   │   │   ├── zalo/                # PRIMARY: Zalo crawler module
│   │   │   │   ├── api/routes/      # auth, crawler, jobs, groups, library, broadcasts, maintenance
│   │   │   │   ├── crawler/         # browser, qr_login, scroll_handler, message_parser, group_parser
│   │   │   │   ├── schemas/         # Pydantic models (session, job, message, group, library, broadcast)
│   │   │   │   └── services/        # session_store, job_store, supabase_service, gsheet_service, worker_pool
│   │   │   ├── linkedin/            # LinkedIn crawler module
│   │   │   └── facebook/            # Facebook crawler module
│   │   └── shared/services/         # google_sheet_service, n8n_webhook_service
│   ├── tests/                       # 15 pytest files (LinkedIn-focused)
│   ├── scripts/                     # Shell/PowerShell helpers
│   ├── requirements.txt
│   ├── Dockerfile / Dockerfile.vnc
│   └── docker-compose.zalo-*.yml    # 5 deployment variants
│
├── linkedin-crawler-ui/             # FRONTEND (Next.js/React)
│   ├── app/
│   │   ├── layout.tsx               # Root layout
│   │   ├── (dashboard)/             # Dashboard shell
│   │   │   ├── zalo-crawl/page.tsx  # Zalo crawler page
│   │   │   └── ...                  # Other pages (crawl-data, Interaction, admin)
│   │   └── loginFb/
│   ├── components/features/zalo/    # Zalo UI components
│   │   └── dashboard/               # ZaloCrawlerPageContent, ConfigCard, GroupInputList, etc.
│   ├── hooks/
│   │   ├── useZaloCrawlerFlow.ts    # Main Zalo orchestration hook (~1430 lines)
│   │   └── useDashboardCrawler.ts   # LinkedIn dashboard hook
│   ├── services/                    # API clients (zaloCrawlerService, linkedinCrawlerService)
│   ├── types/zalo-api.ts            # TypeScript interfaces
│   └── AGENTS.md                    # Frontend-specific agent rules
│
└── docs/
    ├── CRAWL_DATA_LINKEDIN_MAP.md   # Architecture map
    └── zalo-crawler-ui-requirements.md  # UI requirements (375 lines)
```

## Key Entry Points

### Backend
- **`linkedin_group_crawler/app/main.py`** — FastAPI app with lifespan management. Conditionally includes proxy routers (multi-worker) or direct routers based on `ZALO_BROWSER_SERVICE_URL`.
- **Key Zalo routes:**
  - `POST /api/zalo/auth/init` — QR login session
  - `GET /api/zalo/auth/events` — SSE stream for auth status
  - `POST /api/zalo/crawl` — Start crawl job
  - `GET /api/zalo/jobs/events` — SSE stream for job progress
  - `POST /api/zalo/groups/verify` — Verify group names
  - `GET /api/zalo/library/messages` — Query stored messages
  - `POST /api/zalo/broadcasts` — Broadcast campaigns

### Frontend
- **`linkedin-crawler-ui/app/(dashboard)/zalo-crawl/page.tsx`** — Zalo crawler page
- **`hooks/useZaloCrawlerFlow.ts`** — Central orchestration hook managing auth, SSE, group verification, job creation, progress tracking

## Configuration

| File | Purpose |
|---|---|
| `linkedin_group_crawler/.env.example` | Full backend env template (117 lines) |
| `linkedin_group_crawler/app/core/config.py` | Global Settings dataclass |
| `linkedin_group_crawler/app/modules/zalo/config.py` | Zalo-specific settings |
| `linkedin-crawler-ui/next.config.js` | Next.js config: `basePath: "/minhhoang-scraper"`, `output: "standalone"` |

## Development Commands

### Backend
```bash
cd linkedin_group_crawler
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
uvicorn app.main:app --reload --host 0.0.0.0 --port 8101
pytest                                    # Run tests
```

### Frontend
```bash
cd linkedin-crawler-ui
npm install
npm run dev                               # Dev server on port 3101
npm run build                             # Production build (standalone)
npm run lint                              # ESLint
```

### Docker (Production)
```bash
cd linkedin_group_crawler
docker compose -f docker-compose.zalo-prod.yml up -d      # Production
docker compose -f docker-compose.zalo-vnc.yml up -d        # VNC rescue mode
docker compose -f docker-compose.zalo-multi.yml up -d      # Multi-worker
```

### PM2 (Production VM)
```bash
pm2 start ecosystem.config.js
pm2 restart minhhoang-backend
pm2 restart minhhoang-frontend
pm2 restart minhhoang-proxy
```

## Testing

- **Framework:** pytest 7.4.4
- **Location:** `linkedin_group_crawler/tests/`
- **Coverage:** 15 test files, all LinkedIn-focused. No dedicated Zalo tests yet.
- **No frontend tests** configured.

## Deployment

- **Production:** PM2-managed on VPS at `/opt/apps/minhhoang-linkedin-scraper/`
  - Backend: `127.0.0.1:8101`
  - Frontend: `127.0.0.1:3101`
  - Proxy: `0.0.0.0:18080` (public)
  - URL namespace: `/minhhoang-scraper/`
- **Docker variants:** 5 compose files for different modes (prod, VNC, multi-worker, multi-account)
- **Base image:** `mcr.microsoft.com/playwright/python:v1.58.0-jammy`

## Code Conventions

- **Backend:** Python with Pydantic models, async FastAPI endpoints, Loguru logging
- **Frontend:** React 19 with hooks, TypeScript strict, Tailwind CSS 4, Zod validation
- **SSE:** Real-time updates via Server-Sent Events (auth status, job progress)
- **State management:** Custom hooks (`useZaloCrawlerFlow`), no Redux/Zustand
- **API client:** Frontend uses custom service modules (`zaloCrawlerService.ts`)
- **Error handling:** Loguru structured logging backend, sonner toasts frontend

## Key Patterns

- **Browser automation:** Playwright with stealth mode, shared Chromium pool
- **Session management:** In-memory store with optional Redis backing for multi-worker
- **Multi-worker:** Proxy router distributes requests across multiple Zalo browser instances
- **SSE streaming:** Real-time auth and job status updates from backend to frontend
- **Data persistence:** Supabase REST API (messages, assets) + Google Sheets (optional)
