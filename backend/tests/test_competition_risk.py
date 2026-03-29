"""Tests for competition density and demand discovery risk assessment."""
import pytest
from app.services.risk_rules import (
    CompetitionDensityRule,
    DemandDiscoveryRiskRule,
    RiskAssessmentResult,
    RiskRulesEngine,
)
from app.core.enums import RiskDecision


class TestCompetitionDensityRule:
    """Test competition density rule."""

    def test_high_competition(self):
        """Test high competition density."""
        rule = CompetitionDensityRule()
        product_data = {"competition_density": "high"}

        hit, reason = rule.evaluate(product_data)

        assert hit is True
        assert "high" in reason.lower()
        assert rule.weight == 80

    def test_medium_competition(self):
        """Test medium competition density."""
        rule = CompetitionDensityRule()
        product_data = {"competition_density": "medium"}

        hit, reason = rule.evaluate(product_data)

        assert hit is True
        assert "medium" in reason.lower()
        assert rule.weight == 50

    def test_low_competition(self):
        """Test low competition density."""
        rule = CompetitionDensityRule()
        product_data = {"competition_density": "low"}

        hit, reason = rule.evaluate(product_data)

        assert hit is True
        assert "low" in reason.lower()
        assert rule.weight == 20

    def test_unknown_competition(self):
        """Test unknown competition density."""
        rule = CompetitionDensityRule()
        product_data = {"competition_density": "unknown"}

        hit, reason = rule.evaluate(product_data)

        assert hit is True
        assert "unknown" in reason.lower()
        assert rule.weight == 30

    def test_missing_competition_density(self):
        """Test missing competition density defaults to unknown."""
        rule = CompetitionDensityRule()
        product_data = {}

        hit, reason = rule.evaluate(product_data)

        assert hit is True
        assert rule.weight == 30




class TestDemandDiscoveryRiskRule:
    """Test demand discovery quality rule."""

    def test_user_discovery_has_no_extra_risk(self):
        """User-provided validated keywords should have zero additional risk."""
        rule = DemandDiscoveryRiskRule()
        product_data = {
            "discovery_mode": "user",
            "degraded": False,
            "fallback_used": False,
        }

        hit, reason = rule.evaluate(product_data)

        assert hit is False
        assert reason is None
        assert rule.weight == 0

    def test_generated_discovery_has_moderate_risk(self):
        """Generated keywords should add moderate discovery risk."""
        rule = DemandDiscoveryRiskRule()
        product_data = {
            "discovery_mode": "generated",
            "degraded": False,
            "fallback_used": False,
        }

        hit, reason = rule.evaluate(product_data)

        assert hit is True
        assert "discovery_mode=generated" in reason
        assert rule.weight == 10

    def test_fallback_discovery_increases_scrutiny(self):
        """Fallback sourcing should receive higher risk weighting."""
        rule = DemandDiscoveryRiskRule()
        product_data = {
            "discovery_mode": "fallback",
            "degraded": False,
            "fallback_used": True,
        }

        hit, reason = rule.evaluate(product_data)

        assert hit is True
        assert "discovery_mode=fallback" in reason
        assert "fallback_used=True (+5)" in reason
        assert rule.weight == 30

    def test_degraded_discovery_adds_penalty(self):
        """Degraded discovery should add extra risk points."""
        rule = DemandDiscoveryRiskRule()
        product_data = {
            "discovery_mode": "generated",
            "degraded": True,
            "fallback_used": False,
        }

        hit, reason = rule.evaluate(product_data)

        assert hit is True
        assert "degraded=True (+10)" in reason
        assert rule.weight == 20

    def test_none_discovery_is_highest_risk(self):
        """Missing validated keywords should be treated as highest risk."""
        rule = DemandDiscoveryRiskRule()
        product_data = {
            "discovery_mode": "none",
            "degraded": True,
            "fallback_used": False,
        }

        hit, reason = rule.evaluate(product_data)

        assert hit is True
        assert "discovery_mode=none" in reason
        assert rule.weight == 50



