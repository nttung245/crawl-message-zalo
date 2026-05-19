"""Playwright: mở URL bài LinkedIn và click reaction (Like / Love / …); không log cookie/session."""

from __future__ import annotations

from typing import Final, Literal

from playwright.sync_api import Error, Locator, Page, TimeoutError as PlaywrightTimeoutError

from app.config import settings
from app.services.auth_service import build_session_state_path
from app.services.linkedin_session_nav import goto_linkedin_url, is_linkedin_login_url
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

_REACTION_MENU_TRIGGERS: Final[str] = _normalize_selector_blob(
    """
    button[aria-label="Open reactions menu"],
    button[aria-label*="Open reactions menu"],
    button[aria-label*="reactions menu"],
    button[aria-label*="Reaction"]
    """,
)

# Flyout / palette — ưu tiên click trong vùng này (tránh nút ẩn ngoài menu).
_REACTION_FLYOUT_ROOTS: Final[tuple[str, ...]] = (
    "motion.div",
    "motion.ul",
    "motion.div.reactions-menu__content",
    "motion.div.reactions-menu",
    "motion.div[class*='reactions-menu']",
    "div.reactions-menu__content",
    "motion.div[class*='reactions-react-sheet']",
    "motion.div[class*='reactions-react']",
    "div.artdeco-hoverable-content",
    "motion.div[class*='artdeco-hoverable']",
)

_MENU_OPEN_TIMEOUT_MS: Final[int] = 300000
_TARGET_REACTION_TIMEOUT_MS: Final[int] = 60000
_ACTIVE_REACTION_BUTTON_SELECTOR: Final[str] = 'button[aria-label^="Reaction button state:"]'
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
    return is_linkedin_login_url(url)


def _menu_hover_settle_ms() -> int:
    return settings.reaction_menu_hover_settle_ms


def _post_goto_settle_ms() -> int:
    return settings.reaction_post_goto_settle_ms


def _post_click_settle_ms() -> int:
    return settings.reaction_post_click_settle_ms


def _reaction_is_active_on_page(page: Page, reaction: ReactionKind) -> bool:
    post_root = page.locator("main").first
    if post_root.locator(_pressed_reaction_selector(reaction)).count() > 0:
        try:
            if post_root.locator(_pressed_reaction_selector(reaction)).first.is_visible():
                return True
        except Error:
            pass

    state_buttons = post_root.locator(_ACTIVE_REACTION_BUTTON_SELECTOR)
    for index in range(state_buttons.count()):
        candidate = state_buttons.nth(index)
        try:
            if not candidate.is_visible():
                continue
        except Error:
            continue
        label = candidate.get_attribute("aria-label") or ""
        if _label_indicates_reaction_kind(label, reaction):
            return True
    return False


def _find_visible_flyout_root(page: Page, *, timeout_ms: int) -> Locator | None:
    deadline = timeout_ms
    for root_sel in _REACTION_FLYOUT_ROOTS:
        root = page.locator(root_sel)
        try:
            count = root.count()
        except Error:
            continue
        for index in range(min(count, 6)):
            candidate = root.nth(index)
            try:
                if candidate.is_visible():
                    return candidate
            except Error:
                continue

    # Chờ flyout render (VM chậm).
    for root_sel in _REACTION_FLYOUT_ROOTS:
        try:
            page.locator(root_sel).first.wait_for(state="visible", timeout=min(deadline, 8000))
            candidate = page.locator(root_sel).first
            if candidate.is_visible():
                return candidate
        except PlaywrightTimeoutError:
            continue
        except Error:
            continue
    return None


