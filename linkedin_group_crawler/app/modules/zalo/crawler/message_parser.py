import base64
import re
from typing import Any, List, Set
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import Frame, Locator, Page

from app.modules.zalo.schemas.message import Message

ZALO_CDN_PATTERNS = ["zalo.me", "zalostatic", "zalostg", "zadn.vn", "cdn.zalo"]
THUMB_PATTERNS = ["_thumb", "_small", "_icon", "thumbnail"]
NON_MESSAGE_IMAGE_HINTS = [
    "avatar",
    "profile",
    "group_avatar",
    "oa_avatar",
    "ava_",
    "/ava/",
    "sticker",
    "emoji",
    "reaction",
]

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

_JS_EXTRACT_MESSAGE = r"""
async (element) => {
    const normalize = (value) =>
        (value || "")
            .replace(/\u00a0/g, " ")
            .replace(/\s+\n/g, "\n")
            .replace(/\n\s+/g, "\n")
            .replace(/[ \t]+/g, " ")
            .trim();

    const uniqueLines = (value) => {
        const lines = (value || "")
            .split("\n")
            .map((line) => normalize(line))
            .filter(Boolean);
        const result = [];
        for (const line of lines) {
            if (result[result.length - 1] !== line) result.push(line);
        }
        return result.join("\n");
    };

    const closestChatItem = element.closest(".chat-item");
    let dateText = "";
    if (closestChatItem) {
        let sibling = closestChatItem.previousElementSibling;
        while (sibling) {
            if (sibling.classList && sibling.classList.contains("chat-date")) {
                dateText = normalize(sibling.textContent || "");
                break;
            }
            sibling = sibling.previousElementSibling;
        }
    }

    const senderName =
        normalize(
            element.querySelector(".message-sender-name-content .truncate, .message-sender-name-content")
                ?.textContent || ""
        ) || null;

    let timeText = null;
    const timeCandidates = Array.from(
        element.querySelectorAll(".card-send-time__sendTime, .send-time, [class*='sendTime']")
    );
    for (const node of timeCandidates) {
        const value = normalize(node.textContent || "");
        if (/^\d{1,2}:\d{2}$/.test(value)) {
            timeText = value;
            break;
        }
    }

    const messageId =
        element.id ||
        element.getAttribute("data-id") ||
        element.querySelector("[id^='bb_msg_id_']")?.id ||
        null;

    const qid =
        element.getAttribute("data-qid") ||
        element.querySelector("[data-qid]")?.getAttribute("data-qid") ||
        null;

    let textContent = "";
    const textContainer = element.querySelector(".text-message__container [data-component='text-container']");
    if (textContainer) {
        textContent = uniqueLines(textContainer.innerText || textContainer.textContent || "");
    } else {
        const rtfNodes = Array.from(
            element.querySelectorAll(
                ".editor-input [data-z-element-type='rtf-text'], " +
                "[data-component='text-container'], " +
                "[data-component='message-text-content'], " +
                ".text-message__container span, " +
                ".text-message__container div"
            )
        );
        if (rtfNodes.length) {
            textContent = uniqueLines(
                rtfNodes
                    .map((node) => node.innerText || node.textContent || "")
                    .join("\n")
            );
        } else {
            const genericText = element.querySelector(".overflow-hidden [data-component='message-text-content']");
            textContent = uniqueLines(genericText ? genericText.innerText || genericText.textContent || "" : "");
        }
    }

    const linkUrl =
        element.querySelector(".link-message .text-is-link")?.getAttribute("data-content") ||
        element.querySelector(".link-message .text-is-link")?.getAttribute("href") ||
        null;
    const linkTitle =
        normalize(element.querySelector(".link-message__link-title")?.textContent || "") || null;

    const fileName =
        normalize(element.querySelector(".file-message__content-title")?.textContent || "") || null;

    // Only collect images from known message-photo containers. Generic img/blob selectors
    // can catch avatars, reactions, icons, or profile thumbnails near the bubble.
    const messageImageSelector = [
        "[id^='image-mCntr_'] img[src]",
        "[id^='image-mCntr_'] img",
        ".img-msg-v2 img[src]",
        ".img-msg-v2 img",
        ".photo-message-v2 img[src]",
        ".photo-message-v2 img",
        "[data-component='message-content-view'] [id^='image-mCntr_'] img[src]",
        "[data-component='message-content-view'] [id^='image-mCntr_'] img",
        "[data-component='message-content-view'] .img-msg-v2 img[src]",
        "[data-component='message-content-view'] .img-msg-v2 img",
        "[data-component='message-content-view'] .photo-message-v2 img[src]",
        "[data-component='message-content-view'] .photo-message-v2 img",
        "[data-component='message-content-view'] img[src]",
        "[data-component='message-content-view'] img[data-src]",
        "[data-component='message-content-view'] img",
    ].join(",");
    const isNonMessageImage = (img) => {
        const classSignals = [
            img.className || "",
            img.parentElement?.className || "",
            img.closest("[class]")?.className || "",
        ].join(" ").toLowerCase();
        const src = (img.getAttribute("src") || "").toLowerCase();
        const nearbyNonMessage = img.closest(
            "[class*='avatar'], [class*='Avatar'], [class*='profile'], [class*='sticker'], [class*='emoji'], [class*='reaction']"
        );
        const rect = img.getBoundingClientRect();
        const tooSmallForMessageImage =
            rect.width > 0 && rect.height > 0 && (rect.width < 40 || rect.height < 40);
        return (
            !!nearbyNonMessage ||
            /avatar|profile|sticker|emoji|reaction/.test(classSignals) ||
            /avatar|profile|group_avatar|oa_avatar|sticker|emoji|reaction/.test(src) ||
            tooSmallForMessageImage
        );
    };
    const imageSrcs = [];
    const addImageUrl = (url) => {
        if (url && !imageSrcs.includes(url)) imageSrcs.push(url);
    };
    const largestFromSrcset = (srcset) => {
        const candidates = (srcset || "")
            .split(",")
            .map((part) => part.trim())
            .filter(Boolean)
            .map((part) => {
                const [url, descriptor] = part.split(/\s+/);
                const score = descriptor?.endsWith("w")
                    ? Number(descriptor.slice(0, -1)) || 0
                    : descriptor?.endsWith("x")
                        ? (Number(descriptor.slice(0, -1)) || 0) * 1000
                        : 0;
                return { url, score };
            })
            .filter((item) => item.url);
        candidates.sort((left, right) => right.score - left.score);
        return candidates[0]?.url || "";
    };
    for (const img of Array.from(element.querySelectorAll(messageImageSelector)).filter((img) => !isNonMessageImage(img))) {
        const carrier = img.closest("[id^='image-mCntr_'], .img-msg-v2, .photo-message-v2, a, [data-href], [data-url], [data-original], [data-full-src]");
        addImageUrl(largestFromSrcset(img.getAttribute("srcset") || ""));
        addImageUrl(largestFromSrcset(img.getAttribute("data-srcset") || ""));
        addImageUrl(img.getAttribute("data-original"));
        addImageUrl(img.getAttribute("data-full-src"));
        addImageUrl(img.getAttribute("data-preview-src"));
        addImageUrl(img.closest("a")?.getAttribute("href") || "");
        addImageUrl(carrier?.getAttribute("href") || "");
        addImageUrl(carrier?.getAttribute("data-href") || "");
        addImageUrl(carrier?.getAttribute("data-url") || "");
        addImageUrl(carrier?.getAttribute("data-original") || "");
        addImageUrl(carrier?.getAttribute("data-full-src") || "");
        addImageUrl(carrier?.getAttribute("data-preview-src") || "");
        addImageUrl(img.currentSrc || img.getAttribute("src") || img.getAttribute("data-src") || "");
    }
    const backgroundImageUrls = Array.from(
        element.querySelectorAll("[data-component='message-content-view'] [style*='background-image'], [id^='image-mCntr_'] [style*='background-image'], .img-msg-v2 [style*='background-image'], .photo-message-v2 [style*='background-image']")
    ).map((node) => {
        const value = window.getComputedStyle(node).backgroundImage || "";
        const match = value.match(/url\\(["']?(.+?)["']?\\)/);
        return match ? match[1] : "";
    }).filter(Boolean);
    for (const url of backgroundImageUrls) {
        if (!imageSrcs.includes(url)) imageSrcs.push(url);
    }
    const imageCdnUrls = imageSrcs.filter((s) => s.startsWith("http"));
    const imageBlobUrls = imageSrcs.filter((s) => s.startsWith("blob:"));
    const imageUrlToDataUrl = async (url) => {
        try {
            if (url.startsWith("data:image/")) return url;
            const response = await fetch(url, { credentials: "include" });
            if (!response.ok) return null;
            const blob = await response.blob();
            if (!blob.type.startsWith("image/") || blob.size > 8 * 1024 * 1024) return null;
            return await new Promise((resolve) => {
                const reader = new FileReader();
                reader.onloadend = () => resolve(reader.result);
                reader.onerror = () => resolve(null);
                reader.readAsDataURL(blob);
            });
        } catch {
            return null;
        }
    };
    const imageDataUrls = [];
    for (const imageUrl of imageSrcs) {
        if (!imageUrl.startsWith("http") && !imageUrl.startsWith("blob:") && !imageUrl.startsWith("data:image/")) {
            continue;
        }
        const dataUrl = await imageUrlToDataUrl(imageUrl);
        if (dataUrl && !imageDataUrls.includes(dataUrl)) imageDataUrls.push(dataUrl);
    }

    const fullText = normalize(element.textContent || "");
    const frameEl = element.querySelector("[data-component='message-content-view']");
    const bubbleEl = element.querySelector(".chat-message");
    const chatItemEl = element.closest(".chat-item");
    const classSignals = [
        element.className || "",
        frameEl?.className || "",
        bubbleEl?.className || "",
        chatItemEl?.className || "",
    ].join(" ");
    const hasSentDataId = !!element.querySelector(
        "[data-id='div_SentMsg_Text'], [data-id='btn_SentMsg_React'], [data-id='btn_LastSentMsg_React'], [data-id='div_LastSentMsg_ReactList']"
    );

    const isSent =
        /\b(me|send-msg|msg-send|msg--out|msg-item--out|own-msg|message-wrapper--me)\b/i.test(classSignals) ||
        hasSentDataId ||
        (() => {
            const rect = element.getBoundingClientRect();
            return rect.width > 40 && rect.left > window.innerWidth * 0.55 && !senderName;
        })();

    return {
        message_id: messageId,
        qid,
        sender_name: senderName,
        time_text: timeText,
        date_text: dateText,
        text_content: textContent,
        link_url: linkUrl,
        link_title: linkTitle,
        file_name: fileName,
        has_image: imageSrcs.length > 0 || !!element.querySelector("[id^='image-mCntr_'], .img-msg-v2, .photo-message-v2"),
        has_file: !!element.querySelector(".file-message__container"),
        has_link: !!element.querySelector(".link-message"),
        has_sticker: !!element.querySelector("[class*='sticker'], img[class*='sticker']"),
        image_cdn_urls: imageCdnUrls,
        image_blob_urls: imageBlobUrls,
        image_data_urls: imageDataUrls,
        full_text: fullText,
        is_sent: isSent,
    };
}
"""


