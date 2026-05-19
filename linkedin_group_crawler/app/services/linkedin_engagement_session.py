"""Tự động đảm bảo session LinkedIn trước react/comment (login/prime)."""

from __future__ import annotations

import json
from pathlib import Path

from app.config import settings
from app.services.auth_service import (
    _existing_state_is_reusable,
    build_session_state_path,
    login_and_save_session,
)
from app.utils.logger import get_logger

logger = get_logger(__name__)


def resolve_password_for_email(email: str, explicit_password: str | None = None) -> str:
    """Password từ request body, rồi map env ``LINKEDIN_ENGAGEMENT_PASSWORDS_JSON``."""

    if explicit_password and explicit_password.strip():
        return explicit_password.strip()

    key = (email or "").strip().lower()
    if not key:
        return ""

    mapped = settings.linkedin_engagement_passwords.get(key)
    if mapped:
        return mapped

    default_pw = (settings.linkedin_default_engagement_password or "").strip()
    return default_pw


def ensure_linkedin_session_for_engagement(
    *,
    email: str | None,
    session_id: str | None = None,
    password: str | None = None,
    force_relogin: bool = False,
) -> tuple[str, Path]:
    """Trước Playwright react/comment: login lại nếu cần, luôn prime feed (nhanh nếu session còn hợp lệ).

    - File session **hợp lệ** + có password: ``login(force_relogin=False)`` → reuse + prime (~vài giây).
    - File session **hợp lệ** + không password: chỉ ``prime`` pool.
    - File **hỏng** + có password: ``login(force_relogin=True)``.
    - File **hỏng** + không password: ``RuntimeError`` hướng dẫn đăng nhập UI / env.
    """

    if not (email or "").strip() and not (session_id or "").strip():
        raise ValueError("Cần email hoặc session_id để resolve session LinkedIn.")

    login_email = (email or "").strip()

    normalized_session_id, state_path = build_session_state_path(
        session_id=session_id,
        email=login_email if "@" in login_email else None,
    )

    if not settings.linkedin_auto_login_before_engagement:
        if not state_path.is_file() or not _existing_state_is_reusable(state_path) or force_relogin:
            raise RuntimeError(
                f"Session {state_path.name} không hợp lệ và auto login đang tắt "
                "(LINKEDIN_AUTO_LOGIN_BEFORE_ENGAGEMENT=false).",
            )
        return normalized_session_id, state_path

    pw_email = login_email if "@" in login_email else ""
    resolved_password = resolve_password_for_email(pw_email, password)

    reusable = state_path.is_file() and _existing_state_is_reusable(state_path) and not force_relogin

    if reusable and not resolved_password:
        logger.info(
            "Engagement session: reusable session found (%s, li_at OK), but no password provided for auto-login if it fails later.",
            state_path.name,
        )
        return normalized_session_id, state_path

    if not resolved_password:
        raise RuntimeError(
            "Session LinkedIn hết hạn hoặc thiếu li_at. Cần password để tự động login "
            "(đăng nhập trên UI lưu cookie, gửi field password trong API, hoặc "
            "LINKEDIN_ENGAGEMENT_PASSWORDS_JSON / LINKEDIN_DEFAULT_ENGAGEMENT_PASSWORD trong .env).",
        )

    actual_force_relogin = force_relogin or not reusable
    logger.info(
        "Engagement session: auto login email=%s force_relogin=%s file=%s",
        (email or pw_email)[:40],
        actual_force_relogin,
        state_path.name,
    )

    login_target_email = pw_email
    if not login_target_email:
        raise RuntimeError(
            "Auto login cần email LinkedIn (Email_crawl có @ hoặc field email).",
        )

    try:
        result = login_and_save_session(
            email=login_target_email,
            password=resolved_password,
            session_id=session_id,
            force_relogin=actual_force_relogin,
            prime_pool=True,
        )
    except Exception as exc:
        raise RuntimeError(f"Auto login trước tương tác thất bại: {exc}") from exc

    if result.status == "need_otp":
        raise RuntimeError(
            "LinkedIn yêu cầu OTP. Gọi POST /verify hoàn tất xác minh, sau đó thử react/comment lại.",
        )

    if result.state_path is None:
        raise RuntimeError("Auto login không lưu được session.")

    return result.session_id, result.state_path
