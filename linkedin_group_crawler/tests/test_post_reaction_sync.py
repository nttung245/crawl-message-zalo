from __future__ import annotations

from app.modules.linkedin.services.post_reaction_sync_service import (
    apply_reaction_to_sheet_rows,
    build_reaction_action_record,
    build_reaction_cell_value,
    emails_match,
    export_sheet_row_for_n8n,
    linkedin_activity_id_from_url,
    merge_trigger_row_into_reaction_rows,
    pick_row_number_from_post_record,
    posts_match_same_linkedin_post,
    read_reaction_token,
    row_has_reaction,
    should_skip_playwright_for_clear_reaction,
    should_skip_playwright_for_existing_reaction,
)


def test_linkedin_activity_id_from_url() -> None:
    url = "https://www.linkedin.com/feed/update/urn:li:activity:1234567890/"
    assert linkedin_activity_id_from_url(url) == "1234567890"


def test_linkedin_activity_id_from_url_encoded_path() -> None:
    url = "https://www.linkedin.com/feed/update/urn%3Ali%3Aactivity%3A1234567890/"
    assert linkedin_activity_id_from_url(url) == "1234567890"


def test_posts_match_same_linkedin_post_by_activity() -> None:
    a = "https://www.linkedin.com/feed/update/urn:li:activity:42/"
    b = "https://www.linkedin.com/feed/update/urn:li:activity:42?commentUrn=urn%3Ali%3Acomment%3A1"
    assert posts_match_same_linkedin_post(a, b) is True
    other = "https://www.linkedin.com/feed/update/urn:li:activity:43/"
    assert posts_match_same_linkedin_post(a, other) is False


def test_posts_match_encoded_activity_path_equals_plain() -> None:
    plain = "https://www.linkedin.com/feed/update/urn:li:activity:42/"
    encoded = "https://www.linkedin.com/feed/update/urn%3Ali%3Aactivity%3A42/"
    assert posts_match_same_linkedin_post(plain, encoded) is True


def test_emails_match_case_insensitive() -> None:
    assert emails_match("User@Mail.com", "user@mail.com") is True
    assert emails_match("a@b.com", "c@b.com") is False


def test_export_sheet_row_for_n8n_adds_vietnamese_slug_aliases() -> None:
    reaction_cell = build_reaction_cell_value(
        "like",
        triggered_at="2026-05-11T06:35:12.456Z",
    )
    exported = export_sheet_row_for_n8n(
        {
            "Tên nhóm": "Product Leaders VN",
            "URL_Bài_Viết": "https://www.linkedin.com/feed/update/urn:li:activity:1/",
            "Số like": 118,
            "Số comment": 17,
            "Lượng báo sao": 2,
            "Điểm": 84,
            "Email_crawl": "user@mail.com",
            "row_number": 5,
        },
        reaction=reaction_cell,
        post_url="https://www.linkedin.com/feed/update/urn:li:activity:1/",
        apply_like_bump=True,
        row_number_fallback=5,
    )
    assert exported["tennhom"] == "Product Leaders VN"
    assert exported["urlbaiviet"] == "https://www.linkedin.com/feed/update/urn:li:activity:1/"
    assert exported["reaction"]["type"] == "like"
    assert exported["reaction"]["day_trigger"] == "2026-05-11"
    assert exported["solike"] == 119
    assert exported["linkedin_like_count"] == 119
    assert exported["socomment"] == 17
    assert exported["luongbaosao"] == 2
    assert exported["linkedin_report_count"] == 2
    assert exported["Số báo cáo"] == 2
    assert exported["diem"] == 84


def test_apply_reaction_to_sheet_rows_updates_only_matching_email_and_url() -> None:
    post_url = "https://www.linkedin.com/feed/update/urn:li:activity:99/"
    posts = [
        {
            "Email_crawl": "user@mail.com",
            "ID_session_crawl": "sess_a",
            "row_number": 3,
            "URL_Bài_Viết": post_url,
            "Nội dung": "A",
        },
        {
            "Email_crawl": "user@mail.com",
            "ID_session_crawl": "sess_b",
            "row_number": 7,
            "post_url": post_url,
            "Nội dung": "B",
        },
        {
            "Email_crawl": "other@mail.com",
            "ID_session_crawl": "sess_c",
            "row_number": 1,
            "post_url": post_url,
            "Nội dung": "C",
        },
        {
            "Email_crawl": "user@mail.com",
            "ID_session_crawl": "sess_d",
            "row_number": 2,
            "post_url": "https://www.linkedin.com/feed/update/urn:li:activity:1/",
            "Nội dung": "D",
        },
    ]
    action = build_reaction_action_record(
        owner_email="user@mail.com",
        post_url=post_url,
        reaction="celebrate",
        id_session_crawl="sess_a",
        row_number=3,
        sheet_row=None,
    )
    updated, matched = apply_reaction_to_sheet_rows(
        posts,
        action=action,
        final_url=post_url,
        resolved_playwright_session_id="sid-1",
        playwright_executed=True,
        triggered_at="2026-05-11T06:35:12.456Z",
    )
    assert matched == 2
    assert len(updated) == 2
    assert updated[0]["reaction"]["type"] == "celebrate"
    assert updated[1]["reaction"]["type"] == "celebrate"


