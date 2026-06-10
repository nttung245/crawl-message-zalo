"""Đánh giá phản hồi webhook sau reaction — hỗ trợ ``{{ success: true }}`` hoặc ``\"true\"``, kể cả lồng trong ``body`` / ``data``."""

from __future__ import annotations

from typing import Any, Dict, Optional, Tuple
import json


def truthy_success_value(raw: Any) -> bool:
    """True nếu ``success`` coi là thành công (boolean / chuỗi ``true`` / ``1`` / …)."""

    if raw is True:
        return True
    if raw is False or raw is None:
        return False
    if isinstance(raw, (int, float)):
        return bool(raw) and raw == 1
    if isinstance(raw, str):
        t = raw.strip().lower()
        if t in ("false", "0", "no", "", "null"):
            return False
        return t in ("true", "1", "yes", "ok")
    return False


def _dict_with_success_key(parsed: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if "success" in parsed:
        return parsed
    for inner_key in ("body", "data", "response"):
        inner = parsed.get(inner_key)
        if isinstance(inner, dict) and "success" in inner:
            return inner
    return None


def evaluate_post_reaction_webhook_response(http_status: int, response_text: str) -> Tuple[bool, str]:
    """HTTP ≥ 400 → lỗi. Body JSON có ``success`` (root hoặc ``body``/``data``) → bắt buộc truthy."""

    if http_status >= 400:
        return False, f"Webhook trả HTTP {http_status}."

    text = (response_text or "").strip()
    if not text:
        return True, ""

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return True, ""

    if not isinstance(parsed, dict):
        return True, ""

    target = _dict_with_success_key(parsed)
    if target is None:
        return True, ""

    if truthy_success_value(target.get("success")):
        return True, ""

    return False, (
        "Webhook trả JSON nhưng ``success`` không xác nhận thành công "
        f"(giá trị: {target.get('success')!r}). "
        'Trả về ví dụ: {\"success\": true} hoặc {\"success\": \"true\"}, '
        "hoặc bọc trong {\"body\": { … }} (chuẩn n8n)."
    )
