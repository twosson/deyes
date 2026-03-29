"""Tests for AssetDerivationService."""
import io
from unittest.mock import AsyncMock, MagicMock
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
    PlatformContentRule,
    ProductMaster,
    ProductVariant,
    StrategyRun,
)
from app.services.asset_derivation_service import AssetDerivationService


def create_test_image(width: int, height: int, format: str = "PNG") -> bytes:
    """Create a test image."""
    image = Image.new("RGB", (width, height), color="red")
    output = io.BytesIO()
    image.save(output, format=format)
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
    )
    db_session.add(base_asset)
    await db_session.flush()

    return variant, candidate, base_asset


@pytest.mark.asyncio
async def test_resize_success():
    """Should resize image successfully."""
    service = AssetDerivationService()

    # Create 1024x1024 test image
    source_image = create_test_image(1024, 1024, "PNG")

    # Resize to 1000x1000
    resized_image, metadata = await service.resize(source_image, 1000, 1000)

    assert metadata["status"] == "success"
    assert metadata["source_size"] == "1024x1024"
    assert metadata["target_size"] == "1000x1000"

    # Verify resized image dimensions
    image = Image.open(io.BytesIO(resized_image))
    assert image.size == (1000, 1000)


@pytest.mark.asyncio
async def test_resize_source_too_small():
    """Should return regenerate_needed when source is smaller than target."""
    service = AssetDerivationService()

    # Create 800x800 test image
    source_image = create_test_image(800, 800, "PNG")

    # Try to resize to 1000x1000
    resized_image, metadata = await service.resize(source_image, 1000, 1000)

    assert metadata["status"] == "regenerate_needed"
    assert metadata["reason"] == "source_too_small"
    assert metadata["source_size"] == "800x800"
    assert metadata["target_size"] == "1000x1000"


@pytest.mark.asyncio
async def test_convert_format_png_to_jpg():
    """Should convert PNG to JPG."""
    service = AssetDerivationService()

    # Create PNG test image
    source_image = create_test_image(1024, 1024, "PNG")

    # Convert to JPG
    converted_image = await service.convert_format(source_image, "jpg")

    # Verify format
    image = Image.open(io.BytesIO(converted_image))
    assert image.format == "JPEG"


@pytest.mark.asyncio
async def test_convert_format_rgba_to_jpg():
    """Should convert RGBA PNG to JPG with white background."""
    service = AssetDerivationService()

    # Create RGBA test image
    image = Image.new("RGBA", (1024, 1024), color=(255, 0, 0, 128))
    output = io.BytesIO()
    image.save(output, format="PNG")
    source_image = output.getvalue()

    # Convert to JPG
    converted_image = await service.convert_format(source_image, "jpg")

    # Verify format and mode
    result_image = Image.open(io.BytesIO(converted_image))
    assert result_image.format == "JPEG"
    assert result_image.mode == "RGB"


@pytest.mark.asyncio
async def test_derive_asset_reuse(db_session: AsyncSession):
    """Should reuse compliant base asset."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Create compliant platform rule (matches base asset spec)
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
        },
        allow_text_on_image=False,
        max_images=10,
        required_languages=["en"],
    )
    db_session.add(rule)
    await db_session.commit()

    # Mock MinIO client
    mock_minio = AsyncMock()
    service = AssetDerivationService(minio_client=mock_minio)

    # Derive asset
    result = await service.derive_asset(
        base_asset=base_asset,
        platform=TargetPlatform.TEMU,
        db=db_session,
    )

    assert result["status"] == "success"
    assert "reuse" in result["actions_performed"]
    assert result["asset"].usage_scope == ContentUsageScope.PLATFORM_DERIVED
    assert result["asset"].parent_asset_id == base_asset.id


@pytest.mark.asyncio
async def test_derive_asset_resize_and_convert(db_session: AsyncSession):
    """Should resize and convert format."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Create platform rule requiring different dimensions and format
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1000,
            "height": 1000,
            "format": "jpg",
        },
        allow_text_on_image=False,
        max_images=10,
        required_languages=["en"],
    )
    db_session.add(rule)
    await db_session.commit()

    # Mock MinIO client
    mock_minio = AsyncMock()
    mock_minio.download_image = AsyncMock(
        return_value=create_test_image(1024, 1024, "PNG")
    )
    mock_minio.upload_image = AsyncMock(
        return_value="https://example.com/derived.jpg"
    )

    service = AssetDerivationService(minio_client=mock_minio)

    # Derive asset
    result = await service.derive_asset(
        base_asset=base_asset,
        platform=TargetPlatform.AMAZON,
        db=db_session,
    )

    assert result["status"] == "success"
    assert "resize" in result["actions_performed"]
    assert "convert_format" in result["actions_performed"]
    assert result["asset"].usage_scope == ContentUsageScope.PLATFORM_DERIVED
    assert result["asset"].platform_tags == ["amazon"]
    assert result["asset"].spec["format"] == "jpg"
    assert result["asset"].spec["width"] == 1000
    assert result["asset"].spec["height"] == 1000

    # Verify MinIO calls
    mock_minio.download_image.assert_called_once()
    mock_minio.upload_image.assert_called_once()


