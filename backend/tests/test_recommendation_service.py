"""Tests for recommendation service."""
from decimal import Decimal

import pytest

from app.core.enums import ProfitabilityDecision, RiskDecision
from app.services.recommendation_service import RecommendationService


@pytest.fixture
def recommendation_service():
    """Create recommendation service instance."""
    return RecommendationService()


class TestCalculateRecommendationScore:
    """Tests for calculate_recommendation_score method."""

    def test_high_quality_product(self, recommendation_service):
        """Test recommendation score for high-quality product."""
        # High priority, high margin, low risk, good supplier
        score, breakdown = recommendation_service.calculate_recommendation_score(
            priority_score=0.9,  # 90% priority
            margin_percentage=Decimal("45.0"),  # 45% margin
            risk_score=10,  # Low risk
            supplier_confidence=Decimal("0.95"),  # 95% confidence
        )

        # Expected: 0.9*40 + 0.45*30 + 0.9*20 + 0.95*10 = 36 + 13.5 + 18 + 9.5 = 77
        assert score >= 75.0  # HIGH level
        assert breakdown["priority_component"] == 36.0
        assert breakdown["margin_component"] == 13.5
        assert breakdown["risk_component"] == 18.0
        assert breakdown["supplier_component"] == 9.5
        assert breakdown["total_score"] == 77.0

    def test_low_quality_product(self, recommendation_service):
        """Test recommendation score for low-quality product."""
        # Low priority, low margin, high risk, poor supplier
        score, breakdown = recommendation_service.calculate_recommendation_score(
            priority_score=0.2,  # 20% priority
            margin_percentage=Decimal("15.0"),  # 15% margin
            risk_score=80,  # High risk
            supplier_confidence=Decimal("0.3"),  # 30% confidence
        )

        # Expected: 0.2*40 + 0.15*30 + 0.2*20 + 0.3*10 = 8 + 4.5 + 4 + 3 = 19.5
        assert score < 60.0  # LOW level
        assert breakdown["priority_component"] == 8.0
        assert breakdown["margin_component"] == 4.5
        assert breakdown["risk_component"] == 4.0
        assert breakdown["supplier_component"] == 3.0
        assert breakdown["total_score"] == 19.5

    def test_medium_quality_product(self, recommendation_service):
        """Test recommendation score for medium-quality product."""
        # Medium priority, medium margin, medium risk, medium supplier
        score, breakdown = recommendation_service.calculate_recommendation_score(
            priority_score=0.6,  # 60% priority
            margin_percentage=Decimal("35.0"),  # 35% margin
            risk_score=40,  # Medium risk
            supplier_confidence=Decimal("0.7"),  # 70% confidence
        )

        # Expected: 0.6*40 + 0.35*30 + 0.6*20 + 0.7*10 = 24 + 10.5 + 12 + 7 = 53.5
        # This is actually LOW level (< 60), not MEDIUM
        assert score < 60.0  # LOW level
        assert breakdown["priority_component"] == 24.0
        assert breakdown["margin_component"] == 10.5
        assert breakdown["risk_component"] == 12.0
        assert breakdown["supplier_component"] == 7.0
        assert breakdown["total_score"] == 53.5

    def test_medium_level_product(self, recommendation_service):
        """Test recommendation score for MEDIUM level product."""
        # Higher values to reach MEDIUM level (60-74)
        score, breakdown = recommendation_service.calculate_recommendation_score(
            priority_score=0.75,  # 75% priority
            margin_percentage=Decimal("38.0"),  # 38% margin
            risk_score=25,  # Low-medium risk
            supplier_confidence=Decimal("0.85"),  # 85% confidence
        )

        # Expected: 0.75*40 + 0.38*30 + 0.75*20 + 0.85*10 = 30 + 11.4 + 15 + 8.5 = 64.9
        assert 60.0 <= score < 75.0  # MEDIUM level
        assert breakdown["priority_component"] == 30.0
        assert breakdown["margin_component"] == 11.4
        assert breakdown["risk_component"] == 15.0
        assert breakdown["supplier_component"] == 8.5
        assert breakdown["total_score"] == 64.9

    def test_missing_values(self, recommendation_service):
        """Test recommendation score with missing values."""
        # Only priority score available
        score, breakdown = recommendation_service.calculate_recommendation_score(
            priority_score=0.8,
            margin_percentage=None,
            risk_score=None,
            supplier_confidence=None,
        )

        # Expected: 0.8*40 + 0 + 0 + 0 = 32
        assert score == 32.0
        assert breakdown["priority_component"] == 32.0
        assert breakdown["margin_component"] == 0.0
        assert breakdown["risk_component"] == 0.0
        assert breakdown["supplier_component"] == 0.0

    def test_demand_context_adjusts_recommendation_score(self, recommendation_service):
        """Demand context should adjust the recommendation score itself."""
        baseline_score, baseline_breakdown = recommendation_service.calculate_recommendation_score(
            priority_score=0.75,
            margin_percentage=Decimal("38.0"),
            risk_score=25,
            supplier_confidence=Decimal("0.85"),
        )

        conservative_score, conservative_breakdown = recommendation_service.calculate_recommendation_score(
            priority_score=0.75,
            margin_percentage=Decimal("38.0"),
            risk_score=25,
            supplier_confidence=Decimal("0.85"),
            discovery_mode="fallback",
            degraded=True,
            fallback_used=True,
        )

        confident_score, confident_breakdown = recommendation_service.calculate_recommendation_score(
            priority_score=0.75,
            margin_percentage=Decimal("38.0"),
            risk_score=25,
            supplier_confidence=Decimal("0.85"),
            discovery_mode="user",
            degraded=False,
            fallback_used=False,
        )

        assert baseline_breakdown["demand_adjustment"] == 0.0
        assert conservative_breakdown["demand_adjustment"] == -6.0
        assert confident_breakdown["demand_adjustment"] == 3.0
        assert conservative_score < baseline_score < confident_score

    """Tests for generate_recommendation_reasons method."""

    def test_high_profit_product(self, recommendation_service):
        """Test reasons for high-profit product."""
        reasons = recommendation_service.generate_recommendation_reasons(
            margin_percentage=Decimal("45.0"),
            seasonal_boost=1.5,
            competition_density="low",
            risk_decision=RiskDecision.PASS,
            sales_count=8000,
            rating=Decimal("4.8"),
            profitability_decision=ProfitabilityDecision.PROFITABLE,
        )

        assert any("高利润率产品" in r for r in reasons)
        assert any("即将到来的节假日" in r for r in reasons)
        assert any("低竞争蓝海市场" in r for r in reasons)
        assert any("合规风险低" in r for r in reasons)
        assert any("高销量验证" in r for r in reasons)
        assert any("高评分产品" in r for r in reasons)

    def test_marginal_profit_product(self, recommendation_service):
        """Test reasons for marginal profit product."""
        reasons = recommendation_service.generate_recommendation_reasons(
            margin_percentage=Decimal("25.0"),
            seasonal_boost=1.0,
            competition_density="medium",
            risk_decision=RiskDecision.REVIEW,
            sales_count=500,
            rating=Decimal("4.2"),
            profitability_decision=ProfitabilityDecision.MARGINAL,
        )

        assert any("边际利润率" in r for r in reasons)
        assert any("中等竞争市场" in r for r in reasons)
        assert any("需人工审核风险" in r for r in reasons)

    def test_unprofitable_product(self, recommendation_service):
        """Test reasons for unprofitable product."""
        reasons = recommendation_service.generate_recommendation_reasons(
            margin_percentage=Decimal("10.0"),
            seasonal_boost=1.0,
            competition_density="high",
            risk_decision=RiskDecision.REJECT,
            sales_count=50,
            rating=Decimal("3.2"),
            profitability_decision=ProfitabilityDecision.UNPROFITABLE,
        )

        assert any("利润率偏低" in r for r in reasons)
        assert any("高竞争红海市场" in r for r in reasons)
        assert any("高风险产品" in r for r in reasons)
        assert any("评分偏低" in r for r in reasons)

    def test_seasonal_boost_reasons(self, recommendation_service):
        """Test seasonal boost reasons."""
        # High boost
        reasons_high = recommendation_service.generate_recommendation_reasons(
            margin_percentage=Decimal("35.0"),
            seasonal_boost=1.5,
            competition_density="low",
            risk_decision=RiskDecision.PASS,
            sales_count=1000,
            rating=Decimal("4.5"),
            profitability_decision=ProfitabilityDecision.PROFITABLE,
        )
        assert any("即将到来的节假日" in r for r in reasons_high)

        # Medium boost
        reasons_medium = recommendation_service.generate_recommendation_reasons(
            margin_percentage=Decimal("35.0"),
            seasonal_boost=1.15,
            competition_density="low",
            risk_decision=RiskDecision.PASS,
            sales_count=1000,
            rating=Decimal("4.5"),
            profitability_decision=ProfitabilityDecision.PROFITABLE,
        )
        assert any("季节性需求增长" in r for r in reasons_medium)
    def test_demand_discovery_reasons(self, recommendation_service):
        """Test reasons include demand discovery context."""
        reasons = recommendation_service.generate_recommendation_reasons(
            margin_percentage=Decimal("32.0"),
            seasonal_boost=1.0,
            competition_density="medium",
            risk_decision=RiskDecision.REVIEW,
            sales_count=300,
            rating=Decimal("4.1"),
            profitability_decision=ProfitabilityDecision.MARGINAL,
            discovery_mode="fallback",
            degraded=True,
            fallback_used=True,
        )

        assert any("使用回退关键词发现候选" in r for r in reasons)
        assert any("需求发现过程存在降级" in r for r in reasons)

    def test_user_discovery_reason(self, recommendation_service):
        """Test user discovery adds confidence reason."""
        reasons = recommendation_service.generate_recommendation_reasons(
            margin_percentage=Decimal("40.0"),
            seasonal_boost=1.0,
            competition_density="low",
            risk_decision=RiskDecision.PASS,
            sales_count=1000,
            rating=Decimal("4.5"),
            profitability_decision=ProfitabilityDecision.PROFITABLE,
            discovery_mode="user",
            degraded=False,
            fallback_used=False,
        )

        assert any("需求关键词已人工确认" in r for r in reasons)


