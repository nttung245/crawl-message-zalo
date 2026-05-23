import re
from typing import Any, List, Set
from urllib.parse import urlparse

from loguru import logger
from playwright.async_api import Frame, Page

from app.modules.zalo.schemas.message import Message

ZALO_CDN_PATTERNS = ["zalo.me", "zalostatic", "zalostg", "zadn.vn", "cdn.zalo"]
THUMB_PATTERNS = ["_thumb", "_small", "_icon", "thumbnail"]

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
(element) => {
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
        textContent = uniqueLines(textContainer.textContent || "");
    } else {
        const rtfNodes = Array.from(
            element.querySelectorAll(".editor-input [data-z-element-type='rtf-text']")
        );
        if (rtfNodes.length) {
            textContent = uniqueLines(rtfNodes.map((node) => node.textContent || "").join("\n"));
        } else {
            const genericText = element.querySelector(".overflow-hidden [data-component='message-text-content']");
            textContent = uniqueLines(genericText ? genericText.textContent || "" : "");
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

    const imageBlobUrls = Array.from(
        element.querySelectorAll("img[src^='blob:'], .img-msg-v2 img[src]")
    ).map((img) => img.getAttribute("src") || "").filter(Boolean);

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
        has_image: !!element.querySelector("[id^='image-mCntr_'], .img-msg-v2, .photo-message-v2"),
        has_file: !!element.querySelector(".file-message__container"),
        has_link: !!element.querySelector(".link-message"),
        has_sticker: !!element.querySelector("[class*='sticker'], img[class*='sticker']"),
        image_blob_urls: imageBlobUrls,
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


def _normalize_timestamp(date_text: str | None, time_text: str | None) -> str | None:
    date_text = (date_text or "").strip()
    time_text = (time_text or "").strip()
    if date_text and time_text and time_text not in date_text:
        return f"{time_text} {date_text}"
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


async def parse_messages(page: Page, captured_image_urls: Set[str]) -> List[Message]:
    messages: List[Message] = []
    last_named_sender: str | None = None

    items = []
    selector_used = None
    selector_counts: dict[str, dict[str, int]] = {}
    target_label = "main"
    targets: list[tuple[str, Page | Frame]] = [("main", page)]
    for index, frame in enumerate(page.frames):
        if frame is page.main_frame:
            continue
        frame_url = (frame.url or "").strip()
        targets.append((f"frame[{index}] {frame_url or '(about:blank)'}", frame))

    for label, target in targets:
        per_target_counts: dict[str, int] = {}
        for selector in MSG_CONTAINER_SELECTORS:
            found = await target.query_selector_all(selector)
            per_target_counts[selector] = len(found)
            if found:
                items = found
                selector_used = selector
                target_label = label
                logger.debug(
                    f"Found {len(found)} message elements with selector: {selector} in {label}"
                )
                break
        selector_counts[label] = per_target_counts
        if items:
            break

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
    is_deleted = "Ä‘Ã£ bá»‹ thu há»“i" in lowered or "message was unsent" in lowered

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
        image_urls = _image_urls_from_capture(captured_image_urls)
        if not image_urls and data.get("image_blob_urls"):
            image_urls = list(data["image_blob_urls"])
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

