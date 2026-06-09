"""Request models for API endpoints."""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional, Union
from datetime import datetime
import re

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator


def resolve_playwright_session_email(
    *,
    email_crawl: str,
    email: Optional[str] = None,
) -> Optional[str]:
    """Ưu tiên ``Email_crawl`` (tài khoản cào) — tránh ``email`` dashboard khác file session."""

    crawl = (email_crawl or "").strip()
    if "@" in crawl:
        return crawl
    if email and email.strip():
        return email.strip()
    return None


class LoginRequest(BaseModel):
    """Request body for login endpoint."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: str = Field(
        ...,
        min_length=3,
        description="LinkedIn login email.",
        validation_alias=AliasChoices("email", "userEmail"),
    )
    password: str = Field(
        ...,
        min_length=1,
        description="LinkedIn login password.",
        validation_alias=AliasChoices("password", "userPassword"),
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Optional custom session identifier. If omitted, the API generates one.",
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    force_relogin: bool = Field(
        default=True,
        description="Ignore existing state and login again.",
        validation_alias=AliasChoices("force_relogin", "forceRelogin"),
    )
    prime_pool: bool = Field(
        default=True,
        description=(
            "After login (or reusing saved session), load storage_state on every Playwright pool "
            "worker so react/comment do not hit a cold login per browser."
        ),
        validation_alias=AliasChoices("prime_pool", "primePool"),
    )

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: str) -> str:
        return value.strip()

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class VerifyLoginRequest(BaseModel):
    """Request body for OTP verification after POST /login returns need_otp."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    session_id: str = Field(
        ...,
        min_length=8,
        description="Pending session identifier returned by POST /login when status=need_otp.",
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    otp: str = Field(
        ...,
        min_length=1,
        description="OTP/verification code from LinkedIn email challenge.",
        validation_alias=AliasChoices("otp", "code", "verificationCode"),
    )
    checkpoint_url: Optional[str] = Field(
        default=None,
        description="Optional checkpoint URL returned by POST /login.",
        validation_alias=AliasChoices("checkpoint_url", "checkpointUrl"),
    )
    prime_pool: bool = Field(
        default=True,
        description="After OTP success, prime every Playwright pool worker with the saved session.",
        validation_alias=AliasChoices("prime_pool", "primePool"),
    )

    @field_validator("session_id", "otp")
    @classmethod
    def validate_required_trimmed(cls, value: str) -> str:
        trimmed = value.strip()
        if not trimmed:
            raise ValueError("field is required")
        return trimmed

    @field_validator("checkpoint_url")
    @classmethod
    def validate_checkpoint_url(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None


class ProfileCommentsRequest(BaseModel):
    """POST ``/linkedin/profile-comments`` — cào tab recent activity / comments của profile."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    public_id: str = Field(
        ...,
        min_length=1,
        max_length=200,
        description="Slug profile LinkedIn (phần sau /in/).",
        validation_alias=AliasChoices("public_id", "publicId"),
    )
    max_items: int = Field(
        default=20,
        ge=1,
        le=200,
        validation_alias=AliasChoices("max_items", "maxItems"),
    )
    target_post_id: Optional[str] = Field(
        default=None,
        description="Nếu có, chỉ trả comment trùng post_id (chuỗi số).",
        validation_alias=AliasChoices("target_post_id", "targetPostId"),
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session storage Playwright (khuyến nghị — cần đã POST /login).",
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    email: Optional[str] = Field(
        default=None,
        description="Email đã login — resolve file session nếu không truyền session_id.",
        validation_alias=AliasChoices("email", "userEmail"),
    )

    @field_validator("public_id")
    @classmethod
    def validate_public_id_slug(cls, value: str) -> str:
        v = (value or "").strip().strip("/")
        if not v or not re.match(r"^[a-zA-Z0-9_-]+$", v):
            raise ValueError("public_id chỉ chứa chữ, số, _ và - (slug /in/...)")
        return v

    @field_validator("session_id")
    @classmethod
    def strip_pc_session(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("email")
    @classmethod
    def strip_pc_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("target_post_id")
    @classmethod
    def strip_target_post(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None


class GetMyProfileSlugRequest(BaseModel):
    """POST ``/linkedin/me/profile-slug`` — lấy slug ``/in/<slug>`` của tài khoản đã login."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    session_id: Optional[str] = Field(
        default=None,
        description="Session Playwright (ưu tiên).",
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    email: Optional[str] = Field(
        default=None,
        description="Email đã login — resolve file session nếu không truyền session_id.",
        validation_alias=AliasChoices("email", "userEmail"),
    )

    @field_validator("session_id")
    @classmethod
    def strip_profile_slug_session(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("email")
    @classmethod
    def strip_profile_slug_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @model_validator(mode="after")
    def require_session_or_email(self) -> GetMyProfileSlugRequest:
        if not self.session_id and not self.email:
            raise ValueError("Cần session_id hoặc email để resolve session LinkedIn đã lưu.")
        return self


class ProfileSlugSheetCheckRequest(BaseModel):
    """POST ``/linkedin/me/profile-slug-sheet-check`` — webhook lấy slug sheet, kiểm tra email."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: str = Field(..., min_length=3, validation_alias=AliasChoices("email", "userEmail"))

    @field_validator("email")
    @classmethod
    def strip_sheet_check_email(cls, value: str) -> str:
        return value.strip()


class EnsureProfileSlugRequest(BaseModel):
    """POST ``/linkedin/me/ensure-profile-slug`` — kiểm tra sheet → nếu chưa có thì cào slug + gọi webhook add."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: str = Field(..., min_length=3, validation_alias=AliasChoices("email", "userEmail"))
    session_id: Optional[str] = Field(
        default=None,
        description="Session sau /login hoặc /verify — khuyến nghị khi gọi ngay sau đăng nhập.",
        validation_alias=AliasChoices("session_id", "sessionId"),
    )

    @field_validator("email")
    @classmethod
    def strip_ensure_email(cls, value: str) -> str:
        return value.strip()

    @field_validator("session_id")
    @classmethod
    def strip_ensure_session(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None


class CrawlGroupRequest(BaseModel):
    """Request payload for crawling a LinkedIn group."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    session_id: Optional[str] = Field(
        default=None,
        description="Optional session identifier returned by POST /login.",
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    email: Optional[str] = Field(
        default=None,
        description="Optional LinkedIn email used to resolve a stable session automatically.",
        validation_alias=AliasChoices("email", "userEmail"),
    )
    group_url: str = Field(
        ...,
        min_length=1,
        description="LinkedIn group URL.",
        validation_alias=AliasChoices("group_url", "groupUrl"),
    )
    max_items: Optional[int] = Field(
        default=None,
        ge=1,
        le=500,
        validation_alias=AliasChoices("max_items", "maxItems"),
    )
    target_date: Optional[str] = Field(
        default=None,
        description="Target date in YYYY-MM-DD format.",
        validation_alias=AliasChoices("target_date", "targetDate"),
    )
    fallback_recent_count: int = Field(
        default=20,
        ge=1,
        le=500,
        validation_alias=AliasChoices("fallback_recent_count", "fallbackRecentCount"),
        description="Khi không có bài nào đúng ngày mục tiêu, trả tối đa N bài gần nhất cho n8n.",
    )

    @field_validator("session_id")
    @classmethod
    def validate_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("email")
    @classmethod
    def validate_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("group_url")
    @classmethod
    def validate_group_url(cls, value: str) -> str:
        normalized = value.strip()
        if "linkedin.com/groups/" not in normalized:
            raise ValueError("group_url must be a valid LinkedIn Group URL")
        return normalized

    @field_validator("target_date")
    @classmethod
    def validate_target_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            return None
        datetime.strptime(normalized, "%Y-%m-%d")
        return normalized


class N8nCredentialWebhookRequest(BaseModel):
    """Payload gửi lên webhook n8n (tài khoản, mật khẩu, max_post)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: str = Field(
        ...,
        min_length=3,
        description="Tài khoản LinkedIn (thường là email).",
        validation_alias=AliasChoices("email", "tai_khoan", "userEmail"),
    )
    password: str = Field(
        ...,
        min_length=1,
        description="Mật khẩu LinkedIn.",
        validation_alias=AliasChoices("password", "mat_khau", "userPassword"),
    )
    max_post: int = Field(
        ...,
        ge=1,
        le=500,
        validation_alias=AliasChoices(
            "max_post",
            "maxPosts",
            "max_posts",
            "max_items",
            "maxItems",
        ),
    )

    @field_validator("email")
    @classmethod
    def validate_account_email(cls, value: str) -> str:
        return value.strip()


class StartWorkflowRequest(BaseModel):
    """Payload POST ``/start`` → webhook n8n (cấu hình crawler + danh sách nhóm)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: str = Field(
        ...,
        min_length=3,
        validation_alias=AliasChoices("email", "userEmail"),
    )
    password: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("password", "userPassword"),
    )
    force_relogin: bool = Field(
        default=True,
        validation_alias=AliasChoices("force_relogin", "forceRelogin"),
    )
    max_posts: Optional[int] = Field(
        default=None,
        ge=1,
        le=500,
        validation_alias=AliasChoices("max_posts", "maxPosts", "max_post", "maxPost", "max_items", "maxItems"),
    )
    target_date: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("target_date", "targetDate", "date"),
    )
    mode: Optional[Literal["Detailed", "Fast"]] = Field(
        default=None,
        validation_alias=AliasChoices("mode"),
    )
    delay_sec: Optional[int] = Field(
        default=None,
        ge=0,
        le=600,
        validation_alias=AliasChoices("delay_sec", "delaySec", "delay_seconds", "delaySeconds"),
    )
    group_urls: List[str] = Field(
        default_factory=list,
        validation_alias=AliasChoices("group_urls", "groupUrls", "urls"),
    )

    @field_validator("email")
    @classmethod
    def strip_start_email(cls, value: str) -> str:
        return value.strip()

    @field_validator("target_date")
    @classmethod
    def validate_start_target_date(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        datetime.strptime(text, "%Y-%m-%d")
        return text

    @field_validator("group_urls")
    @classmethod
    def validate_group_urls_start(cls, value: List[str]) -> List[str]:
        normalized: List[str] = []
        for url in value:
            candidate = url.strip()
            if not candidate:
                continue
            if "linkedin.com/groups/" not in candidate:
                raise ValueError("Mỗi group_urls phải là URL nhóm LinkedIn hợp lệ.")
            normalized.append(candidate)
        return normalized


class GetAllPostsRequest(BaseModel):
    """Request to fetch all posts from n8n webhook."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: str = Field(
        default="",
        description="Email to fetch posts for.",
        validation_alias=AliasChoices("email", "userEmail"),
    )
    filters: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional additional filters to pass to n8n.",
        validation_alias=AliasChoices("filters", "filter"),
    )

    @field_validator("email")
    @classmethod
    def validate_email_get_all(cls, value: str) -> str:
        return (value or "").strip()


class N8nGetSheetLinkRequest(BaseModel):
    """Body tùy chọn POST sang webhook n8n lấy link Google Sheet."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    webhook_payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="JSON tùy chọn gửi kèm cho workflow n8n (có thể để {}).",
        validation_alias=AliasChoices("webhook_payload", "payload", "body"),
    )


class N8nWebhookPassthroughRequest(BaseModel):
    """Body JSON được chuyển nguyên sang webhook n8n (URL cấu hình theo từng endpoint)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    webhook_payload: Dict[str, Any] = Field(
        default_factory=dict,
        description="Object JSON POST sang n8n (mặc định {}).",
        validation_alias=AliasChoices("webhook_payload", "payload", "body"),
    )


class FilterDataRequest(BaseModel):
    """Gọi webhook ``get-all-posts`` (n8n), lọc ngày trên backend."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: str = Field(
        ...,
        min_length=1,
        description="Email gửi kèm webhook GET_ALL_POSTS.",
        validation_alias=AliasChoices("email", "userEmail"),
    )
    preset: Optional[Literal["last_7_days", "last_30_days"]] = Field(
        default=None,
        description="Preset khoảng ngày tính đến hôm nay (UTC+0 theo ``datetime.now()`` của server).",
        validation_alias=AliasChoices("preset", "range_preset", "rangePreset"),
    )
    date_from: Optional[str] = Field(
        default=None,
        description="YYYY-MM-DD (bao gồm). Có thể kết hợp với date_to; nếu chỉ có date_from thì date_to = hôm nay.",
        validation_alias=AliasChoices("date_from", "from", "tu_ngay"),
    )
    date_to: Optional[str] = Field(
        default=None,
        description="YYYY-MM-DD (bao gồm).",
        validation_alias=AliasChoices("date_to", "to", "den_ngay"),
    )
    date: Optional[str] = Field(
        default=None,
        description="Một ngày duy nhất YYYY-MM-DD (tương đương date_from = date_to).",
        validation_alias=AliasChoices("date", "target_date", "targetDate", "ngay"),
    )

    @field_validator("email")
    @classmethod
    def validate_email_filter(cls, value: str) -> str:
        return value.strip()

    @field_validator("date", "date_from", "date_to")
    @classmethod
    def validate_yyyy_mm_dd_optional(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        datetime.strptime(text, "%Y-%m-%d")
        return text

    @model_validator(mode="after")
    def exclusive_filter_modes(self) -> FilterDataRequest:
        has_preset = self.preset is not None
        has_range = bool(self.date_from or self.date_to)
        has_single = bool(self.date)
        if sum(bool(x) for x in (has_preset, has_range, has_single)) > 1:
            raise ValueError("Chỉ chọn một kiểu lọc: preset | date_from/date_to | date")
        return self


class LinkedinAppGetAllPostsSheetRequest(BaseModel):
    """Đọc bài của user khớp Email_crawl (bắt buộc)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("email", "userEmail", "Email_crawl", "email_crawl"),
    )

    @field_validator("email")
    @classmethod
    def strip_email_owner(cls, value: str) -> str:
        return value.strip()


