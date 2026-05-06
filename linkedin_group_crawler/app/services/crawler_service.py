"""Playwright crawler service for LinkedIn groups."""

from __future__ import annotations

from datetime import datetime
import json
import random
from typing import Any
from urllib.parse import urlparse

from playwright.sync_api import Error, Page, sync_playwright

from app.config import settings
from app.services.auth_service import build_session_state_path
from app.services.parser_service import parse_post_locator
from app.utils.file_utils import ensure_directory, save_text_file
from app.utils.logger import get_logger


logger = get_logger(__name__)

# LinkedIn frequently changes feed/group DOM; keep fallback selectors to reduce breakage.
POST_SELECTORS = [
    'div[data-id^="urn:li:activity"]',
    'article[data-urn*="urn:li:activity"]',
    "article.feed-shared-update-v2",
    "div.feed-shared-update-v2",
    "div.occludable-update",
]
GROUP_NAME_SELECTORS = [
    "h1",
    '[data-test-id*="group-name"]',
    '[data-test-id*="groups-name"]',
    ".groups-hero__main-title",
]


def _state_has_li_at_cookie(state_path) -> bool:
    """Check state file contains LinkedIn auth cookie li_at."""

    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
        cookies = payload.get("cookies") if isinstance(payload, dict) else None
        if not isinstance(cookies, list):
            return False

        for cookie in cookies:
            if not isinstance(cookie, dict):
                continue
            name = str(cookie.get("name", "")).strip()
            value = str(cookie.get("value", "")).strip()
            if name == "li_at" and value:
                return True
        return False
    except Exception:
        logger.exception("Failed to validate LinkedIn state file at %s", state_path)
        return False


def _is_login_url(url: str) -> bool:
    """Return True when LinkedIn navigation lands on an auth page."""

    parsed = urlparse((url or "").strip())
    path = (parsed.path or "").lower()
    return any(path.startswith(prefix) for prefix in ["/login", "/checkpoint", "/authwall"])


def _is_expected_group_url(expected_url: str, actual_url: str) -> bool:
    """Check final URL is still within the target LinkedIn group path."""

    expected = urlparse(expected_url.strip())
    actual = urlparse((actual_url or "").strip())

    expected_path = (expected.path or "").rstrip("/").lower()
    actual_path = (actual.path or "").rstrip("/").lower()

    if not expected_path:
        return False

    return actual.netloc.endswith("linkedin.com") and (
        actual_path == expected_path or actual_path.startswith(f"{expected_path}/")
    )


def _take_error_screenshot(page: Page, filename: str = "error.png") -> str:
    screenshot_path = settings.raw_data_dir / filename
    ensure_directory(screenshot_path.parent)
    page.screenshot(path=str(screenshot_path), full_page=True)
    return str(screenshot_path)


def _goto_group_page(page: Page, group_url: str) -> None:
    """Navigate to a group page without relying on networkidle, which is unstable on LinkedIn."""

    try:
        page.goto(group_url, wait_until="domcontentloaded", timeout=60000)
    except Error as exc:
        current_url = page.url or ""
        if _is_expected_group_url(group_url, current_url):
            logger.warning(
                "Group navigation raised an error after reaching the target page; continuing. url=%s error=%s",
                current_url,
                exc,
            )
        else:
            raise

    try:
        page.wait_for_load_state("load", timeout=15000)
    except Error:
        logger.debug("Group page did not reach full load state in time; continuing with manual wait", exc_info=True)

    page.wait_for_timeout(5000)


def _locate_post_elements(page: Page):
    """Return the first locator that finds LinkedIn post elements."""

    for selector in POST_SELECTORS:
        locator = page.locator(selector)
        try:
            if locator.count() > 0:
                logger.info("Using post selector: %s", selector)
                return locator
        except Error:
            logger.debug("Selector check failed for %s", selector, exc_info=True)
    return page.locator(POST_SELECTORS[0])


def _extract_group_name(page: Page) -> str:
    """Extract group name from the group page with selector fallbacks."""

    for selector in GROUP_NAME_SELECTORS:
        try:
            locator = page.locator(selector).first
            if locator.count() == 0:
                continue
            text = locator.inner_text(timeout=2000).strip()
            if text and "sign in" not in text.lower():
                return text
        except Error:
            logger.debug("Could not extract group name with selector %s", selector, exc_info=True)

    try:
        title = page.title().strip()
        if title:
            return title.split("|")[0].strip()
    except Error:
        logger.debug("Could not read page title for group name fallback", exc_info=True)

    return ""


