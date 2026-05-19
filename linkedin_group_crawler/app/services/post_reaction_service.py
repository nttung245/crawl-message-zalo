"""Playwright: mở URL bài LinkedIn và click reaction (Like / Love / …); không log cookie/session."""

from __future__ import annotations

from typing import Final, Literal
from urllib.parse import urlparse

from playwright.sync_api import Error, Page, TimeoutError as PlaywrightTimeoutError

from app.services.auth_service import build_session_state_path
from app.services.playwright_browser_pool import run_with_linkedin_session_page
from app.utils.logger import get_logger


logger = get_logger(__name__)

ReactionKind = Literal["like", "love", "celebrate", "support", "insightful", "funny"]

REACTION_KINDS: Final[tuple[str, ...]] = (
    "like",
    "love",
    "celebrate",
    "support",
    "insightful",
    "funny",
)


def _normalize_selector_blob(raw: str) -> str:
    """Gộp khoảng trắng / xuống dòng trong chuỗi selector CSS (Playwright)."""

    return " ".join((raw or "").split())


# Nút reaction trong flyout sau khi hover mở menu — khớp luồng UI LinkedIn (EN/VN).
_REACTION_SELECTOR_PARTS: Final[dict[str, tuple[str, ...]]] = {
    "like": (
        'button[aria-label="Like"]',
        'button[aria-label*="Like"]',
        'button[aria-label*="Thích"]',
    ),
    "love": (
        'button[aria-label="Love"]',
        'button[aria-label*="Love"]',
        'button[aria-label*="Yêu thích"]',
    ),
    "celebrate": (
        'button[aria-label="Celebrate"]',
        'button[aria-label*="Celebrate"]',
        'button[aria-label*="Praise"]',
        'button[aria-label*="Chúc mừng"]',
    ),
    "support": (
        'button[aria-label="Support"]',
        'button[aria-label*="Support"]',
        'button[aria-label*="Ủng hộ"]',
    ),
    "insightful": (
        'button[aria-label="Insightful"]',
        'button[aria-label*="Insightful"]',
        'button[aria-label*="Sâu sắc"]',
    ),
    "funny": (
        'button[aria-label="Funny"]',
        'button[aria-label*="Funny"]',
        'button[aria-label*="Entertainment"]',
        'button[aria-label*="Hài hước"]',
    ),
}

REACTION_SELECTORS: Final[dict[str, str]] = {
    kind: ", ".join(parts) for kind, parts in _REACTION_SELECTOR_PARTS.items()
}

# Luồng chuẩn: hover nút mở reaction menu (trong main), đợi flyout, một lần click đúng loại — tránh click kép làm toggle mất like.
_REACTION_MENU_TRIGGERS: Final[str] = _normalize_selector_blob(
    """
    button[aria-label="Open reactions menu"],
    button[aria-label*="Open reactions menu"],
    button[aria-label*="reactions menu"],
    button[aria-label*="Reaction"]
    """,
)

_MENU_OPEN_TIMEOUT_MS: Final[int] = 300000
_MENU_HOVER_SETTLE_MS: Final[int] = 800
_TARGET_REACTION_TIMEOUT_MS: Final[int] = 60000
_ACTIVE_REACTION_BUTTON_SELECTOR: Final[str] = 'button[aria-label^="Reaction button state:"]'
_REACTION_REMOVED_SETTLE_MS: Final[int] = 800
_REACTION_STATE_LABEL_HINTS: Final[dict[str, tuple[str, ...]]] = {
    "like": ("like", "thích", "thich"),
    "love": ("love", "yêu thích", "yeu thich"),
    "celebrate": ("celebrate", "praise", "chúc mừng", "chuc mung"),
    "support": ("support", "ủng hộ", "ung ho"),
    "insightful": ("insightful", "sâu sắc", "sau sac"),
    "funny": ("funny", "entertainment", "hài hước", "hai huoc"),
}


def _pressed_reaction_selector(reaction: ReactionKind) -> str:
    parts = _REACTION_SELECTOR_PARTS[reaction]
    return ", ".join(f'{part}[aria-pressed="true"]' for part in parts)


def _label_indicates_reaction_kind(label: str, reaction: ReactionKind) -> bool:
    text = (label or "").strip().lower()
    if not text:
        return False
    return any(hint in text for hint in _REACTION_STATE_LABEL_HINTS[reaction])


def _is_login_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    path = (parsed.path or "").lower()
    return any(path.startswith(prefix) for prefix in ("/login", "/checkpoint", "/authwall"))


