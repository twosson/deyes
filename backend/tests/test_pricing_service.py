"""Test pricing service."""
from decimal import Decimal

from app.core.enums import ProfitabilityDecision
from app.services.pricing_service import PricingService


def test_profitable_product():
    """Test pricing calculation for profitable product."""
    service = PricingService()

    result = service.calculate_pricing(
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
    )

    assert result.total_cost < result.platform_price
    assert result.estimated_margin > 0
    assert result.margin_percentage > 30
    assert result.profitability_decision == ProfitabilityDecision.PROFITABLE


def test_marginal_product():
    """Test pricing calculation for marginal product."""
    service = PricingService()

    result = service.calculate_pricing(
        supplier_price=Decimal("20.00"),
        platform_price=Decimal("35.00"),
    )

    assert result.estimated_margin > 0
    assert 15 <= result.margin_percentage < 30
    assert result.profitability_decision == ProfitabilityDecision.MARGINAL


def test_unprofitable_product():
    """Test pricing calculation for unprofitable product."""
    service = PricingService()

    result = service.calculate_pricing(
        supplier_price=Decimal("25.00"),
        platform_price=Decimal("28.00"),
    )

    assert result.margin_percentage < 15
    assert result.profitability_decision == ProfitabilityDecision.UNPROFITABLE


def test_pricing_breakdown():
    """Test that pricing breakdown is complete."""
    service = PricingService()

    result = service.calculate_pricing(
        supplier_price=Decimal("10.00"),
        platform_price=Decimal("30.00"),
    )

    result_dict = result.to_dict()

    assert "explanation" in result_dict
    assert "breakdown" in result_dict["explanation"]
    breakdown = result_dict["explanation"]["breakdown"]

    assert "supplier_price" in breakdown
    assert "shipping" in breakdown
    assert "platform_commission" in breakdown
    assert "payment_fee" in breakdown
    assert "return_cost" in breakdown


def test_supplier_selection_prefers_high_confidence_over_low_price():
    """Test that higher confidence can beat a slightly lower price."""
    from app.services.pricing_service import SupplierPathInput

    service = PricingService()

    paths = [
        SupplierPathInput(
            id="supplier_a",
            supplier_name="Supplier A",
            supplier_sku="sku-a",
            supplier_price=Decimal("10.00"),
            moq=50,
            confidence_score=Decimal("0.45"),
            raw_payload={},
        ),
        SupplierPathInput(
            id="supplier_b",
            supplier_name="Supplier B",
            supplier_sku="sku-b",
            supplier_price=Decimal("10.40"),
            moq=20,
            confidence_score=Decimal("0.92"),
            raw_payload={},
        ),
    ]

    result = service.select_best_supplier_path(paths)

    assert result.selected_path is not None
    assert result.selected_path.id == "supplier_b"
    assert result.competition_set_size == 2
    assert result.considered_supplier_count == 2


def test_supplier_selection_prefers_low_moq_when_prices_close():
    """Test that lower MOQ wins when prices and confidence are similar."""
    from app.services.pricing_service import SupplierPathInput

    service = PricingService()

    paths = [
        SupplierPathInput(
            id="supplier_a",
            supplier_name="Supplier A",
            supplier_sku="sku-a",
            supplier_price=Decimal("10.00"),
            moq=100,
            confidence_score=Decimal("0.85"),
            raw_payload={},
        ),
        SupplierPathInput(
            id="supplier_b",
            supplier_name="Supplier B",
            supplier_sku="sku-b",
            supplier_price=Decimal("10.10"),
            moq=10,
            confidence_score=Decimal("0.85"),
            raw_payload={},
        ),
    ]

    result = service.select_best_supplier_path(paths)

    assert result.selected_path is not None
    assert result.selected_path.id == "supplier_b"


def test_supplier_selection_ignores_invalid_prices():
    """Test that suppliers without valid prices are excluded."""
    from app.services.pricing_service import SupplierPathInput

    service = PricingService()

    paths = [
        SupplierPathInput(
            id="supplier_a",
            supplier_name="Supplier A",
            supplier_sku="sku-a",
            supplier_price=None,
            moq=20,
            confidence_score=Decimal("0.95"),
            raw_payload={},
        ),
        SupplierPathInput(
            id="supplier_b",
            supplier_name="Supplier B",
            supplier_sku="sku-b",
            supplier_price=Decimal("15.00"),
            moq=30,
            confidence_score=Decimal("0.70"),
            raw_payload={},
        ),
    ]

    result = service.select_best_supplier_path(paths)

    assert result.selected_path is not None
    assert result.selected_path.id == "supplier_b"
    assert result.considered_supplier_count == 1


def test_supplier_selection_factory_bonus():
    """Test that factory identity signals provide a scoring bonus."""
    from app.services.pricing_service import SupplierPathInput

    service = PricingService()

    paths = [
        SupplierPathInput(
            id="supplier_a",
            supplier_name="Supplier A",
            supplier_sku="sku-a",
            supplier_price=Decimal("10.00"),
            moq=30,
            confidence_score=Decimal("0.80"),
            raw_payload={},
        ),
        SupplierPathInput(
            id="supplier_b",
            supplier_name="Supplier B (Factory)",
            supplier_sku="sku-b",
            supplier_price=Decimal("10.20"),
            moq=30,
            confidence_score=Decimal("0.80"),
            raw_payload={"is_factory_result": True, "verified_supplier": True},
        ),
    ]

    result = service.select_best_supplier_path(paths)

    assert result.selected_path is not None
    assert result.selected_path.id == "supplier_b"


def test_supplier_selection_explanation_structure():
    """Test that selection explanation contains expected keys."""
    from app.services.pricing_service import SupplierPathInput

    service = PricingService()

    paths = [
        SupplierPathInput(
            id="supplier_a",
            supplier_name="Supplier A",
            supplier_sku="sku-a",
            supplier_price=Decimal("10.00"),
            moq=20,
            confidence_score=Decimal("0.85"),
            raw_payload={},
        ),
    ]

    result = service.select_best_supplier_path(paths)
    explanation = result.to_explanation()

    assert "competition_set_size" in explanation
    assert "considered_supplier_count" in explanation
    assert "selected_supplier" in explanation
    assert "ranked_supplier_paths" in explanation
    assert "selection_reason" in explanation

    selected = explanation["selected_supplier"]
    assert selected is not None
    assert "supplier_match_id" in selected
    assert "supplier_name" in selected
    assert "supplier_price" in selected
    assert "score" in selected
    assert "score_breakdown" in selected
    assert "identity_signals" in selected


def test_supplier_selection_returns_no_selection_when_all_prices_invalid():
    """Test that no supplier is selected when every supplier price is unusable."""
    from app.services.pricing_service import SupplierPathInput

    service = PricingService()

    paths = [
        SupplierPathInput(
            id="supplier_a",
            supplier_name="Supplier A",
            supplier_sku="sku-a",
            supplier_price=None,
            moq=20,
            confidence_score=Decimal("0.85"),
            raw_payload={},
        ),
        SupplierPathInput(
            id="supplier_b",
            supplier_name="Supplier B",
            supplier_sku="sku-b",
            supplier_price=Decimal("0.00"),
            moq=10,
            confidence_score=Decimal("0.90"),
            raw_payload={"is_factory_result": True},
        ),
    ]

    result = service.select_best_supplier_path(paths)
    explanation = result.to_explanation()

    assert result.selected_path is None
    assert result.considered_supplier_count == 0
    assert explanation["selected_supplier"] is None
    assert explanation["selection_reason"] == (
        "No supplier path had a valid supplier price, so pricing was skipped."
    )
