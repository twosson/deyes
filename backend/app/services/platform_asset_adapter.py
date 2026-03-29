"""Platform asset adapter for validating and selecting content assets."""
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import AssetType, ContentUsageScope, TargetPlatform
from app.core.logging import get_logger
from app.db.models import ContentAsset, PlatformContentRule

logger = get_logger(__name__)


class PlatformAssetAdapter:
    """Adapter for platform-specific asset rules and selection."""

    async def get_platform_rule(
        self,
        *,
        platform: TargetPlatform,
        asset_type: AssetType,
        db: AsyncSession,
    ) -> Optional[PlatformContentRule]:
        """Get platform content rule.

        Args:
            platform: Target platform
            asset_type: Asset type
            db: Database session

        Returns:
            PlatformContentRule if found, None otherwise
        """
        stmt = select(PlatformContentRule).where(
            PlatformContentRule.platform == platform,
            PlatformContentRule.asset_type == asset_type,
        )
        result = await db.execute(stmt)
        return result.scalar_one_or_none()

    async def validate_asset_compliance(
        self,
        *,
        asset: ContentAsset,
        platform: TargetPlatform,
        db: AsyncSession,
    ) -> dict:
        """Validate asset against platform rules.

        Returns:
            Dict with validation result, violations, and suggestions
        """
        rule = await self.get_platform_rule(
            platform=platform,
            asset_type=asset.asset_type,
            db=db,
        )

        if not rule:
            return {
                "valid": False,
                "violations": ["no_platform_rule_found"],
                "suggestions": ["define_platform_rule"],
            }

        violations = []
        suggestions = []

        spec = asset.spec or {}

        # Validate text on image
        has_text = spec.get("has_text", False)
        if has_text and not rule.allow_text_on_image:
            violations.append("text_not_allowed")
            suggestions.append("regenerate_without_text")

        # Validate dimensions
        asset_width = spec.get("width")
        asset_height = spec.get("height")
        required_width = rule.image_spec.get("width")
        required_height = rule.image_spec.get("height")

        if asset_width and asset_height and required_width and required_height:
            if asset_width != required_width or asset_height != required_height:
                violations.append("dimension_mismatch")
                if asset_width >= required_width and asset_height >= required_height:
                    suggestions.append("resize")
                else:
                    suggestions.append("regenerate_higher_resolution")

        # Validate format
        asset_format = spec.get("format") or asset.format
        required_format = rule.image_spec.get("format")
        if asset_format and required_format and asset_format.lower() != required_format.lower():
            violations.append("format_mismatch")
            suggestions.append("convert_format")

        # Validate language requirements
        if rule.required_languages:
            asset_languages = asset.language_tags or []
            missing_languages = [
                lang for lang in rule.required_languages if lang not in asset_languages
            ]
            if missing_languages:
                violations.append("missing_required_languages")
                suggestions.append("create_localized_variant")

        # Validate compliance tags if present
        if asset.compliance_tags:
            platform_compliance_tag = f"{platform.value}_compliant"
            if platform_compliance_tag not in asset.compliance_tags:
                violations.append("missing_platform_compliance_tag")
                suggestions.append("review_compliance")

        return {
            "valid": len(violations) == 0,
            "violations": violations,
            "suggestions": list(dict.fromkeys(suggestions)),
            "rule": {
                "platform": rule.platform.value,
                "asset_type": rule.asset_type.value,
                "image_spec": rule.image_spec,
                "allow_text_on_image": rule.allow_text_on_image,
            },
        }

    async def suggest_asset_derivation(
        self,
        *,
        base_asset: ContentAsset,
        platform: TargetPlatform,
        db: AsyncSession,
        language: Optional[str] = None,
    ) -> dict:
        """Suggest how to derive a platform asset from a base asset."""
        validation = await self.validate_asset_compliance(
            asset=base_asset,
            platform=platform,
            db=db,
        )

        actions = []
        target_spec = None

        if validation.get("rule"):
            target_spec = validation["rule"]["image_spec"]

        if validation["valid"]:
            actions.append("reuse")
        else:
            suggestions = validation["suggestions"]
            if "resize" in suggestions:
                actions.append("resize")
            if "convert_format" in suggestions:
                actions.append("convert_format")
            if "create_localized_variant" in suggestions and language:
                actions.append("overlay_localized_text")
            if "regenerate_without_text" in suggestions or "regenerate_higher_resolution" in suggestions:
                actions.append("regenerate")

        if not actions:
            actions.append("manual_review")

        return {
            "base_asset_id": str(base_asset.id),
            "platform": platform.value,
            "language": language,
            "target_spec": target_spec,
            "actions": actions,
            "usage_scope": ContentUsageScope.PLATFORM_DERIVED.value,
            "parent_asset_id": str(base_asset.id),
        }

    async def select_best_asset(
        self,
        *,
        variant_id: UUID,
        platform: TargetPlatform,
        asset_type: AssetType,
        db: AsyncSession,
        language: Optional[str] = None,
    ) -> Optional[ContentAsset]:
        """Select the best asset for a platform.

        Prioritizes:
        1. Localized asset matching platform and language (LOCALIZED)
        2. Platform-derived asset matching platform (PLATFORM_DERIVED)
        3. Localized asset matching language only (LOCALIZED)
        4. Base asset (BASE)
        """
        stmt = select(ContentAsset).where(
            ContentAsset.product_variant_id == variant_id,
            ContentAsset.asset_type == asset_type,
            ContentAsset.archived == False,
        )
        result = await db.execute(stmt)
        assets = list(result.scalars().all())

        if not assets:
            return None

        # Priority 1: LOCALIZED asset with exact platform + language match
        if language:
            for asset in assets:
                if (
                    asset.usage_scope == ContentUsageScope.LOCALIZED
                    and asset.platform_tags
                    and platform.value in asset.platform_tags
                    and asset.language_tags
                    and language in asset.language_tags
                ):
                    logger.info(
                        "selected_localized_asset_exact_match",
                        asset_id=str(asset.id),
                        platform=platform.value,
                        language=language,
                    )
                    return asset

        # Priority 2: PLATFORM_DERIVED asset with platform match
        for asset in assets:
            if (
                asset.usage_scope == ContentUsageScope.PLATFORM_DERIVED
                and asset.platform_tags
                and platform.value in asset.platform_tags
            ):
                if language:
                    if asset.language_tags and language in asset.language_tags:
                        logger.info(
                            "selected_platform_derived_asset_with_language",
                            asset_id=str(asset.id),
                            platform=platform.value,
                            language=language,
                        )
                        return asset
                else:
                    logger.info(
                        "selected_platform_derived_asset",
                        asset_id=str(asset.id),
                        platform=platform.value,
                    )
                    return asset

        # Priority 3: LOCALIZED asset with language match only (no platform match)
        if language:
            for asset in assets:
                if (
                    asset.usage_scope == ContentUsageScope.LOCALIZED
                    and asset.language_tags
                    and language in asset.language_tags
                ):
                    logger.info(
                        "selected_localized_asset_language_only",
                        asset_id=str(asset.id),
                        language=language,
                    )
                    return asset

        # Priority 4: BASE asset
        for asset in assets:
            if asset.usage_scope == ContentUsageScope.BASE:
                logger.info(
                    "selected_base_asset",
                    asset_id=str(asset.id),
                )
                return asset

        # Fallback: first asset
        logger.warning(
            "selected_fallback_asset",
            asset_id=str(assets[0].id),
        )
        return assets[0]