def _remove_reaction_on_page(page: Page, reaction: ReactionKind, *, timeout_ms: int) -> bool:
    """Gỡ reaction bằng click trực tiếp nút đang bật đúng loại — không hover flyout."""

    post_root = page.locator("main").first
    locator_timeout = max(timeout_ms, _TARGET_REACTION_TIMEOUT_MS)
    active_btn = post_root.locator(_pressed_reaction_selector(reaction)).first
    if active_btn.count() == 0:
        matched_state_btn = None
        state_buttons = post_root.locator(_ACTIVE_REACTION_BUTTON_SELECTOR)
        for index in range(state_buttons.count()):
            candidate = state_buttons.nth(index)
            label = candidate.get_attribute("aria-label") or ""
            if _label_indicates_reaction_kind(label, reaction):
                matched_state_btn = candidate
                break
        if matched_state_btn is None:
            if state_buttons.count() == 0:
                logger.info("Post chưa có reaction — không cần bỏ.")
            else:
                logger.warning(
                    "Không khớp nút reaction state với %s — bỏ qua click để tránh đổi sang Like.",
                    reaction,
                )
            return False
        active_btn = matched_state_btn

    try:
        active_btn.wait_for(state="visible", timeout=locator_timeout)
        label = active_btn.get_attribute("aria-label")
        if label:
            logger.info("Reaction hiện tại trên bài: %s", label)
        active_btn.scroll_into_view_if_needed(timeout=locator_timeout)
        active_btn.click(timeout=locator_timeout)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            f"Không tìm thấy / không click được nút reaction đang bật để hủy ({reaction}).",
        ) from exc

    page.wait_for_timeout(_REACTION_REMOVED_SETTLE_MS)
    logger.info("Đã bỏ reaction %s trên bài.", reaction)
    return True


def _click_reaction_on_page(page: Page, reaction: ReactionKind, *, timeout_ms: int) -> None:
    """Hover nút mở reactions trong ``main``, chờ flyout, click đúng một reaction (không bấm trigger để tránh toggle)."""

    selector = REACTION_SELECTORS[reaction]
    menu_timeout = max(timeout_ms, _MENU_OPEN_TIMEOUT_MS)

    post_root = page.locator("main").first
    open_menu_btn = post_root.locator(_REACTION_MENU_TRIGGERS).first

    try:
        open_menu_btn.wait_for(state="visible", timeout=menu_timeout)
        open_menu_btn.scroll_into_view_if_needed(timeout=menu_timeout)
        open_menu_btn.hover(timeout=menu_timeout)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            "Không thấy nút mở reaction menu trong main — kiểm tra URL bài và DOM LinkedIn.",
        ) from exc

    page.wait_for_timeout(_MENU_HOVER_SETTLE_MS)

    target = page.locator(selector).first
    try:
        target.wait_for(state="visible", timeout=_TARGET_REACTION_TIMEOUT_MS)
        target.scroll_into_view_if_needed(timeout=_TARGET_REACTION_TIMEOUT_MS)
        target.click(timeout=_TARGET_REACTION_TIMEOUT_MS)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            f"Đã mở menu reaction nhưng không tìm thấy / không click được nút reaction ({reaction}).",
        ) from exc


def _run_linkedin_post_reaction_playwright(
    *,
    post_url: str,
    reaction: ReactionKind,
    session_id: str | None,
    email: str | None,
    clear_reaction: bool,
) -> tuple[str, str]:
    """Trả ``(normalized_session_id, final_page_url)`` sau khi thêm hoặc gỡ reaction."""

    url = (post_url or "").strip()
    if "linkedin.com" not in url.lower():
        raise ValueError("post_url phải là URL LinkedIn.")

    normalized_session_id, state_path = build_session_state_path(session_id=session_id, email=email)
    if not state_path.is_file():
        raise FileNotFoundError(
            f"Không tìm thấy session LinkedIn tại {state_path}. Hãy POST /login (hoặc /verify) trước.",
        )

    if reaction not in REACTION_SELECTORS:
        raise ValueError(f"reaction không hỗ trợ: {reaction}")

    def _playwright_action(page: Page) -> tuple[str, str]:
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=300000)
        except Error as exc:
            current = page.url or ""
            if _is_login_url(current):
                raise RuntimeError(
                    "LinkedIn chuyển sang trang đăng nhập/checkpoint — session có thể đã hết hạn.",
                ) from exc
            raise RuntimeError(f"Lỗi khi mở URL bài: {exc}") from exc

        page.wait_for_timeout(2500)

        if _is_login_url(page.url):
            raise RuntimeError(
                "LinkedIn session không hợp lệ hoặc đã hết hạn (đang ở login/checkpoint).",
            )

        if clear_reaction:
            _remove_reaction_on_page(page, reaction, timeout_ms=300000)
        else:
            _click_reaction_on_page(page, reaction, timeout_ms=300000)

        page.wait_for_timeout(1200)
        final_url = page.url or url
        return normalized_session_id, final_url

    return run_with_linkedin_session_page(
        state_path=state_path,
        action=_playwright_action,
    )


def react_to_linkedin_post(
    *,
    post_url: str,
    reaction: ReactionKind,
    session_id: str | None,
    email: str | None,
) -> tuple[str, str]:
    """Trả ``(normalized_session_id, final_page_url)`` sau khi click reaction.

    Raises:
        FileNotFoundError: không có file storage session.
        ValueError: URL không hợp lệ.
        RuntimeError: session hết hạn hoặc không tìm thấy nút reaction.
    """

    return _run_linkedin_post_reaction_playwright(
        post_url=post_url,
        reaction=reaction,
        session_id=session_id,
        email=email,
        clear_reaction=False,
    )


def remove_reaction_from_linkedin_post(
    *,
    post_url: str,
    reaction: ReactionKind,
    session_id: str | None,
    email: str | None,
) -> tuple[str, str]:
    """Gỡ reaction trên LinkedIn bằng click trực tiếp nút reaction đang bật."""

    return _run_linkedin_post_reaction_playwright(
        post_url=post_url,
        reaction=reaction,
        session_id=session_id,
        email=email,
        clear_reaction=True,
    )