class TestRiskAssessmentResultCombined:
    """Test combined risk assessment."""

    def test_combined_scoring(self):
        """Test combined compliance and competition scoring."""
        result = RiskAssessmentResult()

        # Add compliance risk (brand keyword = 50)
        from app.services.risk_rules import BrandKeywordRule
        brand_rule = BrandKeywordRule()
        brand_rule.weight = 50
        result.add_hit(brand_rule, "Brand detected")

        # Add competition risk (high = 80)
        comp_rule = CompetitionDensityRule()
        comp_rule.weight = 80
        result.add_hit(comp_rule, "High competition")

        result.finalize()

        # Verify scores
        assert result.compliance_score == 50
        assert result.competition_score == 80
        # Total = 50 * 0.6 + 80 * 0.4 = 30 + 32 = 62
        assert result.total_score == 62
        assert result.score == 62
        assert result.decision == RiskDecision.REVIEW

    def test_discovery_risk_accumulates_with_competition_risk(self):
        """Discovery quality risk should add to competition score."""
        result = RiskAssessmentResult()

        comp_rule = CompetitionDensityRule()
        comp_rule.weight = 50
        result.add_hit(comp_rule, "Medium competition")

        discovery_rule = DemandDiscoveryRiskRule()
        discovery_rule.weight = 30
        result.add_hit(discovery_rule, "Fallback discovery")

        result.finalize()

        assert result.competition_score == 80
        assert result.total_score == 32
        assert result.decision == RiskDecision.PASS

    def test_high_compliance_low_competition(self):
        """Test high compliance risk with low competition."""
        result = RiskAssessmentResult()

        # High compliance risk (100)
        from app.services.risk_rules import ForbiddenCategoryRule
        forbidden_rule = ForbiddenCategoryRule()
        forbidden_rule.weight = 100
        result.add_hit(forbidden_rule, "Forbidden category")

        # Low competition risk (20)
        comp_rule = CompetitionDensityRule()
        comp_rule.weight = 20
        result.add_hit(comp_rule, "Low competition")

        result.finalize()

        # Total = 100 * 0.6 + 20 * 0.4 = 60 + 8 = 68
        assert result.total_score == 68
        assert result.decision == RiskDecision.REVIEW

    def test_low_compliance_high_competition(self):
        """Test low compliance risk with high competition."""
        result = RiskAssessmentResult()

        # High competition risk (80)
        comp_rule = CompetitionDensityRule()
        comp_rule.weight = 80
        result.add_hit(comp_rule, "High competition")

        result.finalize()

        # Total = 0 * 0.6 + 80 * 0.4 = 0 + 32 = 32
        assert result.total_score == 32
        assert result.decision == RiskDecision.PASS

    def test_both_high_risk(self):
        """Test both compliance and competition high risk."""
        result = RiskAssessmentResult()

        # High compliance risk (100)
        from app.services.risk_rules import ForbiddenCategoryRule
        forbidden_rule = ForbiddenCategoryRule()
        forbidden_rule.weight = 100
        result.add_hit(forbidden_rule, "Forbidden category")

        # High competition risk (80)
        comp_rule = CompetitionDensityRule()
        comp_rule.weight = 80
        result.add_hit(comp_rule, "High competition")

        result.finalize()

        # Total = 100 * 0.6 + 80 * 0.4 = 60 + 32 = 92
        assert result.total_score == 92
        assert result.decision == RiskDecision.REJECT

    def test_both_low_risk(self):
        """Test both compliance and competition low risk."""
        result = RiskAssessmentResult()

        # Low competition risk (20)
        comp_rule = CompetitionDensityRule()
        comp_rule.weight = 20
        result.add_hit(comp_rule, "Low competition")

        result.finalize()

        # Total = 0 * 0.6 + 20 * 0.4 = 0 + 8 = 8
        assert result.total_score == 8
        assert result.decision == RiskDecision.PASS


