"""Regression tests for schema drift-sensitive read paths."""
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.routes_candidates import list_candidates
from app.api.routes_products import get_product, list_products
from app.core.enums import (
    CandidateStatus,
    ProductLifecycle,
    ProfitabilityDecision,
    SourcePlatform,
    StrategyRunStatus,
    TriggerType,
)
from app.db.models import CandidateProduct, PricingAssessment, StrategyRun, SupplierMatch


@pytest.mark.asyncio
async def test_candidate_and_product_reads_support_phase1_fields(db_session: AsyncSession):
    """Ensure Phase 1 fields can be queried through candidates and serialized through products."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=10,
    )
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="123456",
        title="Minimalist Clear Phone Case",
        category="phone accessories",
        currency="USD",
        platform_price=Decimal("5.50"),
        status=CandidateStatus.DISCOVERED,
        internal_sku="DEY-PH-REG-001",
        lifecycle_status=ProductLifecycle.DRAFT,
    )

    db_session.add_all([strategy_run, candidate])
    await db_session.commit()
    await db_session.refresh(candidate)

    candidates_response = await list_candidates(db=db_session)
    assert len(candidates_response["items"]) == 1
    assert candidates_response["items"][0]["id"] == str(candidate.id)
    assert candidates_response["items"][0]["status"] == CandidateStatus.DISCOVERED.value

    products_response = await list_products(
        lifecycle_status=None,
        status=None,
        category=None,
        search=None,
        limit=50,
        offset=0,
        db=db_session,
    )

    assert products_response.total == 1
    product = products_response.products[0]
    assert product.id == candidate.id
    assert product.internal_sku == "DEY-PH-REG-001"
    assert product.lifecycle_status == ProductLifecycle.DRAFT.value
    assert product.updated_at is not None
    assert product.assets_count == 0
    assert product.listings_count == 0


@pytest.mark.asyncio
async def test_product_detail_includes_pricing_assessment_and_supplier_selection(
    db_session: AsyncSession,
):
    """Ensure product detail read path exposes pricing assessment explanation and selected supplier."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=10,
    )
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="prod-detail-001",
        title="Factory Selected Product",
        category="phone accessories",
        currency="USD",
        platform_price=Decimal("19.90"),
        status=CandidateStatus.PRICED,
        internal_sku="DEY-PH-REG-002",
        lifecycle_status=ProductLifecycle.DRAFT,
    )
    selected_supplier = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="优选工厂",
        supplier_url="https://shop.example.com/factory",
        supplier_sku="factory-001",
        supplier_price=Decimal("6.50"),
        moq=20,
        confidence_score=Decimal("0.93"),
        raw_payload={"is_factory_result": True, "verified_supplier": True},
        selected=True,
    )
    backup_supplier = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="备选供应商",
        supplier_url="https://shop.example.com/backup",
        supplier_sku="backup-001",
        supplier_price=Decimal("6.20"),
        moq=80,
        confidence_score=Decimal("0.61"),
        raw_payload={"alternative_sku": True},
        selected=False,
    )
    pricing_assessment = PricingAssessment(
        id=uuid4(),
        candidate_product_id=candidate.id,
        estimated_shipping_cost=Decimal("0.98"),
        platform_commission_rate=Decimal("0.1000"),
        payment_fee_rate=Decimal("0.0200"),
        return_rate_assumption=Decimal("0.0500"),
        total_cost=Decimal("10.10"),
        estimated_margin=Decimal("9.80"),
        margin_percentage=Decimal("49.25"),
        recommended_price=Decimal("14.43"),
        profitability_decision=ProfitabilityDecision.PROFITABLE,
        explanation={
            "breakdown": {
                "supplier_price": 6.5,
                "shipping": 0.98,
                "platform_commission": 1.99,
                "payment_fee": 0.40,
                "return_cost": 0.33,
            },
            "total_cost": 10.1,
            "revenue": 19.9,
            "margin": 9.8,
            "supplier_selection": {
                "competition_set_size": 2,
                "considered_supplier_count": 2,
                "selected_supplier": {
                    "rank": 1,
                    "supplier_match_id": str(selected_supplier.id),
                    "supplier_name": "优选工厂",
                    "supplier_sku": "factory-001",
                    "supplier_price": 6.5,
                    "moq": 20,
                    "confidence_score": 0.93,
                    "usable_for_pricing": True,
                    "rejection_reason": None,
                    "score": 0.8123,
                    "score_breakdown": {
                        "price_component": 0.2323,
                        "confidence_component": 0.279,
                        "moq_component": 0.15,
                        "identity_bonus": 0.10,
                        "alternative_sku_penalty": 0.0,
                        "price_gap_penalty": 0.0,
                    },
                    "identity_signals": {
                        "is_factory_result": True,
                        "is_super_factory": False,
                        "verified_supplier": True,
                        "alternative_sku": False,
                    },
                },
                "ranked_supplier_paths": [],
                "selection_reason": "Selected because higher confidence and factory signals outweighed the cheaper fallback.",
            },
        },
    )

    db_session.add_all(
        [strategy_run, candidate, selected_supplier, backup_supplier, pricing_assessment]
    )
    await db_session.commit()

    response = await get_product(product_id=candidate.id, db=db_session)

    assert response.id == candidate.id
    assert response.pricing_assessment is not None
    assert response.pricing_assessment["profitability_decision"] == ProfitabilityDecision.PROFITABLE.value
    assert response.pricing_assessment["explanation"] is not None
    assert response.pricing_assessment["explanation"]["supplier_selection"]["selected_supplier"][
        "supplier_name"
    ] == "优选工厂"
    assert any(supplier["selected"] is True for supplier in response.supplier_matches)
