"""Application enums."""
from enum import Enum


class StrategyRunStatus(str, Enum):
    """Strategy run status."""
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class AgentRunStatus(str, Enum):
    """Agent run status."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class CandidateStatus(str, Enum):
    """Candidate product status."""
    DISCOVERED = "discovered"
    PRICED = "priced"
    RISK_ASSESSED = "risk_assessed"
    COPY_GENERATED = "copy_generated"
    REJECTED = "rejected"


class ProfitabilityDecision(str, Enum):
    """Profitability decision."""
    PROFITABLE = "profitable"
    MARGINAL = "marginal"
    UNPROFITABLE = "unprofitable"


class RiskDecision(str, Enum):
    """Risk assessment decision."""
    PASS = "pass"
    REVIEW = "review"
    REJECT = "reject"


class TriggerType(str, Enum):
    """Strategy run trigger type."""
    MANUAL = "manual"
    SCHEDULED = "scheduled"
    API = "api"


class SourcePlatform(str, Enum):
    """Source platform for product discovery."""
    TEMU = "temu"
    ALIBABA_1688 = "alibaba_1688"
    ALIEXPRESS = "aliexpress"
    AMAZON = "amazon"
    OZON = "ozon"
    RAKUTEN = "rakuten"
    MERCADO_LIBRE = "mercado_libre"


class ProductLifecycle(str, Enum):
    """Product lifecycle status."""
    DRAFT = "draft"  # 草稿
    PENDING_REVIEW = "pending_review"  # 待审核
    APPROVED = "approved"  # 已审核
    CONTENT_GENERATING = "content_generating"  # 内容生成中
    READY_TO_PUBLISH = "ready_to_publish"  # 准备发布
    PUBLISHED = "published"  # 已发布
    ARCHIVED = "archived"  # 已归档


class AssetType(str, Enum):
    """Content asset type."""
    MAIN_IMAGE = "main_image"  # 主图
    DETAIL_IMAGE = "detail_image"  # 详情页
    VIDEO = "video"  # 视频
    THREE_D_MODEL = "3d_model"  # 3D模型
    WHITE_BACKGROUND = "white_background"  # 白底图
    LIFESTYLE = "lifestyle"  # 场景图


class PlatformListingStatus(str, Enum):
    """Platform listing status."""
    DRAFT = "draft"  # 草稿
    PENDING_APPROVAL = "pending_approval"  # 待审批
    APPROVED = "approved"  # 已审批
    PENDING = "pending"  # 待上架
    PUBLISHING = "publishing"  # 上架中
    ACTIVE = "active"  # 已上架
    PAUSED = "paused"  # 已暂停
    OUT_OF_STOCK = "out_of_stock"  # 缺货
    REJECTED = "rejected"  # 被拒绝
    DELISTED = "delisted"  # 已下架
    FALLBACK_QUEUED = "fallback_queued"  # RPA fallback queued
    FALLBACK_RUNNING = "fallback_running"  # RPA fallback running
    MANUAL_INTERVENTION_REQUIRED = "manual_intervention_required"  # Manual intervention required


class TargetPlatform(str, Enum):
    """Target platform for selling."""
    TEMU = "temu"
    AMAZON = "amazon"
    ALIEXPRESS = "aliexpress"
    OZON = "ozon"
    WILDBERRIES = "wildberries"
    SHOPEE = "shopee"
    MERCADO_LIBRE = "mercado_libre"
    TIKTOK_SHOP = "tiktok_shop"
    EBAY = "ebay"
    WALMART = "walmart"
    RAKUTEN = "rakuten"
    ALLEGRO = "allegro"


class ExperimentStatus(str, Enum):
    """Experiment status."""
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    ARCHIVED = "archived"


class FeedbackAction(str, Enum):
    """User feedback action on recommendations."""
    ACCEPTED = "accepted"  # 接受推荐
    REJECTED = "rejected"  # 拒绝推荐
    DEFERRED = "deferred"  # 延后决策
