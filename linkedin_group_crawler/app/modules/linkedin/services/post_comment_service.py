"""Playwright: nhập comment LinkedIn trên URL bài — không log cookie/session."""

from __future__ import annotations

import platform
from typing import Final
from urllib.parse import urlparse

from playwright.sync_api import Error, Page, TimeoutError as PlaywrightTimeoutError

from app.modules.linkedin.services.auth_service import build_session_state_path
from app.modules.linkedin.services.linkedin_engagement_session import ensure_linkedin_session_for_engagement
from app.modules.linkedin.services.linkedin_session_nav import goto_linkedin_url, is_linkedin_login_url
from app.core.playwright_browser_pool import run_with_linkedin_session_page
from app.core.logger import get_logger


logger = get_logger(__name__)

_COMMENT_OPEN_TRIGGER_SELECTORS: Final[tuple[str, ...]] = (
    'button[aria-label="Comment"]',
    'button[aria-label*="Comment"]',
    'button[aria-label*="Bình luận"]',
    'button[aria-label*="bình luận"]',
    'button.comments-comment-box__open-artdeco-button',
    'button.artdeco-button.comments-comment-box__open-artdeco-button',
    'button[data-control-name="public_post_comment"]',
)

_COMMENT_EDITOR_SELECTORS: Final[tuple[str, ...]] = (
    '[componentkey^="commentBox-"] [data-testid="ui-core-tiptap-text-editor-wrapper"] '
    'div[contenteditable="true"][role="textbox"]',
    '[componentkey^="commentBox-"] div[contenteditable="true"][role="textbox"].ProseMirror',
    '[data-testid="ui-core-tiptap-text-editor-wrapper"] div[contenteditable="true"][role="textbox"]',
    'div.comments-comment-box__form div[contenteditable="true"][role="textbox"]',
    'div[contenteditable="true"][role="textbox"][aria-label="Text editor for creating comment"]',
    'div[contenteditable="true"][role="textbox"].ProseMirror',
    'div.ql-editor[contenteditable="true"]',
)

_COMMENT_SECTION_SELECTORS: Final[tuple[str, ...]] = (
    '[componentkey^="commentBox-"]',
    'div.comments-comment-box',
    'div.comments-comment-box__form',
    'section.comments-comment-box',
)

_EDITOR_PROBE_TIMEOUT_MS: Final[int] = 2500
_COMPOSER_OPEN_SETTLE_MS: Final[int] = 700
_SUBMIT_ENABLE_SETTLE_MS: Final[int] = 450

_COMMENT_SUBMIT_SELECTORS: Final[tuple[str, ...]] = (
    'button[componentkey*="commentButtonSection"]:not([disabled])',
    'button[componentkey*="commentButtonSection"]',
    'button.comments-comment-box__submit-button--cr:not([disabled])',
    'button.comments-comment-box__submit-button:not([disabled])',
    'button[data-control-name="comment_submit"]:not([disabled])',
    'button.artdeco-button--primary.comments-comment-box__submit-button:not([disabled])',
    'button[aria-label*="Post"]:not([disabled])',
)

_COMMENT_SUBMIT_LABELS: Final[tuple[str, ...]] = (
    "Comment",
    "Bình luận",
    "Post",
)


def _is_login_url(url: str) -> bool:
    return is_linkedin_login_url(url)


def _scroll_comment_section_into_view(post_root, *, timeout_ms: int) -> None:
    for sel in _COMMENT_SECTION_SELECTORS:
        section = post_root.locator(sel).first
        if section.count() == 0:
            continue
        try:
            section.scroll_into_view_if_needed(timeout=min(timeout_ms, 8000))
            return
        except (PlaywrightTimeoutError, Error):
            continue


def _find_visible_comment_editor(post_root, *, timeout_ms: int):
    probe_timeout = min(timeout_ms, _EDITOR_PROBE_TIMEOUT_MS)
    for sel in _COMMENT_EDITOR_SELECTORS:
        editor = post_root.locator(sel).first
        if editor.count() == 0:
            continue
        try:
            editor.wait_for(state="visible", timeout=probe_timeout)
            return editor
        except (PlaywrightTimeoutError, Error):
            continue
    return None


