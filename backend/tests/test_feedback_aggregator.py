"""Tests for feedback aggregator service."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CandidateStatus,
    ProfitabilityDecision,
    RiskDecision,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import CandidateProduct, PlatformListing, PricingAssessment, RiskAssessment, StrategyRun, SupplierMatch
from app.services.feedback_aggregator import FeedbackAggregator


@pytest.mark.asyncio
async def test_get_high_performing_seeds_returns_profitable_seeds(db_session: AsyncSession):
    """FeedbackAggregator should return seeds with high historical performance."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.COMPLETED,
        max_candidates=5,
    )
    db_session.add(strategy_run)

    candidate_good = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="good-seed-001",
        source_url="https://detail.1688.com/offer/good-seed-001.html",
        title="Good Seed Product",
        category="测试类目",
        currency="USD",
        platform_price=Decimal("20.00"),
        status=CandidateStatus.DISCOVERED,
        normalized_attributes={
            "seed_type": "explicit",
            "matched_keyword": "优质商品",
            "shop_name": "优质店铺",
        },
    )
    db_session.add(candidate_good)

    pricing_good = PricingAssessment(
        id=uuid4(),
        candidate_product_id=candidate_good.id,
        profitability_decision=ProfitabilityDecision.PROFITABLE,
        margin_percentage=Decimal("35.00"),
    )
    db_session.add(pricing_good)

    risk_good = RiskAssessment(
        id=uuid4(),
        candidate_product_id=candidate_good.id,
        score=95,
        decision=RiskDecision.PASS,
    )
    db_session.add(risk_good)

    listing_good = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate_good.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("29.99"),
        currency="USD",
        total_sales=500,
    )
    db_session.add(listing_good)

    await db_session.commit()

    aggregator = FeedbackAggregator(lookback_days=90, prior_cap=5.0)
    await aggregator.refresh(db_session)

    seeds = aggregator.get_high_performing_seeds(category=None, limit=10)
    assert "优质商品" in seeds


@pytest.mark.asyncio
async def test_get_seed_performance_prior_returns_bounded_score(db_session: AsyncSession):
    """Seed performance prior should be capped at prior_cap."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.COMPLETED,
        max_candidates=5,
    )
    db_session.add(strategy_run)

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="cap-test-001",
        source_url="https://detail.1688.com/offer/cap-test-001.html",
        title="Cap Test Product",
        category="测试类目",
        currency="USD",
        platform_price=Decimal("20.00"),
        status=CandidateStatus.DISCOVERED,
        normalized_attributes={
            "seed_type": "explicit",
            "matched_keyword": "测试商品",
            "shop_name": "测试店铺",
        },
    )
    db_session.add(candidate)

    pricing = PricingAssessment(
        id=uuid4(),
        candidate_product_id=candidate.id,
        profitability_decision=ProfitabilityDecision.PROFITABLE,
        margin_percentage=Decimal("50.00"),
    )
    db_session.add(pricing)

    risk = RiskAssessment(
        id=uuid4(),
        candidate_product_id=candidate.id,
        score=98,
        decision=RiskDecision.PASS,
    )
    db_session.add(risk)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("29.99"),
        currency="USD",
        total_sales=1000,
    )
    db_session.add(listing)

    await db_session.commit()

    aggregator = FeedbackAggregator(lookback_days=90, prior_cap=5.0)
    await aggregator.refresh(db_session)

    prior = aggregator.get_seed_performance_prior(seed="测试商品", seed_type="explicit")
    assert prior > 0.0
    assert prior <= 5.0


@pytest.mark.asyncio
async def test_get_shop_performance_prior_returns_bounded_score(db_session: AsyncSession):
    """Shop performance prior should be capped at prior_cap."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.COMPLETED,
        max_candidates=5,
    )
    db_session.add(strategy_run)

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="shop-cap-001",
        source_url="https://detail.1688.com/offer/shop-cap-001.html",
        title="Shop Cap Product",
        category="测试类目",
        currency="USD",
        platform_price=Decimal("20.00"),
        status=CandidateStatus.DISCOVERED,
        normalized_attributes={
            "seed_type": "explicit",
            "matched_keyword": "店铺测试商品",
            "shop_name": "高表现店铺",
        },
    )
    db_session.add(candidate)

    pricing = PricingAssessment(
        id=uuid4(),
        candidate_product_id=candidate.id,
        profitability_decision=ProfitabilityDecision.PROFITABLE,
        margin_percentage=Decimal("60.00"),
    )
    db_session.add(pricing)

    risk = RiskAssessment(
        id=uuid4(),
        candidate_product_id=candidate.id,
        score=99,
        decision=RiskDecision.PASS,
    )
    db_session.add(risk)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("39.99"),
        currency="USD",
        total_sales=1200,
    )
    db_session.add(listing)

    await db_session.commit()

    aggregator = FeedbackAggregator(lookback_days=90, prior_cap=5.0)
    await aggregator.refresh(db_session)

    prior = aggregator.get_shop_performance_prior(shop_name="高表现店铺")
    assert prior > 0.0
    assert prior <= 5.0


