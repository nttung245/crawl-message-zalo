#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
export ZALO_BROWSER_HEADLESS="${ZALO_BROWSER_HEADLESS:-false}"
export ZALO_BROWSER_PERSISTENT_PROFILE="${ZALO_BROWSER_PERSISTENT_PROFILE:-true}"
export ZALO_BROWSER_USER_DATA_DIR="${ZALO_BROWSER_USER_DATA_DIR:-/app/storage/chromium-profile}"
export ZALO_AUTO_OPEN_ON_START="${ZALO_AUTO_OPEN_ON_START:-true}"
export ZALO_AUTO_OPEN_URL="${ZALO_AUTO_OPEN_URL:-https://chat.zalo.me/}"

mkdir -p /tmp/.X11-unix /app/storage/chromium-profile

Xvfb "${DISPLAY}" -screen 0 1366x768x24 -ac +extension GLX +render -noreset &
sleep 1

fluxbox >/tmp/fluxbox.log 2>&1 &
x11vnc -display "${DISPLAY}" -forever -shared -rfbport 5900 -nopw -listen 0.0.0.0 >/tmp/x11vnc.log 2>&1 &

NOVNC_WEB="/usr/share/novnc"
if [[ -d "/usr/share/novnc" ]]; then
  websockify --web "${NOVNC_WEB}" 6080 0.0.0.0:5900 >/tmp/novnc.log 2>&1 &
fi

if [[ "${ZALO_AUTO_OPEN_ON_START}" == "true" ]]; then
  CHROME_BIN="$(ls -1 /ms-playwright/chromium-*/chrome-linux*/chrome 2>/dev/null | head -n 1 || true)"
  if [[ -n "${CHROME_BIN}" ]]; then
    mkdir -p /tmp/novnc-welcome-profile
    "${CHROME_BIN}" \
      --no-sandbox \
      --disable-dev-shm-usage \
      --disable-gpu \
      --no-first-run \
      --no-default-browser-check \
      --window-size=1280,900 \
      --user-data-dir=/tmp/novnc-welcome-profile \
      "${ZALO_AUTO_OPEN_URL}" >/tmp/novnc-browser.log 2>&1 &
  else
    echo "[start_zalo_vnc] Chromium binary not found under /ms-playwright; skip auto-open" >&2
  fi
fi

exec uvicorn app.main:app --host 0.0.0.0 --port 8000