@pytest.mark.asyncio
async def test_derive_asset_source_too_small(db_session: AsyncSession):
    """Should defer when source is too small for resize."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Update base asset to smaller dimensions
    base_asset.spec = {
        "width": 800,
        "height": 800,
        "format": "png",
        "has_text": False,
    }
    await db_session.commit()

    # Create platform rule requiring larger dimensions
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1000,
            "height": 1000,
            "format": "jpg",
        },
        allow_text_on_image=False,
        max_images=10,
        required_languages=["en"],
    )
    db_session.add(rule)
    await db_session.commit()

    # Mock MinIO client
    mock_minio = AsyncMock()
    mock_minio.download_image = AsyncMock(
        return_value=create_test_image(800, 800, "PNG")
    )

    service = AssetDerivationService(minio_client=mock_minio)

    # Derive asset
    result = await service.derive_asset(
        base_asset=base_asset,
        platform=TargetPlatform.AMAZON,
        db=db_session,
    )

    assert result["status"] == "deferred"
    assert result["reason"] == "source_too_small_for_resize"


@pytest.mark.asyncio
async def test_derive_asset_text_overlay_success(db_session: AsyncSession):
    """Should overlay localized text when overlay_localized_text action is suggested."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Create localization content
    localization = LocalizationContent(
        id=uuid4(),
        variant_id=variant.id,
        language="zh",
        content_type=LocalizationType.IMAGE_TEXT,
        content={
            "text": "包邮",
            "position": "top-left",
            "font_size": 24,
            "font_color": "#FFFFFF",
            "background_color": "#FF0000",
        },
        platform_tags=["temu"],
    )
    db_session.add(localization)

    # Create platform rule requiring localized variant
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
        },
        allow_text_on_image=True,
        max_images=10,
        required_languages=["en", "zh"],
    )
    db_session.add(rule)
    await db_session.commit()

    # Mock MinIO client
    mock_minio = AsyncMock()
    mock_minio.download_image = AsyncMock(
        return_value=create_test_image(1024, 1024, "PNG")
    )
    mock_minio.upload_image = AsyncMock(
        return_value="https://example.com/localized.png"
    )

    service = AssetDerivationService(minio_client=mock_minio)

    # Derive asset with language
    result = await service.derive_asset(
        base_asset=base_asset,
        platform=TargetPlatform.TEMU,
        language="zh",
        db=db_session,
    )

    assert result["status"] == "success"
    assert "overlay_localized_text" in result["actions_performed"]
    assert result["asset"].usage_scope == ContentUsageScope.LOCALIZED
    assert result["asset"].language_tags == ["zh"]
    assert result["asset"].platform_tags == ["temu"]


@pytest.mark.asyncio
async def test_derive_asset_text_overlay_no_language(db_session: AsyncSession):
    """Should defer when text overlay is required but no language provided."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Create platform rule requiring localized variant
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
        },
        allow_text_on_image=True,
        max_images=10,
        required_languages=["en", "zh"],
    )
    db_session.add(rule)
    await db_session.commit()

    service = AssetDerivationService()

    # Derive asset without language
    result = await service.derive_asset(
        base_asset=base_asset,
        platform=TargetPlatform.TEMU,
        db=db_session,
    )

    assert result["status"] == "deferred"
    assert result["reason"] == "regeneration_not_implemented" or result["reason"] == "language_required_for_text_overlay"


@pytest.mark.asyncio
async def test_derive_asset_text_overlay_no_text_config(db_session: AsyncSession):
    """Should defer gracefully when no localization text is configured."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Create platform rule requiring localized variant
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1024,
            "height": 1024,
            "format": "png",
        },
        allow_text_on_image=True,
        max_images=10,
        required_languages=["en", "zh"],
    )
    db_session.add(rule)
    await db_session.commit()

    # Mock MinIO client
    mock_minio = AsyncMock()
    service = AssetDerivationService(minio_client=mock_minio)

    # Derive asset with language but no localization content
    result = await service.derive_asset(
        base_asset=base_asset,
        platform=TargetPlatform.TEMU,
        language="zh",
        db=db_session,
    )

    # Should defer because no localization text found
    assert result["status"] == "deferred"