@pytest.mark.asyncio
async def test_get_supplier_performance_prior_returns_bounded_score(db_session: AsyncSession):
    """Supplier performance prior should be capped at prior_cap."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.COMPLETED,
        max_candidates=5,
    )
    db_session.add(strategy_run)

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="supplier-cap-001",
        source_url="https://detail.1688.com/offer/supplier-cap-001.html",
        title="Supplier Cap Product",
        category="测试类目",
        currency="USD",
        platform_price=Decimal("20.00"),
        status=CandidateStatus.DISCOVERED,
        normalized_attributes={
            "seed_type": "explicit",
            "matched_keyword": "供应商测试商品",
            "shop_name": "供应商测试店铺",
        },
    )
    db_session.add(candidate)

    pricing = PricingAssessment(
        id=uuid4(),
        candidate_product_id=candidate.id,
        profitability_decision=ProfitabilityDecision.PROFITABLE,
        margin_percentage=Decimal("55.00"),
    )
    db_session.add(pricing)

    risk = RiskAssessment(
        id=uuid4(),
        candidate_product_id=candidate.id,
        score=97,
        decision=RiskDecision.PASS,
    )
    db_session.add(risk)

    supplier = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="高表现供应商",
        supplier_url="https://shop.example.com/high-supplier",
        supplier_sku="high-supplier-001",
        supplier_price=Decimal("8.00"),
        moq=10,
        confidence_score=Decimal("0.95"),
        raw_payload={},
        selected=True,
    )
    db_session.add(supplier)

    await db_session.commit()

    aggregator = FeedbackAggregator(lookback_days=90, prior_cap=5.0)
    await aggregator.refresh(db_session)

    prior = aggregator.get_supplier_performance_prior(
        supplier_name="高表现供应商",
        supplier_url="https://shop.example.com/high-supplier",
    )
    assert prior > 0.0
    assert prior <= 5.0


@pytest.mark.asyncio
async def test_feedback_aggregator_respects_lookback_days(db_session: AsyncSession):
    """FeedbackAggregator should only consider candidates within lookback window."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.COMPLETED,
        max_candidates=5,
    )
    db_session.add(strategy_run)

    old_candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="old-001",
        source_url="https://detail.1688.com/offer/old-001.html",
        title="Old Product",
        category="测试类目",
        currency="USD",
        platform_price=Decimal("20.00"),
        status=CandidateStatus.DISCOVERED,
        normalized_attributes={
            "seed_type": "explicit",
            "matched_keyword": "旧商品",
            "shop_name": "旧店铺",
        },
    )
    old_candidate.created_at = datetime.now(UTC) - timedelta(days=100)
    db_session.add(old_candidate)

    pricing_old = PricingAssessment(
        id=uuid4(),
        candidate_product_id=old_candidate.id,
        profitability_decision=ProfitabilityDecision.PROFITABLE,
        margin_percentage=Decimal("40.00"),
    )
    db_session.add(pricing_old)

    risk_old = RiskAssessment(
        id=uuid4(),
        candidate_product_id=old_candidate.id,
        score=95,
        decision=RiskDecision.PASS,
    )
    db_session.add(risk_old)

    await db_session.commit()

    aggregator = FeedbackAggregator(lookback_days=90, prior_cap=5.0)
    await aggregator.refresh(db_session)

    seeds = aggregator.get_high_performing_seeds(category=None, limit=10)
    assert "旧商品" not in seeds


