"""Database models."""
from datetime import date, datetime
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy import (
    ARRAY,
    DECIMAL,
    JSON,
    Date,
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import (
    AgentRunStatus,
    AssetType,
    CandidateStatus,
    ExperimentStatus,
    FeedbackAction,
    PlatformListingStatus,
    ProductLifecycle,
    ProfitabilityDecision,
    RiskDecision,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.base import Base, TimestampMixin, UpdateTimestampMixin


class StrategyRun(Base, TimestampMixin):
    """Strategy run (discovery job)."""

    __tablename__ = "strategy_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), unique=True, index=True)
    trigger_type: Mapped[TriggerType] = mapped_column(
        SAEnum(TriggerType, native_enum=False), nullable=False
    )
    source_platform: Mapped[SourcePlatform] = mapped_column(
        SAEnum(SourcePlatform, native_enum=False), nullable=False
    )
    region: Mapped[Optional[str]] = mapped_column(String(10))
    category: Mapped[Optional[str]] = mapped_column(String(100))
    keywords: Mapped[Optional[list[str]]] = mapped_column(ARRAY(Text))
    target_languages: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(10)))
    price_min: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    price_max: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    max_candidates: Mapped[int] = mapped_column(Integer, default=10)
    status: Mapped[StrategyRunStatus] = mapped_column(
        SAEnum(StrategyRunStatus, native_enum=False), nullable=False
    )
    requested_by: Mapped[Optional[str]] = mapped_column(String(100))
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    agent_runs: Mapped[list["AgentRun"]] = relationship(back_populates="strategy_run")
    candidates: Mapped[list["CandidateProduct"]] = relationship(back_populates="strategy_run")
    events: Mapped[list["RunEvent"]] = relationship(back_populates="strategy_run")


class AgentRun(Base):
    """Agent execution step."""

    __tablename__ = "agent_runs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    strategy_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("strategy_runs.id"), nullable=False, index=True
    )
    step_name: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_name: Mapped[str] = mapped_column(String(100), nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(
        SAEnum(AgentRunStatus, native_enum=False), nullable=False
    )
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    input_data: Mapped[Optional[dict]] = mapped_column(JSON)
    output_data: Mapped[Optional[dict]] = mapped_column(JSON)
    error_message: Mapped[Optional[str]] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer)

    # Relationships
    strategy_run: Mapped["StrategyRun"] = relationship(back_populates="agent_runs")
    events: Mapped[list["RunEvent"]] = relationship(back_populates="agent_run")


class CandidateProduct(Base, UpdateTimestampMixin):
    """Discovered candidate product."""

    __tablename__ = "candidate_products"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    strategy_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("strategy_runs.id"), nullable=False, index=True
    )
    source_platform: Mapped[SourcePlatform] = mapped_column(
        SAEnum(SourcePlatform, native_enum=False), nullable=False
    )
    source_product_id: Mapped[Optional[str]] = mapped_column(String(255))
    source_url: Mapped[Optional[str]] = mapped_column(Text)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    raw_title: Mapped[Optional[str]] = mapped_column(Text)
    category: Mapped[Optional[str]] = mapped_column(String(100))
    currency: Mapped[Optional[str]] = mapped_column(String(10))
    platform_price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    sales_count: Mapped[Optional[int]] = mapped_column(Integer)
    rating: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(3, 2))
    main_image_url: Mapped[Optional[str]] = mapped_column(Text)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON)
    normalized_attributes: Mapped[Optional[dict]] = mapped_column(JSON)
    status: Mapped[CandidateStatus] = mapped_column(
        SAEnum(CandidateStatus, native_enum=False), nullable=False
    )

    # Phase 1 扩展字段
    internal_sku: Mapped[Optional[str]] = mapped_column(String(50), unique=True, index=True)  # 内部SKU
    lifecycle_status: Mapped[Optional[ProductLifecycle]] = mapped_column(
        SAEnum(ProductLifecycle, native_enum=False), default=ProductLifecycle.DRAFT, index=True
    )  # 生命周期状态

    # Demand discovery metadata (2026-03-28)
    demand_discovery_metadata: Mapped[Optional[dict]] = mapped_column(JSONB)  # discovery_mode, fallback_used, degraded, validated_keywords, rejected_keywords, skipped_reason

    # Relationships
    strategy_run: Mapped["StrategyRun"] = relationship(back_populates="candidates")
    supplier_matches: Mapped[list["SupplierMatch"]] = relationship(back_populates="candidate")
    pricing_assessment: Mapped[Optional["PricingAssessment"]] = relationship(
        back_populates="candidate"
    )
    risk_assessment: Mapped[Optional["RiskAssessment"]] = relationship(back_populates="candidate")
    listing_drafts: Mapped[list["ListingDraft"]] = relationship(back_populates="candidate")

    # Phase 1 新增关系
    content_assets: Mapped[list["ContentAsset"]] = relationship(back_populates="candidate")
    platform_listings: Mapped[list["PlatformListing"]] = relationship(back_populates="candidate")
    experiments: Mapped[list["Experiment"]] = relationship(back_populates="candidate")
    recommendation_feedbacks: Mapped[list["RecommendationFeedback"]] = relationship(
        back_populates="candidate"
    )


