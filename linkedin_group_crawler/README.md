# LinkedIn Group Crawler - Runbook Van Hanh VM

## 1) Chay local nhanh

```bash
cd linkedin_group_crawler
py -3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

API docs: `http://127.0.0.1:8000/docs` — header `x-api-key` = gia tri `API_KEY` trong `.env`.

Ban do day du (API, UI, luong KPI/sync): [../CRAWL_DATA_LINKEDIN_MAP.md](../CRAWL_DATA_LINKEDIN_MAP.md).

## 2) Kien truc deploy on dinh tren VM

- Monorepo: `/opt/apps/minhhoang-linkedin-scraper`
- Backend code: `/opt/apps/minhhoang-linkedin-scraper/linkedin_group_crawler`
- Frontend code: `/opt/apps/minhhoang-linkedin-scraper/linkedin-crawler-ui`
- Private proxy code: `/opt/apps/minhhoang-linkedin-scraper/minhhoang-private-proxy`

Port runtime:

- Backend: `127.0.0.1:8101`
- Frontend: `127.0.0.1:3101`
- Proxy public: `0.0.0.0:18080`

URL su dung:

- UI: `http://10.30.50.29:18080/minhhoang-scraper/`
- API docs: `http://10.30.50.29:18080/minhhoang-scraper/api/docs`
- API health (GET): `http://10.30.50.29:18080/minhhoang-scraper/api/health`

Luu y:

- Khong dung Nginx shared lam duong vao chinh.
- Namespace rieng cua app la `/minhhoang-scraper`.

## 3) Cau hinh frontend bat buoc (de khong loi prefix)

Trong `linkedin-crawler-ui/next.config.ts`:

```ts
basePath: "/minhhoang-scraper",
assetPrefix: "/minhhoang-scraper",
```

Trong `linkedin-crawler-ui/.env.local`:

```env
NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL=http://10.30.50.29:18080/minhhoang-scraper/api
NEXT_PUBLIC_LINKEDIN_CRAWLER_API_KEY=secret_api_key
```

Luu y:

- FE mo qua `:18080` thi API URL phai cung origin `:18080`.

## 4) PM2 process chuan

Ten process:

- `minhhoang-backend`
- `minhhoang-frontend`
- `minhhoang-proxy`

Lenh quan ly:

```bash
pm2 status
pm2 logs minhhoang-backend --lines 120
pm2 logs minhhoang-frontend --lines 120
pm2 logs minhhoang-proxy --lines 120
pm2 restart minhhoang-backend --update-env
pm2 restart minhhoang-frontend --update-env
pm2 restart minhhoang-proxy --update-env
pm2 save
```

## 5) Backend `.env` khuyen nghi (VM)

File: `linkedin_group_crawler/.env` — mau day du: [.env.example](.env.example).

```env
API_KEY=secret_api_key
HEADLESS=true
PLAYWRIGHT_WARMUP_ON_STARTUP=true

# Playwright — nhieu browser song song (comment/reaction khong xep hang 1 browser)
PLAYWRIGHT_POOL_SIZE=3

# Reaction — VM cham: tang neu menu mo nhung Like/Love khong din (ms)
REACTION_MENU_HOVER_SETTLE_MS=1800
REACTION_POST_GOTO_SETTLE_MS=3500
REACTION_POST_CLICK_SETTLE_MS=1500
```

| RAM `available` (`free -h`) | `PLAYWRIGHT_POOL_SIZE` |
|-----------------------------|-------------------------|
| ~2 GB | `1` |
| ~4–6 GB | `2` |
| ~6+ GB | `3` |
| 16 GB+ | `4` |

- Cung **mot** tai khoan LinkedIn (cung file `storage/session/*.json`): van **tuan tu** (lock file session).
- **Khac** tai khoan: chay song song qua pool.
- Kiem tra sau sua: `curl -s http://127.0.0.1:8101/status` → `playwright_pool_size`, `headless`.