@pytest.mark.asyncio
async def test_derive_asset_regenerate_success(db_session: AsyncSession):
    """Should regenerate asset when source is too small."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Update base asset to smaller dimensions
    base_asset.spec = {
        "width": 800,
        "height": 800,
        "format": "png",
        "has_text": False,
    }
    base_asset.generation_params = {
        "prompt": "minimalist product photo",
        "style": "minimalist",
    }
    await db_session.commit()

    # Create platform rule requiring larger dimensions
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1000,
            "height": 1000,
            "format": "png",
        },
        allow_text_on_image=False,
        max_images=10,
        required_languages=["en"],
    )
    db_session.add(rule)
    await db_session.commit()

    # Mock MinIO and ComfyUI
    mock_minio = AsyncMock()
    mock_minio.download_image = AsyncMock(
        return_value=create_test_image(800, 800, "PNG")
    )
    mock_minio.upload_image = AsyncMock(
        return_value="https://example.com/regenerated.png"
    )

    # Mock ComfyUI client
    from app.services.image_generation.comfyui_client import ComfyUIClient
    mock_comfyui = AsyncMock(spec=ComfyUIClient)
    mock_comfyui.generate_product_image = AsyncMock(
        return_value=create_test_image(1000, 1000, "PNG")
    )

    # Patch get_comfyui_client
    from unittest.mock import patch
    with patch(
        "app.services.image_regeneration_service.get_comfyui_client",
        return_value=mock_comfyui,
    ):
        service = AssetDerivationService(minio_client=mock_minio)

        # Derive asset
        result = await service.derive_asset(
            base_asset=base_asset,
            platform=TargetPlatform.AMAZON,
            db=db_session,
        )

    assert result["status"] == "success"
    assert "regenerate" in result["actions_performed"]
    assert result["asset"].usage_scope == ContentUsageScope.PLATFORM_DERIVED
    assert result["asset"].platform_tags == ["amazon"]
    assert result["asset"].spec["width"] == 1000
    assert result["asset"].spec["height"] == 1000
    assert result["asset"].spec["regenerated"] is True

    # Verify ComfyUI was called
    mock_comfyui.generate_product_image.assert_called_once_with(
        prompt="minimalist product photo",
        style="minimalist",
        width=1000,
        height=1000,
    )

    # Verify MinIO upload was called
    mock_minio.upload_image.assert_called_once()


@pytest.mark.asyncio
async def test_derive_asset_regenerate_no_dimensions(db_session: AsyncSession):
    """Should return error when target dimensions not specified."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Update base asset to smaller dimensions
    base_asset.spec = {
        "width": 800,
        "height": 800,
        "format": "png",
        "has_text": False,
    }
    await db_session.commit()

    # Create platform rule without dimensions (invalid)
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "format": "png",
        },
        allow_text_on_image=False,
        max_images=10,
        required_languages=["en"],
    )
    db_session.add(rule)
    await db_session.commit()

    # Mock MinIO
    mock_minio = AsyncMock()
    mock_minio.download_image = AsyncMock(
        return_value=create_test_image(800, 800, "PNG")
    )

    service = AssetDerivationService(minio_client=mock_minio)

    # Derive asset
    result = await service.derive_asset(
        base_asset=base_asset,
        platform=TargetPlatform.AMAZON,
        db=db_session,
    )

    assert result["status"] == "error"
    assert result["reason"] == "target_dimensions_not_specified"


@pytest.mark.asyncio
async def test_derive_asset_regenerate_comfyui_error(db_session: AsyncSession):
    """Should return error when ComfyUI fails."""
    variant, candidate, base_asset = await _create_variant_with_base_asset(db_session)

    # Update base asset to smaller dimensions
    base_asset.spec = {
        "width": 800,
        "height": 800,
        "format": "png",
        "has_text": False,
    }
    base_asset.generation_params = {
        "prompt": "test prompt",
        "style": "minimalist",
    }
    await db_session.commit()

    # Create platform rule requiring larger dimensions
    rule = PlatformContentRule(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        asset_type=AssetType.MAIN_IMAGE,
        image_spec={
            "width": 1000,
            "height": 1000,
            "format": "png",
        },
        allow_text_on_image=False,
        max_images=10,
        required_languages=["en"],
    )
    db_session.add(rule)
    await db_session.commit()

    # Mock MinIO
    mock_minio = AsyncMock()
    mock_minio.download_image = AsyncMock(
        return_value=create_test_image(800, 800, "PNG")
    )

    # Mock ComfyUI client to raise error
    from app.services.image_generation.comfyui_client import ComfyUIClient
    mock_comfyui = AsyncMock(spec=ComfyUIClient)
    mock_comfyui.generate_product_image = AsyncMock(
        side_effect=Exception("ComfyUI connection failed")
    )

    # Patch get_comfyui_client
    from unittest.mock import patch
    with patch(
        "app.services.image_regeneration_service.get_comfyui_client",
        return_value=mock_comfyui,
    ):
        service = AssetDerivationService(minio_client=mock_minio)

        # Derive asset
        result = await service.derive_asset(
            base_asset=base_asset,
            platform=TargetPlatform.AMAZON,
            db=db_session,
        )

    assert result["status"] == "error"
    assert "ComfyUI connection failed" in result["reason"]

