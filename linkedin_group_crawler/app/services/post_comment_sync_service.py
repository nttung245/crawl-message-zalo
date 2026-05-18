"""Đồng bộ comment: get-all → sửa mọi dòng khớp url+email → POST mảng ghi đè Sheet (webhook reaction)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import json
from typing import Any

from app.services.n8n_post_filter_service import email_crawl_from_post
from app.services.post_reaction_sync_service import (
    _non_empty_str,
    _row_sheet_identity,
    emails_match,
    export_sheet_row_for_n8n,
    fetch_posts_for_email_via_n8n,
    pick_row_number_from_post_record,
    post_record_post_url,
    posts_match_same_linkedin_post,
    send_sheet_rows_overwrite_webhook,
)
from app.utils.webhook_payload_keys import (
    bump_comment_metrics_after_app_comment,
    decrement_comment_metrics_after_delete_comment,
)

COMMENT_CONTENT_FIELD = "comment_content"
COMMENT_DAY_FIELD = "ngày comment"

_COMMENT_STATE_KEYS_EXACT: tuple[str, ...] = (
    "comment",
    "Comment",
    "comment_sheet",
    "Comment_sheet",
    "app_comments",
    "linkedin_app_comments",
    "app_comments_json",
    "comments_app",
)


@dataclass(frozen=True)
class CommentActionRecord:
    """Dữ liệu comment từ app (url, email, mảng comment đã merge)."""

    owner_email: str
    post_url: str
    id_session_crawl: str
    row_number: int
    sheet_row: dict[str, Any] | None
    comments_cell: list[dict[str, str]]


def _comment_content_from_entry(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    for key in (COMMENT_CONTENT_FIELD, "comment", "commentContent"):
        value = _non_empty_str(raw.get(key))
        if value:
            return value
    return ""


def _comment_day_from_entry(raw: Any) -> str:
    if not isinstance(raw, dict):
        return ""
    for key in (COMMENT_DAY_FIELD, "ngay_comment", "day_comment", "dayComment"):
        value = _non_empty_str(raw.get(key))
        if value:
            return value[:10]
    return ""


def normalize_comment_entry(raw: Any) -> dict[str, str] | None:
    content = _comment_content_from_entry(raw)
    day = _comment_day_from_entry(raw)
    if not content or not day:
        return None
    return {COMMENT_CONTENT_FIELD: content, COMMENT_DAY_FIELD: day}


def parse_comments_from_record(record: dict[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for key in _COMMENT_STATE_KEYS_EXACT:
        if key not in record:
            continue
        raw = record.get(key)
        if isinstance(raw, list):
            for item in raw:
                normalized = normalize_comment_entry(item)
                if normalized:
                    entries.append(normalized)
            if entries:
                return entries
        if isinstance(raw, str) and raw.strip():
            try:
                parsed = json.loads(raw)
            except Exception:
                continue
            if isinstance(parsed, list):
                for item in parsed:
                    normalized = normalize_comment_entry(item)
                    if normalized:
                        entries.append(normalized)
                if entries:
                    return entries
    return entries


def build_comment_cell_entry(*, comment_content: str, comment_day: str) -> dict[str, str]:
    return {
        COMMENT_CONTENT_FIELD: comment_content.strip(),
        COMMENT_DAY_FIELD: comment_day.strip()[:10],
    }


def merge_comment_entries(
    existing: list[dict[str, Any]],
    *,
    comment_content: str,
    comment_day: str | None = None,
) -> list[dict[str, str]]:
    day = (comment_day or date.today().isoformat()).strip()[:10]
    merged: list[dict[str, str]] = []
    for raw in existing:
        normalized = normalize_comment_entry(raw)
        if normalized:
            merged.append(normalized)
    merged.append(build_comment_cell_entry(comment_content=comment_content, comment_day=day))
    return merged


def update_comment_entry(
    existing: list[dict[str, Any]],
    *,
    old_comment_text: str,
    new_comment_text: str,
) -> list[dict[str, str]]:
    """Tìm entry có nội dung cũ và thay thế bằng nội dung mới."""
    target = old_comment_text.strip().lower()
    merged: list[dict[str, str]] = []
    for raw in existing:
        normalized = normalize_comment_entry(raw)
        if not normalized:
            continue
        content = normalized.get(COMMENT_CONTENT_FIELD, "").strip().lower()
        if content == target:
            # Cập nhật nội dung mới, giữ nguyên ngày
            normalized[COMMENT_CONTENT_FIELD] = new_comment_text.strip()
        merged.append(normalized)
    return merged


def filter_comment_entries(
    existing: list[dict[str, Any]],
    *,
    comment_text_to_remove: str,
) -> list[dict[str, str]]:
    """Loại bỏ các entry có nội dung trùng khớp với comment_text_to_remove."""
    target = comment_text_to_remove.strip().lower()
    merged: list[dict[str, str]] = []
    for raw in existing:
        normalized = normalize_comment_entry(raw)
        if not normalized:
            continue
        content = normalized.get(COMMENT_CONTENT_FIELD, "").strip().lower()
        if content == target:
            continue
        merged.append(normalized)
    return merged


def build_comment_action_record(
    *,
    owner_email: str,
    post_url: str,
    id_session_crawl: str,
    row_number: int,
    sheet_row: dict[str, Any] | None,
    comments_cell: list[dict[str, str]],
) -> CommentActionRecord:
    return CommentActionRecord(
        owner_email=_non_empty_str(owner_email),
        post_url=_non_empty_str(post_url),
        id_session_crawl=_non_empty_str(id_session_crawl),
        row_number=max(1, int(row_number)),
        sheet_row=dict(sheet_row) if isinstance(sheet_row, dict) else None,
        comments_cell=list(comments_cell),
    )


def _patch_row_with_comments(
    row: dict[str, Any],
    *,
    action: CommentActionRecord,
    final_url: str,
    resolved_playwright_session_id: str,
    comments_cell: list[dict[str, str]],
) -> dict[str, Any]:
    out = dict(row)
    out["comment"] = comments_cell
    out["Comment"] = comments_cell
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


def apply_comments_to_sheet_rows(
    posts: list[dict[str, Any]],
    *,
    action: CommentActionRecord,
    final_url: str,
    resolved_playwright_session_id: str,
    playwright_executed: bool,
) -> tuple[list[dict[str, Any]], int]:
    target_url = action.post_url
    owner = action.owner_email
    if not target_url or not owner:
        return [], 0

    updated: list[dict[str, Any]] = []
    matched_count = 0
    comments_cell = list(action.comments_cell)

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
        patched = _patch_row_with_comments(
            record,
            action=action,
            final_url=final_url,
            resolved_playwright_session_id=resolved_playwright_session_id,
            comments_cell=comments_cell,
        )
        exported = export_sheet_row_for_n8n(
            patched,
            comments=comments_cell,
            post_url=action.post_url,
            final_url=final_url,
            resolved_playwright_session_id=resolved_playwright_session_id,
            row_number_fallback=action.row_number,
            owner_email_webhook_key="email_crawl",
        )
        if playwright_executed:
            if comments_cell:  # Thêm comment → +1
                bump_comment_metrics_after_app_comment(exported)
            else:  # Xóa comment → -1
                decrement_comment_metrics_after_delete_comment(exported)
        updated.append(exported)

    return merge_trigger_row_into_comment_rows(
        updated,
        action=action,
        final_url=final_url,
        resolved_playwright_session_id=resolved_playwright_session_id,
        comments_cell=comments_cell,
        playwright_executed=playwright_executed,
    )


def merge_trigger_row_into_comment_rows(
    rows: list[dict[str, Any]],
    *,
    action: CommentActionRecord,
    final_url: str,
    resolved_playwright_session_id: str,
    comments_cell: list[dict[str, str]],
    playwright_executed: bool,
) -> tuple[list[dict[str, Any]], int]:
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
            patched = _patch_row_with_comments(
                action.sheet_row,
                action=action,
                final_url=final_url,
                resolved_playwright_session_id=resolved_playwright_session_id,
                comments_cell=comments_cell,
            )
            exported = export_sheet_row_for_n8n(
                patched,
                comments=comments_cell,
                post_url=action.post_url,
                final_url=final_url,
                resolved_playwright_session_id=resolved_playwright_session_id,
                row_number_fallback=action.row_number,
                owner_email_webhook_key="email_crawl",
            )
            if playwright_executed:
                if comments_cell:  # Thêm comment → +1
                    bump_comment_metrics_after_app_comment(exported)
                else:  # Xóa comment → -1
                    decrement_comment_metrics_after_delete_comment(exported)
            rows = [*rows, exported]
            matched_count += 1

    return rows, matched_count


__all__ = [
    "COMMENT_CONTENT_FIELD",
    "COMMENT_DAY_FIELD",
    "CommentActionRecord",
    "apply_comments_to_sheet_rows",
    "build_comment_action_record",
    "build_comment_cell_entry",
    "fetch_posts_for_email_via_n8n",
    "filter_comment_entries",
    "merge_comment_entries",
    "parse_comments_from_record",
    "send_sheet_rows_overwrite_webhook",
    "update_comment_entry",
]
