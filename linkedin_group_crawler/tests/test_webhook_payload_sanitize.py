from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal

from app.utils.webhook_payload_sanitize import sanitize_webhook_payload


def test_sanitize_nested_datetime() -> None:
    dt = datetime(2026, 5, 10, 14, 30, tzinfo=timezone.utc)
    got = sanitize_webhook_payload({"Ngày": dt, "nested": {"at": dt}})
    assert isinstance(got["Ngày"], str)
    assert "2026-05-10" in got["Ngày"]
    assert isinstance(got["nested"]["at"], str)


def test_sanitize_date_not_truncating_datetime_branch() -> None:
    d = date(2026, 3, 1)
    got = sanitize_webhook_payload({"d": d})
    assert got["d"] == "2026-03-01"


def test_sanitize_decimal_and_nan() -> None:
    assert sanitize_webhook_payload(Decimal("1.5")) == 1.5
    assert sanitize_webhook_payload(float("nan")) is None


def test_sanitize_preserves_all_keys() -> None:
    row = {
        "Ngày": "2026-05-01",
        "Đăng vào": "2026-05-01T10:00:00",
        "Nội dung": "x",
        "Số comment": 3,
        "extra": {"a": 1},
    }
    got = sanitize_webhook_payload(row)
    assert set(got.keys()) == set(row.keys())
