from __future__ import annotations

from typing import Any, Dict, List, Optional
import asyncio
import os
import tempfile
from urllib.parse import urlparse

import httpx
from loguru import logger
from playwright.async_api import Page

from app.modules.zalo.crawler.scroll_handler import open_conversation_for_send
from app.modules.zalo.services.debug_artifacts import save_page_artifacts
from app.modules.zalo.services.supabase_service import download_asset_bytes

COMPOSER_SELECTORS = [
    "#chatInput [contenteditable='true']",
    "[data-lexical-editor='true']",
    "[data-id='txt_Main_Input']",
    "[data-id='txt_Main_Input'] [contenteditable='true']",
    "[class*='chat-input'] [contenteditable='true']",
    "[class*='composer'] [contenteditable='true']",
    "[class*='rich-input'] [contenteditable='true']",
    "[class*='input'] [contenteditable]",
    "[class*='Input'] [contenteditable]",
    "[class*='text-area']",
    "div[contenteditable='true']",
    "[contenteditable='true'][role='textbox']",
    "[contenteditable='true']",
    "[contenteditable]",
    "[role='textbox']",
    "[aria-multiline='true']",
    "textarea",
]

ATTACH_IMAGE_SELECTORS = [
    "[data-id='btn_More_SendPhoto']",
    "[data-id='btn_SendPhoto']",
    "[data-id='btn_Image']",
    "[data-id='btn_File']",
    "[data-id='btn_Attach']",
    "[data-id='btn_More']",
    "[data-id*='SendPhoto']",
    "[data-id*='Photo']",
    "[data-id*='Image']",
    "[data-id*='File']",
    "[data-id*='Attach']",
    "[title='Gửi hình ảnh']",
    "[title*='Gửi hình' i]",
    "[title*='hình ảnh' i]",
    "[title*='ảnh' i]",
    "button[aria-label*='photo' i]",
    "button[aria-label*='image' i]",
    "button[aria-label*='file' i]",
    "button:has-text('Anh')",
    "button:has-text('File')",
    "button:has-text('Tep')",
    "[aria-label*='anh' i]",
    "[aria-label*='ảnh' i]",
    "[aria-label*='hình' i]",
    "[aria-label*='photo' i]",
    "[aria-label*='image' i]",
    "[title*='anh' i]",
    "[title*='hình' i]",
    "[title*='photo' i]",
    "[title*='image' i]",
    "[class*='photo' i]",
    "[class*='image' i]",
    "[class*='attach' i]",
]

SEND_BUTTON_SELECTORS = [
    "[data-id='btn_SendMsg']",
    "[data-id='btn_Send']",
    "[data-id*='SendMsg']",
    "[data-id*='SendMessage']",
    "[data-id*='Send']",
    "button[aria-label*='send' i]",
    "button[aria-label*='gửi' i]",
    "[aria-label*='send' i]",
    "[aria-label*='gửi' i]",
    "[title*='send' i]",
    "[title*='gửi' i]",
    "[class*='send' i]",
]

MAX_TEXT_CHUNK_LENGTH = 3500

OUTGOING_MESSAGE_SELECTORS = [
    "[data-id='div_SentMsg_Text']",
    "[data-id='div_SentMsg_Photo']",
    "[data-id='btn_SentMsg_React']",
    "[data-id='btn_LastSentMsg_React']",
    ".chat-message:has([data-id='div_SentMsg_Text'])",
    ".chat-message:has([data-id='div_SentMsg_Photo'])",
    ".chatImageMessage--audit.-me",
    ".img-msg-v2.-me",
]


def _loop_time(page: Page) -> float:
    return asyncio.get_running_loop().time()


async def _focus_composer_by_dom(page: Page, click: bool = True) -> bool:
    return bool(
        await page.evaluate(
            """
            (shouldClick) => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 120 &&
                        rect.height > 16 &&
                        rect.top > window.innerHeight * 0.35 &&
                        rect.bottom <= window.innerHeight + 80 &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none' &&
                        Number(style.opacity || '1') > 0;
                };
                const candidates = Array.from(document.querySelectorAll(
                    "[contenteditable], [data-lexical-editor='true'], [role='textbox'], [aria-multiline='true'], textarea"
                )).filter(visible);
                candidates.sort((left, right) => {
                    const lr = left.getBoundingClientRect();
                    const rr = right.getBoundingClientRect();
                    return rr.top - lr.top;
                });
                const target = candidates[0];
                if (!target) return false;
                if (shouldClick) {
                    target.scrollIntoView({ block: 'center', inline: 'nearest' });
                    target.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
                    target.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
                    target.click();
                    target.focus();
                }
                return true;
            }
            """,
            click,
        )
    )


