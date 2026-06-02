import re
import random
import time
from typing import List, Set

from loguru import logger
from playwright.async_api import Frame, Locator, Page, TimeoutError as PlaywrightTimeout

from app.modules.zalo.crawler.message_parser import ZALO_CDN_PATTERNS, _is_full_res, parse_messages
from app.modules.zalo.schemas.message import Message
from app.modules.zalo.services.job_store import get_job, save_job

MSG_CONTAINER_SELECTORS = [
    "#messageViewScroll .chat-message[data-component='bubble-message']",
    "#messageViewScroll .chat-message",
    "#messageViewScroll .chat-item",
    ".chat-message[data-component='bubble-message']",
    ".chat-message",
    "[id^='bb_msg_id_']",
    ".chat-item",
    "[class*='chat-item']",
    "[class*='message-item']",
    "[class*='msg-item']",
    "[data-qid]",
]

LOADING_SELECTORS = [
    "[class*='loading']",
    "[class*='spinner']",
    ".loading-indicator",
]

SEARCH_INPUT_SELECTORS = [
    "#contact-search-input",
    "input[data-id='txt_Main_Search']",
    "#contact-search input[type='text']",
]

CHAT_TAB_SELECTORS = [
    "[data-id='btn_Main_TabMsg']",
    "[data-id='div_Main_TabMsg']",
    "#main-tab-message",
    "[id*='TabMsg']",
    "[title*='Tin nhắn' i]",
    "[title*='Message' i]",
]

INVALID_GROUP_IDS = {"", "string", "null", "undefined"}

# FIX C-4: Regex để phát hiện timestamp chỉ có giờ (HH:MM hoặc H:MM) — không có ngày
_TIME_ONLY_RE = re.compile(r"^\d{1,2}:\d{2}$")


def _normalize_title(text: str | None) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def _titles_match(expected: str | None, actual: str | None) -> bool:
    expected_title = _normalize_title(expected).casefold()
    actual_title = _normalize_title(actual).casefold()
    return bool(expected_title and actual_title and expected_title == actual_title)


def _sanitize_group_id(group_id: str | None) -> str | None:
    if group_id is None:
        return None
    value = group_id.strip()
    if value.lower() in INVALID_GROUP_IDS:
        return None
    return value


async def _count_messages(target: Page | Frame | Locator) -> int:
    best_count = 0
    for selector in MSG_CONTAINER_SELECTORS:
        count = await target.locator(selector).count()
        if count > best_count:
            best_count = count
    return best_count


async def _find_best_message_frame(page: Page) -> Frame | None:
    best_frame: Frame | None = None
    best_count = 0

    for frame in page.frames:
        if frame is page.main_frame:
            continue
        try:
            count = 0
            for selector in MSG_CONTAINER_SELECTORS:
                selector_count = await frame.locator(selector).count()
                if selector_count > count:
                    count = selector_count
            if count > best_count:
                best_count = count
                best_frame = frame
        except Exception:
            continue

    if best_frame and best_count > 0:
        logger.info(
            f"Detected message frame with {best_count} nodes: {(best_frame.url or '(about:blank)')}"
        )
    return best_frame


async def _open_group_by_text(page: Page, target_group_title: str, timeout_ms: int = 15000) -> bool:
    target_text = _normalize_title(target_group_title)
    sidebar = page.locator("#sidebarNav")

    for title in (target_group_title, target_text):
        try:
            locator = sidebar.get_by_text(title, exact=True)
            if await locator.count() > 0:
                await locator.first.scroll_into_view_if_needed()
                await locator.first.click(timeout=timeout_ms)
                logger.info(f"Opened group by exact text '{title}'")
                return True
        except Exception:
            continue

    return False


async def _ensure_chat_tab(page: Page) -> None:
    """Return Zalo Web to the message tab before opening/searching a target."""
    for selector in CHAT_TAB_SELECTORS:
        try:
            tab = page.locator(selector).first
            if await tab.count() == 0:
                continue
            await tab.click(timeout=1200)
            await page.wait_for_timeout(800)
            return
        except Exception:
            continue

    try:
        clicked = await page.evaluate(
            """
            () => {
                const candidates = Array.from(document.querySelectorAll('[data-id], [title], [aria-label], button, div'));
                const target = candidates.find((el) => {
                    const text = `${el.getAttribute('data-id') || ''} ${el.getAttribute('title') || ''} ${el.getAttribute('aria-label') || ''} ${el.innerText || ''}`.toLowerCase();
                    const rect = el.getBoundingClientRect();
                    return rect.left < 90 &&
                        rect.top < 260 &&
                        rect.width > 20 &&
                        rect.height > 20 &&
                        (text.includes('tabmsg') || text.includes('tin nh') || text.includes('message'));
                });
                if (!target) return false;
                target.click();
                return true;
            }
            """
        )
        if clicked:
            await page.wait_for_timeout(800)
            return
    except Exception:
        pass

    try:
        await page.mouse.click(32, 148)
        await page.wait_for_timeout(800)
    except Exception:
        pass


