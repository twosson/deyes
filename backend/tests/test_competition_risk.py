"""Tests for competition density risk assessment (Phase 2)."""
import pytest
from app.services.risk_rules import (
    CompetitionDensityRule,
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


class TestRiskAssessmentResultCombined:
    """Test combined risk assessment (Phase 2)."""

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
        assert result.decision == RiskDecision.REVIEW

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

        # No compliance risk (0)

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

        # No compliance risk (0)

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
        engine = RiskRulesEngine(enable_competition_risk=True)

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
        engine = RiskRulesEngine(enable_competition_risk=False)

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
        engine = RiskRulesEngine(enable_competition_risk=True)

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
        engine = RiskRulesEngine(enable_competition_risk=True)

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
