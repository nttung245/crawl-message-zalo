"""Forward crawl credentials to n8n webhook (e.g. to trigger Email node).

Tất cả lời gọi POST webhook n8n đều đi qua ``_post_with_retry`` để xử lý
lỗi DNS / mạng tạm thời — retry tối đa ``MAX_WEBHOOK_RETRIES`` lần với
backoff tăng dần.
"""

from __future__ import annotations

import json
import re
import time
from typing import Any

import httpx

from app.core.config import settings
from app.core.logger import get_logger


logger = get_logger(__name__)

# ── Retry config cho mọi lời gọi webhook n8n ──────────────────────────────
MAX_WEBHOOK_RETRIES: int = 5
"""Số lần thử lại tối đa khi gặp lỗi mạng / DNS."""
_RETRY_BACKOFF_BASE_SEC: float = 2.0
"""Thời gian chờ giữa các lần retry = _RETRY_BACKOFF_BASE_SEC * attempt."""

# Các exception httpx xảy ra ở tầng connect/DNS — luôn nên retry.
_RETRYABLE_EXCEPTIONS: tuple[type[Exception], ...] = (
    httpx.ConnectError,      # DNS resolution failure, connection refused
    httpx.ConnectTimeout,    # connect phase timeout (DNS chậm)
    httpx.PoolTimeout,       # connection pool exhausted
)


