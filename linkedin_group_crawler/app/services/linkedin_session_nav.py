"""Điều hướng Playwright + session LinkedIn: validate file, chọn tab đã login, tránh tab login trống."""

from __future__ import annotations

from pathlib import Path

from playwright.sync_api import BrowserContext, Error, Page

from app.services.auth_service import _existing_state_is_reusable, _is_authwall_url
from app.utils.logger import get_logger

logger = get_logger(__name__)

# UA desktop — giảm redirect login khi headless trên VM.
_LINKEDIN_DESKTOP_UA: str = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)


def is_linkedin_login_url(url: str) -> bool:
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


def pick_authenticated_linkedin_page(context: BrowserContext, preferred: Page) -> Page:
    """Chọn tab đang ở LinkedIn và không phải trang login (khi mở tab mới)."""

    authenticated: list[Page] = []
    for candidate in context.pages:
        try:
            if candidate.is_closed():
                continue
            url = (candidate.url or "").strip()
            if "linkedin.com" not in url.lower():
                continue
            if is_linkedin_login_url(url):
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
        pref_url = preferred.url or ""
        if "linkedin.com" in pref_url.lower() and not is_linkedin_login_url(pref_url):
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
        "Tất cả tab trình duyệt đều ở trang đăng nhập/checkpoint — session hết hạn hoặc "
        f"sai file session. URLs: {login_urls[:5]}",
    )


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
                "LinkedIn chuyển sang trang đăng nhập — session không hợp lệ hoặc sai file session.",
            ) from exc
        raise RuntimeError(f"Lỗi khi mở URL LinkedIn: {exc}") from exc

  # LinkedIn hay mở tab mới sau goto — chờ rồi chọn tab không phải login.
    for _ in range(4):
        page.wait_for_timeout(post_load_wait_ms)
        page = pick_authenticated_linkedin_page(context, page)
        if not is_linkedin_login_url(page.url or ""):
            return page

    raise RuntimeError(
        f"Sau khi mở bài vẫn ở trang login/checkpoint (tab: {page.url}). "
        "Hãy POST /login lại với đúng email và force_relogin=true.",
    )
