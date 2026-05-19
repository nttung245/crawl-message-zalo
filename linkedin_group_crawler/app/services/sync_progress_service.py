"""Service to sync LinkedIn post engagement (reaction and comments) for a user."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any, Final, Literal

from playwright.sync_api import Error, Locator, Page

from app.services.auth_service import build_session_state_path
from app.services.linkedin_engagement_session import ensure_linkedin_session_for_engagement
from app.services.playwright_browser_pool import run_with_linkedin_session_page
from app.services.linkedin_session_nav import goto_linkedin_url
from app.services.post_reaction_service import (
    REACTION_SELECTORS,
    _REACTION_STATE_LABEL_HINTS,
    _label_indicates_reaction_kind,
)
from app.services.post_comment_delete_service import _card_owned_by_self
from app.services.profile_comments_service import (
    _comment_text_from_root,
    _time_text_from_container,
)
from app.services.parser_service import (
    REACTION_SELECTORS as PARSER_REACTION_SELECTORS,
    COMMENT_SELECTORS as PARSER_COMMENT_SELECTORS,
    extract_number,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)

# Constants from other services or redefined for independence
_POST_DETAIL_SETTLE_MS: Final[int] = 3500

def _parse_linkedin_relative_date(text: str) -> str:
    """
    Converts LinkedIn relative time (e.g. '4d', '2w', '3m') to YYYY-MM-DD.
    's' -> seconds
    'm' -> minutes
    'h' -> hours
    'd' -> days
    'w' -> weeks
    'mo' -> months (30 days)
    'yr' -> years (365 days)
    """
    text = (text or "").strip().lower()
    if not text or any(x in text for x in ("vừa xong", "just now", "now", "mới đây")):
        return date.today().isoformat()
    
    # LinkedIn format is usually "4d", "2w", etc.
    # regex capture value and unit. Put 'mo' before 'm' to avoid partial matching.
    match = re.search(r"(\d+)\s*(mo|yr|w|d|h|m|s)", text)
    if not match:
        return date.today().isoformat()
    
    value = int(match.group(1))
    unit = match.group(2)
    
    today = date.today()
    if unit in ('s', 'm', 'h'):
        # For seconds, minutes, hours, current date is accurate enough for a day-level field
        return today.isoformat()
    elif unit == 'd':
        return (today - timedelta(days=value)).isoformat()
    elif unit == 'w':
        return (today - timedelta(weeks=value)).isoformat()
    elif unit == 'mo':
        return (today - timedelta(days=value * 30)).isoformat()
    elif unit == 'yr':
        return (today - timedelta(days=value * 365)).isoformat()
    
    return today.isoformat()

    return today.isoformat()

def load_more_comments(page: Page, max_rounds: int = 15):
    """Clicks 'Load more comments' and 'View replies' buttons and scrolls to reveal more."""
    try:
        # Combined selectors for main comments and nested replies
        load_more_selectors = [
            'button:has-text("Load more")',
            'button:has-text("Show more")',
            'button:has-text("View more")',
            'button:has-text("Xem thêm")',
            'button:has-text("Hiển thị thêm")',
            'button:has-text("replies")',
            'button:has-text("phản hồi")',
            'button:has-text("tất cả")',
            'button[aria-label*="Load more"]',
            'button[aria-label*="replies"]',
            'button[aria-label*="bình luận"]',
            'button[aria-label*="phản hồi"]',
        ]
        selector = ", ".join(load_more_selectors)
        
        for round_idx in range(max_rounds):
            load_more_btns = page.locator(selector)
            count = load_more_btns.count()
            
            clicked_any = False
            # Focus on visible buttons
            for i in range(count):
                btn = load_more_btns.nth(i)
                try:
                    if btn.is_visible():
                        # Scroll to button to ensure it's clickable
                        btn.scroll_into_view_if_needed()
                        btn.click(timeout=3000)
                        page.wait_for_timeout(1000)
                        clicked_any = True
                except Exception:
                    continue
            
            # Every 3 rounds, do a big scroll to trigger lazy loading
            if round_idx % 3 == 0 or not clicked_any:
                page.mouse.wheel(0, 2000)
                page.wait_for_timeout(1200)
            
            # If no buttons found and we already scrolled, we might be at the end
            if not clicked_any and round_idx > 3:
                # One last check for hidden ones
                if page.locator(selector).filter(visible=True).count() == 0:
                    break
                    
    except Exception as exc:
        logger.debug("Load more comments issue: %s", exc)

def detect_current_reaction(page: Page) -> str | None:
    """Detects the current reaction of the user on the main post."""
    try:
        post_root = page.locator("main").first
        if post_root.count() == 0:
            return None

        # 1. Find the main reaction button for the post (first one found)
        selectors = [
            'button[aria-label*="React Like"]',
            'button[aria-label*="Like"]',
            'button[aria-label*="Liked"]',
            'button[aria-label*="React"]',
            'button:has-text("Like")',
            'button:has-text("Liked")',
            'button:has-text("Thích")',
        ]
        reaction_button = post_root.locator(", ".join(selectors)).first
        
        if not reaction_button.is_visible():
            return None
            
        # 2. Analyze the button state
        aria_label = (reaction_button.get_attribute("aria-label") or "").strip().lower()
        text = reaction_button.inner_text().strip().lower()
        aria_pressed = reaction_button.get_attribute("aria-pressed")
        
        combined = f"{aria_label} {text}"
        is_pressed = aria_pressed == "true"
        
        if not is_pressed:
            # Maybe LinkedIn doesn't use aria-pressed here, but the text/label implies it's reacted
            if re.search(r"\bliked\b", combined): return "like"
            if re.search(r"\bloved\b|\blove\b", combined) and not re.search(r"react love", combined): return "love"
            if re.search(r"\bcelebrated\b|\bcelebrate\b", combined) and not re.search(r"react celebrate", combined): return "celebrate"
            if re.search(r"\bsupported\b|\bsupport\b", combined) and not re.search(r"react support", combined): return "support"
            if re.search(r"\binsightful\b", combined) and not re.search(r"react insightful", combined): return "insightful"
            if re.search(r"\bfunny\b", combined) and not re.search(r"react funny", combined): return "funny"
            return None
            
        # If pressed, check what reaction it is
        if re.search(r"\blike|liked|thích\b", combined): return "like"
        if re.search(r"\blove|loved|yêu thích\b", combined): return "love"
        if re.search(r"\bcelebrate|celebrated|chúc mừng\b", combined): return "celebrate"
        if re.search(r"\bsupport|supported|ủng hộ\b", combined): return "support"
        if re.search(r"\binsightful|sâu sắc\b", combined): return "insightful"
        if re.search(r"\bfunny|hài hước\b", combined): return "funny"
        
        return "like" # default if pressed but unknown
        
    except Exception as exc:
        logger.warning("Failed to detect reaction: %s", exc)
    
    return None

def extract_post_metrics(page: Page) -> dict[str, int]:
    """Extracts total reaction count and total comment count from the post page."""
    metrics = {"total_reactions": 0, "total_comments": 0}
    try:
        post_root = page.locator("main").first
        if post_root.count() == 0:
            post_root = page # Fallback to full page if main not found
            
        # 1. Try standard selectors (reusing parser_service but checking aria-label too)
        likes_text = ""
        for selector in PARSER_REACTION_SELECTORS:
            try:
                element = post_root.locator(selector).first
                if element.count() > 0:
                    # Prefer aria-label for counts
                    val = (element.get_attribute("aria-label") or "").strip()
                    if not val or not any(c.isdigit() for c in val):
                        val = element.inner_text().strip()
                    if val:
                        likes_text = val
                        break
            except Exception: continue
        
        # 2. Text-based regex search fallback for reactions
        if not likes_text or extract_number(likes_text) == 0:
            try:
                # Look for patterns like "15 reactions", "15 lượt thích"
                # Using a broad but targeted search on common tags
                reaction_patterns = [r"\d+.*reaction", r"\d+.*lượt thích", r"\d+.*thích"]
                for pattern in reaction_patterns:
                    loc = post_root.locator("span, a, button, p").filter(has_text=re.compile(pattern, re.I)).first
                    if loc.count() > 0:
                        txt = loc.inner_text().strip()
                        if txt:
                            likes_text = txt
                            break
            except Exception: pass

        comments_text = ""
        for selector in PARSER_COMMENT_SELECTORS:
            try:
                element = post_root.locator(selector).first
                if element.count() > 0:
                    val = (element.get_attribute("aria-label") or "").strip()
                    if not val or not any(c.isdigit() for c in val):
                        val = element.inner_text().strip()
                    if val:
                        comments_text = val
                        break
            except Exception: continue

        # 4. Text-based regex search fallback for comments
        if not comments_text or extract_number(comments_text) == 0:
            try:
                comment_patterns = [r"\d+.*comment", r"\d+.*bình luận"]
                for pattern in comment_patterns:
                    loc = post_root.locator("span, a, button, p").filter(has_text=re.compile(pattern, re.I)).first
                    if loc.count() > 0:
                        txt = loc.inner_text().strip()
                        if txt:
                            comments_text = txt
                            break
            except Exception: pass

        metrics["total_reactions"] = extract_number(likes_text)
        metrics["total_comments"] = extract_number(comments_text)
        
        logger.debug("Extracted metrics: %s (from raw: likes='%s', comments='%s')", 
                     metrics, likes_text, comments_text)
        
    except Exception as exc:
        logger.warning("Failed to extract post metrics: %s", exc)
    
    return metrics

def get_my_comment_blocks_by_you(page: Page) -> list[Locator]:
    """Finds comment blocks by looking for the '• You' or '• Bạn' marker."""
    blocks = []
    try:
        you_markers = page.locator("text=/•\\s*(You|Bạn)/i")
        count = you_markers.count()
        
        for i in range(count):
            marker = you_markers.nth(i)
            # Find the closest ancestor that represents the full comment container
            block = marker.locator(
                "xpath=ancestor::*["
                "starts-with(@componentkey, 'replaceableComment') or "
                "contains(@class, 'comments-comment-entity') or "
                "contains(@class, 'comments-comment-item') or "
                "contains(@class, 'comment-item') or "
                "contains(@class, 'comments-reply-item')"
                "][1]"
            )
            if block.count() > 0 and block.first.is_visible():
                blocks.append(block.first)
    except Exception as exc:
        logger.warning("Error finding comment blocks by You marker: %s", exc)
    return blocks

def extract_comment_text(comment_block: Locator) -> str | None:
    """Extracts cleaned text from a comment block using standardized logic."""
    try:
        # Sử dụng chung hàm chuẩn đã được fix logic lọc rác (---, impressions, etc.)
        text = _comment_text_from_root(comment_block)
        return text if text else None
    except Exception:
        return None

def collect_user_comments(page: Page, profile_slug: str) -> list[dict[str, str]]:
    """Collects all comments made by the user on the current post page."""
    user_comments = []
    try:
        # 1. Load all comments first
        load_more_comments(page)
        
        # 2. Extract blocks using the robust "You" marker strategy
        my_blocks = get_my_comment_blocks_by_you(page)
        
        seen_contents = set()
        for block in my_blocks:
            # Extract content using specialized extraction logic
            content = extract_comment_text(block)
            
            # Extract date/time text (reusing existing reliable helper)
            time_text = _time_text_from_container(block)
            
            # Final fallback if extract_comment_text somehow returns empty but block is valid
            if not content:
                raw_full = block.inner_text()
                if raw_full:
                    # Very basic fallback
                    lines = raw_full.split("\n")
                    if len(lines) > 2:
                        content = lines[2].strip()
            
            if content and content not in seen_contents:
                seen_contents.add(content)
                abs_date = _parse_linkedin_relative_date(time_text)
                user_comments.append({
                    "comment_content": content,
                    "ngày comment": abs_date
                })
                
    except Exception as exc:
        logger.warning("Failed to collect comments: %s", exc)
        
    return user_comments

def sync_post_engagement_on_page(
    page: Page,
    post_url: str,
    profile_slug: str,
    timeout_ms: int = 300000,
) -> dict[str, Any]:
    """Syncs engagement for a post using an already open page."""
    logger.info("Syncing engagement on page for %s", post_url)
    try:
        # Sử dụng goto_linkedin_url để kiểm tra chính xác trạng thái auth và xử lý nếu bị redirect login
        goto_linkedin_url(
            page.context,
            page,
            post_url,
            timeout_ms=timeout_ms,
            post_load_wait_ms=_POST_DETAIL_SETTLE_MS,
        )
        
        reaction = detect_current_reaction(page)
        comments = collect_user_comments(page, profile_slug)
        metrics = extract_post_metrics(page)
        
        return {
            "post_url": post_url,
            "reaction": reaction,
            "comments": comments,
            "total_reactions": metrics["total_reactions"],
            "total_comments": metrics["total_comments"],
        }
    except Exception as exc:
        logger.error("Failed to sync engagement for %s: %s", post_url, exc)
        return {
            "post_url": post_url,
            "reaction": None,
            "comments": [],
            "error": str(exc)
        }

def sync_post_engagement(
    post_url: str,
    profile_slug: str,
    session_id: str | None = None,
    email: str | None = None,
    timeout_ms: int = 300000,
    password: str | None = None,
    auto_login: bool = True,
) -> dict[str, Any]:
    """Opens a post in a new browser and returns current engagement data."""

    if auto_login:
        # Luôn force_relogin=True mỗi lần chạy sync để đảm bảo lấy cookie tươi nhất trước khi vào bài viết
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
        if not state_path.is_file():
            raise FileNotFoundError(f"Session not found at {state_path}")

    def _action(page: Page) -> dict[str, Any]:
        page.set_default_timeout(timeout_ms)
        result = sync_post_engagement_on_page(page, post_url, profile_slug, timeout_ms)
        result["session_id"] = normalized_session_id
        return result

    try:
        return run_with_linkedin_session_page(
            state_path=state_path,
            persist_state=True,
            action=_action,
        )
    except RuntimeError as exc:
        err_msg = str(exc)
        is_auth_err = any(hint in err_msg for hint in ("chưa đăng nhập", "login/guest/cold-join", "session hết hạn"))
        if is_auth_err and auto_login:
            logger.warning(
                "Phát hiện session hết hạn hoặc không hợp lệ khi đồng bộ bài viết. Đang thực hiện auto-login lại..."
            )
            # Re-resolve and force fresh login
            normalized_session_id, state_path = ensure_linkedin_session_for_engagement(
                email=email,
                session_id=session_id,
                password=password,
                force_relogin=True,
            )
            # Retry running the action
            return run_with_linkedin_session_page(
                state_path=state_path,
                persist_state=True,
                action=_action,
            )
        else:
            raise
