"""Playwright: xóa comment từ LinkedIn recent-activity/comments → vào deeplink dashCommentUrn → xóa."""

from __future__ import annotations

from typing import Dict, Final, List, Optional, Set, Tuple
import re
from urllib.parse import unquote, urlparse

from playwright.sync_api import Error, Locator, Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from app.core.config import settings
from app.modules.linkedin.services.auth_service import build_session_state_path
from app.modules.linkedin.services.profile_comments_service import (
    _comment_text_from_root,
    _expandable_root_for_link,
    _parse_row,
)
from app.modules.linkedin.services.post_reaction_sync_service import (
    linkedin_activity_id_from_url,
    posts_match_same_linkedin_post,
)
from app.core.logger import get_logger


logger = get_logger(__name__)

_RECENT_COMMENTS_URL_TEMPLATE = "https://www.linkedin.com/in/{profile_slug}/recent-activity/comments/"

_OWNER_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"(?:•\s*)?(?:You|Bạn)\b",
    re.I,
)
_MORE_LABEL_RE: Final[re.Pattern[str]] = re.compile(r"More|Thêm", re.I)
_COMMENT_OPTIONS_LABEL_RE: Final[re.Pattern[str]] = re.compile(
    r"View more options|Open options|Mở tùy chọn|options for|more options for|tùy chọn cho",
    re.I,
)
_DELETE_MENU_RE: Final[re.Pattern[str]] = re.compile(r"^(Delete|Xóa)$", re.I)

_COMMENT_ENTITY_ANCESTOR_XPATHS: Final[Tuple[str, ...]] = (
    'xpath=ancestor::*[.//button[contains(@aria-label,"View more options") or '
    'contains(@aria-label,"more options for") or contains(@aria-label,"Open options") or '
    '@aria-label="More" or @aria-label="Thêm"]][1]',
    'xpath=ancestor::article[contains(@class,"comments-comment-entity")][1]',
    'xpath=ancestor::*[contains(@class,"comments-comment-entity")][1]',
    'xpath=ancestor::*[.//button[@aria-label="More" or @aria-label="Thêm"]][1]',
)

_DETAIL_COMMENT_TEXT_SELECTORS: Final[Tuple[str, ...]] = (
    '[data-testid="expandable-text-box"]',
    ".comments-comment-item__main-content span[dir='ltr']",
    ".comments-comment-item__main-content",
)

_COMMENT_OPTIONS_TRIGGER_SELECTORS: Final[Tuple[str, ...]] = (
    'button[aria-label*="View more options"]',
    'button[aria-label*="more options for"]',
    ".comment-options-trigger button.artdeco-dropdown__trigger",
    ".comments-comment-meta__options button.artdeco-dropdown__trigger",
    'button.artdeco-dropdown__trigger:has(svg[aria-label*="Open options"])',
    'button.artdeco-dropdown__trigger:has(svg[aria-label*="options for"])',
    'button.artdeco-dropdown__trigger:has(.comment-options-dropdown__trigger-icon)',
    'button[aria-label*="Open options"]',
    'button[aria-label*="Mở tùy chọn"]',
    'button[aria-label*="options for"]',
)

_OPEN_COMMENT_DROPDOWN_SELECTOR: Final[str] = (
    ".artdeco-dropdown__content--is-open:visible, "
    ".artdeco-dropdown__content--is-dropdown-element:visible, "
    '[role="menu"]:visible'
)

_DELETE_MENU_ITEM_SELECTORS: Final[Tuple[str, ...]] = (
    '.artdeco-dropdown__content--is-open div[role="button"].option-button:has-text("Delete")',
    '.artdeco-dropdown__content--is-open div[role="button"].option-button:has-text("Xóa")',
    '.artdeco-dropdown__item.option-button .comment-options-dropdown__option-text:has-text("Delete")',
    '.artdeco-dropdown__item.option-button .comment-options-dropdown__option-text:has-text("Xóa")',
    'button[role="menuitem"][aria-label="Delete"]',
    '[role="menuitem"] button:has-text("Delete")',
    '[role="menuitem"]:has-text("Delete")',
    'button[role="menuitem"]:has-text("Xóa")',
    '[role="menuitem"]:has-text("Xóa")',
)

_DELETE_CONFIRMATION_BUTTON_SELECTORS: Final[Tuple[str, ...]] = (
    'button[aria-label*="Delete"]',
    'button:has-text("Delete")',
    'button:has-text("Xóa")',
)

_DELETE_CONFIRM_TIMEOUT_MS: Final[int] = 60000
_SCROLL_SETTLE_MS: Final[int] = 1000
_POST_DETAIL_SETTLE_MS: Final[int] = 2000
_RECENT_ACTIVITY_LOAD_MS: Final[int] = 2800

# Trích URN LinkedIn trong URL (activity, groupPost, ugcPost, share, article).
_LINKEDIN_URN_RE: Final[re.Pattern[str]] = re.compile(
    r"urn:li:(?:activity|groupPost|ugcPost|share|article):[0-9-]+",
    re.IGNORECASE,
)