def _post_with_retry(
    *,
    url: str,
    json_body: Any,
    timeout: httpx.Timeout | float,
    max_retries: int = MAX_WEBHOOK_RETRIES,
) -> httpx.Response:
    """POST JSON tới URL với retry khi gặp lỗi mạng/DNS.

    - **Chỉ retry** cho ``ConnectError``, ``ConnectTimeout``, ``PoolTimeout``
      (tức lỗi ở tầng connect/DNS — request chưa được gửi đi).
    - **KHÔNG retry** cho ``ReadTimeout`` hay HTTP status lỗi — vì request
      đã gửi thành công, retry có thể gây duplicate side-effect.
    - Backoff tăng dần: 2s → 4s → 6s → 8s → ...

    Raises:
        Ngoại lệ cuối cùng nếu hết retry.
    """

    last_exc: Exception | None = None
    for attempt in range(1, max_retries + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                return client.post(url, json=json_body)
        except _RETRYABLE_EXCEPTIONS as exc:
            last_exc = exc
            if attempt < max_retries:
                wait = _RETRY_BACKOFF_BASE_SEC * attempt
                logger.warning(
                    "n8n webhook POST thất bại (attempt %d/%d, %s: %s) — retry sau %.1fs",
                    attempt,
                    max_retries,
                    type(exc).__name__,
                    str(exc)[:200],
                    wait,
                )
                time.sleep(wait)
            else:
                logger.error(
                    "n8n webhook POST thất bại sau %d lần thử (%s: %s)",
                    max_retries,
                    type(exc).__name__,
                    str(exc)[:200],
                )
    # Hết retry — raise lỗi cuối
    assert last_exc is not None
    raise last_exc



def push_credentials_to_n8n_webhook(*, email: str, password: str, max_post: int) -> tuple[int, str]:
    """POST JSON payload to configured n8n webhook URL.

    Returns HTTP status code and response text snippet (truncated). Does not log credentials.
    """

    url = (settings.n8n_webhook_url or "").strip()
    if not url:
        raise RuntimeError(
            "N8N_WEBHOOK_URL chưa được cấu hình trong biến môi trường (.env).",
        )

    payload: dict[str, Any] = {
        "email": email,
        # Tài khoản LinkedIn thường là email — để workflow n8n dễ map
        "tai_khoan": email,
        "password": password,
        "mat_khau": password,
        "max_post": max_post,
    }

    timeout = max(1.0, float(settings.n8n_webhook_timeout_sec))

    response = _post_with_retry(url=url, json_body=payload, timeout=timeout)

    text = (response.text or "").strip()
    if len(text) > 512:
        text = f"{text[:512]}…"

    logger.info(
        "n8n webhook responded status=%s (body length=%s)",
        response.status_code,
        len(response.text or ""),
    )

    response.raise_for_status()

    return response.status_code, text


def push_start_to_n8n_webhook(
    *,
    email: str,
    password: str,
    force_relogin: bool,
    id_session_crawl: str,
    max_posts: int | None = None,
    target_date: str | None = None,
    mode: str | None = None,
    delay_sec: int | None = None,
    group_urls: list[str] | None = None,
) -> tuple[int, str]:
    """POST ``email``, ``password``, ``force_relogin``, ``id_session_crawl`` tới webhook (``N8N_WEBHOOK_START``).

    Không log mật khẩu. Trả về HTTP status và đoạn body rút gọn.
    """

    url = (settings.n8n_webhook_start_url or "").strip()
    if not url:
        raise RuntimeError(
            "N8N_WEBHOOK_START chưa được cấu hình trong biến môi trường (.env).",
        )

    payload: dict[str, Any] = {
        "email": email,
        "password": password,
        "force_relogin": force_relogin,
        "id_session_crawl": id_session_crawl,
    }
    if max_posts is not None:
        payload["max_posts"] = int(max_posts)
    if target_date:
        payload["target_date"] = target_date
    if mode:
        payload["mode"] = mode
    if delay_sec is not None:
        payload["delay_sec"] = int(delay_sec)
    if group_urls is not None:
        payload["group_urls"] = list(group_urls)

    timeout_seconds = max(1.0, float(settings.n8n_webhook_start_timeout_sec))
    timeout = httpx.Timeout(timeout=timeout_seconds, connect=min(30.0, timeout_seconds))
    started_at = time.monotonic()
    logger.info(
        "Calling n8n start webhook with timeout_sec=%s",
        timeout_seconds,
    )
    response = _post_with_retry(url=url, json_body=payload, timeout=timeout)

    text = (response.text or "").strip()
    if len(text) > 512:
        text = f"{text[:512]}…"

    logger.info(
        "n8n start webhook responded status=%s (body length=%s, elapsed_sec=%.2f)",
        response.status_code,
        len(response.text or ""),
        time.monotonic() - started_at,
    )

    response.raise_for_status()

    return response.status_code, text


_SHEET_LINK_JSON_KEYS = (
    "sheet_link",
    "sheetLink",
    "sheet_url",
    "sheetUrl",
    "spreadsheet_url",
    "spreadsheetUrl",
    "url",
    "link",
    "webViewLink",
    "alternateLink",
)


def extract_sheet_link_from_n8n_response_body(raw: str) -> str | None:
    """Cố gắng lấy URL trang tính / Google Sheet từ body JSON hoặc chuỗi thuần."""

    text = (raw or "").strip()
    if not text:
        return None

    try:
        parsed: Any = json.loads(text)
    except json.JSONDecodeError:
        parsed = None

    if isinstance(parsed, dict):
        for key in _SHEET_LINK_JSON_KEYS:
            value = parsed.get(key)
            if isinstance(value, str):
                candidate = value.strip()
                if candidate.startswith(("http://", "https://")):
                    return candidate
        # Một số workflow trả về { "data": { "url": "..." } }
        nested = parsed.get("data")
        if isinstance(nested, dict):
            for key in _SHEET_LINK_JSON_KEYS:
                value = nested.get(key)
                if isinstance(value, str):
                    candidate = value.strip()
                    if candidate.startswith(("http://", "https://")):
                        return candidate
    elif isinstance(parsed, str) and parsed.startswith(("http://", "https://")):
        return parsed.strip()

    # Plain text: dòng đầu hoặc URL đầu tiên trong body
    for line in text.splitlines():
        line = line.strip().strip('"')
        if line.startswith(("http://", "https://")):
            return line.split()[0] if line.split() else line

    match = re.search(r"https?://[^\s\"'<>]+", text)
    if match:
        return match.group(0).rstrip(").,;")

    return None


def fetch_sheet_link_via_n8n_webhook(*, body: dict[str, Any] | None = None) -> tuple[int, str]:
    """POST JSON tới webhook lấy link sheet (URL trong N8n_WEBHOOK_GET_LINK / N8N_WEBHOOK_GET_LINK).

    Trả về (http_status, response_text_đầy_đủ) — không raise; caller xử lý lỗi HTTP.
    """

    url = (settings.n8n_webhook_get_link_url or "").strip()
    if not url:
        raise RuntimeError(
            "N8n_WEBHOOK_GET_LINK (hoặc N8N_WEBHOOK_GET_LINK) chưa được cấu hình trong .env.",
        )

    payload = dict(body) if body else {}
    timeout = max(1.0, float(settings.n8n_webhook_timeout_sec))

    response = _post_with_retry(url=url, json_body=payload, timeout=timeout)

    full_text = response.text or ""

    logger.info(
        "n8n get-sheet-link webhook status=%s (body length=%s)",
        response.status_code,
        len(full_text),
    )

    return response.status_code, full_text


def post_json_to_n8n_webhook(
    *,
    url: str,
    json_body: Any,
    timeout_sec: float | None = None,
) -> tuple[int, str]:
    """POST JSON tới một URL webhook n8n bất kỳ; trả về (status, body_text) — không raise HTTP.

    Chờ đến khi n8n/workflow trả HTTP response (timeout có thể tăng qua ``timeout_sec``).
    """

    target = (url or "").strip()
    if not target:
        raise RuntimeError("Webhook URL rỗng.")

    timeout_seconds = max(1.0, float(timeout_sec if timeout_sec is not None else settings.n8n_webhook_timeout_sec))
    timeout = httpx.Timeout(timeout=timeout_seconds, connect=min(30.0, timeout_seconds))
    payload: Any = json_body if json_body is not None else {}

    response = _post_with_retry(url=target, json_body=payload, timeout=timeout)

    full_text = response.text or ""

    logger.info(
        "n8n passthrough webhook status=%s (body length=%s)",
        response.status_code,
        len(full_text),
    )

    return response.status_code, full_text