**Debug co UI (VNC):** dat `HEADLESS=false` va start backend kem `DISPLAY=:99` — xem muc **15**.

## 6) Lenh start lai full stack (chuan da verify)

```bash
cd /opt/apps/minhhoang-linkedin-scraper

# Backend production (headless, .venv KHONG phai venv)
pm2 delete minhhoang-backend || true
pm2 start "bash -lc 'cd /opt/apps/minhhoang-linkedin-scraper/linkedin_group_crawler && source .venv/bin/activate && set -a && source .env && set +a && python -m uvicorn app.main:app --host 127.0.0.1 --port 8101'" --name minhhoang-backend --update-env

# Frontend standalone
pm2 delete minhhoang-frontend || true
pm2 start "bash -lc 'cd /opt/apps/minhhoang-linkedin-scraper/linkedin-crawler-ui && HOSTNAME=127.0.0.1 PORT=3101 node .next/standalone/server.js'" --name minhhoang-frontend --update-env

# Proxy
pm2 delete minhhoang-proxy || true
pm2 start server.js --name minhhoang-proxy --cwd /opt/apps/minhhoang-linkedin-scraper/minhhoang-private-proxy --update-env

pm2 save
```

## 7) Proxy config chuan (anti-prefix bug)

File: `/opt/apps/minhhoang-linkedin-scraper/minhhoang-private-proxy/server.js`

```js
const express = require("express");
const { createProxyMiddleware } = require("http-proxy-middleware");

const app = express();
const PORT = process.env.PORT || 18080;

app.use((req, res, next) => {
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Credentials", "true");
  res.setHeader(
    "Access-Control-Allow-Methods",
    "GET,POST,PUT,PATCH,DELETE,OPTIONS",
  );
  res.setHeader(
    "Access-Control-Allow-Headers",
    "Content-Type, Authorization, X-API-Key, X-Requested-With",
  );
  if (req.method === "OPTIONS") return res.sendStatus(204);
  next();
});

// API: rewrite bo /minhhoang-scraper/api
app.use(
  createProxyMiddleware({
    target: "http://127.0.0.1:8101",
    changeOrigin: true,
    pathFilter: (path) => path.startsWith("/minhhoang-scraper/api"),
    pathRewrite: { "^/minhhoang-scraper/api": "" },
  }),
);

// Frontend: GIU NGUYEN duong dan /minhhoang-scraper/*
app.use(
  createProxyMiddleware({
    target: "http://127.0.0.1:3101",
    changeOrigin: true,
    pathFilter: (path) =>
      path.startsWith("/minhhoang-scraper") &&
      !path.startsWith("/minhhoang-scraper/api"),
  }),
);

app.listen(PORT, "0.0.0.0", () => {
  console.log(`minhhoang-private-proxy listening on :${PORT}`);
});
```

Quan trong:

- Khong dung `app.use("/minhhoang-scraper", proxy)` neu muon giu nguyen path, vi Express se cat prefix truoc khi forward.
- Bat buoc listen `0.0.0.0` neu can truy cap tu may khac trong LAN.
- Khong them redirect tay `/minhhoang-scraper -> /minhhoang-scraper/` trong proxy neu da co redirect tu Next, de tranh `ERR_TOO_MANY_REDIRECTS`.

API Playwright lau (comment/reaction pending nhieu phut) — tang timeout proxy (tuy chon):

```js
createProxyMiddleware({
  target: "http://127.0.0.1:8101",
  changeOrigin: true,
  proxyTimeout: 600000,
  timeout: 600000,
  pathFilter: (path) => path.startsWith("/minhhoang-scraper/api"),
  pathRewrite: { "^/minhhoang-scraper/api": "" },
}),
```

## 8) Build frontend dung cach (tranh mat CSS/chunk)

