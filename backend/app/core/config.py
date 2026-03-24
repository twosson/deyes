"""Application configuration."""
from functools import lru_cache
from typing import Literal

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql://deyes:deyes_password@localhost:5432/deyes"

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # SGLang
    sglang_base_url: str = "http://localhost:30000/v1"
    sglang_model: str = "Qwen/Qwen3.5-35B-A3B"
    sglang_timeout: int = 120

    # MinIO (optional)
    minio_endpoint: str = "localhost:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket_name: str = "deyes-assets"
    minio_secure: bool = False

    # ComfyUI
    comfyui_base_url: str = "http://localhost:8188"
    comfyui_timeout: int = 300  # 5 minutes for image generation

    # Qdrant (optional)
    qdrant_url: str = "http://localhost:6333"

    # Application
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    environment: Literal["development", "staging", "production"] = "development"
    api_prefix: str = "/api/v1"

    # Scraping
    use_real_scrapers: bool = True
    temu_base_url: str = "https://www.temu.com"
    scraper_timeout: int = 30000
    scraper_headless: bool = True
    scraper_max_retries: int = 3
    scraper_max_browsers: int = 3
    scraper_max_contexts_per_browser: int = 5
    scraper_browser_failure_threshold: int = 3
    scraper_browser_cleanup_interval_seconds: int = 60

    # TMAPI 1688 API (primary)
    tmapi_api_token: str = Field(
        default="",
        validation_alias=AliasChoices("TMAPI_API_TOKEN", "TMAPI_TOKEN"),
    )
    tmapi_base_url: str = Field(
        default="https://api.tmapi.io",
        validation_alias=AliasChoices("TMAPI_BASE_URL"),
    )
    tmapi_timeout: int = Field(
        default=30,
        validation_alias=AliasChoices("TMAPI_TIMEOUT"),
    )
    tmapi_max_retries: int = Field(
        default=3,
        validation_alias=AliasChoices("TMAPI_MAX_RETRIES"),
    )

    # 1688 discovery tuning knobs
    tmapi_1688_cold_start_seeds: list[str] = Field(
        default_factory=lambda: ["热销", "新品", "爆款", "推荐"]
    )
    tmapi_1688_search_language: str = "en"
    tmapi_1688_suggest_limit_per_seed: int = 3
    tmapi_1688_recall_multiplier: int = 3
    tmapi_1688_detail_top_k: int = 8
    tmapi_1688_enable_shipping: bool = True
    tmapi_1688_enable_ratings: bool = True
    tmapi_1688_enable_shop_info: bool = True
    tmapi_1688_enable_llm_query_expansion: bool = False
    tmapi_1688_llm_query_limit: int = 4
    tmapi_1688_seasonal_seed_limit: int = 1
    tmapi_1688_min_seed_count: int = 2
    tmapi_1688_llm_expansion_min_recall_threshold: int = 6
    tmapi_1688_llm_expansion_min_quality_threshold: float = 28.0
    tmapi_1688_region_province_map: dict[str, str] = Field(default_factory=dict)
    tmapi_1688_enable_diversification: bool = True
    tmapi_1688_diversification_shop_cap: int = 2
    tmapi_1688_diversification_seed_min_quota: int = 1
    tmapi_1688_diversification_seed_quota_max_lanes: int = 3
    tmapi_1688_diversification_enable_image_dedupe: bool = True
    tmapi_1688_diversification_enable_title_dedupe: bool = True
    tmapi_1688_diversification_relaxation_passes: int = 2
    tmapi_1688_supplier_competition_set_size: int = 5
    tmapi_1688_supplier_similarity_threshold: float = 0.5
    tmapi_1688_enable_review_risk_analysis: bool = True
    tmapi_1688_enable_shop_intelligence: bool = True
    tmapi_1688_review_risk_penalty_cap: float = 8.0
    tmapi_1688_shop_focus_bonus_cap: float = 6.0
    tmapi_1688_enable_historical_feedback: bool = True
    tmapi_1688_historical_feedback_lookback_days: int = 90
    tmapi_1688_historical_feedback_prior_cap: float = 5.0

    # Temu Seller API
    temu_app_key: str = ""
    temu_app_secret: str = ""
    temu_use_mock: bool = True  # Use mock adapter in development

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
