"""Test fixtures and configuration."""
from decimal import Decimal
from uuid import uuid4

import pytest_asyncio
from sqlalchemy import ARRAY as SA_ARRAY, JSON
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.core.enums import (
    CandidateStatus,
    PlatformListingStatus,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.base import Base
from app.db.models import CandidateProduct, PlatformListing, StrategyRun


@compiles(PGUUID, "sqlite")
def compile_uuid_sqlite(_type, _compiler, **_kw):
    """Map PostgreSQL UUID columns to SQLite-compatible storage for tests."""
    return "CHAR(36)"


@compiles(SA_ARRAY, "sqlite")
@compiles(PG_ARRAY, "sqlite")
def compile_array_sqlite(_type, _compiler, **_kw):
    """Map PostgreSQL ARRAY columns to SQLite JSON storage for tests."""
    return "JSON"


def _adapt_array_columns_for_sqlite() -> None:
    """Replace ARRAY column types with JSON so SQLite can bind Python lists."""
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if isinstance(column.type, (SA_ARRAY, PG_ARRAY)):
                column.type = JSON()


@pytest_asyncio.fixture
async def db_session():
    """Create a test database session."""
    _adapt_array_columns_for_sqlite()
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()


@pytest_asyncio.fixture
async def sample_strategy_run(db_session):
    """Create a sample strategy run."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.MANUAL,
        status=StrategyRunStatus.COMPLETED,
    )
    db_session.add(strategy_run)
    await db_session.commit()
    await db_session.refresh(strategy_run)
    return strategy_run


@pytest_asyncio.fixture
async def sample_candidate(db_session, sample_strategy_run):
    """Create a sample candidate product."""
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=sample_strategy_run.id,
        source_platform=SourcePlatform.TEMU,
        title="Test Product",
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)
    await db_session.commit()
    await db_session.refresh(candidate)
    return candidate


@pytest_asyncio.fixture
async def sample_pending_listing(db_session, sample_candidate):
    """Create a sample pending approval listing."""
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        status=PlatformListingStatus.PENDING_APPROVAL,
        approval_required=True,
        approval_reason="first_time_product",
    )
    db_session.add(listing)
    await db_session.commit()
    await db_session.refresh(listing)
    return listing


@pytest_asyncio.fixture
async def sample_active_listing(db_session, sample_candidate):
    """Create a sample active listing."""
    listing = PlatformListing(
        id=uuid4(),
        candidate_product_id=sample_candidate.id,
        platform=TargetPlatform.TEMU,
        region="US",
        price=Decimal("50.0"),
        currency="USD",
        status=PlatformListingStatus.ACTIVE,
        platform_listing_id="temu_12345",
    )
    db_session.add(listing)
    await db_session.commit()
    await db_session.refresh(listing)
    return listing

