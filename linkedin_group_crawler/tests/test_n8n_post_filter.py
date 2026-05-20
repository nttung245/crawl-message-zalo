"""Unit tests for n8n post extraction và lọc ngày."""

from datetime import date

from app.modules.linkedin.services.n8n_post_filter_service import (
    build_crawl_sessions_from_posts,
    filter_posts_by_inclusive_date_range,
    flatten_crawl_sessions_posts,
    normalize_n8n_posts,
    parse_post_record_date,
    pick_top_post_per_group,
    posts_from_n8n_payload,
)


def test_posts_from_nested_posts() -> None:
    body = {"posts": [{"Ngày": "2026-05-01", "author": "a"}, {"Ngày": "2026-05-02"}]}
    got = posts_from_n8n_payload(body)
    assert len(got) == 2


def test_posts_from_n8n_success_envelope() -> None:
    body = {
        "success": True,
        "message": "Get posts successfully",
        "total": 2,
        "data": [{"Ngày": "2026-05-06", "ID_session_crawl": "x_1"}, {"Ngày": "2026-05-06"}],
    }
    got = normalize_n8n_posts(posts_from_n8n_payload(body))
    assert len(got) == 2
    assert got[0].get("id_session_crawl") == "x_1"


def test_posts_from_envelope_without_rows_is_empty() -> None:
    body = {"success": True, "message": "ok", "total": 0}
    assert posts_from_n8n_payload(body) == []


def test_filter_range_inclusive() -> None:
    posts = [
        {"Ngày": "2026-05-01"},
        {"Ngày": "2026-05-05"},
        {"Ngày": "2026-05-10"},
    ]
    out, meta = filter_posts_by_inclusive_date_range(
        posts,
        date(2026, 5, 5),
        date(2026, 5, 10),
    )
    assert len(out) == 2
    assert meta["total_output"] == 2


def test_parse_post_record_date_iso_prefix() -> None:
    d = parse_post_record_date({"posted_at": "2026-05-06T10:00:00"})
    assert d == date(2026, 5, 6)


def test_build_crawl_sessions_groups_by_session_id() -> None:
    posts = [
        {
            "id_session_crawl": "user_111",
            "Tên nhóm": "G1",
            "URL_Nhóm": "https://linkedin.com/groups/1",
            "Ngày": "2026-05-02",
            "Điểm": 5,
        },
        {
            "id_session_crawl": "user_222",
            "Tên nhóm": "G2",
            "URL_Nhóm": "https://linkedin.com/groups/2",
            "Ngày": "2026-05-06",
            "Điểm": 1,
        },
        {
            "id_session_crawl": "user_111",
            "Ngày": "2026-05-01",
            "Điểm": 1,
        },
    ]
    sessions = build_crawl_sessions_from_posts(posts)
    assert len(sessions) == 2
    assert sessions[0]["id_session_crawl"] == "user_222"
    assert sessions[0]["posts_count"] == 1
    assert sessions[1]["id_session_crawl"] == "user_111"
    assert sessions[1]["posts_count"] == 2
    assert sessions[1]["group_name"] == "G1"


def test_pick_top_post_per_group_keeps_highest_score() -> None:
    posts = [
        {
            "URL_Nhóm": "https://linkedin.com/groups/1",
            "Điểm": 3,
            "row_number": 1,
        },
        {
            "URL_Nhóm": "https://linkedin.com/groups/1",
            "Điểm": 10,
            "row_number": 2,
        },
        {
            "URL_Nhóm": "https://linkedin.com/groups/2",
            "Số like": 7,
            "Điểm": 7,
        },
    ]
    got = pick_top_post_per_group(posts)
    assert len(got) == 2
    assert got[0]["row_number"] == 2
    assert got[1]["Số like"] == 7


def test_flatten_crawl_sessions_matches_session_order() -> None:
    posts = [
        {
            "id_session_crawl": "a",
            "Ngày": "2026-05-01",
            "URL_Nhóm": "https://g-a1",
            "Điểm": 1,
        },
        {
            "id_session_crawl": "b",
            "Ngày": "2026-05-10",
            "URL_Nhóm": "https://g-b",
            "Điểm": 1,
        },
        {
            "id_session_crawl": "a",
            "Ngày": "2026-05-02",
            "URL_Nhóm": "https://g-a2",
            "Điểm": 2,
        },
    ]
    sessions = build_crawl_sessions_from_posts(posts)
    flat = flatten_crawl_sessions_posts(sessions)
    assert [p["id_session_crawl"] for p in flat] == ["b", "a", "a"]
    assert [p["URL_Nhóm"] for p in flat] == ["https://g-b", "https://g-a1", "https://g-a2"]
