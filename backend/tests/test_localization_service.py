"""Tests for LocalizationService."""
import pytest
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    InventoryMode,
    LocalizationType,
    ProductMasterStatus,
    ProductVariantStatus,
)
from app.db.models import ProductMaster, ProductVariant
from app.services.localization_service import LocalizationService


async def _create_variant(db_session: AsyncSession) -> ProductVariant:
    master = ProductMaster(
        id=uuid4(),
        internal_sku="SKU-TEST-001",
        name="Test Product",
        status=ProductMasterStatus.ACTIVE,
    )
    db_session.add(master)
    await db_session.flush()

    variant = ProductVariant(
        id=uuid4(),
        master_id=master.id,
        variant_sku="SKU-TEST-001",
        inventory_mode=InventoryMode.STOCK_FIRST,
        status=ProductVariantStatus.ACTIVE,
    )
    db_session.add(variant)
    await db_session.flush()
    return variant


@pytest.mark.asyncio
async def test_create_localization(db_session: AsyncSession):
    """Should create localization content."""
    variant = await _create_variant(db_session)
    await db_session.commit()

    service = LocalizationService()
    localization = await service.create_localization(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.TITLE,
        content={"text": "Amazing Product"},
        db=db_session,
        generated_by="qwen3.5",
    )

    assert localization.variant_id == variant.id
    assert localization.language == "en"
    assert localization.content_type == LocalizationType.TITLE
    assert localization.content["text"] == "Amazing Product"
    assert localization.generated_by == "qwen3.5"
    assert localization.reviewed is False


@pytest.mark.asyncio
async def test_create_localization_is_idempotent(db_session: AsyncSession):
    """Should update existing localization if already exists."""
    variant = await _create_variant(db_session)
    await db_session.commit()

    service = LocalizationService()

    # Create first time
    loc1 = await service.create_localization(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.TITLE,
        content={"text": "First Title"},
        db=db_session,
    )
    await db_session.commit()

    # Create again with same key
    loc2 = await service.create_localization(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.TITLE,
        content={"text": "Updated Title"},
        db=db_session,
    )
    await db_session.commit()

    # Should be same ID
    assert loc1.id == loc2.id
    assert loc2.content["text"] == "Updated Title"


@pytest.mark.asyncio
async def test_get_localization(db_session: AsyncSession):
    """Should retrieve localization by variant, language, and type."""
    variant = await _create_variant(db_session)
    await db_session.commit()

    service = LocalizationService()
    await service.create_localization(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.DESCRIPTION,
        content={"text": "Product description"},
        db=db_session,
    )
    await db_session.commit()

    localization = await service.get_localization(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.DESCRIPTION,
        db=db_session,
    )

    assert localization is not None
    assert localization.content["text"] == "Product description"


@pytest.mark.asyncio
async def test_list_localizations(db_session: AsyncSession):
    """Should list all localizations for a variant."""
    variant = await _create_variant(db_session)
    await db_session.commit()

    service = LocalizationService()

    # Create multiple localizations
    await service.create_localization(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.TITLE,
        content={"text": "English Title"},
        db=db_session,
    )
    await service.create_localization(
        variant_id=variant.id,
        language="zh",
        content_type=LocalizationType.TITLE,
        content={"text": "中文标题"},
        db=db_session,
    )
    await service.create_localization(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.DESCRIPTION,
        content={"text": "English Description"},
        db=db_session,
    )
    await db_session.commit()

    # List all
    all_localizations = await service.list_localizations(
        variant_id=variant.id,
        db=db_session,
    )
    assert len(all_localizations) == 3

    # Filter by language
    en_localizations = await service.list_localizations(
        variant_id=variant.id,
        language="en",
        db=db_session,
    )
    assert len(en_localizations) == 2

    # Filter by content type
    title_localizations = await service.list_localizations(
        variant_id=variant.id,
        content_type=LocalizationType.TITLE,
        db=db_session,
    )
    assert len(title_localizations) == 2


@pytest.mark.asyncio
async def test_update_localization(db_session: AsyncSession):
    """Should update localization content."""
    variant = await _create_variant(db_session)
    await db_session.commit()

    service = LocalizationService()
    localization = await service.create_localization(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.TITLE,
        content={"text": "Original Title"},
        db=db_session,
    )
    await db_session.commit()

    updated = await service.update_localization(
        localization_id=localization.id,
        content={"text": "Updated Title"},
        quality_score=0.95,
        reviewed=True,
        db=db_session,
    )
    await db_session.commit()

    assert updated is not None
    assert updated.content["text"] == "Updated Title"
    assert updated.quality_score == Decimal("0.95")
    assert updated.reviewed is True


@pytest.mark.asyncio
async def test_list_localizations_with_platform_filter(db_session: AsyncSession):
    """Should filter localizations by platform tags."""
    variant = await _create_variant(db_session)
    await db_session.commit()

    service = LocalizationService()

    await service.create_localization(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.TITLE,
        content={"text": "Amazon Title"},
        platform_tags=["amazon"],
        db=db_session,
    )
    await service.create_localization(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.DESCRIPTION,
        content={"text": "Temu Description"},
        platform_tags=["temu"],
        db=db_session,
    )
    await db_session.commit()

    amazon_localizations = await service.list_localizations(
        variant_id=variant.id,
        platform="amazon",
        db=db_session,
    )
    assert len(amazon_localizations) == 1
    assert amazon_localizations[0].content["text"] == "Amazon Title"