```bash
cd /opt/apps/minhhoang-linkedin-scraper/linkedin-crawler-ui
rm -rf .next
npm run build
mkdir -p .next/standalone/.next
rm -rf .next/standalone/.next/static
cp -r .next/static .next/standalone/.next/static
[ -d public ] && { rm -rf .next/standalone/public; cp -r public .next/standalone/public; } || true
pm2 restart minhhoang-frontend --update-env
pm2 save
```

Sau khi sua `NEXT_PUBLIC_*`: **bat buoc** `npm run build` lai tren VM (gia tri bake vao JS).

## 9) Healthcheck nhanh sau deploy (pass/fail)

```bash
curl -s -o /dev/null -w "backend=%{http_code}\n" http://127.0.0.1:8101/health
curl -s -o /dev/null -w "direct=%{http_code}\n" http://127.0.0.1:3101/minhhoang-scraper/quan-ly-nhom
curl -s -o /dev/null -w "root=%{http_code}\n" http://127.0.0.1:18080/minhhoang-scraper
curl -s -o /dev/null -w "home=%{http_code}\n" http://127.0.0.1:18080/minhhoang-scraper/
curl -s -o /dev/null -w "page=%{http_code}\n" http://127.0.0.1:18080/minhhoang-scraper/quan-ly-nhom
curl -s -o /dev/null -w "api=%{http_code}\n" http://127.0.0.1:18080/minhhoang-scraper/api/health
```

Gia tri pass:

- `backend=200`
- `direct=200`
- `root=200`
- `home=308` (redirect hop le)
- `page=200`
- `api=200`

## 10) Xu ly su co thuong gap

1. `Connection refused` tu may local vao `:18080`

- Kiem tra proxy listen `0.0.0.0:18080`:
  ```bash
  ss -ltnp | rg 18080
  ```
- Mo firewall:
  ```bash
  sudo ufw allow 18080/tcp
  ```

2. `api=200` nhung `page=404`

- Loi mapping prefix cua proxy.
- Dung lai file `server.js` theo muc 6 va restart `minhhoang-proxy`.

3. `backend errored` voi `venv/bin/activate: No such file`

- VM dang dung `.venv`, khong phai `venv`.
- Sua PM2 command backend theo muc 5.

4. Sau pull/build thay doi nhung UI khong cap nhat

- Hard refresh trinh duyet: `Ctrl + F5`.
- Rebuild frontend theo muc 7.

5. `minhhoang-frontend` errored — `Cannot find module .../.next/standalone/server.js`

- `next.config.ts` phai co `output: "standalone"` (khong dung `output: "export"`).
- Chay lai muc 7 (build), roi `pm2 delete minhhoang-frontend` va start lai theo muc 5.
- Kiem tra file ton tai: `test -f linkedin-crawler-ui/.next/standalone/server.js && echo OK`.

6. `page=200` nhung `api=504` — backend treo / crash loop (↺ tang, CPU 100%)

- Test truc tiep (bo proxy):
  ```bash
  curl -s -o /dev/null -w "backend_direct=%{http_code}\n" http://127.0.0.1:8101/health
  pm2 logs minhhoang-backend --lines 80 --nostream
  ```
- Thuong do Playwright Chromium khoi dong loi tren VM. Trong `.env`:
  ```env
  PLAYWRIGHT_WARMUP_ON_STARTUP=false
  ```
  Sau do `pm2 restart minhhoang-backend --update-env` — `/health` phai `200` ngay.
- Cai browser Playwright (neu thieu):
  ```bash
  cd /opt/apps/minhhoang-linkedin-scraper/linkedin_group_crawler
  source .venv/bin/activate
  playwright install chromium
  ```
- Pull ban moi: warmup Playwright chay **nen** sau khi API listen (khong chan `/health`).

7. **Comment/reaction pending lau / khong thay log API**

