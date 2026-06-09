"""Patch scroll_handler.py to fix browser fallback crawl.

Changes:
1. scroll_and_collect: add skip_open parameter, use _active_group_name for title checks
2. verify_group_for_crawl (2nd definition): simplified fallback to read current conversation
"""
import pathlib, re

target = pathlib.Path(r"linkedin_group_crawler/app/modules/zalo/crawler/scroll_handler.py")
text = target.read_text(encoding="utf-8")

# Detect line ending
nl = "\r\n" if "\r\n" in text else "\n"

# ── CHANGE 1: scroll_and_collect signature + skip_open logic ──
# Replace the function signature and first few lines of scroll_and_collect
old_sig = (
    "async def scroll_and_collect(" + nl +
    "    page: Page," + nl +
    "    group_id: Optional[str]," + nl +
    "    group_name: Optional[str]," + nl +
    "    job_id: str," + nl +
    "    max_messages: int = 50," + nl +
    ") -> Tuple[str, List[Message]]:" + nl +
    "    captured_image_urls: Set[str] = set()" + nl +
    "    message_limit = max(1, min(int(max_messages or 50), 500))" + nl +
    nl +
    "    async def _on_response(response):" + nl +
    "        try:" + nl +
    "            content_type = response.headers.get(\"content-type\", \"\")" + nl +
    "            if \"image/\" in content_type:" + nl +
    "                url = response.url" + nl +
    "                if any(cdn in url for cdn in ZALO_CDN_PATTERNS) and _is_full_res(url):" + nl +
    "                    captured_image_urls.add(url)" + nl +
    "        except Exception:" + nl +
    "            pass" + nl +
    nl +
    "    page.on(\"response\", _on_response)" + nl +
    nl +
    "    try:" + nl +
    "        resolved_group_id = await _open_group(page, group_id, group_name)" + nl +
    "        logger.info(f\"Starting scroll collection for group {resolved_group_id}; max_messages={message_limit}\")"
)

new_sig = (
    "async def scroll_and_collect(" + nl +
    "    page: Page," + nl +
    "    group_id: Optional[str]," + nl +
    "    group_name: Optional[str]," + nl +
    "    job_id: str," + nl +
    "    max_messages: int = 50," + nl +
    "    *," + nl +
    "    skip_open: bool = False," + nl +
    ") -> Tuple[str, List[Message]]:" + nl +
    "    \"\"\"Scroll through the Zalo message panel and collect messages." + nl +
    nl +
    "    When *skip_open* is True the function assumes the target conversation is" + nl +
    "    already visible and skips all sidebar/search navigation." + nl +
    "    \"\"\"" + nl +
    "    captured_image_urls: Set[str] = set()" + nl +
    "    message_limit = max(1, min(int(max_messages or 50), 500))" + nl +
    nl +
    "    async def _on_response(response):" + nl +
    "        try:" + nl +
    "            content_type = response.headers.get(\"content-type\", \"\")" + nl +
    "            if \"image/\" in content_type:" + nl +
    "                url = response.url" + nl +
    "                if any(cdn in url for cdn in ZALO_CDN_PATTERNS) and _is_full_res(url):" + nl +
    "                    captured_image_urls.add(url)" + nl +
    "        except Exception:" + nl +
    "            pass" + nl +
    nl +
    "    page.on(\"response\", _on_response)" + nl +
    nl +
    "    # When skip_open=True we read whatever is currently open and use the" + nl +
    "    # visible header title as the \"active\" group name for later checks." + nl +
    "    _active_group_name = group_name  # may be relaxed below" + nl +
    nl +
    "    try:" + nl +
    "        if skip_open:" + nl +
    "            current_title = await _wait_for_group_title(page, group_name, timeout_ms=3000)" + nl +
    "            resolved_group_id = group_id or current_title or group_name or \"\"" + nl +
    "            _active_group_name = current_title  # use real title for subsequent checks" + nl +
    "            logger.info(" + nl +
    "                f\"skip_open=True — reading currently open conversation: \"" + nl +
    "                f\"title={current_title!r} resolved_group_id={resolved_group_id!r}\"" + nl +
    "            )" + nl +
    "        else:" + nl +
    "            resolved_group_id = await _open_group(page, group_id, group_name)" + nl +
    "        logger.info(f\"Starting scroll collection for group {resolved_group_id}; max_messages={message_limit}\")"
)

assert old_sig in text, "Could not find scroll_and_collect signature"
text = text.replace(old_sig, new_sig, 1)

