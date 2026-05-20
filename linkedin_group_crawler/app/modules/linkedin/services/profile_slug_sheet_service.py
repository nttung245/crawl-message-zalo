"""Webhook n8n: đọc danh sách profile slug trên Sheet và (tuỳ chọn) đăng ký slug mới."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import httpx

from app.core.config import settings
from app.shared.services.n8n_webhook_service import _post_with_retry
from app.modules.linkedin.services.profile_slug_service import parse_profile_slug_from_href
from app.core.logger import get_logger


logger = get_logger(__name__)

_EMAIL_KEYS = ("email", "Email_crawl", "email_crawl", "userEmail")


def normalize_email_for_match(value: str | None) -> str:
    return (value or "").strip().lower()


def sheet_webhook_body_email(email: str) -> dict[str, str]:
    e = email.strip()
    return {"email": e, "Email_crawl": e, "userEmail": e}


def normalize_sheet_data_rows(data_field: Any) -> list[dict[str, Any]]:
    """Chuẩn hoá ``data`` từ webhook (mảng object, JSON string, hoặc wrapper dict)."""

    if data_field is None:
        return []

    if isinstance(data_field, str):
        text = data_field.strip()
        if not text:
            return []
        try:
            data_field = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("Không parse JSON được từ data string webhook profile slug sheet.")
            return []

    if isinstance(data_field, dict):
        for key in ("rows", "items", "data", "records", "groups"):
            inner = data_field.get(key)
            if isinstance(inner, list):
                return [x for x in inner if isinstance(x, dict)]
        return [data_field]

    if isinstance(data_field, list):
        return [x for x in data_field if isinstance(x, dict)]

    return []


def row_matches_owner_email(row: dict[str, Any], target_normalized: str) -> bool:
    if not target_normalized:
        return False
    for key in _EMAIL_KEYS:
        val = row.get(key)
        if isinstance(val, str) and normalize_email_for_match(val) == target_normalized:
            return True
    return False


def extract_profile_slug_hint(row: dict[str, Any] | None) -> str | None:
    """Lấy slug gợi ý từ một dòng sheet (cột slug hoặc URL chứa ``/in/<slug>``)."""

    if not row:
        return None
    for key in ("profile_slug", "public_id", "slug", "linkedin_slug", "profileSlug"):
        val = row.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    for key in (
        "profile_url",
        "profileUrl",
        "linkedin_url",
        "LinkedIn_URL",
        "URL_profile",
        "url_profile",
        "url",
    ):
        val = row.get(key)
        if not isinstance(val, str):
            continue
        v = val.strip()
        if "/in/" not in v.lower():
            continue
        try:
            slug, _ = parse_profile_slug_from_href(v)
            return slug
        except ValueError:
            continue
    return None


def should_skip_playwright_slug_fetch(
    rows: list[dict[str, Any]],
    owner_email: str,
) -> tuple[bool, dict[str, Any] | None]:
    """Chỉ bỏ qua cào slug khi **đã có email trong sheet và đã có slug/URL**."""

    found, matched = find_owner_row(rows, owner_email)
    if not found or matched is None:
        return False, None
    if extract_profile_slug_hint(matched):
        return True, matched
    return False, matched


def find_owner_row(rows: list[dict[str, Any]], owner_email: str) -> tuple[bool, dict[str, Any] | None]:
    """True + row đầu tiên khớp email."""

    target = normalize_email_for_match(owner_email)
    if not target:
        return False, None
    for row in rows:
        if row_matches_owner_email(row, target):
            return True, row
    return False, None


def _truncate_preview(raw: str, limit: int = 512) -> str:
    text = (raw or "").strip()
    if len(text) > limit:
        return f"{text[:limit]}…"
    return text


def fetch_sheet_rows_via_webhook(
    *,
    webhook_url: str,
    email: str,
    timeout_sec: float,
) -> tuple[int, list[dict[str, Any]], Any, str]:
    """POST webhook lấy slug sheet → (http_status, rows, parsed_body_or_None, preview)."""

    url = (webhook_url or "").strip()
    if not url:
        raise RuntimeError("N8N_WEBHOOK_GET_PROFILE_SLUGS chưa được cấu hình trong .env.")

    timeout = max(5.0, float(timeout_sec))
    payload = sheet_webhook_body_email(email)

    resp = _post_with_retry(url=url, json_body=payload, timeout=timeout)

    preview = _truncate_preview(resp.text or "")
    parsed: Any = None
    try:
        parsed = resp.json()
    except Exception:
        parsed = None

    rows: list[dict[str, Any]] = []
    total: int | None = None
    if isinstance(parsed, dict):
        total_raw = parsed.get("total")
        try:
            total = int(total_raw) if total_raw is not None else None
        except (TypeError, ValueError):
            total = None
        rows = normalize_sheet_data_rows(parsed.get("data"))
        if total is not None and total >= 0:
            pass
    elif isinstance(parsed, list):
        rows = normalize_sheet_data_rows(parsed)

    return resp.status_code, rows, parsed, preview


def register_profile_slug_via_webhook(
    *,
    webhook_url: str,
    email: str,
    profile_slug: str,
    profile_url: str,
    timeout_sec: float,
) -> tuple[int, Any, str]:
    """POST webhook để ghi slug mới lên sheet / workflow."""

    url = (webhook_url or "").strip()
    if not url:
        raise RuntimeError("N8N_WEBHOOK_ADD_PROFILE_SLUG chưa được cấu hình trong .env.")

    timeout = max(5.0, float(timeout_sec))
    body = {
        **sheet_webhook_body_email(email),
        "profile_slug": profile_slug,
        "profile_url": profile_url,
        "public_id": profile_slug,
    }

    resp = _post_with_retry(url=url, json_body=body, timeout=timeout)

    preview = _truncate_preview(resp.text or "")
    parsed: Any = None
    try:
        parsed = resp.json()
    except Exception:
        parsed = None

    return resp.status_code, parsed, preview


@dataclass(frozen=True)
class SheetCheckOutcome:
    http_status: int
    email_found_in_sheet: bool
    matched_row: dict[str, Any] | None
    rows: list[dict[str, Any]]
    response_preview: str
    parsed: Any


def check_email_in_profile_slug_sheet(owner_email: str) -> SheetCheckOutcome:
    """Gọi webhook GET_PROFILE_SLUGS và kiểm tra email đã có trong ``data`` chưa."""

    url = (settings.n8n_webhook_get_profile_slugs_url or "").strip()
    status_code, rows, parsed, preview = fetch_sheet_rows_via_webhook(
        webhook_url=url,
        email=owner_email.strip(),
        timeout_sec=float(settings.n8n_webhook_get_profile_slugs_timeout_sec),
    )
    found, matched = find_owner_row(rows, owner_email)
    return SheetCheckOutcome(
        http_status=status_code,
        email_found_in_sheet=found,
        matched_row=matched,
        rows=rows,
        response_preview=preview,
        parsed=parsed,
    )