def _open_comment_composer(page: Page, post_root, *, timeout_ms: int):
    editor = _find_visible_comment_editor(post_root, timeout_ms=timeout_ms)
    if editor is not None:
        return editor

    _scroll_comment_section_into_view(post_root, timeout_ms=timeout_ms)

    for sel in _COMMENT_OPEN_TRIGGER_SELECTORS:
        trigger = post_root.locator(sel).first
        if trigger.count() == 0:
            continue
        try:
            trigger.wait_for(state="visible", timeout=3000)
            trigger.scroll_into_view_if_needed(timeout=3000)
            trigger.click(timeout=timeout_ms)
            page.wait_for_timeout(_COMPOSER_OPEN_SETTLE_MS)
        except (PlaywrightTimeoutError, Error):
            continue

        editor = _find_visible_comment_editor(post_root, timeout_ms=timeout_ms)
        if editor is not None:
            return editor

    editor = _find_visible_comment_editor(post_root, timeout_ms=timeout_ms)
    if editor is not None:
        return editor

    raise RuntimeError(
        "Bài viết này không cho phép bình luận, xin cảm ơn.",
    )


def _comment_composer_root(editor):
    for sel in (
        'xpath=ancestor::*[starts-with(@componentkey, "commentBox-")][1]',
        'xpath=ancestor::*[contains(@componentkey, "commentBox")][1]',
        'xpath=ancestor::div[contains(@class, "comments-comment-box")][1]',
    ):
        root = editor.locator(sel)
        if root.count() > 0:
            return root.first
    return None


def _submit_comment(page: Page, post_root, *, timeout_ms: int, editor=None) -> None:
    """LinkedIn: bấm nút Comment trong composer sau khi đã gõ."""

    page.wait_for_timeout(_SUBMIT_ENABLE_SETTLE_MS)
    submit_timeout = min(timeout_ms, 12000)
    roots = []
    if editor is not None:
        composer_root = _comment_composer_root(editor)
        if composer_root is not None:
            roots.append(composer_root)
    roots.append(post_root)

    for root in roots:
        for sel in _COMMENT_SUBMIT_SELECTORS:
            btn = root.locator(sel).first
            if btn.count() == 0:
                continue
            try:
                btn.wait_for(state="visible", timeout=3000)
                btn.scroll_into_view_if_needed(timeout=3000)
                btn.click(timeout=submit_timeout)
                return
            except (PlaywrightTimeoutError, Error):
                continue

        for label in _COMMENT_SUBMIT_LABELS:
            btn = root.get_by_role("button", name=label, exact=True).first
            if btn.count() == 0:
                continue
            try:
                btn.wait_for(state="visible", timeout=3000)
                btn.scroll_into_view_if_needed(timeout=3000)
                btn.click(timeout=submit_timeout)
                return
            except (PlaywrightTimeoutError, Error):
                continue

    mod = "Meta" if platform.system() == "Darwin" else "Control"
    page.keyboard.press(f"{mod}+Enter")


