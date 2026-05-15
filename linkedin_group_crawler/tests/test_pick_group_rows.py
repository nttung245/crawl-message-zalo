"""Kiểm tra trích mảng nhóm từ JSON n8n (route helper)."""

from __future__ import annotations

from app.api.routes import _normalize_n8n_groups, _pick_group_rows


def test_pick_group_rows_plain_list() -> None:
    rows = _pick_group_rows([{"url_group": "https://x", "row_number": 2}])
    assert len(rows) == 1
    assert rows[0]["row_number"] == 2


def test_pick_group_rows_data_envelope() -> None:
    rows = _pick_group_rows({"success": True, "data": [{"url_group": "https://x", "row_number": 1}]})
    assert len(rows) == 1


def test_pick_group_rows_groups_key() -> None:
    rows = _pick_group_rows({"groups": [{"url_group": "https://g", "row_number": 5}]})
    assert len(rows) == 1
    assert rows[0]["row_number"] == 5


def test_normalize_keeps_row_number_from_groups_envelope() -> None:
    parsed = {"groups": [{"URL_Nhóm": "https://linkedin.com/groups/1", "row_number": 3}]}
    got = _normalize_n8n_groups(parsed)
    assert len(got) == 1
    assert got[0]["row_number"] == 3
