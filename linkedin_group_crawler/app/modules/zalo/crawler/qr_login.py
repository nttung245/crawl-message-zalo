from typing import Any, Dict, List, Optional, Tuple, Union
import base64
import hashlib
import time

from loguru import logger
from playwright.async_api import Error as PlaywrightError, Frame, Page

from app.modules.zalo.services.debug_artifacts import save_page_artifacts

ZALO_WEB_URL = "https://chat.zalo.me"
_last_account_continue_click_at = 0.0

CANVAS_SELECTORS = [
    "canvas.qr-img",
    ".qr-panel canvas",
    "canvas[class*=qr]",
    "[class*=qr-code] canvas",
    "[class*=QRCode] canvas",
    "[class*=login] canvas",
]

IMG_SELECTORS = [
    "img[class*=qr]",
    "img[class*=QR]",
    "[class*=qr] img",
    "[class*=QR] img",
    "[class*=login] img",
]

QR_SCREENSHOT_FALLBACK_SELECTORS = [
    *CANVAS_SELECTORS,
    *IMG_SELECTORS,
    "[class*=qr]",
    "[id*=qr]",
    "[data-id*=QR]",
    "[data-id*=qr]",
]

QR_PRIMARY_SCREENSHOT_SELECTORS = [
    "canvas.qr-img",
    ".qr-panel canvas",
    "[class*=qr-code] canvas",
    "[class*=QRCode] canvas",
    "canvas[class*=qr]",
    "img[class*=qr]",
    "img[class*=QR]",
    "[class*=qr] img",
    "[class*=QR] img",
]

ACCOUNT_CONTINUE_SELECTORS = [
    "button:has-text('Tiếp tục')",
    "button:has-text('Tiep tuc')",
    "button:has-text('Continue')",
    "a:has-text('Tiếp tục')",
    "a:has-text('Tiep tuc')",
    "a:has-text('Continue')",
    "[role='button']:has-text('Tiếp tục')",
    "[role='button']:has-text('Tiep tuc')",
    "[role='button']:has-text('Continue')",
    "text=Tiếp tục",
    "text=Tiep tuc",
    "text=Continue",
]

_JS_CANVAS = """
(selectors) => {
    const isVisible = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (!style) return false;
        if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) {
            return false;
        }
        const rect = el.getBoundingClientRect();
        if (rect.width < 140 || rect.height < 140) return false;
        const ratio = rect.width / rect.height;
        return ratio > 0.75 && ratio < 1.25;
    };
    for (const sel of selectors) {
        const canvas = document.querySelector(sel);
        if (!canvas || !isVisible(canvas) || canvas.width < 140 || canvas.height < 140) continue;
        try {
            const dataUrl = canvas.toDataURL('image/png');
            if (dataUrl && dataUrl.length > 2000) return dataUrl;
        } catch (_) {}
    }
    return null;
}
"""

_JS_IMG = """
(selectors) => {
    const isVisible = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (!style) return false;
        if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) {
            return false;
        }
        const rect = el.getBoundingClientRect();
        if (rect.width < 140 || rect.height < 140) return false;
        const ratio = rect.width / rect.height;
        return ratio > 0.75 && ratio < 1.25;
    };
    for (const sel of selectors) {
        const img = document.querySelector(sel);
        if (!img || !img.src || !isVisible(img) || img.naturalWidth < 140 || img.naturalHeight < 140) continue;
        return img.src;
    }
    return null;
}
"""