class LinkedinAppStatsRequest(BaseModel):
    """Request for LinkedIn app statistics."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("email", "userEmail", "Email_crawl", "email_crawl"),
    )

    @field_validator("email")
    @classmethod
    def strip_email(cls, value: str) -> str:
        return value.strip()


class LinkedinAppFilterPostsSheetRequest(BaseModel):
    """Lọc tab ``top_posts`` theo email owner + khoảng ngày (cột ``Ngày``). Email bắt buộc."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: str = Field(..., min_length=1, validation_alias=AliasChoices("email", "userEmail"))
    date_from: Optional[str] = Field(
        default=None,
        description="Tùy chọn — YYYY-MM-DD (bao gồm).",
        validation_alias=AliasChoices("date_from", "from", "tu_ngay", "TuNgay"),
    )
    date_to: Optional[str] = Field(
        default=None,
        description="Tùy chọn — YYYY-MM-DD (bao gồm).",
        validation_alias=AliasChoices("date_to", "to", "den_ngay", "DenNgay"),
    )

    @field_validator("email")
    @classmethod
    def strip_filter_email(cls, value: str) -> str:
        return value.strip()

    @field_validator("date_from", "date_to")
    @classmethod
    def normalize_optional_dates(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        datetime.strptime(text, "%Y-%m-%d")
        return text

    @model_validator(mode="after")
    def ensure_date_order(self) -> "LinkedinAppFilterPostsSheetRequest":
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError("date_from phải nhỏ hơn hoặc bằng date_to")
        return self


class LinkedinAppCrawlBatchRequest(BaseModel):
    """Crawl nhiều nhóm: mỗi nhóm ghi **1 bài điểm cao nhất trong ngày** (theo ``target_date``); nếu ngày đó không có bài trong feed thì ghi **N bài gần nhất** (scroll/metrics đã có)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    group_urls: List[str] = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("group_urls", "groupUrls", "urls"),
    )
    session_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    email: Optional[str] = Field(
        default=None,
        description="Email đã login (dùng để resolve session).",
        validation_alias=AliasChoices("email", "userEmail"),
    )
    email_crawl: str = Field(
        ...,
        min_length=1,
        description="Giá trị ghi vào cột Email_crawl trên sheet.",
        validation_alias=AliasChoices("email_crawl", "emailCrawl"),
    )
    max_items: Optional[int] = Field(default=None, ge=1, le=500)
    mark_group_done: bool = Field(
        default=True,
        validation_alias=AliasChoices("mark_group_done", "markGroupDone"),
    )
    group_delay_min_sec: Optional[float] = Field(default=None, ge=0.0, le=600.0)
    group_delay_max_sec: Optional[float] = Field(default=None, ge=0.0, le=600.0)
    scroll_times: Optional[int] = Field(default=None, ge=1, le=80)
    scroll_delay_min_sec: Optional[float] = Field(default=None, ge=0.0, le=120.0)
    scroll_delay_max_sec: Optional[float] = Field(default=None, ge=0.0, le=120.0)
    target_date: Optional[str] = Field(
        default=None,
        description='Ngày mục tiêu YYYY-MM-DD (mặc định: ngày crawl). Khớp "cùng ngày" với posted_at đã normalize.',
        validation_alias=AliasChoices("target_date", "targetDate", "ngay", "Ngày"),
    )
    fallback_recent_count: int = Field(
        default=20,
        ge=1,
        le=500,
        validation_alias=AliasChoices("fallback_recent_count", "fallbackRecentCount", "recent_limit"),
        description="Khi không có bài nào thuộc ngày mục tiêu, số bài gần nhất cần ghi vào sheet.",
    )

    @field_validator("session_id")
    @classmethod
    def validate_session_id_batch(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("email")
    @classmethod
    def validate_email_batch(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None

    @field_validator("email_crawl")
    @classmethod
    def validate_email_crawl(cls, value: str) -> str:
        return value.strip()

    @field_validator("target_date")
    @classmethod
    def validate_target_date_sheet(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        text = value.strip()
        if not text:
            return None
        datetime.strptime(text, "%Y-%m-%d")
        return text

    @field_validator("group_urls")
    @classmethod
    def validate_group_urls_batch(cls, value: List[str]) -> List[str]:
        normalized: List[str] = []
        for url in value:
            candidate = url.strip()
            if "linkedin.com/groups/" not in candidate:
                raise ValueError("Mỗi group_urls phải là URL nhóm LinkedIn hợp lệ.")
            normalized.append(candidate)
        return normalized


class N8nGetAllGroupsRequest(BaseModel):
    """POST ``/groups/n8n-get-all``: lấy **toàn bộ nhóm** theo email crawl (``N8N_WEBHOOK_GET_GROUP``).

    Phải có ít nhất một nguồn: cookie ``email_crawl`` hoặc ``body.email``.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: Optional[str] = Field(
        default=None,
        description="Email crawl — n8n lọc danh sách nhóm theo owner này (hoặc dùng cookie email_crawl).",
        validation_alias=AliasChoices("email", "userEmail"),
    )

    @field_validator("email")
    @classmethod
    def strip_email_get_groups(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None


class AddListGroupRequest(BaseModel):
    """Cào hàng loạt URL nhóm LinkedIn (tên + member), POST batch lên ``N8N_WEBHOOK_ADD_LIST_GROUP`` và chờ response."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    group_urls: List[str] = Field(
        ...,
        min_length=1,
        max_length=80,
        validation_alias=AliasChoices("group_urls", "groupUrls", "urls"),
    )
    email: Optional[str] = Field(
        default=None,
        description="Email owner (gửi kèm webhook). Có thể dùng cookie ``email_crawl`` thay cho body.",
        validation_alias=AliasChoices("email", "userEmail"),
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session Playwright đã login (file storage) — khuyến nghị để cào được trang nhóm.",
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    post_to_webhook: bool = Field(
        default=True,
        description="false = chỉ cào, không POST lên n8n. null/omitted = true (gửi webhook).",
        validation_alias=AliasChoices("post_to_webhook", "postToWebhook"),
    )
    webhook_timeout_sec: Optional[float] = Field(
        default=None,
        ge=1.0,
        le=3600.0,
        description="Timeout HTTP chờ n8n trả response (giây). None = N8N_WEBHOOK_ADD_LIST_GROUP_TIMEOUT_SEC (mặc định ~5 phút).",
        validation_alias=AliasChoices("webhook_timeout_sec", "webhookTimeoutSec"),
    )
    delay_min_sec: float = Field(default=2.0, ge=0.0, le=120.0)
    delay_max_sec: float = Field(default=5.0, ge=0.0, le=120.0)
    type: str = Field(
        default="",
        description="Loại nhóm/Intent",
        validation_alias=AliasChoices("type", "Loại nhóm", "loai_nhom", "intent"),
    )

    @field_validator("post_to_webhook", mode="before")
    @classmethod
    def post_to_webhook_coerce(cls, value: Any) -> Any:
        """null / chuỗi rỗng → gửi webhook. Chỉ khi gửi rõ false / 0 / 'false' mới bỏ qua."""

        if value is None or value == "":
            return True
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "on", "y"):
                return True
            if s in ("false", "0", "no", "off", "n"):
                return False
        return value

    @field_validator("session_id")
    @classmethod
    def strip_bulk_session(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("email")
    @classmethod
    def strip_bulk_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("group_urls")
    @classmethod
    def validate_bulk_group_urls(cls, value: List[str]) -> List[str]:
        normalized: List[str] = []
        for url in value:
            candidate = url.strip()
            if not candidate:
                continue
            if "linkedin.com/groups/" not in candidate:
                raise ValueError("Mỗi group_urls phải là URL nhóm LinkedIn hợp lệ.")
            normalized.append(candidate)
        if not normalized:
            raise ValueError("Cần ít nhất một URL nhóm hợp lệ.")
        return normalized


# Tên lớp cũ (tương thích import).
BulkImportGroupsFromUrlsRequest = AddListGroupRequest


class N8nAddGroupRequest(BaseModel):
    """POST tới ``N8N_WEBHOOK_ADD_GROUP``."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    url_group: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("url_group", "urlGroup"),
    )
    name_group: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("name_group", "nameGroup"),
    )
    member: int = Field(..., ge=0, validation_alias=AliasChoices("member", "members"))
    email: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("email", "userEmail"),
    )
    type: str = Field(
        default="",
        description="Loại nhóm/Intent",
        validation_alias=AliasChoices("type", "Loại nhóm", "loai_nhom", "intent"),
    )

    @field_validator("url_group", "name_group")
    @classmethod
    def strip_add_strings(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def strip_add_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    def to_webhook_payload(self, email_resolved: str) -> Dict[str, Any]:
        return {
            "url_group": self.url_group.strip(),
            "name_group": self.name_group.strip(),
            "member": int(self.member),
            "email": email_resolved.strip(),
            "type": self.type.strip(),
        }


class N8nRemoveGroupRequest(BaseModel):
    """POST tới ``N8N_WEBHOOK_REMOVE_GROUP``."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    url_group: str = Field(..., min_length=1, validation_alias=AliasChoices("url_group", "urlGroup"))
    email: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("email", "userEmail"),
    )

    @field_validator("url_group")
    @classmethod
    def strip_remove_url(cls, value: str) -> str:
        return value.strip()

    @field_validator("email")
    @classmethod
    def strip_remove_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    def to_webhook_payload(self, email_resolved: str) -> Dict[str, Any]:
        return {
            "url_group": self.url_group.strip(),
            "email": email_resolved.strip(),
        }


class N8nUpdateGroupRequest(BaseModel):
    """POST tới ``N8N_WEBHOOK_UPDATE_GROUP``. Trường ``new_*`` tùy chọn — để trống thì gửi giá trị hiện tại."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    url_group_need_update: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("url_group_need_update", "urlGroupNeedUpdate"),
    )
    name_group: str = Field(
        ...,
        description="Tên hiện tại — dùng khi không đổi (new_name_group trống).",
        validation_alias=AliasChoices("name_group", "nameGroup", "current_name_group", "currentNameGroup"),
    )
    member: int = Field(
        ...,
        ge=0,
        description="Member hiện tại — dùng khi không gửi new_member.",
        validation_alias=AliasChoices("member", "members", "current_member", "currentMember"),
    )
    new_url_group: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("new_url_group", "newUrlGroup"),
    )
    new_name_group: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("new_name_group", "newNameGroup"),
    )
    new_member: Optional[int] = Field(
        default=None,
        ge=0,
        validation_alias=AliasChoices("new_member", "newMember"),
    )
    new_type: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("new_type", "newType"),
    )
    email: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("email", "userEmail"),
    )

    @field_validator("url_group_need_update", "name_group")
    @classmethod
    def strip_upd_req(cls, value: str) -> str:
        return value.strip()

    @field_validator("new_url_group", "new_name_group")
    @classmethod
    def strip_upd_opt(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("email")
    @classmethod
    def strip_upd_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    def to_webhook_payload(self, email_resolved: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "url_group_need_update": self.url_group_need_update.strip(),
            "name_group": self.name_group.strip(),
            "member": int(self.member),
            "email": email_resolved.strip(),
        }
        if self.new_url_group is not None:
            payload["new_url_group"] = self.new_url_group
        if self.new_name_group is not None:
            payload["new_name_group"] = self.new_name_group
        if self.new_member is not None:
            payload["new_member"] = int(self.new_member)
        if self.new_type is not None:
            payload["new_type"] = self.new_type.strip()
        return payload


PostReactionKind = Literal["like", "love", "celebrate", "support", "insightful", "funny"]


class PostReactionRequest(BaseModel):
    """POST ``/linkedin/post/react`` — Playwright mở ``post_url``, click reaction, rồi (tuỳ chọn) webhook sheet."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    post_url: str = Field(
        ...,
        min_length=12,
        description="URL bài LinkedIn (vd. permalink activity).",
        validation_alias=AliasChoices("post_url", "postUrl", "URL_Bài_Viết"),
    )
    reaction: PostReactionKind = Field(
        ...,
        description="Loại reaction: like | love | celebrate | support | insightful | funny.",
    )
    Email_crawl: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("Email_crawl", "email_crawl"),
    )
    ID_session_crawl: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("ID_session_crawl", "id_session_crawl"),
    )
    row_number: int = Field(
        ...,
        ge=1,
        validation_alias=AliasChoices("row_number", "rowNumber"),
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session Playwright đã login — ưu tiên resolve file storage.",
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    email: Optional[str] = Field(
        default=None,
        description="Email đã login — dùng nếu không có session_id (hoặc kèm session_id).",
        validation_alias=AliasChoices("email", "userEmail"),
    )
    password: Optional[str] = Field(
        default=None,
        description="LinkedIn password — tự login trước Playwright nếu session hết hạn.",
        validation_alias=AliasChoices(
            "password",
            "userPassword",
            "linkedin_password",
            "mat_khau",
        ),
    )
    auto_login: bool = Field(
        default=True,
        description="Tự đảm bảo session (login/prime) trước khi mở bài.",
        validation_alias=AliasChoices("auto_login", "autoLogin"),
    )
    post_to_webhook: bool = Field(
        default=True,
        description="Sau khi reaction thành công, POST JSON tới N8N_WEBHOOK_REACTION (fallback N8N_WEBHOOK_POST_REACTION).",
        validation_alias=AliasChoices("post_to_webhook", "postToWebhook"),
    )
    clear_reaction: bool = Field(
        default=False,
        description="true: gỡ reaction trên LinkedIn và ghi ô reaction trống (không null) trên sheet.",
        validation_alias=AliasChoices("clear_reaction", "clearReaction"),
    )
    sheet_row: Optional[Dict[str, Any]] = Field(
        default=None,
        description=(
            "Toàn bộ key/value của dòng bài (như sheet/API) — webhook nhận merge object này "
            "rồi ghi đè Email_crawl, ID_session_crawl, row_number, reaction, post_url."
        ),
        validation_alias=AliasChoices(
            "sheet_row",
            "sheetRow",
            "full_row",
            "fullRow",
            "post_record",
            "postRecord",
            "fields",
        ),
    )

    @field_validator("post_url")
    @classmethod
    def validate_post_url_li(cls, value: str) -> str:
        u = value.strip()
        if "linkedin.com" not in u.lower():
            raise ValueError("post_url phải là URL LinkedIn.")
        return u

    @field_validator("Email_crawl")
    @classmethod
    def strip_email_crawl(cls, value: str) -> str:
        return value.strip()

    @field_validator("ID_session_crawl")
    @classmethod
    def strip_id_session(cls, value: str) -> str:
        return value.strip()

    @field_validator("session_id")
    @classmethod
    def strip_session_id(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("email")
    @classmethod
    def strip_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("post_to_webhook", mode="before")
    @classmethod
    def coerce_post_to_webhook(cls, value: Union[bool, str, int, None]) -> Any:
        if value is None or value == "":
            return True
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "on", "y"):
                return True
            if s in ("false", "0", "no", "off", "n"):
                return False
        return value

    @field_validator("clear_reaction", mode="before")
    @classmethod
    def coerce_clear_reaction(cls, value: Union[bool, str, int, None]) -> Any:
        if value is None or value == "":
            return False
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "on", "y"):
                return True
            if s in ("false", "0", "no", "off", "n"):
                return False
        return value

    @model_validator(mode="after")
    def require_playwright_session_hint(self) -> PostReactionRequest:
        has_session = bool(self.session_id)
        has_email_field = bool(self.email)
        crawl_email = self.Email_crawl
        crawl_as_login = "@" in crawl_email
        if not has_session and not has_email_field and not crawl_as_login:
            raise ValueError(
                "Cần ít nhất một trong: session_id, email (Playwright), hoặc Email_crawl là địa chỉ email để resolve session.",
            )
        return self

    def playwright_resolve_email(self) -> Optional[str]:
        """Email dùng cho ``build_session_state_path`` khi không chỉ có session_id."""

        return resolve_playwright_session_email(
            email_crawl=self.Email_crawl,
            email=self.email,
        )


class AppCommentEntry(BaseModel):
    """Một phần tử trong mảng ``comment`` trên sheet / webhook."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    comment_content: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("comment_content", "commentContent", "comment"),
    )
    ngay_comment: str = Field(
        ...,
        min_length=6,
        max_length=32,
        serialization_alias="ngày comment",
        validation_alias=AliasChoices(
            "ngày comment",
            "ngay_comment",
            "day_comment",
            "dayComment",
        ),
        description="Ngày gửi comment (ISO YYYY-MM-DD).",
    )

    @field_validator("comment_content", "ngay_comment")
    @classmethod
    def strip_comment_fields(cls, value: str) -> str:
        return value.strip()


