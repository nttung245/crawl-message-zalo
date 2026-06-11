# Zalo VPS deploy

This runbook is for the Zalo crawler only.

## Required mode — always use proxy mode

The Zalo Playwright session is a live browser object, so all crawl state
(`job_store`, `job_events` subscribers, the in-process crawl queue) must
live in a single Python process. The recommended way to scale request
handling is to run `zalo-api` as a stateless multi-worker proxy in front
of a dedicated single-worker `zalo-browser` container. This is the
**only** supported way to get progress updates (`GET /api/zalo/jobs` and
`GET /api/zalo/jobs/events` SSE) to line up with the worker that owns
the job.

If `zalo-api` runs multi-worker without `ZALO_BROWSER_SERVICE_URL`, the
job_store is per-process: a job created in worker A is invisible to the
browser in worker B, and the "Tiến độ crawl theo nhóm" UI will show
jobs stuck in `queued` forever even though they are progressing.

- Run `zalo-browser` with exactly one worker.
- Run `zalo-api` with multiple workers (4 by default) and set
  `ZALO_BROWSER_SERVICE_URL=http://zalo-browser:8000` so it routes to
  the dedicated browser container.
- Keep `storage/` mounted so the Chromium profile survives restarts.
- Do not use Redis for Zalo sessions. Zalo sessions contain live Playwright objects.
- Do not expose VNC/noVNC directly to the internet.
- For production, prefer `docker-compose.zalo-multi.yml` over
  `docker-compose.zalo-prod.yml` (the prod file runs `zalo-api`
  multi-worker without a separate browser container, which re-introduces
  the per-process state problem). Use the prod file only if you have
  exactly one Zalo account and never run multiple concurrent users.
- Use noVNC only as rescue/manual screen mode.

## Backend `.env`

Create `linkedin_group_crawler/.env` from `.env.example` and set at minimum:

```env
API_KEY=<long-random-api-key>
CORS_ORIGINS=http://<frontend-host>:3000
ZALO_CORS_ORIGINS=http://<frontend-host>:3000

ZALO_GOOGLE_CREDENTIALS_PATH=/app/credentials/service_account.json
ZALO_DEFAULT_SHEET_ID=<google-sheet-id>
GOOGLE_SERVICE_ACCOUNT_JSON=/app/credentials/service_account.json
GOOGLE_SPREADSHEET_ID=<google-sheet-id>

ZALO_BROWSER_HEADLESS=false
ZALO_BROWSER_PERSISTENT_PROFILE=true
ZALO_BROWSER_USER_DATA_DIR=/app/storage/chromium-profile
ZALO_BROWSER_REMOTE_VIEWER_URL=

ZALO_VNC_ENABLED=false
ZALO_AUTO_OPEN_ON_START=false
ZALO_VNC_PASSWORD=<strong-vnc-password-for-rescue-mode>
ZALO_API_BIND=127.0.0.1
ZALO_VNC_BIND=127.0.0.1
ZALO_NOVNC_BIND=127.0.0.1
ZALO_SESSION_STORE=memory
```

If the frontend is on another machine, put the public frontend origin in `CORS_ORIGINS`.

## Start production mode

Production mode runs headed Chrome inside Xvfb, but does not start x11vnc/noVNC.
Users log in by scanning QR on the web UI. Each browser/user gets a separate
`X-User-ID`, so profiles are stored under `storage/chromium-profile/<user-id>`.

From `linkedin_group_crawler`:

```bash
mkdir -p storage data credentials
# Put service_account.json in ./credentials/service_account.json
docker compose -f docker-compose.zalo-prod.yml up -d --build
docker compose -f docker-compose.zalo-prod.yml logs -f
```

## Start rescue noVNC mode

From `linkedin_group_crawler`:

```bash
mkdir -p storage data credentials
# Put service_account.json in ./credentials/service_account.json
docker compose -f docker-compose.zalo-vnc.yml up -d --build
docker compose -f docker-compose.zalo-vnc.yml logs -f
```

Use this only when Zalo requires manual interaction that QR login cannot solve.

## Start multi-worker proxy mode (recommended)

This mode runs:

- `zalo-browser`: one worker, owns Chromium/session/crawl and the
  in-process `job_store` / `job_events`.
- `zalo-api`: multiple Uvicorn workers, stateless proxy for
  `/api/zalo/*`. All Zalo-specific routes are routed to
  `zalo-browser` via `ZALO_BROWSER_SERVICE_URL`.
- Apartment-agent and villa-sync routes are mounted on `zalo-api`
  itself (they don't need a browser) and run multi-worker.

```bash
ZALO_API_WORKERS=4 docker compose -f docker-compose.zalo-multi.yml up -d --build
docker compose -f docker-compose.zalo-multi.yml logs -f
```

Point frontend/API clients to `zalo-api` port `8000`, not directly to
`zalo-browser`.

Health check from the VPS:

```bash
curl -s http://127.0.0.1:8000/health
curl -s -H "x-api-key: $API_KEY" http://127.0.0.1:8000/api/zalo/jobs
```

## Diagnose "stuck in queued"

If the "Tiến độ crawl theo nhóm" panel shows jobs that never leave
`queued`, run the diagnostics below before suspecting the code.

1. Confirm the live process count:

   ```bash
   docker exec zalo-api ps -ef | grep uvicorn | grep -v grep | wc -l
   ```

   If this returns `> 1` AND you are NOT in proxy mode (no
   `ZALO_BROWSER_SERVICE_URL` set), you have hit the per-process
   `job_store` bug. Switch to `docker-compose.zalo-multi.yml`.

2. Confirm proxy routing is wired:

   ```bash
   docker logs zalo-api 2>&1 | grep -E "Zalo API|proxy|workers"
   curl -s -H "x-api-key: $API_KEY" http://127.0.0.1:8000/api/zalo/workers
   ```

   The response should show `"routing_mode": "proxy"`. If it shows
   `"routing_mode": "direct"`, `ZALO_BROWSER_SERVICE_URL` was not
   picked up — restart `zalo-api` after setting it.

3. Confirm SSE events are flowing:

   ```bash
   curl -N -s -H "x-api-key: $API_KEY" http://127.0.0.1:8000/api/zalo/jobs/events &
   ```

   Then submit a fresh crawl from the UI. You should see
   `event: job-status` lines within 1–2 seconds for each status
   transition. If the stream is silent, the publisher and the SSE
   client are on different workers — back to step 1.

## Access noVNC safely

Use SSH tunnel from your local machine:

```bash
ssh -N -L 6080:127.0.0.1:6080 -L 8000:127.0.0.1:8000 <user>@<vps-ip>
```

Then open:

```text
http://127.0.0.1:6080/vnc.html?autoconnect=true&reconnect=true&resize=scale&show_dot=true
```

Use `ZALO_VNC_PASSWORD` when noVNC asks for the VNC password.

## Frontend env

For local frontend connecting through the SSH tunnel:

```env
NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_LINKEDIN_CRAWLER_API_KEY=<same API_KEY>
```

For a production reverse proxy, point `NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL` at the protected API URL and rebuild the frontend.

## Smoke test

```bash
curl -s -H "x-api-key: <API_KEY>" http://127.0.0.1:8000/api/zalo/auth/current-status
curl -s -H "x-api-key: <API_KEY>" http://127.0.0.1:8000/api/zalo/jobs
```

Expected: JSON response, not `Invalid API key`.