_INVISIBLE_CHARS_RE: Final[re.Pattern[str]] = re.compile(
    r"[\u200b-\u200d\ufeff\u200e\u200f]",
)


def _normalize_compare_url(url: str) -> str:
    """Giống snippet TS: chỉ scheme+host+path, bỏ query, trailing slash."""
    raw = unquote((url or "").strip())
    if not raw:
        return ""
    if raw.startswith("//"):
        raw = f"https:{raw}"
    if not raw.startswith("http"):
        raw = f"https://www.linkedin.com{raw}" if raw.startswith("/") else raw
    try:
        u = urlparse(raw)
        path = (u.path or "").rstrip("/")
        if u.scheme and u.netloc:
            return f"{u.scheme}://{u.netloc}{path}"
    except Exception:
        pass
    return raw.split("?")[0].rstrip("/")


def _urn_post_fingerprints(url: str) -> Set[str]:
    """Chuỗi nhận dạng từ URN trong URL đã decode."""

    decoded = unquote((url or "").strip())
    out: Set[str] = set()
    for match in _LINKEDIN_URN_RE.finditer(decoded):
        token = match.group(0).strip().lower()
        if token:
            out.add(token)
    act = linkedin_activity_id_from_url(decoded)
    if act:
        out.add(f"activity:{act}")
    return out


def _urls_same_post(post_url: str, activity_href: str) -> bool:
    """So khớp bài giữa URL sheet và href activity/deeplink trên DOM."""
    full = (
        activity_href
        if activity_href.startswith(("http://", "https://"))
        else f"https://www.linkedin.com{activity_href}"
    )
    if posts_match_same_linkedin_post(post_url, full):
        return True
    fp_sheet = _urn_post_fingerprints(post_url)
    fp_href = _urn_post_fingerprints(full)
    if fp_sheet and fp_href and fp_sheet & fp_href:
        return True
    a = _normalize_compare_url(post_url)
    b = _normalize_compare_url(full)
    return bool(a and b and (b in a or a in b))


def _safe_visible(locator) -> bool:
    try:
        return bool(locator.is_visible())
    except Exception:
        return False


def _first_words_for_timeline_match(comment_text: str, *, word_count: int = 5) -> str:
    """Recent-activity thường truncate — chỉ khớp vài từ đầu."""

    return " ".join((comment_text or "").strip().split()[:word_count])


def _comment_text_pattern(comment_text: str) -> re.Pattern[str]:
    prefix = _first_words_for_timeline_match(comment_text)
    if not prefix:
        return re.compile(r"(?!)", re.IGNORECASE)
    return re.compile(re.escape(prefix), re.IGNORECASE)


def _detail_comment_text_pattern(comment_text: str) -> re.Pattern[str]:
    body = (comment_text or "").strip()
    if not body:
        return re.compile(r"(?!)", re.IGNORECASE)
    return re.compile(re.escape(body), re.IGNORECASE)


def _collapse_ws(value: str) -> str:
    return re.sub(r"\s+", " ", (value or "").strip())


def _sanitize_compare_text(value: str) -> str:
    """Bỏ ký tự ẩn (ZWSP, v.v.), gộp khoảng trắng — khớp text DOM với ô sheet."""

    return _collapse_ws(_INVISIBLE_CHARS_RE.sub("", value or ""))


def _truncate_timeline_match(dom_normalized: str, sheet_normalized: str) -> bool:
    """Timeline thường cắt comment (… hoặc ...); ô sheet có thể dài hơn DOM."""

    if not dom_normalized or not sheet_normalized:
        return False
    if dom_normalized.endswith("…") or dom_normalized.endswith("..."):
        stem = dom_normalized.removesuffix("…").removesuffix("...")
        stem = stem.rstrip(".").strip()
        if stem and sheet_normalized.lower().startswith(stem.lower()):
            return True
    if len(dom_normalized) <= len(sheet_normalized):
        short, long_ = dom_normalized, sheet_normalized
    else:
        short, long_ = sheet_normalized, dom_normalized
    if short.lower() == long_.lower():
        return True
    # Timeline thường cắt: DOM là prefix của đầy đủ ô sheet.
    if len(short) >= 4 and long_.lower().startswith(short.lower()):
        return True
    return False


def _comment_text_in_blob_relaxed(sheet_raw: str, blob: str) -> bool:
    """Ô timeline / inner_text card: tìm substring an toàn (tránh ô quá ngắn khớp nhầm)."""

    sheet = _sanitize_compare_text(sheet_raw)
    b = _sanitize_compare_text(blob)
    if not sheet or not b:
        return False
    if sheet.lower() == b.lower():
        return True
    if len(sheet) >= 4 and sheet.lower() in b.lower():
        return True
    return _truncate_timeline_match(b, sheet)


def _main_activity_root(page: Page) -> Locator:
    return page.locator("main, [role='main']").first


def _block_inner_text_safe(block: Locator) -> str:
    try:
        return block.inner_text(timeout=2500)
    except Error:
        return ""


