"""Asset derivation service for platform-specific image transformations.

Provides functionality for:
- Resizing images to platform-specific dimensions
- Converting image formats (PNG ↔ JPG)
- Overlaying localized text on images
- Deriving platform-specific assets from base assets
- Executing PlatformAssetAdapter suggestions
"""
from __future__ import annotations

import io
from typing import TYPE_CHECKING, Optional
from uuid import UUID, uuid4

from PIL import Image

from app.core.enums import AssetType, ContentUsageScope, TargetPlatform
from app.core.logging import get_logger
from app.services.platform_asset_adapter import PlatformAssetAdapter
from app.services.storage.minio_client import MinIOClient, get_minio_client

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

    from app.db.models import ContentAsset

logger = get_logger(__name__)


class AssetDerivationService:
    """Service for deriving platform-specific assets from base assets."""

    def __init__(self, *, minio_client: MinIOClient | None = None):
        self.minio_client = minio_client or get_minio_client()
        self.adapter = PlatformAssetAdapter()

    async def resize(
        self,
        image_bytes: bytes,
        target_width: int,
        target_height: int,
    ) -> tuple[bytes, dict]:
        """Resize image to target dimensions.

        Strategy:
        - Maintain aspect ratio
        - Center crop to target dimensions
        - If source is smaller than target, return regenerate_needed status

        Args:
            image_bytes: Source image bytes
            target_width: Target width in pixels
            target_height: Target height in pixels

        Returns:
            Tuple of (resized_image_bytes, metadata)
            metadata contains: {"status": "success"|"regenerate_needed", "actual_size": ...}
        """
        try:
            # Load image
            image = Image.open(io.BytesIO(image_bytes))
            source_width, source_height = image.size

            logger.info(
                "resize_started",
                source_size=f"{source_width}x{source_height}",
                target_size=f"{target_width}x{target_height}",
            )

            # Check if source is smaller than target
            if source_width < target_width or source_height < target_height:
                logger.warning(
                    "source_smaller_than_target",
                    source_size=f"{source_width}x{source_height}",
                    target_size=f"{target_width}x{target_height}",
                )
                return image_bytes, {
                    "status": "regenerate_needed",
                    "reason": "source_too_small",
                    "source_size": f"{source_width}x{source_height}",
                    "target_size": f"{target_width}x{target_height}",
                }

            # Calculate aspect ratios
            source_ratio = source_width / source_height
            target_ratio = target_width / target_height

            # Resize to fit target dimensions while maintaining aspect ratio
            if source_ratio > target_ratio:
                # Source is wider, fit to height
                new_height = target_height
                new_width = int(source_width * (target_height / source_height))
            else:
                # Source is taller, fit to width
                new_width = target_width
                new_height = int(source_height * (target_width / source_width))

            # Resize image
            image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # Center crop to exact target dimensions
            left = (new_width - target_width) // 2
            top = (new_height - target_height) // 2
            right = left + target_width
            bottom = top + target_height

            image = image.crop((left, top, right, bottom))

            # Convert to bytes
            output = io.BytesIO()
            image.save(output, format=image.format or "PNG")
            resized_bytes = output.getvalue()

            logger.info(
                "resize_completed",
                source_size=f"{source_width}x{source_height}",
                target_size=f"{target_width}x{target_height}",
                output_size=len(resized_bytes),
            )

            return resized_bytes, {
                "status": "success",
                "source_size": f"{source_width}x{source_height}",
                "target_size": f"{target_width}x{target_height}",
            }

        except Exception as e:
            logger.error("resize_failed", error=str(e))
            raise

    async def convert_format(
        self,
        image_bytes: bytes,
        target_format: str,
    ) -> bytes:
        """Convert image format.

        Args:
            image_bytes: Source image bytes
            target_format: Target format ("png", "jpg", "jpeg")

        Returns:
            Converted image bytes
        """
        try:
            # Normalize format
            target_format = target_format.lower()
            if target_format == "jpg":
                target_format = "jpeg"

            logger.info("format_conversion_started", target_format=target_format)

            # Load image
            image = Image.open(io.BytesIO(image_bytes))

            # Convert RGBA to RGB if converting to JPEG
            if target_format == "jpeg" and image.mode in ("RGBA", "LA", "P"):
                # Create white background
                background = Image.new("RGB", image.size, (255, 255, 255))
                if image.mode == "P":
                    image = image.convert("RGBA")
                background.paste(image, mask=image.split()[-1] if image.mode == "RGBA" else None)
                image = background

            # Convert to bytes
            output = io.BytesIO()
            image.save(output, format=target_format.upper())
            converted_bytes = output.getvalue()

            logger.info(
                "format_conversion_completed",
                target_format=target_format,
                output_size=len(converted_bytes),
            )

            return converted_bytes

        except Exception as e:
            logger.error("format_conversion_failed", error=str(e), target_format=target_format)
            raise

    async def derive_asset(
        self,
        *,
        base_asset: ContentAsset,
        platform: TargetPlatform,
        db: AsyncSession,
        language: Optional[str] = None,
    ) -> dict:
        """Derive a platform-specific asset from a base asset.

        Args:
            base_asset: Source base asset
            platform: Target platform
            db: Database session
            language: Optional language code

        Returns:
            Dict with derivation result:
            {
                "status": "success"|"deferred"|"error",
                "asset": ContentAsset (if success),
                "reason": str (if deferred/error),
            }
        """
        try:
            logger.info(
                "asset_derivation_started",
                base_asset_id=str(base_asset.id),
                platform=platform.value,
                language=language,
            )

            # Get derivation suggestion
            suggestion = await self.adapter.suggest_asset_derivation(
                base_asset=base_asset,
                platform=platform,
                db=db,
                language=language,
            )

            actions = suggestion["actions"]
            target_spec = suggestion.get("target_spec", {})

            # Handle reuse action
            if "reuse" in actions:
                # Create derived record pointing to same file
                derived_asset = await self._create_derived_record(
                    base_asset=base_asset,
                    platform=platform,
                    language=language,
                    file_url=base_asset.file_url,
                    spec=base_asset.spec or {},
                    db=db,
                )

                logger.info(
                    "asset_reused",
                    base_asset_id=str(base_asset.id),
                    derived_asset_id=str(derived_asset.id),
                )

                return {
                    "status": "success",
                    "asset": derived_asset,
                    "actions_performed": ["reuse"],
                }

            # Handle deferred actions
            if "overlay_localized_text" in actions:
                if not language:
                    logger.warning(
                        "asset_derivation_deferred",
                        reason="language_required_for_text_overlay",
                        base_asset_id=str(base_asset.id),
                    )
                    return {
                        "status": "deferred",
                        "reason": "language_required_for_text_overlay",
                        "actions_required": actions,
                    }

                # Execute text overlay
                from app.services.text_overlay_service import TextOverlayService

                text_overlay_service = TextOverlayService(minio_client=self.minio_client)
                result = await text_overlay_service.overlay_localized_text(
                    base_asset=base_asset,
                    platform=platform,
                    language=language,
                    db=db,
                )

                if result["status"] == "success":
                    logger.info(
                        "text_overlay_success",
                        base_asset_id=str(base_asset.id),
                        localized_asset_id=str(result["asset"].id),
                    )
                    return {
                        "status": "success",
                        "asset": result["asset"],
                        "actions_performed": ["overlay_localized_text"],
                    }
                elif result["status"] == "no_text_found":
                    # No localization text found, continue with other actions
                    logger.warning(
                        "no_localization_text_found",
                        base_asset_id=str(base_asset.id),
                        variant_id=str(base_asset.product_variant_id),
                        language=language,
                    )
                    # Remove overlay action and continue
                    actions = [a for a in actions if a != "overlay_localized_text"]
                    if not actions:
                        # No other actions, return deferred
                        return {
                            "status": "deferred",
                            "reason": "no_localization_text_and_no_other_actions",
                        }
                else:
                    # Error occurred
                    logger.error(
                        "text_overlay_failed",
                        base_asset_id=str(base_asset.id),
                        reason=result.get("reason"),
                    )
                    return result

            if "regenerate" in actions:
                from app.services.image_regeneration_service import ImageRegenerationService

                regeneration_service = ImageRegenerationService()

                # 获取目标规格
                target_width = target_spec.get("width")
                target_height = target_spec.get("height")

                if not target_width or not target_height:
                    logger.error(
                        "regeneration_failed",
                        reason="target_dimensions_not_specified",
                        base_asset_id=str(base_asset.id),
                    )
                    return {
                        "status": "error",
                        "reason": "target_dimensions_not_specified",
                    }

                # 重新生成更高分辨率图片
                result = await regeneration_service.regenerate_with_higher_resolution(
                    base_asset=base_asset,
                    target_width=target_width,
                    target_height=target_height,
                    db=db,
                )

                if result["status"] == "success":
                    # 上传到 MinIO
                    regenerated_url = await self.minio_client.upload_image(
                        image_data=result["image_bytes"],
                        product_id=base_asset.candidate_product_id,
                        asset_type=f"{base_asset.asset_type.value}_regenerated",
                        style_tags=[platform.value],
                        filename=f"{platform.value}_regenerated_{uuid4().hex[:8]}.png",
                        content_type="image/png",
                    )

                    # 创建派生素材记录
                    derived_spec = {
                        "width": target_width,
                        "height": target_height,
                        "format": target_spec.get("format", "png"),
                        "has_text": False,
                        "regenerated": True,
                    }

                    derived_asset = await self._create_derived_record(
                        base_asset=base_asset,
                        platform=platform,
                        language=language,
                        file_url=regenerated_url,
                        spec=derived_spec,
                        db=db,
                    )

                    logger.info(
                        "asset_regenerated",
                        base_asset_id=str(base_asset.id),
                        derived_asset_id=str(derived_asset.id),
                    )

                    return {
                        "status": "success",
                        "asset": derived_asset,
                        "actions_performed": ["regenerate"],
                    }
                else:
                    return result

            # Handle resize and/or convert_format
            if "resize" in actions or "convert_format" in actions:
                # Download source image
                image_bytes = await self.minio_client.download_image(base_asset.file_url)

                actions_performed = []

                # Resize if needed
                if "resize" in actions:
                    target_width = target_spec.get("width")
                    target_height = target_spec.get("height")

                    if not target_width or not target_height:
                        raise ValueError("Target dimensions not specified in platform rule")

                    image_bytes, resize_metadata = await self.resize(
                        image_bytes, target_width, target_height
                    )

                    if resize_metadata["status"] == "regenerate_needed":
                        logger.warning(
                            "asset_derivation_deferred",
                            reason="source_too_small_for_resize",
                            base_asset_id=str(base_asset.id),
                        )
                        return {
                            "status": "deferred",
                            "reason": "source_too_small_for_resize",
                            "metadata": resize_metadata,
                        }

                    actions_performed.append("resize")

                # Convert format if needed
                if "convert_format" in actions:
                    target_format = target_spec.get("format")
                    if not target_format:
                        raise ValueError("Target format not specified in platform rule")

                    image_bytes = await self.convert_format(image_bytes, target_format)
                    actions_performed.append("convert_format")

                # Upload derived image
                derived_url = await self.minio_client.upload_image(
                    image_data=image_bytes,
                    product_id=base_asset.candidate_product_id,
                    asset_type=f"{base_asset.asset_type.value}_derived",
                    style_tags=[platform.value],
                    filename=f"{platform.value}_{uuid4().hex[:8]}.{target_spec.get('format', 'jpg')}",
                    content_type=f"image/{target_spec.get('format', 'jpg')}",
                )

                # Create derived asset record
                derived_spec = {
                    "width": target_spec.get("width"),
                    "height": target_spec.get("height"),
                    "format": target_spec.get("format"),
                    "has_text": base_asset.spec.get("has_text", False) if base_asset.spec else False,
                }

                derived_asset = await self._create_derived_record(
                    base_asset=base_asset,
                    platform=platform,
                    language=language,
                    file_url=derived_url,
                    spec=derived_spec,
                    db=db,
                )

                logger.info(
                    "asset_derived",
                    base_asset_id=str(base_asset.id),
                    derived_asset_id=str(derived_asset.id),
                    actions_performed=actions_performed,
                )

                return {
                    "status": "success",
                    "asset": derived_asset,
                    "actions_performed": actions_performed,
                }

            # Manual review needed
            logger.warning(
                "asset_derivation_manual_review",
                base_asset_id=str(base_asset.id),
                actions=actions,
            )
            return {
                "status": "deferred",
                "reason": "manual_review_required",
                "actions_required": actions,
            }

        except Exception as e:
            logger.error(
                "asset_derivation_failed",
                base_asset_id=str(base_asset.id),
                error=str(e),
            )
            return {
                "status": "error",
                "reason": str(e),
            }

    async def _create_derived_record(
        self,
        *,
        base_asset: ContentAsset,
        platform: TargetPlatform,
        language: Optional[str],
        file_url: str,
        spec: dict,
        db: AsyncSession,
    ) -> ContentAsset:
        """Create a derived asset record."""
        from app.db.models import ContentAsset

        derived_asset = ContentAsset(
            id=uuid4(),
            candidate_product_id=base_asset.candidate_product_id,
            product_variant_id=base_asset.product_variant_id,
            asset_type=base_asset.asset_type,
            usage_scope=ContentUsageScope.PLATFORM_DERIVED,
            parent_asset_id=base_asset.id,
            file_url=file_url,
            spec=spec,
            format=spec.get("format"),
            dimensions=f"{spec.get('width')}x{spec.get('height')}" if spec.get("width") else None,
            platform_tags=[platform.value],
            language_tags=[language] if language else None,
            style_tags=base_asset.style_tags,
            region_tags=base_asset.region_tags,
            generation_params={
                "derived_from": str(base_asset.id),
                "platform": platform.value,
                "language": language,
                "derivation_actions": spec.get("derivation_actions", []),
            },
            human_approved=False,
            usage_count=0,
            version=1,
        )

        db.add(derived_asset)
        await db.flush()

        return derived_asset
