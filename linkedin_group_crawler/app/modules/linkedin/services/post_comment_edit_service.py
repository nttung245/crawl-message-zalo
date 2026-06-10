"""Playwright: chỉnh sửa comment trên LinkedIn post detail."""

from __future__ import annotations

from typing import Final, List, Optional, Tuple
import re
from urllib.parse import unquote, urlparse

from playwright.sync_api import Error, Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from app.core.config import settings
from app.modules.linkedin.services.auth_service import build_session_state_path
from app.modules.linkedin.services.post_comment_delete_service import (
    _absolute_activity_href,
    _choose_detail_delete_block,
    _collect_self_comment_blocks_on_detail,
    _detail_comment_text_pattern,
    _open_comment_action_menu,
    _POST_DETAIL_SETTLE_MS,
    _safe_visible,
    _visible_dropdown_menu,
)
from app.core.logger import get_logger


logger = get_logger(__name__)

_EDIT_MENU_ITEM_SELECTORS: Final[Tuple[str, ...]] = (
    '.artdeco-dropdown__content--is-open div[role="button"].option-button:has-text("Edit")',
    '.artdeco-dropdown__item.option-button .comment-options-dropdown__option-text:has-text("Edit")',
    '[role="menuitem"] button:has-text("Edit")',
    '[role="menuitem"]:has-text("Edit")',
    'button[role="menuitem"][aria-label*="Edit"]',
)

_COMMENT_EDIT_FORM_SELECTOR: Final[str] = '[role="textbox"][contenteditable="true"]'
_SAVE_COMMENT_BUTTON_SELECTORS: Final[Tuple[str, ...]] = (
    'button:has-text("Save changes")',
    'button:has-text("Save"):not(:has-text("Save photo"))',
)


def _click_edit_menu_item(page: Page) -> bool:
    """Click Edit từ dropdown menu comment."""
    dropdown = _visible_dropdown_menu(page)
    scopes: List[Locator] = []
    if dropdown.count() > 0:
        scopes.append(dropdown)
    scopes.append(page.locator("body"))

    for scope in scopes:
        try:
            scope.get_by_role("button", name="Edit").first.click(timeout=15000)
            return True
        except (PlaywrightTimeoutError, Error):
            pass
        try:
            scope.get_by_text("Edit").first.click(timeout=15000)
            return True
        except (PlaywrightTimeoutError, Error):
            pass
        for selector in _EDIT_MENU_ITEM_SELECTORS:
            item = scope.locator(selector).first
            if item.count() <= 0:
                continue
            try:
                if item.is_visible():
                    item.click()
                    return True
            except Error:
                continue
    return False


def _wait_for_comment_edit_form(
    page: Page,
    target_block: Locator,
    old_text: str,
    timeout_ms: int = 30000,
) -> Optional[Locator]:
    """Chờ form edit comment hiển thị (contenteditable textbox) đúng block."""
    scoped = target_block.locator(_COMMENT_EDIT_FORM_SELECTOR).first
    try:
        if scoped.count() > 0:
            scoped.wait_for(state="visible", timeout=timeout_ms)
            return scoped
    except (PlaywrightTimeoutError, Error):
        pass

    old_text_clean = (old_text or "").strip()
    if old_text_clean:
        try:
            matched = page.locator(_COMMENT_EDIT_FORM_SELECTOR).filter(has_text=old_text_clean).first
            if matched.count() > 0:
                matched.wait_for(state="visible", timeout=timeout_ms)
                return matched
        except (PlaywrightTimeoutError, Error):
            pass

    try:
        form = page.locator(_COMMENT_EDIT_FORM_SELECTOR).filter(has_text=re.compile(r"\S")).first
        form.wait_for(state="visible", timeout=timeout_ms)
        return form
    except (PlaywrightTimeoutError, Error):
        return None


def _update_comment_text_in_form(
    form: Locator,
    old_text: str,
    new_text: str,
    page: Page,
) -> bool:
    """Cập nhật text trong contenteditable form."""
    try:
        # Focus and clear
        form.click()
        page.wait_for_timeout(150)
        page.keyboard.press("Control+A")
        page.keyboard.press("Delete")
        page.wait_for_timeout(150)

        # Type new text
        page.keyboard.type(new_text, delay=20)
        page.wait_for_timeout(300)
        return True
    except Error:
        pass

    try:
        # Fallback: direct DOM update for contenteditable
        form.evaluate(
            """
            (node, value) => {
              node.focus();
              node.textContent = value;
              node.dispatchEvent(new InputEvent('input', { bubbles: true }));
              node.dispatchEvent(new Event('change', { bubbles: true }));
            }
            """,
            new_text,
        )
        page.wait_for_timeout(200)
        return True
    except Error:
        return False


def _click_save_comment_changes(page: Page, scope: Optional[Locator] = None) -> bool:
    """Click Save changes button."""
    scopes: List[Locator] = []
    if scope is not None:
        scopes.append(scope)
    scopes.append(page.locator("body"))

    for root in scopes:
        for selector in _SAVE_COMMENT_BUTTON_SELECTORS:
            try:
                btn = root.locator(selector).last
                if btn.count() > 0 and _safe_visible(btn):
                    btn.click()
                    page.wait_for_timeout(300)
                    return True
            except Error:
                continue

        try:
            save_btn = root.get_by_role("button", name="Save changes").last
            if save_btn.count() > 0 and _safe_visible(save_btn):
                save_btn.click()
                page.wait_for_timeout(300)
                return True
        except Error:
            pass

    return False