def _wait_after_recent_activity_scroll(
    page: Page,
    timeline_pattern: re.Pattern[str],
    prev_count: int,
) -> None:
    """Chờ DOM đổi sau scroll thay vì sleep cố định."""

    try:
        page.wait_for_function(
            """({ regex, prev }) => {
              const nodes = Array.from(
                document.querySelectorAll('main *, [role="main"] *'),
              );
              const r = new RegExp(regex, 'i');
              const count = nodes.filter((n) =>
                r.test(n.textContent ?? ''),
              ).length;
              return count !== prev;
            }""",
            arg={"regex": timeline_pattern.pattern, "prev": prev_count},
            timeout=5000,
        )
    except (PlaywrightTimeoutError, Error):
        pass


def _absolute_activity_href(href: str) -> str:
    raw = (href or "").strip()
    if not raw:
        return ""
    if raw.startswith(("http://", "https://")):
        return raw
    return f"https://www.linkedin.com{raw}"


def _card_owned_by_self(card: Locator, profile_slug: str) -> bool:
    if _safe_visible(card.get_by_text(_OWNER_LABEL_RE)):
        return True
    blob = _block_inner_text_safe(card)
    if _OWNER_LABEL_RE.search(blob):
        return True
    slug = (profile_slug or "").strip().lower()
    if not slug:
        return False
    try:
        profile_link = card.locator(
            f'a[href*="/in/{profile_slug}"], a[href*="/in/{profile_slug}/"]',
        ).first
        return profile_link.count() > 0
    except Error:
        return False


def _card_comment_text_matches(
    card: Locator,
    pattern: re.Pattern[str],
    sheet_raw: str,
) -> bool:
    dom_box = ""
    try:
        dom_box = _comment_text_from_root(card)
    except Error:
        pass
    if _dom_comment_matches_sheet(dom_box, pattern, sheet_raw):
        return True
    blob = _block_inner_text_safe(card)
    if _dom_comment_matches_sheet(blob, pattern, sheet_raw):
        return True
    return _comment_text_in_blob_relaxed(sheet_raw, blob)


def _deeplink_via_owned_comment_on_timeline(
    page: Page,
    post_url: str,
    pattern: re.Pattern[str],
    sheet_raw: str,
    profile_slug: str,
) -> Optional[str]:
    """
    Timeline recent-activity: khớp comment của chính mình (You/Bạn hoặc /in/<slug>)
    trước khi bắt buộc postUrl trùng activity trên DOM.
    """

    root = _main_activity_root(page)
    links = root.locator(
        'a[href*="/feed/update/"], a[href*="/posts/"], a[href*="dashCommentUrn"]',
    )
    candidates: List[Tuple[str, bool]] = []

    for i in range(links.count()):
        link = links.nth(i)
        try:
            href = link.get_attribute("href") or ""
        except Error:
            continue
        full = _absolute_activity_href(href)
        if not full:
            continue
        try:
            card = _expandable_root_for_link(link)
        except Error:
            continue
        if not _card_owned_by_self(card, profile_slug):
            continue
        if not _card_comment_text_matches(card, pattern, sheet_raw):
            continue
        candidates.append((full, _urls_same_post(post_url, full)))

    if not candidates:
        return None

    post_matched = [href for href, matched in candidates if matched]
    if len(post_matched) == 1:
        return post_matched[0]
    if len(post_matched) > 1:
        raise ValueError(
            "Nhiều activity trên timeline cùng khớp commentText của bạn và postUrl — "
            "dừng để tránh xóa nhầm."
        )

    unique_hrefs = {href for href, _ in candidates}
    if len(unique_hrefs) == 1:
        sole = next(iter(unique_hrefs))
        logger.warning(
            "[recent] khớp commentText + You/Bạn, postUrl sheet không trùng activity timeline — "
            "dùng href timeline: %s…",
            sole[:160],
        )
        return sole

    return None


def _nudge_recent_activity_timeline(page: Page) -> None:
    """Cuộn timeline và bấm Load more nếu LinkedIn chưa render đủ item."""

    for selector in (
        'button[aria-label*="Load more comments"]',
        'button:has-text("Load more comments")',
        'button:has-text("Tải thêm bình luận")',
    ):
        btn = page.locator(selector).first
        if btn.count() <= 0 or not _safe_visible(btn):
            continue
        try:
            btn.click()
            page.wait_for_timeout(900)
        except Error:
            pass
        break

    page.mouse.wheel(0, 2200)
    page.wait_for_timeout(_SCROLL_SETTLE_MS)