async def _wait_for_group_title(page: Page, expected_title: str | None = None, timeout_ms: int = 15000) -> str | None:
    title_locator = page.locator("div.header-title, [class*='header-title']")
    try:
        await title_locator.first.wait_for(state="visible", timeout=timeout_ms)
        current_title = _normalize_title(await title_locator.first.inner_text())
        logger.info(f"Current group title: {current_title}")
        if expected_title and _normalize_title(expected_title) not in current_title:
            logger.warning(f"Expected group title {expected_title!r} but current is {current_title!r}")
        return current_title
    except Exception:
        logger.warning("Could not find group title after opening conversation")
        return None


async def _detect_group_member_count(page: Page) -> int | None:
    try:
        text = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        return None

    patterns = [
        r"(\d{1,5})\s+thành\s+viên",
        r"(\d{1,5})\s+members?",
        r"(\d{1,5})\s+người\s+tham\s+gia",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                return None
    return None


async def _assert_group_conversation(page: Page, group_name: str | None) -> None:
    member_count = await _detect_group_member_count(page)
    if member_count is None:
        logger.warning(
            f"Could not detect member count for conversation {group_name!r}; continuing with title check only"
        )
        return
    if member_count < 3:
        title = _normalize_title(group_name)
        if title and any(marker in title.lower() for marker in ("group", "team", "lớp", "nhóm", "[", "]")):
            logger.warning(
                f"Detected member_count={member_count} but title looks like a group ({group_name!r}); continuing"
            )
            return
        raise RuntimeError(
            f"Conversation {group_name or ''!r} has {member_count} member(s), so it is treated as a personal chat. "
            "Zalo crawl only allows groups with at least 3 members."
        )
    logger.info(f"Verified Zalo group member_count={member_count} for {group_name!r}")


async def verify_group_for_crawl(
    page: Page,
    group_name: str,
    group_id: str | None = None,
) -> dict:
    """Open a Zalo conversation and verify it is safe to crawl.

    The verification is intentionally tolerant when Zalo does not expose member
    count: exact title/message panel are stronger signals than the sidebar list,
    while an explicit member_count < 3 remains a hard personal-chat signal.
    """
    normalized_name = _normalize_title(group_name)
    if not normalized_name:
        return {
            "ok": False,
            "reason": "invalid_name",
            "detail": "Tên nhóm trống.",
            "group_name": group_name,
            "resolved_group_id": group_id,
            "current_title": None,
            "member_count": None,
            "message_count": 0,
            "warnings": [],
        }

    warnings: list[str] = []
    current_title: str | None = None
    member_count: int | None = None
    message_count = 0
    resolved_group_id = group_id or group_name

    try:
        resolved_group_id = await _open_group(page, group_id, group_name)
    except RuntimeError as exc:
        detail = str(exc)
        reason = "personal_chat" if "member(s)" in detail or "personal chat" in detail else "not_found"
        return {
            "ok": False,
            "reason": reason,
            "detail": detail,
            "group_name": group_name,
            "resolved_group_id": resolved_group_id,
            "current_title": None,
            "member_count": None,
            "message_count": 0,
            "warnings": warnings,
        }
    except Exception as exc:
        return {
            "ok": False,
            "reason": "not_found",
            "detail": f"Không mở được nhóm Zalo: {exc}",
            "group_name": group_name,
            "resolved_group_id": resolved_group_id,
            "current_title": None,
            "member_count": None,
            "message_count": 0,
            "warnings": warnings,
        }

    current_title = await _wait_for_group_title(page, group_name, timeout_ms=5000)
    if not current_title:
        return {
            "ok": False,
            "reason": "message_panel_missing",
            "detail": "Không thấy tiêu đề cuộc trò chuyện sau khi mở nhóm.",
            "group_name": group_name,
            "resolved_group_id": resolved_group_id,
            "current_title": None,
            "member_count": None,
            "message_count": 0,
            "warnings": warnings,
        }

    if not _titles_match(normalized_name, current_title):
        return {
            "ok": False,
            "reason": "not_found",
            "detail": f"Đang mở sai cuộc trò chuyện: {current_title}",
            "group_name": group_name,
            "resolved_group_id": resolved_group_id,
            "current_title": current_title,
            "member_count": None,
            "message_count": 0,
            "warnings": warnings,
        }

    member_count = await _detect_group_member_count(page)
    if member_count is None:
        warnings.append("member_count_unknown")
    elif member_count < 3:
        return {
            "ok": False,
            "reason": "personal_chat",
            "detail": f"Cuộc trò chuyện chỉ có {member_count} thành viên, hệ thống xem là chat cá nhân.",
            "group_name": group_name,
            "resolved_group_id": resolved_group_id,
            "current_title": current_title,
            "member_count": member_count,
            "message_count": 0,
            "warnings": warnings,
        }

    message_frame = await _find_best_message_frame(page)
    message_root_target: Page | Frame = message_frame or page
    message_root = await _find_message_root(message_root_target)
    message_count = await _count_messages(message_root)
    if message_count <= 0:
        warnings.append("no_messages_synced")

    return {
        "ok": True,
        "reason": "verified",
        "detail": "Đã xác minh nhóm Zalo.",
        "group_name": group_name,
        "resolved_group_id": resolved_group_id,
        "current_title": current_title,
        "member_count": member_count,
        "message_count": message_count,
        "warnings": warnings,
    }


async def _find_message_root(page: Page | Frame) -> Page | Frame | Locator:
    selectors = [
        "main",
        "[role='main']",
        "[class*='conversation']",
        "[class*='chat']",
        "[class*='message-list']",
        "[data-qa*='conversation']",
        "[data-qa*='chat']",
    ]

    best_locator: Locator | None = None
    best_score = (-1, -1)

    for selector in selectors:
        try:
            locator = page.locator(selector)
            count = await locator.count()
            for index in range(min(count, 5)):
                candidate = locator.nth(index)
                try:
                    score = await candidate.evaluate(
                        """el => {
                            const messageNodes = el.querySelectorAll(
                                "[class*='msg'], [class*='message'], [data-qa*='message'], [class*='bubble'], [class*='chat']"
                            );
                            const textLen = (el.innerText || '').trim().length;
                            return [messageNodes.length, textLen];
                        }"""
                    )
                    candidate_score = (int(score[0]), int(score[1]))
                    if candidate_score > best_score:
                        best_score = candidate_score
                        best_locator = candidate
                except Exception:
                    continue
        except Exception:
            continue

    if best_locator is not None:
        logger.info(f"Using message root score={best_score}")
        return best_locator

    logger.warning("Could not identify a conversation root; falling back to full page")
    return page


async def _scroll_message_root_up(root: Page | Frame | Locator) -> dict:
    """Cuộn khung tin nhắn lên một trang. Trả về dict gồm:
    - scrolled (bool): có tìm được khung cuộn không
    - at_top (bool): scrollTop sau khi cuộn bằng 0, đã lên đỉnh lịch sử
    - scroll_top_before / scroll_top_after: vị trí cuộn để phát hiện không di chuyển
    """
    try:
        result = await root.evaluate(
            """el => {
                const root = el || document;
                const knownSelectors = [
                    '#messageViewScroll',
                    '[id="messageViewScroll"]',
                    '.message-view__scroll',
                    '[class*="message-view__scroll"]',
                    '[class*="msg-list-scroll"]',
                    '[class*="chat-scroll"]',
                    '.ReactVirtualized__Grid',
                    '[class*="virtualized"]',
                ];
                let target = null;
                for (const sel of knownSelectors) {
                    const found = root.querySelector(sel) || document.querySelector(sel);
                    if (found && found.scrollHeight > found.clientHeight + 10) {
                        target = found;
                        break;
                    }
                }
                if (!target) {
                    const nodes = [root, ...root.querySelectorAll('*')];
                    let bestScore = -1;
                    for (const node of nodes) {
                        const oy = window.getComputedStyle(node).overflowY;
                        const canScroll =
                            (oy === 'auto' || oy === 'scroll' || oy === 'overlay') &&
                            node.scrollHeight > node.clientHeight + 10;
                        if (!canScroll) continue;
                        const score = node.scrollHeight - node.clientHeight;
                        if (score > bestScore) {
                            bestScore = score;
                            target = node;
                        }
                    }
                }
                if (!target) return { scrolled: false, at_top: false, scroll_top_before: -1, scroll_top_after: -1 };
                const before = target.scrollTop;
                target.scrollTop = Math.max(0, before - target.clientHeight);
                target.dispatchEvent(new Event('scroll', { bubbles: true }));
                const after = target.scrollTop;
                return {
                    scrolled: true,
                    at_top: after === 0,
                    scroll_top_before: before,
                    scroll_top_after: after,
                };
            }"""
        )
        if isinstance(result, dict):
            return result
        # Fallback nếu JS trả về bool (backward compat)
        return {"scrolled": bool(result), "at_top": False, "scroll_top_before": -1, "scroll_top_after": -1}
    except Exception:
        return {"scrolled": False, "at_top": False, "scroll_top_before": -1, "scroll_top_after": -1}



async def _scroll_to_bottom(root: Page | Frame | Locator) -> None:
    try:
        await root.evaluate(
            """el => {
                const root = el || document;
                const knownSelectors = [
                    '#messageViewScroll',
                    '[id="messageViewScroll"]',
                    '.message-view__scroll',
                    '[class*="message-view__scroll"]',
                    '[class*="msg-list-scroll"]',
                    '[class*="chat-scroll"]',
                    '.ReactVirtualized__Grid',
                    '[class*="virtualized"]',
                ];
                let target = null;
                for (const sel of knownSelectors) {
                    const found = root.querySelector(sel) || document.querySelector(sel);
                    if (found && found.scrollHeight > found.clientHeight + 10) {
                        target = found;
                        break;
                    }
                }
                if (!target) {
                    const nodes = [root, ...root.querySelectorAll('*')];
                    let best = -1;
                    for (const node of nodes) {
                        const oy = window.getComputedStyle(node).overflowY;
                        if ((oy === 'auto' || oy === 'scroll' || oy === 'overlay') &&
                            node.scrollHeight > node.clientHeight + 10) {
                            const score = node.scrollHeight - node.clientHeight;
                            if (score > best) {
                                best = score;
                                target = node;
                            }
                        }
                    }
                }
                if (target) {
                    target.scrollTop = target.scrollHeight;
                    target.dispatchEvent(new Event('scroll', { bubbles: true }));
                }
            }"""
        )
    except Exception:
        pass


async def _click_visible_group_by_name(page: Page, group_name: str) -> str | None:
    group_name = _normalize_title(group_name)
    if not group_name:
        return None

    result = await page.evaluate(
        """
        (targetName) => {
            const normalize = (value) =>
                (value || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').trim().toLowerCase();

            const expected = normalize(targetName);
            const selectors = [
                '#conversationList .msg-item',
                '#recent-search-list [id^="recent-item-"]',
                '#recent-search-list .conv-item',
                '.msg-item',
                '.conv-item',
                '.conv-list-item',
                '.contact-item',
                '[role="listitem"]',
                '[role="button"]',
                '[class*="ConvItem"]',
                '[class*="conversation-item"]',
            ];

            for (const listSelector of selectors) {
                const items = Array.from(document.querySelectorAll(listSelector));
                for (const item of items) {
                    const nameEl = item.querySelector(
                        '.conv-item-title__name .truncate, .conv-item-title__name, [class*="name"], [class*="Name"], .title'
                    );
                    const lines = normalize(item.innerText || item.textContent || '').split('\\n').filter(Boolean);
                    const actual = normalize(nameEl ? nameEl.textContent : lines[0] || '');
                    if (!actual) continue;
                    if (actual === expected) {
                        item.click();
                        return (
                            item.getAttribute('anim-data-id') ||
                            item.getAttribute('data-convid') ||
                            item.getAttribute('data-id') ||
                            item.id ||
                            actual
                        );
                    }
                }
            }

            return null;
        }
        """,
        group_name,
    )
    if result:
        logger.info(f"Opened visible group by name: {group_name} -> {result}")
        return str(result)
    return None


async def _search_group_by_name(page: Page, group_name: str) -> str | None:
    group_name = _normalize_title(group_name)
    if not group_name:
        return None

    visible_match = await _click_visible_group_by_name(page, group_name)
    if visible_match:
        return visible_match

    for selector in SEARCH_INPUT_SELECTORS:
        try:
            search_input = await page.query_selector(selector)
            if not search_input:
                continue

            await search_input.click()
            await search_input.fill("")
            await search_input.fill(group_name)
            await page.wait_for_timeout(1800)

            result = await _click_visible_group_by_name(page, group_name)
            await search_input.fill("")

            if result:
                logger.info(f"Opened group by search input: {group_name} -> {result}")
                return result
        except Exception as e:
            logger.warning(f"Could not search group by name with selector {selector}: {e}")

    return None


async def _open_group(page: Page, group_id: str | None, group_name: str | None) -> str:
    group_id = _sanitize_group_id(group_id)
    resolved_group_id = group_id or group_name or ""
    clicked = False

    if group_id:
        for selector_template in [
            f"[anim-data-id='{group_id}']",
            f"[data-convid='{group_id}']",
            f"[data-id='{group_id}']",
        ]:
            try:
                el = await page.query_selector(selector_template)
                if el:
                    await el.click()
                    clicked = True
                    logger.info(f"Opened group {group_id} via sidebar click")
                    break
            except Exception as e:
                logger.warning(f"Could not click group {group_id} with selector {selector_template}: {e}")

    if not clicked and group_name:
        clicked = await _open_group_by_text(page, group_name)
        if clicked:
            resolved_group_id = await _click_visible_group_by_name(page, group_name) or resolved_group_id

    if not clicked and group_name:
        logger.info(f"Trying to open group by name search: {group_name}")
        found_group_id = await _search_group_by_name(page, group_name)
        if found_group_id:
            clicked = True
            resolved_group_id = found_group_id

    if not clicked and group_name:
        raise RuntimeError(
            f"Could not open Zalo group {group_name!r}. "
            "Crawler stopped instead of reading the currently open conversation."
        )
    if not clicked:
        logger.warning(f"Could not explicitly open group_id={group_id!r}; assuming already open because no group_name was provided")

    await page.wait_for_timeout(2000)
    current_title = await _wait_for_group_title(page, group_name)
    if group_name and current_title and not _titles_match(group_name, current_title):
        logger.warning(
            f"Title mismatch after open attempt. expected={group_name!r} current={current_title!r}; retrying exact search"
        )
        found_group_id = await _search_group_by_name(page, group_name)
        if found_group_id:
            resolved_group_id = found_group_id
            await page.wait_for_timeout(1200)
            current_title = await _wait_for_group_title(page, group_name)

    if group_name and not current_title:
        raise RuntimeError(
            f"Could not verify the opened Zalo conversation title for {group_name!r}. "
            "Crawler stopped to avoid mixing messages between groups."
        )

    if group_name and current_title and not _titles_match(group_name, current_title):
        raise RuntimeError(
            f"Expected group {group_name!r} but current title is {current_title!r}. "
            "Hint: avoid running multiple crawl jobs in parallel on the same session."
        )

    await _assert_group_conversation(page, group_name)
    return resolved_group_id


async def open_conversation_for_send(page: Page, conversation_id: str | None, conversation_name: str | None) -> str:
    """Open a Zalo target for broadcast.

    Unlike crawl, broadcast targets can be either groups or personal chats. This
    still verifies the visible title when a name is provided so we do not send to
    the currently open conversation by accident.
    """
    target_id = _sanitize_group_id(conversation_id)
    resolved_id = target_id or conversation_name or ""
    clicked = False
    await _ensure_chat_tab(page)

    if target_id:
        for selector_template in [
            f"[anim-data-id='{target_id}']",
            f"[data-convid='{target_id}']",
            f"[data-id='{target_id}']",
        ]:
            try:
                el = await page.query_selector(selector_template)
                if el:
                    await el.click()
                    clicked = True
                    logger.info(f"Opened Zalo broadcast target {target_id} via sidebar click")
                    break
            except Exception as e:
                logger.warning(f"Could not click Zalo broadcast target {target_id} with selector {selector_template}: {e}")

    if not clicked and conversation_name:
        clicked = await _open_group_by_text(page, conversation_name)
        if clicked:
            resolved_id = await _click_visible_group_by_name(page, conversation_name) or resolved_id

    if not clicked and conversation_name:
        logger.info(f"Trying to open Zalo broadcast target by name search: {conversation_name}")
        found_id = await _search_group_by_name(page, conversation_name)
        if found_id:
            clicked = True
            resolved_id = found_id

    if not clicked and conversation_name:
        raise RuntimeError(
            f"Could not open Zalo conversation {conversation_name!r}. "
            "Broadcast stopped instead of sending to the currently open conversation."
        )
    if not clicked:
        logger.warning(
            f"Could not explicitly open conversation_id={target_id!r}; "
            "assuming already open because no conversation_name was provided"
        )

    await page.wait_for_timeout(2000)
    current_title = await _wait_for_group_title(page, conversation_name)
    if conversation_name and current_title and not _titles_match(conversation_name, current_title):
        logger.warning(
            f"Title mismatch after opening broadcast target. expected={conversation_name!r} "
            f"current={current_title!r}; retrying exact search"
        )
        found_id = await _search_group_by_name(page, conversation_name)
        if found_id:
            resolved_id = found_id
            await page.wait_for_timeout(1200)
            current_title = await _wait_for_group_title(page, conversation_name)

    if conversation_name and not current_title:
        raise RuntimeError(
            f"Could not verify the opened Zalo conversation title for {conversation_name!r}. "
            "Broadcast stopped to avoid sending to the wrong conversation."
        )

    if conversation_name and current_title and not _titles_match(conversation_name, current_title):
        raise RuntimeError(
            f"Expected Zalo conversation {conversation_name!r} but current title is {current_title!r}."
        )

    return resolved_id


async def _click_message_sync_action(page: Page) -> str | None:
    try:
        clicked_text = await page.evaluate(
            """
            () => {
                const normalize = (value) =>
                    (value || '')
                        .replace(/\\u00a0/g, ' ')
                        .replace(/\\s+/g, ' ')
                        .trim()
                        .toLowerCase();
                const isVisible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 && rect.height > 0 && style.visibility !== 'hidden' && style.display !== 'none';
                };
                const candidates = Array.from(document.querySelectorAll(
                    "button, [role='button'], [class*='sync'], [class*='Sync']"
                ));
                for (const el of candidates) {
                    if (!isVisible(el)) continue;
                    const text = normalize(el.innerText || el.textContent || '');
                    if (!text) continue;
                    const shouldClick =
                        text.includes('đồng bộ') ||
                        text.includes('dong bo') ||
                        text.includes('sync') ||
                        text.includes('tải tin nhắn') ||
                        text.includes('tai tin nhan') ||
                        text.includes('load messages');
                    const isProgressOnly =
                        text.includes('đang đồng bộ') ||
                        text.includes('dang dong bo') ||
                        text.includes('syncing');
                    if (shouldClick && !isProgressOnly) {
                        el.click();
                        return text;
                    }
                }
                return null;
            }
            """
        )
        return str(clicked_text) if clicked_text else None
    except Exception as exc:
        logger.debug(f"Could not click Zalo sync action: {exc}")
        return None


async def _wait_for_message_sync(page: Page, timeout_ms: int = 90000) -> None:
    logger.info("Checking whether Zalo message sync is required...")
    clicked_text = await _click_message_sync_action(page)
    if clicked_text:
        logger.info(f"Clicked Zalo message sync action: {clicked_text!r}")
        await page.wait_for_timeout(1500)

    sync_locators = [
        page.get_by_text("Đang đồng bộ"),
        page.get_by_text("Đồng bộ tin nhắn"),
        page.get_by_text("Syncing messages"),
        page.get_by_text("Äang Ä‘á»“ng bá»™"),
        page.get_by_text("Äá»“ng bá»™ tin nháº¯n"),
        page.locator("[class*='sync-banner']"),
        page.locator("[class*='SyncBanner']"),
    ]

    deadline = time.monotonic() + (timeout_ms / 1000)
    while time.monotonic() < deadline:
        saw_sync_indicator = False
        for locator in sync_locators:
            try:
                if await locator.first.is_visible(timeout=750):
                    saw_sync_indicator = True
                    logger.info("Detected Zalo message sync indicator, waiting for it to finish...")
                    try:
                        await locator.first.wait_for(state="hidden", timeout=min(15000, timeout_ms))
                    except PlaywrightTimeout:
                        pass
                    break
            except PlaywrightTimeout:
                continue
            except Exception:
                continue

        clicked_text = await _click_message_sync_action(page)
        if clicked_text:
            saw_sync_indicator = True
            logger.info(f"Clicked additional Zalo sync action: {clicked_text!r}")
            await page.wait_for_timeout(1500)

        if not saw_sync_indicator:
            return

        await page.wait_for_timeout(1000)

    logger.warning("Zalo message sync did not finish within timeout; continuing with currently available messages")


async def _wait_for_message_dom_stable(
    page: Page,
    root: Page | Frame | Locator,
    group_name: str | None,
    timeout_ms: int = 45000,
    stable_rounds_required: int = 3,
) -> None:
    """Wait until Zalo finishes lazy-rendering the currently visible chat batch."""
    deadline = time.monotonic() + timeout_ms / 1000
    last_count = -1
    stable_rounds = 0

    while time.monotonic() < deadline:
        current_title = await _wait_for_group_title(page, group_name, timeout_ms=1000)
        if group_name and not _titles_match(group_name, current_title):
            raise RuntimeError(
                f"Conversation changed while waiting for sync. expected={group_name!r} current={current_title!r}."
            )

        count = await _count_messages(root)
        if count > 0 and count == last_count:
            stable_rounds += 1
        else:
            stable_rounds = 0
        last_count = count

        if count > 0 and stable_rounds >= stable_rounds_required:
            logger.info(f"Zalo visible message DOM is stable: count={count}")
            return

        await page.wait_for_timeout(1200)

    logger.warning(f"Zalo visible message DOM did not stabilize within {timeout_ms}ms; continuing")


async def _get_message_root_after_sync(page: Page) -> tuple[Page | Frame | Locator, int]:
    message_frame = await _find_best_message_frame(page)
    message_root_target: Page | Frame = message_frame or page
    message_root = await _find_message_root(message_root_target)
    message_count = await _count_messages(message_root)
    return message_root, message_count


async def scroll_and_collect(
    page: Page, group_id: str | None, group_name: str | None, job_id: str
) -> tuple[str, List[Message]]:
    captured_image_urls: Set[str] = set()

    async def _on_response(response):
        try:
            content_type = response.headers.get("content-type", "")
            if "image/" in content_type:
                url = response.url
                if any(cdn in url for cdn in ZALO_CDN_PATTERNS) and _is_full_res(url):
                    captured_image_urls.add(url)
        except Exception:
            pass

    page.on("response", _on_response)

    try:
        resolved_group_id = await _open_group(page, group_id, group_name)
        logger.info(f"Starting scroll collection for group {resolved_group_id}")

        await _wait_for_message_sync(page)

        message_root, message_count = await _get_message_root_after_sync(page)
        if message_count <= 0:
            logger.info("No visible messages immediately after sync; waiting for Zalo to render the message panel")
            await page.wait_for_timeout(3000)
            message_root, message_count = await _get_message_root_after_sync(page)

        await _scroll_to_bottom(message_root)
        await page.wait_for_timeout(2500)
        message_root, _ = await _get_message_root_after_sync(page)
        await _wait_for_message_dom_stable(page, message_root, group_name)
        current_title = await _wait_for_group_title(page, group_name, timeout_ms=5000)
        if group_name and not _titles_match(group_name, current_title):
            raise RuntimeError(
                f"Conversation changed before crawl. expected={group_name!r} current={current_title!r}. "
                "Crawler stopped to avoid mixing messages between groups."
            )

        # 1. FIX SYNC ISSUE: Chờ Zalo đồng bộ xong trước khi crawl
        sync_selectors = [
            "text='Đang đồng bộ'", 
            "text='Đồng bộ tin nhắn'", 
            "text='Syncing messages'",
            "[class*='sync-banner']"
        ]
        logger.info("Checking for Zalo sync overlay...")
        # FIX H-3: Sync check phải dùng page.get_by_text() / page.locator() đúng chuẩn
        # Playwright. wait_for_selector("text='...'") là LOCATOR syntax, không phải CSS
        # selector — sẽ raise ValueError và bị swallow, mất 3 giây timeout mỗi lần.
        sync_locators = [
            page.get_by_text("Đang đồng bộ"),
            page.get_by_text("Đồng bộ tin nhắn"),
            page.get_by_text("Đang đồng bộ"),
            page.get_by_text("Đồng bộ tin nhắn"),
            page.get_by_text("Syncing messages"),
            page.locator("[class*='sync-banner']"),
        ]
        for locator in sync_locators:
            try:
                await locator.first.wait_for(state="visible", timeout=1)
                logger.info(f"Detected sync overlay, waiting for sync to finish...")
                await locator.first.wait_for(state="hidden", timeout=1000)
                break
            except PlaywrightTimeout:
                continue
            except Exception:
                continue

        seen_message_ids: Set[str] = set()
        ordered_messages: List[Message] = []
        stagnant_rounds = 0
        round_index = 0
        MAX_MESSAGES_PER_JOB = 20000  # Tránh infinite loop nếu group chat quá nhanh

        while True:
            round_index += 1
            current_title = await _wait_for_group_title(page, group_name, timeout_ms=1500)
            if group_name and not _titles_match(group_name, current_title):
                raise RuntimeError(
                    f"Conversation changed during crawl. expected={group_name!r} current={current_title!r}. "
                    "Crawler stopped before saving mixed messages."
                )
            batch = await parse_messages(message_root, captured_image_urls)
            new_count = 0
            # Zalo renders the visible batch top-to-bottom, while the crawl starts from the newest
            # messages and moves upward. Reverse each batch so the sheet keeps newest-first order
            # without relying on time_text.
            for msg in reversed(batch):
                if msg.message_id not in seen_message_ids:
                    seen_message_ids.add(msg.message_id)
                    ordered_messages.append(msg)
                    new_count += 1

            logger.info(f"Scroll round {round_index}: +{new_count} messages, total={len(ordered_messages)}")

            if len(ordered_messages) >= MAX_MESSAGES_PER_JOB:
                logger.warning(f"Reached MAX_MESSAGES_PER_JOB ({MAX_MESSAGES_PER_JOB}). Force stopping to avoid infinite loop.")
                break

            scroll_result = await _scroll_message_root_up(message_root)
            if not scroll_result.get("scrolled"):
                logger.warning("Could not find a scrollable message container; stopping crawl loop")
                break

            # BUG FIX: Thoát ngay khi đã lên tới đỉnh (scrollTop = 0) — không cần chờ stagnant.
            if scroll_result.get("at_top"):
                logger.info(
                    f"Reached top of message history (scrollTop=0) at round {round_index}; "
                    f"total={len(ordered_messages)} messages"
                )
                break

            # Phát hiện scroll bị kẹt (scroll_top không thay đổi sau khi cuộn)
            scroll_before = scroll_result.get("scroll_top_before", -1)
            scroll_after = scroll_result.get("scroll_top_after", -1)
            if scroll_before >= 0 and scroll_after >= 0 and scroll_before == scroll_after and scroll_after > 0:
                logger.warning(
                    f"Scroll position did not change ({scroll_before} -> {scroll_after}); "
                    "container may be temporarily stuck; retrying before stopping"
                )

            for loading_sel in LOADING_SELECTORS:
                try:
                    await page.wait_for_selector(loading_sel, timeout=1500)
                    await page.wait_for_selector(loading_sel, state="hidden", timeout=5000)
                    break
                except PlaywrightTimeout:
                    continue

            await page.wait_for_timeout(random.randint(1200, 2200))
            message_root, _ = await _get_message_root_after_sync(page)

            if new_count == 0:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            job = get_job(job_id)
            if job:
                job.progress.messages_collected = len(ordered_messages)
                save_job(job)

            # BUG FIX: Giảm từ 8 xuống 3 vòng — tiết kiệm ~15-30 giây chờ vô ích sau khi hết lịch sử.
            # at_top=True ở trên sẽ xử lý phần lớn các trường hợp thoát sớm.
            # 3 vòng còn lại để xử lý trường hợp mạng lag làm trễ tải batch mới.
            if stagnant_rounds >= 8:
                logger.info(
                    f"No new messages for 8 consecutive rounds; reached history limit at {len(ordered_messages)} messages"
                )
                break

        current_title = await _wait_for_group_title(page, group_name, timeout_ms=1500)
        if group_name and not _titles_match(group_name, current_title):
            raise RuntimeError(
                f"Conversation changed before final parse. expected={group_name!r} current={current_title!r}. "
                "Crawler stopped before saving mixed messages."
            )
        final_batch = await parse_messages(message_root, captured_image_urls)
        for msg in reversed(final_batch):
            if msg.message_id not in seen_message_ids:
                seen_message_ids.add(msg.message_id)
                ordered_messages.append(msg)

        # FIX C-4: Date Forwarding — kế thừa ngày cho tin nhắn chỉ có giờ (HH:MM)
        # do Virtual DOM cắt mất nhãn "Ngày" khi cuộn lên trên.
        #
        # ordered_messages: Mới nhất → Cũ nhất
        # Duyệt ngược (Cũ nhất → Mới nhất) để propagate date context.
        # Logic cũ dùng điều kiện `time_text == timestamp` không bao giờ true
        # vì timestamp được build từ date_text + time_text.
        current_date_context: str | None = None
        for i in range(len(ordered_messages) - 1, -1, -1):
            msg = ordered_messages[i]
            ts = (msg.timestamp or "").strip()
            if not ts:
                continue
            if not _TIME_ONLY_RE.match(ts):
                # Timestamp có ngày đầy đủ — nhớ lại làm context
                time_text = (msg.time_text or "").strip()
                if time_text and ts.endswith(time_text):
                    current_date_context = ts[: -len(time_text)].strip()
                else:
                    current_date_context = ts
            elif current_date_context:
                # Chỉ có giờ (HH:MM) — kế thừa ngày từ tin nhắn cũ hơn đã biết ngày
                msg.timestamp = f"{current_date_context} {ts}"

        messages = ordered_messages
        logger.info(f"Collected {len(messages)} messages from group {resolved_group_id}")
        return resolved_group_id, messages

    finally:
        page.remove_listener("response", _on_response)
