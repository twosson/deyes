"""Tests for OperationsControlPlaneService."""
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    ActionExecutionStatus,
    ActionType,
    PlatformListingStatus,
    ProductVariantStatus,
    SkuLifecycleState,
    SupplierStatus,
    TargetPlatform,
)
from app.db.models import (
    ActionExecutionLog,
    InventoryLevel,
    PlatformListing,
    ProductMaster,
    ProductVariant,
    ProfitLedger,
    SkuLifecycleStateModel,
)
from app.services.operations_control_plane_service import OperationsControlPlaneService


@pytest_asyncio.fixture
async def lifecycle_variants(db_session: AsyncSession):
    """Create variants in different lifecycle states."""
    variants = {}

    for state_name, state in [
        ("testing", SkuLifecycleState.TESTING),
        ("scaling", SkuLifecycleState.SCALING),
        ("declining", SkuLifecycleState.DECLINING),
        ("clearance", SkuLifecycleState.CLEARANCE),
    ]:
        master = ProductMaster(
            id=uuid4(),
            internal_sku=f"OPS-{state_name.upper()}-{uuid4().hex[:8]}",
            name=f"Operations {state_name.title()} Product",
            status="active",
        )
        db_session.add(master)
        await db_session.flush()

        variant = ProductVariant(
            id=uuid4(),
            master_id=master.id,
            variant_sku=f"OPS-{state_name.upper()}-{uuid4().hex[:8]}-V1",
            status=ProductVariantStatus.ACTIVE,
        )
        db_session.add(variant)
        await db_session.flush()

        lifecycle = SkuLifecycleStateModel(
            id=uuid4(),
            product_variant_id=variant.id,
            current_state=state,
            entered_at=datetime.now(timezone.utc) - timedelta(days=7),
            state_metadata={"confidence_score": 0.85 if state in [SkuLifecycleState.TESTING, SkuLifecycleState.SCALING] else 0.65},
        )
        db_session.add(lifecycle)

        variants[state_name] = variant

    await db_session.commit()
    return variants


@pytest_asyncio.fixture
async def pending_actions(db_session: AsyncSession, lifecycle_variants):
    """Create pending action execution logs."""
    actions = []

    action_data = [
        {
            "action_type": ActionType.REPRICING,
            "target_type": "product_variant",
            "target_id": lifecycle_variants["testing"].id,
            "input_params": {"price_change_percentage": -0.1},
        },
        {
            "action_type": ActionType.DELIST,
            "target_type": "platform_listing",
            "target_id": uuid4(),
            "input_params": {"reason": "declining_performance"},
        },
    ]

    for data in action_data:
        action = ActionExecutionLog(
            id=uuid4(),
            action_type=data["action_type"],
            target_type=data["target_type"],
            target_id=data["target_id"],
            status=ActionExecutionStatus.PENDING,
            started_at=datetime.now(timezone.utc),
            input_params=data["input_params"],
        )
        db_session.add(action)
        actions.append(action)

    await db_session.commit()
    return actions


@pytest_asyncio.fixture
async def active_listing_with_anomalies(db_session: AsyncSession, lifecycle_variants, sample_candidate):
    """Create active listing and data that trigger anomalies."""
    variant = lifecycle_variants["testing"]

    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        product_variant_id=variant.id,
        platform=TargetPlatform.TEMU,
        region="US",
        status=PlatformListingStatus.ACTIVE,
        price=Decimal("50.00"),
        currency="USD",
    )
    db_session.add(listing)

    # Create profit ledger entries causing sales drop
    today = date.today()
    for i in range(7):
        db_session.add(
            ProfitLedger(
                id=uuid4(),
                product_variant_id=variant.id,
                platform_listing_id=listing.id,
                snapshot_date=today - timedelta(days=i),
                gross_revenue=Decimal("40.00"),
                net_profit=Decimal("8.00"),
                profit_margin=Decimal("20.00"),
            )
        )

    for i in range(7, 14):
        db_session.add(
            ProfitLedger(
                id=uuid4(),
                product_variant_id=variant.id,
                platform_listing_id=listing.id,
                snapshot_date=today - timedelta(days=i),
                gross_revenue=Decimal("100.00"),
                net_profit=Decimal("30.00"),
                profit_margin=Decimal("30.00"),
            )
        )

    db_session.add(
        InventoryLevel(
            id=uuid4(),
            variant_id=variant.id,
            available_quantity=3,
            reserved_quantity=0,
            damaged_quantity=0,
        )
    )

    await db_session.commit()
    return listing


