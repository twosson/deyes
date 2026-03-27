"""Tests for auto action Celery tasks."""
import pytest
from contextlib import asynccontextmanager
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from app.core.enums import PlatformListingStatus, TargetPlatform
from app.services.rpa_publisher import RPAResult
from app.workers.tasks_auto_actions import _run_temu_rpa_fallback


@pytest.fixture
def mock_get_db_context(db_session):
    """Fixture to patch get_db_context to return test db_session."""
    @asynccontextmanager
    async def _mock_context():
        yield db_session

    with patch("app.workers.tasks_auto_actions.get_db_context", return_value=_mock_context()):
        yield


@pytest.mark.asyncio
async def test_temu_fallback_already_active(db_session, sample_active_listing, mock_get_db_context):
    """Test listing already ACTIVE is no-op."""
    result = await _run_temu_rpa_fallback(sample_active_listing.id)

    assert result["success"] is True
    assert result["status"] == "already_active"


@pytest.mark.asyncio
async def test_temu_fallback_missing_prerequisites(db_session, sample_candidate, mock_get_db_context):
    """Test missing prerequisites sets MANUAL_INTERVENTION_REQUIRED."""
    from app.db.models import PlatformListing

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        inventory=0,
        status=PlatformListingStatus.FALLBACK_QUEUED,
        platform_data={},
    )
    db_session.add(listing)
    await db_session.commit()
    await db_session.refresh(listing)

    with patch("app.workers.tasks_auto_actions.RPAPublisher") as mock_publisher_class:
        mock_publisher = AsyncMock()
        mock_publisher.get_missing_prerequisites.return_value = [
            "payload.main_image_url",
            "payload.leaf_category",
        ]
        mock_publisher_class.return_value = mock_publisher

        result = await _run_temu_rpa_fallback(listing.id)

        assert result["success"] is False
        assert result["status"] == "missing_prerequisites"
        assert "payload.main_image_url" in result["missing_fields"]

        await db_session.refresh(listing)
        assert listing.status == PlatformListingStatus.MANUAL_INTERVENTION_REQUIRED
        assert listing.auto_action_metadata["manual_intervention_reason"] == "Temu RPA prerequisites missing"
        assert "payload.main_image_url" in listing.auto_action_metadata["missing_fields"]


@pytest.mark.asyncio
async def test_temu_fallback_rpa_success(db_session, sample_candidate, mock_get_db_context):
    """Test RPA success sets ACTIVE."""
    from app.db.models import PlatformListing

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        inventory=100,
        status=PlatformListingStatus.FALLBACK_QUEUED,
        platform_data={
            "category": "home",
            "leaf_category": "storage-hooks",
            "core_attributes": {"material": "metal"},
            "logistics_template": "default-template",
        },
        auto_action_metadata={"publish_attempts": {"api": {"count": 1}}},
    )
    sample_candidate.raw_payload = {"description": "Test description"}
    sample_candidate.main_image_url = "https://example.com/test.jpg"
    sample_candidate.category = "home"
    db_session.add(sample_candidate)
    db_session.add(listing)
    await db_session.commit()
    await db_session.refresh(listing)

    with patch("app.workers.tasks_auto_actions.RPAPublisher") as mock_publisher_class:
        mock_publisher = AsyncMock()
        mock_publisher.get_missing_prerequisites.return_value = []
        mock_publisher.publish.return_value = RPAResult(
            success=True,
            platform_listing_id="TEMU-RPA-12345",
            platform_url="https://temu.com/goods.html?goods_id=12345",
        )
        mock_publisher_class.return_value = mock_publisher

        result = await _run_temu_rpa_fallback(listing.id)

        assert result["success"] is True
        assert result["status"] == "active"
        assert result["platform_listing_id"] == "TEMU-RPA-12345"

        await db_session.refresh(listing)
        assert listing.status == PlatformListingStatus.ACTIVE
        assert listing.platform_listing_id == "TEMU-RPA-12345"
        assert listing.platform_url == "https://temu.com/goods.html?goods_id=12345"
        assert listing.auto_action_metadata["publish_attempts"]["rpa"]["count"] == 1
        assert listing.auto_action_metadata["last_publish_channel"] == "rpa"


@pytest.mark.asyncio
async def test_temu_fallback_challenge_detection(db_session, sample_candidate, mock_get_db_context):
    """Test challenge detection sets MANUAL_INTERVENTION_REQUIRED."""
    from app.db.models import PlatformListing

    sample_candidate.raw_payload = {"description": "Test description"}
    db_session.add(sample_candidate)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        status=PlatformListingStatus.FALLBACK_QUEUED,
    )
    db_session.add(listing)
    await db_session.commit()
    await db_session.refresh(listing)

    with patch("app.workers.tasks_auto_actions.RPAPublisher") as mock_publisher_class:
        mock_publisher = AsyncMock()
        mock_publisher.publish.return_value = RPAResult(
            success=False,
            error_message="Challenge detected during Temu login",
            requires_manual_intervention=True,
            manual_intervention_reason="Captcha or verification challenge detected",
            error_code="CHALLENGE_DETECTED",
        )
        mock_publisher_class.return_value = mock_publisher

        result = await _run_temu_rpa_fallback(listing.id)

        assert result["success"] is False
        assert result["status"] == "manual_intervention_required"
        assert "challenge" in result["reason"].lower() or "captcha" in result["reason"].lower()

        await db_session.refresh(listing)
        assert listing.status == PlatformListingStatus.MANUAL_INTERVENTION_REQUIRED
        assert listing.sync_error is not None


@pytest.mark.asyncio
async def test_temu_fallback_normal_failure(db_session, sample_candidate, mock_get_db_context):
    """Test normal failure sets REJECTED."""
    from app.db.models import PlatformListing

    sample_candidate.raw_payload = {"description": "Test description"}
    db_session.add(sample_candidate)

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        status=PlatformListingStatus.FALLBACK_QUEUED,
    )
    db_session.add(listing)
    await db_session.commit()
    await db_session.refresh(listing)

    with patch("app.workers.tasks_auto_actions.RPAPublisher") as mock_publisher_class:
        mock_publisher = AsyncMock()
        mock_publisher.publish.return_value = RPAResult(
            success=False,
            error_message="RPA execution error: Network timeout",
            requires_manual_intervention=False,
            error_code="RPA_EXECUTION_ERROR",
        )
        mock_publisher_class.return_value = mock_publisher

        result = await _run_temu_rpa_fallback(listing.id)

        assert result["success"] is False
        assert result["status"] == "rejected"
        assert "error" in result

        await db_session.refresh(listing)
        assert listing.status == PlatformListingStatus.REJECTED
        assert listing.sync_error is not None
