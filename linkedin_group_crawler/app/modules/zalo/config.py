from typing import Optional
from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    google_credentials_path: str = Field(
        default="/app/credentials/service_account.json",
        validation_alias=AliasChoices("ZALO_GOOGLE_CREDENTIALS_PATH", "GOOGLE_CREDENTIALS_PATH"),
    )
    default_sheet_id: str = Field(
        default="",
        validation_alias=AliasChoices("ZALO_DEFAULT_SHEET_ID", "DEFAULT_SHEET_ID"),
    )
    cors_origins: str = Field(
        default="http://localhost:3000",
        validation_alias=AliasChoices("ZALO_CORS_ORIGINS", "CORS_ORIGINS"),
    )
    session_ttl_hours: int = Field(
        default=8,
        validation_alias=AliasChoices("ZALO_SESSION_TTL_HOURS", "SESSION_TTL_HOURS"),
    )
    debug_artifacts_dir: str = Field(
        default="artifacts/debug",
        validation_alias=AliasChoices("ZALO_DEBUG_ARTIFACTS_DIR", "DEBUG_ARTIFACTS_DIR"),
    )
    zca_auth_store_dir: str = Field(
        default="artifacts/zca-auth",
        validation_alias=AliasChoices("ZALO_ZCA_AUTH_STORE_DIR", "ZCA_AUTH_STORE_DIR"),
    )
    browser_headless: bool = Field(
        default=True,
        validation_alias=AliasChoices("ZALO_BROWSER_HEADLESS", "BROWSER_HEADLESS"),
    )
    browser_stealth: bool = Field(
        default=True,
        validation_alias=AliasChoices("ZALO_BROWSER_STEALTH", "BROWSER_STEALTH"),
    )
    browser_persistent_profile: bool = Field(
        default=False,
        validation_alias=AliasChoices(
            "ZALO_BROWSER_PERSISTENT_PROFILE",
            "BROWSER_PERSISTENT_PROFILE",
        ),
    )
    browser_user_data_dir: str = Field(
        default="artifacts/chromium-profile",
        validation_alias=AliasChoices("ZALO_BROWSER_USER_DATA_DIR", "BROWSER_USER_DATA_DIR"),
    )
    browser_kill_stale_processes: bool = Field(
        default=True,
        validation_alias=AliasChoices(
            "ZALO_BROWSER_KILL_STALE_PROCESSES",
            "BROWSER_KILL_STALE_PROCESSES",
        ),
    )
    browser_executable_path: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices("ZALO_BROWSER_EXECUTABLE_PATH", "BROWSER_EXECUTABLE_PATH"),
    )
    browser_remote_viewer_url: Optional[str] = Field(
        default=None,
        validation_alias=AliasChoices(
            "ZALO_BROWSER_REMOTE_VIEWER_URL",
            "BROWSER_REMOTE_VIEWER_URL",
        ),
    )
    qr_login_mode: str = Field(
        default="web",
        validation_alias=AliasChoices("ZALO_QR_LOGIN_MODE", "QR_LOGIN_MODE"),
    )
    supabase_url: str = Field(
        default="",
        validation_alias=AliasChoices("SUPABASE_URL", "ZALO_SUPABASE_URL"),
    )
    supabase_service_role_key: str = Field(
        default="",
        validation_alias=AliasChoices("SUPABASE_SERVICE_ROLE_KEY", "ZALO_SUPABASE_SERVICE_ROLE_KEY"),
    )
    supabase_storage_bucket: str = Field(
        default="zalo-assets",
        validation_alias=AliasChoices("SUPABASE_STORAGE_BUCKET", "ZALO_SUPABASE_STORAGE_BUCKET"),
    )
    save_to_supabase: bool = Field(
        default=True,
        validation_alias=AliasChoices("ZALO_SAVE_TO_SUPABASE", "SAVE_TO_SUPABASE"),
    )
    supabase_ssl_verify: bool = Field(
        default=True,
        validation_alias=AliasChoices("ZALO_SUPABASE_SSL_VERIFY", "SUPABASE_SSL_VERIFY"),
    )
    write_google_sheet: bool = Field(
        default=False,
        validation_alias=AliasChoices("ZALO_WRITE_GOOGLE_SHEET", "WRITE_GOOGLE_SHEET"),
    )
    broadcast_delay_seconds: float = Field(
        default=3.0,
        validation_alias=AliasChoices("ZALO_BROADCAST_DELAY_SECONDS", "BROADCAST_DELAY_SECONDS"),
    )
    broadcast_composer_timeout_seconds: int = Field(
        default=60,
        validation_alias=AliasChoices(
            "ZALO_BROADCAST_COMPOSER_TIMEOUT_SECONDS",
            "BROADCAST_COMPOSER_TIMEOUT_SECONDS",
        ),
    )
    asset_retention_days: int = Field(
        default=7,
        validation_alias=AliasChoices("ZALO_ASSET_RETENTION_DAYS", "ASSET_RETENTION_DAYS"),
    )
    asset_cleanup_batch_size: int = Field(
        default=200,
        validation_alias=AliasChoices("ZALO_ASSET_CLEANUP_BATCH_SIZE", "ASSET_CLEANUP_BATCH_SIZE"),
    )
    zca_old_message_interval_ms: int = Field(
        default=60000,
        validation_alias=AliasChoices("ZALO_ZCA_OLD_MESSAGE_INTERVAL_MS", "ZCA_OLD_MESSAGE_INTERVAL_MS"),
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