class PostCommentRequest(BaseModel):
    """POST ``/linkedin/post/comment`` — Playwright nhập và đăng comment; webhook Giống reaction."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    post_url: str = Field(
        ...,
        min_length=12,
        validation_alias=AliasChoices("post_url", "postUrl", "URL_Bài_Viết"),
    )
    comment_text: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("comment_text", "commentText"),
    )
    Email_crawl: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("Email_crawl", "email_crawl"),
    )
    ID_session_crawl: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("ID_session_crawl", "id_session_crawl"),
    )
    row_number: int = Field(
        ...,
        ge=1,
        validation_alias=AliasChoices("row_number", "rowNumber"),
    )
    existing_app_comments: List[AppCommentEntry] = Field(
        default_factory=list,
        validation_alias=AliasChoices(
            "existing_app_comments",
            "existingAppComments",
            "app_comments_existing",
        ),
    )
    session_id: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    email: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("email", "userEmail"),
    )
    password: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "password",
            "userPassword",
            "linkedin_password",
            "mat_khau",
        ),
    )
    auto_login: bool = Field(
        default=True,
        validation_alias=AliasChoices("auto_login", "autoLogin"),
    )
    post_to_webhook: bool = Field(
        default=True,
        validation_alias=AliasChoices("post_to_webhook", "postToWebhook"),
    )
    sheet_row: Optional[Dict[str, Any]] = Field(
        default=None,
        validation_alias=AliasChoices(
            "sheet_row",
            "sheetRow",
            "full_row",
            "fullRow",
            "post_record",
            "postRecord",
            "fields",
        ),
    )
    typing_delay_ms: int = Field(
        default=30,
        ge=0,
        le=500,
        validation_alias=AliasChoices("typing_delay_ms", "typingDelayMs"),
    )
    timeout_ms: int = Field(
        default=300000,
        ge=5000,
        le=600000,
        validation_alias=AliasChoices("timeout_ms", "timeoutMs"),
    )

    @field_validator("post_url")
    @classmethod
    def validate_post_url_li_comment(cls, value: str) -> str:
        u = value.strip()
        if "linkedin.com" not in u.lower():
            raise ValueError("post_url phải là URL LinkedIn.")
        return u

    @field_validator("comment_text")
    @classmethod
    def strip_comment_text(cls, value: str) -> str:
        t = value.strip()
        if not t:
            raise ValueError("comment_text không được rỗng.")
        return t

    @field_validator("Email_crawl")
    @classmethod
    def strip_email_crawl_comment(cls, value: str) -> str:
        return value.strip()

    @field_validator("ID_session_crawl")
    @classmethod
    def strip_id_session_comment(cls, value: str) -> str:
        return value.strip()

    @field_validator("session_id")
    @classmethod
    def strip_session_id_comment(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("email")
    @classmethod
    def strip_email_comment(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("post_to_webhook", mode="before")
    @classmethod
    def coerce_post_to_webhook_comment(cls, value: Union[bool, str, int, None]) -> Any:
        if value is None or value == "":
            return True
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "on", "y"):
                return True
            if s in ("false", "0", "no", "off", "n"):
                return False
        return value

    @model_validator(mode="after")
    def require_playwright_session_hint_comment(self) -> PostCommentRequest:
        has_session = bool(self.session_id)
        has_email_field = bool(self.email)
        crawl_email = self.Email_crawl
        crawl_as_login = "@" in crawl_email
        if not has_session and not has_email_field and not crawl_as_login:
            raise ValueError(
                "Cần ít nhất một trong: session_id, email (Playwright), hoặc Email_crawl là địa chỉ email để resolve session.",
            )
        return self

    def playwright_resolve_email(self) -> Optional[str]:
        return resolve_playwright_session_email(
            email_crawl=self.Email_crawl,
            email=self.email,
        )


class PostCommentDeleteRequest(BaseModel):
    """POST ``/linkedin/post/comment/delete`` — Xóa comment từ LinkedIn (optimized direct post URL route).
    
    Workflow:
    1. Vào trực tiếp URL bài viết (post_url) — không cần qua recent-activity page
    2. Tìm commentText + You/Bạn trong comment blocks
    3. Mở menu tùy chọn → Delete → confirm
    
    Lợi ích: Nhanh hơn vì skip timeline scan, không cần max_scroll.
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    profile_slug: str = Field(
        ...,
        min_length=1,
        description="LinkedIn profile slug (e.g. 'nmhoang-dev').",
        validation_alias=AliasChoices("profile_slug", "profileSlug"),
    )
    post_url: str = Field(
        ...,
        min_length=12,
        description="URL bài LinkedIn (vd. permalink activity).",
        validation_alias=AliasChoices("post_url", "postUrl", "URL_Bài_Viết"),
    )
    comment_text: str = Field(
        ...,
        min_length=1,
        description="Nội dung comment cần xóa (exact match).",
        validation_alias=AliasChoices("comment_text", "commentText"),
    )
    Email_crawl: str = Field(
        ...,
        min_length=1,
        description="Email tài khoản crawl.",
        validation_alias=AliasChoices("Email_crawl", "email_crawl"),
    )
    ID_session_crawl: str = Field(
        ...,
        min_length=1,
        description="ID phiên crawl.",
        validation_alias=AliasChoices("ID_session_crawl", "id_session_crawl"),
    )
    row_number: int = Field(
        ...,
        ge=1,
        description="Số dòng trong bảng.",
        validation_alias=AliasChoices("row_number", "rowNumber"),
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session Playwright đã login — ưu tiên resolve file storage.",
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    email: Optional[str] = Field(
        default=None,
        description="Email đã login — dùng nếu không có session_id (hoặc kèm session_id).",
        validation_alias=AliasChoices("email", "userEmail"),
    )
    post_to_webhook: bool = Field(
        default=True,
        description="Sau khi xóa comment thành công, POST JSON tới N8N_WEBHOOK_REACTION để ghi đè Sheet.",
        validation_alias=AliasChoices("post_to_webhook", "postToWebhook"),
    )
    sheet_row: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Toàn bộ key/value của dòng bài (như sheet/API) — webhook nhận merge object này.",
        validation_alias=AliasChoices(
            "sheet_row",
            "sheetRow",
            "full_row",
            "fullRow",
            "post_record",
            "postRecord",
            "fields",
        ),
    )
    max_scroll: int = Field(
        default=8,
        ge=1,
        le=20,
        description="[Deprecated] Không dùng cho optimized route. Giữ lại vì backward compatible.",
        validation_alias=AliasChoices("max_scroll", "maxScroll"),
    )
    timeout_ms: int = Field(
        default=300000,
        ge=30000,
        le=600000,
        description="Timeout chung (ms). Default 300s hỗ trợ mạng yếu.",
        validation_alias=AliasChoices("timeout_ms", "timeoutMs"),
    )

    @field_validator("profile_slug")
    @classmethod
    def validate_profile_slug(cls, value: str) -> str:
        s = value.strip()
        if not s or len(s) < 1:
            raise ValueError("profile_slug không được rỗng.")
        return s

    @field_validator("post_url")
    @classmethod
    def validate_post_url_delete(cls, value: str) -> str:
        u = value.strip()
        if "linkedin.com" not in u.lower():
            raise ValueError("post_url phải là URL LinkedIn.")
        return u

    @field_validator("comment_text")
    @classmethod
    def strip_comment_text_delete(cls, value: str) -> str:
        t = value.strip()
        if not t:
            raise ValueError("comment_text không được rỗng.")
        return t

    @field_validator("Email_crawl")
    @classmethod
    def strip_email_crawl_delete(cls, value: str) -> str:
        return value.strip()

    @field_validator("ID_session_crawl")
    @classmethod
    def strip_id_session_delete(cls, value: str) -> str:
        return value.strip()

    @field_validator("session_id")
    @classmethod
    def strip_session_id_delete(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("email")
    @classmethod
    def strip_email_delete(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("post_to_webhook", mode="before")
    @classmethod
    def coerce_post_to_webhook_delete(cls, value: Union[bool, str, int, None]) -> Any:
        if value is None or value == "":
            return True
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "on", "y"):
                return True
            if s in ("false", "0", "no", "off", "n"):
                return False
        return value

    @model_validator(mode="after")
    def require_playwright_session_hint_delete(self) -> PostCommentDeleteRequest:
        has_session = bool(self.session_id)
        has_email_field = bool(self.email)
        crawl_email = self.Email_crawl
        crawl_as_login = "@" in crawl_email
        if not has_session and not has_email_field and not crawl_as_login:
            raise ValueError(
                "Cần ít nhất một trong: session_id, email (Playwright), hoặc Email_crawl là địa chỉ email để resolve session.",
            )
        return self

    def playwright_resolve_email(self) -> Optional[str]:
        return resolve_playwright_session_email(
            email_crawl=self.Email_crawl,
            email=self.email,
        )


class PostCommentEditRequest(BaseModel):
    """POST ``/linkedin/post/comment/edit`` — Chỉnh sửa comment từ LinkedIn post detail.
    
    Workflow:
    1. Vào trực tiếp URL bài viết (post_url)
    2. Tìm comment với nội dung = comment_text (cũ)
    3. Mở menu tùy chọn → Click Edit
    4. Hiển thị form edit với contenteditable text editor
    5. Xóa text cũ, nhập text mới
    6. Click Save changes
    7. Gửi webhook để ghi đè Sheet (giống post comment)
    """

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    profile_slug: str = Field(
        ...,
        min_length=1,
        description="LinkedIn profile slug (e.g. 'nmhoang-dev').",
        validation_alias=AliasChoices("profile_slug", "profileSlug"),
    )
    post_url: str = Field(
        ...,
        min_length=12,
        description="URL bài LinkedIn.",
        validation_alias=AliasChoices("post_url", "postUrl", "URL_Bài_Viết"),
    )
    comment_text: str = Field(
        ...,
        min_length=1,
        description="Nội dung comment cũ (để tìm).",
        validation_alias=AliasChoices("comment_text", "commentText"),
    )
    new_comment_text: str = Field(
        ...,
        min_length=1,
        description="Nội dung comment mới (để replace).",
        validation_alias=AliasChoices("new_comment_text", "newCommentText"),
    )
    Email_crawl: str = Field(
        ...,
        min_length=1,
        description="Email tài khoản crawl.",
        validation_alias=AliasChoices("Email_crawl", "email_crawl"),
    )
    ID_session_crawl: str = Field(
        ...,
        min_length=1,
        description="ID phiên crawl.",
        validation_alias=AliasChoices("ID_session_crawl", "id_session_crawl"),
    )
    row_number: int = Field(
        ...,
        ge=1,
        description="Số dòng trong bảng.",
        validation_alias=AliasChoices("row_number", "rowNumber"),
    )
    session_id: Optional[str] = Field(
        default=None,
        description="Session Playwright đã login — ưu tiên resolve file storage.",
        validation_alias=AliasChoices("session_id", "sessionId"),
    )
    email: Optional[str] = Field(
        default=None,
        description="Email đã login — dùng nếu không có session_id.",
        validation_alias=AliasChoices("email", "userEmail"),
    )
    post_to_webhook: bool = Field(
        default=True,
        description="Sau khi edit comment thành công, POST JSON tới N8N_WEBHOOK_REACTION để ghi đè Sheet.",
        validation_alias=AliasChoices("post_to_webhook", "postToWebhook"),
    )
    sheet_row: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Toàn bộ key/value của dòng bài — webhook nhận merge object này.",
        validation_alias=AliasChoices(
            "sheet_row",
            "sheetRow",
            "full_row",
            "fullRow",
            "post_record",
            "postRecord",
            "fields",
        ),
    )
    timeout_ms: int = Field(
        default=300000,
        ge=30000,
        le=600000,
        description="Timeout chung (ms).",
        validation_alias=AliasChoices("timeout_ms", "timeoutMs"),
    )

    @field_validator("profile_slug")
    @classmethod
    def validate_profile_slug_edit(cls, value: str) -> str:
        s = value.strip()
        if not s or len(s) < 1:
            raise ValueError("profile_slug không được rỗng.")
        return s

    @field_validator("post_url")
    @classmethod
    def validate_post_url_edit(cls, value: str) -> str:
        u = value.strip()
        if "linkedin.com" not in u.lower():
            raise ValueError("post_url phải là URL LinkedIn.")
        return u

    @field_validator("comment_text")
    @classmethod
    def strip_comment_text_edit(cls, value: str) -> str:
        t = value.strip()
        if not t:
            raise ValueError("comment_text không được rỗng.")
        return t

    @field_validator("new_comment_text")
    @classmethod
    def strip_new_comment_text(cls, value: str) -> str:
        t = value.strip()
        if not t:
            raise ValueError("new_comment_text không được rỗng.")
        return t

    @field_validator("Email_crawl")
    @classmethod
    def strip_email_crawl_edit(cls, value: str) -> str:
        return value.strip()

    @field_validator("ID_session_crawl")
    @classmethod
    def strip_id_session_edit(cls, value: str) -> str:
        return value.strip()

    @field_validator("session_id")
    @classmethod
    def strip_session_id_edit(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("email")
    @classmethod
    def strip_email_edit(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        t = value.strip()
        return t or None

    @field_validator("post_to_webhook", mode="before")
    @classmethod
    def coerce_post_to_webhook_edit(cls, value: Union[bool, str, int, None]) -> Any:
        if value is None or value == "":
            return True
        if isinstance(value, str):
            s = value.strip().lower()
            if s in ("true", "1", "yes", "on", "y"):
                return True
            if s in ("false", "0", "no", "off", "n"):
                return False
        return value

    @model_validator(mode="after")
    def require_playwright_session_hint_edit(self) -> PostCommentEditRequest:
        has_session = bool(self.session_id)
        has_email_field = bool(self.email)
        crawl_email = self.Email_crawl
        crawl_as_login = "@" in crawl_email
        if not has_session and not has_email_field and not crawl_as_login:
            raise ValueError(
                "Cần ít nhất một trong: session_id, email (Playwright), hoặc Email_crawl là địa chỉ email để resolve session.",
            )
        return self

    def playwright_resolve_email(self) -> Optional[str]:
        return resolve_playwright_session_email(
            email_crawl=self.Email_crawl,
            email=self.email,
        )


class SyncPostProgressRequest(BaseModel):
    """POST ``/linkedin/post/sync-progress`` — Đọc lại reaction/comment của user trên 1 bài."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    post_url: str = Field(..., min_length=12, validation_alias=AliasChoices("post_url", "postUrl"))
    profile_slug: str = Field(..., min_length=1, validation_alias=AliasChoices("profile_slug", "profileSlug"))
    Email_crawl: str = Field(..., min_length=1, validation_alias=AliasChoices("Email_crawl", "email_crawl"))
    ID_session_crawl: str = Field(..., min_length=1, validation_alias=AliasChoices("ID_session_crawl", "id_session_crawl"))
    row_number: int = Field(..., ge=1, validation_alias=AliasChoices("row_number", "rowNumber"))
    session_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("session_id", "sessionId"))
    email: Optional[str] = Field(default=None, validation_alias=AliasChoices("email", "userEmail"))
    password: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "password",
            "userPassword",
            "linkedin_password",
            "mat_khau",
        ),
    )
    auto_login: bool = Field(
        default=True,
        validation_alias=AliasChoices("auto_login", "autoLogin"),
    )
    post_to_webhook: bool = Field(default=True, validation_alias=AliasChoices("post_to_webhook", "postToWebhook"))
    sheet_row: Optional[Dict[str, Any]] = Field(default=None, validation_alias=AliasChoices("sheet_row", "sheetRow"))
    timeout_ms: int = Field(default=300000, ge=30000, le=600000)

    @model_validator(mode="after")
    def require_playwright_session_hint_sync(self) -> SyncPostProgressRequest:
        has_session = bool(self.session_id)
        has_email_field = bool(self.email)
        crawl_email = self.Email_crawl
        crawl_as_login = "@" in crawl_email
        if not has_session and not has_email_field and not crawl_as_login:
            raise ValueError("Cần session_id hoặc email để resolve session.")
        return self

    def playwright_resolve_email(self) -> Optional[str]:
        """Email dùng cho ``build_session_state_path`` khi không chỉ có session_id."""
        return resolve_playwright_session_email(
            email_crawl=self.Email_crawl,
            email=self.email,
        )


class SyncAllProgressRequest(BaseModel):
    """POST ``/linkedin/sync-all-progress`` — Đọc lại toàn bộ bài của user (danh sách lấy từ Sheet)."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email_crawl: str = Field(..., min_length=1, validation_alias=AliasChoices("email_crawl", "Email_crawl"))
    profile_slug: str = Field(..., min_length=1, validation_alias=AliasChoices("profile_slug", "profileSlug"))
    session_id: Optional[str] = Field(default=None, validation_alias=AliasChoices("session_id", "sessionId"))
    email: Optional[str] = Field(default=None, validation_alias=AliasChoices("email", "userEmail"))
    password: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "password",
            "userPassword",
            "linkedin_password",
            "mat_khau",
        ),
    )
    auto_login: bool = Field(
        default=True,
        validation_alias=AliasChoices("auto_login", "autoLogin"),
    )
    timeout_ms_per_post: int = Field(default=120000, ge=30000, le=300000)
    limit_posts: Optional[int] = Field(default=None, ge=1, le=100)

    def playwright_resolve_email(self) -> Optional[str]:
        """Email dùng cho ``build_session_state_path`` khi không chỉ có session_id."""
        return resolve_playwright_session_email(
            email_crawl=self.email_crawl,
            email=self.email,
        )


