"""Chuẩn hoá giá trị trước khi POST JSON tới n8n — không làm mất field, chỉ ép kiểu an toàn."""

from __future__ import annotations

import math
from datetime import date, datetime, timezone
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID


def sanitize_webhook_payload(obj: Any) -> Any:
    """Đệ quy: datetime/date → ISO string; Decimal → float; NaN float → None; dict/list giữ cấu trúc."""

    if obj is None:
        return None
    if isinstance(obj, bool):
        return obj
    if isinstance(obj, str):
        return obj
    if isinstance(obj, int):
        return obj
    if isinstance(obj, float):
        return obj if math.isfinite(obj) else None
    if isinstance(obj, datetime):
        dt = obj if obj.tzinfo else obj.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, UUID):
        return str(obj)
    if isinstance(obj, bytes):
        return obj.decode("utf-8", errors="replace")
    if isinstance(obj, Enum):
        return obj.value
    if isinstance(obj, dict):
        out: dict[str, Any] = {}
        for k, v in obj.items():
            sk = k if isinstance(k, str) else str(k)
            out[sk] = sanitize_webhook_payload(v)
        return out
    if isinstance(obj, (list, tuple, set)):
        return [sanitize_webhook_payload(x) for x in obj]
    return str(obj)
