"""Recommendation service for candidate products.

Provides intelligent recommendations based on:
- Priority score (seasonal boost, sales, rating, competition)
- Margin percentage (profitability)
- Risk score (compliance and competition risks)
- Supplier quality (confidence score)

Recommendation score formula (0-100):
    recommendation_score = (
        priority_score * 40 +           # 优先级 40%
        margin_score * 30 +             # 利润率 30%
        risk_score_inverse * 20 +       # 风险反向 20%
        supplier_quality * 10           # 供应商质量 10%
    )
"""
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional
from uuid import UUID

from app.core.enums import ProfitabilityDecision, RiskDecision
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class RecommendationResult:
    """Recommendation result for a candidate product."""

    candidate_id: UUID
    recommendation_score: float  # 0-100
    recommendation_level: str  # HIGH/MEDIUM/LOW
    score_breakdown: dict
    reasons: list[str]


class RecommendationService:
    """Service for generating product recommendations."""

    # Recommendation level thresholds
    HIGH_THRESHOLD = 75.0
    MEDIUM_THRESHOLD = 60.0

    # Demand discovery confidence adjustments (2026-03-28)
    DISCOVERY_MODE_ADJUSTMENTS = {
        "user": 3.0,
        "seed_pool": 1.0,
        "generated": 1.0,
        "exploration": 0.0,
        "fallback": -4.0,
        "none": -6.0,
    }
    DEGRADED_PENALTY = -2.0
    FALLBACK_USED_PENALTY = -1.0

    @classmethod
    def get_demand_context_adjustment(
        cls,
        discovery_mode: Optional[str] = None,
        degraded: bool = False,
        fallback_used: bool = False,
    ) -> float:
        """Get additive recommendation adjustment from demand context."""
        adjustment = 0.0

        if discovery_mode:
            adjustment += cls.DISCOVERY_MODE_ADJUSTMENTS.get(discovery_mode.lower(), 0.0)

        if degraded:
            adjustment += cls.DEGRADED_PENALTY

        if fallback_used and (not discovery_mode or discovery_mode.lower() != "fallback"):
            adjustment += cls.FALLBACK_USED_PENALTY

        return adjustment

    def calculate_recommendation_score(
        self,
        priority_score: Optional[float],
        margin_percentage: Optional[Decimal],
        risk_score: Optional[int],
        supplier_confidence: Optional[Decimal],
        discovery_mode: Optional[str] = None,
        degraded: bool = False,
        fallback_used: bool = False,
    ) -> tuple[float, dict]:
        """Calculate recommendation score (0-100).

        Args:
            priority_score: Priority score from product selector (0-1)
            margin_percentage: Profit margin percentage (0-100)
            risk_score: Risk assessment score (0-100)
            supplier_confidence: Best supplier confidence score (0-1)
            discovery_mode: Demand discovery mode (user/generated/fallback/none)
            degraded: Whether demand discovery was degraded
            fallback_used: Whether fallback seeds were used

        Returns:
            Tuple of (recommendation_score, score_breakdown)
        """
        # Component 1: Priority score (40%)
        # Already includes seasonal boost, sales, rating, competition
        priority_component = 0.0
        if priority_score is not None:
            priority_component = float(priority_score) * 40.0

        # Component 2: Margin score (30%)
        margin_component = 0.0
        if margin_percentage is not None:
            # Normalize margin_percentage (0-100) to 0-1, then scale to 30
            margin_normalized = min(float(margin_percentage) / 100.0, 1.0)
            margin_component = margin_normalized * 30.0

        # Component 3: Risk score inverse (20%)
        # Lower risk = higher score
        risk_component = 0.0
        if risk_score is not None:
            risk_inverse = (100 - risk_score) / 100.0
            risk_component = risk_inverse * 20.0

        # Component 4: Supplier quality (10%)
        supplier_component = 0.0
        if supplier_confidence is not None:
            supplier_component = float(supplier_confidence) * 10.0

        # Total score
        total_score = (
            priority_component + margin_component + risk_component + supplier_component
        )

        # Component 5: Demand discovery confidence adjustment (2026-03-28)
        demand_adjustment = self.get_demand_context_adjustment(
            discovery_mode=discovery_mode,
            degraded=degraded,
            fallback_used=fallback_used,
        )
        total_score += demand_adjustment
        total_score = max(0.0, min(100.0, total_score))  # Clamp to 0-100

        # Build breakdown
        breakdown = {
            "priority_component": round(priority_component, 2),
            "margin_component": round(margin_component, 2),
            "risk_component": round(risk_component, 2),
            "supplier_component": round(supplier_component, 2),
            "demand_adjustment": round(demand_adjustment, 2),
            "total_score": round(total_score, 2),
        }

        return total_score, breakdown

    def generate_recommendation_reasons(
        self,
        margin_percentage: Optional[Decimal],
        seasonal_boost: Optional[float],
        competition_density: Optional[str],
        risk_decision: Optional[RiskDecision],
        sales_count: Optional[int],
        rating: Optional[Decimal],
        profitability_decision: Optional[ProfitabilityDecision],
        discovery_mode: Optional[str] = None,
        degraded: bool = False,
        fallback_used: bool = False,
    ) -> list[str]:
        """Generate human-readable recommendation reasons.

        Args:
            margin_percentage: Profit margin percentage
            seasonal_boost: Seasonal boost factor (1.0-2.0)
            competition_density: Competition density (low/medium/high)
            risk_decision: Risk assessment decision
            sales_count: Product sales count
            rating: Product rating (0-5)
            profitability_decision: Profitability decision
            discovery_mode: Demand discovery mode (user/generated/fallback/none)
            degraded: Whether demand discovery was degraded
            fallback_used: Whether fallback seeds were used

        Returns:
            List of recommendation reasons
        """
        reasons = []

        # 1. Profitability reason
        if profitability_decision == ProfitabilityDecision.PROFITABLE:
            if margin_percentage and margin_percentage >= 40:
                reasons.append(f"高利润率产品（{float(margin_percentage):.1f}%）")
            elif margin_percentage and margin_percentage >= 35:
                reasons.append(f"良好利润率（{float(margin_percentage):.1f}%）")
        elif profitability_decision == ProfitabilityDecision.MARGINAL:
            reasons.append(f"边际利润率（{float(margin_percentage):.1f}%），需优化定价")
        elif profitability_decision == ProfitabilityDecision.UNPROFITABLE:
            reasons.append(f"利润率偏低（{float(margin_percentage):.1f}%），不建议上架")

        # 2. Seasonal reason
        if seasonal_boost and seasonal_boost >= 1.3:
            boost_pct = (seasonal_boost - 1.0) * 100
            reasons.append(f"即将到来的节假日，需求旺盛（+{boost_pct:.0f}%）")
        elif seasonal_boost and seasonal_boost >= 1.1:
            boost_pct = (seasonal_boost - 1.0) * 100
            reasons.append(f"季节性需求增长（+{boost_pct:.0f}%）")

        # 3. Competition density reason
        if competition_density == "low":
            reasons.append("低竞争蓝海市场")
        elif competition_density == "medium":
            reasons.append("中等竞争市场")
        elif competition_density == "high":
            reasons.append("高竞争红海市场，需谨慎评估")

        # 4. Demand discovery reason
        if discovery_mode == "user":
            reasons.append("需求关键词已人工确认")
        elif discovery_mode == "seed_pool":
            reasons.append("基于品类种子池完成需求发现")
        elif discovery_mode == "generated":
            reasons.append("基于生成关键词完成需求发现（离线）")
        elif discovery_mode == "exploration":
            reasons.append("基于探索模式自主发现候选，建议人工复核")
        elif discovery_mode == "fallback":
            reasons.append("使用回退关键词发现候选，建议谨慎验证")
        elif discovery_mode == "none":
            reasons.append("缺少有效需求关键词支撑，建议人工复核")

        if degraded:
            reasons.append("需求发现过程存在降级，建议补充验证")
        elif fallback_used and discovery_mode != "fallback":
            reasons.append("需求发现使用了部分回退信号")

        # 5. Risk reason
        if risk_decision == RiskDecision.PASS:
            reasons.append("合规风险低，可安全上架")
        elif risk_decision == RiskDecision.REVIEW:
            reasons.append("需人工审核风险")
        elif risk_decision == RiskDecision.REJECT:
            reasons.append("高风险产品，不建议上架")

        # 6. Sales reason
        if sales_count and sales_count >= 5000:
            reasons.append(f"高销量验证（{sales_count}单）")
        elif sales_count and sales_count >= 1000:
            reasons.append(f"中等销量（{sales_count}单）")
        elif sales_count and sales_count >= 100:
            reasons.append(f"有一定销量基础（{sales_count}单）")

        # 7. Rating reason
        if rating and rating >= 4.5:
            reasons.append(f"高评分产品（{float(rating):.1f}星）")
        elif rating and rating >= 4.0:
            reasons.append(f"良好评分（{float(rating):.1f}星）")
        elif rating and rating < 3.5:
            reasons.append(f"评分偏低（{float(rating):.1f}星），需注意质量")

        return reasons

    def get_recommendation_level(self, score: float) -> str:
        """Determine recommendation level based on score.

        Args:
            score: Recommendation score (0-100)

        Returns:
            Recommendation level: HIGH (>=75), MEDIUM (60-74), LOW (<60)
        """
        if score >= self.HIGH_THRESHOLD:
            return "HIGH"
        elif score >= self.MEDIUM_THRESHOLD:
            return "MEDIUM"
        else:
            return "LOW"

    def explain_score_breakdown(
        self,
        score_breakdown: dict,
    ) -> dict:
        """Explain score breakdown with component descriptions.

        Args:
            score_breakdown: Score breakdown from calculate_recommendation_score

        Returns:
            Enhanced breakdown with descriptions
        """
        return {
            "total_score": score_breakdown["total_score"],
            "components": [
                {
                    "name": "priority_score",
                    "value": score_breakdown["priority_component"],
                    "weight": "40%",
                    "description": "综合优先级（季节性、销量、评分、竞争密度）",
                },
                {
                    "name": "margin_score",
                    "value": score_breakdown["margin_component"],
                    "weight": "30%",
                    "description": "利润率评分",
                },
                {
                    "name": "risk_score_inverse",
                    "value": score_breakdown["risk_component"],
                    "weight": "20%",
                    "description": "风险反向评分（低风险=高分）",
                },
                {
                    "name": "supplier_quality",
                    "value": score_breakdown["supplier_component"],
                    "weight": "10%",
                    "description": "供应商质量评分",
                },
            ],
        }