def _is_zalo_cdn_image(url: str) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    hostname = parsed.netloc.lower()
    return any(cdn in hostname for cdn in ZALO_CDN_PATTERNS)


def _is_full_res(url: str) -> bool:
    return not any(t in url.lower() for t in THUMB_PATTERNS)


def _is_likely_message_image_url(url: str) -> bool:
    lowered = (url or "").lower()
    if not lowered:
        return False
    if any(hint in lowered for hint in NON_MESSAGE_IMAGE_HINTS):
        return False
    return (
        lowered.startswith("blob:")
        or lowered.startswith("data:image/")
        or (_is_zalo_cdn_image(url) and _is_full_res(url))
    )


def _normalize_timestamp(date_text: str | None, time_text: str | None) -> str | None:
    date_text = (date_text or "").strip()
    time_text = (time_text or "").strip()
    if date_text and time_text and time_text not in date_text:
        return f"{date_text} {time_text}"
    return date_text or time_text or None


def _sender_id_from_qid(qid: str | None) -> str | None:
    if not qid:
        return None
    match = re.search(r"@[^_]+_([^_]+)_", qid)
    if match:
        return match.group(1)
    return None


def _image_urls_from_capture(captured_image_urls: Set[str]) -> List[str]:
    return [url for url in captured_image_urls if _is_zalo_cdn_image(url) and _is_full_res(url)]


