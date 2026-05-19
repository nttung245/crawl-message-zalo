"""Điều hướng Playwright + session LinkedIn — luồng đơn giản, ưu tiên ổn định."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import BrowserContext, Error, Page

from app.services.auth_service import (
    _context_has_li_at_cookie,
    _existing_state_is_reusable,
    _is_authwall_url,
    _is_linkedin_authenticated_app_url,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

_LINKEDIN_DESKTOP_UA: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"


def is_linkedin_login_url(url: str) -> bool:
    return _is_authwall_url(url)


def validate_storage_state_file(state_path: Path) -> None:
    if not state_path.is_file():
        raise FileNotFoundError(
            f"Không tìm thấy file session LinkedIn: {state_path}. "
            "Gọi POST /login (force_relogin=true).",
        )
    if not _existing_state_is_reusable(state_path):
        raise RuntimeError(
            f"File session {state_path} thiếu hoặc hết hạn cookie li_at — "
            "POST /login với email trùng Email_crawl, force_relogin=true."
        )


def linkedin_browser_context_options() -> dict[str, object]:
    return {
        "viewport": {"width": 1366, "height": 768},
        "locale": "en-US",
        "timezone_id": "Asia/Ho_Chi_Minh",
        "user_agent": _LINKEDIN_DESKTOP_UA,
    }


def _page_is_guest(page: Page) -> bool:
    url = (page.url or "").lower()
    if is_linkedin_login_url(url):
        return True
    try:
        if page.locator("header.global-nav").count() > 0:
            return False
        if "cold-join" in url or "/signup" in url:
            return True
    except Error:
        pass
    return False


def _session_not_authenticated_error(page: Page) -> RuntimeError:
    url = page.url or ""
    return RuntimeError(
        "LinkedIn chưa đăng nhập (login/guest/cold-join). "
        "Chạy POST /login với email trùng Email_crawl, force_relogin=true. "
        f"URL hiện tại: {url[:200]}"
    )


def ensure_context_loaded_session(context: BrowserContext, state_path: Path) -> None:
    if _context_has_li_at_cookie(context):
        return
    raise RuntimeError(
        f"Không nạp được cookie li_at từ {state_path.name}. POST /login lại (force_relogin=true)."
    )


def _open_feed_once(page: Page, *, timeout_ms: int, wait_ms: int) -> None:
    logger.info("Mở feed để xác nhận session (từ %s)", page.url)
    page.goto(_LINKEDIN_FEED_URL, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(wait_ms)


def goto_linkedin_url(
    context: BrowserContext,
    page: Page,
    url: str,
    *,
    timeout_ms: int = 300000,
    post_load_wait_ms: int = 800,
) -> Page:
    """Mở URL LinkedIn: một lần feed nếu bị redirect guest, không vòng lặp phức tạp."""

    target = (url or "").strip()
    wait_ms = max(post_load_wait_ms, 1200)

    page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(wait_ms)

    if not _page_is_guest(page) and not is_linkedin_login_url(page.url or ""):
        return page

    if not _context_has_li_at_cookie(context):
        raise _session_not_authenticated_error(page)

    _open_feed_once(page, timeout_ms=timeout_ms, wait_ms=wait_ms * 2)
    if _page_is_guest(page):
        raise _session_not_authenticated_error(page)

    page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
    page.wait_for_timeout(wait_ms)

    if _page_is_guest(page) or is_linkedin_login_url(page.url or ""):
        raise _session_not_authenticated_error(page)

    return page
