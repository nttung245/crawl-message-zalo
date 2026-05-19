"""Tests for LinkedIn guest/login URL detection."""

from app.schemas.request_models import resolve_playwright_session_email
from app.services.auth_service import _is_authwall_url, _is_linkedin_authenticated_app_url


def test_authwall_detects_login_paths() -> None:
    assert _is_authwall_url("https://www.linkedin.com/login")
    assert _is_authwall_url("https://www.linkedin.com/checkpoint/challenge/123")
    assert _is_authwall_url("https://www.linkedin.com/authwall")


def test_authwall_detects_guest_homepage() -> None:
    assert _is_authwall_url("https://www.linkedin.com/")
    assert _is_authwall_url("https://www.linkedin.com")
    assert _is_authwall_url("https://www.linkedin.com/home")
    assert _is_authwall_url("https://www.linkedin.com/welcome")


def test_authwall_does_not_flag_feed_or_posts() -> None:
    assert not _is_authwall_url("https://www.linkedin.com/feed/")
    assert not _is_authwall_url("https://www.linkedin.com/posts/user_activity-123")


def test_authenticated_app_urls() -> None:
    assert _is_linkedin_authenticated_app_url("https://www.linkedin.com/feed/")
    assert _is_linkedin_authenticated_app_url("https://www.linkedin.com/in/someone/")
    assert _is_linkedin_authenticated_app_url("https://www.linkedin.com/posts/foo")
    assert not _is_linkedin_authenticated_app_url("https://www.linkedin.com/")


def test_resolve_playwright_email_prefers_email_crawl() -> None:
    assert (
        resolve_playwright_session_email(
            email_crawl="crawl@gmail.com",
            email="other@gmail.com",
        )
        == "crawl@gmail.com"
    )
    assert (
        resolve_playwright_session_email(
            email_crawl="not-an-email",
            email="fallback@gmail.com",
        )
        == "fallback@gmail.com"
    )
