#!/usr/bin/env python3
"""Simple test script for demand validator without pytest dependencies."""
import sys
import asyncio
from decimal import Decimal

# Add backend to path
sys.path.insert(0, '/Users/twosson/deyes/backend')

from app.services.demand_validator import (
    CompetitionDensity,
    DemandValidationResult,
    DemandValidator,
    TrendDirection,
)


def test_validation_result():
    """Test DemandValidationResult logic."""
    print("Testing DemandValidationResult...")

    # Test 1: Good metrics should pass
    result = DemandValidationResult(
        keyword="phone case",
        search_volume=2000,
        competition_density=CompetitionDensity.LOW,
        trend_direction=TrendDirection.RISING,
        trend_growth_rate=Decimal("0.25"),
    )
    assert result.passed is True, "Good metrics should pass"
    print("✓ Good metrics pass validation")

    # Test 2: Low search volume should fail
    result = DemandValidationResult(
        keyword="obscure product",
        search_volume=100,
        competition_density=CompetitionDensity.LOW,
        trend_direction=TrendDirection.STABLE,
        trend_growth_rate=Decimal("0.05"),
    )
    assert result.passed is False, "Low search volume should fail"
    assert "Search volume too low" in result.rejection_reasons[0]
    print("✓ Low search volume rejected")

    # Test 3: High competition should fail
    result = DemandValidationResult(
        keyword="phone case",
        search_volume=5000,
        competition_density=CompetitionDensity.HIGH,
        trend_direction=TrendDirection.STABLE,
        trend_growth_rate=Decimal("0.05"),
    )
    assert result.passed is False, "High competition should fail"
    assert "Competition density too high" in result.rejection_reasons[0]
    print("✓ High competition rejected")

    # Test 4: Declining trend should fail
    result = DemandValidationResult(
        keyword="fidget spinner",
        search_volume=2000,
        competition_density=CompetitionDensity.LOW,
        trend_direction=TrendDirection.DECLINING,
        trend_growth_rate=Decimal("-0.30"),
    )
    assert result.passed is False, "Declining trend should fail"
    assert "Market trend declining" in result.rejection_reasons[0]
    print("✓ Declining trend rejected")

    print("✅ All DemandValidationResult tests passed\n")


def test_validator_helpers():
    """Test DemandValidator helper methods."""
    print("Testing DemandValidator helper methods...")

    validator = DemandValidator()

    # Test region conversion
    assert validator._region_to_geo("US") == "US"
    assert validator._region_to_geo("UK") == "GB"
    assert validator._region_to_geo("JP") == "JP"
    assert validator._region_to_geo("") == "US"
    print("✓ Region conversion works")

    # Test search volume estimation
    assert validator._estimate_search_volume_from_interest(80) == 10000
    assert validator._estimate_search_volume_from_interest(60) == 5000
    assert validator._estimate_search_volume_from_interest(40) == 2000
    assert validator._estimate_search_volume_from_interest(20) == 500
    assert validator._estimate_search_volume_from_interest(7) == 200
    assert validator._estimate_search_volume_from_interest(2) == 100
    print("✓ Search volume estimation works")

    # Test trend classification
    assert validator._classify_trend_direction(Decimal("0.30")) == TrendDirection.RISING
    assert validator._classify_trend_direction(Decimal("0.10")) == TrendDirection.STABLE
    assert validator._classify_trend_direction(Decimal("-0.30")) == TrendDirection.DECLINING
    print("✓ Trend classification works")

    print("✅ All helper method tests passed\n")


async def test_validator_integration():
    """Test DemandValidator with mock data."""
    print("Testing DemandValidator integration...")

    validator = DemandValidator(min_search_volume=500)

    # This will use mock data since pytrends may not be installed
    result = await validator.validate(
        keyword="phone case",
        category="electronics",
        region="US",
    )

    assert result.keyword == "phone case"
    assert result.search_volume is not None
    assert result.competition_density is not None
    assert result.trend_direction is not None
    print(f"✓ Validation result: search_volume={result.search_volume}, "
          f"competition={result.competition_density.value}, "
          f"trend={result.trend_direction.value}, "
          f"passed={result.passed}")

    # Test batch validation
    keywords = ["phone case", "wireless charger", "bluetooth speaker"]
    results = await validator.validate_batch(
        keywords=keywords,
        category="electronics",
        region="US",
    )

    assert len(results) == 3
    print(f"✓ Batch validation: {len(results)} keywords processed")

    print("✅ All integration tests passed\n")


def main():
    """Run all tests."""
    print("=" * 60)
    print("Demand Validator Test Suite")
    print("=" * 60 + "\n")

    try:
        test_validation_result()
        test_validator_helpers()
        asyncio.run(test_validator_integration())

        print("=" * 60)
        print("✅ ALL TESTS PASSED")
        print("=" * 60)
        return 0

    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        return 1
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