@pytest.mark.asyncio
async def test_feedback_aggregator_consumes_real_profit(db_session: AsyncSession):
    """FeedbackAggregator should prioritize real profit data when available."""
    from app.core.enums import InventoryMode, OrderLineStatus, OrderStatus
    from app.db.models import (
        PlatformOrder,
        PlatformOrderLine,
        ProductMaster,
        ProductVariant,
        Supplier,
        SupplierOffer,
    )
    from app.services.profit_ledger_service import ProfitLedgerService

    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.COMPLETED,
        max_candidates=5,
    )
    db_session.add(strategy_run)

    # Create candidate with real profit data
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="real-profit-001",
        source_url="https://detail.1688.com/offer/real-profit-001.html",
        title="Real Profit Product",
        category="测试类目",
        currency="USD",
        platform_price=Decimal("20.00"),
        status=CandidateStatus.DISCOVERED,
        normalized_attributes={
            "seed_type": "explicit",
            "matched_keyword": "真实利润商品",
            "shop_name": "真实利润店铺",
        },
    )
    db_session.add(candidate)

    # Create variant and supplier
    master = ProductMaster(
        id=uuid4(),
        internal_sku="TEST-REAL-PROFIT-001",
        name="Test Real Profit Product",
        status="active",
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="TEST-REAL-PROFIT-001-V1",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status="active",
    )
    db_session.add(variant)
    await db_session.flush()

    supplier = Supplier(
        id=uuid4(),
        name="Test Real Profit Supplier",
        status="active",
    )
    db_session.add(supplier)
    await db_session.flush()

    offer = SupplierOffer(
        id=uuid4(),
        supplier_id=supplier.id,
        variant_id=variant.id,
        unit_price=Decimal("10.00"),
        currency="USD",
        moq=100,
        lead_time_days=30,
    )
    db_session.add(offer)

    # Create listing linked to candidate
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        inventory_mode=InventoryMode.STOCK_FIRST,
        platform=TargetPlatform.TEMU,
        region="us",
        price=Decimal("29.99"),
        currency="USD",
        total_sales=0,
    )
    db_session.add(listing)
    await db_session.flush()

    # Create multiple orders to reach statistical significance (>= 10 entries)
    profit_service = ProfitLedgerService()
    for i in range(12):
        order = PlatformOrder(
            id=uuid4(),
            platform=TargetPlatform.TEMU,
            region="us",
            platform_order_id=f"ORDER-REAL-PROFIT-{i:03d}",
            idempotency_key=f"order:temu:ORDER-REAL-PROFIT-{i:03d}",
            order_status=OrderStatus.CONFIRMED,
            currency="USD",
            total_amount=Decimal("30.00"),
            ordered_at=datetime.now(UTC),
        )
        db_session.add(order)
        await db_session.flush()

        line = PlatformOrderLine(
            id=uuid4(),
            order_id=order.id,
            platform_listing_id=listing.id,
            product_variant_id=variant.id,
            platform_sku="TEMU-REAL-PROFIT-001",
            quantity=1,
            unit_price=Decimal("30.00"),
            gross_revenue=Decimal("30.00"),
            line_status=OrderLineStatus.CONFIRMED,
        )
        db_session.add(line)
        await db_session.flush()

        # Build profit ledger
        await profit_service.build_order_profit_ledger(
            db=db_session,
            order_line_id=line.id,
        )

    await db_session.commit()

    # Refresh aggregator
    aggregator = FeedbackAggregator(lookback_days=90, prior_cap=5.0)
    await aggregator.refresh(db_session)

    # Check that seed has high prior (real profit should boost score)
    prior = aggregator.get_seed_performance_prior(seed="真实利润商品", seed_type="explicit")
    assert prior > 0.0


@pytest.mark.asyncio
async def test_feedback_aggregator_fallback_to_theoretical_profit(db_session: AsyncSession):
    """FeedbackAggregator should fall back to theoretical profit when real data insufficient."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.COMPLETED,
        max_candidates=5,
    )
    db_session.add(strategy_run)

    # Create candidate with only theoretical profit data
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="theoretical-001",
        source_url="https://detail.1688.com/offer/theoretical-001.html",
        title="Theoretical Profit Product",
        category="测试类目",
        currency="USD",
        platform_price=Decimal("20.00"),
        status=CandidateStatus.DISCOVERED,
        normalized_attributes={
            "seed_type": "explicit",
            "matched_keyword": "理论利润商品",
            "shop_name": "理论利润店铺",
        },
    )
    db_session.add(candidate)

    pricing = PricingAssessment(
        id=uuid4(),
        candidate_product_id=candidate.id,
        profitability_decision=ProfitabilityDecision.PROFITABLE,
        margin_percentage=Decimal("35.00"),
    )
    db_session.add(pricing)

    risk = RiskAssessment(
        id=uuid4(),
        candidate_product_id=candidate.id,
        score=95,
        decision=RiskDecision.PASS,
    )
    db_session.add(risk)

    await db_session.commit()

    # Refresh aggregator
    aggregator = FeedbackAggregator(lookback_days=90, prior_cap=5.0)
    await aggregator.refresh(db_session)

    # Check that seed has prior (should use theoretical signals)
    prior = aggregator.get_seed_performance_prior(seed="理论利润商品", seed_type="explicit")
    assert prior > 0.0
