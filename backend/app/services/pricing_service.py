"""Pricing calculation service."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional, Union

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import ProfitabilityDecision, TargetPlatform
from app.core.logging import get_logger

logger = get_logger(__name__)

_SCORE_QUANTIZE = Decimal("0.0001")
_ZERO = Decimal("0")
_ONE = Decimal("1")
_HALF = Decimal("0.5")


class PricingConfig:
    """Pricing calculation configuration."""

    # Default rates
    DEFAULT_SHIPPING_RATE = Decimal("0.15")  # 15% of product cost
    DEFAULT_PLATFORM_COMMISSION = Decimal("0.10")  # 10%
    DEFAULT_PAYMENT_FEE = Decimal("0.02")  # 2%
    DEFAULT_RETURN_RATE = Decimal("0.05")  # 5%

    # Profitability thresholds (updated 2026-03-26)
    PROFITABLE_THRESHOLD = Decimal("0.35")  # 35% (raised from 30%)
    MARGINAL_THRESHOLD = Decimal("0.20")  # 20% (raised from 15%)

    # Platform-specific thresholds
    PLATFORM_THRESHOLDS = {
        "amazon": Decimal("0.40"),  # 40% (high fees, high competition)
        "temu": Decimal("0.30"),  # 30% (lower fees, price-sensitive)
        "aliexpress": Decimal("0.35"),  # 35% (moderate fees)
        "ozon": Decimal("0.35"),  # 35% (moderate fees)
        "rakuten": Decimal("0.38"),  # 38% (higher fees)
        "mercado_libre": Decimal("0.35"),  # 35% (moderate fees)
    }

    # Category-specific thresholds
    CATEGORY_THRESHOLDS = {
        "electronics": Decimal("0.25"),  # 25% (low margin category)
        "jewelry": Decimal("0.50"),  # 50% (high margin category)
        "home": Decimal("0.35"),  # 35% (moderate margin)
        "fashion": Decimal("0.40"),  # 40% (moderate-high margin)
        "toys": Decimal("0.35"),  # 35% (moderate margin)
        "beauty": Decimal("0.45"),  # 45% (high margin)
        "sports": Decimal("0.35"),  # 35% (moderate margin)
    }

    # Competition density adjustments (2026-03-28)
    COMPETITION_DENSITY_ADJUSTMENTS = {
        "low": Decimal("0.00"),  # No adjustment for low competition
        "medium": Decimal("0.03"),  # +3% threshold for medium competition
        "high": Decimal("0.05"),  # +5% threshold for high competition
        "unknown": Decimal("0.02"),  # +2% threshold for unknown competition (conservative)
    }

    # Discovery mode adjustments (2026-03-28)
    DISCOVERY_MODE_ADJUSTMENTS = {
        "user": Decimal("0.00"),  # No adjustment for user-validated keywords
        "seed_pool": Decimal("0.01"),  # +1% threshold for category seed pool discovery
        "generated": Decimal("0.01"),  # +1% threshold for generated keywords (offline)
        "exploration": Decimal("0.02"),  # +2% threshold for autonomous exploration mode
        "fallback": Decimal("0.03"),  # +3% threshold for fallback seeds
        "none": Decimal("0.05"),  # +5% threshold when no validation occurred
    }

    # Degraded discovery penalty (2026-03-28)
    DEGRADED_DISCOVERY_PENALTY = Decimal("0.02")  # +2% threshold when discovery degraded

    @classmethod
    def get_profitable_threshold(
        cls,
        platform: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Decimal:
        """Get effective profitable threshold based on platform and category.

        Returns the maximum of platform-specific and category-specific thresholds,
        falling back to the base threshold if neither is specified.

        Args:
            platform: Platform name (e.g., "amazon", "temu")
            category: Category name (e.g., "electronics", "jewelry")

        Returns:
            Effective profitable threshold as Decimal
        """
        thresholds = [cls.PROFITABLE_THRESHOLD]

        if platform:
            platform_lower = platform.lower()
            if platform_lower in cls.PLATFORM_THRESHOLDS:
                thresholds.append(cls.PLATFORM_THRESHOLDS[platform_lower])

        if category:
            category_lower = category.lower()
            if category_lower in cls.CATEGORY_THRESHOLDS:
                thresholds.append(cls.CATEGORY_THRESHOLDS[category_lower])

        return max(thresholds)

    @classmethod
    def get_marginal_threshold(
        cls,
        platform: Optional[str] = None,
        category: Optional[str] = None,
    ) -> Decimal:
        """Get effective marginal threshold based on platform and category.

        Marginal threshold is calculated as 60% of the profitable threshold.

        Args:
            platform: Platform name (e.g., "amazon", "temu")
            category: Category name (e.g., "electronics", "jewelry")

        Returns:
            Effective marginal threshold as Decimal
        """
        profitable_threshold = cls.get_profitable_threshold(platform, category)
        return profitable_threshold * Decimal("0.60")

    @classmethod
    def get_demand_context_adjustment(
        cls,
        competition_density: Optional[str] = None,
        discovery_mode: Optional[str] = None,
        degraded: bool = False,
    ) -> Decimal:
        """Get additive threshold adjustment from demand context."""
        adjustment = _ZERO

        if competition_density:
            adjustment += cls.COMPETITION_DENSITY_ADJUSTMENTS.get(
                competition_density.lower(),
                _ZERO,
            )

        if discovery_mode:
            adjustment += cls.DISCOVERY_MODE_ADJUSTMENTS.get(
                discovery_mode.lower(),
                _ZERO,
            )

        if degraded:
            adjustment += cls.DEGRADED_DISCOVERY_PENALTY

        return adjustment

    # Supplier path selection weights
    SUPPLIER_PRICE_WEIGHT = Decimal("0.45")
    SUPPLIER_CONFIDENCE_WEIGHT = Decimal("0.30")
    SUPPLIER_MOQ_WEIGHT = Decimal("0.15")
    SUPPLIER_PRICE_GAP_TOLERANCE = Decimal("0.20")  # 20% premium reduces price score to zero
    SUPPLIER_PRICE_GAP_PENALTY_WEIGHT = Decimal("0.20")
    SUPPLIER_FACTORY_BONUS = Decimal("0.06")
    SUPPLIER_SUPER_FACTORY_BONUS = Decimal("0.04")
    SUPPLIER_VERIFIED_BONUS = Decimal("0.04")
    SUPPLIER_ALTERNATIVE_SKU_PENALTY = Decimal("0.05")


@dataclass(frozen=True)
class SupplierPathInput:
    """Input data required to evaluate a supplier path."""

    id: str
    supplier_name: Optional[str]
    supplier_sku: Optional[str]
    supplier_price: Optional[Decimal]
    moq: Optional[int]
    confidence_score: Optional[Decimal]
    raw_payload: Optional[dict[str, Any]]


@dataclass(frozen=True)
class SupplierPathScore:
    """Supplier path score and breakdown."""

    path: SupplierPathInput
    usable_for_pricing: bool
    total_score: Optional[Decimal]
    price_component: Optional[Decimal]
    confidence_component: Optional[Decimal]
    moq_component: Optional[Decimal]
    identity_bonus: Optional[Decimal]
    alternative_sku_penalty: Optional[Decimal]
    price_gap_penalty: Optional[Decimal]
    is_factory_result: bool = False
    is_super_factory: bool = False
    verified_supplier: bool = False
    alternative_sku: bool = False
    rejection_reason: Optional[str] = None

    def to_dict(self, rank: Optional[int] = None) -> dict[str, Any]:
        """Convert score details to a JSON-serializable dictionary."""
        return {
            "rank": rank,
            "supplier_match_id": self.path.id,
            "supplier_name": self.path.supplier_name,
            "supplier_sku": self.path.supplier_sku,
            "supplier_price": _decimal_to_float(self.path.supplier_price),
            "moq": self.path.moq,
            "confidence_score": _decimal_to_float(self.path.confidence_score),
            "usable_for_pricing": self.usable_for_pricing,
            "rejection_reason": self.rejection_reason,
            "score": _decimal_to_float(self.total_score),
            "score_breakdown": {
                "price_component": _decimal_to_float(self.price_component),
                "confidence_component": _decimal_to_float(self.confidence_component),
                "moq_component": _decimal_to_float(self.moq_component),
                "identity_bonus": _decimal_to_float(self.identity_bonus),
                "alternative_sku_penalty": _decimal_to_float(self.alternative_sku_penalty),
                "price_gap_penalty": _decimal_to_float(self.price_gap_penalty),
            },
            "identity_signals": {
                "is_factory_result": self.is_factory_result,
                "is_super_factory": self.is_super_factory,
                "verified_supplier": self.verified_supplier,
                "alternative_sku": self.alternative_sku,
            },
        }


@dataclass(frozen=True)
class SupplierPathSelectionResult:
    """Supplier selection result across a competition set."""

    selected_path: Optional[SupplierPathInput]
    ranked_paths: list[SupplierPathScore]
    competition_set_size: int
    considered_supplier_count: int

    @property
    def selected_score(self) -> Optional[SupplierPathScore]:
        """Return the scored record for the selected path."""
        if not self.selected_path:
            return None

        for score in self.ranked_paths:
            if score.path.id == self.selected_path.id:
                return score
        return None

    def to_explanation(self) -> dict[str, Any]:
        """Convert the selection result to an explanation payload."""
        ranked_supplier_paths = [
            score.to_dict(rank=index + 1) for index, score in enumerate(self.ranked_paths)
        ]
        selected_score = self.selected_score

        return {
            "competition_set_size": self.competition_set_size,
            "considered_supplier_count": self.considered_supplier_count,
            "selected_supplier": selected_score.to_dict(rank=1) if selected_score else None,
            "ranked_supplier_paths": ranked_supplier_paths,
            "selection_reason": self._build_selection_reason(selected_score),
        }

    def _build_selection_reason(self, selected_score: Optional[SupplierPathScore]) -> str:
        """Build a human-readable explanation for the selected supplier path."""
        if not selected_score:
            return "No supplier path had a valid supplier price, so pricing was skipped."

        eligible_scores = [score for score in self.ranked_paths if score.usable_for_pricing]
        if len(eligible_scores) == 1:
            return "Selected the only supplier path with a valid supplier price for pricing."

        cheapest_score = min(
            eligible_scores,
            key=lambda score: score.path.supplier_price if score.path.supplier_price is not None else Decimal("999999"),
        )

        if cheapest_score.path.id == selected_score.path.id:
            return (
                "Selected the lowest-cost supplier path because it also led the competition set on "
                "overall confidence, MOQ, and supplier identity adjusted score."
            )

        reasons = []
        if _or_zero(selected_score.confidence_component) > _or_zero(cheapest_score.confidence_component):
            reasons.append("higher confidence")
        if _or_zero(selected_score.moq_component) > _or_zero(cheapest_score.moq_component):
            reasons.append("lower MOQ")
        if _or_zero(selected_score.identity_bonus) > _or_zero(cheapest_score.identity_bonus):
            reasons.append("stronger factory / verified supplier signals")
        if selected_score.alternative_sku is False and cheapest_score.alternative_sku is True:
            reasons.append("not relying on an alternative SKU fallback")
        if not reasons:
            reasons.append("a better overall composite supplier score")

        cheapest_price = cheapest_score.path.supplier_price or _ZERO
        selected_price = selected_score.path.supplier_price or _ZERO
        if cheapest_price > _ZERO:
            price_premium = ((selected_price - cheapest_price) / cheapest_price * 100).quantize(
                Decimal("0.01")
            )
            return (
                "Selected this supplier path because "
                f"{', '.join(reasons)} outweighed a {price_premium}% price premium versus the "
                "absolute cheapest option."
            )

        return "Selected this supplier path based on the strongest composite score across price, confidence, MOQ, and supplier identity signals."


class PricingResult:
    """Pricing calculation result."""

    def __init__(
        self,
        supplier_price: Decimal,
        platform_price: Decimal,
        estimated_shipping_cost: Decimal,
        platform_commission_rate: Decimal,
        payment_fee_rate: Decimal,
        return_rate_assumption: Decimal,
        platform: Optional[str] = None,
        category: Optional[str] = None,
        competition_density: Optional[str] = None,
        discovery_mode: Optional[str] = None,
        degraded: bool = False,
        profitable_threshold_override: Optional[Decimal] = None,
        marginal_threshold_override: Optional[Decimal] = None,
    ):
        self.supplier_price = supplier_price
        self.platform_price = platform_price
        self.estimated_shipping_cost = estimated_shipping_cost
        self.platform_commission_rate = platform_commission_rate
        self.payment_fee_rate = payment_fee_rate
        self.return_rate_assumption = return_rate_assumption
        self.platform = platform
        self.category = category
        self.competition_density = competition_density
        self.discovery_mode = discovery_mode
        self.degraded = degraded

        # Get dynamic thresholds based on platform and category
        # Priority: 1) explicit override, 2) PricingConfig.get_profitable_threshold(), 3) default
        if profitable_threshold_override is not None:
            base_profitable_threshold = profitable_threshold_override
        else:
            base_profitable_threshold = PricingConfig.get_profitable_threshold(platform, category)

        demand_adjustment = PricingConfig.get_demand_context_adjustment(
            competition_density=competition_density,
            discovery_mode=discovery_mode,
            degraded=degraded,
        )
        self.profitable_threshold = base_profitable_threshold + demand_adjustment

        # Marginal threshold: use override if provided, otherwise calculate from profitable threshold
        if marginal_threshold_override is not None:
            self.marginal_threshold = marginal_threshold_override
        else:
            self.marginal_threshold = self.profitable_threshold * Decimal("0.60")

        # Calculate costs
        self.platform_commission = platform_price * platform_commission_rate
        self.payment_fee = platform_price * payment_fee_rate
        self.return_cost = supplier_price * return_rate_assumption

        self.total_cost = (
            supplier_price
            + estimated_shipping_cost
            + self.platform_commission
            + self.payment_fee
            + self.return_cost
        )

        # Calculate margin
        self.estimated_margin = platform_price - self.total_cost
        self.margin_percentage = (
            (self.estimated_margin / platform_price * 100)
            if platform_price > 0
            else Decimal("0")
        )

        # Determine profitability using dynamic thresholds
        margin_ratio = self.estimated_margin / platform_price if platform_price > 0 else Decimal("0")
        if margin_ratio >= self.profitable_threshold:
            self.profitability_decision = ProfitabilityDecision.PROFITABLE
        elif margin_ratio >= self.marginal_threshold:
            self.profitability_decision = ProfitabilityDecision.MARGINAL
        else:
            self.profitability_decision = ProfitabilityDecision.UNPROFITABLE

        # Recommended price (using dynamic profitable threshold)
        break_even = self.total_cost / (1 - self.profitable_threshold)
        self.recommended_price = break_even.quantize(Decimal("0.01"))

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "supplier_price": float(self.supplier_price),
            "platform_price": float(self.platform_price),
            "estimated_shipping_cost": float(self.estimated_shipping_cost),
            "platform_commission_rate": float(self.platform_commission_rate),
            "payment_fee_rate": float(self.payment_fee_rate),
            "return_rate_assumption": float(self.return_rate_assumption),
            "total_cost": float(self.total_cost),
            "estimated_margin": float(self.estimated_margin),
            "margin_percentage": float(self.margin_percentage),
            "recommended_price": float(self.recommended_price),
            "profitability_decision": self.profitability_decision.value,
            "platform": self.platform,
            "category": self.category,
            "competition_density": self.competition_density,
            "discovery_mode": self.discovery_mode,
            "degraded": self.degraded,
            "profitable_threshold": float(self.profitable_threshold),
            "marginal_threshold": float(self.marginal_threshold),
            "explanation": {
                "breakdown": {
                    "supplier_price": float(self.supplier_price),
                    "shipping": float(self.estimated_shipping_cost),
                    "platform_commission": float(self.platform_commission),
                    "payment_fee": float(self.payment_fee),
                    "return_cost": float(self.return_cost),
                },
                "total_cost": float(self.total_cost),
                "revenue": float(self.platform_price),
                "margin": float(self.estimated_margin),
                "thresholds": {
                    "profitable": float(self.profitable_threshold),
                    "marginal": float(self.marginal_threshold),
                    "competition_density": self.competition_density,
                    "discovery_mode": self.discovery_mode,
                    "degraded": self.degraded,
                },
            },
        }


class PricingService:
    """Service for profit calculation and pricing recommendations."""

    def __init__(self, config: Optional[PricingConfig] = None):
        self.config = config or PricingConfig()

    def select_best_supplier_path(
        self,
        supplier_paths: list[SupplierPathInput],
    ) -> SupplierPathSelectionResult:
        """Select the best supplier path from a competition set."""
        valid_paths = [path for path in supplier_paths if self._is_valid_price(path.supplier_price)]
        min_price = min((path.supplier_price for path in valid_paths if path.supplier_price is not None), default=None)
        known_moqs = [
            path.moq
            for path in valid_paths
            if path.moq is not None and path.moq > 0
        ]

        ranked_paths = [
            self._score_supplier_path(path=path, min_price=min_price, known_moqs=known_moqs)
            for path in supplier_paths
        ]

        ranked_paths.sort(key=self._score_sort_key, reverse=True)
        selected_score = next((score for score in ranked_paths if score.usable_for_pricing), None)

        return SupplierPathSelectionResult(
            selected_path=selected_score.path if selected_score else None,
            ranked_paths=ranked_paths,
            competition_set_size=len(supplier_paths),
            considered_supplier_count=len(valid_paths),
        )

    def calculate_pricing(
        self,
        supplier_price: Decimal,
        platform_price: Decimal,
        shipping_cost: Optional[Decimal] = None,
        platform_commission_rate: Optional[Decimal] = None,
        payment_fee_rate: Optional[Decimal] = None,
        return_rate_assumption: Optional[Decimal] = None,
        platform: Optional[str] = None,
        category: Optional[str] = None,
        competition_density: Optional[str] = None,
        discovery_mode: Optional[str] = None,
        degraded: bool = False,
    ) -> PricingResult:
        """Calculate pricing and profitability.

        Args:
            supplier_price: Supplier price
            platform_price: Platform selling price
            shipping_cost: Shipping cost (optional, defaults to 15% of supplier price)
            platform_commission_rate: Platform commission rate (optional, defaults to 10%)
            payment_fee_rate: Payment fee rate (optional, defaults to 2%)
            return_rate_assumption: Return rate assumption (optional, defaults to 5%)
            platform: Platform name for dynamic threshold (e.g., "amazon", "temu")
            category: Category name for dynamic threshold (e.g., "electronics", "jewelry")
            competition_density: Demand competition density from discovery metadata
            discovery_mode: Demand discovery mode (user/generated/fallback/none)
            degraded: Whether demand discovery ran in degraded mode

        Returns:
            PricingResult with profitability decision based on dynamic thresholds
        """
        # Use defaults if not provided
        shipping_cost = shipping_cost or (supplier_price * self.config.DEFAULT_SHIPPING_RATE)
        platform_commission_rate = (
            platform_commission_rate or self.config.DEFAULT_PLATFORM_COMMISSION
        )
        payment_fee_rate = payment_fee_rate or self.config.DEFAULT_PAYMENT_FEE
        return_rate_assumption = return_rate_assumption or self.config.DEFAULT_RETURN_RATE

        result = PricingResult(
            supplier_price=supplier_price,
            platform_price=platform_price,
            estimated_shipping_cost=shipping_cost,
            platform_commission_rate=platform_commission_rate,
            payment_fee_rate=payment_fee_rate,
            return_rate_assumption=return_rate_assumption,
            platform=platform,
            category=category,
            competition_density=competition_density,
            discovery_mode=discovery_mode,
            degraded=degraded,
        )

        logger.info(
            "pricing_calculated",
            supplier_price=float(supplier_price),
            platform_price=float(platform_price),
            margin_percentage=float(result.margin_percentage),
            decision=result.profitability_decision.value,
            platform=platform,
            category=category,
            competition_density=competition_density,
            discovery_mode=discovery_mode,
            degraded=degraded,
            profitable_threshold=float(result.profitable_threshold),
            marginal_threshold=float(result.marginal_threshold),
        )

        return result

    async def calculate_pricing_with_policy(
        self,
        *,
        db: AsyncSession,
        supplier_price: Decimal,
        platform_price: Decimal,
        platform: Union[str, TargetPlatform],
        region: Optional[str] = None,
        category: Optional[str] = None,
        shipping_cost: Optional[Decimal] = None,
        competition_density: Optional[str] = None,
        discovery_mode: Optional[str] = None,
        degraded: bool = False,
    ) -> PricingResult:
        """Calculate pricing using platform policy configuration.

        Falls back to hardcoded PricingConfig if no policy found.

        Args:
            db: Database session
            supplier_price: Supplier price
            platform_price: Platform selling price
            platform: Platform name or enum
            region: Region code (optional)
            category: Category name (optional)
            shipping_cost: Shipping cost (optional)
            competition_density: Demand competition density
            discovery_mode: Demand discovery mode
            degraded: Whether demand discovery ran in degraded mode

        Returns:
            PricingResult with policy-aware configuration
        """
        # Import here to avoid circular dependency
        from app.services.platform_policy_service import PlatformPolicyService

        policy_service = PlatformPolicyService()

        # Convert platform to enum if string
        platform_enum = platform if isinstance(platform, TargetPlatform) else TargetPlatform(platform)

        # Get commission config from policy
        commission_config = await policy_service.get_commission_config(
            db=db,
            platform=platform_enum,
            region=region,
        )

        # Get pricing config from policy
        pricing_config = await policy_service.get_pricing_config(
            db=db,
            platform=platform_enum,
            region=region,
        )

        # Merge policy configs
        platform_commission_rate = Decimal(str(commission_config.get("commission_rate", self.config.DEFAULT_PLATFORM_COMMISSION)))
        payment_fee_rate = Decimal(str(commission_config.get("payment_fee_rate", self.config.DEFAULT_PAYMENT_FEE)))
        return_rate_assumption = Decimal(str(commission_config.get("return_rate_assumption", self.config.DEFAULT_RETURN_RATE)))

        # Shipping rate from pricing config
        shipping_rate_default = Decimal(str(pricing_config.get("shipping_rate_default", self.config.DEFAULT_SHIPPING_RATE)))
        if shipping_cost is None:
            shipping_cost = supplier_price * shipping_rate_default

        # Threshold overrides from pricing config
        profitable_threshold_override = None
        marginal_threshold_override = None

        # Base profitable threshold from policy
        if "profitable_threshold" in pricing_config:
            profitable_threshold_override = Decimal(str(pricing_config["profitable_threshold"]))

        # Category-specific override
        category_overrides = pricing_config.get("category_threshold_overrides", {})
        if category and category.lower() in category_overrides:
            profitable_threshold_override = Decimal(str(category_overrides[category.lower()]))

        # Marginal threshold ratio from policy
        if profitable_threshold_override is not None and "marginal_threshold_ratio" in pricing_config:
            marginal_threshold_ratio = Decimal(str(pricing_config["marginal_threshold_ratio"]))
            marginal_threshold_override = profitable_threshold_override * marginal_threshold_ratio

        # Construct PricingResult with overrides
        result = PricingResult(
            supplier_price=supplier_price,
            platform_price=platform_price,
            estimated_shipping_cost=shipping_cost,
            platform_commission_rate=platform_commission_rate,
            payment_fee_rate=payment_fee_rate,
            return_rate_assumption=return_rate_assumption,
            platform=platform_enum.value,
            category=category,
            competition_density=competition_density,
            discovery_mode=discovery_mode,
            degraded=degraded,
            profitable_threshold_override=profitable_threshold_override,
            marginal_threshold_override=marginal_threshold_override,
        )

        logger.info(
            "pricing_calculated_with_policy",
            supplier_price=float(supplier_price),
            platform_price=float(platform_price),
            margin_percentage=float(result.margin_percentage),
            decision=result.profitability_decision.value,
            platform=platform_enum.value,
            region=region,
            category=category,
            profitable_threshold=float(result.profitable_threshold),
            marginal_threshold=float(result.marginal_threshold),
            policy_applied=True,
        )

        return result

    async def get_effective_pricing_inputs(
        self,
        *,
        db: AsyncSession,
        platform: Union[str, TargetPlatform],
        region: Optional[str] = None,
        category: Optional[str] = None,
    ) -> dict[str, Any]:
        """Get effective pricing inputs from policy with fallback.

        Returns dict with:
        - commission_rate
        - payment_fee_rate
        - return_rate_assumption
        - shipping_rate
        - profitable_threshold
        - marginal_threshold

        Args:
            db: Database session
            platform: Platform name or enum
            region: Region code (optional)
            category: Category name (optional)

        Returns:
            Dict with effective pricing inputs
        """
        # Import here to avoid circular dependency
        from app.services.platform_policy_service import PlatformPolicyService

        policy_service = PlatformPolicyService()

        # Convert platform to enum if string
        platform_enum = platform if isinstance(platform, TargetPlatform) else TargetPlatform(platform)

        # Get commission config from policy
        commission_config = await policy_service.get_commission_config(
            db=db,
            platform=platform_enum,
            region=region,
        )

        # Get pricing config from policy
        pricing_config = await policy_service.get_pricing_config(
            db=db,
            platform=platform_enum,
            region=region,
        )

        # Build effective inputs
        commission_rate = Decimal(str(commission_config.get("commission_rate", self.config.DEFAULT_PLATFORM_COMMISSION)))
        payment_fee_rate = Decimal(str(commission_config.get("payment_fee_rate", self.config.DEFAULT_PAYMENT_FEE)))
        return_rate_assumption = Decimal(str(commission_config.get("return_rate_assumption", self.config.DEFAULT_RETURN_RATE)))
        shipping_rate = Decimal(str(pricing_config.get("shipping_rate_default", self.config.DEFAULT_SHIPPING_RATE)))

        # Threshold calculation
        profitable_threshold = Decimal(str(pricing_config.get("profitable_threshold", self.config.PROFITABLE_THRESHOLD)))

        # Category-specific override
        category_overrides = pricing_config.get("category_threshold_overrides", {})
        if category and category.lower() in category_overrides:
            profitable_threshold = Decimal(str(category_overrides[category.lower()]))

        # Marginal threshold
        marginal_threshold_ratio = Decimal(str(pricing_config.get("marginal_threshold_ratio", "0.60")))
        marginal_threshold = profitable_threshold * marginal_threshold_ratio

        return {
            "commission_rate": commission_rate,
            "payment_fee_rate": payment_fee_rate,
            "return_rate_assumption": return_rate_assumption,
            "shipping_rate": shipping_rate,
            "profitable_threshold": profitable_threshold,
            "marginal_threshold": marginal_threshold,
        }

    def _score_supplier_path(
        self,
        path: SupplierPathInput,
        min_price: Optional[Decimal],
        known_moqs: list[int],
    ) -> SupplierPathScore:
        """Score a supplier path for pricing selection."""
        if not self._is_valid_price(path.supplier_price):
            return SupplierPathScore(
                path=path,
                usable_for_pricing=False,
                total_score=None,
                price_component=None,
                confidence_component=None,
                moq_component=None,
                identity_bonus=None,
                alternative_sku_penalty=None,
                price_gap_penalty=None,
                rejection_reason=self._price_rejection_reason(path.supplier_price),
            )

        raw_payload = path.raw_payload or {}
        is_factory_result = self._is_truthy(raw_payload.get("is_factory_result"))
        is_super_factory = self._is_truthy(raw_payload.get("is_super_factory"))
        verified_supplier = self._is_truthy(raw_payload.get("verified_supplier"))
        alternative_sku = self._is_truthy(raw_payload.get("alternative_sku"))

        confidence = self._normalize_confidence(path.confidence_score)
        moq_score = self._normalize_moq(path.moq, known_moqs)
        price_gap_ratio = self._price_gap_ratio(path.supplier_price, min_price)
        price_component = self._quantize(
            self.config.SUPPLIER_PRICE_WEIGHT * self._price_score(price_gap_ratio)
        )
        confidence_component = self._quantize(
            self.config.SUPPLIER_CONFIDENCE_WEIGHT * confidence
        )
        moq_component = self._quantize(self.config.SUPPLIER_MOQ_WEIGHT * moq_score)

        identity_bonus = _ZERO
        if is_factory_result:
            identity_bonus += self.config.SUPPLIER_FACTORY_BONUS
        if is_super_factory:
            identity_bonus += self.config.SUPPLIER_SUPER_FACTORY_BONUS
        if verified_supplier:
            identity_bonus += self.config.SUPPLIER_VERIFIED_BONUS
        identity_bonus = self._quantize(identity_bonus)

        alternative_sku_penalty = self._quantize(
            self.config.SUPPLIER_ALTERNATIVE_SKU_PENALTY if alternative_sku else _ZERO
        )
        price_gap_penalty = self._quantize(
            min(price_gap_ratio, _ONE) * self.config.SUPPLIER_PRICE_GAP_PENALTY_WEIGHT
        )

        total_score = self._quantize(
            price_component
            + confidence_component
            + moq_component
            + identity_bonus
            - alternative_sku_penalty
            - price_gap_penalty
        )

        return SupplierPathScore(
            path=path,
            usable_for_pricing=True,
            total_score=total_score,
            price_component=price_component,
            confidence_component=confidence_component,
            moq_component=moq_component,
            identity_bonus=identity_bonus,
            alternative_sku_penalty=alternative_sku_penalty,
            price_gap_penalty=price_gap_penalty,
            is_factory_result=is_factory_result,
            is_super_factory=is_super_factory,
            verified_supplier=verified_supplier,
            alternative_sku=alternative_sku,
        )

    def _score_sort_key(self, score: SupplierPathScore) -> tuple:
        """Sort eligible paths first, then by score, then deterministic tie-breakers."""
        supplier_price = score.path.supplier_price if score.path.supplier_price is not None else Decimal("999999")
        moq_value = score.path.moq if score.path.moq is not None and score.path.moq > 0 else 999999
        confidence = self._normalize_confidence(score.path.confidence_score)

        return (
            1 if score.usable_for_pricing else 0,
            _or_zero(score.total_score),
            -supplier_price,
            confidence,
            -Decimal(str(moq_value)),
        )

    def _price_score(self, price_gap_ratio: Decimal) -> Decimal:
        """Convert a price premium versus the cheapest path into a weighted score."""
        tolerance = self.config.SUPPLIER_PRICE_GAP_TOLERANCE
        if tolerance <= _ZERO:
            return _ONE if price_gap_ratio <= _ZERO else _ZERO

        normalized_gap = min(price_gap_ratio / tolerance, _ONE)
        return max(_ZERO, _ONE - normalized_gap)

    def _price_gap_ratio(
        self,
        supplier_price: Optional[Decimal],
        min_price: Optional[Decimal],
    ) -> Decimal:
        """Compute price gap versus the cheapest valid supplier."""
        if supplier_price is None or min_price is None or min_price <= _ZERO:
            return _ZERO
        if supplier_price <= min_price:
            return _ZERO
        return (supplier_price - min_price) / min_price

    def _normalize_moq(self, moq: Optional[int], known_moqs: list[int]) -> Decimal:
        """Normalize MOQ so lower MOQ receives a higher score."""
        if moq is None or moq <= 0:
            return _HALF
        if not known_moqs:
            return _HALF

        min_moq = min(known_moqs)
        max_moq = max(known_moqs)
        if max_moq == min_moq:
            return _ONE

        return (Decimal(str(max_moq)) - Decimal(str(moq))) / Decimal(str(max_moq - min_moq))

    def _normalize_confidence(self, confidence_score: Optional[Decimal]) -> Decimal:
        """Normalize confidence to a 0-1 range."""
        if confidence_score is None:
            return _ZERO

        try:
            confidence = Decimal(str(confidence_score))
        except (InvalidOperation, ValueError):
            return _ZERO

        if confidence < _ZERO:
            return _ZERO
        if confidence > _ONE:
            return _ONE
        return confidence

    def _is_valid_price(self, supplier_price: Optional[Decimal]) -> bool:
        """Return whether a supplier price can be used for pricing."""
        if supplier_price is None:
            return False

        try:
            return Decimal(str(supplier_price)) > _ZERO
        except (InvalidOperation, ValueError):
            return False

    def _price_rejection_reason(self, supplier_price: Optional[Decimal]) -> str:
        """Return a machine-readable reason for rejecting a supplier path."""
        if supplier_price is None:
            return "missing_supplier_price"
        return "invalid_supplier_price"

    def _is_truthy(self, value: Any) -> bool:
        """Interpret raw payload truthy values consistently."""
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y", "on"}
        if isinstance(value, (int, float, Decimal)):
            return value != 0
        return False

    async def calculate_regionalized_pricing(
        self,
        *,
        db: AsyncSession,
        supplier_price: Decimal,
        platform_price: Decimal,
        platform: Union[str, TargetPlatform],
        region: str,
        base_currency: str = "USD",
        local_currency: Optional[str] = None,
        category: Optional[str] = None,
        shipping_cost: Optional[Decimal] = None,
        competition_density: Optional[str] = None,
        discovery_mode: Optional[str] = None,
        degraded: bool = False,
    ) -> dict[str, Any]:
        """Calculate regionalized pricing with tax estimation and currency conversion.

        Args:
            db: Database session
            supplier_price: Supplier price (in base currency)
            platform_price: Platform selling price (in local currency)
            platform: Platform name or enum
            region: Region code
            base_currency: Base currency for profit comparison (default: USD)
            local_currency: Local currency for the region (optional, defaults to base_currency)
            category: Category name (optional)
            shipping_cost: Shipping cost (optional)
            competition_density: Demand competition density
            discovery_mode: Demand discovery mode
            degraded: Whether demand discovery ran in degraded mode

        Returns:
            Dict with:
                - local_price: Price in local currency
                - base_currency_profit: Profit in base currency
                - tax_estimate: Estimated tax amount
                - risk_notes: List of risk warnings
                - pricing_result: Standard PricingResult dict
                - currency_metadata: Currency conversion metadata
        """
        from app.services.currency_converter import CurrencyConverter
        from app.services.platform_policy_service import PlatformPolicyService

        policy_service = PlatformPolicyService()
        currency_converter = CurrencyConverter()

        # Convert platform to enum if string
        platform_enum = platform if isinstance(platform, TargetPlatform) else TargetPlatform(platform)

        # Default local currency to base currency if not specified
        if local_currency is None:
            local_currency = base_currency

        # Calculate base pricing using policy-aware method
        pricing_result = await self.calculate_pricing_with_policy(
            db=db,
            supplier_price=supplier_price,
            platform_price=platform_price,
            platform=platform_enum,
            region=region,
            category=category,
            shipping_cost=shipping_cost,
            competition_density=competition_density,
            discovery_mode=discovery_mode,
            degraded=degraded,
        )

        # Query tax rules
        tax_rules = await policy_service.get_tax_rules(
            db=db,
            platform=platform_enum,
            region=region,
        )

        # Calculate tax estimate
        tax_estimate = Decimal("0.00")
        tax_breakdown = []
        for rule in tax_rules:
            tax_amount = platform_price * rule.tax_rate
            tax_estimate += tax_amount
            tax_breakdown.append({
                "tax_type": rule.tax_type,
                "tax_rate": float(rule.tax_rate),
                "tax_amount": float(tax_amount),
                "applies_to": rule.applies_to,
            })

        # Query risk rules
        risk_rules = await policy_service.get_risk_rules(
            db=db,
            platform=platform_enum,
            region=region,
        )

        # Build risk notes
        risk_notes = []
        for rule in risk_rules:
            risk_notes.append({
                "rule_code": rule.rule_code,
                "severity": rule.severity,
                "rule_data": rule.rule_data,
                "notes": rule.notes,
            })

        # Convert profit to base currency if needed
        base_currency_profit = pricing_result.estimated_margin
        if local_currency != base_currency:
            try:
                base_currency_profit = await currency_converter.convert_amount(
                    db=db,
                    amount=pricing_result.estimated_margin,
                    from_currency=local_currency,
                    to_currency=base_currency,
                )
            except ValueError as e:
                logger.warning(
                    "currency_conversion_failed_for_profit",
                    from_currency=local_currency,
                    to_currency=base_currency,
                    error=str(e),
                )

        # Check minimum margin requirement from pricing policy
        pricing_config = await policy_service.get_pricing_config(
            db=db,
            platform=platform_enum,
            region=region,
        )
        min_margin_percentage = pricing_config.get("min_margin_percentage")
        margin_check_passed = True
        margin_check_note = None

        if min_margin_percentage is not None:
            min_margin_decimal = Decimal(str(min_margin_percentage))
            actual_margin_ratio = pricing_result.estimated_margin / platform_price if platform_price > 0 else Decimal("0")
            if actual_margin_ratio < min_margin_decimal:
                margin_check_passed = False
                margin_check_note = (
                    f"Margin {float(actual_margin_ratio * 100):.2f}% is below "
                    f"minimum required {float(min_margin_decimal * 100):.2f}% for {platform_enum.value}/{region}"
                )

        # Build result
        result = {
            "local_price": float(platform_price),
            "local_currency": local_currency,
            "base_currency_profit": float(base_currency_profit),
            "base_currency": base_currency,
            "tax_estimate": float(tax_estimate),
            "tax_breakdown": tax_breakdown,
            "risk_notes": risk_notes,
            "pricing_result": pricing_result.to_dict(),
            "currency_metadata": {
                "local_currency": local_currency,
                "base_currency": base_currency,
                "conversion_applied": local_currency != base_currency,
            },
            "margin_check": {
                "passed": margin_check_passed,
                "min_margin_percentage": float(min_margin_decimal) if min_margin_percentage is not None else None,
                "actual_margin_percentage": float(pricing_result.margin_percentage),
                "note": margin_check_note,
            },
        }

        logger.info(
            "regionalized_pricing_calculated",
            platform=platform_enum.value,
            region=region,
            local_price=float(platform_price),
            base_currency_profit=float(base_currency_profit),
            tax_estimate=float(tax_estimate),
            risk_count=len(risk_notes),
            margin_check_passed=margin_check_passed,
        )

        return result

    def _quantize(self, value: Decimal) -> Decimal:
        """Quantize supplier selection scores for stable storage and tests."""
        return value.quantize(_SCORE_QUANTIZE)


def _decimal_to_float(value: Optional[Decimal]) -> Optional[float]:
    """Convert a Decimal value to float for JSON serialization."""
    if value is None:
        return None
    return float(value)


def _or_zero(value: Optional[Decimal]) -> Decimal:
    """Return zero when the score component is missing."""
    return value if value is not None else _ZERO