def _next_scroll_delay_ms(
    *,
    scroll_delay_min_ms: int | None = None,
    scroll_delay_max_ms: int | None = None,
) -> int:
    """Return a randomized delay between scroll actions."""

    lo = settings.default_scroll_delay_min_ms if scroll_delay_min_ms is None else scroll_delay_min_ms
    hi = settings.default_scroll_delay_max_ms if scroll_delay_max_ms is None else scroll_delay_max_ms
    min_delay = min(lo, hi)
    max_delay = max(lo, hi)
    return random.randint(min_delay, max_delay)


def open_group_and_collect_posts(
    session_id: str | None,
    email: str | None,
    group_url: str,
    max_items: int | None = None,
    save_raw_html: bool = True,
    scroll_times_override: int | None = None,
    scroll_delay_min_ms: int | None = None,
    scroll_delay_max_ms: int | None = None,
) -> dict[str, Any]:
    """Open a LinkedIn group page, scroll, and parse post data."""

    normalized_session_id, state_path = build_session_state_path(session_id=session_id, email=email)

    if not state_path.exists():
        raise FileNotFoundError(
            f"LinkedIn state file not found for session_id '{normalized_session_id}'. Call POST /login first."
        )

    if not _state_has_li_at_cookie(state_path):
        raise RuntimeError(
            f"LinkedIn state file for session_id '{normalized_session_id}' is missing auth cookie (li_at). "
            "Relogin via POST /login before crawling."
        )

    crawl_time = datetime.now()
    max_items = max_items or settings.default_max_items
    scroll_times = scroll_times_override if scroll_times_override is not None else settings.default_scroll_times
    ensure_directory(settings.raw_data_dir)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(
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
            logger.info("Opening group URL directly using saved LinkedIn session: %s", group_url)
            _goto_group_page(page, group_url)

            if _is_login_url(page.url):
                logger.warning("Session redirected to login/checkpoint. Retrying group navigation once.")
                _goto_group_page(page, group_url)

            if _is_login_url(page.url):
                raise RuntimeError(
                    "LinkedIn session is invalid or expired (redirected to login/checkpoint). "
                    "Relogin via POST /login."
                )

            if not _is_expected_group_url(group_url, page.url):
                screenshot_path = _take_error_screenshot(page, "unexpected_group_redirect.png")
                raise RuntimeError(
                    "LinkedIn did not stay on the requested group page after navigation. "
                    f"Expected group URL: {group_url}. Final URL: {page.url}. "
                    f"Screenshot saved to {screenshot_path}"
                )

            group_name = _extract_group_name(page)
            context.storage_state(path=str(state_path))

            for scroll_index in range(scroll_times):
                page.mouse.wheel(0, 3000)
                scroll_delay_ms = _next_scroll_delay_ms(
                    scroll_delay_min_ms=scroll_delay_min_ms,
                    scroll_delay_max_ms=scroll_delay_max_ms,
                )
                page.wait_for_timeout(scroll_delay_ms)
                locator = _locate_post_elements(page)
                count = locator.count()
                logger.info(
                    "Scroll %s/%s collected %s posts after %sms delay",
                    scroll_index + 1,
                    scroll_times,
                    count,
                    scroll_delay_ms,
                )
                if count >= max_items:
                    break

            # Đợi thêm để lazy-render / layout ổn định trước khi dump HTML và parse.
            page.wait_for_timeout(2500)

            locator = _locate_post_elements(page)
            total_found = min(locator.count(), max_items)
            logger.info("Preparing to parse %s posts", total_found)

            if save_raw_html:
                html_path = settings.raw_data_dir / "last_group_page.html"
                save_text_file(html_path, page.content())

            posts: list[dict[str, Any]] = []
            for index in range(total_found):
                item = locator.nth(index)
                parsed = parse_post_locator(item)
                if parsed:
                    posts.append(parsed)

            if not posts:
                logger.warning("No posts found on the group page")

            return {
                "session_id": normalized_session_id,
                "crawl_time": crawl_time,
                "group_url": group_url,
                "group_name": group_name,
                "posts": posts,
                "total_posts_scraped": total_found,
            }
        except Error as exc:
            screenshot_path = _take_error_screenshot(page)
            logger.exception("Crawl failed; screenshot saved to %s", screenshot_path)
            raise RuntimeError(f"Crawl failed: {exc}. Screenshot saved to {screenshot_path}") from exc
        except Exception as exc:
            screenshot_path = _take_error_screenshot(page)
            logger.exception("Crawl failed; screenshot saved to %s", screenshot_path)
            raise RuntimeError(f"{exc}. Screenshot saved to {screenshot_path}") from exc
        finally:
            context.close()
            browser.close()