class TestGetRecommendationLevel:
    """Tests for get_recommendation_level method."""

    def test_high_level(self, recommendation_service):
        """Test HIGH recommendation level."""
        assert recommendation_service.get_recommendation_level(75.0) == "HIGH"
        assert recommendation_service.get_recommendation_level(85.0) == "HIGH"
        assert recommendation_service.get_recommendation_level(100.0) == "HIGH"

    def test_medium_level(self, recommendation_service):
        """Test MEDIUM recommendation level."""
        assert recommendation_service.get_recommendation_level(60.0) == "MEDIUM"
        assert recommendation_service.get_recommendation_level(70.0) == "MEDIUM"
        assert recommendation_service.get_recommendation_level(74.9) == "MEDIUM"

    def test_low_level(self, recommendation_service):
        """Test LOW recommendation level."""
        assert recommendation_service.get_recommendation_level(0.0) == "LOW"
        assert recommendation_service.get_recommendation_level(30.0) == "LOW"
        assert recommendation_service.get_recommendation_level(59.9) == "LOW"


class TestExplainScoreBreakdown:
    """Tests for explain_score_breakdown method."""

    def test_explain_breakdown(self, recommendation_service):
        """Test score breakdown explanation."""
        breakdown = {
            "priority_component": 36.0,
            "margin_component": 13.5,
            "risk_component": 18.0,
            "supplier_component": 9.5,
            "total_score": 77.0,
        }

        explained = recommendation_service.explain_score_breakdown(breakdown)

        assert explained["total_score"] == 77.0
        assert len(explained["components"]) == 4

        # Check priority component
        priority = explained["components"][0]
        assert priority["name"] == "priority_score"
        assert priority["value"] == 36.0
        assert priority["weight"] == "40%"
        assert "季节性" in priority["description"]

        # Check margin component
        margin = explained["components"][1]
        assert margin["name"] == "margin_score"
        assert margin["value"] == 13.5
        assert margin["weight"] == "30%"

        # Check risk component
        risk = explained["components"][2]
        assert risk["name"] == "risk_score_inverse"
        assert risk["value"] == 18.0
        assert risk["weight"] == "20%"

        # Check supplier component
        supplier = explained["components"][3]
        assert supplier["name"] == "supplier_quality"
        assert supplier["value"] == 9.5
        assert supplier["weight"] == "10%"
