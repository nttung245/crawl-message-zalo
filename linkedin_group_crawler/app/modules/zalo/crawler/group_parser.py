
from typing import Any, Dict, List, Optional
from loguru import logger
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.modules.zalo.schemas.group import Group

# Zalo Web sidebar conversation item selectors (try in order)
CONV_ITEM_SELECTORS = [
    ".msg-item[anim-data-id]",
    ".msg-item",
    "#conversationList [anim-data-id]",
    "#conversationList [data-convid]",
    "#conversationList [role='button']",
    "[data-id='div_TabMsg_ThrdChItem'] [anim-data-id]",
    ".conv-item",
    ".conv-list-item",
    ".contact-item",
    "[role='listitem']",
    "[class*='ConvItem']",
    "[class*='conversation-item']",
    "[class*='ConversationItem']",
    "._3sM9",
]

SIDEBAR_CONTAINER_SELECTORS = [
    "[class*='sidebar']",
    "[class*='Sidebar']",
    "[class*='conversation-list']",
    "[class*='ConversationList']",
    "[class*='chat-list']",
]

GROUP_NAME_SELECTORS = [
    ".conv-item-title__name .truncate",
    ".conv-item-title__name",
    ".conv-name",
    ".contact-name",
    "[class*='ConvName']",
    "[class*='name']",
    ".title",
]

LAST_MESSAGE_SELECTORS = [
    ".z-conv-message__preview-message",
    ".conv-item-body__main",
    ".conv-item-body",
    ".last-message",
    ".preview",
    "[class*='LastMsg']",
    "[class*='last-msg']",
    ".subtitle",
]

UNREAD_BADGE_SELECTORS = [
    ".conv-item__badge",
    ".unread",
    ".badge",
    ".unread-count",
    "[class*='badge']",
    "[class*='unread']",
]

INVALID_GROUP_IDS = {
    "div_TabMsg_ThrdChItem",
}

MAX_GROUP_SCROLL_ROUNDS = 80
GROUP_SCROLL_STABLE_ROUNDS = 5

CHAT_TAB_SELECTORS = [
    "[data-id='btn_Main_TabMsg']",
    "[data-id='div_Main_TabMsg']",
    "#main-tab-message",
    "[id*='TabMsg']",
]

POPUP_DISMISS_TEXTS = [
    "Đã hiểu",
    "Bỏ qua",
    "Đóng",
    "OK",
    "Later",
    "Skip",
]


async def _first_text(item, selectors: List[str]) -> str:
    for selector in selectors:
        try:
            el = await item.query_selector(selector)
            if not el:
                continue
            text = (await el.inner_text()).strip()
            if text:
                return " ".join(text.split())
        except Exception:
            continue
    return ""


def _clean_group_id(value: Optional[str]) -> Optional[str]:
    if not value:
        return None
    value = value.strip()
    if not value or value in INVALID_GROUP_IDS:
        return None
    return value