- Network `pending` = request da gui; log `POST /linkedin/post/react` thuong chi hien **sau** khi Playwright xong (co the 1–5 phut).
- FE goi dung URL: `http://10.30.50.29:18080/minhhoang-scraper/api/linkedin/post/...` (khong phai `127.0.0.1:8000` tren may client).
- Popup thanh cong **truoc** khi API xong (optimistic UI) — doi hoac xem `pm2 logs minhhoang-backend`.
- Tang `PLAYWRIGHT_POOL_SIZE` neu RAM du; dung `pm2 stop` app khac khi test.

8. **Session / tab moi ve login**

- File: `storage/session/{email_slug}.json` (email `user@gmail.com` → `user_gmail_com.json`).
- Request can `Email_crawl` / `session_id` **khop** file. Kiem tra `li_at`:

```bash
cd /opt/apps/minhhoang-linkedin-scraper/linkedin_group_crawler
ls -la storage/session/
python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print('li_at OK:', any(c.get('name')=='li_at' and c.get('value') for c in d.get('cookies',[])))" storage/session/FILE.json
```

- Login lai: `POST /login` + `force_relogin=true` (xem muc **15** neu can VNC).
- Sau login thanh cong, API tu dong **prime pool** (`prime_pool=true`, mac dinh): nap `storage/session/*.json` len **tat ca** worker `PLAYWRIGHT_POOL_SIZE` — react/comment khong bi bat dang nhap lan dau tren tung browser.
- Response co `playwright_pool_primed_workers` / `playwright_pool_workers` (vd. `3/3`). Neu `0/3`, xem log va login lai.
- Chi nap lai pool khong login LinkedIn: `force_relogin=false`, `prime_pool=true`.
- Code moi: sau `goto` tu **chon tab LinkedIn da login** neu LinkedIn mo tab login.
- Trang guest `linkedin.com/` (Welcome…) duoc coi la chua login; neu co `li_at` se thu mo `/feed/` mot lan truoc khi bao loi.
- API react/comment **uu tien Email_crawl** (khong dung email dashboard khac file session).

## 11) Vi tri file quan trong

- Backend env: `/opt/apps/minhhoang-linkedin-scraper/linkedin_group_crawler/.env`
- Frontend env: `/opt/apps/minhhoang-linkedin-scraper/linkedin-crawler-ui/.env.local`
- Frontend config: `/opt/apps/minhhoang-linkedin-scraper/linkedin-crawler-ui/next.config.ts`
- Proxy config: `/opt/apps/minhhoang-linkedin-scraper/minhhoang-private-proxy/server.js`
- PM2 dump: `/home/vmadmin/.pm2/dump.pm2`

- Session Playwright: `linkedin_group_crawler/storage/session/`
- Module pool: `app/services/playwright_browser_pool.py`
- Module session/nav: `app/services/linkedin_session_nav.py`
- Reaction timing: `app/services/post_reaction_service.py`

## 12) Ghi chu Python 3.8

VM dang chay Python 3.8, da fix:

- `from typing import Annotated` -> `from typing_extensions import Annotated`
- `@dataclass(slots=True)` -> `@dataclass`

Khuyen nghi dai han: nang cap Python 3.10+.

---

## 13) Tinh nang moi (2026-05)

### Dong bo tien do bai (`sync-progress`)

- `POST /linkedin/post/sync-progress` — Playwright mo **truc tiep URL bai**, doc reaction + comment (marker You/Bạn) + so like/comment.
- Frontend: sau popup thanh cong (comment/reaction), nut OK goi sync; slug lay tu **sheet** (`kpi/get-by-email` hoac cot `profile_slug` tren dong), **khong** qua `/linkedin/me/profile-slug` (tranh vao `/in/me` thua).
- Service: `app/services/sync_progress_service.py`.

### KPI & leader (`/admin/team`)

- Leader: `POST /kpi/get-all` → lay member; moi member `POST /get-all-posts` rieng → gop feed tinh KPI thuc te.
- `POST /kpi/assign`, `POST /kpi/get-by-email`, `POST /team/add-member`, `POST /auth/check-permission`.
- UI: `linkedin-crawler-ui/app/(dashboard)/admin/team` — chi role `leader`.