class SupplierMatch(Base, TimestampMixin):
    """Matched supplier from 1688 or other sources."""

    __tablename__ = "supplier_matches"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    candidate_product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidate_products.id"), nullable=False, index=True
    )
    supplier_name: Mapped[Optional[str]] = mapped_column(String(255))
    supplier_url: Mapped[Optional[str]] = mapped_column(Text)
    supplier_sku: Mapped[Optional[str]] = mapped_column(String(255))
    supplier_price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    moq: Mapped[Optional[int]] = mapped_column(Integer)
    confidence_score: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(3, 2))
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON)
    selected: Mapped[bool] = mapped_column(default=False)

    # Relationships
    candidate: Mapped["CandidateProduct"] = relationship(back_populates="supplier_matches")


class PricingAssessment(Base, TimestampMixin):
    """Profit calculation and pricing recommendation."""

    __tablename__ = "pricing_assessments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    candidate_product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("candidate_products.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    estimated_shipping_cost: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    platform_commission_rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 4))
    payment_fee_rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 4))
    return_rate_assumption: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 4))
    total_cost: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    estimated_margin: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    margin_percentage: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 2))
    recommended_price: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(10, 2))
    profitability_decision: Mapped[Optional[ProfitabilityDecision]] = mapped_column(
        SAEnum(ProfitabilityDecision, native_enum=False)
    )
    explanation: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    candidate: Mapped["CandidateProduct"] = relationship(back_populates="pricing_assessment")


class RiskAssessment(Base, TimestampMixin):
    """IP infringement and compliance screening."""

    __tablename__ = "risk_assessments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    candidate_product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True),
        ForeignKey("candidate_products.id"),
        nullable=False,
        unique=True,
        index=True,
    )
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    decision: Mapped[RiskDecision] = mapped_column(
        SAEnum(RiskDecision, native_enum=False), nullable=False
    )
    rule_hits: Mapped[Optional[dict]] = mapped_column(JSON)
    llm_notes: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    candidate: Mapped["CandidateProduct"] = relationship(back_populates="risk_assessment")


class ListingDraft(Base, TimestampMixin):
    """Generated multilingual listing copy."""

    __tablename__ = "listing_drafts"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    candidate_product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidate_products.id"), nullable=False, index=True
    )
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    bullets: Mapped[Optional[list]] = mapped_column(JSON)
    description: Mapped[Optional[str]] = mapped_column(Text)
    seo_keywords: Mapped[Optional[list]] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(50))

    # Relationships
    candidate: Mapped["CandidateProduct"] = relationship(back_populates="listing_drafts")