_JS_CHECK_LOGGED_IN = """
() => {
    const inChatUrl = typeof location?.href === 'string' && location.href.includes('chat.zalo.me');
    if (!inChatUrl) return 'waiting:notChatUrl';

    const loggedInSelectors = [
        '#chatView',
        '#messageView',
        '#chatInput',
        '#messageViewScroll',
        '[data-component="message-content-view"]',
        '[data-id="div_SentMsg_Text"]',
        '[data-id="div_ReceivedMsg_Text"]',
        '.message-view',
        '.chat-box-input-container'
    ];
    for (const sel of loggedInSelectors) {
        if (document.querySelector(sel)) return 'confirmed:chatDom';
    }

    const appEl = document.querySelector(
        '[class*=contact],[class*=Contact],[class*=conv],[class*=Conv],' +
        '[class*=sidebar],[class*=Sidebar],[class*=friend],[class*=Friend],' +
        '[class*=chatList],[class*=msgList],[class*=userList],' +
        '[contenteditable="true"],textarea,input'
    );

    const convCount = document.querySelectorAll(
        '.conv-list-item, .contact-item, [class*=ConvItem], [class*=conversation-item]'
    ).length;
    if (convCount > 0) return 'confirmed:conversationList';

    const chatComposer = document.querySelector('[contenteditable="true"], textarea');
    if (chatComposer) return 'confirmed:composer';

    if (appEl) return 'confirmed:appElement';

    const rawText = ((document.body ? document.body.innerText : '') || '').toLowerCase();
    const text = rawText.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
    if (
        text.includes('het han') ||
        text.includes('ma qr het han') ||
        text.includes('lay ma moi') ||
        text.includes('refresh qr') ||
        text.includes('reload qr')
    ) {
        return 'qr_expired';
    }

    const qrSelectors = [
        'canvas.qr-img',
        '.qr-panel canvas',
        'canvas[class*=qr]',
        '[class*=qr-code] canvas',
        '[class*=QRCode] canvas',
        'img[class*=qr]',
        'img[class*=QR]',
        '[class*=qr] img'
    ];
    const isVisible = (el) => {
        if (!el) return false;
        const style = window.getComputedStyle(el);
        if (!style) return false;
        if (style.display === 'none' || style.visibility === 'hidden' || Number(style.opacity) === 0) {
            return false;
        }
        const rect = el.getBoundingClientRect();
        return rect.width > 50 && rect.height > 50;
    };
    for (const sel of qrSelectors) {
        const qrEl = document.querySelector(sel);
        if (isVisible(qrEl)) return 'waiting_scan';
    }

    return inChatUrl ? 'confirmed:fallbackChatUrl' : 'waiting_scan';
}
"""

_JS_QR_EXPIRED = """
() => {
    const rawText = ((document.body ? document.body.innerText : '') || '').toLowerCase();
    const text = rawText.normalize('NFD').replace(/[\\u0300-\\u036f]/g, '');
    return (
        text.includes('het han') ||
        text.includes('ma qr het han') ||
        text.includes('lay ma moi') ||
        text.includes('refresh qr') ||
        text.includes('reload qr')
    );
}
"""


class ZaloAlreadyLoggedInError(RuntimeError):
    """Raised when the page is already in a confirmed logged-in state."""


def _qr_targets(page: Page) -> List[Tuple[str, Union[Page, Frame]]]:
    targets: List[Tuple[str, Union[Page, Frame]]] = [("main", page)]
    for index, frame in enumerate(page.frames):
        if frame is page.main_frame:
            continue
        frame_url = (frame.url or "").strip()
        targets.append((f"frame[{index}] {frame_url or '(about:blank)'}", frame))
    return targets


async def _canvas_data_url(page: Page) -> Optional[str]:
    for label, target in _qr_targets(page):
        try:
            data_url = await target.evaluate(_JS_CANVAS, CANVAS_SELECTORS)
            if data_url:
                logger.debug(f"QR canvas found in {label}")
                return data_url
        except PlaywrightError as exc:
            if "Execution context was destroyed" in str(exc):
                logger.debug(f"QR canvas evaluation interrupted by navigation in {label}; will retry")
                return None
            logger.debug(f"QR canvas evaluation error in {label}: {exc}")
        except Exception as exc:
            logger.debug(f"QR canvas evaluation failed in {label}: {exc}")
    return None


