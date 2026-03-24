"""Pricing calculation service."""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from app.core.enums import ProfitabilityDecision
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

    # Profitability thresholds
    PROFITABLE_THRESHOLD = Decimal("0.30")  # 30%
    MARGINAL_THRESHOLD = Decimal("0.15")  # 15%

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
    ):
        self.supplier_price = supplier_price
        self.platform_price = platform_price
        self.estimated_shipping_cost = estimated_shipping_cost
        self.platform_commission_rate = platform_commission_rate
        self.payment_fee_rate = payment_fee_rate
        self.return_rate_assumption = return_rate_assumption

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

        # Determine profitability
        margin_ratio = self.estimated_margin / platform_price if platform_price > 0 else Decimal("0")
        if margin_ratio >= PricingConfig.PROFITABLE_THRESHOLD:
            self.profitability_decision = ProfitabilityDecision.PROFITABLE
        elif margin_ratio >= PricingConfig.MARGINAL_THRESHOLD:
            self.profitability_decision = ProfitabilityDecision.MARGINAL
        else:
            self.profitability_decision = ProfitabilityDecision.UNPROFITABLE

        # Recommended price (add 20% buffer to break-even)
        break_even = self.total_cost / (1 - PricingConfig.PROFITABLE_THRESHOLD)
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
    ) -> PricingResult:
        """Calculate pricing and profitability."""
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
        )

        logger.info(
            "pricing_calculated",
            supplier_price=float(supplier_price),
            platform_price=float(platform_price),
            margin_percentage=float(result.margin_percentage),
            decision=result.profitability_decision.value,
        )

        return result

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