def _resolve_reaction_click_target(page: Page, reaction: ReactionKind) -> Locator:
    """Nút reaction visible — ưu tiên trong flyout để tránh click DOM ẩn."""

    selector = REACTION_SELECTORS[reaction]
    flyout = _find_visible_flyout_root(page, timeout_ms=_TARGET_REACTION_TIMEOUT_MS)
    if flyout is not None:
        scoped = flyout.locator(selector)
        try:
            if scoped.count() > 0:
                for index in range(min(scoped.count(), 8)):
                    candidate = scoped.nth(index)
                    if candidate.is_visible():
                        return candidate
        except Error:
            pass

    global_loc = page.locator(selector)
    for index in range(min(global_loc.count(), 12)):
        candidate = global_loc.nth(index)
        try:
            if candidate.is_visible():
                return candidate
        except Error:
            continue

    return global_loc.first


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

    page.wait_for_timeout(_post_click_settle_ms())
    logger.info("Đã bỏ reaction %s trên bài.", reaction)
    return True


def _click_reaction_on_page(page: Page, reaction: ReactionKind, *, timeout_ms: int) -> None:
    """Hover mở menu → chờ flyout ổn định → hover + click đúng nút → xác minh."""

    menu_timeout = max(timeout_ms, _MENU_OPEN_TIMEOUT_MS)
    hover_settle = _menu_hover_settle_ms()

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

    page.wait_for_timeout(hover_settle)

    target = _resolve_reaction_click_target(page, reaction)
    try:
        target.wait_for(state="visible", timeout=_TARGET_REACTION_TIMEOUT_MS)
        target.scroll_into_view_if_needed(timeout=_TARGET_REACTION_TIMEOUT_MS)
        # Hover nút đích trước click — giữ flyout mở, tránh mất focus khi VM chậm.
        target.hover(timeout=_TARGET_REACTION_TIMEOUT_MS)
        page.wait_for_timeout(max(400, hover_settle // 2))
        target.click(timeout=_TARGET_REACTION_TIMEOUT_MS, delay=120)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            f"Đã mở menu reaction nhưng không tìm thấy / không click được nút reaction ({reaction}).",
        ) from exc

    page.wait_for_timeout(_post_click_settle_ms())

    if not _reaction_is_active_on_page(page, reaction):
        logger.warning(
            "Reaction %s chưa xác nhận trên UI sau click — thử lại một lần (settle=%sms).",
            reaction,
            hover_settle,
        )
        try:
            open_menu_btn.hover(timeout=menu_timeout)
            page.wait_for_timeout(hover_settle)
            target = _resolve_reaction_click_target(page, reaction)
            target.wait_for(state="visible", timeout=_TARGET_REACTION_TIMEOUT_MS)
            target.hover(timeout=_TARGET_REACTION_TIMEOUT_MS)
            page.wait_for_timeout(max(500, hover_settle // 2))
            target.click(timeout=_TARGET_REACTION_TIMEOUT_MS, delay=150)
            page.wait_for_timeout(_post_click_settle_ms())
        except (PlaywrightTimeoutError, Error) as retry_exc:
            raise RuntimeError(
                f"Đã click reaction ({reaction}) nhưng LinkedIn không ghi nhận trên bài.",
            ) from retry_exc

        if not _reaction_is_active_on_page(page, reaction):
            raise RuntimeError(
                f"Đã click reaction ({reaction}) hai lần nhưng LinkedIn vẫn chưa hiển thị đã thích.",
            )

    logger.info("Đã áp dụng reaction %s trên bài (đã xác minh trên UI).", reaction)


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
        page = goto_linkedin_url(
            page.context,
            page,
            url,
            timeout_ms=300000,
            post_load_wait_ms=max(600, _post_goto_settle_ms() // 4),
        )
        page.wait_for_timeout(_post_goto_settle_ms())

        if clear_reaction:
            _remove_reaction_on_page(page, reaction, timeout_ms=300000)
        else:
            _click_reaction_on_page(page, reaction, timeout_ms=300000)

        page.wait_for_timeout(_post_click_settle_ms())
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
    """Trả ``(normalized_session_id, final_page_url)`` sau khi click reaction."""

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