class RunEvent(Base, TimestampMixin):
    """Append-only audit trail."""

    __tablename__ = "run_events"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    strategy_run_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("strategy_runs.id"), nullable=False, index=True
    )
    agent_run_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("agent_runs.id"), index=True
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    event_payload: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    strategy_run: Mapped["StrategyRun"] = relationship(back_populates="events")
    agent_run: Mapped[Optional["AgentRun"]] = relationship(back_populates="events")


class RecommendationFeedback(Base, TimestampMixin):
    """User feedback on recommendation decisions."""

    __tablename__ = "recommendation_feedback"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    candidate_product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidate_products.id"), nullable=False, index=True
    )
    action: Mapped[FeedbackAction] = mapped_column(
        SAEnum(FeedbackAction, native_enum=False), nullable=False, index=True
    )
    comment: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON)

    # Relationships
    candidate: Mapped["CandidateProduct"] = relationship(back_populates="recommendation_feedbacks")


# ============================================================================
# Phase 1 最小中台: 内容资产管理 & 平台发布
# ============================================================================


class ContentAsset(Base, UpdateTimestampMixin):
    """Content asset (images, videos, etc.) for products.

    核心功能:
    - 存储生成的图片/视频等内容资产
    - 支持多风格、多平台、多地区标签
    - AI质量评分和人工审核
    - 版本控制和使用统计
    """

    __tablename__ = "content_assets"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    candidate_product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidate_products.id"), nullable=False, index=True
    )

    # 资产类型
    asset_type: Mapped[AssetType] = mapped_column(
        SAEnum(AssetType, native_enum=False), nullable=False
    )

    # 标签系统（用于筛选和匹配）
    style_tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(50)))  # ["minimalist", "luxury", "cute"]
    platform_tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(50)))  # ["temu", "amazon", "ozon"]
    region_tags: Mapped[Optional[list[str]]] = mapped_column(ARRAY(String(10)))  # ["us", "eu", "ru"]
    variant_group: Mapped[Optional[str]] = mapped_column(String(100), index=True)

    # 文件信息
    file_url: Mapped[str] = mapped_column(Text, nullable=False)  # MinIO URL
    file_size: Mapped[Optional[int]] = mapped_column(Integer)  # bytes
    dimensions: Mapped[Optional[str]] = mapped_column(String(20))  # "1024x1024"
    format: Mapped[Optional[str]] = mapped_column(String(10))  # "png", "jpg", "mp4"

    # 质量评分
    ai_quality_score: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(3, 1))  # 0.0-10.0
    human_approved: Mapped[bool] = mapped_column(default=False)
    approval_notes: Mapped[Optional[str]] = mapped_column(Text)

    # 使用统计
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    conversion_rate: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(5, 4))  # 转化率（后续回填）

    # 归档状态（A/B 测试输家素材）
    archived: Mapped[bool] = mapped_column(default=False)

    # 版本控制
    version: Mapped[int] = mapped_column(Integer, default=1)
    parent_asset_id: Mapped[Optional[UUID]] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("content_assets.id")
    )  # 衍生自哪个资产

    # 生成参数（用于复现）
    generation_params: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    candidate: Mapped["CandidateProduct"] = relationship(back_populates="content_assets")
    parent_asset: Mapped[Optional["ContentAsset"]] = relationship(
        remote_side=[id], back_populates="derived_assets"
    )
    derived_assets: Mapped[list["ContentAsset"]] = relationship(
        back_populates="parent_asset", remote_side=[parent_asset_id]
    )
    platform_listings: Mapped[list["PlatformListing"]] = relationship(
        secondary="listing_asset_associations", back_populates="assets"
    )
    performance_daily: Mapped[list["AssetPerformanceDaily"]] = relationship(
        back_populates="asset", passive_deletes=True
    )