class TestGetDailyExceptions:
    """Tests for get_daily_exceptions."""

    @pytest.mark.asyncio
    async def test_get_daily_exceptions_empty(self, db_session: AsyncSession):
        """Test daily exceptions with no anomalies."""
        service = OperationsControlPlaneService()

        result = await service.get_daily_exceptions(db=db_session, limit=100)

        assert "date" in result
        assert "total_anomalies" in result
        assert "by_severity" in result
        assert "anomalies" in result
        assert result["total_anomalies"] == 0
        assert result["anomalies"] == []

    @pytest.mark.asyncio
    async def test_get_daily_exceptions_with_anomalies(
        self, db_session: AsyncSession, active_listing_with_anomalies
    ):
        """Test daily exceptions returns global anomalies."""
        service = OperationsControlPlaneService()

        result = await service.get_daily_exceptions(db=db_session, limit=100)

        assert result["total_anomalies"] >= 1
        assert isinstance(result["anomalies"], list)
        assert "critical" in result["by_severity"]
        assert "high" in result["by_severity"]
        assert "medium" in result["by_severity"]
        assert "low" in result["by_severity"]

    @pytest.mark.asyncio
    async def test_get_daily_exceptions_respects_limit(
        self, db_session: AsyncSession, active_listing_with_anomalies
    ):
        """Test daily exceptions respects result limit."""
        service = OperationsControlPlaneService()

        result = await service.get_daily_exceptions(db=db_session, limit=1)

        assert len(result["anomalies"]) <= 1


class TestGetScalingCandidates:
    """Tests for get_scaling_candidates."""

    @pytest.mark.asyncio
    async def test_get_scaling_candidates_empty(self, db_session: AsyncSession):
        """Test scaling candidates with no lifecycle states."""
        service = OperationsControlPlaneService()

        candidates = await service.get_scaling_candidates(db=db_session, limit=50)

        assert candidates == []

    @pytest.mark.asyncio
    async def test_get_scaling_candidates_returns_testing_and_scaling(
        self, db_session: AsyncSession, lifecycle_variants
    ):
        """Test scaling candidates include TESTING and SCALING states."""
        service = OperationsControlPlaneService()

        candidates = await service.get_scaling_candidates(db=db_session, limit=50)

        assert len(candidates) == 2
        states = {candidate["current_state"] for candidate in candidates}
        assert states == {"testing", "scaling"}

        for candidate in candidates:
            assert "product_variant_id" in candidate
            assert "entered_at" in candidate
            assert "confidence_score" in candidate
            assert "reason" in candidate
            assert candidate["reason"] == "Testing/Scaling with good performance"

    @pytest.mark.asyncio
    async def test_get_scaling_candidates_respects_limit(
        self, db_session: AsyncSession, lifecycle_variants
    ):
        """Test scaling candidates respects limit."""
        service = OperationsControlPlaneService()

        candidates = await service.get_scaling_candidates(db=db_session, limit=1)

        assert len(candidates) == 1


