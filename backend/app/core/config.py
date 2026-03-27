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

    # Demand Validation (Phase 1 Enhancement)
    enable_demand_validation: bool = True
    demand_validation_min_search_volume: int = 500
    demand_validation_use_helium10: bool = False
    demand_validation_helium10_api_key: str = ""
    demand_validation_cache_ttl_seconds: int = 86400  # 24 hours

    # Keyword Generation (Phase 3 Enhancement)
    enable_keyword_generation: bool = True
    keyword_generation_categories: list[str] = Field(
        default_factory=lambda: ["electronics", "fashion", "home", "beauty", "sports"]
    )
    keyword_generation_region: str = "US"
    keyword_generation_limit_per_category: int = 50
    keyword_generation_min_trend_score: int = 20
    keyword_generation_cache_ttl_seconds: int = 86400  # 24 hours
    keyword_generation_auto_trigger_selection: bool = False  # Auto-trigger product selection

    # Seasonal Calendar (Phase 4 Enhancement)
    enable_seasonal_boost: bool = True
    seasonal_calendar_lookahead_days: int = 90

    # Product Selection Demand Discovery (Phase 7 Refactor)
    product_selection_require_demand_discovery: bool = True
    product_selection_allow_validated_seed_fallback: bool = True
    product_selection_enable_runtime_keyword_generation: bool = True
    product_selection_adapter_legacy_seed_mode: bool = False

    # Auto Action Engine (2026-03-27)
    enable_auto_actions: bool = True

    # Auto Publish Rules
    auto_publish_require_approval_first_time: bool = True
    auto_publish_require_approval_high_risk: bool = True
    auto_publish_require_approval_price_above: float = 100.0
    auto_publish_require_approval_margin_below: float = 0.25
    auto_publish_auto_execute_score_above: float = 75.0
    auto_publish_auto_execute_risk_below: int = 30
    auto_publish_auto_execute_margin_above: float = 0.35

    # Auto Reprice Rules
    auto_reprice_enable: bool = True
    auto_reprice_target_roi: float = 0.30  # 30% ROI target
    auto_reprice_low_roi_threshold: float = 0.24  # 80% of target
    auto_reprice_high_roi_threshold: float = 0.36  # 120% of target
    auto_reprice_decrease_percentage: float = 0.08  # Decrease by 8% (midpoint of 5-10%)
    auto_reprice_increase_percentage: float = 0.04  # Increase by 4% (midpoint of 3-5%)
    auto_reprice_max_change_percentage: float = 0.10  # Max 10% change requires approval
    auto_reprice_lookback_days: int = 7

    # Auto Pause Rules
    auto_pause_enable: bool = True
    auto_pause_roi_threshold: float = 0.10  # Pause if ROI < 10%
    auto_pause_lookback_days: int = 7
    auto_pause_min_data_points: int = 7  # Need at least 7 days of data

    # Auto Asset Switch Rules
    auto_asset_switch_enable: bool = True
    auto_asset_switch_ctr_threshold: float = 0.80  # Switch if CTR < 80% of platform average
    auto_asset_switch_lookback_days: int = 7

    # Platform API Configuration
    temu_api_base_url: str = "https://api-sg.temu.com"
    temu_api_timeout: int = 30
    amazon_sp_api_base_url: str = "https://sellingpartnerapi-na.amazon.com"
    amazon_sp_api_timeout: int = 30
    amazon_sp_api_refresh_token: str = ""
    amazon_sp_api_client_id: str = ""
    amazon_sp_api_client_secret: str = ""
    aliexpress_api_base_url: str = "https://api-sg.aliexpress.com/sync"
    aliexpress_api_timeout: int = 30
    aliexpress_api_app_key: str = ""
    aliexpress_api_app_secret: str = ""
    platform_api_max_retries: int = 3  # Retry count for platform API calls

    # RPA Configuration
    rpa_enable: bool = True
    rpa_headless: bool = True
    rpa_timeout: int = 300000  # 5 minutes
    rpa_max_retries: int = 3
    rpa_captcha_service: str = "2captcha"  # or "manual"
    rpa_captcha_api_key: str = ""
    temu_rpa_enabled: bool = False
    temu_rpa_login_url: str = ""
    temu_rpa_publish_url: str = ""
    temu_rpa_username: str = ""
    temu_rpa_password: str = ""
    rpa_manual_intervention_on_challenge: bool = True

@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
