#!/usr/bin/env bash
set -euo pipefail

export DISPLAY="${DISPLAY:-:99}"
export ZALO_BROWSER_HEADLESS="${ZALO_BROWSER_HEADLESS:-false}"
export ZALO_BROWSER_PERSISTENT_PROFILE="${ZALO_BROWSER_PERSISTENT_PROFILE:-true}"
export ZALO_BROWSER_USER_DATA_DIR="${ZALO_BROWSER_USER_DATA_DIR:-/app/storage/chromium-profile}"
export ZALO_VNC_ENABLED="${ZALO_VNC_ENABLED:-true}"
export ZALO_AUTO_OPEN_ON_START="${ZALO_AUTO_OPEN_ON_START:-false}"
export ZALO_AUTO_OPEN_URL="${ZALO_AUTO_OPEN_URL:-https://chat.zalo.me/}"
export ZALO_VNC_ALLOW_NO_PASSWORD="${ZALO_VNC_ALLOW_NO_PASSWORD:-false}"

mkdir -p /tmp/.X11-unix /app/storage/chromium-profile
chmod 1777 /tmp/.X11-unix 2>/dev/null || true

DISPLAY_NUM="${DISPLAY#:}"
rm -f "/tmp/.X${DISPLAY_NUM}-lock" "/tmp/.X11-unix/X${DISPLAY_NUM}"

Xvfb "${DISPLAY}" -screen 0 1366x768x24 -ac +extension GLX +render -noreset >/tmp/xvfb.log 2>&1 &
XVFB_PID="$!"

for _ in $(seq 1 30); do
  if [[ -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]]; then
    break
  fi
  if ! kill -0 "${XVFB_PID}" 2>/dev/null; then
    echo "[start_zalo_vnc] Xvfb exited before creating display ${DISPLAY}" >&2
    cat /tmp/xvfb.log >&2 || true
    exit 1
  fi
  sleep 0.2
done

if [[ ! -S "/tmp/.X11-unix/X${DISPLAY_NUM}" ]]; then
  echo "[start_zalo_vnc] Xvfb did not create display socket ${DISPLAY}" >&2
  cat /tmp/xvfb.log >&2 || true
  exit 1
fi

if [[ "${ZALO_VNC_ENABLED}" == "true" ]]; then
  fluxbox >/tmp/fluxbox.log 2>&1 &
  if [[ -n "${ZALO_VNC_PASSWORD:-}" ]]; then
    x11vnc -display "${DISPLAY}" -forever -shared -rfbport 5900 -passwd "${ZALO_VNC_PASSWORD}" -listen 0.0.0.0 >/tmp/x11vnc.log 2>&1 &
  elif [[ "${ZALO_VNC_ALLOW_NO_PASSWORD}" == "true" ]]; then
    x11vnc -display "${DISPLAY}" -forever -shared -rfbport 5900 -nopw -listen 0.0.0.0 >/tmp/x11vnc.log 2>&1 &
  else
    echo "[start_zalo_vnc] ZALO_VNC_PASSWORD is required when ZALO_VNC_ENABLED=true. Set ZALO_VNC_ALLOW_NO_PASSWORD=true only for local debugging." >&2
    exit 1
  fi

  NOVNC_WEB="/usr/share/novnc"
  if [[ -d "/usr/share/novnc" ]]; then
    websockify --web "${NOVNC_WEB}" 6080 0.0.0.0:5900 >/tmp/novnc.log 2>&1 &
  fi
fi

if [[ "${ZALO_VNC_ENABLED}" == "true" && "${ZALO_AUTO_OPEN_ON_START}" == "true" ]]; then
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

exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