async def _screenshot_message_image_data_url(item) -> str | None:
    selectors = [
        "[id^='image-mCntr_']",
        ".img-msg-v2",
        ".photo-message-v2",
        "[data-component='message-content-view'] [id^='image-mCntr_']",
        "[data-component='message-content-view'] .img-msg-v2",
        "[data-component='message-content-view'] .photo-message-v2",
        "[data-component='message-content-view'] img[src]",
        "[data-component='message-content-view'] img",
    ]
    for selector in selectors:
        try:
            handle = await item.query_selector(selector)
            if not handle:
                continue
            box = await handle.bounding_box()
            if not box or box["width"] < 40 or box["height"] < 40:
                continue
            shot = await handle.screenshot(type="png")
            if shot:
                return "data:image/png;base64," + base64.b64encode(shot).decode()
        except Exception:
            continue
    return None


async def parse_messages(root: Page | Frame | Locator, captured_image_urls: Set[str]) -> List[Message]:
    messages: List[Message] = []
    last_named_sender: str | None = None

    items = []
    selector_used = None
    selector_counts: dict[str, dict[str, int]] = {}
    target_label = "message-root"
    targets: list[tuple[str, Page | Frame | Locator]] = [("message-root", root)]
    if isinstance(root, Page):
        for index, frame in enumerate(root.frames):
            if frame is root.main_frame:
                continue
            frame_url = (frame.url or "").strip()
            targets.append((f"frame[{index}] {frame_url or '(about:blank)'}", frame))

    best_match: tuple[int, str, str, list] | None = None
    for label, target in targets:
        per_target_counts: dict[str, int] = {}
        for selector in MSG_CONTAINER_SELECTORS:
            if isinstance(target, Locator):
                found = await target.locator(selector).element_handles()
            else:
                found = await target.query_selector_all(selector)
            visible_found = []
            for handle in found:
                try:
                    is_current_visible = await handle.evaluate(
                        """
                        (el) => {
                            const rect = el.getBoundingClientRect();
                            const style = window.getComputedStyle(el);
                            if (rect.width <= 0 || rect.height <= 0) return false;
                            if (style.display === 'none' || style.visibility === 'hidden') return false;
                            if (Number(style.opacity || '1') <= 0) return false;
                            const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
                            const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
                            if (rect.bottom < -200 || rect.top > viewportHeight + 200) return false;
                            if (rect.right < 0 || rect.left > viewportWidth) return false;
                            const hiddenAncestor = el.closest('[aria-hidden="true"], [hidden]');
                            if (hiddenAncestor) return false;
                            return true;
                        }
                        """
                    )
                    if is_current_visible:
                        visible_found.append(handle)
                except Exception:
                    continue
            per_target_counts[selector] = len(visible_found)
            if visible_found:
                logger.debug(
                    f"Found {len(visible_found)} visible message elements with selector: {selector} in {label}"
                )
                if best_match is None or len(visible_found) > best_match[0]:
                    best_match = (len(visible_found), selector, label, visible_found)
        selector_counts[label] = per_target_counts

    if best_match:
        _, selector_used, target_label, items = best_match

    if not items:
        logger.warning(f"No message elements found in DOM; selector_counts={selector_counts}")
        return messages

    logger.info(
        f"Parsing {len(items)} message nodes using selector {selector_used} in target={target_label}"
    )
    for index, item in enumerate(items, start=1):
        try:
            msg = await _parse_message(item, captured_image_urls)
            if msg:
                if msg.is_sent:
                    if not msg.sender_name:
                        msg.sender_name = "__me__"
                else:
                    if msg.sender_name and msg.sender_name != "__me__":
                        last_named_sender = msg.sender_name
                    elif not msg.sender_name and last_named_sender:
                        msg.sender_name = last_named_sender
                messages.append(msg)
        except Exception as e:
            logger.warning(f"Failed to parse message #{index}: {e}")
            continue

    logger.info(f"Parsed {len(messages)} messages")
    return messages