def _deeplink_via_dashcomment_anchors(
    page,
    post_url: str,
    pattern: re.Pattern[str],
    sheet_raw: str,
) -> Optional[str]:
    """Giống ``crawl_profile_comments``: các ``a`` có dashCommentUrn + ``_parse_row``."""

    links = _main_activity_root(page).locator('a[href*="dashCommentUrn"]')
    same_post: List[Tuple[str, Locator]] = []
    n_links = links.count()

    for i in range(n_links):
        link = links.nth(i)
        try:
            href = link.get_attribute("href") or ""
        except Error:
            continue
        if not href:
            continue
        full = (
            href
            if href.startswith(("http://", "https://"))
            else f"https://www.linkedin.com{href}"
        )
        if not _urls_same_post(post_url, full):
            continue
        same_post.append((full, link))

    text_hits = []
    for full, link in same_post:
        try:
            row = _parse_row(link, page)
        except Error:
            row = None
        if row and _dom_comment_matches_sheet(row.get("comment_text") or "", pattern, sheet_raw):
            text_hits.append(full)

    if len(text_hits) == 1:
        return text_hits[0]
    if len(text_hits) > 1:
        raise ValueError(
            "Nhiều deeplink cùng URL bài và cùng nội dung comment trên recent-activity — "
            "dừng để tránh xóa nhầm."
        )

    if len(text_hits) == 0 and len(same_post) == 1:
        sole, _lnk = same_post[0]
        return sole

    return None


def _deeplink_via_comment_text_near_activity_anchor(
    page,
    post_url: str,
    pattern: re.Pattern[str],
    profile_slug: str,
) -> Optional[str]:
    """Fallback: getByText → ancestor có link bài (/feed/update, /posts, dashComment)."""

    root = _main_activity_root(page)
    text_candidates = root.get_by_text(pattern)
    count = text_candidates.count()
    xpath = (
        "xpath=ancestor::a[(contains(@href, \"/feed/update/\") or "
        'contains(@href, "/posts/") or '
        'contains(@href, "dashCommentUrn"))][1]'
    )
    activity_block_xpath = (
        "xpath=ancestor::*[.//a[contains(@href, '/feed/update/') or "
        "contains(@href, '/posts/') or contains(@href, 'dashCommentUrn')]][1]"
    )

    for i in range(count):
        text_node = text_candidates.nth(i)
        activity_link = text_node.locator(xpath)

        if not _safe_visible(activity_link):
            continue

        href = activity_link.get_attribute("href") or ""
        if not href:
            continue

        full_href = (
            href
            if href.startswith(("http://", "https://"))
            else f"https://www.linkedin.com{href}"
        )
        if _urls_same_post(post_url, full_href):
            return full_href

        activity_block = text_node.locator(activity_block_xpath)
        block_text = _block_inner_text_safe(activity_block)
        slug_token = (profile_slug or "").strip().lower()
        if not slug_token or slug_token not in block_text.lower():
            continue

        try:
            hrefs = activity_block.locator("a[href]").evaluate_all(
                "els => els.map((a) => a.href || a.getAttribute('href') || '')",
            )
        except Error:
            hrefs = []

        fallback_href = next(
            (h for h in hrefs if h and "dashCommentUrn" in h),
            None,
        )
        if fallback_href:
            logger.warning(
                "[recent] fallback with profileSlug validation: %s…",
                fallback_href[:160],
            )
            return (
                fallback_href
                if fallback_href.startswith(("http://", "https://"))
                else f"https://www.linkedin.com{fallback_href}"
            )

    return None


def _deeplink_via_feed_post_cards_matching_text(
    page: Page,
    post_url: str,
    pattern: re.Pattern[str],
    sheet_raw: str,
) -> Optional[str]:
    """
    LinkedIn không lúc nào cũng đặt ``dashCommentUrn`` trên ``<a>`` timeline.
    Quét ``/feed/update/`` và ``/posts/`` khớp bài, đọc text trong card (expandable hoặc inner_text).
    """

    root = _main_activity_root(page)
    links = root.locator('a[href*="/feed/update/"], a[href*="/posts/"]')
    n_links = links.count()

    score_by_href: Dict[str, int] = {}

    def _remember(href_full: str) -> None:
        key = href_full.strip()
        if not key:
            return
        prefer = 2 if "dashCommentUrn" in key else 1
        prev = score_by_href.get(key, 0)
        score_by_href[key] = max(prev, prefer)

    for i in range(n_links):
        link = links.nth(i)
        try:
            href = link.get_attribute("href") or ""
        except Error:
            continue
        if not href:
            continue
        full = (
            href
            if href.startswith(("http://", "https://"))
            else f"https://www.linkedin.com{href}"
        )
        if not _urls_same_post(post_url, full):
            continue

        try:
            card = _expandable_root_for_link(link)
        except Error:
            continue

        dom_box = ""
        try:
            dom_box = _comment_text_from_root(card)
        except Error:
            pass

        if _dom_comment_matches_sheet(dom_box, pattern, sheet_raw):
            _remember(full)
            continue

        blob = ""
        try:
            blob = card.inner_text(timeout=2500)
        except Error:
            pass
        if _dom_comment_matches_sheet(blob, pattern, sheet_raw):
            _remember(full)
            continue
        if _comment_text_in_blob_relaxed(sheet_raw, blob):
            _remember(full)

    candidates = sorted(score_by_href.keys(), key=lambda h: (-score_by_href[h], h))
    if len(candidates) == 0:
        return None
    if len(candidates) == 1:
        return candidates[0]
    top = score_by_href[candidates[0]]
    tied = [h for h in candidates if score_by_href[h] == top]
    if len(tied) == 1:
        return tied[0]
    raise ValueError(
        "Nhiều link khác nhau trên timeline cùng khớp postUrl + commentText — dừng để tránh xóa nhầm."
    )


