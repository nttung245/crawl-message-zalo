"""So khớp URL bài khi xóa comment."""

from __future__ import annotations

from app.services.post_comment_delete_service import (
    _comment_text_pattern,
    _dom_comment_matches_sheet,
    _first_words_for_timeline_match,
    _urls_same_post,
)
from app.services.profile_comments_service import parse_comment_activity_href


def test_urls_same_post_group_post_and_deeplink() -> None:
    sheet = (
        "https://www.linkedin.com/feed/update/urn:li:groupPost:8586225-7416783543630016512/"
    )
    deeplink = (
        "https://www.linkedin.com/feed/update/urn:li:groupPost:8586225-7416783543630016512/"
        "?dashCommentUrn=urn%3Ali%3Afsd_comment%3A%287458445761945579520"
        "%2Curn%3Ali%3AgroupPost%3A8586225-7416783543630016512%29"
    )
    assert _urls_same_post(sheet, deeplink) is True


def test_urls_same_post_activity_plain_and_encoded_path() -> None:
    plain = "https://www.linkedin.com/feed/update/urn:li:activity:4242/"
    enc = (
        "https://www.linkedin.com/feed/update/urn%3Ali%3Aactivity%3A4242/"
        "?dashCommentUrn=x"
    )
    assert _urls_same_post(plain, enc) is True


def test_urls_same_post_ugc_share_article_urn() -> None:
    sheet = "https://www.linkedin.com/feed/update/urn:li:ugcPost:7123456789/"
    deeplink = (
        "https://www.linkedin.com/feed/update/urn:li:ugcPost:7123456789/"
        "?dashCommentUrn=urn%3Ali%3Afsd_comment%3A%281%2Curn%3Ali%3AugcPost%3A7123456789%29"
    )
    assert _urls_same_post(sheet, deeplink) is True

    share = "https://www.linkedin.com/feed/update/urn:li:share:1234567890/"
    assert _urls_same_post(share, share) is True

    article = "https://www.linkedin.com/feed/update/urn:li:article:9876543210/"
    assert _urls_same_post(article, article) is True


def test_dom_comment_matches_whitespace_sheet() -> None:
    text = """Good   job
    
there"""
    import re

    raw = "good job there"
    pat = re.compile(re.escape(raw), re.I)
    assert _dom_comment_matches_sheet(text, pat, raw) is True


def test_dom_comment_matches_timeline_ellipsis() -> None:
    import re

    sheet = "good job there everyone"
    pat = _comment_text_pattern(sheet)
    assert _dom_comment_matches_sheet("Good job …", pat, sheet) is True


def test_timeline_comment_pattern_uses_first_five_words() -> None:
    full = "one two three four five six seven"
    assert _first_words_for_timeline_match(full) == "one two three four five"
    pat = _comment_text_pattern(full)
    assert pat.search("ONE two THREE four FIVE and more") is not None
    assert pat.search("six seven only") is None


def test_dom_comment_matches_zero_width_and_prefix() -> None:
    import re

    sheet = "hello world from me"
    pat = re.compile(re.escape(sheet), re.I)
    dom = "hello\u200b world from"  # ZWSP
    assert _dom_comment_matches_sheet(dom, pat, sheet) is True


def test_dom_comment_matches_short_exact_blob() -> None:
    from app.services.post_comment_delete_service import _comment_text_in_blob_relaxed

    assert _comment_text_in_blob_relaxed("good job", "good job") is True


def test_owner_label_matches_bullet_you() -> None:
    from app.services.post_comment_delete_service import _OWNER_LABEL_RE

    assert _OWNER_LABEL_RE.search(" • You") is not None
    assert _OWNER_LABEL_RE.search("Minh Hoàng Nguyễn • You") is not None


def test_parse_keeps_group_deeplink_for_flow() -> None:
    """Parse sample từ test_profile_comments_parse — đảm bảo vẫn hợp lệ."""

    href = (
        "https://www.linkedin.com/feed/update/urn:li:groupPost:8586225-7416783543630016512/"
        "?dashCommentUrn=urn%3Ali%3Afsd_comment%3A%287458445761945579520%2Curn%"
        "3Ali%3AgroupPost%3A8586225-7416783543630016512%29"
    )
    got = parse_comment_activity_href(href)
    assert got is not None
    assert got["type"] == "groupPost"
