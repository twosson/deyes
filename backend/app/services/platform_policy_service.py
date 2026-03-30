"""Platform policy service for managing platform-specific configurations.

Provides centralized access to platform policies, category mappings,
and configuration with fallback to hardcoded defaults.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import TargetPlatform
from app.core.logging import get_logger
from app.db.models import PlatformCategoryMapping, PlatformPolicy, RegionRiskRule, RegionTaxRule


class PlatformPolicyService:
    """Service for accessing platform policies and configurations.

    Provides read-through caching with fallback to hardcoded defaults
    for backward compatibility.
    """

    # Default commission rates (fallback)
    DEFAULT_COMMISSION_RATES = {
        TargetPlatform.TEMU: 0.08,
        TargetPlatform.AMAZON: 0.15,
        TargetPlatform.OZON: 0.10,
        TargetPlatform.SHOPEE: 0.06,
        TargetPlatform.TIKTOK_SHOP: 0.05,
    }

    # Default pricing config (fallback)
    DEFAULT_PRICING_CONFIG = {
        "profitable_threshold": 0.35,
        "marginal_threshold_ratio": 0.60,
        "shipping_rate_default": 0.15,
        "category_threshold_overrides": {
            "electronics": 0.25,
            "jewelry": 0.50,
        },
    }

    def __init__(self):
        self.logger = get_logger(__name__)

    async def get_active_policy(
        self,
        db: AsyncSession,
        platform: TargetPlatform,
        policy_type: str,
        region: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> Optional[PlatformPolicy]:
        """Get active policy for platform/region.

        Args:
            db: Database session
            platform: Target platform
            policy_type: Policy type (commission/pricing/content/listing)
            region: Region code (optional)
            as_of: Effective date (defaults to now)

        Returns:
            Active PlatformPolicy or None if not found
        """
        if as_of is None:
            as_of = datetime.now(timezone.utc)

        # Build query
        conditions = [
            PlatformPolicy.platform == platform,
            PlatformPolicy.policy_type == policy_type,
            PlatformPolicy.is_active == True,
        ]

        # Add region filter (NULL matches all regions)
        if region:
            conditions.append(
                (PlatformPolicy.region == region) | (PlatformPolicy.region == None)
            )
        else:
            conditions.append(PlatformPolicy.region == None)

        # Add time-based filters
        conditions.append(
            (PlatformPolicy.effective_from == None) | (PlatformPolicy.effective_from <= as_of)
        )
        conditions.append(
            (PlatformPolicy.effective_to == None) | (PlatformPolicy.effective_to > as_of)
        )

        stmt = (
            select(PlatformPolicy)
            .where(and_(*conditions))
            .order_by(
                PlatformPolicy.region.isnot(None).desc(),  # Prefer region-specific (non-NULL first)
                PlatformPolicy.version.desc(),  # Prefer latest version
            )
            .limit(1)
        )

        result = await db.execute(stmt)
        policy = result.scalar_one_or_none()

        if policy:
            self.logger.info(
                "platform_policy_found",
                platform=platform.value,
                region=region,
                policy_type=policy_type,
                version=policy.version,
            )
        else:
            self.logger.info(
                "platform_policy_not_found",
                platform=platform.value,
                region=region,
                policy_type=policy_type,
            )

        return policy

    async def get_commission_config(
        self,
        db: AsyncSession,
        platform: TargetPlatform,
        region: Optional[str] = None,
    ) -> dict:
        """Get commission configuration with fallback to defaults.

        Args:
            db: Database session
            platform: Target platform
            region: Region code (optional)

        Returns:
            Commission config dict with:
                - commission_rate: float
                - payment_fee_rate: float
                - return_rate_assumption: float
        """
        policy = await self.get_active_policy(
            db=db,
            platform=platform,
            policy_type="commission",
            region=region,
        )

        if policy:
            return policy.policy_data

        # Fallback to defaults
        default_rate = self.DEFAULT_COMMISSION_RATES.get(platform, 0.10)
        return {
            "commission_rate": default_rate,
            "payment_fee_rate": 0.02,
            "return_rate_assumption": 0.05,
        }

    async def get_pricing_config(
        self,
        db: AsyncSession,
        platform: TargetPlatform,
        region: Optional[str] = None,
    ) -> dict:
        """Get pricing configuration with fallback to defaults.

        Args:
            db: Database session
            platform: Target platform
            region: Region code (optional)

        Returns:
            Pricing config dict with:
                - profitable_threshold: float
                - marginal_threshold_ratio: float
                - shipping_rate_default: float
                - category_threshold_overrides: dict
        """
        policy = await self.get_active_policy(
            db=db,
            platform=platform,
            policy_type="pricing",
            region=region,
        )

        if policy:
            return policy.policy_data

        # Fallback to defaults
        return self.DEFAULT_PRICING_CONFIG.copy()

    async def get_category_mapping(
        self,
        db: AsyncSession,
        platform: TargetPlatform,
        internal_category: str,
        region: Optional[str] = None,
    ) -> Optional[PlatformCategoryMapping]:
        """Get category mapping with fallback to hardcoded.

        Args:
            db: Database session
            platform: Target platform
            internal_category: Internal category name
            region: Region code (optional)

        Returns:
            PlatformCategoryMapping or None if not found
        """
        # Build query
        conditions = [
            PlatformCategoryMapping.platform == platform,
            PlatformCategoryMapping.internal_category == internal_category,
            PlatformCategoryMapping.is_active == True,
        ]

        # Add region filter (NULL matches all regions)
        if region:
            conditions.append(
                (PlatformCategoryMapping.region == region) | (PlatformCategoryMapping.region == None)
            )
        else:
            conditions.append(PlatformCategoryMapping.region == None)

        stmt = (
            select(PlatformCategoryMapping)
            .where(and_(*conditions))
            .order_by(
                PlatformCategoryMapping.region.isnot(None).desc(),  # Prefer region-specific (non-NULL first)
                PlatformCategoryMapping.mapping_version.desc(),  # Prefer latest version
            )
            .limit(1)
        )

        result = await db.execute(stmt)
        mapping = result.scalar_one_or_none()

        if mapping:
            self.logger.info(
                "category_mapping_found",
                platform=platform.value,
                region=region,
                internal_category=internal_category,
                platform_category_id=mapping.platform_category_id,
            )
        else:
            self.logger.info(
                "category_mapping_not_found",
                platform=platform.value,
                region=region,
                internal_category=internal_category,
            )

        return mapping

    async def get_tax_rules(
        self,
        db: AsyncSession,
        platform: TargetPlatform,
        region: str,
        tax_type: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> list[RegionTaxRule]:
        """Get active tax rules for platform/region.

        Args:
            db: Database session
            platform: Target platform
            region: Region code
            tax_type: Tax type filter (vat/sales_tax/import_tax)
            as_of: Effective date (defaults to now)

        Returns:
            List of active RegionTaxRule instances
        """
        if as_of is None:
            as_of = datetime.now(timezone.utc)

        # Build query
        conditions = [
            RegionTaxRule.region == region,
            RegionTaxRule.is_active == True,
        ]

        # Platform filter (NULL matches all platforms)
        conditions.append(
            (RegionTaxRule.platform == platform) | (RegionTaxRule.platform == None)
        )

        # Tax type filter
        if tax_type:
            conditions.append(RegionTaxRule.tax_type == tax_type)

        # Time-based filters
        conditions.append(
            (RegionTaxRule.effective_from == None) | (RegionTaxRule.effective_from <= as_of)
        )
        conditions.append(
            (RegionTaxRule.effective_to == None) | (RegionTaxRule.effective_to > as_of)
        )

        stmt = (
            select(RegionTaxRule)
            .where(and_(*conditions))
            .order_by(
                RegionTaxRule.platform.isnot(None).desc(),  # Prefer platform-specific
                RegionTaxRule.version.desc(),  # Prefer latest version
            )
        )

        result = await db.execute(stmt)
        rules = list(result.scalars().all())

        self.logger.info(
            "tax_rules_found",
            platform=platform.value,
            region=region,
            tax_type=tax_type,
            rule_count=len(rules),
        )

        return rules

    async def get_risk_rules(
        self,
        db: AsyncSession,
        platform: TargetPlatform,
        region: str,
        rule_code: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> list[RegionRiskRule]:
        """Get active risk rules for platform/region.

        Args:
            db: Database session
            platform: Target platform
            region: Region code
            rule_code: Rule code filter (optional)
            as_of: Effective date (defaults to now)

        Returns:
            List of active RegionRiskRule instances
        """
        if as_of is None:
            as_of = datetime.now(timezone.utc)

        # Build query
        conditions = [
            RegionRiskRule.region == region,
            RegionRiskRule.is_active == True,
        ]

        # Platform filter (NULL matches all platforms)
        conditions.append(
            (RegionRiskRule.platform == platform) | (RegionRiskRule.platform == None)
        )

        # Rule code filter
        if rule_code:
            conditions.append(RegionRiskRule.rule_code == rule_code)

        # Time-based filters
        conditions.append(
            (RegionRiskRule.effective_from == None) | (RegionRiskRule.effective_from <= as_of)
        )
        conditions.append(
            (RegionRiskRule.effective_to == None) | (RegionRiskRule.effective_to > as_of)
        )

        stmt = (
            select(RegionRiskRule)
            .where(and_(*conditions))
            .order_by(
                RegionRiskRule.platform.isnot(None).desc(),  # Prefer platform-specific
                RegionRiskRule.version.desc(),  # Prefer latest version
            )
        )

        result = await db.execute(stmt)
        rules = list(result.scalars().all())

        self.logger.info(
            "risk_rules_found",
            platform=platform.value,
            region=region,
            rule_code=rule_code,
            rule_count=len(rules),
        )

        return rules


__all__ = ["PlatformPolicyService"]
