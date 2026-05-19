"""Response models for API endpoints."""

from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


class BaseResponse(BaseModel):
    """Common response envelope."""

    success: bool
    message: str
    data: Optional[Any] = None


class LoginResponse(BaseResponse):
    """Login response payload."""

    session_id: Optional[str] = None
    state_path: Optional[str] = None
    email: Optional[str] = None
    login_step: Literal["success", "need_otp", "error"] = "error"
    need_otp: bool = False
    checkpoint_url: Optional[str] = None


class VerifyLoginResponse(LoginResponse):
    """Verify OTP response payload (same envelope as login)."""


class StatusDataResponse(BaseModel):
    """Runtime status exposed to the frontend."""

    api_key_enabled: bool
    headless: bool
    playwright_pool_size: int = 1
    default_max_items: int
    default_scroll_times: int
    cors_origins: list[str]
    n8n_webhook_configured: bool
    n8n_get_link_webhook_configured: bool
    n8n_webhook_get_post_crawled_configured: bool = False
    n8n_webhook_get_url_group_crawled_configured: bool = False
    n8n_webhook_get_result_crawl_by_id_configured: bool = False
    n8n_webhook_filter_data_configured: bool = False
    n8n_webhook_get_all_posts_configured: bool = False
    n8n_webhook_start_configured: bool = False
    n8n_webhook_get_group_configured: bool = False
    n8n_webhook_add_group_configured: bool = False
    n8n_webhook_remove_group_configured: bool = False
    n8n_webhook_update_group_configured: bool = False
    n8n_webhook_add_list_group_configured: bool = False
    n8n_webhook_bulk_import_groups_configured: bool = False
    n8n_webhook_get_profile_slugs_configured: bool = False
    n8n_webhook_add_profile_slug_configured: bool = False
    n8n_webhook_post_reaction_configured: bool = False
    n8n_webhook_post_comment_configured: bool = False
    n8n_webhook_assign_kpi_configured: bool = False
    n8n_webhook_check_permission_configured: bool = False
    google_sheet_configured: bool = False


class StatusResponse(BaseResponse):
    """Status endpoint response."""

    data: StatusDataResponse


class TopPostResponse(BaseModel):
    """Normalized top post representation."""

    model_config = ConfigDict(extra="ignore")

    author: str = ""
    content: str = ""
    posted_at_raw: str = ""
    posted_at: Optional[str] = None
    likes: int = 0
    comments: int = 0
    reposts: int = 0
    score: int = 0
    post_url: str = ""

    @classmethod
    def from_post_dict(cls, data: dict[str, Any]) -> TopPostResponse:
        """Map dict crawl/webhook sang schema cố định (tránh lỗi kiểu dữ liệu)."""

        raw_pa = data.get("posted_at")
        posted_at = raw_pa if isinstance(raw_pa, str) else (str(raw_pa) if raw_pa is not None else None)

        def _int(v: Any, default: int = 0) -> int:
            try:
                return int(v)
            except (TypeError, ValueError):
                return default

        return cls(
            author=str(data.get("author") or ""),
            content=str(data.get("content") or ""),
            posted_at_raw=str(data.get("posted_at_raw") or ""),
            posted_at=posted_at,
            likes=_int(data.get("likes")),
            comments=_int(data.get("comments")),
            reposts=_int(data.get("reposts")),
            score=_int(data.get("score")),
            post_url=str(data.get("post_url") or ""),
        )


class CrawlDataResponse(BaseModel):
    """Data section for crawl response."""

    session_id: str
    group_url: str
    group_name: str = ""
    target_date: str
    email: Optional[str] = None
    total_posts_scraped: int = Field(default=0)
    total_posts_in_target_date: int = Field(default=0)
    top_post: Optional[TopPostResponse] = None
    posts: list[TopPostResponse] = Field(
        default_factory=list,
        description="Tất cả bài thuộc ngày mục tiêu; hoặc tối đa N bài gần nhất khi fallback.",
    )
    selection_mode: str = Field(
        default="target_day",
        description="target_day = lọc theo ngày; fallback_recent = không có bài trong ngày.",
    )


class CrawlResponse(BaseResponse):
    """Crawl endpoint response."""

    data: Optional[CrawlDataResponse] = None


class N8nWebhookNotifyData(BaseModel):
    """Metadata after calling n8n webhook (không chứa mật khẩu)."""

    http_status: int = Field(ge=100, lt=600)
    response_preview: str = ""
    response_message: Optional[str] = Field(
        default=None,
        description="Thông điệp chính đã parse từ body webhook (nếu có).",
    )
    response_payload: Optional[Any] = Field(
        default=None,
        description="Body webhook đã parse JSON (nếu parse được).",
    )
    id_session_crawl: Optional[str] = Field(
        default=None,
        description="Định danh phiên (POST /start): gửi kèm webhook start và trả về cho client.",
    )