def _dom_comment_matches_sheet(
    dom_comment: str, pattern: re.Pattern[str], sheet_raw: str
) -> bool:
    """Khớp nội dung comment ô sheet với DOM (regex + whitespace chuẩn hoá)."""

    plain = _sanitize_compare_text(dom_comment)
    sheet = _sanitize_compare_text(sheet_raw)
    if not sheet:
        return False
    if pattern.search(dom_comment or "") or pattern.search(plain):
        return True
    if plain.lower() == sheet.lower():
        return True
    return _truncate_timeline_match(plain, sheet)


def _locator_dom_key(block: Locator) -> str:
    """Khóa ổn định theo node DOM — tránh đếm trùng một comment nhiều lần."""

    try:
        key = block.evaluate(
            """(node) => {
              const selfId = node.getAttribute?.('data-id')
                || node.getAttribute?.('componentkey')
                || node.getAttribute?.('id');
              if (selfId) return `self:${selfId}`;
              const box = node.querySelector?.('[data-testid="expandable-text-box"]');
              const btn = node.querySelector?.(
                'button[aria-label*="View more options"],'
                + 'button[aria-label*="more options for"],'
                + 'button[aria-label*="Open options"]',
              );
              const text = (box?.textContent || node.textContent || '').trim();
              const label = btn?.getAttribute?.('aria-label') || '';
              if (text || label) return `blob:${text}::${label}`;
              return `tag:${node.tagName}:${node.className || ''}`;
            }""",
        )
        return str(key or "").strip()
    except Error:
        return ""


def _dedupe_comment_blocks(blocks: List[Locator]) -> List[Locator]:
    unique: List[Locator] = []
    seen: Set[str] = set()
    for block in blocks:
        key = _locator_dom_key(block)
        if key:
            if key in seen:
                continue
            seen.add(key)
        unique.append(block)
    return unique


def _block_has_comment_options_menu(block: Locator) -> bool:
    trigger = block.locator(
        'button[aria-label*="View more options"], '
        'button[aria-label*="more options for"], '
        'button[aria-label*="Open options"], '
        'button.artdeco-dropdown__trigger',
    ).first
    return trigger.count() > 0 and _safe_visible(trigger)


def _detail_comment_body_text(block: Locator) -> str:
    try:
        host = block.locator('[data-testid="expandable-text-box"]').first
        if host.count() > 0:
            return _sanitize_compare_text(host.inner_text(timeout=1500))
    except Error:
        pass
    return _sanitize_compare_text(_block_inner_text_safe(block))


def _choose_detail_delete_block(
    blocks: List[Locator],
    sheet_raw: str,
    profile_slug: str,
) -> Optional[Locator]:
    """Chọn một khối comment để xóa khi DOM báo trùng text."""

    candidates = _dedupe_comment_blocks(blocks)
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    sheet = _sanitize_compare_text(sheet_raw)
    ranked: List[Tuple[int, int, int, Locator]] = []
    for block in candidates:
        if not _card_owned_by_self(block, profile_slug):
            continue
        body = _detail_comment_body_text(block)
        exact = 0 if body.lower() == sheet.lower() else 1
        ranked.append(
            (
                0 if _block_has_comment_options_menu(block) else 1,
                exact,
                len(body) if body else 10_000,
                block,
            ),
        )

    if not ranked:
        return None
    ranked.sort(key=lambda item: (item[0], item[1], item[2]))
    if len(ranked) > 1 and ranked[0][:3] == ranked[1][:3]:
        raise ValueError(
            "Tìm thấy nhiều comment trùng text của bạn. Dừng để tránh xóa nhầm."
        )
    logger.warning(
        "Nhiều khối comment trùng text trên post detail — chọn khối có menu tùy chọn "
        "và nội dung khớp nhất với sheet.",
    )
    return ranked[0][3]


def _detail_text_host_matches(
    host: Locator,
    detail_pattern: re.Pattern[str],
    sheet_raw: str,
) -> bool:
    if host.get_by_text(detail_pattern).count() > 0:
        return True
    try:
        dom_text = host.inner_text(timeout=1500)
    except Error:
        dom_text = ""
    return _dom_comment_matches_sheet(dom_text, detail_pattern, sheet_raw)


def _resolve_detail_comment_block(text_node: Locator) -> Optional[Locator]:
    """Khối comment trên post detail (article comments-comment-entity hoặc DOM cũ More)."""

    for xpath in _COMMENT_ENTITY_ANCESTOR_XPATHS:
        block = text_node.locator(xpath)
        if block.count() <= 0:
            continue
        if _safe_visible(block):
            return block
    return None


