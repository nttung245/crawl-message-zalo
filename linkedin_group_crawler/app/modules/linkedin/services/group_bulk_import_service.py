"""Cào tên + số thành viên từ trang nhóm LinkedIn và gom payload gửi webhook (batch)."""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple
import json
import random
import re
from pathlib import Path
from urllib.parse import urlparse

from playwright.sync_api import Error, Page, sync_playwright

from app.core.config import settings
from app.modules.linkedin.services.auth_service import build_session_state_path
from app.core.logger import get_logger


logger = get_logger(__name__)

_MEMBER_COUNT_PATTERNS = (
    re.compile(r'"memberCount"\s*:\s*(\d+)', re.I),
    re.compile(r'"groupMemberCount"\s*:\s*(\d+)', re.I),
    re.compile(r'memberCount["\']?\s*[:=]\s*(\d+)', re.I),
)


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


def normalize_group_url(url: str) -> str:
    u = (url or "").strip()
    if not u:
        return u
    if not u.startswith(("http://", "https://")):
        u = "https://" + u
    parsed = urlparse(u)
    if not parsed.netloc.endswith("linkedin.com"):
        return u
    path = (parsed.path or "").rstrip("/") + "/"
    return f"{parsed.scheme}://{parsed.netloc}{path}"


def extract_member_count_from_html(html: str) -> Optional[int]:
    for pat in _MEMBER_COUNT_PATTERNS:
        m = pat.search(html or "")
        if m:
            try:
                return int(m.group(1))
            except (TypeError, ValueError):
                continue
    # "19,994 members" / "19994 members"
    m2 = re.search(
        r"([\d,]+)\s*(?:members?|thành viên|thanh vien)",
        (html or ""),
        re.I,
    )
    if m2:
        digits = re.sub(r"[^\d]", "", m2.group(1))
        if digits:
            try:
                return int(digits)
            except ValueError:
                return None
    return None


def _extract_group_name_from_page(page: Page) -> str:
    selectors = [
        "h1.groups-entity__name",
        "h1.groups-entity__name span",
        ".groups-hero__main-title",
        "h1",
    ]
    for sel in selectors:
        try:
            loc = page.locator(sel).first
            if loc.count() == 0:
                continue
            text = loc.inner_text(timeout=5000).strip()
            if text and "sign in" not in text.lower():
                return " ".join(text.split())
        except Error:
            logger.debug("Không đọc được tên nhóm với selector %s", sel, exc_info=True)
    return ""


def scrape_group_metadata(page: Page, group_url: str) -> Tuple[str, Optional[int]]:
    """Mở trang nhóm, trả về (name_group, member_count)."""

    page.goto(group_url, wait_until="domcontentloaded", timeout=90000)
    try:
        page.wait_for_load_state("load", timeout=20000)
    except Error:
        logger.debug("Group page load timeout; tiếp tục parse", exc_info=True)
    page.wait_for_timeout(2500)
    html = page.content()
    member = extract_member_count_from_html(html)
    name = _extract_group_name_from_page(page)
    return name, member


def bulk_scrape_groups(
    *,
    group_urls: List[str],
    session_id: Optional[str],
    email: Optional[str],
    delay_min_sec: float = 2.0,
    delay_max_sec: float = 5.0,
) -> List[Dict[str, Any]]:
    """Mở một browser context (có session nếu có), cào lần lượt từng URL."""

    normalized_urls = [normalize_group_url(u) for u in group_urls if (u or "").strip()]
    _, state_path = build_session_state_path(session_id=session_id, email=email)
    has_state = state_path.exists() and _state_has_li_at_cookie(state_path)
    if not has_state:
        logger.warning(
            "Không có session LinkedIn hợp lệ (li_at) cho email/session này — file mong đợi: %s. "
            "Hãy POST /login trước với cùng email (hoặc session_id) để cào nhóm không bị chặn login.",
            state_path,
        )

    results: List[Dict[str, Any]] = []

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
            for index, url in enumerate(normalized_urls):
                if index > 0 and delay_max_sec > 0:
                    time_sleep = random.uniform(
                        min(delay_min_sec, delay_max_sec),
                        max(delay_min_sec, delay_max_sec),
                    )
                    page.wait_for_timeout(int(time_sleep * 1000))
                item: Dict[str, Any] = {
                    "url_group": url,
                    "name_group": "",
                    "member": 0,
                    "memberCount": None,
                    "success": False,
                    "error": None,
                }
                try:
                    name, member = scrape_group_metadata(page, url)
                    item["name_group"] = name
                    item["memberCount"] = member
                    item["member"] = int(member) if member is not None else 0
                    item["success"] = bool(name) or member is not None
                    if not item["success"]:
                        item["error"] = "Không trích được tên hoặc số thành viên (có thể cần đăng nhập / URL sai)."
                except Exception as exc:
                    item["error"] = str(exc)
                    logger.warning("Lỗi cào nhóm %s: %s", url, exc)
                results.append(item)
        finally:
            context.close()
            browser.close()

    return results
