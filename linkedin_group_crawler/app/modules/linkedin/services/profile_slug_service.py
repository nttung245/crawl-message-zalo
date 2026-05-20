"""Lấy public profile slug của user đã đăng nhập qua menu Me / View profile."""

from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

from playwright.sync_api import Error, Page, sync_playwright

from app.core.config import settings
from app.modules.linkedin.services.auth_service import build_session_state_path
from app.modules.linkedin.services.crawler_service import _is_login_url
from app.core.logger import get_logger


logger = get_logger(__name__)

LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"
LINKEDIN_ME_REDIRECT_URL = "https://www.linkedin.com/in/me/"
LINKEDIN_ME_PAGE_URL = "https://www.linkedin.com/me/"

_ME_REDIRECT_POLL_SEC = 300.0


def _state_has_li_at_cookie(state_path: Path) -> bool:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        cookies = payload.get("cookies") if isinstance(payload, dict) else None
        if not isinstance(cookies, list):
            return False
        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            if str(cookie.get("name", "")).strip() == "li_at" and str(cookie.get("value", "")).strip():
                return True
        return False
    except Exception:
        logger.exception("Không đọc được state file %s", state_path)
        return False


def parse_profile_slug_from_href(href: str) -> tuple[str, str]:
    """Trả về (slug, profile_url chuẩn https://www.linkedin.com/in/<slug>/)."""

    raw = (href or "").strip()
    if not raw or raw.startswith("#"):
        raise ValueError(f"href profile không hợp lệ: {href!r}")

    absolute = urljoin("https://www.linkedin.com", raw)
    parsed = urlparse(absolute)
    if parsed.netloc and "linkedin.com" not in parsed.netloc.lower():
        raise ValueError(f"href không thuộc linkedin.com: {href}")

    match = re.match(r"^/in/([^/?#]+)", (parsed.path or "").strip(), re.I)
    if not match:
        raise ValueError(f"Không parse được slug từ href: {href}")

    slug = match.group(1).strip().rstrip("/")
    if not slug:
        raise ValueError(f"Slug rỗng sau khi parse href: {href}")

    profile_url = f"https://www.linkedin.com/in/{slug}/"
    return slug, profile_url


def _slug_tuple_from_page_url(page: Page) -> tuple[str, str] | None:
    """Lấy slug từ URL hiện tại nếu đã là profile ``/in/<slug>`` (không phải ``/in/me``)."""

    url = (page.url or "").strip()
    if _is_login_url(url) or "/company/" in url.lower():
        return None
    try:
        slug, profile_url = parse_profile_slug_from_href(url)
    except ValueError:
        return None
    if slug.lower() == "me":
        return None
    return slug, profile_url


def _try_resolve_slug_via_me_redirect(page: Page) -> tuple[str, str] | None:
    """LinkedIn thường redirect ``/in/me/`` → canonical ``/in/<public-id>/``."""

    page.goto(LINKEDIN_ME_REDIRECT_URL, wait_until="domcontentloaded", timeout=300000)
    try:
        page.wait_for_load_state("load", timeout=60000)
    except Error:
        logger.debug("/in/me load timeout; chờ redirect URL", exc_info=True)

    deadline = _ME_REDIRECT_POLL_SEC
    waited = 0.0
    step = 0.45
    while waited <= deadline:
        if _is_login_url(page.url):
            return None
        resolved = _slug_tuple_from_page_url(page)
        if resolved:
            return resolved
        page.wait_for_timeout(int(step * 1000))
        waited += step

    return None


def _try_resolve_slug_via_me_page(page: Page) -> tuple[str, str] | None:
    """Navigate thẳng tới ``/me/`` — LinkedIn redirect về ``/in/<slug>/``.

    Ổn định hơn cách dùng menu Me/Feed vì không phụ thuộc DOM nav bar.
    """

    page.goto(LINKEDIN_ME_PAGE_URL, wait_until="domcontentloaded", timeout=300000)
    try:
        page.wait_for_load_state("load", timeout=60000)
    except Error:
        logger.debug("/me/ load timeout; chờ redirect URL", exc_info=True)

    if _is_login_url(page.url):
        raise RuntimeError(
            "LinkedIn redirect sang login/checkpoint — session hết hạn hoặc không hợp lệ.",
        )

    # Chờ redirect /me/ → /in/<slug>/
    deadline = _ME_REDIRECT_POLL_SEC
    waited = 0.0
    step = 0.5
    while waited <= deadline:
        resolved = _slug_tuple_from_page_url(page)
        if resolved:
            return resolved
        # Kiểm tra login redirect giữa chừng
        if _is_login_url(page.url):
            return None
        page.wait_for_timeout(int(step * 1000))
        waited += step

    # Fallback: nếu URL vẫn không có slug, thử đọc canonical link hoặc
    # meta og:url từ page (LinkedIn thường đặt slug ở đó)
    try:
        canonical = page.locator('link[rel="canonical"]').first.get_attribute("href")
        if canonical:
            slug_result = _slug_tuple_from_url_string(canonical)
            if slug_result:
                return slug_result
    except Error:
        pass

    try:
        og_url = page.locator('meta[property="og:url"]').first.get_attribute("content")
        if og_url:
            slug_result = _slug_tuple_from_url_string(og_url)
            if slug_result:
                return slug_result
    except Error:
        pass

    return None


def _slug_tuple_from_url_string(url: str) -> tuple[str, str] | None:
    """Parse slug từ chuỗi URL (không cần Page object)."""
    try:
        slug, profile_url = parse_profile_slug_from_href(url)
        if slug.lower() == "me":
            return None
        return slug, profile_url
    except ValueError:
        return None


def get_my_profile_slug(*, session_id: str | None, email: str | None) -> tuple[str, str, str]:
    """Đọc slug profile của session hiện tại.

    Returns:
        (normalized_session_id, profile_slug, profile_url)
    """

    normalized_session_id, state_path = build_session_state_path(session_id=session_id, email=email)

    if not state_path.exists():
        raise FileNotFoundError(
            f"Không có file session cho '{normalized_session_id}'. Gọi POST /login trước.",
        )

    if not _state_has_li_at_cookie(state_path):
        raise RuntimeError(
            "Session không có cookie li_at — đăng nhập lại qua POST /login.",
        )

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=settings.headless,
            args=[
                "--disable-gpu",
                "--disable-dev-shm-usage",
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-infobars",
                "--disable-crash-reporter",
                "--disable-web-resources",
            ],
        )
        context = browser.new_context(storage_state=str(state_path))
        page = context.new_page()

        try:
            resolved: tuple[str, str] | None = None

            try:
                resolved = _try_resolve_slug_via_me_redirect(page)
            except Error as exc:
                logger.warning("Thử /in/me/ lấy slug thất bại: %s", exc)

            if resolved is None:
                try:
                    resolved = _try_resolve_slug_via_me_page(page)
                except Error as exc:
                    raise RuntimeError(
                        "Không lấy được profile slug qua /me/. Session có thể hết hạn. "
                        f"Chi tiết: {exc}",
                    ) from exc

            if resolved is None:
                raise RuntimeError(
                    "Không lấy được profile slug — cả /in/me/ và /me/ đều không redirect sang profile thực.",
                )

            slug, profile_url = resolved

            context.storage_state(path=str(state_path))
            return normalized_session_id, slug, profile_url
        finally:
            context.close()
            browser.close()
