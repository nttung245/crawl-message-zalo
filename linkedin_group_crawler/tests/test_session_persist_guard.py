"""Session file guard — không ghi đè khi thiếu li_at."""

from app.services.auth_service import _has_li_at_cookie


def test_has_li_at_requires_name_and_value() -> None:
    assert _has_li_at_cookie(
        {"cookies": [{"name": "li_at", "value": "abc", "domain": ".linkedin.com"}]},
    )
    assert not _has_li_at_cookie({"cookies": [{"name": "li_at", "value": ""}]})
    assert not _has_li_at_cookie({"cookies": [{"name": "JSESSIONID", "value": "x"}]})
    assert not _has_li_at_cookie({})