class TestGetClearanceCandidates:
    """Tests for get_clearance_candidates."""

    @pytest.mark.asyncio
    async def test_get_clearance_candidates_empty(self, db_session: AsyncSession):
        """Test clearance candidates with no lifecycle states."""
        service = OperationsControlPlaneService()

        candidates = await service.get_clearance_candidates(db=db_session, limit=50)

        assert candidates == []

    @pytest.mark.asyncio
    async def test_get_clearance_candidates_returns_declining_and_clearance(
        self, db_session: AsyncSession, lifecycle_variants
    ):
        """Test clearance candidates include DECLINING and CLEARANCE states."""
        service = OperationsControlPlaneService()

        candidates = await service.get_clearance_candidates(db=db_session, limit=50)

        assert len(candidates) == 2
        states = {candidate["current_state"] for candidate in candidates}
        assert states == {"declining", "clearance"}

        for candidate in candidates:
            assert "product_variant_id" in candidate
            assert "entered_at" in candidate
            assert "confidence_score" in candidate
            assert "reason" in candidate
            assert candidate["reason"] == "Declining/Clearance with poor performance"

    @pytest.mark.asyncio
    async def test_get_clearance_candidates_respects_limit(
        self, db_session: AsyncSession, lifecycle_variants
    ):
        """Test clearance candidates respects limit."""
        service = OperationsControlPlaneService()

        candidates = await service.get_clearance_candidates(db=db_session, limit=1)

        assert len(candidates) == 1


class TestGetPendingActionApprovals:
    """Tests for get_pending_action_approvals."""

    @pytest.mark.asyncio
    async def test_get_pending_action_approvals_empty(self, db_session: AsyncSession):
        """Test pending actions with no action logs."""
        service = OperationsControlPlaneService()

        pending = await service.get_pending_action_approvals(db=db_session, limit=50)

        assert pending == []

    @pytest.mark.asyncio
    async def test_get_pending_action_approvals_returns_pending_actions(
        self, db_session: AsyncSession, pending_actions
    ):
        """Test pending action approvals returns pending action logs."""
        service = OperationsControlPlaneService()

        pending = await service.get_pending_action_approvals(db=db_session, limit=50)

        assert len(pending) == 2

        for item in pending:
            assert "execution_id" in item
            assert "action_type" in item
            assert "target_type" in item
            assert "input_params" in item
            assert "status" in item
            assert item["status"] == "pending"
            assert "created_at" in item

    @pytest.mark.asyncio
    async def test_get_pending_action_approvals_separates_target_types(
        self, db_session: AsyncSession, pending_actions
    ):
        """Test pending actions expose product_variant_id or listing_id based on target type."""
        service = OperationsControlPlaneService()

        pending = await service.get_pending_action_approvals(db=db_session, limit=50)

        product_variant_action = next(item for item in pending if item["target_type"] == "product_variant")
        platform_listing_action = next(item for item in pending if item["target_type"] == "platform_listing")

        assert product_variant_action["product_variant_id"] is not None
        assert product_variant_action["listing_id"] is None
        assert platform_listing_action["listing_id"] is not None
        assert platform_listing_action["product_variant_id"] is None


class TestGetOperationsSummary:
    """Tests for get_operations_summary."""

    @pytest.mark.asyncio
    async def test_get_operations_summary_empty(self, db_session: AsyncSession):
        """Test operations summary with no data."""
        service = OperationsControlPlaneService()

        summary = await service.get_operations_summary(db=db_session)

        assert "daily_exceptions" in summary
        assert "scaling_candidates_count" in summary
        assert "clearance_candidates_count" in summary
        assert "pending_actions_count" in summary
        assert summary["daily_exceptions"]["total"] == 0
        assert summary["scaling_candidates_count"] == 0
        assert summary["clearance_candidates_count"] == 0
        assert summary["pending_actions_count"] == 0

    @pytest.mark.asyncio
    async def test_get_operations_summary_with_data(
        self,
        db_session: AsyncSession,
        lifecycle_variants,
        pending_actions,
        active_listing_with_anomalies,
    ):
        """Test operations summary aggregates data from all sections."""
        service = OperationsControlPlaneService()

        summary = await service.get_operations_summary(db=db_session)

        assert summary["daily_exceptions"]["total"] >= 1
        assert summary["scaling_candidates_count"] == 2
        assert summary["clearance_candidates_count"] == 2
        assert summary["pending_actions_count"] == 2
        assert "by_severity" in summary["daily_exceptions"]