def test_merge_trigger_row_into_reaction_rows_appends_missing_trigger() -> None:
    post_url = "https://www.linkedin.com/feed/update/urn:li:activity:77/"
    reaction_cell = build_reaction_cell_value(
        "like",
        triggered_at="2026-05-11T06:35:12.456Z",
    )
    rows = [
        {
            "Email_crawl": "user@mail.com",
            "ID_session_crawl": "sess_a",
            "row_number": 5,
            "URL_Bài_Viết": post_url,
        },
    ]
    action = build_reaction_action_record(
        owner_email="user@mail.com",
        post_url=post_url,
        reaction="like",
        id_session_crawl="sess_new",
        row_number=2,
        sheet_row={
            "Email_crawl": "user@mail.com",
            "ID_session_crawl": "sess_new",
            "row_number": 2,
            "URL_Bài_Viết": post_url,
        },
    )
    merged, matched = merge_trigger_row_into_reaction_rows(
        rows,
        action=action,
        final_url=post_url,
        resolved_playwright_session_id="sid",
        reaction_cell=reaction_cell,
        playwright_executed=True,
    )
    assert matched == 2
    assert len(merged) == 2
    assert merged[1]["ID_session_crawl"] == "sess_new"
    assert merged[1]["reaction"]["type"] == "like"


def test_should_skip_playwright_when_any_row_has_reaction() -> None:
    rows = [
        {"reaction": None},
        {"reaction": {"type": "like", "triggered_at": "2026-05-11T06:35:12.456Z"}},
    ]
    assert should_skip_playwright_for_existing_reaction(rows) is True
    assert should_skip_playwright_for_existing_reaction([{"reaction": ""}]) is False
    assert (
        should_skip_playwright_for_existing_reaction(
            [{"reaction": {"type": "love", "triggered_at": "2026-05-11T06:35:12.456Z"}}],
            reaction_kind="like",
        )
        is False
    )
    assert should_skip_playwright_for_clear_reaction([{"reaction": ""}]) is True
    assert (
        should_skip_playwright_for_clear_reaction(
            [{"reaction": {"type": "love", "triggered_at": "2026-05-11T06:35:12.456Z"}}],
        )
        is False
    )


def test_apply_reaction_to_sheet_rows_clears_matching_rows_with_empty_string() -> None:
    post_url = "https://www.linkedin.com/feed/update/urn:li:activity:88/"
    posts = [
        {
            "Email_crawl": "user@mail.com",
            "ID_session_crawl": "sess_a",
            "row_number": 3,
            "URL_Bài_Viết": post_url,
            "reaction": {"type": "love", "triggered_at": "2026-05-11T06:35:12.456Z"},
        },
        {
            "Email_crawl": "user@mail.com",
            "ID_session_crawl": "sess_b",
            "row_number": 7,
            "post_url": post_url,
            "reaction": "love",
        },
    ]
    action = build_reaction_action_record(
        owner_email="user@mail.com",
        post_url=post_url,
        reaction="love",
        id_session_crawl="sess_a",
        row_number=3,
        sheet_row=None,
        clear_reaction=True,
    )
    updated, matched = apply_reaction_to_sheet_rows(
        posts,
        action=action,
        final_url=post_url,
        resolved_playwright_session_id="sid-1",
        playwright_executed=True,
        triggered_at="2026-05-11T06:35:12.456Z",
    )
    assert matched == 2
    assert updated[0]["reaction"] == ""
    assert updated[0]["Reaction"] == ""
    assert updated[1]["reaction"] == ""


def test_read_reaction_token_and_row_number() -> None:
    assert read_reaction_token({"reaction": "love"}) == "love"
    assert (
        read_reaction_token(
            {"reaction": {"type": "celebrate", "triggered_at": "2026-05-11T06:35:12.456Z"}},
        )
        == "celebrate"
    )
    assert row_has_reaction({"Reaction": "null"}) is False
    assert pick_row_number_from_post_record({"STT": "4"}, fallback=1) == 4
    assert pick_row_number_from_post_record({}, fallback=9) == 9