class TestRiskRulesEngineWithCompetition:
    """Test risk rules engine with competition assessment."""

    def test_engine_with_competition_enabled(self):
        """Test engine with competition risk enabled."""
        engine = RiskRulesEngine(
            enable_competition_risk=True,
            enable_demand_discovery_risk=False,
        )

        product_data = {
            "title": "Generic phone case",
            "category": "electronics",
            "platform_price": 15.0,
            "competition_density": "high",
        }

        result = engine.assess(product_data)

        # Should have competition risk
        assert result.competition_score == 80
        assert result.total_score == 32  # 0 * 0.6 + 80 * 0.4

    def test_engine_with_competition_disabled(self):
        """Test engine with competition risk disabled."""
        engine = RiskRulesEngine(
            enable_competition_risk=False,
            enable_demand_discovery_risk=False,
        )

        product_data = {
            "title": "Generic phone case",
            "category": "electronics",
            "platform_price": 15.0,
            "competition_density": "high",
        }

        result = engine.assess(product_data)

        # Should NOT have competition risk
        assert result.competition_score == 0
        assert result.total_score == 0

    def test_engine_combined_assessment(self):
        """Test engine with both compliance and competition risks."""
        engine = RiskRulesEngine(
            enable_competition_risk=True,
            enable_demand_discovery_risk=False,
        )

        product_data = {
            "title": "Nike shoes",  # Brand keyword
            "category": "fashion",
            "platform_price": 50.0,
            "competition_density": "high",
        }

        result = engine.assess(product_data)

        # Should have both risks
        assert result.compliance_score == 50  # Brand keyword
        assert result.competition_score == 80  # High competition
        # Total = 50 * 0.6 + 80 * 0.4 = 30 + 32 = 62
        assert result.total_score == 62
        assert result.decision == RiskDecision.REVIEW

    def test_result_to_dict(self):
        """Test result serialization includes all scores."""
        engine = RiskRulesEngine(
            enable_competition_risk=True,
            enable_demand_discovery_risk=False,
        )

        product_data = {
            "title": "Phone case",
            "category": "electronics",
            "platform_price": 15.0,
            "competition_density": "medium",
        }

        result = engine.assess(product_data)
        result_dict = result.to_dict()

        assert "score" in result_dict
        assert "compliance_score" in result_dict
        assert "competition_score" in result_dict
        assert "decision" in result_dict
        assert "rule_hits" in result_dict

        assert result_dict["compliance_score"] == 0
        assert result_dict["competition_score"] == 50
        assert result_dict["score"] == 20  # 0 * 0.6 + 50 * 0.4

    def test_engine_with_demand_discovery_enabled(self):
        """Test engine with demand discovery risk enabled."""
        engine = RiskRulesEngine(
            enable_competition_risk=True,
            enable_demand_discovery_risk=True,
        )

        product_data = {
            "title": "Generic phone case",
            "category": "electronics",
            "platform_price": 15.0,
            "competition_density": "medium",
            "discovery_mode": "fallback",
            "degraded": True,
            "fallback_used": True,
        }

        result = engine.assess(product_data)

        # Competition: medium (50) + fallback (25) + degraded (+10) + fallback_used (+5) = 90
        assert result.competition_score == 90
        # Total = 0 * 0.6 + 90 * 0.4 = 36
        assert result.total_score == 36
        assert result.decision == RiskDecision.PASS

    def test_engine_with_demand_discovery_disabled(self):
        """Test engine with demand discovery risk disabled."""
        engine = RiskRulesEngine(
            enable_competition_risk=True,
            enable_demand_discovery_risk=False,
        )

        product_data = {
            "title": "Generic phone case",
            "category": "electronics",
            "platform_price": 15.0,
            "competition_density": "medium",
            "discovery_mode": "fallback",
            "degraded": True,
            "fallback_used": True,
        }

        result = engine.assess(product_data)

        # Only competition density should be counted
        assert result.competition_score == 50
        assert result.total_score == 20
        assert result.decision == RiskDecision.PASS