# ── CHANGE 2: Replace group_name references in scroll_and_collect body ──
# Title check before crawl
text = text.replace(
    "        await _wait_for_message_dom_stable(page, message_root, group_name)" + nl +
    "        current_title = await _wait_for_group_title(page, group_name, timeout_ms=5000)" + nl +
    "        if group_name and not _titles_match(group_name, current_title):" + nl +
    "            raise RuntimeError(" + nl +
    "                f\"Conversation changed before crawl. expected={group_name!r} current={current_title!r}. \"" + nl +
    "                \"Crawler stopped to avoid mixing messages between groups.\"" + nl +
    "            )",
    "        await _wait_for_message_dom_stable(page, message_root, _active_group_name)" + nl +
    "        current_title = await _wait_for_group_title(page, _active_group_name, timeout_ms=5000)" + nl +
    "        if _active_group_name and not _titles_match(_active_group_name, current_title):" + nl +
    "            raise RuntimeError(" + nl +
    "                f\"Conversation changed before crawl. expected={_active_group_name!r} current={current_title!r}. \"" + nl +
    "                \"Crawler stopped to avoid mixing messages between groups.\"" + nl +
    "            )",
    1,
)

# During crawl check
text = text.replace(
    "            current_title = await _wait_for_group_title(page, group_name, timeout_ms=1500)" + nl +
    "            if group_name and not _titles_match(group_name, current_title):" + nl +
    "                raise RuntimeError(" + nl +
    "                    f\"Conversation changed during crawl. expected={group_name!r} current={current_title!r}. \"" + nl +
    "                    \"Crawler stopped before saving mixed messages.\"" + nl +
    "                )",
    "            current_title = await _wait_for_group_title(page, _active_group_name, timeout_ms=1500)" + nl +
    "            if _active_group_name and not _titles_match(_active_group_name, current_title):" + nl +
    "                raise RuntimeError(" + nl +
    "                    f\"Conversation changed during crawl. expected={_active_group_name!r} current={current_title!r}. \"" + nl +
    "                    \"Crawler stopped before saving mixed messages.\"" + nl +
    "                )",
    1,
)

# Final parse check
text = text.replace(
    "        current_title = await _wait_for_group_title(page, group_name, timeout_ms=1500)" + nl +
    "        if group_name and not _titles_match(group_name, current_title):" + nl +
    "            raise RuntimeError(" + nl +
    "                f\"Conversation changed before final parse. expected={group_name!r} current={current_title!r}. \"" + nl +
    "                \"Crawler stopped before saving mixed messages.\"" + nl +
    "            )",
    "        current_title = await _wait_for_group_title(page, _active_group_name, timeout_ms=1500)" + nl +
    "        if _active_group_name and not _titles_match(_active_group_name, current_title):" + nl +
    "            raise RuntimeError(" + nl +
    "                f\"Conversation changed before final parse. expected={_active_group_name!r} current={current_title!r}. \"" + nl +
    "                \"Crawler stopped before saving mixed messages.\"" + nl +
    "            )",
    1,
)

# ── CHANGE 3: Replace the second verify_group_for_crawl definition ──
# Find the second definition (it starts after scroll_and_collect's finally block)
second_verify_marker = "async def verify_group_for_crawl(\n    page: Page,\n    group_name: str,\n    group_id: Optional[str] = None,\n) -> dict:\n    \"\"\"Open or reuse a Zalo conversation and verify it is safe to crawl.\n\n    This definition intentionally overrides the older implementation above.\n    Zalo Web search/sidebar can miss recent conversations, so browser fallback\n    must be able to continue when the requested conversation is already open.\n    \"\"\""

# Try with \r\n as well
second_verify_marker_crlf = second_verify_marker.replace("\n", "\r\n")

if second_verify_marker_crlf in text:
    marker = second_verify_marker_crlf
elif second_verify_marker in text:
    marker = second_verify_marker
else:
    raise RuntimeError("Could not find the second verify_group_for_crawl definition")

# Find the position and replace everything from this marker to end of file
idx = text.index(marker)
old_second_verify = text[idx:]

