"""Tests for platform sync agent integration."""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from uuid import uuid4
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.base.agent import AgentContext
from app.agents.platform_publisher import PlatformSyncAgent
from app.core.enums import (
    CandidateStatus,
    PlatformListingStatus,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import CandidateProduct, PlatformListing, StrategyRun


async def _create_strategy_run(db_session: AsyncSession) -> StrategyRun:
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.COMPLETED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()
    return strategy_run


async def _create_candidate(db_session: AsyncSession) -> CandidateProduct:
    strategy_run = await _create_strategy_run(db_session)
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id=f"sync-{uuid4()}",
        title="Sync Test Product",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)
    await db_session.flush()
    return candidate


async def _create_listing(
    db_session: AsyncSession,
    *,
    candidate_id,
    region: str,
    status: PlatformListingStatus = PlatformListingStatus.ACTIVE,
) -> PlatformListing:
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=candidate_id,
        platform=TargetPlatform.TEMU,
        region=region,
        platform_listing_id=f"TEMU-{uuid4().hex[:10].upper()}",
        price=Decimal("19.99"),
        currency="USD" if region == "us" else "GBP",
        inventory=10,
        status=status,
    )
    db_session.add(listing)
    await db_session.flush()
    return listing


@pytest.mark.asyncio
async def test_platform_sync_agent_syncs_active_listings(db_session: AsyncSession):
    """PlatformSyncAgent should call PlatformSyncService for active listings."""
    candidate = await _create_candidate(db_session)
    listing1 = await _create_listing(db_session, candidate_id=candidate.id, region="us")
    listing2 = await _create_listing(db_session, candidate_id=candidate.id, region="uk")
    await db_session.commit()

    agent = PlatformSyncAgent()
    agent.sync_service.sync_listing_metrics = AsyncMock(
        return_value={"status": "ok", "synced_days": 1}
    )

    today = date.today()
    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "sync_type": "listing_metrics",
            "start_date": str(today),
            "end_date": str(today),
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["synced_count"] == 2
    assert result.output_data["failed_count"] == 0
    assert result.output_data["start_date"] == str(today)
    assert result.output_data["end_date"] == str(today)
    assert agent.sync_service.sync_listing_metrics.await_count == 2

    for awaited_call in agent.sync_service.sync_listing_metrics.await_args_list:
        assert awaited_call.kwargs["start_date"] == today
        assert awaited_call.kwargs["end_date"] == today

    await db_session.refresh(listing1)
    await db_session.refresh(listing2)
    assert listing1.last_synced_at is not None
    assert listing2.last_synced_at is not None
    assert listing1.sync_error is None
    assert listing2.sync_error is None


@pytest.mark.asyncio
async def test_platform_sync_agent_filters_by_listing_ids(db_session: AsyncSession):
    """PlatformSyncAgent should only sync requested listing ids when provided."""
    candidate = await _create_candidate(db_session)
    target_listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")
    other_listing = await _create_listing(db_session, candidate_id=candidate.id, region="uk")
    await db_session.commit()

    agent = PlatformSyncAgent()
    agent.sync_service.sync_listing_metrics = AsyncMock(
        return_value={"status": "ok", "synced_days": 1}
    )

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "sync_type": "listing_metrics",
            "platform_listing_ids": [str(target_listing.id)],
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["synced_count"] == 1
    assert result.output_data["failed_count"] == 0
    assert agent.sync_service.sync_listing_metrics.await_count == 1
    awaited_call = agent.sync_service.sync_listing_metrics.await_args_list[0]
    assert awaited_call.kwargs["listing_id"] == target_listing.id

    await db_session.refresh(target_listing)
    await db_session.refresh(other_listing)
    assert target_listing.last_synced_at is not None
    assert other_listing.last_synced_at is None


@pytest.mark.asyncio
async def test_platform_sync_agent_records_sync_errors(db_session: AsyncSession):
    """PlatformSyncAgent should record sync_error when service call fails."""
    candidate = await _create_candidate(db_session)
    listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")
    await db_session.commit()

    agent = PlatformSyncAgent()
    agent.sync_service.sync_listing_metrics = AsyncMock(side_effect=RuntimeError("sync failed"))

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "sync_type": "listing_metrics",
        },
    )

    result = await agent.execute(context)

    assert result.success is False
    assert result.output_data["synced_count"] == 0
    assert result.output_data["failed_count"] == 1

    await db_session.refresh(listing)
    assert listing.last_synced_at is None
    assert listing.sync_error == "sync failed"


@pytest.mark.asyncio
async def test_platform_sync_agent_rejects_invalid_date_range(db_session: AsyncSession):
    """PlatformSyncAgent should reject end_date earlier than start_date."""
    agent = PlatformSyncAgent()

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "sync_type": "listing_metrics",
            "start_date": "2026-03-10",
            "end_date": "2026-03-01",
        },
    )

    result = await agent.execute(context)

    assert result.success is False
    assert "end_date cannot be earlier than start_date" in result.error_message


@pytest.mark.asyncio
async def test_platform_sync_agent_dispatches_status_sync(db_session: AsyncSession):
    """PlatformSyncAgent should call sync_listing_status for status sync_type."""
    candidate = await _create_candidate(db_session)
    listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")
    await db_session.commit()

    agent = PlatformSyncAgent()
    agent.sync_service.sync_listing_status = AsyncMock(
        return_value={"listing_id": str(listing.id), "status": "ok"}
    )

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={"sync_type": "status"},
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["synced_count"] == 1
    assert agent.sync_service.sync_listing_status.await_count == 1


@pytest.mark.asyncio
async def test_platform_sync_agent_dispatches_inventory_sync(db_session: AsyncSession):
    """PlatformSyncAgent should call sync_listing_inventory for inventory sync_type."""
    candidate = await _create_candidate(db_session)
    listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")
    await db_session.commit()

    agent = PlatformSyncAgent()
    agent.sync_service.sync_listing_inventory = AsyncMock(
        return_value={"listing_id": str(listing.id), "status": "ok"}
    )

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={"sync_type": "inventory"},
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["synced_count"] == 1
    assert agent.sync_service.sync_listing_inventory.await_count == 1


@pytest.mark.asyncio
async def test_platform_sync_agent_dispatches_price_sync(db_session: AsyncSession):
    """PlatformSyncAgent should call sync_listing_price for price sync_type."""
    candidate = await _create_candidate(db_session)
    listing = await _create_listing(db_session, candidate_id=candidate.id, region="us")
    await db_session.commit()

    agent = PlatformSyncAgent()
    agent.sync_service.sync_listing_price = AsyncMock(
        return_value={"listing_id": str(listing.id), "status": "ok"}
    )

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={"sync_type": "price"},
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["synced_count"] == 1
    assert agent.sync_service.sync_listing_price.await_count == 1
