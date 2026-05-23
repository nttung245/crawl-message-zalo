import random
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

INVALID_GROUP_IDS = {"", "string", "null", "undefined"}


def _normalize_title(text: str | None) -> str:
    return " ".join((text or "").replace("\xa0", " ").split())


def _sanitize_group_id(group_id: str | None) -> str | None:
    if group_id is None:
        return None
    value = group_id.strip()
    if value.lower() in INVALID_GROUP_IDS:
        return None
    return value


async def _count_messages(target: Page | Frame | Locator) -> int:
    for selector in MSG_CONTAINER_SELECTORS:
        count = await target.locator(selector).count()
        if count:
            return count
    return 0


async def _find_best_message_frame(page: Page) -> Frame | None:
    best_frame: Frame | None = None
    best_count = 0

    for frame in page.frames:
        if frame is page.main_frame:
            continue
        try:
            count = 0
            for selector in MSG_CONTAINER_SELECTORS:
                count = await frame.locator(selector).count()
                if count:
                    break
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

    for exact in (True, False):
        for title in (target_group_title, target_text):
            try:
                locator = sidebar.get_by_text(title, exact=exact)
                if await locator.count() > 0:
                    await locator.first.scroll_into_view_if_needed()
                    await locator.first.click(timeout=timeout_ms)
                    logger.info(f"Opened group by text '{title}' (exact={exact})")
                    return True
            except Exception:
                continue

    return False


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


async def _scroll_message_root_up(root: Page | Frame | Locator) -> bool:
    try:
        return bool(
            await root.evaluate(
                """el => {
                    const knownSelectors = [
                        '.message-view__scroll',
                        '[class*="message-view__scroll"]',
                        '[class*="msg-list-scroll"]',
                        '[class*="chat-scroll"]',
                    ];
                    let target = null;
                    for (const sel of knownSelectors) {
                        const found = el.querySelector(sel) || document.querySelector(sel);
                        if (found && found.scrollHeight > found.clientHeight + 10) {
                            target = found;
                            break;
                        }
                    }
                    if (!target) {
                        const nodes = [el, ...el.querySelectorAll('*')];
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
                    if (!target) return false;
                    const before = target.scrollTop;
                    target.scrollTop = Math.max(0, before - target.clientHeight);
                    target.dispatchEvent(new Event('scroll', { bubbles: true }));
                    return true;
                }"""
            )
        )
    except Exception:
        return False


async def _scroll_to_bottom(root: Page | Frame | Locator) -> None:
    try:
        await root.evaluate(
            """el => {
                const knownSelectors = [
                    '.message-view__scroll',
                    '[class*="message-view__scroll"]',
                    '[class*="msg-list-scroll"]',
                    '[class*="chat-scroll"]',
                ];
                let target = null;
                for (const sel of knownSelectors) {
                    const found = el.querySelector(sel) || document.querySelector(sel);
                    if (found && found.scrollHeight > found.clientHeight + 10) {
                        target = found;
                        break;
                    }
                }
                if (!target) {
                    const nodes = [el, ...el.querySelectorAll('*')];
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
            ];

            for (const listSelector of selectors) {
                const items = Array.from(document.querySelectorAll(listSelector));
                for (const item of items) {
                    const nameEl = item.querySelector('.conv-item-title__name .truncate, .conv-item-title__name');
                    const actual = normalize(nameEl ? nameEl.textContent : '');
                    if (!actual) continue;
                    if (actual === expected || actual.includes(expected)) {
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
            await page.wait_for_timeout(1200)
            await search_input.press("Enter")
            await page.wait_for_timeout(800)

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

    if group_name:
        clicked = await _open_group_by_text(page, group_name)
        if clicked:
            resolved_group_id = await _click_visible_group_by_name(page, group_name) or resolved_group_id

    if not clicked and group_id:
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
        logger.info(f"Trying to open group by name search: {group_name}")
        found_group_id = await _search_group_by_name(page, group_name)
        if found_group_id:
            clicked = True
            resolved_group_id = found_group_id

    if not clicked:
        logger.warning(
            f"Could not explicitly open group_id={group_id!r} group_name={group_name!r}, assuming already open"
        )

    await page.wait_for_timeout(2000)
    current_title = await _wait_for_group_title(page, group_name)
    if group_name and current_title and _normalize_title(group_name) not in current_title:
        logger.warning(
            f"Title mismatch after open attempt. expected={group_name!r} current={current_title!r}; retrying exact search"
        )
        found_group_id = await _search_group_by_name(page, group_name)
        if found_group_id:
            resolved_group_id = found_group_id
            await page.wait_for_timeout(1200)
            current_title = await _wait_for_group_title(page, group_name)

    if group_name and current_title and _normalize_title(group_name) not in current_title:
        raise RuntimeError(
            f"Expected group {group_name!r} but current title is {current_title!r}. "
            "Hint: avoid running multiple crawl jobs in parallel on the same session."
        )

    return resolved_group_id


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
        message_frame = await _find_best_message_frame(page)
        message_root_target: Page | Frame = message_frame or page
        message_root = await _find_message_root(message_root_target)
        await _scroll_to_bottom(message_root)
        await page.wait_for_timeout(2000)

        logger.info(f"Starting scroll collection for group {resolved_group_id}")

        seen_message_ids: Set[str] = set()
        ordered_messages: List[Message] = []
        stagnant_rounds = 0
        round_index = 0

        while True:
            round_index += 1
            batch = await parse_messages(page, captured_image_urls)
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

            scrolled = await _scroll_message_root_up(message_root)
            if not scrolled:
                logger.warning("Could not find a scrollable message container; stopping crawl loop")
                break

            for loading_sel in LOADING_SELECTORS:
                try:
                    await page.wait_for_selector(loading_sel, timeout=1500)
                    await page.wait_for_selector(loading_sel, state="hidden", timeout=5000)
                    break
                except PlaywrightTimeout:
                    continue

            await page.wait_for_timeout(random.randint(1200, 2200))

            if new_count == 0:
                stagnant_rounds += 1
            else:
                stagnant_rounds = 0

            job = get_job(job_id)
            if job:
                job.progress.messages_collected = len(ordered_messages)
                save_job(job)

            if stagnant_rounds >= 8:
                logger.info(
                    f"No new messages for 8 consecutive rounds; reached history limit at {len(ordered_messages)} messages"
                )
                break

        final_batch = await parse_messages(page, captured_image_urls)
        for msg in reversed(final_batch):
            if msg.message_id not in seen_message_ids:
                seen_message_ids.add(msg.message_id)
                ordered_messages.append(msg)

        messages = ordered_messages
        logger.info(f"Collected {len(messages)} messages from group {resolved_group_id}")
        return resolved_group_id, messages

    finally:
        page.remove_listener("response", _on_response)