def _collect_self_comment_blocks_on_detail(
    page: Page,
    detail_pattern: re.Pattern[str],
    sheet_raw: str,
    profile_slug: str,
) -> List[Locator]:
    root = page.locator("main, [role='main']").first
    matched_blocks: List[Locator] = []
    seen_keys: Set[str] = set()

    def _remember(block: Locator) -> None:
        key = _locator_dom_key(block)
        if key:
            if key in seen_keys:
                return
            seen_keys.add(key)
        matched_blocks.append(block)

    hosts = root.locator(_DETAIL_COMMENT_TEXT_SELECTORS[0])
    for i in range(hosts.count()):
        host = hosts.nth(i)
        if not _detail_text_host_matches(host, detail_pattern, sheet_raw):
            continue
        comment_block = _resolve_detail_comment_block(host)
        if comment_block is None:
            continue
        if _card_owned_by_self(comment_block, profile_slug):
            _remember(comment_block)

    if matched_blocks:
        return _dedupe_comment_blocks(matched_blocks)

    for selector in _DETAIL_COMMENT_TEXT_SELECTORS[1:]:
        hosts = root.locator(selector)
        for i in range(hosts.count()):
            host = hosts.nth(i)
            if not _detail_text_host_matches(host, detail_pattern, sheet_raw):
                continue
            comment_block = _resolve_detail_comment_block(host)
            if comment_block is None:
                continue
            if _card_owned_by_self(comment_block, profile_slug):
                _remember(comment_block)

    if matched_blocks:
        return _dedupe_comment_blocks(matched_blocks)

    articles = root.locator("article.comments-comment-entity")
    for i in range(articles.count()):
        block = articles.nth(i)
        content = block.locator(", ".join(_DETAIL_COMMENT_TEXT_SELECTORS))
        text_host = content.first if content.count() > 0 else block
        if not _detail_text_host_matches(text_host, detail_pattern, sheet_raw):
            continue
        if _card_owned_by_self(block, profile_slug):
            _remember(block)

    if matched_blocks:
        return _dedupe_comment_blocks(matched_blocks)

    text_candidates = root.get_by_text(detail_pattern)
    for i in range(text_candidates.count()):
        text_node = text_candidates.nth(i)
        comment_block = _resolve_detail_comment_block(text_node)
        if comment_block is None:
            continue
        if _card_owned_by_self(comment_block, profile_slug):
            _remember(comment_block)

    return _dedupe_comment_blocks(matched_blocks)


def _open_comment_action_menu(target_block: Locator, page: Page) -> bool:
    """Mở menu overflow (Open options) hoặc nút More/Thêm trên DOM cũ."""

    for selector in _COMMENT_OPTIONS_TRIGGER_SELECTORS:
        trigger = target_block.locator(selector).first
        if trigger.count() <= 0:
            continue
        if not _safe_visible(trigger):
            continue
        try:
            trigger.click()
            page.wait_for_timeout(400)
            try:
                page.wait_for_selector(_OPEN_COMMENT_DROPDOWN_SELECTOR, timeout=3000)
            except Error:
                pass
            return True
        except Error:
            continue

    legacy_more = target_block.get_by_role("button", name=_MORE_LABEL_RE).first
    if legacy_more.count() > 0 and _safe_visible(legacy_more):
        legacy_more.click()
        page.wait_for_timeout(500)
        return True

    options_btn = target_block.get_by_role("button", name=_COMMENT_OPTIONS_LABEL_RE).first
    if options_btn.count() > 0 and _safe_visible(options_btn):
        options_btn.click()
        page.wait_for_timeout(400)
        return True

    return False


def _visible_dropdown_menu(page: Page) -> Locator:
    return page.locator(_OPEN_COMMENT_DROPDOWN_SELECTOR).last


def _click_delete_menu_item(page: Page) -> bool:
    dropdown = _visible_dropdown_menu(page)
    scopes: List[Locator] = []
    if dropdown.count() > 0:
        scopes.append(dropdown)
    scopes.append(page.locator("body"))

    for scope in scopes:
        try:
            scope.get_by_role("button", name=_DELETE_MENU_RE).first.click(timeout=5000)
            return True
        except PlaywrightTimeoutError:
            pass
        except Error:
            pass
        try:
            scope.get_by_text(_DELETE_MENU_RE).first.click(timeout=5000)
            return True
        except PlaywrightTimeoutError:
            pass
        except Error:
            pass
        for selector in _DELETE_MENU_ITEM_SELECTORS:
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