class KpiItem(BaseModel):
    """Một mục KPI trong mảng ``kpi``."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    start_day: str = Field(..., validation_alias=AliasChoices("start_day", "startDay"))
    end_day: str = Field(..., validation_alias=AliasChoices("end_day", "endDay"))
    total_reaction: Union[int, str] = Field(
        ...,
        validation_alias=AliasChoices("total_reaction", "totalReaction", "reactions"),
    )
    total_comment: Union[int, str] = Field(
        ...,
        validation_alias=AliasChoices("total_comment", "totalComment", "comments"),
    )
    total_post_crawl: Union[int, str] = Field(
        ...,
        validation_alias=AliasChoices("total_post_crawl", "totalPostCrawl", "posts"),
    )
    total_session_crawl: Union[int, str] = Field(
        ...,
        validation_alias=AliasChoices("total_session_crawl", "totalSessionCrawl", "sessions"),
    )


class AssignKpiRequest(BaseModel):
    """POST ``/kpi/assign`` — Leader gán KPI cho member."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    leader_role: str = Field(
        ...,
        description="Vai trò người gọi (phải là 'leader').",
        validation_alias=AliasChoices("leader_role", "leaderRole"),
    )
    email: str = Field(..., min_length=1, description="Email của member được gán.")
    profile_slug: str = Field(
        ...,
        min_length=1,
        validation_alias=AliasChoices("profile_slug", "profileSlug"),
    )
    email_leader: str = Field(
        ...,
        min_length=1,
        description="Email leader (n8n/sheet dùng để ghi đúng nhóm / cột email_leader).",
        validation_alias=AliasChoices("email_leader", "emailLeader", "leaderEmail"),
    )
    member_role: str = Field(
        default="member",
        description="Vai trò của member (JSON gửi n8n dùng key ``role``).",
        serialization_alias="role",
        validation_alias=AliasChoices("member_role", "role", "memberRole"),
    )
    kpi: List[KpiItem] = Field(default_factory=list)

    @field_validator("leader_role", "email", "profile_slug", "member_role", "email_leader")
    @classmethod
    def strip_kpi_fields(cls, value: str) -> str:
        return value.strip()