class PlatformListing(Base, UpdateTimestampMixin):
    """Platform listing mapping (商品在各平台的上架记录).

    核心功能:
    - 记录商品在各平台的上架信息
    - 跟踪库存、价格、状态
    - 支持多地区
    - 同步日志
    """

    __tablename__ = "platform_listings"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    candidate_product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidate_products.id"), nullable=False, index=True
    )

    # 平台信息
    platform: Mapped[TargetPlatform] = mapped_column(
        SAEnum(TargetPlatform, native_enum=False), nullable=False, index=True
    )
    region: Mapped[str] = mapped_column(String(10), nullable=False, index=True)  # "us", "uk", "de"

    # 平台商品ID
    platform_listing_id: Mapped[Optional[str]] = mapped_column(String(100), index=True)  # Temu SKU, Amazon ASIN
    platform_url: Mapped[Optional[str]] = mapped_column(Text)
    idempotency_key: Mapped[Optional[str]] = mapped_column(String(255), index=True)

    # 价格和库存
    price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)  # "USD", "EUR", "RUB"
    inventory: Mapped[int] = mapped_column(Integer, default=0)

    # 状态
    status: Mapped[PlatformListingStatus] = mapped_column(
        SAEnum(PlatformListingStatus, native_enum=False), nullable=False, default=PlatformListingStatus.PENDING
    )

    # 平台特定数据
    platform_data: Mapped[Optional[dict]] = mapped_column(JSON)  # 平台特定字段

    # 同步信息
    last_synced_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    sync_error: Mapped[Optional[str]] = mapped_column(Text)

    # 销售数据（后续回填）
    total_sales: Mapped[int] = mapped_column(Integer, default=0)
    total_revenue: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))

    # Auto Action Engine (2026-03-27)
    approval_required: Mapped[bool] = mapped_column(default=False, index=True)
    approval_reason: Mapped[Optional[str]] = mapped_column(Text)
    auto_action_metadata: Mapped[Optional[dict]] = mapped_column(JSON)  # recommendation_score, risk_score, etc.
    approved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    approved_by: Mapped[Optional[str]] = mapped_column(String(100))
    rejected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    rejected_by: Mapped[Optional[str]] = mapped_column(String(100))
    rejection_reason: Mapped[Optional[str]] = mapped_column(Text)
    last_auto_action_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Relationships
    candidate: Mapped["CandidateProduct"] = relationship(back_populates="platform_listings")
    assets: Mapped[list["ContentAsset"]] = relationship(
        secondary="listing_asset_associations", back_populates="platform_listings"
    )
    inventory_logs: Mapped[list["InventorySyncLog"]] = relationship(back_populates="listing")
    price_history: Mapped[list["PriceHistory"]] = relationship(back_populates="listing")
    performance_daily: Mapped[list["ListingPerformanceDaily"]] = relationship(
        back_populates="listing", cascade="all, delete-orphan", passive_deletes=True
    )
    asset_performance_daily: Mapped[list["AssetPerformanceDaily"]] = relationship(
        back_populates="listing", passive_deletes=True
    )


class ListingPerformanceDaily(Base, UpdateTimestampMixin):
    """Daily performance facts for a platform listing."""

    __tablename__ = "listing_performance_daily"
    __table_args__ = (
        Index(
            "uq_listing_performance_daily_listing_date",
            "listing_id",
            "metric_date",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    listing_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_listings.id"), nullable=False, index=True
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    units_sold: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))
    ad_spend: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))
    returns_count: Mapped[int] = mapped_column(Integer, default=0)
    refund_amount: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    listing: Mapped["PlatformListing"] = relationship(back_populates="performance_daily")