### Member dashboard

- `LinkedInStats`: KPI tuan + actuals tu `get-all-posts` (email dang nhap).
- Leader vao home LinkedIn → redirect `/admin/team`.

---

### Frontend engagement (optimistic UI)

- Popup reaction/comment thanh cong hien **ngay**; Playwright + webhook chay **nen**.
- API goi ngay khi bam (khong xep hang FIFO toan cuc nhu truoc).
- Nut OK popup **chi dong popup**, khong bat dau API.
- Badge `Nen: N tac vu` khi con sync/refresh trong hang doi.

---

## 14) Cau hinh webhook n8n (.env)

Mau bien: [.env.example](.env.example). **Khong commit** `.env` that.

| Bien | Ghi chu |
|------|---------|
| `N8N_WEBHOOK_URL` | Credentials → `/n8n/webhook-credentials` (**khong** dung ten `N8N_WEBHOOK`) |
| `N8N_WEBHOOK_START` | `POST /start` |
| `N8N_WEBHOOK_GET_ALL_POSTS` | `get-all-posts` + `filter-data` |
| `N8N_WEBHOOK_REACTION` | Reaction, sync-progress, sync-all (ghi sheet) |
| `N8N_WEBHOOK_GET_ALL_KPI` / `N8N_WEBHOOK_GET_KPI_BY_EMAIL` / `N8N_WEBHOOK_ASSIGN_KPI` | **URL rieng** tren n8n (khong copy chung 1 webhook neu workflow khac nhau) |
| `N8N_CHECK_PERMISSION` vs `N8N_WEBHOOK_ADD_MEMBER` | **Khong trung URL** — body khac nhau (`email` vs `email_member`+`email_leader`) |
| `LEADER_CODE` | Xac nhan leader tren UI |

Sau sua `.env` tren VM: `pm2 restart minhhoang-backend --update-env`.

---

## 15) Debug Playwright bang RealVNC (VM khong co man hinh that)

Dung khi can **nhin Chromium**, login thu cong, OTP, hoac debug reaction/comment.

### A. Cai dat display ao + VNC (chay tren VM, mot lan hoac sau reboot)

```bash
sudo apt-get update -y
sudo apt-get install -y xvfb x11vnc fluxbox

pkill -f x11vnc || true
pkill -f fluxbox || true
pkill -f "Xvfb :99" || true

/usr/bin/Xvfb :99 -screen 0 1366x768x24 -ac >/tmp/xvfb.log 2>&1 &
sleep 2
DISPLAY=:99 /usr/bin/fluxbox >/tmp/fluxbox.log 2>&1 &
sleep 1
/usr/bin/x11vnc -display :99 -forever -shared -rfbport 5900 -nopw -listen 0.0.0.0 >/tmp/x11vnc.log 2>&1 &
sleep 2
ss -ltnp | grep 5900
```

Kiem tra: co dong `LISTEN ... 5900` va log `The VNC desktop is`.

### B. Ket noi RealVNC tu Windows

**Cach 1 — SSH tunnel (khuyen nghi, tranh firewall port 5900):**

Tren **may Windows** (CMD/PowerShell rieng — **khong** chay trong SSH session `vmadmin@web`):

```bash
ssh -N -L 5901:127.0.0.1:5900 vmadmin@10.30.50.29
```

- Nhap password SSH xong cua so **im lang** = tunnel dang chay — **khong dong**.
- Mo **RealVNC Viewer** → connect: **`127.0.0.1:5901`**

**Cach 2 — Truc tiep LAN** (neu port 5900 mo):

- RealVNC → **`10.30.50.29:5900`**
- Neu timeout: dung Cach 1 hoac `sudo ufw allow 5900/tcp`

**Lu y RealVNC Connect:** Add device / nhap thang `IP:port` (direct), khong chi tim tren cloud.

