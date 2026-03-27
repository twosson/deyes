"""Tests for recommendation feedback API."""
from decimal import Decimal
from uuid import uuid4

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    CandidateStatus,
    FeedbackAction,
    ProfitabilityDecision,
    RiskDecision,
    SourcePlatform,
    StrategyRunStatus,
    TriggerType,
)
from app.db.models import (
    CandidateProduct,
    PricingAssessment,
    RecommendationFeedback,
    RiskAssessment,
    RunEvent,
    StrategyRun,
    SupplierMatch,
)
from app.db.session import get_db
from app.main import app


async def _create_test_candidate(
    db_session: AsyncSession,
    *,
    title: str = "Test Product",
    category: str = "electronics",
    platform_price: Decimal = Decimal("50.00"),
    sales_count: int = 1000,
    rating: Decimal = Decimal("4.5"),
    priority_score: float = 0.7,
    seasonal_boost: float = 1.2,
    competition_density: str = "low",
) -> CandidateProduct:
    """Create a test candidate with all relationships."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.TEMU,
        status=StrategyRunStatus.COMPLETED,
        max_candidates=10,
    )
    db_session.add(strategy_run)
    await db_session.flush()

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.TEMU,
        source_product_id="test-123",
        source_url="https://example.com/product/123",
        title=title,
        category=category,
        platform_price=platform_price,
        sales_count=sales_count,
        rating=rating,
        status=CandidateStatus.DISCOVERED,
        normalized_attributes={
            "priority_score": priority_score,
            "seasonal_boost": seasonal_boost,
            "competition_density": competition_density,
        },
    )
    db_session.add(candidate)
    await db_session.flush()

    return candidate


async def _add_pricing_assessment(
    db_session: AsyncSession,
    candidate_id,
    *,
    margin_percentage: Decimal = Decimal("35.0"),
    profitability_decision: ProfitabilityDecision = ProfitabilityDecision.PROFITABLE,
) -> PricingAssessment:
    """Add pricing assessment to candidate."""
    pricing = PricingAssessment(
        id=uuid4(),
        candidate_product_id=candidate_id,
        estimated_shipping_cost=Decimal("5.00"),
        platform_commission_rate=Decimal("0.10"),
        payment_fee_rate=Decimal("0.02"),
        return_rate_assumption=Decimal("0.05"),
        total_cost=Decimal("30.00"),
        estimated_margin=Decimal("20.00"),
        margin_percentage=margin_percentage,
        recommended_price=Decimal("55.00"),
        profitability_decision=profitability_decision,
    )
    db_session.add(pricing)
    await db_session.flush()
    return pricing


async def _add_risk_assessment(
    db_session: AsyncSession,
    candidate_id,
    *,
    score: int = 20,
    decision: RiskDecision = RiskDecision.PASS,
) -> RiskAssessment:
    """Add risk assessment to candidate."""
    risk = RiskAssessment(
        id=uuid4(),
        candidate_product_id=candidate_id,
        score=score,
        decision=decision,
        rule_hits={},
    )
    db_session.add(risk)
    await db_session.flush()
    return risk


@pytest.mark.asyncio
async def test_create_feedback_accepted(db_session: AsyncSession):
    """Test creating accepted feedback."""
    candidate = await _create_test_candidate(db_session)
    await _add_pricing_assessment(db_session, candidate.id)
    await _add_risk_assessment(db_session, candidate.id)
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/recommendations/{candidate.id}/feedback",
            json={"action": "accepted", "comment": "Great product!"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "accepted"
    assert data["comment"] == "Great product!"
    assert data["candidate_product_id"] == str(candidate.id)
    assert "metadata" in data
    assert data["metadata"]["recommendation_level"] in ["HIGH", "MEDIUM", "LOW"]

    result = await db_session.execute(
        select(RecommendationFeedback).where(
            RecommendationFeedback.candidate_product_id == candidate.id
        )
    )
    feedback = result.scalar_one()
    assert feedback.action == FeedbackAction.ACCEPTED
    assert feedback.comment == "Great product!"


@pytest.mark.asyncio
async def test_create_feedback_rejected(db_session: AsyncSession):
    """Test creating rejected feedback."""
    candidate = await _create_test_candidate(db_session)
    await _add_pricing_assessment(db_session, candidate.id)
    await _add_risk_assessment(db_session, candidate.id)
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/recommendations/{candidate.id}/feedback",
            json={"action": "rejected", "comment": "Too risky"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "rejected"
    assert data["comment"] == "Too risky"


@pytest.mark.asyncio
async def test_create_feedback_deferred(db_session: AsyncSession):
    """Test creating deferred feedback."""
    candidate = await _create_test_candidate(db_session)
    await _add_pricing_assessment(db_session, candidate.id)
    await _add_risk_assessment(db_session, candidate.id)
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/recommendations/{candidate.id}/feedback",
            json={"action": "deferred"},
        )

    assert response.status_code == 200
    data = response.json()
    assert data["action"] == "deferred"
    assert data["comment"] is None


@pytest.mark.asyncio
async def test_create_feedback_creates_event(db_session: AsyncSession):
    """Test that feedback creation creates a RunEvent."""
    candidate = await _create_test_candidate(db_session)
    await _add_pricing_assessment(db_session, candidate.id)
    await _add_risk_assessment(db_session, candidate.id)
    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            f"/api/recommendations/{candidate.id}/feedback",
            json={"action": "accepted"},
        )

    result = await db_session.execute(
        select(RunEvent)
        .where(RunEvent.strategy_run_id == candidate.strategy_run_id)
        .where(RunEvent.event_type == "recommendation_feedback_created")
    )
    event = result.scalar_one()
    assert event.event_payload["action"] == "accepted"
    assert event.event_payload["candidate_product_id"] == str(candidate.id)


@pytest.mark.asyncio
async def test_create_feedback_candidate_not_found(db_session: AsyncSession):
    """Test feedback creation with non-existent candidate."""
    fake_id = uuid4()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/api/recommendations/{fake_id}/feedback",
            json={"action": "accepted"},
        )

    assert response.status_code == 404
    assert "not found" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_feedback_stats_endpoint(db_session: AsyncSession):
    """Test feedback statistics endpoint."""
    candidate1 = await _create_test_candidate(db_session, title="Product 1")
    candidate2 = await _create_test_candidate(db_session, title="Product 2")
    candidate3 = await _create_test_candidate(db_session, title="Product 3")

    for candidate in [candidate1, candidate2, candidate3]:
        await _add_pricing_assessment(db_session, candidate.id)
        await _add_risk_assessment(db_session, candidate.id)

    await db_session.commit()

    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        await client.post(
            f"/api/recommendations/{candidate1.id}/feedback",
            json={"action": "accepted"},
        )
        await client.post(
            f"/api/recommendations/{candidate2.id}/feedback",
            json={"action": "accepted"},
        )
        await client.post(
            f"/api/recommendations/{candidate3.id}/feedback",
            json={"action": "rejected"},
        )

        response = await client.get("/api/recommendations/stats/feedback?days=30")

    assert response.status_code == 200
    data = response.json()
    assert data["total_feedback"] == 3
    assert len(data["data"]) == 2

    action_counts = {item["action"]: item["count"] for item in data["data"]}
    assert action_counts["accepted"] == 2
    assert action_counts["rejected"] == 1