def _fill_comment_box(
    page: Page,
    comment_text: str,
    *,
    timeout_ms: int,
    typing_delay_ms: int,
) -> None:
    text = (comment_text or "").strip()
    if not text:
        raise ValueError("comment_text không được rỗng.")

    post_root = page.locator("main").first
    editor = _open_comment_composer(page, post_root, timeout_ms=timeout_ms)
    try:
        editor.scroll_into_view_if_needed(timeout=timeout_ms)
        editor.click(timeout=timeout_ms)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            "Không mở được editor comment. DOM LinkedIn có thể đã đổi.",
        ) from exc

    if platform.system() == "Darwin":
        page.keyboard.press("Meta+A")
    else:
        page.keyboard.press("Control+A")
    page.keyboard.press("Backspace")
    page.keyboard.type(text, delay=max(0, int(typing_delay_ms)))

    verify_js = """
        ({ text }) => {
          const needle = String(text).trim();
          if (!needle) return false;
          const selectors = [
            '[componentkey^="commentBox-"] div[contenteditable="true"][role="textbox"]',
            'div.comments-comment-box__form div[contenteditable="true"][role="textbox"]',
            '[data-testid="ui-core-tiptap-text-editor-wrapper"] div[contenteditable="true"][role="textbox"]',
            'div[contenteditable="true"][role="textbox"].ProseMirror',
          ];
          return selectors.some((selector) =>
            Array.from(document.querySelectorAll(selector)).some((ed) =>
              ed.innerText.trim().includes(needle),
            ),
          );
        }
    """
    try:
        page.wait_for_function(verify_js, arg={"text": text}, timeout=60000)
    except PlaywrightTimeoutError as exc:
        raise RuntimeError(
            "Nội dung comment không khớp trong editor sau khi gõ — có thể popup hoặc DOM khác.",
        ) from exc

    _submit_comment(page, post_root, timeout_ms=min(timeout_ms, 15000), editor=editor)
    page.wait_for_timeout(1800)


def comment_on_linkedin_post(
    *,
    post_url: str,
    comment_text: str,
    session_id: str | None,
    email: str | None,
    typing_delay_ms: int = 30,
    timeout_ms: int = 300000,
    password: str | None = None,
    auto_login: bool = True,
) -> tuple[str, str]:
    """Trả ``(normalized_session_id, final_page_url)`` sau khi gửi comment.

    Raises:
        FileNotFoundError: không có file storage session.
        ValueError: URL / comment không hợp lệ.
        RuntimeError: session hết hạn hoặc không đăng được comment.
    """

    url = (post_url or "").strip()
    if "linkedin.com" not in url.lower():
        raise ValueError("post_url phải là URL LinkedIn.")

    if auto_login:
        normalized_session_id, state_path = ensure_linkedin_session_for_engagement(
            email=email,
            session_id=session_id,
            password=password,
            force_relogin=True,
        )
    else:
        normalized_session_id, state_path = build_session_state_path(
            session_id=session_id,
            email=email,
        )
    logger.info(
        "Playwright comment session_id=%s email=%s state_file=%s auto_login=%s",
        normalized_session_id,
        email or "",
        state_path.name,
        auto_login,
    )

    def _playwright_action(page: Page) -> tuple[str, str]:
        page = goto_linkedin_url(
            page.context,
            page,
            url,
            timeout_ms=300000,
            post_load_wait_ms=700,
        )
        page.wait_for_timeout(2800)

        _fill_comment_box(
            page,
            comment_text,
            timeout_ms=timeout_ms,
            typing_delay_ms=typing_delay_ms,
        )

        final_url = page.url or url
        return normalized_session_id, final_url

    try:
        return run_with_linkedin_session_page(
            state_path=state_path,
            action=_playwright_action,
        )
    except RuntimeError as exc:
        err_msg = str(exc)
        is_auth_err = any(hint in err_msg for hint in ("chưa đăng nhập", "login/guest/cold-join", "session hết hạn"))
        if is_auth_err and auto_login:
            logger.warning(
                "Phát hiện session hết hạn hoặc không hợp lệ khi gửi comment. Đang thực hiện auto-login lại..."
            )
            # Re-resolve and force fresh login
            normalized_session_id, state_path = ensure_linkedin_session_for_engagement(
                email=email,
                session_id=session_id,
                password=password,
                force_relogin=True,
            )
            # Retry running the action with updated session ID
            def _playwright_action_retry(page: Page) -> tuple[str, str]:
                page_res = goto_linkedin_url(
                    page.context,
                    page,
                    url,
                    timeout_ms=300000,
                    post_load_wait_ms=700,
                )
                page_res.wait_for_timeout(2800)
                _fill_comment_box(
                    page_res,
                    comment_text,
                    timeout_ms=timeout_ms,
                    typing_delay_ms=typing_delay_ms,
                )
                final_url = page_res.url or url
                return normalized_session_id, final_url

            return run_with_linkedin_session_page(
                state_path=state_path,
                action=_playwright_action_retry,
            )
        else:
            raise