async def _parse_message(item, captured_image_urls: Set[str]) -> Message | None:
    data: dict[str, Any] = await item.evaluate(_JS_EXTRACT_MESSAGE)

    message_id = data.get("message_id") or data.get("qid")
    if not message_id:
        return None

    full_text = (data.get("full_text") or "").strip()
    lowered = full_text.lower()
    # BUG FIX: Trước đây so sánh với chuỗi mojibake (UTF-8 bytes bị decode sai thành Latin-1).
    # Playwright trả về chuỗi Unicode chuẩn, cần so sánh đúng tiếng Việt có dấu.
    is_deleted = (
        "đã bị thu hồi" in lowered
        or "tin nhắn đã bị thu hồi" in lowered
        or "message was unsent" in lowered
        or "this message was deleted" in lowered
    )

    is_sent = bool(data.get("is_sent"))
    sender_name = data.get("sender_name")
    if is_sent:
        # Force owner label for right-side/sent bubbles to avoid quote/name pollution.
        sender_name = "__me__"

    sender_id = _sender_id_from_qid(data.get("qid"))
    time_text = data.get("time_text")
    timestamp = _normalize_timestamp(data.get("date_text"), data.get("time_text"))

    msg_type = "text"
    content = None
    image_urls: List[str] = []

    if data.get("has_image"):
        msg_type = "image"
        content = data.get("text_content") or None
        # BUG FIX: Trước đây dùng captured_image_urls (global pool) → tất cả message ảnh
        # đều nhận cùng một danh sách ảnh của toàn bộ group. Nay ưu tiên CDN URL từ DOM
        # của bubble cụ thể này. Chỉ fallback sang global pool khi bubble không có CDN src.
        bubble_cdn_urls = [
            url for url in (data.get("image_cdn_urls") or [])
            if isinstance(url, str) and _is_likely_message_image_url(url) and _is_zalo_cdn_image(url)
        ]
        if bubble_cdn_urls:
            # Prefer real CDN URLs. Data URLs are often generated from the visible
            # bubble thumbnail, which makes Supabase and resend output blurry.
            # Still keep browser-fetched data URLs as a fallback because many Zalo
            # CDN URLs require the active browser cookie and cannot be downloaded
            # later from the backend container.
            image_urls = bubble_cdn_urls + [
                url for url in (data.get("image_data_urls") or [])
                if isinstance(url, str) and _is_likely_message_image_url(url)
            ]
        elif data.get("image_blob_urls"):
            image_urls = [
                url for url in data["image_blob_urls"]
                if isinstance(url, str) and _is_likely_message_image_url(url)
            ]
        elif data.get("image_data_urls"):
            image_urls = [
                url for url in data["image_data_urls"]
                if isinstance(url, str) and _is_likely_message_image_url(url)
            ]
        if not image_urls:
            screenshot_data_url = await _screenshot_message_image_data_url(item)
            if screenshot_data_url:
                image_urls = [screenshot_data_url]
    elif is_deleted:
        msg_type = "system"
        content = "Tin nhan da bi thu hoi"
    elif data.get("has_file"):
        msg_type = "file"
        content = data.get("file_name") or full_text or None
    elif data.get("has_sticker"):
        msg_type = "sticker"
    elif data.get("has_link"):
        link_url = data.get("link_url")
        link_title = data.get("link_title")
        content = " | ".join(part for part in [link_title, link_url] if part) or full_text or None
    else:
        content = data.get("text_content") or full_text or None

    return Message(
        message_id=message_id,
        sender_id=sender_id,
        sender_name=sender_name,
        timestamp=timestamp,
        time_text=time_text,
        type=msg_type,
        content=content,
        image_urls=image_urls,
        reply_to_id=None,
        is_deleted=is_deleted,
        is_sent=is_sent,
    )

