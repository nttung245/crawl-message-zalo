from __future__ import annotations

from app.utils.webhook_payload_keys import (
    bump_like_metrics_after_like_reaction,
    enrich_webhook_sheet_metrics,
    merge_sheet_row_into_webhook_body,
    sync_webhook_body_row_number_aliases,
    vietnamese_slug_key,
)


def test_vietnamese_slug_tennhom() -> None:
    assert vietnamese_slug_key("Tên nhóm") == "tennhom"


def test_vietnamese_slug_url_post() -> None:
    assert vietnamese_slug_key("URL_Bài_Viết") == "urlbaiviet"


def test_vietnamese_slug_diem() -> None:
    assert vietnamese_slug_key("Điểm") == "diem"


def test_enrich_metrics_from_vietnamese_columns() -> None:
    body: dict[str, object] = {}
    merge_sheet_row_into_webhook_body(
        body,
        {"Số like": 42, "Số comment": "10", "Số báo cáo": 2, "Điểm": 3.5},
    )
    enrich_webhook_sheet_metrics(body)
    assert body["linkedin_like_count"] == 42
    assert body["linkedin_comment_count"] == 10
    assert body["linkedin_report_count"] == 2
    assert body["post_score"] == 3
    assert body["linkedin_post_score"] == 3


def test_bump_like_after_like_reaction() -> None:
    body: dict[str, object] = {}
    merge_sheet_row_into_webhook_body(body, {"Số like": 9})
    enrich_webhook_sheet_metrics(body)
    bump_like_metrics_after_like_reaction(body)
    assert body["linkedin_like_count"] == 10
    assert body["Số like"] == 10
    assert body["solike"] == 10


def test_bump_like_when_missing_defaults_to_one() -> None:
    body: dict[str, object] = {}
    enrich_webhook_sheet_metrics(body)
    bump_like_metrics_after_like_reaction(body)
    assert body["linkedin_like_count"] == 1
    assert body["Số like"] == 1


def test_enrich_session_posts_total_slug_and_canonical() -> None:
    body: dict[str, object] = {}
    merge_sheet_row_into_webhook_body(
        body,
        {"posts_count": 9, "Tổng số bài lấy được mỗi lần cào": 9},
    )
    enrich_webhook_sheet_metrics(body)
    assert body["tongsobailayduocmoilancao"] == 9
    assert body["session_posts_count"] == 9
    assert body["total_posts_per_scrape"] == 9


def test_enrich_reports_slug_sobaocao() -> None:
    body: dict[str, object] = {}
    merge_sheet_row_into_webhook_body(body, {"Số báo cáo": "5"})
    enrich_webhook_sheet_metrics(body)
    assert body["sobaocao"] == 5
    assert body["linkedin_report_count"] == 5


def test_enrich_reports_from_luong_bao_sao() -> None:
    body: dict[str, object] = {}
    merge_sheet_row_into_webhook_body(body, {"Lượng báo sao": 3, "reposts": 3})
    enrich_webhook_sheet_metrics(body)
    assert body["luongbaosao"] == 3
    assert body["linkedin_report_count"] == 3
    assert body["Số báo cáo"] == 3
    assert body["sobaocao"] == 3
    assert body["reposts"] == 3


def test_sync_row_number_aliases_overwrites_sheet_row_stale_values() -> None:
    body: dict[str, object] = {}
    merge_sheet_row_into_webhook_body(
        body,
        {"row_number": 1, "STT": 1, "rowNumber": 1},
    )
    sync_webhook_body_row_number_aliases(body, 8)
    assert body["row_number"] == 8
    assert body["rownumber"] == 8
    assert body["rowNumber"] == 8
    assert body["STT"] == 8
    assert body["stt"] == 8


def test_merge_adds_slug_alias() -> None:
    body: dict[str, object] = {}
    merge_sheet_row_into_webhook_body(
        body,
        {
            "Tên nhóm": "X",
            "row_number": 2,
            "Email_crawl": "a@b.c",
        },
    )
    assert body["Tên nhóm"] == "X"
    assert body["tennhom"] == "X"
    assert body["row_number"] == 2
    assert "emailcrawl" not in body
