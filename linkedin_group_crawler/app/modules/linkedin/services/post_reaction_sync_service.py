"""Đồng bộ reaction: get-all → sửa mọi dòng khớp url+email → POST một mảng ghi đè Sheet."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Any, Literal
from urllib.parse import unquote, urlparse

import httpx

from app.core.config import settings
from app.modules.linkedin.services.n8n_post_filter_service import (
    email_crawl_from_post,
    normalize_n8n_posts,
    posts_from_n8n_payload,
    session_id_from_post,
)
from app.shared.services.n8n_webhook_service import post_json_to_n8n_webhook, _post_with_retry
from app.core.logger import get_logger
from app.modules.linkedin.utils.post_reaction_webhook_ack import evaluate_post_reaction_webhook_response
from app.modules.linkedin.utils.webhook_payload_keys import (
    bump_like_metrics_after_like_reaction,
    decrement_like_metrics_after_clear_reaction,
    enrich_webhook_sheet_metrics,
    merge_sheet_row_into_webhook_body,
    sync_webhook_body_row_number_aliases,
    vietnamese_slug_key,
)
from app.modules.linkedin.utils.webhook_payload_sanitize import sanitize_webhook_payload


logger = get_logger(__name__)

_POST_URL_KEYS_EXACT: tuple[str, ...] = (
    "URL_Bài_Viết",
    "URL_Bai_Viet",
    "url_bai_viet",
    "post_url",
    "postUrl",
    "urlbaiviet",
)

_REACTION_STATE_KEYS_EXACT: tuple[str, ...] = (
    "reaction",
    "Reaction",
    "reaction_type",
    "Reaction_type",
    "loại_tương_tác",
    "Loại tương tác",
    "tuong_tac",
    "Tuong_tac",
)

_ROW_NUMBER_KEYS_EXACT: tuple[str, ...] = (
    "row_number",
    "rowNumber",
    "STT",
    "stt",
    "Stt",
)

_REACTION_EMPTY_TOKENS: frozenset[str] = frozenset(
    {
        "",
        "null",
        "undefined",
        "false",
        "0",
        "no",
        "không",
        "khong",
    },
)


@dataclass(frozen=True)
class ReactionActionRecord:
    """Bước 1 — dữ liệu reaction từ app (url, email, loại reaction, meta phiên)."""

    owner_email: str
    post_url: str
    reaction: str
    id_session_crawl: str
    row_number: int
    sheet_row: dict[str, Any] | None
    clear_reaction: bool = False


def _non_empty_str(raw: Any) -> str:
    if raw is None:
        return ""
    return str(raw).strip()


def linkedin_activity_id_from_url(url: str) -> str:
    """Trích id activity từ URL/URN LinkedIn (nếu có)."""

    text = unquote((url or "").strip())
    if not text:
        return ""
    match = re.search(r"urn:li:activity:(\d+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    match = re.search(r"/feed/update/urn:li:activity:(\d+)", text, flags=re.IGNORECASE)
    if match:
        return match.group(1)
    return ""


def _normalize_linkedin_url_for_compare(url: str) -> str:
    text = (url or "").strip()
    if not text:
        return ""
    parsed = urlparse(text)
    path = (parsed.path or "").rstrip("/").lower()
    query = f"?{parsed.query}" if parsed.query else ""
    return f"{parsed.netloc.lower()}{path}{query}"


def posts_match_same_linkedin_post(left: str, right: str) -> bool:
    """So khớp bài theo activity id; fallback so sánh URL chuẩn hoá."""

    left_id = linkedin_activity_id_from_url(left)
    right_id = linkedin_activity_id_from_url(right)
    if left_id and right_id and left_id == right_id:
        return True
    left_norm = _normalize_linkedin_url_for_compare(left)
    right_norm = _normalize_linkedin_url_for_compare(right)
    return bool(left_norm and right_norm and left_norm == right_norm)


def post_record_post_url(record: dict[str, Any]) -> str:
    for key in _POST_URL_KEYS_EXACT:
        val = _non_empty_str(record.get(key))
        if val:
            return val
    for key, raw in record.items():
        lk = str(key).lower().replace(" ", "").replace("_", "")
        if "url" in lk and ("bai" in lk or "post" in lk):
            val = _non_empty_str(raw)
            if val:
                return val
    return ""


def emails_match(left: str, right: str) -> bool:
    return _non_empty_str(left).lower() == _non_empty_str(right).lower()


def build_reaction_cell_value(reaction_kind: str, *, triggered_at: str) -> dict[str, str]:
    """Ô ``reaction`` trên sheet: loại reaction + thời điểm trigger."""

    kind = _non_empty_str(reaction_kind)
    ts = _non_empty_str(triggered_at)
    day = ts[:10] if len(ts) >= 10 else ts
    return {
        "type": kind,
        "triggered_at": ts,
        "day_trigger": day,
    }


def _reaction_type_from_cell(raw: Any) -> str | None:
    if isinstance(raw, dict):
        for key in ("type", "kind", "reaction", "reaction_type"):
            token = _non_empty_str(raw.get(key)).lower()
            if token and token not in _REACTION_EMPTY_TOKENS:
                return token
        return None
    token = _non_empty_str(raw).lower()
    if token in _REACTION_EMPTY_TOKENS:
        return None
    return token or None


def read_reaction_token(record: dict[str, Any]) -> str | None:
    for key in _REACTION_STATE_KEYS_EXACT:
        if key not in record:
            continue
        raw = record.get(key)
        if raw is None:
            continue
        token = _reaction_type_from_cell(raw)
        if token:
            return token
    return None


def row_has_reaction(record: dict[str, Any]) -> bool:
    return read_reaction_token(record) is not None


def pick_row_number_from_post_record(record: dict[str, Any], *, fallback: int) -> int:
    for key in _ROW_NUMBER_KEYS_EXACT:
        if key not in record:
            continue
        raw = record.get(key)
        if raw is None:
            continue
        try:
            if isinstance(raw, (int, float)):
                n = int(raw)
            else:
                n = int(str(raw).strip())
        except (TypeError, ValueError):
            continue
        if n >= 1:
            return n
    return max(1, int(fallback))


def build_reaction_action_record(
    *,
    owner_email: str,
    post_url: str,
    reaction: str,
    id_session_crawl: str,
    row_number: int,
    sheet_row: dict[str, Any] | None,
    clear_reaction: bool = False,
) -> ReactionActionRecord:
    return ReactionActionRecord(
        owner_email=_non_empty_str(owner_email),
        post_url=_non_empty_str(post_url),
        reaction=_non_empty_str(reaction),
        id_session_crawl=_non_empty_str(id_session_crawl),
        row_number=max(1, int(row_number)),
        sheet_row=dict(sheet_row) if isinstance(sheet_row, dict) else None,
        clear_reaction=bool(clear_reaction),
    )


def should_skip_playwright_for_existing_reaction(
    rows: list[dict[str, Any]],
    *,
    reaction_kind: str | None = None,
) -> bool:
    """Tránh toggle trên LinkedIn khi sheet đã ghi đúng loại reaction cần thêm."""

    requested = _non_empty_str(reaction_kind).lower()
    for row in rows:
        token = read_reaction_token(row)
        if not token:
            continue
        if requested and token != requested:
            continue
        return True
    return False


def should_skip_playwright_for_clear_reaction(rows: list[dict[str, Any]]) -> bool:
    """Bỏ qua Playwright khi sheet chưa ghi reaction để gỡ."""

    return not any(row_has_reaction(row) for row in rows)


def fetch_posts_for_email_via_n8n(email: str) -> list[dict[str, Any]]:
    """Bước 3 — gọi webhook get-all-posts (n8n) và trả toàn bộ dòng phẳng."""

    owner = _non_empty_str(email)
    if not owner:
        return []

    url = (settings.n8n_webhook_get_all_posts_url or "").strip()
    if not url:
        logger.warning("post reaction sync: N8N_WEBHOOK_GET_ALL_POSTS chưa cấu hình")
        return []

    timeout = max(1.0, float(settings.n8n_webhook_timeout_sec))
    try:
        response = _post_with_retry(url=url, json_body={"email": owner}, timeout=timeout)
    except httpx.RequestError as exc:
        logger.warning("post reaction sync: get-all-posts network error: %s", type(exc).__name__)
        return []

    if response.status_code >= 400:
        logger.warning(
            "post reaction sync: get-all-posts HTTP %s (body length=%s)",
            response.status_code,
            len(response.text or ""),
        )
        return []

    try:
        result_data = response.json()
    except Exception as exc:
        logger.warning("post reaction sync: cannot parse get-all-posts JSON: %s", exc)
        return []

    posts_raw = normalize_n8n_posts(posts_from_n8n_payload(result_data))
    return [dict(p) for p in posts_raw if isinstance(p, dict)]


def _row_sheet_identity(row: dict[str, Any], *, fallback_url: str) -> tuple[str, int, str]:
    sid = session_id_from_post(row) or _non_empty_str(row.get("ID_session_crawl"))
    row_number = pick_row_number_from_post_record(row, fallback=1)
    row_url = post_record_post_url(row) or fallback_url
    activity = linkedin_activity_id_from_url(row_url) or row_url
    return (sid, row_number, activity)


def export_sheet_row_for_n8n(
    row: dict[str, Any],
    *,
    reaction: dict[str, Any] | str | None = None,
    comments: list[dict[str, Any]] | None = None,
    post_url: str | None = None,
    final_url: str | None = None,
    resolved_playwright_session_id: str | None = None,
    apply_like_bump: bool = False,
    row_number_fallback: int = 1,
    owner_email_webhook_key: Literal["Email_crawl", "email_crawl"] = "Email_crawl",
) -> dict[str, Any]:
    """Parse một dòng sheet giống webhook reaction cũ: slug tiếng Việt + metric chuẩn."""

    body: dict[str, Any] = {}
    merge_sheet_row_into_webhook_body(body, row)
    enrich_webhook_sheet_metrics(body)

    owner_email = email_crawl_from_post(row) or _non_empty_str(row.get("Email_crawl"))
    if owner_email:
        if owner_email_webhook_key == "email_crawl":
            body["email_crawl"] = owner_email
            body.pop("Email_crawl", None)
        else:
            body["Email_crawl"] = owner_email

    sid = session_id_from_post(row) or _non_empty_str(row.get("ID_session_crawl"))
    if sid:
        body["ID_session_crawl"] = sid

    row_number = pick_row_number_from_post_record(row, fallback=row_number_fallback)
    sync_webhook_body_row_number_aliases(body, row_number)

    reaction_kind: str | None = None
    if reaction is not None:
        body["reaction"] = reaction
        body["Reaction"] = reaction
        reaction_kind = _reaction_type_from_cell(reaction)
    if comments is not None:
        body["comment"] = comments
        body["Comment"] = comments
    if post_url:
        body["post_url"] = post_url
        body["URL_Bài_Viết"] = post_url
        slug = vietnamese_slug_key("URL_Bài_Viết")
        if slug:
            body[slug] = post_url
    if final_url:
        body["final_url"] = final_url
    if resolved_playwright_session_id:
        body["resolved_playwright_session_id"] = resolved_playwright_session_id

    if apply_like_bump and reaction_kind == "like":
        bump_like_metrics_after_like_reaction(body)

    sanitized = sanitize_webhook_payload(body)
    return sanitized if isinstance(sanitized, dict) else {}


def _patch_row_with_reaction(
    row: dict[str, Any],
    *,
    action: ReactionActionRecord,
    final_url: str,
    resolved_playwright_session_id: str,
    reaction_cell: dict[str, str] | str,
) -> dict[str, Any]:
    out = dict(row)

    out["reaction"] = reaction_cell
    out["Reaction"] = reaction_cell
    out["post_url"] = action.post_url
    out["URL_Bài_Viết"] = action.post_url
    out["final_url"] = final_url
    out["resolved_playwright_session_id"] = resolved_playwright_session_id
    out["Email_crawl"] = action.owner_email
    out["ID_session_crawl"] = _non_empty_str(
        out.get("ID_session_crawl") or out.get("id_session_crawl") or action.id_session_crawl,
    )

    row_number = pick_row_number_from_post_record(out, fallback=action.row_number)
    out["row_number"] = row_number
    out["rownumber"] = row_number
    out["rowNumber"] = row_number
    out["STT"] = row_number
    out["stt"] = row_number

    return out


def apply_reaction_to_sheet_rows(
    posts: list[dict[str, Any]],
    *,
    action: ReactionActionRecord,
    final_url: str,
    resolved_playwright_session_id: str,
    playwright_executed: bool,
    triggered_at: str,
) -> tuple[list[dict[str, Any]], int]:
    """Bước 3 — từ get-all chỉ giữ và parse các dòng trùng url bài + email crawl."""

    target_url = action.post_url
    owner = action.owner_email
    if not target_url or not owner:
        return [], 0

    updated: list[dict[str, Any]] = []
    matched_count = 0
    if action.clear_reaction:
        reaction_cell: dict[str, str] | str = ""
    else:
        reaction_cell = build_reaction_cell_value(action.reaction, triggered_at=triggered_at)

    for record in posts:
        if not isinstance(record, dict):
            continue
        row_email = email_crawl_from_post(record) or _non_empty_str(record.get("Email_crawl"))
        row_url = post_record_post_url(record)
        matches = (
            row_email
            and emails_match(row_email, owner)
            and row_url
            and posts_match_same_linkedin_post(row_url, target_url)
        )
        if not matches:
            continue

        matched_count += 1
        patched = _patch_row_with_reaction(
            record,
            action=action,
            final_url=final_url,
            resolved_playwright_session_id=resolved_playwright_session_id,
            reaction_cell=reaction_cell,
        )
        apply_like_bump = (
            not action.clear_reaction
            and playwright_executed
            and action.reaction  # Bất kỳ reaction nào cũng coi là 1 "tương tác" (like)
            and not row_has_reaction(record)
        )
        exported = export_sheet_row_for_n8n(
            patched,
            reaction=reaction_cell,
            post_url=action.post_url,
            final_url=final_url,
            resolved_playwright_session_id=resolved_playwright_session_id,
            apply_like_bump=apply_like_bump,
            row_number_fallback=action.row_number,
        )
        # Trừ 1 like nếu gỡ reaction và Playwright đã thực thi
        if action.clear_reaction and playwright_executed and row_has_reaction(record):
            decrement_like_metrics_after_clear_reaction(exported)
        updated.append(exported)

    return merge_trigger_row_into_reaction_rows(
        updated,
        action=action,
        final_url=final_url,
        resolved_playwright_session_id=resolved_playwright_session_id,
        reaction_cell=reaction_cell,
        playwright_executed=playwright_executed,
    )


def merge_trigger_row_into_reaction_rows(
    rows: list[dict[str, Any]],
    *,
    action: ReactionActionRecord,
    final_url: str,
    resolved_playwright_session_id: str,
    reaction_cell: dict[str, str] | str,
    playwright_executed: bool,
) -> tuple[list[dict[str, Any]], int]:
    """Gộp dòng trigger từ app vào ``rows`` nếu chưa có trong danh sách khớp."""

    identities = {
        _row_sheet_identity(row, fallback_url=action.post_url)
        for row in rows
    }
    matched_count = len(rows)

    if action.sheet_row:
        trigger_identity = _row_sheet_identity(
            action.sheet_row,
            fallback_url=action.post_url,
        )
        if trigger_identity not in identities:
            patched = _patch_row_with_reaction(
                action.sheet_row,
                action=action,
                final_url=final_url,
                resolved_playwright_session_id=resolved_playwright_session_id,
                reaction_cell=reaction_cell,
            )
            apply_like_bump = (
                not action.clear_reaction
                and playwright_executed
                and action.reaction  # Bất kỳ reaction nào cũng coi là 1 "tương tác" (like)
                and not row_has_reaction(action.sheet_row)
            )
            exported = export_sheet_row_for_n8n(
                patched,
                reaction=reaction_cell,
                post_url=action.post_url,
                final_url=final_url,
                resolved_playwright_session_id=resolved_playwright_session_id,
                apply_like_bump=apply_like_bump,
                row_number_fallback=action.row_number,
            )
            # Trừ 1 like nếu gỡ reaction và Playwright đã thực thi
            if action.clear_reaction and playwright_executed and row_has_reaction(action.sheet_row):
                decrement_like_metrics_after_clear_reaction(exported)
            rows = [*rows, exported]
            matched_count += 1

    return rows, matched_count


def send_sheet_rows_overwrite_webhook(
    *,
    webhook_url: str,
    rows: list[dict[str, Any]],
    matched_row_count: int,
) -> tuple[int, int, int | None, str | None]:
    """POST **chỉ** mảng ``rows`` (JSON array) để n8n ghi đè Sheet."""

    payload = sanitize_webhook_payload(rows)
    if not isinstance(payload, list):
        payload = []
    try:
        http_status, full_text = post_json_to_n8n_webhook(url=webhook_url, json_body=payload)
    except Exception as exc:
        logger.warning("post reaction overwrite webhook failed: %s", exc)
        return matched_row_count, 0, None, str(exc)[:512]

    preview = (full_text or "").strip()
    if len(preview) > 512:
        preview = f"{preview[:512]}…"
    webhook_ok, _ = evaluate_post_reaction_webhook_response(http_status, full_text or "")
    success_count = matched_row_count if webhook_ok else 0
    return matched_row_count, success_count, http_status, preview
