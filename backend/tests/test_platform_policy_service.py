"""Tests for platform policy service."""
from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TargetPlatform
from app.db.models import PlatformCategoryMapping, PlatformPolicy
from app.services.platform_policy_service import PlatformPolicyService


@pytest.mark.asyncio
async def test_get_active_policy_returns_matching_policy(db_session: AsyncSession):
    """PlatformPolicyService should return active policy matching platform/region."""
    service = PlatformPolicyService()

    policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="us",
        policy_type="commission",
        version=1,
        is_active=True,
        policy_data={"commission_rate": 0.08, "payment_fee_rate": 0.02},
    )
    db_session.add(policy)
    await db_session.commit()

    result = await service.get_active_policy(
        db=db_session,
        platform=TargetPlatform.TEMU,
        policy_type="commission",
        region="us",
    )

    assert result is not None
    assert result.policy_type == "commission"
    assert result.policy_data["commission_rate"] == 0.08


@pytest.mark.asyncio
async def test_get_active_policy_returns_none_when_not_found(db_session: AsyncSession):
    """PlatformPolicyService should return None when no matching policy exists."""
    service = PlatformPolicyService()

    result = await service.get_active_policy(
        db=db_session,
        platform=TargetPlatform.TEMU,
        policy_type="commission",
        region="us",
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_active_policy_prefers_region_specific(db_session: AsyncSession):
    """PlatformPolicyService should prefer region-specific over platform-wide policy."""
    service = PlatformPolicyService()

    # Platform-wide (no region)
    platform_policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region=None,
        policy_type="commission",
        version=1,
        is_active=True,
        policy_data={"commission_rate": 0.20},
    )
    db_session.add(platform_policy)

    # Region-specific
    region_policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.AMAZON,
        region="us",
        policy_type="commission",
        version=1,
        is_active=True,
        policy_data={"commission_rate": 0.15},
    )
    db_session.add(region_policy)
    await db_session.commit()

    result = await service.get_active_policy(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        policy_type="commission",
        region="us",
    )

    assert result is not None
    assert result.region == "us"
    assert result.policy_data["commission_rate"] == 0.15


@pytest.mark.asyncio
async def test_get_commission_config_falls_back_to_defaults(db_session: AsyncSession):
    """get_commission_config should fallback to defaults when no policy in DB."""
    service = PlatformPolicyService()

    config = await service.get_commission_config(
        db=db_session,
        platform=TargetPlatform.AMAZON,
        region="us",
    )

    assert "commission_rate" in config
    assert "payment_fee_rate" in config
    assert "return_rate_assumption" in config
    assert config["commission_rate"] == 0.15  # Default for Amazon


@pytest.mark.asyncio
async def test_get_commission_config_returns_db_policy(db_session: AsyncSession):
    """get_commission_config should return DB policy when available."""
    service = PlatformPolicyService()

    policy = PlatformPolicy(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        policy_type="commission",
        version=2,
        is_active=True,
        policy_data={"commission_rate": 0.06, "payment_fee_rate": 0.015},
    )
    db_session.add(policy)
    await db_session.commit()

    config = await service.get_commission_config(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="uk",
    )

    assert config["commission_rate"] == 0.06
    assert config["payment_fee_rate"] == 0.015


@pytest.mark.asyncio
async def test_get_pricing_config_falls_back_to_defaults(db_session: AsyncSession):
    """get_pricing_config should fallback to defaults when no policy in DB."""
    service = PlatformPolicyService()

    config = await service.get_pricing_config(
        db=db_session,
        platform=TargetPlatform.TEMU,
        region="us",
    )

    assert "profitable_threshold" in config
    assert config["profitable_threshold"] == 0.35
    assert "category_threshold_overrides" in config


@pytest.mark.asyncio
async def test_get_category_mapping_returns_mapping(db_session: AsyncSession):
    """get_category_mapping should return mapping when found."""
    service = PlatformPolicyService()

    mapping = PlatformCategoryMapping(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="us",
        internal_category="electronics",
        platform_category_id="5001",
        platform_category_name="Consumer Electronics",
        mapping_version=1,
        is_active=True,
    )
    db_session.add(mapping)
    await db_session.commit()

    result = await service.get_category_mapping(
        db=db_session,
        platform=TargetPlatform.TEMU,
        internal_category="electronics",
        region="us",
    )

    assert result is not None
    assert result.platform_category_id == "5001"
    assert result.internal_category == "electronics"


@pytest.mark.asyncio
async def test_get_category_mapping_returns_none_when_not_found(db_session: AsyncSession):
    """get_category_mapping should return None when no mapping exists."""
    service = PlatformPolicyService()

    result = await service.get_category_mapping(
        db=db_session,
        platform=TargetPlatform.TEMU,
        internal_category="nonexistent_category",
        region="us",
    )

    assert result is None


@pytest.mark.asyncio
async def test_get_category_mapping_prefers_region_specific(db_session: AsyncSession):
    """get_category_mapping should prefer region-specific over platform-wide mapping."""
    service = PlatformPolicyService()

    # Platform-wide
    platform_mapping = PlatformCategoryMapping(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region=None,
        internal_category="beauty tools",
        platform_category_id="3000",
        platform_category_name="Beauty",
        mapping_version=1,
        is_active=True,
    )
    db_session.add(platform_mapping)

    # Region-specific
    region_mapping = PlatformCategoryMapping(
        id=uuid4(),
        platform=TargetPlatform.TEMU,
        region="uk",
        internal_category="beauty tools",
        platform_category_id="3001",
        platform_category_name="Beauty UK",
        mapping_version=1,
        is_active=True,
    )
    db_session.add(region_mapping)
    await db_session.commit()

    result = await service.get_category_mapping(
        db=db_session,
        platform=TargetPlatform.TEMU,
        internal_category="beauty tools",
        region="uk",
    )

    assert result is not None
    assert result.region == "uk"
    assert result.platform_category_id == "3001"
