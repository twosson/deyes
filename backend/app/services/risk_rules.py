"""Risk assessment rules engine.

Phase 2 Enhancement: Added competition density risk assessment.
- Compliance risk (brand, category, price) - 60% weight
- Competition risk (market saturation) - 40% weight
- Combined risk score determines final decision
"""
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


class CompetitionDensityRule(RiskRule):
    """Assess competition density risk (Phase 2 Enhancement).

    Competition density indicates market saturation:
    - HIGH: Red ocean market, >5000 competing listings
    - MEDIUM: Moderate competition, 2000-5000 listings
    - LOW: Blue ocean market, <2000 listings

    Risk scoring:
    - HIGH competition = 80 points (high risk)
    - MEDIUM competition = 50 points (moderate risk)
    - LOW competition = 20 points (low risk)
    - UNKNOWN = 30 points (default moderate risk)
    """

    def __init__(self):
        super().__init__(
            name="competition_density",
            weight=0,  # Weight is dynamic based on density
            description="Assesses market competition density",
        )

    def evaluate(self, product_data: dict) -> tuple[bool, Optional[str]]:
        """Evaluate competition density risk.

        Args:
            product_data: Must include "competition_density" field with value:
                         "low", "medium", "high", or "unknown"

        Returns:
            Tuple of (always True, reason with score)
        """
        competition_density = product_data.get("competition_density", "unknown").lower()

        # Map density to risk score
        density_scores = {
            "high": 80,
            "medium": 50,
            "low": 20,
            "unknown": 30,
        }

        score = density_scores.get(competition_density, 30)

        # Update weight dynamically
        self.weight = score

        reason = f"Competition density: {competition_density} (risk score: {score})"

        # Always return True to include in assessment
        return True, reason


class RiskAssessmentResult:
    """Risk assessment result with combined scoring (Phase 2 Enhancement).

    Combines compliance risk and competition risk:
    - Compliance risk: Brand infringement, forbidden categories, suspicious pricing
    - Competition risk: Market saturation (red ocean vs blue ocean)

    Final score = compliance_score * 0.6 + competition_score * 0.4
    """

    def __init__(self):
        self.compliance_score = 0
        self.competition_score = 0
        self.total_score = 0
        self.rule_hits: list[dict] = []
        self.decision = RiskDecision.PASS

    def add_hit(self, rule: RiskRule, reason: str):
        """Add a rule hit."""
        # Separate compliance and competition scores
        if rule.name == "competition_density":
            self.competition_score = rule.weight
        else:
            self.compliance_score += rule.weight

        self.rule_hits.append(
            {
                "rule": rule.name,
                "weight": rule.weight,
                "reason": reason,
                "description": rule.description,
            }
        )

    def finalize(self):
        """Finalize decision based on combined score.

        Phase 2 Enhancement: Uses weighted combination of compliance and competition.
        - Compliance risk: 60% weight
        - Competition risk: 40% weight
        """
        # Calculate combined score
        self.total_score = int(self.compliance_score * 0.6 + self.competition_score * 0.4)

        # Decision thresholds
        if self.total_score >= 70:
            self.decision = RiskDecision.REJECT
        elif self.total_score >= 40:
            self.decision = RiskDecision.REVIEW
        else:
            self.decision = RiskDecision.PASS

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "score": self.total_score,
            "compliance_score": self.compliance_score,
            "competition_score": self.competition_score,
            "decision": self.decision.value,
            "rule_hits": self.rule_hits,
        }


class RiskRulesEngine:
    """Rule-based risk assessment engine.

    Phase 2 Enhancement: Added competition density assessment.
    """

    def __init__(self, enable_competition_risk: bool = True):
        """Initialize risk rules engine.

        Args:
            enable_competition_risk: Whether to enable competition density assessment
                                    (default: True)
        """
        self.rules: list[RiskRule] = [
            BrandKeywordRule(),
            ForbiddenCategoryRule(),
            SuspiciousPriceRule(),
        ]

        if enable_competition_risk:
            self.rules.append(CompetitionDensityRule())

        self.enable_competition_risk = enable_competition_risk

    def assess(self, product_data: dict) -> RiskAssessmentResult:
        """Assess product risk.

        Args:
            product_data: Product data including:
                - title: Product title
                - category: Product category
                - platform_price: Platform price
                - competition_density: Competition density ("low", "medium", "high", "unknown")
                                      Optional, defaults to "unknown" if not provided

        Returns:
            RiskAssessmentResult with combined compliance and competition scores
        """
        result = RiskAssessmentResult()

        for rule in self.rules:
            hit, reason = rule.evaluate(product_data)
            if hit:
                result.add_hit(rule, reason)

        result.finalize()

        logger.info(
            "risk_assessed",
            product_title=product_data.get("title"),
            total_score=result.total_score,
            compliance_score=result.compliance_score,
            competition_score=result.competition_score,
            decision=result.decision.value,
            hits=len(result.rule_hits),
        )

        return result