async def wait_for_group_list_ready(page: Page, timeout_ms: int = 15000) -> Dict[str, Any]:
    await ensure_chat_sidebar_ready(page)

    last_counts: Dict[str, int] = {}
    attempts = max(1, timeout_ms // 1000)

    for attempt in range(1, attempts + 1):
        selector_counts: Dict[str, int] = {}
        for selector in CONV_ITEM_SELECTORS:
            count = await page.locator(selector).count()
            selector_counts[selector] = count
            if count:
                logger.info(
                    f"Conversation list ready after {attempt}s with selector {selector} ({count} items)"
                )
                return selector_counts

        fallback_count = await _fallback_conversation_count(page)
        selector_counts["__fallback_text_scan__"] = fallback_count
        if fallback_count:
            logger.info(f"Conversation list ready after {attempt}s with fallback scan ({fallback_count} items)")
            return selector_counts

        last_counts = selector_counts
        logger.debug(f"Waiting for conversation list (attempt {attempt}/{attempts}): {selector_counts}")
        await page.wait_for_timeout(1000)

    for selector in SIDEBAR_CONTAINER_SELECTORS:
        try:
            await page.wait_for_selector(selector, timeout=1000)
            logger.warning(f"Sidebar container appeared but no conversation items matched: {selector}")
            break
        except PlaywrightTimeout:
            continue

    return last_counts


async def ensure_chat_sidebar_ready(page: Page) -> None:
    if not page.url.startswith("https://chat.zalo.me"):
        logger.info(f"Current page is {page.url!r}, navigating back to Zalo chat app")
        await page.goto("https://chat.zalo.me", wait_until="domcontentloaded", timeout=60000)

    await page.wait_for_load_state("domcontentloaded")
    await page.wait_for_timeout(1500)
    await _dismiss_common_popups(page)
    await _open_message_tab(page)


async def _dismiss_common_popups(page: Page) -> None:
    for text in POPUP_DISMISS_TEXTS:
        try:
            button = page.get_by_text(text, exact=True)
            if await button.count() > 0 and await button.first.is_visible(timeout=300):
                await button.first.click(timeout=1000)
                await page.wait_for_timeout(300)
        except Exception:
            continue


async def _open_message_tab(page: Page) -> None:
    for selector in CHAT_TAB_SELECTORS:
        try:
            locator = page.locator(selector)
            if await locator.count() > 0 and await locator.first.is_visible(timeout=500):
                await locator.first.click(timeout=1500)
                await page.wait_for_timeout(800)
                return
        except Exception:
            continue
    for text in ("Tin nhắn", "Messages"):
        try:
            locator = page.get_by_text(text, exact=False)
            if await locator.count() > 0 and await locator.first.is_visible(timeout=500):
                await locator.first.click(timeout=1500)
                await page.wait_for_timeout(800)
                return
        except Exception:
            continue


async def _fallback_conversation_count(page: Page) -> int:
    try:
        return int(
            await page.evaluate(
                """
                () => {
                    const leftLimit = Math.max(260, window.innerWidth * 0.45);
                    const nodes = Array.from(document.querySelectorAll("[role='button'], [class*='item'], [class*='Item'], [data-id], [id]"));
                    return nodes.filter((node) => {
                        const rect = node.getBoundingClientRect();
                        if (rect.width < 120 || rect.height < 28 || rect.left > leftLimit) return false;
                        const text = (node.innerText || node.textContent || '').trim();
                        if (!text || text.length < 2 || text.length > 180) return false;
                        return true;
                    }).length;
                }
                """
            )
        )
    except Exception:
        return 0


async def collect_group_debug_info(page: Page) -> Dict[str, Any]:
    title = ""
    body_text = ""
    try:
        title = await page.title()
    except Exception:
        pass

    try:
        body_text = await page.locator("body").inner_text(timeout=3000)
    except Exception:
        pass

    selector_counts: Dict[str, int] = {}
    for selector in CONV_ITEM_SELECTORS:
        try:
            selector_counts[selector] = await page.locator(selector).count()
        except Exception:
            selector_counts[selector] = -1

    return {
        "url": page.url,
        "title": title,
        "selector_counts": selector_counts,
        "body_preview": body_text[:1000],
    }


async def parse_groups(page: Page) -> List[Group]:
    groups_by_key: Dict[str, Group] = {}
    selector_used = ""
    stable_rounds = 0

    for round_index in range(1, MAX_GROUP_SCROLL_ROUNDS + 1):
        items = []
        for selector in CONV_ITEM_SELECTORS:
            items = await page.query_selector_all(selector)
            if items:
                if selector != selector_used:
                    logger.info(f"Found conversation items with selector: {selector}")
                    selector_used = selector
                break

        if not items:
            logger.warning("No conversation items found with selectors; trying fallback text scan")
            fallback_groups = await _parse_groups_by_text_scan(page)
            if fallback_groups:
                for group in fallback_groups:
                    groups_by_key[group.group_id or group.name] = group
                break
            return list(groups_by_key.values())

        before_count = len(groups_by_key)
        for index, item in enumerate(items, start=1):
            try:
                group = await _parse_item(item)
                if group:
                    groups_by_key[group.group_id or group.name] = group
                else:
                    preview = (await item.inner_text()).strip().replace("\n", " ")
                    logger.debug(
                        f"Skipped conversation item #{index}: no parsable group_id/name, preview={preview[:120]!r}"
                    )
            except Exception as e:
                logger.warning(f"Failed to parse group item #{index}: {e}")
                continue

        after_count = len(groups_by_key)
        if after_count == before_count:
            stable_rounds += 1
        else:
            stable_rounds = 0

        scroll_result = await _scroll_group_list(page)
        if not scroll_result.get("moved"):
            logger.info(
                f"Conversation list reached end after {round_index} rounds, parsed={after_count}"
            )
            break

        if stable_rounds >= GROUP_SCROLL_STABLE_ROUNDS:
            logger.info(
                f"Conversation list produced no new groups for {stable_rounds} rounds, parsed={after_count}"
            )
            break

        await page.wait_for_timeout(350)

    if not groups_by_key:
        for group in await _parse_conversation_list_direct(page):
            groups_by_key[group.group_id or group.name] = group
    if not groups_by_key:
        for group in await _parse_visual_conversation_rows(page):
            groups_by_key[group.group_id or group.name] = group

    groups = list(groups_by_key.values())
    logger.info(f"Parsed {len(groups)} groups")
    return groups


async def _parse_visual_conversation_rows(page: Page) -> List[Group]:
    rows = await page.evaluate(
        """
        () => {
            const normalize = (value) => (value || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').trim();
            const appLeftLimit = Math.max(520, window.innerWidth * 0.42);
            const badNames = new Set([
                'tất cả',
                'chưa đọc',
                'phân loại',
                'tin nhắn',
                'danh bạ',
                'khám phá',
                'cloud',
                'cloud của tôi',
                'todo',
            ]);
            const isVisible = (el) => {
                const rect = el.getBoundingClientRect();
                const style = window.getComputedStyle(el);
                return rect.width > 0 && rect.height > 0 && style.display !== 'none' && style.visibility !== 'hidden';
            };
            const scoreRow = (el) => {
                const rect = el.getBoundingClientRect();
                if (rect.left < 70 || rect.left > appLeftLimit || rect.width < 220 || rect.height < 46 || rect.height > 110) {
                    return -1;
                }
                const text = normalize(el.innerText || el.textContent || '');
                if (!text || text.length < 4 || text.length > 260) return -1;
                const hasImage = !!el.querySelector('img[src]');
                const hasTime = /(?:\\d+\\s*(?:phút|giờ)|hôm qua|\\d{1,2}:\\d{2})/i.test(text);
                return (hasImage ? 2 : 0) + (hasTime ? 1 : 0) + Math.min(3, Math.floor(rect.height / 24));
            };
            const candidates = Array.from(document.querySelectorAll('img[src]'));
            const seen = new Set();
            const result = [];
            for (const img of candidates) {
                const imgRect = img.getBoundingClientRect();
                if (imgRect.left < 80 || imgRect.left > 180 || imgRect.width < 24 || imgRect.height < 24) continue;

                let node = img.parentElement;
                let best = null;
                let bestScore = -1;
                for (let depth = 0; node && node !== document.body && depth < 8; depth += 1) {
                    const score = scoreRow(node);
                    if (score > bestScore) {
                        bestScore = score;
                        best = node;
                    }
                    node = node.parentElement;
                }
                if (!best || bestScore < 2 || !isVisible(best)) continue;

                const rowText = normalize(best.innerText || best.textContent || '');
                const lines = rowText.split('\\n').map(normalize).filter(Boolean);
                const nameCandidates = lines.filter((line) => {
                    const lower = line.toLowerCase();
                    if (badNames.has(lower)) return false;
                    if (/^\\d+\\s*(phút|giờ)$/i.test(lower) || lower === 'hôm qua') return false;
                    if (lower.length > 120) return false;
                    return true;
                });
                const name = nameCandidates[0] || '';
                if (!name) continue;

                const id =
                    best.getAttribute('anim-data-id') ||
                    best.getAttribute('data-convid') ||
                    best.getAttribute('data-id') ||
                    best.id ||
                    name;
                const key = `${id}|${name}`;
                if (seen.has(key)) continue;
                seen.add(key);
                result.push({
                    group_id: String(id),
                    name,
                    avatar_url: img.getAttribute('src'),
                    last_message: lines.find((line) => line !== name && !/^\\d+\\s*(phút|giờ)$/i.test(line.toLowerCase())) || null,
                    unread_count: 0,
                });
            }
            return result;
        }
        """
    )
    groups: List[Group] = []
    for row in rows or []:
        try:
            group_id = _clean_group_id(str(row.get("group_id") or "")) or str(row.get("name") or "")
            name = str(row.get("name") or "").strip()
            if not group_id or not name:
                continue
            groups.append(
                Group(
                    group_id=group_id,
                    name=name,
                    avatar_url=row.get("avatar_url"),
                    last_message=row.get("last_message"),
                    unread_count=int(row.get("unread_count") or 0),
                )
            )
        except Exception:
            continue
    logger.info(f"Visual conversation row parser found {len(groups)} items")
    return groups


async def _parse_conversation_list_direct(page: Page) -> List[Group]:
    rows = await page.evaluate(
        """
        () => {
            const normalize = (value) => (value || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').trim();
            const containers = [
                document.querySelector('#conversationList'),
                document.querySelector('[data-id="div_TabMsg_ThrdChItem"]'),
                ...Array.from(document.querySelectorAll("[class*='conversation'], [class*='Conversation'], [class*='sidebar'], [class*='Sidebar']")),
            ].filter(Boolean);
            const roots = containers.length ? containers : [document.body];
            const itemSelectors = [
                "[anim-data-id]",
                "[data-convid]",
                ".msg-item",
                ".conv-item",
                "[role='listitem']",
                "[role='button']",
                "[class*='item']",
                "[class*='Item']",
            ];
            const seen = new Set();
            const result = [];
            for (const root of roots) {
                const items = itemSelectors.flatMap((selector) => Array.from(root.querySelectorAll(selector)));
                for (const item of items) {
                    const rect = item.getBoundingClientRect();
                    if (rect.width < 120 || rect.height < 28) continue;
                    const raw = normalize(item.innerText || item.textContent || '');
                    if (!raw || raw.length < 2) continue;
                    const lines = raw.split('\\n').map(normalize).filter(Boolean);
                    const nameEl = item.querySelector(".conv-item-title__name .truncate, .conv-item-title__name, [class*='name'], [class*='Name'], .title");
                    const name = normalize(nameEl ? nameEl.textContent : lines[0]);
                    if (!name || name.length < 2 || name.length > 120) continue;
                    const lower = name.toLowerCase();
                    if (
                        lower === 'tin nhắn' ||
                        lower === 'danh bạ' ||
                        lower === 'khám phá' ||
                        lower === 'cloud của tôi' ||
                        lower === 'todo'
                    ) continue;
                    const id =
                        item.getAttribute('anim-data-id') ||
                        item.getAttribute('data-convid') ||
                        item.getAttribute('data-id') ||
                        item.id ||
                        name;
                    const key = `${id}|${name}`;
                    if (seen.has(key)) continue;
                    seen.add(key);
                    const img = item.querySelector('img[src]');
                    result.push({
                        group_id: String(id),
                        name,
                        avatar_url: img ? img.getAttribute('src') : null,
                        last_message: lines.slice(1).join(' ') || null,
                        unread_count: 0,
                    });
                }
            }
            return result;
        }
        """
    )
    groups: List[Group] = []
    for row in rows or []:
        try:
            group_id = _clean_group_id(str(row.get("group_id") or "")) or str(row.get("name") or "")
            name = str(row.get("name") or "").strip()
            if not group_id or not name:
                continue
            groups.append(
                Group(
                    group_id=group_id,
                    name=name,
                    avatar_url=row.get("avatar_url"),
                    last_message=row.get("last_message"),
                    unread_count=int(row.get("unread_count") or 0),
                )
            )
        except Exception:
            continue
    logger.info(f"Direct conversation list parser found {len(groups)} items")
    return groups


async def _parse_groups_by_text_scan(page: Page) -> List[Group]:
    rows = await page.evaluate(
        """
        () => {
            const normalize = (value) => (value || '').replace(/\\u00a0/g, ' ').replace(/\\s+/g, ' ').trim();
            const leftLimit = Math.max(260, window.innerWidth * 0.45);
            const nodes = Array.from(document.querySelectorAll("[role='button'], [class*='item'], [class*='Item'], [data-id], [id]"));
            const seen = new Set();
            const result = [];
            for (const node of nodes) {
                const rect = node.getBoundingClientRect();
                if (rect.width < 120 || rect.height < 28 || rect.left > leftLimit) continue;
                const text = normalize(node.innerText || node.textContent || '');
                if (!text || text.length < 2 || text.length > 180) continue;
                const lines = text.split('\\n').map(normalize).filter(Boolean);
                const name = lines[0] || text;
                const lower = name.toLowerCase();
                if (
                    lower.includes('tin nhắn') ||
                    lower.includes('danh bạ') ||
                    lower.includes('khám phá') ||
                    lower.includes('cloud') ||
                    lower.includes('todo') ||
                    lower.includes('thêm')
                ) continue;
                const id =
                    node.getAttribute('anim-data-id') ||
                    node.getAttribute('data-convid') ||
                    node.getAttribute('data-id') ||
                    node.id ||
                    name;
                const key = `${id}|${name}`;
                if (seen.has(key)) continue;
                seen.add(key);
                const img = node.querySelector('img[src]');
                result.push({
                    group_id: String(id),
                    name,
                    avatar_url: img ? img.getAttribute('src') : null,
                    last_message: lines.slice(1).join(' ') || null,
                    unread_count: 0,
                });
            }
            return result;
        }
        """
    )
    groups: List[Group] = []
    for row in rows or []:
        try:
            group_id = _clean_group_id(str(row.get("group_id") or ""))
            name = str(row.get("name") or "").strip()
            if not group_id or not name:
                continue
            groups.append(
                Group(
                    group_id=group_id,
                    name=name,
                    avatar_url=row.get("avatar_url"),
                    last_message=row.get("last_message"),
                    unread_count=int(row.get("unread_count") or 0),
                )
            )
        except Exception:
            continue
    logger.info(f"Fallback text scan parsed {len(groups)} conversations")
    return groups


async def _scroll_group_list(page: Page) -> Dict[str, Any]:
    return await page.evaluate(
        """
        (selectors) => {
            const items = selectors.flatMap((selector) => Array.from(document.querySelectorAll(selector)));
            const firstItem = items.find(Boolean);
            let el = firstItem ? firstItem.parentElement : null;
            while (el && el !== document.body) {
                if (el.scrollHeight > el.clientHeight + 20) {
                    const before = el.scrollTop;
                    const maxTop = el.scrollHeight - el.clientHeight;
                    el.scrollTop = Math.min(maxTop, before + Math.max(360, Math.floor(el.clientHeight * 0.85)));
                    el.dispatchEvent(new Event("scroll", { bubbles: true }));
                    return {
                        moved: el.scrollTop > before,
                        before,
                        after: el.scrollTop,
                        maxTop,
                    };
                }
                el = el.parentElement;
            }

            const before = window.scrollY;
            window.scrollBy(0, 600);
            return {
                moved: window.scrollY > before,
                before,
                after: window.scrollY,
                maxTop: document.documentElement.scrollHeight - window.innerHeight,
            };
        }
        """,
        CONV_ITEM_SELECTORS,
    )


async def _parse_item(item) -> Optional[Group]:
    group_id = _clean_group_id(await item.get_attribute("anim-data-id"))
    if not group_id:
        group_id = _clean_group_id(await item.get_attribute("data-convid"))
    if not group_id:
        group_id = _clean_group_id(await item.get_attribute("data-id"))
    if not group_id:
        child = await item.query_selector("[anim-data-id], [data-convid], [data-id]")
        if child:
            group_id = (
                _clean_group_id(await child.get_attribute("anim-data-id"))
                or _clean_group_id(await child.get_attribute("data-convid"))
                or _clean_group_id(await child.get_attribute("data-id"))
            )
    if not group_id:
        href_el = await item.query_selector("a[href*='chat.zalo.me'], a[href]")
        if href_el:
            href = await href_el.get_attribute("href") or ""
            if href:
                group_id = href.rstrip("/").split("/")[-1]
    if not group_id:
        return None

    name = await _first_text(item, GROUP_NAME_SELECTORS)
    if not name:
        return None

    avatar_el = await item.query_selector("img.avatar, img[class*='avatar'], img")
    avatar_url = await avatar_el.get_attribute("src") if avatar_el else None

    last_message = await _first_text(item, LAST_MESSAGE_SELECTORS) or None

    unread_count = 0
    for selector in UNREAD_BADGE_SELECTORS:
        try:
            badge_el = await item.query_selector(selector)
            if not badge_el:
                continue
            text = (await badge_el.inner_text()).strip()
            if text.isdigit():
                unread_count = int(text)
                break
        except Exception:
            continue

    return Group(
        group_id=group_id,
        name=name,
        avatar_url=avatar_url,
        last_message=last_message,
        unread_count=unread_count,
    )