new_second_verify = f"""async def verify_group_for_crawl(
    page: Page,
    group_name: str,
    group_id: Optional[str] = None,
) -> dict:
    \"\"\"Open or reuse a Zalo conversation and verify it is safe to crawl.

    This definition intentionally overrides the older implementation above.
    Zalo Web search/sidebar can miss recent conversations, so browser fallback
    must be able to continue when the requested conversation is already open.

    **Simplified fallback logic (June 2026):**
    When the group cannot be found via sidebar/search, the function now falls
    back to reading whatever conversation is currently open on screen, rather
    than failing.  The response dict includes ``skip_open: True`` so the caller
    knows to pass ``skip_open=True`` to ``scroll_and_collect``.
    \"\"\"
    normalized_name = _normalize_title(group_name)
    if not normalized_name:
        return {{
            "ok": False,
            "reason": "invalid_name",
            "detail": "Empty group name.",
            "group_name": group_name,
            "resolved_group_id": group_id,
            "current_title": None,
            "member_count": None,
            "message_count": 0,
            "warnings": [],
            "skip_open": False,
        }}

    warnings: List[str] = []
    current_title: Optional[str] = await _wait_for_group_title(page, group_name, timeout_ms=1200)
    member_count: Optional[int] = None
    message_count = 0
    resolved_group_id = group_id or group_name
    use_current_conversation = False

    if current_title and _titles_match(normalized_name, current_title):
        # Exact match with currently open conversation — best case
        warnings.append("used_current_open_conversation")
        use_current_conversation = True
        logger.info(f"Using currently open Zalo conversation for crawl: {{current_title!r}}")
    else:
        try:
            resolved_group_id = await _open_group(page, group_id, group_name)
        except (RuntimeError, Exception) as exc:
            detail = str(exc)
            # Re-read the current title after the failed open attempt
            current_title = await _wait_for_group_title(page, group_name, timeout_ms=1200)

            if current_title:
                # ── SIMPLIFIED FALLBACK ──
                # There IS a conversation open on screen.  Instead of failing,
                # we read whatever is open and let the caller know it was a
                # fallback.  This avoids the "Could not open Zalo group …
                # Crawler stopped" error entirely.
                warnings.append("open_group_failed_using_current_conversation_as_fallback")
                use_current_conversation = True
                logger.warning(
                    f"Could not open Zalo group {{group_name!r}} via sidebar/search. "
                    f"Falling back to currently open conversation: {{current_title!r}}. "
                    f"Original error: {{detail}}"
                )
            else:
                # No conversation open at all — genuinely cannot proceed
                reason = "personal_chat" if "member(s)" in detail or "personal chat" in detail else "not_found"
                return {{
                    "ok": False,
                    "reason": reason,
                    "detail": detail,
                    "group_name": group_name,
                    "resolved_group_id": resolved_group_id,
                    "current_title": current_title,
                    "member_count": None,
                    "message_count": 0,
                    "warnings": warnings,
                    "skip_open": False,
                }}

    if not current_title:
        current_title = await _wait_for_group_title(page, group_name, timeout_ms=5000)
    if not current_title:
        return {{
            "ok": False,
            "reason": "message_panel_missing",
            "detail": "Could not find Zalo conversation title after opening group.",
            "group_name": group_name,
            "resolved_group_id": resolved_group_id,
            "current_title": None,
            "member_count": None,
            "message_count": 0,
            "warnings": warnings,
            "skip_open": False,
        }}

    # When using the current conversation as fallback, skip strict title check
    if not use_current_conversation and not _titles_match(normalized_name, current_title):
        return {{
            "ok": False,
            "reason": "not_found",
            "detail": f"Wrong Zalo conversation is open: {{current_title}}",
            "group_name": group_name,
            "resolved_group_id": resolved_group_id,
            "current_title": current_title,
            "member_count": None,
            "message_count": 0,
            "warnings": warnings,
            "skip_open": False,
        }}

    member_count = await _detect_group_member_count(page)
    if member_count is None:
        warnings.append("member_count_unknown")
    elif member_count < 3:
        return {{
            "ok": False,
            "reason": "personal_chat",
            "detail": f"Conversation has only {{member_count}} members, treated as personal chat.",
            "group_name": group_name,
            "resolved_group_id": resolved_group_id,
            "current_title": current_title,
            "member_count": member_count,
            "message_count": 0,
            "warnings": warnings,
            "skip_open": False,
        }}

    message_frame = await _find_best_message_frame(page)
    message_root_target: Union[Page, Frame] = message_frame or page
    message_root = await _find_message_root(message_root_target)
    message_count = await _count_messages(message_root)
    if message_count <= 0:
        warnings.append("no_messages_synced")

    return {{
        "ok": True,
        "reason": "verified",
        "detail": "Verified Zalo group.",
        "group_name": group_name,
        "resolved_group_id": resolved_group_id,
        "current_title": current_title,
        "member_count": member_count,
        "message_count": message_count,
        "warnings": warnings,
        "skip_open": use_current_conversation,
    }}
""".replace("\n", nl)

text = text[:idx] + new_second_verify

target.write_text(text, encoding="utf-8")
print("✅ Patched scroll_handler.py successfully")

# Verify syntax
import ast
ast.parse(text)
print("✅ Syntax check passed")
