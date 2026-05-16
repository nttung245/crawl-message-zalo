"""Tests cho parse ``data`` webhook slug sheet."""

from __future__ import annotations

from app.services.profile_slug_sheet_service import (
    find_owner_row,
    normalize_sheet_data_rows,
)


def test_normalize_json_string_array() -> None:
    raw = '[{"email":"a@b.com","profile_slug":"ab"}]'
    rows = normalize_sheet_data_rows(raw)
    assert len(rows) == 1
    assert rows[0].get("email") == "a@b.com"


def test_normalize_wrapper_dict() -> None:
    rows = normalize_sheet_data_rows({"data": [{"Email_crawl": "x@y.com"}]})
    assert len(rows) == 1


def test_find_owner_case_insensitive() -> None:
    rows = [{"Email_crawl": "User@Test.COM"}]
    ok, matched = find_owner_row(rows, "user@test.com")
    assert ok and matched == rows[0]
