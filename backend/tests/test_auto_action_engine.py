"""Tests for AutoActionEngine."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

from app.clients.platform_api_base import PlatformActionResult
from app.core.enums import (
    PlatformListingStatus,
    ProfitabilityDecision,
    RiskDecision,
    TargetPlatform,
)
from app.db.models import PricingAssessment, RiskAssessment
from app.services.auto_action_engine import AutoActionEngine


async def _add_pricing_assessment(
    db_session,
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
    db_session,
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
async def test_check_approval_required_first_time(db_session, sample_candidate):
    """Test approval required for first-time product."""
    engine = AutoActionEngine(db_session)

    approval_required, reason = engine._check_approval_required(
        candidate=sample_candidate,
        recommendation_score=80.0,
        risk_score=20,
        margin_percentage=Decimal("40.0"),
        price=Decimal("50.0"),
    )

    assert approval_required is True
    assert "first_time_product" in reason


@pytest.mark.asyncio
async def test_check_approval_required_high_risk(db_session, sample_candidate):
    """Test approval required for high risk score."""
    engine = AutoActionEngine(db_session)

    approval_required, reason = engine._check_approval_required(
        candidate=sample_candidate,
        recommendation_score=80.0,
        risk_score=60,  # High risk
        margin_percentage=Decimal("40.0"),
        price=Decimal("50.0"),
    )

    assert approval_required is True
    assert "high_risk_score" in reason


@pytest.mark.asyncio
async def test_check_approval_required_high_price(db_session, sample_candidate):
    """Test approval required for high price."""
    engine = AutoActionEngine(db_session)

    approval_required, reason = engine._check_approval_required(
        candidate=sample_candidate,
        recommendation_score=80.0,
        risk_score=20,
        margin_percentage=Decimal("40.0"),
        price=Decimal("150.0"),  # Above threshold
    )

    assert approval_required is True
    assert "high_price" in reason


@pytest.mark.asyncio
async def test_check_approval_required_low_margin(db_session, sample_candidate):
    """Test approval required for low margin."""
    engine = AutoActionEngine(db_session)

    approval_required, reason = engine._check_approval_required(
        candidate=sample_candidate,
        recommendation_score=80.0,
        risk_score=20,
        margin_percentage=Decimal("20.0"),  # Below threshold
        price=Decimal("50.0"),
    )

    assert approval_required is True
    assert "low_margin" in reason


@pytest.mark.asyncio
async def test_auto_publish_requires_approval(db_session, sample_candidate):
    """Test auto-publish creates listing with pending_approval status."""
    engine = AutoActionEngine(db_session)

    listing = await engine.auto_publish(
        candidate_id=sample_candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        recommendation_score=80.0,
        risk_score=20,
        margin_percentage=Decimal("40.0"),
    )

    assert listing.status == PlatformListingStatus.PENDING_APPROVAL
    assert listing.approval_required is True
    assert listing.approval_reason is not None


@pytest.mark.asyncio
async def test_approve_listing(db_session, sample_pending_listing):
    """Test approving a pending listing."""
    engine = AutoActionEngine(db_session)

    listing = await engine.approve_listing(sample_pending_listing.id, approved_by="test_user")

    assert listing.status == PlatformListingStatus.ACTIVE  # Mock API succeeds
    assert listing.approved_at is not None
    assert listing.approved_by == "test_user"


@pytest.mark.asyncio
async def test_reject_listing(db_session, sample_pending_listing):
    """Test rejecting a pending listing."""
    engine = AutoActionEngine(db_session)

    listing = await engine.reject_listing(
        sample_pending_listing.id,
        rejected_by="test_user",
        reason="Low quality product",
    )

    assert listing.status == PlatformListingStatus.REJECTED
    assert listing.rejected_at is not None
    assert listing.rejected_by == "test_user"
    assert listing.rejection_reason == "Low quality product"


@pytest.mark.asyncio
async def test_auto_reprice_no_data(db_session, sample_active_listing):
    """Test auto-reprice with no performance data."""
    engine = AutoActionEngine(db_session)

    result = await engine.auto_reprice(sample_active_listing.id)

    assert result is None  # No price change


@pytest.mark.asyncio
async def test_auto_pause_no_data(db_session, sample_active_listing):
    """Test auto-pause with no performance data."""
    engine = AutoActionEngine(db_session)

    paused = await engine.auto_pause(sample_active_listing.id)

    assert paused is False  # No pause


@pytest.mark.asyncio
async def test_temu_api_success_goes_to_active(db_session, sample_pending_listing):
    """Test Temu API success still goes to ACTIVE."""
    engine = AutoActionEngine(db_session)
    # Ensure raw_payload has description for the fallback task's prerequisite check
    sample_pending_listing.candidate.raw_payload = {"description": "Test description"}
    db_session.add(sample_pending_listing.candidate)
    await db_session.commit()

    with patch.object(engine, "_get_platform_client") as mock_client:
        mock_api = Mock()
        mock_api.create_product = AsyncMock(
            return_value=PlatformActionResult(
                success=True,
                platform_listing_id="temu_12345",
                platform_url="https://temu.com/product/12345",
            )
        )
        mock_client.return_value = mock_api

        await engine._execute_publish(sample_pending_listing)

        assert sample_pending_listing.status == PlatformListingStatus.ACTIVE
        assert sample_pending_listing.platform_listing_id == "temu_12345"


@pytest.mark.asyncio
async def test_temu_api_failure_goes_to_fallback_queued(db_session, sample_pending_listing):
    """Test Temu API failure goes to FALLBACK_QUEUED (not REJECTED)."""
    engine = AutoActionEngine(db_session)
    # Ensure raw_payload has description for the fallback task's prerequisite check
    sample_pending_listing.candidate.raw_payload = {"description": "Test description"}
    db_session.add(sample_pending_listing.candidate)
    await db_session.commit()

    with patch.object(engine, "_get_platform_client") as mock_client, \
         patch("app.workers.celery_app.celery_app.send_task") as mock_send_task:
        mock_api = Mock()
        mock_api.create_product = AsyncMock(
            return_value=PlatformActionResult(
                success=False,
                error_message="API rate limit exceeded",
            )
        )
        mock_client.return_value = mock_api
        mock_async_result = Mock()
        mock_async_result.id = "test-task-id-123"
        mock_send_task.return_value = mock_async_result

        await engine._execute_publish(sample_pending_listing)

        assert sample_pending_listing.status == PlatformListingStatus.FALLBACK_QUEUED
        assert sample_pending_listing.sync_error == "API rate limit exceeded"
        assert sample_pending_listing.auto_action_metadata["publish_attempts"]["api"]["count"] == 1
        assert sample_pending_listing.auto_action_metadata["last_celery_task_id"] == "test-task-id-123"
        mock_send_task.assert_called_once_with(
            "tasks.temu_rpa_publish_fallback",
            args=[str(sample_pending_listing.id)],
        )


@pytest.mark.asyncio
async def test_non_temu_platform_keeps_existing_behavior(db_session, sample_pending_listing):
    """Test non-Temu platforms keep existing behavior (REJECTED on failure)."""
    engine = AutoActionEngine(db_session)
    sample_pending_listing.platform = TargetPlatform.AMAZON
    sample_pending_listing.candidate.raw_payload = {"description": "Test description"}
    db_session.add(sample_pending_listing.candidate)
    await db_session.commit()

    with patch.object(engine, "_get_platform_client") as mock_client:
        mock_api = Mock()
        mock_api.create_product = AsyncMock(
            return_value=PlatformActionResult(
                success=False,
                error_message="Amazon API error",
            )
        )
        mock_client.return_value = mock_api

        await engine._execute_publish(sample_pending_listing)

        assert sample_pending_listing.status == PlatformListingStatus.REJECTED
        assert sample_pending_listing.sync_error == "Amazon API error"


@pytest.mark.asyncio
async def test_auto_publish_ignores_client_scores(db_session, sample_candidate):
    """Test auto-publish ignores client-supplied scores and uses source-of-truth."""
    engine = AutoActionEngine(db_session)

    # Set up source-of-truth data: low margin (20%) and high risk (80)
    await _add_pricing_assessment(
        db_session,
        sample_candidate.id,
        margin_percentage=Decimal("20.0"),
        profitability_decision=ProfitabilityDecision.MARGINAL,
    )
    await _add_risk_assessment(
        db_session,
        sample_candidate.id,
        score=80,
        decision=RiskDecision.REVIEW,
    )
    await db_session.commit()

    # Client tries to bypass approval by sending fake high scores
    listing = await engine.auto_publish(
        candidate_id=sample_candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        recommendation_score=95.0,  # Fake high score
        risk_score=10,  # Fake low risk
        margin_percentage=Decimal("50.0"),  # Fake high margin
    )

    # Should require approval because real margin=20% < 25% threshold
    assert listing.approval_required is True
    assert "low_margin" in listing.approval_reason
    # Verify stored metadata uses real scores, not client-supplied
    assert listing.auto_action_metadata["margin_percentage"] == 20.0
    assert listing.auto_action_metadata["risk_score"] == 80


@pytest.mark.asyncio
async def test_auto_publish_uses_source_of_truth(db_session, sample_candidate):
    """Test that _recompute_approval_inputs returns correct values from DB."""
    engine = AutoActionEngine(db_session)

    # Set up source-of-truth data
    await _add_pricing_assessment(
        db_session,
        sample_candidate.id,
        margin_percentage=Decimal("38.0"),
    )
    await _add_risk_assessment(
        db_session,
        sample_candidate.id,
        score=25,
    )
    # Add priority_score to normalized_attributes
    sample_candidate.normalized_attributes = {
        "priority_score": 0.75,
        "competition_density": "low",
    }
    db_session.add(sample_candidate)
    await db_session.commit()

    # Call the recompute method
    rec_score, risk_score, margin_pct = await engine._recompute_approval_inputs(
        candidate=sample_candidate,
    )

    # Verify values match source-of-truth
    assert margin_pct == Decimal("38.0")
    assert risk_score == 25
    # recommendation_score = 0.75 * 100 * 1.2 (low competition bonus) = 90.0
    assert rec_score == 90.0
