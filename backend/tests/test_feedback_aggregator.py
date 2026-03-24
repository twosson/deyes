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