class CheckPermissionRequest(BaseModel):
    """POST ``/auth/check-permission`` — Kiểm tra quyền leader/member."""

    model_config = ConfigDict(populate_by_name=True, extra="ignore")

    email: str = Field(..., min_length=1, validation_alias=AliasChoices("email", "userEmail"))

    @field_validator("email")
    @classmethod
    def strip_email(cls, value: str) -> str:
        return value.strip()


class GetAllKpiRequest(BaseModel):
    """POST /kpi/get-all — Lấy toàn bộ KPI cho leader."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    email_leader: str = Field(..., validation_alias=AliasChoices("email_leader", "emailLeader", "email"))

class GetKpiByEmailRequest(BaseModel):
    """POST /kpi/get-by-email — Lấy KPI cho member."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    email: str = Field(..., validation_alias=AliasChoices("email", "userEmail"))

class AddMemberRequest(BaseModel):
    """POST /team/add-member — Thêm member mới."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    email_member: str = Field(..., validation_alias=AliasChoices("email_member", "emailMember", "memberEmail"))
    email_leader: str = Field(..., validation_alias=AliasChoices("email_leader", "emailLeader", "leaderEmail"))

class VerifyLeaderCodeRequest(BaseModel):
    """POST /auth/verify-leader-code — Kiểm tra mã leader."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    code: str

class GetProfilesRequest(BaseModel):
    """POST /linkedin/all-profiles — Lấy danh sách toàn bộ profile."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    email: str = Field(..., validation_alias=AliasChoices("email", "userEmail"))

class UpdateProfileSlugRequest(BaseModel):
    """POST /linkedin/me/profile-slug-update — Cập nhật profile slug kèm thông tin mở rộng."""
    model_config = ConfigDict(populate_by_name=True, extra="ignore")
    email_crawl: str = Field(..., validation_alias=AliasChoices("email_crawl", "Email_crawl", "email"))
    profile_slug: str = Field(default="", validation_alias=AliasChoices("profile_slug", "profileSlug", "slug"))
    profile_url: str = Field(default="", validation_alias=AliasChoices("profile_url", "profileUrl", "url"))
    role: str = Field(default="member", validation_alias=AliasChoices("role", "member_role", "memberRole"))
    kpi: List[Dict[str, Any]] = Field(default_factory=list)
    email_leader: Optional[str] = Field(default="", validation_alias=AliasChoices("email_leader", "emailLeader", "leaderEmail"))
