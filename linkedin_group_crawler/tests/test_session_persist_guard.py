"""Session file guard — không ghi đè khi thiếu li_at."""

import time

from app.services.auth_service import _has_li_at_cookie, _li_at_cookie_is_valid


def test_has_li_at_requires_name_and_value() -> None:
    assert _has_li_at_cookie(
        {"cookies": [{"name": "li_at", "value": "abc", "domain": ".linkedin.com"}]},
    )
    assert not _has_li_at_cookie({"cookies": [{"name": "li_at", "value": ""}]})
    assert not _has_li_at_cookie({"cookies": [{"name": "JSESSIONID", "value": "x"}]})
    assert not _has_li_at_cookie({})


def test_li_at_expired() -> None:
    expired = {"name": "li_at", "value": "x", "expires": time.time() - 3600}
    assert not _li_at_cookie_is_valid(expired)
    valid = {"name": "li_at", "value": "x", "expires": time.time() + 3600}
    assert _li_at_cookie_is_valid(valid)
