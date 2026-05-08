"""Tests for profile comments URL parsing."""

from __future__ import annotations

from app.services.profile_comments_service import parse_comment_activity_href


def test_parse_group_post_comment_href() -> None:
    href = (
        "https://www.linkedin.com/feed/update/urn:li:groupPost:8586225-7416783543630016512/"
        "?dashCommentUrn=urn%3Ali%3Afsd_comment%3A%287458445761945579520%2Curn%3Ali%3AgroupPost%3A8586225-7416783543630016512%29"
    )
    got = parse_comment_activity_href(href)
    assert got is not None
    assert got["type"] == "groupPost"
    assert got["group_id"] == "8586225"
    assert got["post_id"] == "7416783543630016512"
    assert got["comment_id"] == "7458445761945579520"


def test_parse_activity_comment_href() -> None:
    href = (
        "https://www.linkedin.com/feed/update/urn:li:activity:1234567890/"
        "?dashCommentUrn=urn%3Ali%3Afsd_comment%3A%289999%2Curn%3Ali%3Aactivity%3A1234567890%29"
    )
    got = parse_comment_activity_href(href)
    assert got is not None
    assert got["type"] == "activity"
    assert got["post_id"] == "1234567890"
    assert got["comment_id"] == "9999"


def test_parse_missing_dash_returns_none() -> None:
    assert parse_comment_activity_href("https://www.linkedin.com/in/x/") is None
