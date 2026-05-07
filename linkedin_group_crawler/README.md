# LinkedIn Group Crawler - Runbook

## Chay local nhanh

```bash
py -3 -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Deploy tren VM dung chung (ban da fix on dinh)

### 1) Vi tri source code tren VM

- Monorepo: `/opt/apps/minhhoang-linkedin-scraper`
- Backend: `/opt/apps/minhhoang-linkedin-scraper/linkedin_group_crawler`
- Frontend: `/opt/apps/minhhoang-linkedin-scraper/linkedin-crawler-ui`

### 2) Vi tri file cau hinh quan trong

- Nginx he thong (shared, khong con la duong chinh cua MinhHoang): `/etc/nginx/sites-available/*`, `/etc/nginx/sites-enabled/*`
- Backend env: `/opt/apps/minhhoang-linkedin-scraper/linkedin_group_crawler/.env`
- Frontend env: `/opt/apps/minhhoang-linkedin-scraper/linkedin-crawler-ui/.env.local`
- Frontend Next config: `/opt/apps/minhhoang-linkedin-scraper/linkedin-crawler-ui/next.config.ts`
- Private proxy code (rieng MinhHoang): `/opt/apps/minhhoang-linkedin-scraper/minhhoang-private-proxy/server.js`
- Private proxy package: `/opt/apps/minhhoang-linkedin-scraper/minhhoang-private-proxy/package.json`
- PM2 process dump: `/home/vmadmin/.pm2/dump.pm2`
- PM2 logs:
  - `/home/vmadmin/.pm2/logs/minhhoang-backend-out.log`
  - `/home/vmadmin/.pm2/logs/minhhoang-backend-error.log`
  - `/home/vmadmin/.pm2/logs/minhhoang-frontend-out.log`
  - `/home/vmadmin/.pm2/logs/minhhoang-frontend-error.log`
  - `/home/vmadmin/.pm2/logs/minhhoang-proxy-out.log`
  - `/home/vmadmin/.pm2/logs/minhhoang-proxy-error.log`

### 3) Port va URL namespace rieng (tranh xung dot)

- Frontend process: `127.0.0.1:3101`
- Backend process: `127.0.0.1:8101`
- Private proxy process: `0.0.0.0:18080` (PM2 app: `minhhoang-proxy`)
- URL frontend (chinh thuc): `http://10.30.50.29:18080/minhhoang-scraper` (khong them `/` o cuoi)
- URL frontend page quan ly nhom: `http://10.30.50.29:18080/minhhoang-scraper/quan-ly-nhom`
- URL backend docs (chinh thuc): `http://10.30.50.29:18080/minhhoang-scraper/api/docs`

### 4) Cau hinh frontend bat buoc (sub-path)

Trong `next.config.ts` can co:

```ts
basePath: "/minhhoang-scraper",
assetPrefix: "/minhhoang-scraper",
```

Trong `.env.local` can co:

```env
NEXT_PUBLIC_LINKEDIN_CRAWLER_API_URL=http://10.30.50.29:18080/minhhoang-scraper/api
NEXT_PUBLIC_LINKEDIN_CRAWLER_API_KEY=secret_api_key
```

Luu y:
- FE dang mo qua `:18080` thi API URL phai cung origin `:18080` de tranh CORS.

### 5) Lenh quan ly PM2

```bash
pm2 status
pm2 restart minhhoang-frontend --update-env
pm2 restart minhhoang-backend --update-env
pm2 restart minhhoang-proxy --update-env
pm2 logs minhhoang-frontend --lines 120
pm2 logs minhhoang-backend --lines 120
pm2 logs minhhoang-proxy --lines 120
pm2 save
```

Frontend dang dung `output: "standalone"`, lenh chay dung la:

```bash
pm2 delete minhhoang-frontend || true
pm2 start "node .next/standalone/server.js" --name minhhoang-frontend --cwd /opt/apps/minhhoang-linkedin-scraper/linkedin-crawler-ui
pm2 save
```

### 6) Lenh verify sau moi lan deploy

```bash
curl -I http://127.0.0.1:3101/minhhoang-scraper
curl -I http://127.0.0.1:8101/docs
curl -I http://127.0.0.1:18080/healthz
curl -I http://127.0.0.1:18080/minhhoang-scraper
curl -I http://127.0.0.1:18080/minhhoang-scraper/quan-ly-nhom
curl -I http://127.0.0.1:18080/minhhoang-scraper/api/docs
```

Ky vong:
- `/healthz` -> `200`
- `/minhhoang-scraper` -> `200`
- `/minhhoang-scraper/api/docs` -> `200`
- PM2: `minhhoang-frontend`, `minhhoang-backend`, `minhhoang-proxy` deu `online`

### 7) Trang thai Nginx va pham vi anh huong

Duong vao chinh thuc cua MinhHoang hien tai la private proxy `:18080`, KHONG phu thuoc route Nginx shared.

Nginx shared van co the duoc nhieu nguoi sua, nhung khong anh huong den URL rieng:

- `http://10.30.50.29:18080/minhhoang-scraper`

Lenh kiem tra nhanh:

```bash
curl -I http://127.0.0.1:18080/healthz
curl -I http://127.0.0.1:18080/minhhoang-scraper/api/docs
```

Luu y quan trong:
- Neu ai do co quyen `sudo/root` tren VM, ho van co the sua PM2 process hoac file cua ban.
- "Khong anh huong nhau" o day duoc dam bao o muc van hanh: tach cong `18080`, tach process `minhhoang-proxy`, khong dung route Nginx chung.

### 8) DNS loi tren VM (thuong gap)

Neu `Could not resolve host` khi `git pull` hoac `pip install`:

```bash
echo -e "nameserver 8.8.8.8\nnameserver 1.1.1.1" | sudo tee /etc/resolv.conf
ping -c 2 github.com
ping -c 2 pypi.org
```

### 9) Ghi chu tuong thich Python 3.8

VM dang dung Python 3.8, da can fix:

- `from typing import Annotated` -> `from typing_extensions import Annotated`
- `@dataclass(slots=True)` -> `@dataclass`
- Can package: `eval_type_backport`, `typing_extensions`

Khuyen nghi dai han: nang cap Python 3.10+ de tranh loi typing/pydantic.