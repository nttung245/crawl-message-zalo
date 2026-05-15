from __future__ import annotations

from app.services.post_comment_sync_service import (
    COMMENT_CONTENT_FIELD,
    COMMENT_DAY_FIELD,
    apply_comments_to_sheet_rows,
    build_comment_action_record,
    build_comment_cell_entry,
    merge_comment_entries,
    normalize_comment_entry,
)


def test_normalize_comment_entry_supports_legacy_and_new_keys() -> None:
    assert normalize_comment_entry(
        {"comment": "Hi", "day_comment": "2026-05-11"},
    ) == {
        COMMENT_CONTENT_FIELD: "Hi",
        COMMENT_DAY_FIELD: "2026-05-11",
    }
    assert normalize_comment_entry(
        {"comment_content": "Xin chào", "ngày comment": "2026-05-12"},
    ) == {
        COMMENT_CONTENT_FIELD: "Xin chào",
        COMMENT_DAY_FIELD: "2026-05-12",
    }


def test_merge_comment_entries_appends_new_item() -> None:
    merged = merge_comment_entries(
        [{"comment_content": "A", "ngày comment": "2026-05-10"}],
        comment_content="B",
        comment_day="2026-05-11",
    )
    assert len(merged) == 2
    assert merged[1] == build_comment_cell_entry(
        comment_content="B",
        comment_day="2026-05-11",
    )


def test_apply_comments_to_sheet_rows_updates_matching_email_and_url() -> None:
    post_url = "https://www.linkedin.com/feed/update/urn:li:activity:55/"
    comments = [
        build_comment_cell_entry(comment_content="A", comment_day="2026-05-10"),
        build_comment_cell_entry(comment_content="B", comment_day="2026-05-11"),
    ]
    posts = [
        {
            "Email_crawl": "user@mail.com",
            "ID_session_crawl": "sess_a",
            "row_number": 2,
            "URL_Bài_Viết": post_url,
            "comment": [{"comment": "Old", "day_comment": "2026-05-09"}],
        },
        {
            "Email_crawl": "user@mail.com",
            "ID_session_crawl": "sess_b",
            "row_number": 8,
            "post_url": post_url,
        },
        {
            "Email_crawl": "other@mail.com",
            "row_number": 1,
            "post_url": post_url,
        },
    ]
    action = build_comment_action_record(
        owner_email="user@mail.com",
        post_url=post_url,
        id_session_crawl="sess_a",
        row_number=2,
        sheet_row=None,
        comments_cell=comments,
    )
    updated, matched = apply_comments_to_sheet_rows(
        posts,
        action=action,
        final_url=post_url,
        resolved_playwright_session_id="sid-1",
        playwright_executed=True,
    )
    assert matched == 2
    assert len(updated) == 2
    assert updated[0]["comment"] == comments
    assert updated[0]["Comment"] == comments
    assert updated[0]["socomment"] == 1
    assert updated[0]["linkedin_comment_count"] == 1
    assert updated[0]["email_crawl"] == "user@mail.com"
    assert "Email_crawl" not in updated[0]
