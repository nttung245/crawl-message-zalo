"""Configuration for the Apartment Agent module."""

from __future__ import annotations

from pydantic_settings import BaseSettings


class ApartmentAgentSettings(BaseSettings):
    """Environment-based configuration for apartment agent pipeline."""

    # GoDaNang Supabase connection
    godanang_supabase_url: str = ""
    godanang_supabase_service_key: str = ""

    # LLM configuration
    llm_api_key: str = ""
    llm_base_url: str = "https://api.openai.com/v1"
    llm_model: str = "gpt-4o-mini"

    # Dedup
    dedup_threshold: int = 85

    # Pipeline tuning
    batch_concurrency: int = 5
    insert_delay_ms: int = 200

    # Auto-trigger after Zalo crawl
    auto_process: bool = False

    # Classifier gate
    classifier_enabled: bool = False

    model_config = {"env_prefix": "", "case_sensitive": False}


settings = ApartmentAgentSettings()


def validate_settings() -> list[str]:
    """Return list of missing required settings. Empty = all good."""
    missing: list[str] = []
    if not settings.godanang_supabase_url:
        missing.append("GODANANG_SUPABASE_URL")
    if not settings.godanang_supabase_service_key:
        missing.append("GODANANG_SUPABASE_SERVICE_KEY")
    if not settings.llm_api_key:
        missing.append("LLM_API_KEY")
    return missing
