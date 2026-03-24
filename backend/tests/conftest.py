"""Test fixtures and configuration."""
import pytest_asyncio
from sqlalchemy import ARRAY as SA_ARRAY
from sqlalchemy.dialects.postgresql import ARRAY as PG_ARRAY, UUID as PGUUID
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.ext.compiler import compiles

from app.db.base import Base


@compiles(PGUUID, "sqlite")
def compile_uuid_sqlite(_type, _compiler, **_kw):
    """Map PostgreSQL UUID columns to SQLite-compatible storage for tests."""
    return "CHAR(36)"


@compiles(SA_ARRAY, "sqlite")
@compiles(PG_ARRAY, "sqlite")
def compile_array_sqlite(_type, _compiler, **_kw):
    """Map PostgreSQL ARRAY columns to SQLite JSON storage for tests."""
    return "JSON"


@pytest_asyncio.fixture
async def db_session():
    """Create a test database session."""
    engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with session_factory() as session:
        yield session

    await engine.dispose()
