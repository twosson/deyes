"""Test risk rules engine."""
from decimal import Decimal

from app.core.enums import RiskDecision
from app.services.risk_rules import RiskRulesEngine


def test_brand_keyword_detection():
    """Test brand keyword detection."""
    engine = RiskRulesEngine()

    product_data = {
        "title": "Nike Air Max Running Shoes",
        "category": "shoes",
        "platform_price": 89.99,
    }

    result = engine.assess(product_data)

    assert result.score >= 50
    assert result.decision in [RiskDecision.REVIEW, RiskDecision.REJECT]
    assert len(result.rule_hits) > 0
    assert any("nike" in hit["reason"].lower() for hit in result.rule_hits)


def test_forbidden_category_detection():
    """Test forbidden category detection."""
    engine = RiskRulesEngine()

    product_data = {
        "title": "Tactical Weapon Accessory",
        "category": "weapon",
        "platform_price": 49.99,
    }

    result = engine.assess(product_data)

    assert result.score >= 100
    assert result.decision == RiskDecision.REJECT
    assert len(result.rule_hits) > 0


def test_clean_product_passes():
    """Test that clean products pass risk assessment."""
    engine = RiskRulesEngine()

    product_data = {
        "title": "Wireless Charging Pad",
        "category": "electronics",
        "platform_price": 24.99,
    }

    result = engine.assess(product_data)

    assert result.score < 40
    assert result.decision == RiskDecision.PASS
    assert len(result.rule_hits) == 0


def test_suspicious_price_detection():
    """Test suspicious price detection."""
    engine = RiskRulesEngine()

    product_data = {
        "title": "Authentic Luxury Watch Premium",
        "category": "watches",
        "platform_price": 5.99,
    }

    result = engine.assess(product_data)

    assert result.score >= 30
    assert result.decision in [RiskDecision.REVIEW, RiskDecision.REJECT]
