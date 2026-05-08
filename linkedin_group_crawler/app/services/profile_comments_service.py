"""Crawl LinkedIn profile recent activity — comments tab (by public_id)."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import parse_qs, unquote, urljoin, urlparse

from playwright.sync_api import Error, Locator, Page, sync_playwright

from app.config import settings
from app.services.auth_service import build_session_state_path
from app.utils.logger import get_logger


logger = get_logger(__name__)

_TIME_TEXT_RE = re.compile(r"^\d+\s*(s|m|h|d|w|mo|yr)$", re.IGNORECASE)
_GROUP_POST_PATH_RE = re.compile(r"urn:li:groupPost:([^/?]+)", re.IGNORECASE)
_ACTIVITY_PATH_RE = re.compile(r"urn:li:activity:([^/?]+)", re.IGNORECASE)
_FSD_COMMENT_RE = re.compile(
    r"urn:li:fsd_comment:\s*\(\s*(\d+)\s*,\s*([^)]+)\)",
    re.IGNORECASE | re.DOTALL,
)


class LinkedinLoginRequiredError(Exception):
    """Trang yêu cầu đăng nhập / checkpoint."""


def _state_has_li_at_cookie(state_path) -> bool:
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


def _is_login_url(url: str) -> bool:
    parsed = urlparse((url or "").strip())
    path = (parsed.path or "").lower()
    return any(path.startswith(p) for p in ("/login", "/checkpoint", "/authwall"))


def _is_login_form_visible(page: Page) -> bool:
    try:
        pw = page.locator('input[type="password"]').first
        if pw.count() > 0 and pw.is_visible(timeout=1500):
            return True
    except Error:
        pass
    try:
        sk = page.locator('input[name="session_key"]').first
        if sk.count() > 0 and sk.is_visible(timeout=800):
            return True
    except Error:
        pass
    return False


def build_profile_urls(public_id: str) -> tuple[str, str]:
    slug = (public_id or "").strip().strip("/")
    base = f"https://www.linkedin.com/in/{slug}/"
    comments = f"https://www.linkedin.com/in/{slug}/recent-activity/comments/"
    return base, comments


def _absolute_href(page: Page, href: str | None) -> str:
    if not href:
        return ""
    if href.startswith(("http://", "https://")):
        return href
    return urljoin(page.url or "https://www.linkedin.com/", href)


def parse_comment_activity_href(href: str, page_url: str = "") -> dict[str, Any] | None:
    """Parse decoded activity URL + dashCommentUrn → type, ids, activity_url."""

    if not href or "dashCommentUrn" not in href:
        return None
    abs_href = href if href.startswith(("http://", "https://")) else urljoin(page_url or "https://www.linkedin.com/", href)
    parsed = urlparse(abs_href)
    activity_path = unquote(parsed.path or "")
    qs = parse_qs(parsed.query, keep_blank_values=True)
    dash_raw = (qs.get("dashCommentUrn") or [None])[0]
    if not dash_raw:
        return None
    dash_decoded = unquote(dash_raw)
    m_comment = _FSD_COMMENT_RE.search(dash_decoded)
    comment_id = m_comment.group(1) if m_comment else None

    gm = _GROUP_POST_PATH_RE.search(activity_path) or _GROUP_POST_PATH_RE.search(abs_href)
    am = _ACTIVITY_PATH_RE.search(activity_path) or _ACTIVITY_PATH_RE.search(abs_href)

    if gm:
        rest = gm.group(1).strip()
        # group_id-post_id (post_id is numeric tail after last hyphen between two numeric segments)
        if "-" in rest:
            left, right = rest.rsplit("-", 1)
            if left.isdigit() and right.isdigit():
                group_id, post_id = left, right
            else:
                # fallback: first segment group, rest post
                parts = rest.split("-", 1)
                group_id, post_id = parts[0], parts[1] if len(parts) > 1 else rest
        else:
            return None
        base_url = abs_href.split("?", 1)[0]
        return {
            "type": "groupPost",
            "group_id": str(group_id),
            "post_id": str(post_id),
            "comment_id": str(comment_id) if comment_id else None,
            "activity_url": base_url,
        }

    if am:
        post_id = am.group(1).strip()
        base_url = abs_href.split("?", 1)[0]
        return {
            "type": "activity",
            "group_id": None,
            "post_id": str(post_id),
            "comment_id": str(comment_id) if comment_id else None,
            "activity_url": base_url,
        }

    return None


def _time_text_from_container(root: Locator) -> str:
    try:
        paragraphs = root.locator("p")
        n = paragraphs.count()
        for i in range(min(n, 40)):
            try:
                text = paragraphs.nth(i).inner_text(timeout=800).strip()
                if not text:
                    continue
                compact = re.sub(r"\s+", "", text)
                if _TIME_TEXT_RE.match(compact) or _TIME_TEXT_RE.match(text.strip()):
                    return text.strip()
            except Error:
                continue
    except Error:
        pass
    return ""


def _comment_text_from_root(root: Locator) -> str:
    try:
        box = root.locator('[data-testid="expandable-text-box"]').first
        if box.count() == 0:
            return ""
        return box.inner_text(timeout=3000).strip()
    except Error:
        return ""


def _expandable_root_for_link(link: Locator) -> Locator:
    """Ancestor gần nhất có [data-testid=expandable-text-box] (không dùng class LinkedIn random)."""

    try:
        scoped = link.locator(
            'xpath=ancestor::*[.//*[@data-testid="expandable-text-box"]][1]',
        )
        if scoped.count() > 0:
            return scoped
    except Error:
        pass
    return link.locator("xpath=..")


def _parse_row(link: Locator, page: Page) -> dict[str, Any] | None:
    try:
        href = link.get_attribute("href")
    except Error:
        return None
    abs_href = _absolute_href(page, href)
    parsed = parse_comment_activity_href(abs_href, page_url=page.url or "")
    if not parsed:
        return None
    root = _expandable_root_for_link(link)
    comment_text = _comment_text_from_root(root)
    time_text = _time_text_from_container(root)

    row: dict[str, Any] = {
        "type": parsed["type"],
        "post_id": parsed["post_id"],
        "comment_id": parsed.get("comment_id"),
        "comment_text": comment_text,
        "time_text": time_text,
        "activity_url": parsed.get("activity_url") or abs_href.split("?")[0],
    }
    if parsed["type"] == "groupPost" and parsed.get("group_id"):
        row["group_id"] = parsed["group_id"]
    return row


def _unique_key(row: dict[str, Any]) -> str:
    cid = row.get("comment_id")
    if cid:
        return f"c:{cid}"
    return f"p:{row.get('post_id','')}:{row.get('comment_text','')[:120]}:{row.get('time_text','')}"


def crawl_profile_comments(
    *,
    public_id: str,
    max_items: int,
    target_post_id: str | None,
    session_id: str | None,
    email: str | None,
) -> dict[str, Any]:
    """Mở comments_url, scroll, parse. Cần session (li_at) — nếu không có thì có thể gặp login."""

    slug = (public_id or "").strip().strip("/")
    profile_url, comments_url = build_profile_urls(slug)

    _, state_path = build_session_state_path(session_id=session_id, email=email)
    has_state = state_path.exists() and _state_has_li_at_cookie(state_path)

    collected: list[dict[str, Any]] = []
    seen: set[str] = set()
    max_items = max(1, min(max_items, 200))

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
        context = (
            browser.new_context(storage_state=str(state_path))
            if has_state
            else browser.new_context()
        )
        page = context.new_page()
        try:
            page.goto(comments_url, wait_until="domcontentloaded", timeout=90000)
            page.wait_for_timeout(3500)

            if _is_login_url(page.url) or _is_login_form_visible(page):
                raise LinkedinLoginRequiredError()

            # Chờ ít nhất một frame render (có thể 0 comment)
            try:
                page.wait_for_selector('a[href*="dashCommentUrn"]', timeout=15000)
            except Error:
                logger.debug("Không thấy anchor dashCommentUrn trong timeout — có thể không có comment")

            prev_link_count = -1
            stagnant_rounds = 0
            for _ in range(60):
                links = page.locator('a[href*="dashCommentUrn"]')
                link_count = links.count()
                prev_collected = len(collected)
                for i in range(link_count):
                    if len(collected) >= max_items:
                        break
                    link = links.nth(i)
                    try:
                        row = _parse_row(link, page)
                    except Error:
                        continue
                    if not row:
                        continue
                    key = _unique_key(row)
                    if key in seen:
                        continue
                    seen.add(key)
                    collected.append(row)
                if len(collected) >= max_items:
                    break
                if link_count == prev_link_count and len(collected) == prev_collected:
                    stagnant_rounds += 1
                    if stagnant_rounds >= 5:
                        break
                else:
                    stagnant_rounds = 0
                prev_link_count = link_count
                page.mouse.wheel(0, 2200)
                page.wait_for_timeout(1200)

        finally:
            context.close()
            browser.close()

    total = len(collected)
    if total == 0:
        tid = str(target_post_id).strip() if target_post_id else None
        return {
            "success": True,
            "code": "NO_COMMENTS_FOUND",
            "public_id": slug,
            "profile_url": profile_url,
            "comments_url": comments_url,
            "total_comments_found": 0,
            "target_post_id": tid,
            "has_commented_target_post": False if tid else None,
            "matched_comment_count": 0 if tid else None,
            "comments": [],
        }

    matched: list[dict[str, Any]] = []
    if target_post_id:
        tid = str(target_post_id).strip()
        for c in collected:
            if str(c.get("post_id") or "") == tid:
                matched.append(c)
        mcount = len(matched)
        return {
            "success": True,
            "code": "OK",
            "public_id": slug,
            "profile_url": profile_url,
            "comments_url": comments_url,
            "total_comments_found": total,
            "target_post_id": tid,
            "has_commented_target_post": mcount > 0,
            "matched_comment_count": mcount,
            "comments": matched,
        }

    return {
        "success": True,
        "code": "OK",
        "public_id": slug,
        "profile_url": profile_url,
        "comments_url": comments_url,
        "total_comments_found": total,
        "target_post_id": None,
        "has_commented_target_post": None,
        "matched_comment_count": None,
        "comments": collected[:max_items],
    }
