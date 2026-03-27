"""Tests for ProductScoringService."""
from decimal import Decimal

from app.services.product_scoring_service import ProductScoreInput, ProductScoringService


def test_priority_score_seasonal_boost():
    """Test seasonal boost component is applied correctly."""
    service = ProductScoringService()

    result = service.calculate_priority_score(
        ProductScoreInput(
            title="Valentine Gift",
            sales_count=None,
            rating=None,
            seasonal_boost=1.5,
            competition_density="unknown",
        )
    )

    assert result.seasonal_component == 0.2
    assert result.sales_component == 0.0
    assert result.rating_component == 0.0
    assert result.competition_component == 0.03
    assert result.total_score == 0.23


def test_priority_score_sales_count_log_scale():
    """Test sales count uses logarithmic normalization."""
    service = ProductScoringService()

    result = service.calculate_priority_score(
        ProductScoreInput(
            title="Popular Product",
            sales_count=1000,
            rating=None,
            seasonal_boost=1.0,
            competition_density="unknown",
        )
    )

    assert result.seasonal_component == 0.0
    assert result.sales_component == 0.225
    assert result.rating_component == 0.0
    assert result.competition_component == 0.03
    assert result.total_score == 0.255


def test_priority_score_competition_density():
    """Test competition density is scored inversely."""
    service = ProductScoringService()

    low_result = service.calculate_priority_score(
        ProductScoreInput(
            title="Low Competition Product",
            sales_count=None,
            rating=None,
            seasonal_boost=1.0,
            competition_density="low",
        )
    )
    high_result = service.calculate_priority_score(
        ProductScoreInput(
            title="High Competition Product",
            sales_count=None,
            rating=None,
            seasonal_boost=1.0,
            competition_density="high",
        )
    )

    assert low_result.competition_component == 0.1
    assert high_result.competition_component == 0.0
    assert low_result.total_score > high_result.total_score


def test_priority_score_combined():
    """Test combined score uses all components."""
    service = ProductScoringService()

    result = service.calculate_priority_score(
        ProductScoreInput(
            title="Strong Product",
            sales_count=100,
            rating=Decimal("4.5"),
            seasonal_boost=1.2,
            competition_density="low",
        )
    )

    assert result.seasonal_component == 0.08
    assert result.sales_component == 0.15
    assert result.rating_component == 0.18
    assert result.competition_component == 0.1
    assert result.total_score == 0.51