async def _composer_text(locator) -> str:
    try:
        value = await locator.evaluate(
            """el => ((el.value || el.innerText || el.textContent || '').trim())"""
        )
        return str(value or "").strip()
    except Exception:
        return ""


async def _click_send_button(page: Page) -> bool:
    for selector in SEND_BUTTON_SELECTORS:
        try:
            button = page.locator(selector).first
            if await button.count() == 0:
                continue
            if not await button.is_visible(timeout=300):
                continue
            await button.click(timeout=1000)
            return True
        except Exception:
            continue

    try:
        return bool(
            await page.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 8 &&
                            rect.height > 8 &&
                            rect.bottom > 0 &&
                            rect.right > 0 &&
                            rect.top < window.innerHeight &&
                            rect.left < window.innerWidth &&
                            style.visibility !== 'hidden' &&
                            style.display !== 'none' &&
                            Number(style.opacity || '1') > 0;
                    };
                    const nodes = Array.from(document.querySelectorAll(
                        "button, [role='button'], [data-id], [aria-label], [title], [class]"
                    ));
                    const candidates = nodes.filter((el) => {
                        if (!visible(el)) return false;
                        const rect = el.getBoundingClientRect();
                        if (rect.top < window.innerHeight * 0.55 || rect.left < window.innerWidth * 0.45) {
                            return false;
                        }
                        const haystack = `${el.getAttribute('data-id') || ''} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''} ${el.className || ''} ${el.innerText || ''}`.toLowerCase();
                        return haystack.includes('send') || haystack.includes('gửi') || haystack.includes('gui');
                    });
                    candidates.sort((a, b) => b.getBoundingClientRect().left - a.getBoundingClientRect().left);
                    const target = candidates[0];
                    if (!target) return false;
                    target.click();
                    return true;
                }
                """
            )
        )
    except Exception:
        return False


async def _outgoing_message_count(page: Page) -> int:
    best_count = 0
    for selector in OUTGOING_MESSAGE_SELECTORS:
        try:
            count = await page.locator(selector).count()
            if count > best_count:
                best_count = count
        except Exception:
            continue
    return best_count


async def _send_composer_content(page: Page, composer, chunk: str) -> None:
    await composer.click()
    await page.keyboard.press("Control+A")
    await page.keyboard.press("Backspace")
    await page.keyboard.insert_text(chunk)
    await page.wait_for_timeout(250)
    before_count = await _outgoing_message_count(page)

    for attempt in range(3):
        if attempt == 0:
            await page.keyboard.press("Enter")
        elif attempt == 1:
            if not await _click_send_button(page):
                await page.keyboard.press("Control+Enter")
        else:
            await page.keyboard.press("Enter")

        await page.wait_for_timeout(1800)
        after_count = await _outgoing_message_count(page)
        composer_empty = not await _composer_text(composer)
        if composer_empty and after_count >= before_count:
            return

    diagnostics = await _composer_debug_snapshot(page)
    artifacts = await save_page_artifacts(page, "broadcast-text-not-sent", diagnostics)
    raise RuntimeError(f"Zalo text remained in composer after send attempts; artifacts={artifacts}")


async def _composer_debug_snapshot(page: Page) -> Dict[str, Any]:
    try:
        return await page.evaluate(
            """
            () => {
                const rectOf = (el) => {
                    const rect = el.getBoundingClientRect();
                    return {
                        top: Math.round(rect.top),
                        left: Math.round(rect.left),
                        width: Math.round(rect.width),
                        height: Math.round(rect.height),
                        bottom: Math.round(rect.bottom),
                    };
                };
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 &&
                        rect.height > 0 &&
                        rect.bottom > 0 &&
                        rect.right > 0 &&
                        rect.top < window.innerHeight &&
                        rect.left < window.innerWidth &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none' &&
                        Number(style.opacity || '1') > 0;
                };
                const describe = (el) => ({
                    tag: el.tagName,
                    id: el.id || '',
                    className: String(el.className || '').slice(0, 180),
                    dataId: el.getAttribute('data-id') || '',
                    role: el.getAttribute('role') || '',
                    ariaLabel: el.getAttribute('aria-label') || '',
                    contenteditable: el.getAttribute('contenteditable') || '',
                    text: (el.innerText || el.value || '').trim().slice(0, 120),
                    rect: rectOf(el),
                });
                const composerCandidates = Array.from(document.querySelectorAll(
                    "[contenteditable], [data-lexical-editor='true'], [role='textbox'], [aria-multiline='true'], textarea"
                )).filter(visible).map(describe).slice(0, 30);
                const bottomButtons = Array.from(document.querySelectorAll(
                    "button, [role='button'], [data-id]"
                )).filter((el) => {
                    const rect = el.getBoundingClientRect();
                    return visible(el) && rect.top > window.innerHeight * 0.45;
                }).map(describe).slice(0, 50);
                return {
                    url: location.href,
                    title: document.title,
                    viewport: { width: window.innerWidth, height: window.innerHeight },
                    activeElement: document.activeElement ? describe(document.activeElement) : null,
                    composerCandidates,
                    bottomButtons,
                };
            }
            """
        )
    except Exception as exc:
        return {"error": str(exc)}


async def _wait_for_chat_ready(page: Page, timeout_ms: int = 30000) -> None:
    deadline = _loop_time(page) + timeout_ms / 1000
    last_error: Optional[Exception] = None
    await page.keyboard.press("Escape")
    while _loop_time(page) < deadline:
        try:
            for selector in COMPOSER_SELECTORS:
                locator = page.locator(selector).first
                if await locator.count() > 0 and await locator.is_visible(timeout=500):
                    return
            if await _focus_composer_by_dom(page, click=False):
                return
            await page.mouse.click(980, 840)
            if await _focus_composer_by_dom(page, click=False):
                return
        except Exception as exc:
            last_error = exc
        await page.wait_for_timeout(500)
    diagnostics = await _composer_debug_snapshot(page)
    artifacts = await save_page_artifacts(page, "broadcast-composer-missing", diagnostics)
    raise RuntimeError(
        f"Zalo chat composer was not ready after {timeout_ms}ms: {last_error}; "
        f"artifacts={artifacts}"
    )


def _split_text_chunks(text: str, max_length: int = MAX_TEXT_CHUNK_LENGTH) -> List[str]:
    remaining = (text or "").strip()
    chunks: List[str] = []
    while len(remaining) > max_length:
        split_at = max(
            remaining.rfind("\n", 0, max_length),
            remaining.rfind(". ", 0, max_length),
            remaining.rfind(" ", 0, max_length),
        )
        if split_at < max_length // 2:
            split_at = max_length
        chunk = remaining[:split_at].strip()
        if chunk:
            chunks.append(chunk)
        remaining = remaining[split_at:].strip()
    if remaining:
        chunks.append(remaining)
    return chunks


async def _send_text(page: Page, content: str) -> None:
    text = (content or "").strip()
    if not text:
        raise RuntimeError("Empty text content")

    last_error: Optional[Exception] = None
    for selector in COMPOSER_SELECTORS:
        try:
            composer = page.locator(selector).first
            await composer.wait_for(state="visible", timeout=3000)
            for chunk in _split_text_chunks(text):
                await _send_composer_content(page, composer, chunk)
            return
        except Exception as exc:
            last_error = exc
            continue
    try:
        if await _focus_composer_by_dom(page):
            composer = page.locator("[contenteditable], [role='textbox'], [aria-multiline='true'], textarea").first
            for chunk in _split_text_chunks(text):
                await _send_composer_content(page, composer, chunk)
            return
    except Exception as exc:
        last_error = exc
    raise RuntimeError(f"Could not locate Zalo message composer: {last_error}")


async def _write_temp_image(content: bytes, suffix: str) -> str:
    fd, path = tempfile.mkstemp(prefix="zalo-broadcast-", suffix=suffix)
    with os.fdopen(fd, "wb") as tmp:
        tmp.write(content)
    return path


async def _download_to_temp(url: str, storage_path: Optional[str] = None) -> str:
    if storage_path:
        content, _content_type, ext = await download_asset_bytes(storage_path)
        return await _write_temp_image(content, ext)

    parsed = urlparse(url)
    suffix = os.path.splitext(parsed.path)[1] or ".jpg"
    async with httpx.AsyncClient(timeout=90, follow_redirects=True) as client:
        response = await client.get(url)
    if response.status_code >= 400:
        raise RuntimeError(f"Image download failed: HTTP {response.status_code}")
    return await _write_temp_image(response.content, suffix)


async def _existing_file_input(page: Page):
    file_inputs = page.locator("input[type='file'][accept*='image'], input[type='file']")
    if await file_inputs.count() > 0:
        return file_inputs.first
    return None


async def _upload_debug_snapshot(page: Page) -> Dict[str, Any]:
    try:
        return await page.evaluate(
            """
            () => {
                const visible = (el) => {
                    const rect = el.getBoundingClientRect();
                    const style = window.getComputedStyle(el);
                    return rect.width > 0 &&
                        rect.height > 0 &&
                        rect.bottom > 0 &&
                        rect.right > 0 &&
                        rect.top < window.innerHeight &&
                        rect.left < window.innerWidth &&
                        style.visibility !== 'hidden' &&
                        style.display !== 'none' &&
                        Number(style.opacity || '1') > 0;
                };
                const describe = (el) => {
                    const rect = el.getBoundingClientRect();
                    return {
                        tag: el.tagName,
                        id: el.id || '',
                        className: String(el.className || '').slice(0, 180),
                        dataId: el.getAttribute('data-id') || '',
                        role: el.getAttribute('role') || '',
                        ariaLabel: el.getAttribute('aria-label') || '',
                        title: el.getAttribute('title') || '',
                        text: (el.innerText || el.value || '').trim().slice(0, 120),
                        rect: {
                            top: Math.round(rect.top),
                            left: Math.round(rect.left),
                            width: Math.round(rect.width),
                            height: Math.round(rect.height),
                        },
                    };
                };
                const inputs = Array.from(document.querySelectorAll("input[type='file']"))
                    .map((el) => ({ ...describe(el), accept: el.getAttribute('accept') || '' }));
                const lowerControls = Array.from(document.querySelectorAll("button, [role='button'], [data-id], [aria-label], [title]"))
                    .filter((el) => visible(el) && el.getBoundingClientRect().top > window.innerHeight * 0.35)
                    .map(describe)
                    .slice(0, 80);
                return {
                    url: location.href,
                    title: document.title,
                    inputs,
                    lowerControls,
                };
            }
            """
        )
    except Exception as exc:
        return {"error": str(exc)}


async def _click_image_upload_trigger_by_dom(page: Page) -> bool:
    try:
        return bool(
            await page.evaluate(
                """
                () => {
                    const visible = (el) => {
                        const rect = el.getBoundingClientRect();
                        const style = window.getComputedStyle(el);
                        return rect.width > 8 &&
                            rect.height > 8 &&
                            rect.bottom > 0 &&
                            rect.right > 0 &&
                            rect.top < window.innerHeight &&
                            rect.left < window.innerWidth &&
                            style.visibility !== 'hidden' &&
                            style.display !== 'none' &&
                            Number(style.opacity || '1') > 0;
                    };
                    const normalize = (value) => (value || '')
                        .normalize('NFD')
                        .replace(/[\\u0300-\\u036f]/g, '')
                        .toLowerCase();
                    const nodes = Array.from(document.querySelectorAll(
                        "button, [role='button'], [data-id], [aria-label], [title], .chat-box-toolbar-button"
                    ));
                    const candidates = nodes.filter((el) => {
                        if (!visible(el)) return false;
                        const rect = el.getBoundingClientRect();
                        if (rect.top < window.innerHeight * 0.55) return false;
                        const haystack = normalize(`${el.getAttribute('data-id') || ''} ${el.getAttribute('aria-label') || ''} ${el.getAttribute('title') || ''} ${el.className || ''} ${el.innerText || ''}`);
                        return haystack.includes('gui hinh anh') ||
                            haystack.includes('hinh anh') ||
                            haystack.includes('sendphoto') ||
                            haystack.includes('photo') ||
                            haystack.includes('image');
                    });
                    candidates.sort((a, b) => {
                        const ar = a.getBoundingClientRect();
                        const br = b.getBoundingClientRect();
                        return ar.left - br.left;
                    });
                    const target = candidates[0];
                    if (!target) return false;
                    target.click();
                    return true;
                }
                """
            )
        )
    except Exception:
        return False


async def _set_image_file(page: Page, path: str) -> None:
    await page.keyboard.press("Escape")
    await page.wait_for_timeout(500)

    existing_input = await _existing_file_input(page)
    if existing_input is not None:
        await existing_input.set_input_files(path)
        return

    for selector in ATTACH_IMAGE_SELECTORS:
        try:
            trigger = page.locator(selector).first
            if await trigger.count() == 0:
                continue
            async with page.expect_file_chooser(timeout=2500) as chooser_info:
                await trigger.click(timeout=1500)
            chooser = await chooser_info.value
            await chooser.set_files(path)
            return
        except Exception as exc:
            logger.debug(f"Could not use Zalo upload trigger {selector}: {exc}")
            try:
                existing_input = await _existing_file_input(page)
                if existing_input is not None:
                    await existing_input.set_input_files(path)
                    return
            except Exception:
                pass
            continue
    try:
        async with page.expect_file_chooser(timeout=3000) as chooser_info:
            if not await _click_image_upload_trigger_by_dom(page):
                raise RuntimeError("no_dom_upload_trigger")
        chooser = await chooser_info.value
        await chooser.set_files(path)
        return
    except Exception as exc:
        logger.debug(f"Could not use DOM upload trigger: {exc}")
        existing_input = await _existing_file_input(page)
        if existing_input is not None:
            await existing_input.set_input_files(path)
            return
    diagnostics = await _upload_debug_snapshot(page)
    artifacts = await save_page_artifacts(page, "broadcast-upload-input-missing", diagnostics)
    raise RuntimeError(f"Zalo upload input was not found; artifacts={artifacts}")

async def _send_image_asset(page: Page, asset: Dict[str, Any]) -> None:
    storage_path = asset.get("storage_path")
    storage_url = asset.get("storage_url")
    if not storage_path and not storage_url:
        raise RuntimeError("Uploaded image asset has no storage path or URL")

    try:
        temp_path = await _download_to_temp(storage_url or "", storage_path=storage_path)
    except Exception:
        if not storage_url:
            raise
        temp_path = await _download_to_temp(storage_url)
    try:
        before_count = await _outgoing_message_count(page)
        await _set_image_file(page, temp_path)
        await page.wait_for_timeout(1500)
        for attempt in range(3):
            if attempt == 0:
                await page.keyboard.press("Enter")
            elif attempt == 1:
                await _click_send_button(page)
            else:
                await page.keyboard.press("Enter")
            await page.wait_for_timeout(2200)
            after_count = await _outgoing_message_count(page)
            if after_count > before_count:
                return
        diagnostics = await _upload_debug_snapshot(page)
        artifacts = await save_page_artifacts(page, "broadcast-image-not-sent", diagnostics)
        raise RuntimeError(f"Zalo image did not appear sent after upload attempts; artifacts={artifacts}")
    finally:
        try:
            os.remove(temp_path)
        except OSError:
            pass


def _uploaded_assets(message: Dict[str, Any]) -> List[Dict[str, Any]]:
    assets: List[Dict[str, Any]] = []
    for asset in message.get("assets") or []:
        if asset.get("status") == "uploaded" and (asset.get("storage_url") or asset.get("storage_path")):
            assets.append(asset)
    return assets


async def send_broadcast_to_targets(
    page: Page,
    campaign_id: str,
    messages: List[Dict[str, Any]],
    targets: List[Dict[str, Any]],
    content_mode: str,
    delay_seconds: float,
    composer_timeout_seconds: int,
    log_callback,
) -> None:
    for target in targets:
        group_name = target["group_name"]
        group_id = target.get("group_id")
        composer_timeout_ms = max(30, composer_timeout_seconds) * 1000

        async def ensure_target_ready() -> None:
            await open_conversation_for_send(page, group_id, group_name)
            await _wait_for_chat_ready(page, timeout_ms=composer_timeout_ms)

        try:
            await ensure_target_ready()
            await log_callback(campaign_id, group_name, "opened", "Opened target group")

            for message in messages:
                message_id = message["id"]
                send_text = content_mode in {"text", "both"} and bool((message.get("content") or "").strip())
                send_images = content_mode in {"image", "both"}
                image_assets = _uploaded_assets(message) if send_images else []

                if not send_text and not image_assets:
                    await log_callback(campaign_id, group_name, "skipped", "No selected content to send", message_id)
                    continue

                try:
                    if send_text:
                        await ensure_target_ready()
                        await _send_text(page, message["content"])
                        await log_callback(campaign_id, group_name, "sent", "Text sent", message_id)
                    for image_asset in image_assets:
                        await ensure_target_ready()
                        await _send_image_asset(page, image_asset)
                        await log_callback(campaign_id, group_name, "sent", "Image sent", message_id)
                except Exception as exc:
                    logger.warning(f"Failed to send broadcast message {message_id} to {group_name}: {exc}")
                    await log_callback(campaign_id, group_name, "failed", str(exc), message_id)

                await asyncio.sleep(max(0.5, delay_seconds))
        except Exception as exc:
            logger.warning(f"Failed to send broadcast campaign {campaign_id} to group {group_name}: {exc}")
            await log_callback(campaign_id, group_name, "failed", str(exc))
