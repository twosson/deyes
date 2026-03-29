"""Tests for ImageRegenerationService."""
from __future__ import annotations

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AssetType, ContentUsageScope, SourcePlatform, StrategyRunStatus, TriggerType
from app.db.models import CandidateProduct, ContentAsset, StrategyRun
from app.services.image_regeneration_service import ImageRegenerationService


@pytest.mark.asyncio
async def test_regenerate_with_higher_resolution_success(db_session: AsyncSession):
    """Should regenerate image with higher resolution using ComfyUI."""
    # Create test data
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

    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.png",
        usage_scope=ContentUsageScope.BASE,
        spec={
            "width": 800,
            "height": 800,
            "format": "png",
            "has_text": False,
        },
        generation_params={
            "prompt": "minimalist product photo of a red mug",
            "style": "minimalist",
        },
    )
    db_session.add(base_asset)
    await db_session.commit()

    # Mock ComfyUI client
    mock_comfyui = AsyncMock()
    mock_comfyui.generate_product_image = AsyncMock(return_value=b"fake_image_bytes")

    service = ImageRegenerationService(comfyui_client=mock_comfyui)

    # Regenerate with higher resolution
    result = await service.regenerate_with_higher_resolution(
        base_asset=base_asset,
        target_width=1000,
        target_height=1000,
        db=db_session,
    )

    assert result["status"] == "success"
    assert result["image_bytes"] == b"fake_image_bytes"

    # Verify ComfyUI was called with correct parameters
    mock_comfyui.generate_product_image.assert_called_once_with(
        prompt="minimalist product photo of a red mug",
        style="minimalist",
        width=1000,
        height=1000,
    )


@pytest.mark.asyncio
async def test_regenerate_with_no_prompt_uses_candidate_title(db_session: AsyncSession):
    """Should use candidate title when no prompt in generation_params."""
    # Create test data
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
        title="Red Ceramic Mug",
    )
    db_session.add(candidate)
    await db_session.flush()

    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.png",
        usage_scope=ContentUsageScope.BASE,
        spec={
            "width": 800,
            "height": 800,
            "format": "png",
            "has_text": False,
        },
        generation_params={},  # No prompt
    )
    db_session.add(base_asset)
    await db_session.commit()

    # Mock ComfyUI client
    mock_comfyui = AsyncMock()
    mock_comfyui.generate_product_image = AsyncMock(return_value=b"fake_image_bytes")

    service = ImageRegenerationService(comfyui_client=mock_comfyui)

    # Regenerate
    result = await service.regenerate_with_higher_resolution(
        base_asset=base_asset,
        target_width=1000,
        target_height=1000,
        db=db_session,
    )

    assert result["status"] == "success"

    # Verify ComfyUI was called with candidate title as prompt
    mock_comfyui.generate_product_image.assert_called_once_with(
        prompt="Red Ceramic Mug",
        style="minimalist",
        width=1000,
        height=1000,
    )


@pytest.mark.asyncio
async def test_regenerate_with_no_prompt_and_no_candidate(db_session: AsyncSession):
    """Should return error when no prompt and candidate not found."""
    # Create test data without candidate
    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=uuid4(),  # Non-existent candidate
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.png",
        usage_scope=ContentUsageScope.BASE,
        spec={
            "width": 800,
            "height": 800,
            "format": "png",
            "has_text": False,
        },
        generation_params={},  # No prompt
    )

    # Mock ComfyUI client
    mock_comfyui = AsyncMock()

    service = ImageRegenerationService(comfyui_client=mock_comfyui)

    # Regenerate
    result = await service.regenerate_with_higher_resolution(
        base_asset=base_asset,
        target_width=1000,
        target_height=1000,
        db=db_session,
    )

    assert result["status"] == "error"
    assert result["reason"] == "no_prompt_or_candidate"

    # Verify ComfyUI was not called
    mock_comfyui.generate_product_image.assert_not_called()


@pytest.mark.asyncio
async def test_regenerate_with_comfyui_error(db_session: AsyncSession):
    """Should return error when ComfyUI fails."""
    # Create test data
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

    base_asset = ContentAsset(
        id=uuid4(),
        candidate_product_id=candidate.id,
        asset_type=AssetType.MAIN_IMAGE,
        file_url="https://example.com/base.png",
        usage_scope=ContentUsageScope.BASE,
        spec={
            "width": 800,
            "height": 800,
            "format": "png",
            "has_text": False,
        },
        generation_params={
            "prompt": "test prompt",
            "style": "minimalist",
        },
    )
    db_session.add(base_asset)
    await db_session.commit()

    # Mock ComfyUI client to raise error
    mock_comfyui = AsyncMock()
    mock_comfyui.generate_product_image = AsyncMock(
        side_effect=Exception("ComfyUI connection failed")
    )

    service = ImageRegenerationService(comfyui_client=mock_comfyui)

    # Regenerate
    result = await service.regenerate_with_higher_resolution(
        base_asset=base_asset,
        target_width=1000,
        target_height=1000,
        db=db_session,
    )

    assert result["status"] == "error"
    assert "ComfyUI connection failed" in result["reason"]
