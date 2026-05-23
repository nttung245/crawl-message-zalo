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
    browser_executable_path: str | None = Field(
        default=None,
        validation_alias=AliasChoices("ZALO_BROWSER_EXECUTABLE_PATH", "BROWSER_EXECUTABLE_PATH"),
    )
    browser_remote_viewer_url: str | None = Field(
        default=None,
        validation_alias=AliasChoices(
            "ZALO_BROWSER_REMOTE_VIEWER_URL",
            "BROWSER_REMOTE_VIEWER_URL",
        ),
    )

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
