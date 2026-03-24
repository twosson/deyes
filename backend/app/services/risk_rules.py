"""Risk assessment rules engine."""
import re
from typing import Optional

from app.core.enums import RiskDecision
from app.core.logging import get_logger

logger = get_logger(__name__)


class RiskRule:
    """Base class for risk rules."""

    def __init__(self, name: str, weight: int, description: str):
        self.name = name
        self.weight = weight
        self.description = description

    def evaluate(self, product_data: dict) -> tuple[bool, Optional[str]]:
        """Evaluate rule. Returns (hit, reason)."""
        raise NotImplementedError


class BrandKeywordRule(RiskRule):
    """Detect brand keywords in title."""

    BRAND_KEYWORDS = [
        "nike",
        "adidas",
        "apple",
        "samsung",
        "sony",
        "gucci",
        "prada",
        "louis vuitton",
        "chanel",
        "rolex",
        "disney",
        "marvel",
        "pokemon",
        "hello kitty",
        "lego",
    ]

    def __init__(self):
        super().__init__(
            name="brand_keyword",
            weight=50,
            description="Detects known brand keywords",
        )

    def evaluate(self, product_data: dict) -> tuple[bool, Optional[str]]:
        title = product_data.get("title", "").lower()
        for brand in self.BRAND_KEYWORDS:
            if brand in title:
                return True, f"Brand keyword detected: {brand}"
        return False, None


class ForbiddenCategoryRule(RiskRule):
    """Detect forbidden product categories."""

    FORBIDDEN_CATEGORIES = [
        "weapon",
        "drug",
        "medicine",
        "tobacco",
        "alcohol",
        "adult",
        "counterfeit",
    ]

    def __init__(self):
        super().__init__(
            name="forbidden_category",
            weight=100,
            description="Detects forbidden product categories",
        )

    def evaluate(self, product_data: dict) -> tuple[bool, Optional[str]]:
        category = product_data.get("category", "").lower()
        title = product_data.get("title", "").lower()

        for forbidden in self.FORBIDDEN_CATEGORIES:
            if forbidden in category or forbidden in title:
                return True, f"Forbidden category: {forbidden}"
        return False, None


class SuspiciousPriceRule(RiskRule):
    """Detect suspiciously low prices for branded items."""

    def __init__(self):
        super().__init__(
            name="suspicious_price",
            weight=30,
            description="Detects suspiciously low prices",
        )

    def evaluate(self, product_data: dict) -> tuple[bool, Optional[str]]:
        title = product_data.get("title", "").lower()
        platform_price = product_data.get("platform_price")

        # Check if title contains luxury/brand keywords and price is very low
        luxury_keywords = ["luxury", "premium", "authentic", "original", "genuine"]
        has_luxury_claim = any(kw in title for kw in luxury_keywords)

        if has_luxury_claim and platform_price and platform_price < 10:
            return True, f"Suspiciously low price (${platform_price}) for luxury claim"

        return False, None


class RiskAssessmentResult:
    """Risk assessment result."""

    def __init__(self):
        self.score = 0
        self.rule_hits: list[dict] = []
        self.decision = RiskDecision.PASS

    def add_hit(self, rule: RiskRule, reason: str):
        """Add a rule hit."""
        self.score += rule.weight
        self.rule_hits.append(
            {
                "rule": rule.name,
                "weight": rule.weight,
                "reason": reason,
                "description": rule.description,
            }
        )

    def finalize(self):
        """Finalize decision based on score."""
        if self.score >= 70:
            self.decision = RiskDecision.REJECT
        elif self.score >= 40:
            self.decision = RiskDecision.REVIEW
        else:
            self.decision = RiskDecision.PASS

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "score": self.score,
            "decision": self.decision.value,
            "rule_hits": self.rule_hits,
        }


class RiskRulesEngine:
    """Rule-based risk assessment engine."""

    def __init__(self):
        self.rules: list[RiskRule] = [
            BrandKeywordRule(),
            ForbiddenCategoryRule(),
            SuspiciousPriceRule(),
        ]

    def assess(self, product_data: dict) -> RiskAssessmentResult:
        """Assess product risk."""
        result = RiskAssessmentResult()

        for rule in self.rules:
            hit, reason = rule.evaluate(product_data)
            if hit:
                result.add_hit(rule, reason)

        result.finalize()

        logger.info(
            "risk_assessed",
            product_title=product_data.get("title"),
            score=result.score,
            decision=result.decision.value,
            hits=len(result.rule_hits),
        )

        return result
