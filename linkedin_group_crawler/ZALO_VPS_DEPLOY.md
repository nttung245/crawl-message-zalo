# Zalo VPS deploy

This runbook is for the Zalo crawler only.

## Required mode

- Run `zalo-browser` with exactly one worker.
- `zalo-api` may use multiple workers in proxy mode.
- Keep `storage/` mounted so the Chromium profile survives restarts.
- Do not use Redis for Zalo sessions. Zalo sessions contain live Playwright objects.
- Do not expose VNC/noVNC directly to the internet.
- For production, use `docker-compose.zalo-prod.yml`.
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

## Start legacy multi-worker + noVNC mode

This mode runs:

- `zalo-browser`: one worker, owns Chromium/session/crawl.
- `zalo-api`: multiple Uvicorn workers, stateless proxy for `/api/zalo/*`.
- This scales request handling, not one shared Zalo account. Jobs for the same session/account are still serialized by session lock.

```bash
ZALO_API_WORKERS=4 docker compose -f docker-compose.zalo-multi.yml up -d --build
docker compose -f docker-compose.zalo-multi.yml logs -f
```

Point frontend/API clients to `zalo-api` port `8000`, not directly to `zalo-browser`.

Health check from the VPS:

```bash
curl -s http://127.0.0.1:8000/health
```

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
