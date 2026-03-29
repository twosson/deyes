"""Tests for TextOverlayService."""
import io
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import (
    AssetType,
    ContentUsageScope,
    InventoryMode,
    LocalizationType,
    ProductMasterStatus,
    ProductVariantStatus,
    SourcePlatform,
    StrategyRunStatus,
    TargetPlatform,
    TriggerType,
)
from app.db.models import (
    CandidateProduct,
    ContentAsset,
    LocalizationContent,
    ProductMaster,
    ProductVariant,
    StrategyRun,
)
from app.services.text_overlay_service import TextOverlayService


def create_test_image(width: int, height: int, color: str = "red") -> bytes:
    """Create a test image."""
    image = Image.new("RGB", (width, height), color=color)
    output = io.BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


async def _create_variant_with_base_asset(
    db_session: AsyncSession,
) -> tuple[ProductVariant, CandidateProduct, ContentAsset]:
    """Create variant with base asset."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.flush()

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        title="Test Product",
    )
    db_session.add(candidate)
    await db_session.flush()

    master = ProductMaster(
        id=uuid4(),
        candidate_product_id=candidate.id,
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

    # Create base asset
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        product_variant_id=variant.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.png",
        usage_scope=ContentUsageScope.BASE,
        spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
            "has_text": False,
        },
        format="png",
    )
    db_session.add(base_asset)
    await db_session.flush()

    return variant, candidate, base_asset


@pytest.mark.asyncio
async def test_render_text_on_image_top_left():
    """Should render text at top-left position."""
    service = TextOverlayService()

    # Create test image
    source_image = create_test_image(800, 800, "white")

    # Render text
    text_config = {
        "text": "Free Shipping",
        "position": "top-left",
        "font_size": 24,
        "font_color": "#000000",
    }

    rendered_image = await service.render_text_on_image(source_image, text_config)

    # Verify image is valid
    image = Image.open(io.BytesIO(rendered_image))
    assert image.size == (800, 800)
    assert image.format == "PNG"


@pytest.mark.asyncio
async def test_render_text_on_image_with_background():
    """Should render text with background color."""
    service = TextOverlayService()

    source_image = create_test_image(800, 800, "white")

    text_config = {
        "text": "Sale",
        "position": "top-right",
        "font_size": 32,
        "font_color": "#FFFFFF",
        "background_color": "#FF0000",
        "padding": 15,
    }

    rendered_image = await service.render_text_on_image(source_image, text_config)

    # Verify image is valid
    image = Image.open(io.BytesIO(rendered_image))
    assert image.size == (800, 800)


@pytest.mark.asyncio
async def test_render_text_on_image_center():
    """Should render text at center position."""
    service = TextOverlayService()

    source_image = create_test_image(800, 800, "blue")

    text_config = {
        "text": "NEW",
        "position": "center",
        "font_size": 48,
        "font_color": "#FFFFFF",
    }

    rendered_image = await service.render_text_on_image(source_image, text_config)

    # Verify image is valid
    image = Image.open(io.BytesIO(rendered_image))
    assert image.size == (800, 800)


@pytest.mark.asyncio
async def test_render_text_empty_text():
    """Should return original image when text is empty."""
    service = TextOverlayService()

    source_image = create_test_image(800, 800)

    text_config = {
        "text": "",
        "position": "top-left",
    }

    rendered_image = await service.render_text_on_image(source_image, text_config)

    # Should return original image
    assert rendered_image == source_image


@pytest.mark.asyncio
async def test_get_localization_text_found(db_session: AsyncSession):
    """Should retrieve localization text."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Create localization content
    localization = LocalizationContent(
        id=uuid4(),
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.IMAGE_TEXT,
        content={
            "text": "Free Shipping",
            "position": "top-left",
            "font_size": 24,
        },
        platform_tags=["temu"],
    )
    db_session.add(localization)
    await db_session.commit()

    # Get localization text
    service = TextOverlayService()
    text_config = await service.get_localization_text(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.IMAGE_TEXT,
        platform=TargetPlatform.TEMU,
        db=db_session,
    )

    assert text_config is not None
    assert text_config["text"] == "Free Shipping"
    assert text_config["position"] == "top-left"


@pytest.mark.asyncio
async def test_get_localization_text_not_found(db_session: AsyncSession):
    """Should return None when localization text not found."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)
    await db_session.commit()

    # Get localization text (not created)
    service = TextOverlayService()
    text_config = await service.get_localization_text(
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.IMAGE_TEXT,
        db=db_session,
    )

    assert text_config is None


@pytest.mark.asyncio
async def test_overlay_localized_text_success(db_session: AsyncSession):
    """Should overlay localized text on base asset."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Create localization content
    localization = LocalizationContent(
        id=uuid4(),
        variant_id=variant.id,
        language="en",
        content_type=LocalizationType.IMAGE_TEXT,
        content={
            "text": "Free Shipping",
            "position": "top-left",
            "font_size": 24,
            "font_color": "#FFFFFF",
            "background_color": "#FF0000",
        },
        platform_tags=["temu"],
    )
    db_session.add(localization)
    await db_session.commit()

    # Mock MinIO client
    mock_minio = AsyncMock()
    mock_minio.download_image = AsyncMock(
        return_value=create_test_image(1024, 1024)
    )
    mock_minio.upload_image = AsyncMock(
        return_value="https://example.com/localized.png"
    )

    # Overlay text
    service = TextOverlayService(minio_client=mock_minio)
    result = await service.overlay_localized_text(
        base_asset=base_asset,
        platform=TargetPlatform.TEMU,
        language="en",
        db=db_session,
    )

    assert result["status"] == "success"
    assert result["asset"].usage_scope == ContentUsageScope.LOCALIZED
    assert result["asset"].parent_asset_id == base_asset.id
    assert result["asset"].platform_tags == ["temu"]
    assert result["asset"].language_tags == ["en"]

    # Verify MinIO calls
    mock_minio.download_image.assert_called_once()
    mock_minio.upload_image.assert_called_once()


@pytest.mark.asyncio
async def test_overlay_localized_text_no_text_found(db_session: AsyncSession):
    """Should return no_text_found when localization not configured."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)
    await db_session.commit()

    # Mock MinIO client
    mock_minio = AsyncMock()

    # Overlay text (no localization content created)
    service = TextOverlayService(minio_client=mock_minio)
    result = await service.overlay_localized_text(
        base_asset=base_asset,
        platform=TargetPlatform.TEMU,
        language="en",
        db=db_session,
    )

    assert result["status"] == "no_text_found"
    assert result["reason"] == "no_localization_text_configured"

    # MinIO should not be called
    mock_minio.download_image.assert_not_called()
    mock_minio.upload_image.assert_not_called()