class AssetPerformanceDaily(Base, UpdateTimestampMixin):
    """Daily performance facts for a content asset within a listing context."""

    __tablename__ = "asset_performance_daily"
    __table_args__ = (
        Index(
            "uq_asset_performance_daily_asset_listing_date",
            "asset_id",
            "listing_id",
            "metric_date",
            unique=True,
        ),
    )

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("content_assets.id"), nullable=False, index=True
    )
    listing_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_listings.id"), nullable=False, index=True
    )
    metric_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    impressions: Mapped[int] = mapped_column(Integer, default=0)
    clicks: Mapped[int] = mapped_column(Integer, default=0)
    orders: Mapped[int] = mapped_column(Integer, default=0)
    units_sold: Mapped[int] = mapped_column(Integer, default=0)
    revenue: Mapped[Optional[Decimal]] = mapped_column(DECIMAL(12, 2))
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    raw_payload: Mapped[Optional[dict]] = mapped_column(JSON)

    # Relationships
    asset: Mapped["ContentAsset"] = relationship(back_populates="performance_daily")
    listing: Mapped["PlatformListing"] = relationship(back_populates="asset_performance_daily")


class Experiment(Base, UpdateTimestampMixin):
    """A/B test experiment for content asset variants.

    Tracks experiments comparing multiple content asset variants (identified by variant_group)
    to determine which performs best based on a chosen metric (e.g., CTR).
    """

    __tablename__ = "experiments"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    candidate_product_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("candidate_products.id"), nullable=False, index=True
    )

    # Experiment metadata
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    status: Mapped[ExperimentStatus] = mapped_column(
        SAEnum(ExperimentStatus, native_enum=False), nullable=False, default=ExperimentStatus.DRAFT
    )

    # Optional filters
    target_platform: Mapped[Optional[TargetPlatform]] = mapped_column(
        SAEnum(TargetPlatform, native_enum=False)
    )
    region: Mapped[Optional[str]] = mapped_column(String(10))

    # Experiment configuration
    metric_goal: Mapped[str] = mapped_column(String(50), nullable=False, default="ctr")  # "ctr", "cvr", "roas"

    # Winner selection
    winner_variant_group: Mapped[Optional[str]] = mapped_column(String(100))
    winner_selected_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))

    # Notes
    notes: Mapped[Optional[str]] = mapped_column(Text)
    metadata_: Mapped[Optional[dict]] = mapped_column("metadata", JSON)

    # Relationships
    candidate: Mapped["CandidateProduct"] = relationship(back_populates="experiments")


class ListingAssetAssociation(Base):
    """Many-to-many association between listings and assets."""

    __tablename__ = "listing_asset_associations"

    listing_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_listings.id"), primary_key=True
    )
    asset_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("content_assets.id"), primary_key=True
    )
    display_order: Mapped[int] = mapped_column(Integer, default=0)  # 显示顺序
    is_main: Mapped[bool] = mapped_column(default=False)  # 是否为主图


class InventorySyncLog(Base):
    """Inventory synchronization log."""

    __tablename__ = "inventory_sync_logs"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    listing_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_listings.id"), nullable=False, index=True
    )

    old_inventory: Mapped[int] = mapped_column(Integer, nullable=False)
    new_inventory: Mapped[int] = mapped_column(Integer, nullable=False)

    sync_status: Mapped[str] = mapped_column(String(20), nullable=False)  # "success", "failed"
    error_message: Mapped[Optional[str]] = mapped_column(Text)

    synced_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    listing: Mapped["PlatformListing"] = relationship(back_populates="inventory_logs")


class PriceHistory(Base):
    """Price change history."""

    __tablename__ = "price_history"

    id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), primary_key=True)
    listing_id: Mapped[UUID] = mapped_column(
        PGUUID(as_uuid=True), ForeignKey("platform_listings.id"), nullable=False, index=True
    )

    old_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)
    new_price: Mapped[Decimal] = mapped_column(DECIMAL(10, 2), nullable=False)

    reason: Mapped[Optional[str]] = mapped_column(String(200))  # "exchange_rate", "promotion", "competitor"
    changed_by: Mapped[Optional[str]] = mapped_column(String(100))  # "agent", "manual", "system"

    changed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # Relationships
    listing: Mapped["PlatformListing"] = relationship(back_populates="price_history")
