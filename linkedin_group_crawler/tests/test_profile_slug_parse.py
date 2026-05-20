"""Unit tests for profile slug parsing."""

from __future__ import annotations

import pytest

from app.modules.linkedin.services.profile_slug_service import parse_profile_slug_from_href


def test_parse_relative_href() -> None:
    slug, url = parse_profile_slug_from_href("/in/nmhoang-dev/")
    assert slug == "nmhoang-dev"
    assert url == "https://www.linkedin.com/in/nmhoang-dev/"


def test_parse_absolute_href_with_query() -> None:
    slug, url = parse_profile_slug_from_href("https://www.linkedin.com/in/some-user?trk=nav")
    assert slug == "some-user"
    assert url == "https://www.linkedin.com/in/some-user/"


def test_parse_invalid_raises() -> None:
    with pytest.raises(ValueError):
        parse_profile_slug_from_href("/company/acme/")
