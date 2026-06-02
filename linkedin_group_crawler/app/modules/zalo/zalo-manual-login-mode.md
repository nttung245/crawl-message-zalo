# Zalo Manual Login Mode (noVNC)

## Mục tiêu
- Dùng 1 flow đăng nhập thủ công qua giao diện Zalo Web trong noVNC.
- Tránh lỗi popup đồng bộ tin nhắn khi auto QR.
- Giữ session để crawl lại không cần login mỗi lần.

## Những gì đã implement
- Backend:
  - `POST /api/zalo/auth/manual-login/start`
  - `POST /api/zalo/auth/manual-login/resume`
  - `GET /api/zalo/auth/current-status` trả thêm `manual_viewer_url`.
  - Browser Zalo không còn bị ép headless trong Docker nếu `ZALO_BROWSER_HEADLESS=false`.
- Frontend:
  - Nút `Mở màn hình Zalo`.
  - Nút `Tiếp tục crawl`.
  - Link `Mở noVNC`.
  - UI tối giản theo flow manual login.
  - Job `running` có loading animation, `queued` có pulse.
- Docker:
  - `Dockerfile.vnc`: image có `Xvfb + x11vnc + noVNC`.
  - `scripts/start_zalo_vnc.sh`: start display + VNC + API trong 1 container.
  - `docker-compose.zalo-vnc.yml`: chạy service `zalo-api-vnc`.

## File chính
- `Dockerfile.vnc`
- `docker-compose.zalo-vnc.yml`
- `scripts/start_zalo_vnc.sh`
- `app/modules/zalo/api/routes/auth.py`
- `app/modules/zalo/crawler/browser.py`

## Cấu hình env cần có
Trong `.env` của backend:

```env
ZALO_BROWSER_HEADLESS=false
ZALO_BROWSER_PERSISTENT_PROFILE=true
ZALO_BROWSER_USER_DATA_DIR=/app/storage/chromium-profile
ZALO_BROWSER_REMOTE_VIEWER_URL=http://127.0.0.1:6080/vnc.html?autoconnect=true&reconnect=true&resize=scale&show_dot=true
ZALO_VNC_PASSWORD=<strong-vnc-password>
ZALO_API_BIND=127.0.0.1
ZALO_VNC_BIND=127.0.0.1
ZALO_NOVNC_BIND=127.0.0.1
```

Ghi chú:
- `ZALO_BROWSER_REMOTE_VIEWER_URL` là URL FE dùng để mở noVNC.
- Nếu chạy local: `http://localhost:6080/vnc.html`.

## Cách chạy bằng Docker Compose
Tại thư mục `linkedin_group_crawler`:

```bash
docker compose -f docker-compose.zalo-vnc.yml up -d --build
```

Default bind:
- API: `127.0.0.1:8000`
- noVNC: `127.0.0.1:6080`
- VNC raw: `127.0.0.1:5900`

## Flow test trên FE
1. Vào trang Zalo crawl trên FE.
2. Bấm `Mở màn hình Zalo`.
3. Trong noVNC: login Zalo + xử lý popup đồng bộ.
4. Quay lại FE bấm `Tiếp tục crawl`.
5. Khi trạng thái `Đã đăng nhập`, nhập group + tab sheet.
6. Bấm `Chạy Crawl`.

## Lưu ý vận hành
- Bắt buộc mount volume `./storage:/app/storage` để giữ profile/session.
- Không xóa volume `storage` nếu muốn giữ login.
- Nếu noVNC mở được nhưng không thấy browser:
  - kiểm tra `ZALO_BROWSER_HEADLESS=false`
  - kiểm tra log container:
    - `docker logs zalo-api-vnc --tail 200`

## Lệnh hữu ích
```bash
docker compose -f docker-compose.zalo-vnc.yml ps
docker compose -f docker-compose.zalo-vnc.yml logs -f
docker compose -f docker-compose.zalo-vnc.yml restart
docker compose -f docker-compose.zalo-vnc.yml down
```