def delete_linkedin_comment_from_recent_activity(
    profile_slug: str,
    post_url: str,
    comment_text: str,
    session_id: Optional[str] = None,
    email: Optional[str] = None,
    max_scroll: int = 8,
    timeout_ms: int = 120000,
) -> Tuple[str, str]:
    """
    1. /in/<slug>/recent-activity/comments/
    2. Tìm commentText (regex, không phân biệt hoa thường)
    3. ``a[href*="dashCommentUrn"]`` + ``_parse_row``; quét card comment của bạn; không có thì fallback text → ancestor link bài.
    4. goto href (hoặc postUrl sheet nếu timeline không khớp activity) → trang chi tiết
    5. Tìm commentText + You/Bạn trong block comment → mở menu (Open options / More) → Delete → confirm
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
    recent_comments_url = _RECENT_COMMENTS_URL_TEMPLATE.format(profile_slug=profile_slug)
    timeline_comment_re = _comment_text_pattern(comment_text)
    detail_comment_re = _detail_comment_text_pattern(comment_text)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless)
        try:
            context = browser.new_context(storage_state=state_path)
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            # --- Bước 1–4: Recent activity ---
            page.goto(recent_comments_url, wait_until="domcontentloaded")
            main_root = page.locator("main, [role='main']").first
            main_root.wait_for(state="visible", timeout=20000)
            page.wait_for_timeout(_RECENT_ACTIVITY_LOAD_MS)
            try:
                page.wait_for_selector(
                    'main a[href*="/feed/update/"], main a[href*="/posts/"], '
                    'main a[href*="dashCommentUrn"], [role="main"] a[href*="/feed/update/"]',
                    timeout=15000,
                )
            except Error:
                pass

            matched_activity_href: Optional[str] = None

            for _scroll_idx in range(max_scroll + 1):
                matched_activity_href = _deeplink_via_owned_comment_on_timeline(
                    page,
                    post_url,
                    timeline_comment_re,
                    sheet_comment_raw,
                    profile_slug,
                )
                if not matched_activity_href:
                    matched_activity_href = _deeplink_via_dashcomment_anchors(
                        page,
                        post_url,
                        timeline_comment_re,
                        sheet_comment_raw,
                    )
                if not matched_activity_href:
                    matched_activity_href = _deeplink_via_feed_post_cards_matching_text(
                        page,
                        post_url,
                        timeline_comment_re,
                        sheet_comment_raw,
                    )
                if not matched_activity_href:
                    matched_activity_href = _deeplink_via_comment_text_near_activity_anchor(
                        page,
                        post_url,
                        timeline_comment_re,
                        profile_slug,
                    )

                if matched_activity_href:
                    break

                _nudge_recent_activity_timeline(page)
                root = _main_activity_root(page)
                prev_count = root.get_by_text(timeline_comment_re).count()
                _wait_after_recent_activity_scroll(page, timeline_comment_re, prev_count)

            if not matched_activity_href:
                try:
                    all_links = page.locator(
                        'main a[href*="/feed/update/"], [role="main"] a[href*="/feed/update/"]',
                    ).evaluate_all("els => els.map(a => a.href)")
                except Error:
                    all_links = []
                logger.error("[recent] All feed/update links: %s", all_links)
                logger.error("[recent] postUrl was: %s", post_url)

                fallback_post = _absolute_activity_href(post_url)
                if fallback_post:
                    logger.warning(
                        "[recent] Không khớp activity trên timeline — mở trực tiếp postUrl sheet: %s…",
                        fallback_post[:160],
                    )
                    matched_activity_href = fallback_post
                else:
                    raise ValueError(
                        "Không tìm thấy activity comment khớp commentText + postUrl trên "
                        "/recent-activity/comments/. Đề xuất: đảm bảo ô comment và URL bài khớp "
                        "thiết kế trên timeline; có thể cần tăng max_scroll để timeline kịp nạp."
                    )

            logger.info(
                "Comment delete — opening activity deeplink: %s…",
                matched_activity_href[:160],
            )

            # --- Bước 5–6: Vào trang chi tiết (dashCommentUrn) ---
            page.goto(matched_activity_href, wait_until="domcontentloaded")
            page.locator("main").wait_for(state="visible", timeout=20000)
            page.wait_for_timeout(_POST_DETAIL_SETTLE_MS)

            matched_blocks = _collect_self_comment_blocks_on_detail(
                page,
                detail_comment_re,
                sheet_comment_raw,
                profile_slug,
            )

            target_block = _choose_detail_delete_block(
                matched_blocks,
                sheet_comment_raw,
                profile_slug,
            )
            if target_block is None:
                raise ValueError(
                    "Đã vào post detail nhưng không tìm thấy commentText + You/Bạn."
                )

            target_block.scroll_into_view_if_needed()

            if not _open_comment_action_menu(target_block, page):
                raise RuntimeError(
                    "Không tìm thấy hoặc click được menu tùy chọn comment (Open options / More)."
                )

            clicked_delete_menu = _click_delete_menu_item(page)
            if not clicked_delete_menu:
                raise RuntimeError("Không tìm thấy hoặc click được Delete / Xóa trong menu.")

            page.wait_for_timeout(500)

            try:
                confirm = page.get_by_role("button", name=_DELETE_MENU_RE).last
                if confirm.count() > 0 and confirm.is_visible():
                    confirm.click()
            except Exception:
                for selector in _DELETE_CONFIRMATION_BUTTON_SELECTORS:
                    btn = page.locator(selector).last
                    if btn.count() > 0:
                        try:
                            if btn.is_visible():
                                btn.click()
                                break
                        except Exception:
                            continue

            # Verify: text comment ẩn khỏi main
            try:
                page.locator("main").get_by_text(detail_comment_re).first.wait_for(
                    state="hidden",
                    timeout=_DELETE_CONFIRM_TIMEOUT_MS,
                )
            except PlaywrightTimeoutError:
                raise RuntimeError(
                    f"Comment vẫn còn sau {_DELETE_CONFIRM_TIMEOUT_MS}ms. "
                    "Xóa có thể thất bại."
                )

            logger.info(
                "Successfully deleted comment from LinkedIn. "
                f"Comment: {comment_text[:50]}... URL: {post_url}"
            )

            context.close()
            browser.close()

            return (resolved_session_id, post_url)

        except PlaywrightTimeoutError as exc:
            browser.close()
            raise RuntimeError(f"Playwright timeout khi xóa comment: {str(exc)}") from exc
        except Error as exc:
            browser.close()
            raise RuntimeError(f"Playwright error: {str(exc)}") from exc
        except Exception:
            browser.close()
            raise


def delete_linkedin_comment_from_post_detail(
    post_url: str,
    comment_text: str,
    profile_slug: Optional[str] = None,
    session_id: Optional[str] = None,
    email: Optional[str] = None,
    timeout_ms: int = 300000,
) -> Tuple[str, str]:
    """
    Optimize: Xóa comment bằng cách vào trực tiếp post detail (URL bài) thay vì qua recent-activity.
    
    Workflow:
    1. post_url (đã có từ frontend)
    2. Vào trang chi tiết post (post_url)
    3. Tìm commentText + You/Bạn trong comment blocks
    4. Mở menu (Open options / More) → Delete → confirm
    
    Lợi thế: Nhanh hơn vì không cần quét timeline, không cần scroll timeline tìm comment.
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
    detail_comment_re = _detail_comment_text_pattern(comment_text)
    
    # Normalize post_url
    post_url_normalized = _absolute_activity_href(post_url)
    if not post_url_normalized:
        raise ValueError(f"Invalid post_url: {post_url}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=settings.headless)
        try:
            context = browser.new_context(storage_state=state_path)
            page = context.new_page()
            page.set_default_timeout(timeout_ms)

            # --- Vào trực tiếp post detail ---
            logger.info(
                "Comment delete (optimized) — opening post URL directly: %s…",
                post_url_normalized[:160],
            )
            page.goto(post_url_normalized, wait_until="domcontentloaded", timeout=300000)
            page.locator("main").wait_for(state="visible", timeout=60000)
            page.wait_for_timeout(_POST_DETAIL_SETTLE_MS)

            # --- Tìm comment và xóa ---
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
                    "Đã vào post detail nhưng không tìm thấy commentText + You/Bạn. "
                    "Có thể comment đã bị xóa hoặc URL bài không chính xác."
                )

            target_block.scroll_into_view_if_needed()

            if not _open_comment_action_menu(target_block, page):
                raise RuntimeError(
                    "Không tìm thấy hoặc click được menu tùy chọn comment (Open options / More)."
                )

            clicked_delete_menu = _click_delete_menu_item(page)
            if not clicked_delete_menu:
                raise RuntimeError("Không tìm thấy hoặc click được Delete / Xóa trong menu.")

            page.wait_for_timeout(500)

            try:
                confirm = page.get_by_role("button", name=_DELETE_MENU_RE).last
                if confirm.count() > 0 and confirm.is_visible():
                    confirm.click()
            except Exception:
                for selector in _DELETE_CONFIRMATION_BUTTON_SELECTORS:
                    btn = page.locator(selector).last
                    if btn.count() > 0:
                        try:
                            if btn.is_visible():
                                btn.click()
                                break
                        except Exception:
                            continue

            # Verify: text comment ẩn khỏi main
            try:
                page.locator("main").get_by_text(detail_comment_re).first.wait_for(
                    state="hidden",
                    timeout=_DELETE_CONFIRM_TIMEOUT_MS,
                )
            except PlaywrightTimeoutError:
                raise RuntimeError(
                    f"Comment vẫn còn sau {_DELETE_CONFIRM_TIMEOUT_MS}ms. "
                    "Xóa có thể thất bại."
                )

            logger.info(
                "Successfully deleted comment from LinkedIn (optimized). "
                f"Comment: {comment_text[:50]}... URL: {post_url_normalized}"
            )

            context.close()
            browser.close()

            return (resolved_session_id, post_url_normalized)

        except PlaywrightTimeoutError as exc:
            browser.close()
            raise RuntimeError(f"Playwright timeout khi xóa comment: {str(exc)}") from exc
        except Error as exc:
            browser.close()
            raise RuntimeError(f"Playwright error: {str(exc)}") from exc
        except Exception:
            browser.close()
            raise
