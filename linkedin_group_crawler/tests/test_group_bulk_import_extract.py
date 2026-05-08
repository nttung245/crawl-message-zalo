"""Unit tests for LinkedIn group bulk-import HTML helpers."""

from __future__ import annotations

from app.schemas.request_models import AddListGroupRequest
from app.services.group_bulk_import_service import extract_member_count_from_html, normalize_group_url


def _sample_group_url() -> str:
    return "https://www.linkedin.com/groups/12345/"


def test_add_list_group_post_to_webhook_null_means_send() -> None:
    body = {"group_urls": [_sample_group_url()], "post_to_webhook": None}
    req = AddListGroupRequest.model_validate(body)
    assert req.post_to_webhook is True


def test_add_list_group_post_to_webhook_omitted_means_send() -> None:
    req = AddListGroupRequest(group_urls=[_sample_group_url()])
    assert req.post_to_webhook is True


def test_extract_member_count_json() -> None:
    html = 'foo "memberCount":19994 bar'
    assert extract_member_count_from_html(html) == 19994


def test_extract_member_count_group_member_count() -> None:
    html = '{"groupMemberCount": 42}'
    assert extract_member_count_from_html(html) == 42


def test_normalize_group_url_adds_https() -> None:
    u = normalize_group_url("www.linkedin.com/groups/123/")
    assert u.startswith("https://")
    assert "linkedin.com/groups/123/" in u


def test_extract_member_count_none() -> None:
    assert extract_member_count_from_html("<html></html>") is None