async def _img_src(page: Page) -> Optional[str]:
    for label, target in _qr_targets(page):
        try:
            src = await target.evaluate(_JS_IMG, IMG_SELECTORS)
            if src:
                logger.debug(f"QR image found in {label}")
                return src
        except PlaywrightError as exc:
            if "Execution context was destroyed" in str(exc):
                logger.debug(f"QR image evaluation interrupted by navigation in {label}; will retry")
                return None
            logger.debug(f"QR image evaluation error in {label}: {exc}")
        except Exception as exc:
            logger.debug(f"QR image evaluation failed in {label}: {exc}")
    return None


async def qr_element_screenshot_bytes(page: Page) -> Optional[bytes]:
    for label, target in _qr_targets(page):
        for selector in QR_PRIMARY_SCREENSHOT_SELECTORS:
            try:
                handle = await target.query_selector(selector)
                if not handle:
                    continue
                box = await handle.bounding_box()
                if not box or box["width"] < 140 or box["height"] < 140:
                    continue
                ratio = box["width"] / box["height"]
                if ratio <= 0.75 or ratio >= 1.25:
                    continue
                shot = await handle.screenshot(type="png")
                if not shot:
                    continue
                logger.info(f"QR captured via visible element screenshot in {label} using selector={selector}")
                return shot
            except PlaywrightError as exc:
                if "Execution context was destroyed" in str(exc):
                    logger.debug(f"QR screenshot interrupted by navigation in {label}; will retry")
                    return None
                logger.debug(f"QR screenshot error in {label} selector={selector}: {exc}")
            except Exception as exc:
                logger.debug(f"QR screenshot failed in {label} selector={selector}: {exc}")
    return None


async def _qr_element_screenshot_data_url(page: Page) -> Optional[str]:
    shot = await qr_element_screenshot_bytes(page)
    if not shot:
        return None
    return "data:image/png;base64," + base64.b64encode(shot).decode()


async def _capture_qr(page: Page) -> str:
    screenshot_data_url = await _qr_element_screenshot_data_url(page)
    if screenshot_data_url:
        return screenshot_data_url

    data_url = await _canvas_data_url(page)
    if data_url:
        logger.info("QR captured via canvas.toDataURL()")
        return data_url

    src = await _img_src(page)
    if src:
        if src.startswith("data:"):
            logger.info("QR captured from img data URL")
            return src
        try:
            resp = await page.request.get(src)
            b64 = base64.b64encode(await resp.body()).decode()
            logger.info("QR captured by fetching img URL")
            return "data:image/png;base64," + b64
        except Exception as exc:
            logger.warning(f"Could not fetch img src {src}: {exc}")

    logger.warning("No QR matched via data extraction, trying element screenshot fallback")
    for label, target in _qr_targets(page):
        for selector in QR_SCREENSHOT_FALLBACK_SELECTORS:
            try:
                handle = await target.query_selector(selector)
                if not handle:
                    continue
                box = await handle.bounding_box()
                if not box or box["width"] < 140 or box["height"] < 140:
                    continue
                ratio = box["width"] / box["height"]
                if ratio <= 0.75 or ratio >= 1.25:
                    continue
                shot = await handle.screenshot(type="png")
                logger.info(f"QR captured via element screenshot fallback in {label} using selector={selector}")
                return "data:image/png;base64," + base64.b64encode(shot).decode()
            except Exception:
                continue

    await _save_qr_failure_artifacts(
        page,
        "qr-capture-failed",
        {
            "stage": "capture_qr",
            "message": "Could not locate a QR canvas or image element",
        },
    )
    raise RuntimeError("Could not extract QR from canvas or image")


async def _capture_qr_if_ready(page: Page) -> Optional[str]:
    screenshot_data_url = await _qr_element_screenshot_data_url(page)
    if screenshot_data_url:
        return screenshot_data_url

    data_url = await _canvas_data_url(page)
    if data_url:
        return data_url

    src = await _img_src(page)
    if not src:
        return None
    if src.startswith("data:"):
        return src

    try:
        resp = await page.request.get(src)
        b64 = base64.b64encode(await resp.body()).decode()
        return "data:image/png;base64," + b64
    except Exception as exc:
        logger.warning(f"Could not fetch img src {src}: {exc}")
        return None