def _comment_edit_scope_from_form(form: Locator) -> Locator:
    """Tìm container gần nhất chứa nút Save/Cancel cho form edit."""
    return form.locator(
        'xpath=ancestor::*[.//button[contains(.,"Save changes") or contains(.,"Save") or contains(.,"Cancel")]][1]'
    )


def edit_linkedin_comment_from_post_detail(
    post_url: str,
    comment_text: str,
    new_comment_text: str,
    profile_slug: Optional[str] = None,
    session_id: Optional[str] = None,
    email: Optional[str] = None,
    timeout_ms: int = 300000,
) -> Tuple[str, str]:
    """
    Chỉnh sửa comment trên LinkedIn bằng cách vào post detail trực tiếp.
    
    Workflow:
    1. Vào post detail (post_url)
    2. Tìm comment với nội dung = comment_text + You/Bạn
    3. Mở menu (Open options) → Click Edit
    4. Chờ form edit hiển thị
    5. Clear text cũ, nhập text mới
    6. Click Save changes
    7. Verify comment đã cập nhật
    
    Return: (session_id, post_url_normalized)
    """
    # Resolve session
    try:
        resolved_session_id, state_path = build_session_state_path(
            session_id=session_id,
            email=email,
        )
    except FileNotFoundError as exc:
        raise FileNotFoundError(
            f"Session file không tồn tại. Email: {email}, Session: {session_id}"
        ) from exc

    sheet_comment_raw = (comment_text or "").strip()
    new_comment_raw = (new_comment_text or "").strip()
    
    if not new_comment_raw:
        raise ValueError("new_comment_text không thể rỗng.")
    
    detail_comment_re = _detail_comment_text_pattern(comment_text)
    post_url_normalized = _absolute_activity_href(post_url)
    
    if not post_url_normalized:
        raise ValueError(f"Invalid post_url: {post_url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless)
        try:
            context = browser.new_context(storage_state=state_path)
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            # --- Vào post detail ---
            logger.info(
                "Comment edit — opening post URL: %s…",
                post_url_normalized[:160],
            )
            page.goto(post_url_normalized, wait_until="domcontentloaded")
            page.locator("main").wait_for(state="visible", timeout=60000)
            page.wait_for_timeout(_POST_DETAIL_SETTLE_MS)

            # --- Tìm comment ---
            matched_blocks = _collect_self_comment_blocks_on_detail(
                page,
                detail_comment_re,
                sheet_comment_raw,
                profile_slug or "",
            )

            target_block = _choose_detail_delete_block(
                matched_blocks,
                sheet_comment_raw,
                profile_slug or "",
            )
            if target_block is None:
                raise ValueError(
                    "Không tìm thấy comment để chỉnh sửa."
                )

            target_block.scroll_into_view_if_needed()

            # --- Mở menu tùy chọn ---
            if not _open_comment_action_menu(target_block, page):
                raise RuntimeError(
                    "Không tìm thấy hoặc click được menu tùy chọn comment."
                )

            # --- Click Edit ---
            if not _click_edit_menu_item(page):
                raise RuntimeError("Không tìm thấy hoặc click được Edit trong menu.")

            page.wait_for_timeout(500)

            # --- Chờ form edit hiển thị ---
            edit_form = _wait_for_comment_edit_form(
                page,
                target_block,
                sheet_comment_raw,
                timeout_ms=30000,
            )
            if edit_form is None:
                raise RuntimeError("Form edit comment không hiển thị.")

            # --- Update text ---
            if not _update_comment_text_in_form(edit_form, sheet_comment_raw, new_comment_raw, page):
                raise RuntimeError("Không thể cập nhật text trong form edit.")

            # --- Click Save changes ---
            edit_scope = _comment_edit_scope_from_form(edit_form)
            if not _click_save_comment_changes(page, edit_scope):
                raise RuntimeError("Không tìm thấy hoặc click được Save changes button.")

            # --- Verify: comment cũ ẩn, text mới hiện ---
            try:
                old_text_pattern = _detail_comment_text_pattern(comment_text)
                page.locator("main").get_by_text(old_text_pattern).first.wait_for(
                    state="hidden",
                    timeout=10000,
                )
            except PlaywrightTimeoutError:
                logger.warning("Old comment text vẫn hiển thị sau khi save, có thể cần refresh.")

            page.wait_for_timeout(1000)

            logger.info(
                "Successfully edited comment on LinkedIn. "
                f"Old: {comment_text[:50]}... New: {new_comment_text[:50]}... URL: {post_url_normalized}"
            )

            context.close()
            browser.close()

            return (resolved_session_id, post_url_normalized)

        except PlaywrightTimeoutError as exc:
            browser.close()
            raise RuntimeError(f"Playwright timeout khi chỉnh sửa comment: {str(exc)}") from exc
        except Error as exc:
            browser.close()
            raise RuntimeError(f"Playwright error: {str(exc)}") from exc
        except Exception:
            browser.close()
            raise
