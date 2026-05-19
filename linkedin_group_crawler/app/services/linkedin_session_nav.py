"""Điều hướng Playwright + session LinkedIn: validate file, chọn tab đã login, tránh tab login trống."""

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

# UA desktop — giảm redirect login khi headless trên VM.
_LINKEDIN_DESKTOP_UA: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

_LINKEDIN_FEED_URL = "https://www.linkedin.com/feed/"


def is_linkedin_login_url(url: str) -> bool:
    """Login wall, checkpoint, hoặc trang chủ guest chưa đăng nhập."""

    return _is_authwall_url(url)


def validate_storage_state_file(state_path: Path) -> None:
    """Raise nếu thiếu file hoặc không có cookie ``li_at``."""

    if not state_path.is_file():
        raise FileNotFoundError(
            f"Không tìm thấy file session LinkedIn: {state_path}. "
            "Gọi POST /login (force_relogin=true) trên VM hoặc copy file .json vào storage/session/.",
        )
    if not _existing_state_is_reusable(state_path):
        raise RuntimeError(
            f"File session {state_path} thiếu cookie li_at hoặc không đọc được — "
            "cần đăng nhập lại: POST /login với email đúng, hoàn tất OTP nếu có, "
            "rồi kiểm tra file được ghi đè trong storage/session/.",
        )


def linkedin_browser_context_options() -> dict[str, object]:
    return {
        "viewport": {"width": 1366, "height": 768},
        "locale": "en-US",
        "timezone_id": "Asia/Ho_Chi_Minh",
        "user_agent": _LINKEDIN_DESKTOP_UA,
    }


def _page_looks_like_guest_home(page: Page) -> bool:
    """DOM guest: marketing home hoặc nút Sign in nổi bật (không có global nav đã login)."""

    try:
        if page.locator("header.global-nav").count() > 0:
            return False
        if page.locator('[data-tracking-control-name="guest_homepage-basic_sign-in"]').count() > 0:
            return True
        if page.get_by_role("heading", name="Welcome to your professional community").count() > 0:
            return True
        if page.get_by_role("link", name="Sign in", exact=True).count() > 0 and page.locator(
            "header.global-nav"
        ).count() == 0:
            return True
    except Error:
        logger.debug("Guest home DOM probe failed", exc_info=True)
    return False


def _is_usable_authenticated_page(page: Page) -> bool:
    url = (page.url or "").strip()
    if is_linkedin_login_url(url):
        return False
    if _is_linkedin_authenticated_app_url(url):
        return True
    if _context_has_li_at_cookie(page.context) and not _page_looks_like_guest_home(page):
        return True
    return False


def pick_authenticated_linkedin_page(context: BrowserContext, preferred: Page) -> Page:
    """Chọn tab LinkedIn đã đăng nhập (bỏ guest home / login)."""

    authenticated: list[Page] = []
    for candidate in context.pages:
        try:
            if candidate.is_closed():
                continue
            url = (candidate.url or "").strip()
            if "linkedin.com" not in url.lower():
                continue
            if not _is_usable_authenticated_page(candidate):
                continue
            authenticated.append(candidate)
        except Error:
            continue

    if authenticated:
        if preferred in authenticated:
            return preferred
        chosen = authenticated[-1]
        if chosen is not preferred:
            logger.info(
                "Dùng tab LinkedIn đã đăng nhập (không phải tab mặc định): %s",
                chosen.url,
            )
        return chosen

    try:
        if _is_usable_authenticated_page(preferred):
            return preferred
    except Error:
        pass

    login_urls = []
    for candidate in context.pages:
        try:
            if not candidate.is_closed():
                login_urls.append(candidate.url or "")
        except Error:
            continue
    raise RuntimeError(
        "Tất cả tab trình duyệt đều ở trang đăng nhập/guest — session hết hạn hoặc "
        f"sai file session. URLs: {login_urls[:5]}",
    )


def _open_feed_to_restore_session(
    context: BrowserContext,
    page: Page,
    *,
    timeout_ms: int,
    post_load_wait_ms: int,
) -> Page:
    """Thử mở feed khi cookie còn nhưng tab đang ở trang guest."""

    logger.info("Phục hồi session: mở %s (tab hiện tại: %s)", _LINKEDIN_FEED_URL, page.url)
    page.goto(_LINKEDIN_FEED_URL, wait_until="domcontentloaded", timeout=timeout_ms)
    for _ in range(5):
        page.wait_for_timeout(post_load_wait_ms)
        page = pick_authenticated_linkedin_page(context, page)
        if _is_usable_authenticated_page(page):
            return page
    return page


def ensure_linkedin_session_ready(
    context: BrowserContext,
    page: Page,
    *,
    timeout_ms: int = 300000,
    post_load_wait_ms: int = 800,
) -> Page:
    """Đảm bảo tab đã login (cookie + URL/DOM); thử feed một lần nếu đang guest."""

    page = pick_authenticated_linkedin_page(context, page)
    current_url = (page.url or "").strip()
    if _is_linkedin_authenticated_app_url(current_url):
        return page
    if _is_usable_authenticated_page(page):
        return page

    if not _context_has_li_at_cookie(context):
        raise RuntimeError(
            "Cookie li_at không còn trong trình duyệt — session hết hạn. "
            "Gọi POST /login với đúng email (Email_crawl), force_relogin=true, prime_pool=true."
        )

    page = _open_feed_to_restore_session(
        context,
        page,
        timeout_ms=timeout_ms,
        post_load_wait_ms=post_load_wait_ms,
    )
    if _is_usable_authenticated_page(page):
        return page

    current = (page.url or "").strip()
    if is_linkedin_login_url(current) or _page_looks_like_guest_home(page):
        raise RuntimeError(
            f"LinkedIn vẫn ở trang chưa đăng nhập ({current}). "
            "Kiểm tra Email_crawl khớp email đã POST /login; đăng nhập lại và prime pool."
        )
    return page


def goto_linkedin_url(
    context: BrowserContext,
    page: Page,
    url: str,
    *,
    timeout_ms: int = 300000,
    post_load_wait_ms: int = 800,
) -> Page:
    """``page.goto`` rồi chuyển sang tab LinkedIn đã login nếu LinkedIn mở tab mới."""

    target = (url or "").strip()
    try:
        page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
    except Error as exc:
        current = ""
        try:
            current = page.url or ""
        except Error:
            pass
        if is_linkedin_login_url(current):
            raise RuntimeError(
                "LinkedIn chuyển sang trang đăng nhập/guest — session không hợp lệ hoặc sai file session.",
            ) from exc
        raise RuntimeError(f"Lỗi khi mở URL LinkedIn: {exc}") from exc

    for _ in range(4):
        page.wait_for_timeout(post_load_wait_ms)
        try:
            page = pick_authenticated_linkedin_page(context, page)
        except RuntimeError:
            if not _context_has_li_at_cookie(context):
                raise
            page = _open_feed_to_restore_session(
                context,
                page,
                timeout_ms=timeout_ms,
                post_load_wait_ms=post_load_wait_ms,
            )
            page.goto(target, wait_until="domcontentloaded", timeout=timeout_ms)
            continue
        if _is_usable_authenticated_page(page):
            return ensure_linkedin_session_ready(
                context,
                page,
                timeout_ms=timeout_ms,
                post_load_wait_ms=post_load_wait_ms,
            )

    current = (page.url or "").strip()
    raise RuntimeError(
        f"Sau khi mở bài vẫn ở trang login/guest (tab: {current}). "
        "Hãy POST /login lại với đúng email (Email_crawl) và force_relogin=true."
    )