async def _save_qr_failure_artifacts(page: Page, name: str, metadata: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    debug_metadata: Dict[str, Any] = dict(metadata or {})
    try:
        debug_metadata.setdefault("url", page.url)
    except Exception:
        debug_metadata.setdefault("url", "unknown")
    try:
        debug_metadata.setdefault("title", await page.title())
    except Exception:
        debug_metadata.setdefault("title", "unknown")
    try:
        debug_metadata.setdefault("login_status", await check_login_status(page))
    except Exception as exc:
        debug_metadata.setdefault("login_status", f"error:{type(exc).__name__}")
    return await save_page_artifacts(page, name, debug_metadata)


async def _try_continue_from_account_page(page: Page) -> bool:
    """Some Zalo flows stay on the account page after QR scan and require a continue click."""
    global _last_account_continue_click_at

    try:
        if "id.zalo.me/account" not in page.url:
            return False
    except Exception:
        return False

    now = time.monotonic()
    if now - _last_account_continue_click_at < 8:
        return False

    for selector in ACCOUNT_CONTINUE_SELECTORS:
        try:
            locator = page.locator(selector)
            if await locator.count():
                target = locator.first
                try:
                    await target.scroll_into_view_if_needed(timeout=1000)
                except Exception:
                    pass
                _last_account_continue_click_at = time.monotonic()
                await target.click(timeout=2000, force=True)
                await page.wait_for_timeout(1500)
                logger.info(f"Clicked continue on Zalo account page: {selector}")
                return True
        except Exception as exc:
            logger.debug(f"Could not click continue selector {selector}: {exc}")

    return False


async def _wait_for_stable_qr(page: Page, previous_signature: Optional[str] = None) -> Optional[str]:
    """Return a QR only after it is observed more than once in a row.

    Zalo can render the QR canvas before the bitmap is fully settled. Returning the
    first canvas snapshot too early can produce a QR that scans but is already stale.
    Requiring two matching captures reduces those false positives.
    """
    last_data_url: Optional[str] = None
    last_signature: Optional[str] = None

    for _ in range(8):
        try:
            if await page.evaluate(_JS_QR_EXPIRED):
                return None
        except Exception:
            pass

        data_url = await _capture_qr_if_ready(page)
        if not data_url:
            last_data_url = None
            last_signature = None
            await page.wait_for_timeout(250)
            continue

        current_signature = qr_signature(data_url)
        if previous_signature and current_signature == previous_signature:
            last_data_url = data_url
            last_signature = current_signature
            await page.wait_for_timeout(250)
            continue

        if last_signature and current_signature == last_signature and last_data_url == data_url:
            logger.info("QR stabilized across consecutive captures")
            return data_url

        last_data_url = data_url
        last_signature = current_signature
        await page.wait_for_timeout(300)

    if previous_signature and last_signature == previous_signature:
        return None
    return last_data_url


def qr_signature(data_url: Optional[str]) -> str:
    if not data_url:
        return ""
    return hashlib.sha256(data_url.encode("utf-8")).hexdigest()


async def navigate_and_get_qr(page: Page) -> str:
    logger.info(f"Navigating to {ZALO_WEB_URL}")
    await page.goto(ZALO_WEB_URL, wait_until="domcontentloaded", timeout=60000)
    await _try_continue_from_account_page(page)

    if await check_login_status(page) == "confirmed":
        raise ZaloAlreadyLoggedInError("Zalo is already logged in")

    for attempt in range(30):
        if attempt:
            await page.wait_for_timeout(500)
        data_url = await _wait_for_stable_qr(page)
        if data_url:
            logger.info(f"QR ready after ~{attempt * 0.5:.1f}s")
            return data_url
        if await check_login_status(page) == "confirmed":
            raise ZaloAlreadyLoggedInError("Zalo is already logged in")
        logger.debug(f"Waiting for QR render ({attempt + 1}/30)")

    if await check_login_status(page) == "confirmed":
        raise ZaloAlreadyLoggedInError("Zalo is already logged in")
    return await _capture_qr(page)


async def check_login_status(page: Page) -> str:
    try:
        if page is None:
            return "waiting_scan"
        await _try_continue_from_account_page(page)
        url = page.url
        title = await page.title()
        result: str = await page.evaluate(_JS_CHECK_LOGGED_IN)
        logger.debug(f"Status check - url={url!r} title={title!r} js={result!r}")
        if result == "qr_expired":
            logger.info("QR expired")
            return "qr_expired"
        if "id.zalo.me/account" in url or "Đăng nhập" in title or "Dang nhap" in title:
            logger.info(f"Zalo account/login page is not crawl-ready yet (url={url!r}, title={title!r})")
            return "waiting_scan"
        if result.startswith("confirmed"):
            logger.info(f"Login confirmed ({result})")
            return "confirmed"
        return "waiting_scan"
    except Exception as exc:
        logger.warning(f"check_login_status error: {exc}")
        return "waiting_scan"


async def refresh_qr(page: Page) -> str:
    return await refresh_qr_with_previous(page, previous_signature=None)


async def refresh_qr_with_previous(page: Page, previous_signature: Optional[str]) -> str:
    clicked_refresh = False
    try:
        clicked_by_text = await page.evaluate(
            """
            () => {
                const normalize = (value) => String(value || '')
                    .toLowerCase()
                    .normalize('NFD')
                    .replace(/[\\u0300-\\u036f]/g, '');
                const candidates = Array.from(document.querySelectorAll('button, [role="button"], a'));
                for (const el of candidates) {
                    const text = normalize(el.innerText || el.textContent || el.getAttribute('aria-label'));
                    if (
                        text.includes('lay ma moi') ||
                        text.includes('lam moi') ||
                        text.includes('tai lai') ||
                        text.includes('refresh')
                    ) {
                        el.click();
                        return true;
                    }
                }
                return false;
            }
            """
        )
        if clicked_by_text:
            await page.wait_for_timeout(1000)
            clicked_refresh = True
            logger.info("Clicked refresh QR by normalized text")
    except Exception as exc:
        logger.debug(f"Could not click refresh QR by normalized text: {exc}")

    for selector in [
        "[class*=refresh]",
        "button[class*=refresh]",
        ".refresh-qr",
        "button:has-text('LÃ m má»›i')",
        "button:has-text('Lam moi')",
        "button:has-text('Refresh')",
        "button:has-text('Táº£i láº¡i')",
    ]:
        try:
            locator = page.locator(selector)
            if await locator.count():
                await locator.first.click(timeout=2000)
                await page.wait_for_timeout(800)
                clicked_refresh = True
                logger.info(f"Clicked refresh QR: {selector}")
                break
        except Exception:
            continue

    for _ in range(20):
        data_url = await _wait_for_stable_qr(page, previous_signature=previous_signature)
        if not data_url:
            await page.wait_for_timeout(300)
            continue
        current_sig = qr_signature(data_url)
        if not previous_signature or current_sig != previous_signature:
            logger.info("QR refreshed with a new signature")
            return data_url
        await page.wait_for_timeout(300)

    if clicked_refresh:
        logger.warning("QR signature did not change after refresh click; forcing page reload")
    else:
        logger.warning("Refresh button not found; forcing page reload")

    await page.goto(ZALO_WEB_URL, wait_until="domcontentloaded", timeout=60000)
    for _ in range(30):
        try:
            if await page.evaluate(_JS_QR_EXPIRED):
                await page.wait_for_timeout(400)
                continue
        except Exception:
            pass

        data_url = await _capture_qr_if_ready(page)
        if data_url:
            current_sig = qr_signature(data_url)
            if not previous_signature or current_sig != previous_signature:
                logger.info("QR refreshed after page reload")
                return data_url
        await page.wait_for_timeout(400)

    await _save_qr_failure_artifacts(
        page,
        "qr-refresh-failed",
        {
            "stage": "refresh_qr_with_previous",
            "message": "Could not generate a fresh QR code after refresh attempts",
            "previous_signature": previous_signature,
        },
    )
    raise RuntimeError("Could not generate a fresh QR code")