class N8nWebhookNotifyResponse(BaseResponse):
    """Envelope cho POST forward tới webhook n8n."""

    data: Optional[N8nWebhookNotifyData] = None


class BulkGroupImportScrapedItem(BaseModel):
    """Một dòng kết quả sau khi cào trang nhóm."""

    url_group: str
    name_group: str = ""
    member: int = 0
    memberCount: Optional[int] = None
    success: bool = False
    error: Optional[str] = None


class BulkGroupImportData(BaseModel):
    items: list[BulkGroupImportScrapedItem]
    webhook_http_status: Optional[int] = None
    webhook_response_preview: Optional[str] = Field(
        default=None,
        description="Đoạn đầu body webhook (rút gọn) — giữ cho UI/log nhanh.",
    )
    webhook_response: Optional[Any] = Field(
        default=None,
        description="Body webhook sau khi chờ response: parse JSON thì trả dict/list; không parse được thì chuỗi (giới hạn độ dài).",
    )
    webhook_skipped: bool = False


class BulkGroupImportResponse(BaseResponse):
    data: Optional[BulkGroupImportData] = None


class ProfileSlugData(BaseModel):
    """Slug và URL profile công khai của user đang đăng nhập."""

    profile_slug: str = Field(description="Phần path sau /in/, ví dụ nmhoang-dev.")
    profile_url: str = Field(description="URL đầy đủ https://www.linkedin.com/in/<slug>/")
    session_id: str = Field(description="Session id đã dùng để resolve storage state.")


class ProfileSlugResponse(BaseResponse):
    data: Optional[ProfileSlugData] = None


class ProfileSlugSheetCheckData(BaseModel):
    email_found_in_sheet: bool
    webhook_http_status: int
    row_count: int = Field(description="Số dòng dict đã parse từ ``data``.")
    matched_profile_slug: Optional[str] = Field(
        default=None,
        description="Slug đọc từ dòng khớp email (nếu sheet có cột).",
    )


class ProfileSlugSheetCheckResponse(BaseResponse):
    data: Optional[ProfileSlugSheetCheckData] = None


class EnsureProfileSlugData(BaseModel):
    email_found_in_sheet: bool = False
    skipped_playwright: bool = False
    skipped_register_webhook: bool = False
    sheet_check_skipped_no_webhook: bool = False
    profile_slug: Optional[str] = None
    profile_url: Optional[str] = None
    sheet_webhook_http_status: Optional[int] = None
    register_webhook_http_status: Optional[int] = None


class EnsureProfileSlugResponse(BaseResponse):
    data: Optional[EnsureProfileSlugData] = None


class SheetLinkFromN8nData(BaseModel):
    """Kết quả sau khi gọi webhook lấy link sheet."""

    sheet_link: Optional[str] = None
    http_status: int = Field(ge=100, lt=600)
    response_preview: str = ""


class SheetLinkFromN8nResponse(BaseResponse):
    """Envelope cho POST lấy link Google Sheet qua webhook n8n thứ hai."""

    data: Optional[SheetLinkFromN8nData] = None


class FilterDataResponse(BaseResponse):
    """``data`` = mảng các lần cào (phiên mới nhất trước); mỗi phần tử có ``posts``."""

    data: Optional[list[dict[str, Any]]] = None


class GetAllPostsResponse(BaseResponse):
    """``data`` = cùng cấu trúc ``FilterDataResponse`` — chỉ các phiên và bài trong phiên."""

    data: Optional[list[dict[str, Any]]] = None


class LinkedinSheetTopPostsData(BaseModel):
    """Đọc từ Google Sheet tab top_posts."""

    headers: list[str]
    rows: list[dict[str, Any]]
    row_count: int


class LinkedinSheetTopPostsResponse(BaseResponse):
    data: Optional[LinkedinSheetTopPostsData] = None


class LinkedinSheetFilterPostsResponse(BaseResponse):
    data: Optional[LinkedinSheetTopPostsData] = None


class LinkedinSheetGroupsData(BaseModel):
    rows: list[dict[str, Any]]
    row_count: int


class LinkedinSheetGroupsResponse(BaseResponse):
    data: Optional[LinkedinSheetGroupsData] = None


class LinkedinAppStatsData(BaseModel):
    total_comments: int = 0
    total_interactions: int = 0
    total_posts_crawled: int = 0


class LinkedinAppStatsResponse(BaseResponse):
    data: Optional[LinkedinAppStatsData] = None


