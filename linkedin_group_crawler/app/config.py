"""Application settings and environment loading."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv
import os


BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _parse_csv(value: str | None, default: tuple[str, ...]) -> list[str]:
    """Parse a comma-separated env var into a list of non-empty strings."""

    if value is None:
        return list(default)
    items = [item.strip() for item in value.split(",")]
    return [item for item in items if item]


DEFAULT_WEBHOOK_TIMEOUT_SEC = 300
DEFAULT_START_WEBHOOK_TIMEOUT_SEC = 3600


def _n8n_get_sheet_link_webhook_url_from_env() -> str:
    """URL webhook thứ 2: n8n trả về link Google Sheet (key do user đặt trong .env)."""

    return (os.getenv("N8n_WEBHOOK_GET_LINK") or os.getenv("N8N_WEBHOOK_GET_LINK") or "").strip()


def _n8n_webhook_get_post_crawled_from_env() -> str:
    return (os.getenv("N8N_WEBHOOK_GET_POST_CRAWLED") or "").strip()


def _n8n_webhook_get_url_group_crawled_from_env() -> str:
    return (os.getenv("N8N_WEBHOOK_GET_URL_GROUP_CRAWLED") or "").strip()


def _n8n_webhook_get_result_crawl_by_id_from_env() -> str:
    """Alias: N8N_WEBHOOK_GET_RESULT_CRAWL_BY_ID (chữ N8N hoa thường)."""

    return (
        os.getenv("N8n_WEBHOOK_GET_RESULT_CRAWL_BY_ID")
        or os.getenv("N8N_WEBHOOK_GET_RESULT_CRAWL_BY_ID")
        or ""
    ).strip()


def _n8n_webhook_filter_data_from_env() -> str:
    """URL webhook for filtering data by email and date."""

    return (os.getenv("N8N_WEBHOOK_FILTER_DATA") or "").strip()


def _n8n_webhook_get_all_posts_from_env() -> str:
    """URL webhook for fetching all posts."""

    return (os.getenv("N8N_WEBHOOK_GET_ALL_POSTS") or "").strip()


def _n8n_webhook_start_from_env() -> str:
    """Webhook nhận ``email``, ``password``, ``force_relogin`` để kích hoạt workflow (POST /start)."""

    return (os.getenv("N8N_WEBHOOK_START") or "").strip()


def _n8n_webhook_get_group_from_env() -> str:
    return (os.getenv("N8N_WEBHOOK_GET_GROUP") or "").strip()


def _n8n_webhook_add_group_from_env() -> str:
    return (os.getenv("N8N_WEBHOOK_ADD_GROUP") or "").strip()


def _n8n_webhook_remove_group_from_env() -> str:
    return (os.getenv("N8N_WEBHOOK_REMOVE_GROUP") or "").strip()


def _n8n_webhook_update_group_from_env() -> str:
    return (os.getenv("N8N_WEBHOOK_UPDATE_GROUP") or "").strip()


def _n8n_webhook_add_list_group_from_env() -> str:
    """Ưu tiên key mới; fallback key cũ để tương thích."""

    return (
        os.getenv("N8N_WEBHOOK_ADD_LIST_GROUP")
        or os.getenv("N8N_WEBHOOK_BULK_IMPORT_GROUPS")
        or ""
    ).strip()


def _n8n_webhook_add_list_group_timeout_sec_from_env() -> float:
    """Ưu tiên timeout key mới; fallback key cũ; mặc định 300s."""

    raw = (
        os.getenv("N8N_WEBHOOK_ADD_LIST_GROUP_TIMEOUT_SEC")
        or os.getenv("N8N_WEBHOOK_BULK_IMPORT_GROUPS_TIMEOUT_SEC")
        or "300"
    )
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 300.0


def _n8n_webhook_get_profile_slugs_from_env() -> str:
    """Webhook trả JSON có ``total`` + ``data`` (mảng dòng sheet chứa email/slug)."""

    return (os.getenv("N8N_WEBHOOK_GET_PROFILE_SLUGS") or "").strip()


def _n8n_webhook_get_profile_slugs_timeout_sec_from_env() -> float:
    raw = os.getenv("N8N_WEBHOOK_GET_PROFILE_SLUGS_TIMEOUT_SEC") or "300"
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 300.0


def _n8n_webhook_add_profile_slug_from_env() -> str:
    """Webhook ghi slug mới khi email chưa có trong sheet."""

    return (os.getenv("N8N_WEBHOOK_ADD_PROFILE_SLUG") or "").strip()


def _n8n_webhook_reaction_url_from_env() -> str:
    """Webhook sau reaction Playwright — ưu tiên ``N8N_WEBHOOK_REACTION``, fallback ``N8N_WEBHOOK_POST_REACTION``."""

    return (
        (os.getenv("N8N_WEBHOOK_REACTION") or "").strip()
        or (os.getenv("N8N_WEBHOOK_POST_REACTION") or "").strip()
    )


def _n8n_webhook_comment_url_from_env() -> str:
    """Webhook sau comment Playwright — ``N8N_WEBHOOK_COMMENT`` hoặc ``N8N_WEBHOOK_POST_COMMENT``."""

    return (
        (os.getenv("N8N_WEBHOOK_COMMENT") or "").strip()
        or (os.getenv("N8N_WEBHOOK_POST_COMMENT") or "").strip()
    )


def _n8n_webhook_assign_kpi_from_env() -> str:
    """Webhook gán KPI cho member — leader gọi endpoint /kpi/assign."""

    return (os.getenv("N8N_WEBHOOK_ASSIGN_KPI") or "").strip()


def _n8n_webhook_check_permission_from_env() -> str:
    """Webhook kiểm tra quyền leader/member — /auth/check-permission."""

    return (os.getenv("N8N_CHECK_PERMISSION") or "").strip()


def _n8n_webhook_get_all_kpi_from_env() -> str:
    """Webhook lấy toàn bộ KPI cho leader — /kpi/get-all."""
    return (os.getenv("N8N_WEBHOOK_GET_ALL_KPI") or "").strip()


def _n8n_webhook_get_kpi_by_email_from_env() -> str:
    """Webhook lấy KPI cho member — /kpi/get-by-email."""
    return (os.getenv("N8N_WEBHOOK_GET_KPI_BY_EMAIL") or "").strip()


def _n8n_webhook_add_member_from_env() -> str:
    """Webhook thêm member — /team/add-member."""
    return (os.getenv("N8N_WEBHOOK_ADD_MEMBER") or "").strip()


def _leader_code_from_env() -> str:
    """Mã code để xác nhận vai trò Leader."""
    return (os.getenv("LEADER_CODE") or "8888").strip()


def _n8n_webhook_add_profile_slug_timeout_sec_from_env() -> float:
    raw = os.getenv("N8N_WEBHOOK_ADD_PROFILE_SLUG_TIMEOUT_SEC") or "300"
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 300.0


def _google_service_account_json_from_env() -> Path:
    """Đường dẫn file JSON service account (tương đối BASE_DIR hoặc absolute)."""

    raw = (os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON") or "").strip()
    if not raw:
        raw = "storage/permission/crawllinkedinapp-2e203d199c52.json"
    path = Path(raw)
    if not path.is_absolute():
        path = BASE_DIR / path
    return path


def _google_spreadsheet_id_from_env() -> str:
    return (
        os.getenv("GOOGLE_SPREADSHEET_ID") or "1rfep85y5_97gnm2uIarsc6yVQIkZJYK4ALuPgzM939I"
    ).strip()


def _google_sheet_group_urls_tab_from_env() -> str:
    """Tên tab sheet chứa URL nhóm; để trống để service tự chọn tab (ngoài ``top_posts``)."""

    return (os.getenv("GOOGLE_SHEET_GROUP_URLS_TAB") or "").strip()


@dataclass
class Settings:
    """Typed settings loaded from environment variables."""

    headless: bool = _parse_bool(os.getenv("HEADLESS"), default=True)
    # Số browser Chromium song song (mỗi worker thread một browser). VM 8GB: 2–3; 16GB+: 4.
    playwright_pool_size: int = max(
        1,
        min(8, int(os.getenv("PLAYWRIGHT_POOL_SIZE", "3"))),
    )
    # Playwright reaction — VM chậm cần settle dài hơn (ms).
    reaction_menu_hover_settle_ms: int = max(
        400,
        int(os.getenv("REACTION_MENU_HOVER_SETTLE_MS", "1800")),
    )
    reaction_post_goto_settle_ms: int = max(
        1000,
        int(os.getenv("REACTION_POST_GOTO_SETTLE_MS", "3500")),
    )
    reaction_post_click_settle_ms: int = max(
        500,
        int(os.getenv("REACTION_POST_CLICK_SETTLE_MS", "1500")),
    )
    # Sau POST /login — mo session tren moi worker pool (tranh react/comment bi login lan dau moi browser)
    linkedin_session_prime_url: str = (
        os.getenv("LINKEDIN_SESSION_PRIME_URL", "https://www.linkedin.com/feed/").strip()
        or "https://www.linkedin.com/feed/"
    )
    linkedin_session_prime_timeout_ms: int = max(
        30_000,
        int(os.getenv("LINKEDIN_SESSION_PRIME_TIMEOUT_MS", "120000")),
    )
    # Pre-launch Chromium sau khi API listen (nền). false = chỉ khi có request Playwright.
    playwright_warmup_on_startup: bool = _parse_bool(
        os.getenv("PLAYWRIGHT_WARMUP_ON_STARTUP"),
        default=True,
    )
    state_path: Path = BASE_DIR / os.getenv("STATE_PATH", "storage/linkedin_state.json")
    session_storage_dir: Path = BASE_DIR / "storage" / "session"
    default_scroll_times: int = int(os.getenv("DEFAULT_SCROLL_TIMES", "8"))
    default_scroll_delay_ms: int = int(os.getenv("DEFAULT_SCROLL_DELAY_MS", "2000"))
    default_scroll_delay_min_ms: int = int(os.getenv("DEFAULT_SCROLL_DELAY_MIN_MS", "1000"))
    default_scroll_delay_max_ms: int = int(os.getenv("DEFAULT_SCROLL_DELAY_MAX_MS", "2000"))
    default_max_items: int = int(os.getenv("DEFAULT_MAX_ITEMS", "50"))
    api_key: str = os.getenv("API_KEY", "")
    render_api_key: str = os.getenv("RENDER_API_KEY", "")
    render_service_id: str = os.getenv("RENDER_SERVICE_ID", "")
    cors_origins: list[str] | None = None
    host: str = os.getenv("HOST", "0.0.0.0")
    port: int = int(os.getenv("PORT", "8000"))
    raw_data_dir: Path = BASE_DIR / "data" / "raw"
    output_data_dir: Path = BASE_DIR / "data" / "output"
    n8n_webhook_url: str = os.getenv("N8N_WEBHOOK_URL", "")
    n8n_webhook_timeout_sec: float = float(
        os.getenv("N8N_WEBHOOK_TIMEOUT_SEC", str(DEFAULT_WEBHOOK_TIMEOUT_SEC)),
    )
    n8n_webhook_start_timeout_sec: float = float(
        os.getenv("N8N_WEBHOOK_START_TIMEOUT_SEC", str(DEFAULT_START_WEBHOOK_TIMEOUT_SEC)),
    )
    n8n_webhook_get_link_url: str = field(default_factory=_n8n_get_sheet_link_webhook_url_from_env)
    n8n_webhook_get_post_crawled_url: str = field(
        default_factory=_n8n_webhook_get_post_crawled_from_env,
    )
    n8n_webhook_get_url_group_crawled_url: str = field(
        default_factory=_n8n_webhook_get_url_group_crawled_from_env,
    )
    n8n_webhook_get_result_crawl_by_id_url: str = field(
        default_factory=_n8n_webhook_get_result_crawl_by_id_from_env,
    )
    n8n_webhook_filter_data_url: str = field(
        default_factory=_n8n_webhook_filter_data_from_env,
    )
    n8n_webhook_get_all_posts_url: str = field(
        default_factory=_n8n_webhook_get_all_posts_from_env,
    )
    n8n_webhook_start_url: str = field(default_factory=_n8n_webhook_start_from_env)
    n8n_webhook_get_group_url: str = field(default_factory=_n8n_webhook_get_group_from_env)
    n8n_webhook_add_group_url: str = field(default_factory=_n8n_webhook_add_group_from_env)
    n8n_webhook_remove_group_url: str = field(default_factory=_n8n_webhook_remove_group_from_env)
    n8n_webhook_update_group_url: str = field(default_factory=_n8n_webhook_update_group_from_env)
    n8n_webhook_add_list_group_url: str = field(default_factory=_n8n_webhook_add_list_group_from_env)
    n8n_webhook_add_list_group_timeout_sec: float = field(
        default_factory=_n8n_webhook_add_list_group_timeout_sec_from_env,
    )
    n8n_webhook_get_profile_slugs_url: str = field(
        default_factory=_n8n_webhook_get_profile_slugs_from_env,
    )
    n8n_webhook_get_profile_slugs_timeout_sec: float = field(
        default_factory=_n8n_webhook_get_profile_slugs_timeout_sec_from_env,
    )
    n8n_webhook_add_profile_slug_url: str = field(
        default_factory=_n8n_webhook_add_profile_slug_from_env,
    )
    n8n_webhook_add_profile_slug_timeout_sec: float = field(
        default_factory=_n8n_webhook_add_profile_slug_timeout_sec_from_env,
    )
    n8n_webhook_post_reaction_url: str = field(
        default_factory=_n8n_webhook_reaction_url_from_env,
    )
    n8n_webhook_post_comment_url: str = field(
        default_factory=_n8n_webhook_comment_url_from_env,
    )
    n8n_webhook_assign_kpi_url: str = field(
        default_factory=_n8n_webhook_assign_kpi_from_env,
    )
    n8n_webhook_check_permission_url: str = field(
        default_factory=_n8n_webhook_check_permission_from_env,
    )
    n8n_webhook_get_all_kpi_url: str = field(
        default_factory=_n8n_webhook_get_all_kpi_from_env,
    )
    n8n_webhook_get_kpi_by_email_url: str = field(
        default_factory=_n8n_webhook_get_kpi_by_email_from_env,
    )
    n8n_webhook_add_member_url: str = field(
        default_factory=_n8n_webhook_add_member_from_env,
    )
    leader_code: str = field(
        default_factory=_leader_code_from_env,
    )
    google_service_account_json_path: Path = field(
        default_factory=_google_service_account_json_from_env,
    )
    google_spreadsheet_id: str = field(default_factory=_google_spreadsheet_id_from_env)
    google_sheet_top_posts_tab: str = (os.getenv("GOOGLE_SHEET_TOP_POSTS_TAB") or "top_posts").strip()
    google_sheet_group_urls_tab: str = field(
        default_factory=_google_sheet_group_urls_tab_from_env,
    )
    crawl_batch_group_delay_min_sec: float = float(os.getenv("CRAWL_BATCH_GROUP_DELAY_MIN_SEC", "3"))
    crawl_batch_group_delay_max_sec: float = float(os.getenv("CRAWL_BATCH_GROUP_DELAY_MAX_SEC", "12"))

    def __post_init__(self) -> None:
        if self.cors_origins is None:
            self.cors_origins = _parse_csv(
                os.getenv("CORS_ORIGINS"),
                default=("http://localhost:3000", "http://127.0.0.1:3000"),
            )


settings = Settings()
