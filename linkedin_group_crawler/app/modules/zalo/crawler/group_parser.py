from typing import Any, List

from loguru import logger
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from app.modules.zalo.schemas.group import Group

# Zalo Web sidebar conversation item selectors (try in order)
CONV_ITEM_SELECTORS = [
    ".msg-item[anim-data-id]",
    ".msg-item",
    ".conv-item",
    ".conv-list-item",
    ".contact-item",
    "[class*='ConvItem']",
    "[class*='conversation-item']",
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


async def _first_text(item, selectors: list[str]) -> str:
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


def _clean_group_id(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if not value or value in INVALID_GROUP_IDS:
        return None
    return value


async def wait_for_group_list_ready(page: Page, timeout_ms: int = 15000) -> dict[str, Any]:
    if not page.url.startswith("https://chat.zalo.me"):
        logger.info(f"Current page is {page.url!r}, navigating back to Zalo chat app")
        await page.goto("https://chat.zalo.me", wait_until="domcontentloaded", timeout=60000)

    await page.wait_for_load_state("domcontentloaded")

    last_counts: dict[str, int] = {}
    attempts = max(1, timeout_ms // 1000)

    for attempt in range(1, attempts + 1):
        selector_counts: dict[str, int] = {}
        for selector in CONV_ITEM_SELECTORS:
            count = await page.locator(selector).count()
            selector_counts[selector] = count
            if count:
                logger.info(
                    f"Conversation list ready after {attempt}s with selector {selector} ({count} items)"
                )
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


async def collect_group_debug_info(page: Page) -> dict[str, Any]:
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

    selector_counts: dict[str, int] = {}
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
    groups: List[Group] = []

    # Find the list container
    items = []
    for selector in CONV_ITEM_SELECTORS:
        items = await page.query_selector_all(selector)
        if items:
            logger.info(f"Found {len(items)} conversation items with selector: {selector}")
            break

    if not items:
        logger.warning("No conversation items found in sidebar")
        return groups

    for index, item in enumerate(items, start=1):
        try:
            group = await _parse_item(item)
            if group:
                groups.append(group)
            else:
                preview = (await item.inner_text()).strip().replace("\n", " ")
                logger.debug(f"Skipped conversation item #{index}: no parsable group_id/name, preview={preview[:120]!r}")
        except Exception as e:
            logger.warning(f"Failed to parse group item #{index}: {e}")
            continue

    logger.info(f"Parsed {len(groups)} groups")
    return groups


async def _parse_item(item) -> Group | None:
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