class LinkedinAppCrawlGroupResult(BaseModel):
    group_url: str
    success: bool
    message: str
    posts_appended: int = 0


class LinkedinAppCrawlBatchData(BaseModel):
    results: list[LinkedinAppCrawlGroupResult]
    spreadsheet_id: str


class LinkedinAppCrawlBatchResponse(BaseResponse):
    data: Optional[LinkedinAppCrawlBatchData] = None


class PostReactionData(BaseModel):
    """Kết quả POST /linkedin/post/react."""

    model_config = ConfigDict(populate_by_name=True)

    reaction: str
    row_number: int
    Email_crawl: str
    ID_session_crawl: str
    post_url: str
    final_url: str = ""
    resolved_playwright_session_id: str = ""
    webhook_called: bool = False
    webhook_http_status: Optional[int] = None
    webhook_response_preview: Optional[str] = None
    playwright_skipped: bool = False
    synced_row_count: int = 0
    webhook_sync_success_count: int = 0


class PostReactionResponse(BaseResponse):
    data: Optional[PostReactionData] = None


class PostCommentData(BaseModel):
    """Kết quả POST /linkedin/post/comment."""

    model_config = ConfigDict(populate_by_name=True)

    comment_text: str
    app_comments: list[dict[str, Any]]
    row_number: int
    Email_crawl: str
    ID_session_crawl: str
    post_url: str
    final_url: str = ""
    resolved_playwright_session_id: str = ""
    webhook_called: bool = False
    webhook_http_status: Optional[int] = None
    webhook_response_preview: Optional[str] = None
    synced_row_count: int = 0
    webhook_sync_success_count: int = 0


class PostCommentResponse(BaseResponse):
    data: Optional[PostCommentData] = None


class PostCommentDeleteData(BaseModel):
    """Kết quả POST /linkedin/post/comment/delete."""

    model_config = ConfigDict(populate_by_name=True)

    comment_text: str
    row_number: int
    Email_crawl: str
    ID_session_crawl: str
    post_url: str
    final_url: str = ""
    resolved_playwright_session_id: str = ""
    webhook_called: bool = False
    webhook_http_status: Optional[int] = None
    webhook_response_preview: Optional[str] = None
    synced_row_count: int = 0
    webhook_sync_success_count: int = 0


class PostCommentDeleteResponse(BaseResponse):
    data: Optional[PostCommentDeleteData] = None


class PostCommentEditData(BaseModel):
    """Kết quả POST /linkedin/post/comment/edit."""

    model_config = ConfigDict(populate_by_name=True)

    old_comment_text: str
    new_comment_text: str
    row_number: int
    Email_crawl: str
    ID_session_crawl: str
    post_url: str
    final_url: str = ""
    resolved_playwright_session_id: str = ""
    webhook_called: bool = False
    webhook_http_status: Optional[int] = None
    webhook_response_preview: Optional[str] = None
    synced_row_count: int = 0
    webhook_sync_success_count: int = 0


class PostCommentEditResponse(BaseResponse):
    data: Optional[PostCommentEditData] = None


class SyncPostProgressData(BaseModel):
    """Kết quả POST /linkedin/post/sync-progress."""

    model_config = ConfigDict(populate_by_name=True)

    post_url: str
    reaction: Optional[str] = None
    comments: list[dict[str, Any]] = []
    total_reactions: int = 0
    total_comments: int = 0
    row_number: Optional[int] = None
    webhook_called: bool = False
    webhook_http_status: Optional[int] = None
    webhook_response_preview: Optional[str] = None


class SyncPostProgressResponse(BaseResponse):
    data: Optional[SyncPostProgressData] = None


class SyncAllProgressData(BaseModel):
    """Kết quả POST /linkedin/sync-all-progress."""

    posts_attempted: int
    posts_succeeded: int
    details: list[SyncPostProgressData]


class SyncAllProgressResponse(BaseResponse):
    data: Optional[SyncAllProgressData] = None


class CheckPermissionData(BaseModel):
    permission: bool = False


class CheckPermissionResponse(BaseResponse):
    data: Optional[CheckPermissionData] = None


class KpiMemberData(BaseModel):
    email: str
    role: str = "member"
    profile_slug: Optional[str] = None
    email_leader: Optional[str] = None
    kpi: list[dict[str, Any]] = []


class GetAllKpiResponse(BaseResponse):
    total: int = 0
    data: list[KpiMemberData] = []


class GetKpiByEmailResponse(BaseResponse):
    total: int = 0
    data: list[KpiMemberData] = []


class AddMemberResponse(BaseResponse):
    allowAdd: Optional[bool] = None
    code: Optional[str] = None