### C. Backend hien browser tren VNC (`:99`)

Trong `.env`:

```env
HEADLESS=false
```

Start backend **kem** `DISPLAY=:99` (quan trong — chi `HEADLESS=false` khong du):

```bash
pm2 delete minhhoang-backend || true
pm2 start "bash -lc 'cd /opt/apps/minhhoang-linkedin-scraper/linkedin_group_crawler && source .venv/bin/activate && export DISPLAY=:99 && set -a && source .env && set +a && python -m uvicorn app.main:app --host 127.0.0.1 --port 8101'" --name minhhoang-backend
pm2 save
```

Kiem tra: `curl -s http://127.0.0.1:8101/status` → `"headless":false`.

### D. Login LinkedIn qua API (mo browser tren VNC)

```bash
curl -X POST "http://10.30.50.29:18080/minhhoang-scraper/api/login" \
  -H "Content-Type: application/json" \
  -H "x-api-key: secret_api_key" \
  -d '{"email":"EMAIL_CUA_BAN","password":"MAT_KHAU","force_relogin":true}'
```

- Neu can OTP: dung `session_id` pending → `POST /verify`.
- Sau login: file `storage/session/{email_slug}.json` co cookie `li_at`.

### E. Debug reaction/comment

1. VNC dang mo + backend `DISPLAY=:99`, `HEADLESS=false`.
2. UI gui reaction → xem Chromium tren VNC (hover menu → chon Like/Love).
3. Log realtime: `pm2 logs minhhoang-backend --lines 0`
4. Xong debug: dat lai `HEADLESS=true`, start backend muc **6** (khong can `DISPLAY`).

### F. Xử lý lỗi VNC thường gặp

| Lỗi | Cách xử lý |
|-----|------------|
| `XOpenDisplay(:99) failed` | Chay lai block muc **A** (Xvfb truoc, x11vnc sau) |
| `Connection refused` voi `127.0.0.1:5901` | Tunnel SSH chua chay hoac chay nham tren VM thay vi Windows |
| `Timed out` voi `10.30.50.29:5900` | Dung SSH tunnel |
| VNC den nhung khong thay browser | `HEADLESS=true` hoac thieu `DISPLAY=:99` tren PM2 |

---

## 16) Deploy nhanh sau `git pull`

```bash
cd /opt/apps/minhhoang-linkedin-scraper
git pull origin main

cd linkedin_group_crawler
# cap nhat .env theo muc 5 neu can
pm2 restart minhhoang-backend --update-env

cd ../linkedin-crawler-ui
npm ci
rm -rf .next
npm run build
mkdir -p .next/standalone/.next
cp -r .next/static .next/standalone/.next/static
pm2 restart minhhoang-frontend --update-env

curl -s -o /dev/null -w "api=%{http_code}\n" http://127.0.0.1:18080/minhhoang-scraper/api/health
```

---

## 17) Frontend local (tham khao)

```bash
cd linkedin-crawler-ui
npm install
npm run dev
```

`.env.local`:

```env
NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL=http://127.0.0.1:8000
NEXT_PUBLIC_LINKEDIN_CRAWLER_API_KEY=<cung API_KEY backend>
```

Production qua proxy: xem muc 3 (`basePath` `/minhhoang-scraper`).

---

## Tom tat thay doi code (2026-05)

| Phan | Mo ta |
|------|--------|
| Playwright pool | `PLAYWRIGHT_POOL_SIZE` — nhieu browser/worker song song |
| Reaction | Settle lau hon, click trong flyout, verify + retry |
| Session | `linkedin_session_nav.py` — validate `li_at`, chon tab da login |
| Login / verify | Sau thanh cong: `prime_linkedin_session_on_pool` — nap session len moi worker |
| Sync-progress | Dung chung pool (khong mo browser rieng moi lan) |
| FE | Optimistic UI; API reaction/comment goi ngay |
| Startup | Playwright warmup nen (khong chan `/health`) |
