"""Content Asset Manager Agent.

This agent is responsible for:
1. Generating images via ComfyUI
2. Uploading to MinIO
3. Creating ContentAsset records
4. Managing content lifecycle
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.core.enums import AssetType, ContentUsageScope, ProductLifecycle
from app.core.logging import get_logger
from app.db.models import CandidateProduct, ContentAsset, ProductVariant
from app.services.image_generation.comfyui_client import ComfyUIClient, get_comfyui_client
from app.services.storage.minio_client import MinIOClient, get_minio_client


class ContentAssetManagerAgent(BaseAgent):
    """Agent for managing content assets (images, videos).

    Input parameters:
    - candidate_product_id: UUID of the candidate product
    - asset_types: List of asset types to generate ["main_image", "detail_image"]
    - styles: List of style presets ["minimalist", "luxury", "cute"]
    - reference_images: Optional reference images for IPAdapter
    - generate_count: Number of images per style (default: 1)
    - platforms: Target platforms for tagging ["temu", "amazon"]
    - regions: Target regions for tagging ["us", "eu"]
    """

    STYLE_PROMPTS = {
        "minimalist": "clean white background, minimalist product photography, professional studio lighting, high-end e-commerce, neutral colors",
        "luxury": "premium luxury product photography, gold accents, marble background, elegant lighting, sophisticated, high-end brand",
        "cute": "adorable cute product photography, pastel colors, soft lighting, playful, kawaii style, youthful",
        "tech": "modern tech product photography, sleek design, blue LED accents, futuristic, clean lines, gadget aesthetic",
        "natural": "natural organic product photography, wooden surface, plants, earth tones, eco-friendly, sustainable",
        "seasonal": "seasonal holiday product photography, festive decorations, warm lighting, gift-ready, celebration",
    }

    DETAIL_PAGE_PROMPTS = {
        "feature_highlight": "product feature highlight, infographic style, clean layout, icons, specifications",
        "lifestyle": "lifestyle product usage, real-world setting, happy customer, relatable scene",
        "comparison": "before after comparison, problem solution, benefit showcase, visual demonstration",
    }

    def __init__(
        self,
        *,
        comfyui_client: ComfyUIClient | None = None,
        minio_client: MinIOClient | None = None,
    ):
        super().__init__("content_asset_manager")
        self.comfyui_client = comfyui_client
        self.minio_client = minio_client

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute content asset management.

        Generates images, uploads to storage, and creates ContentAsset records.
        """
        try:
            action = context.input_data.get("action")
            if action == "generate_base_assets":
                return await self.generate_base_assets(context)
            elif action == "generate_platform_assets":
                return await self.generate_platform_assets(context)

            # Get input parameters
            candidate_product_id = UUID(context.input_data.get("candidate_product_id"))
            asset_types = context.input_data.get("asset_types", ["main_image"])
            styles = context.input_data.get("styles", ["minimalist"])
            reference_images = context.input_data.get("reference_images")
            generate_count = context.input_data.get("generate_count", 1)
            platforms = context.input_data.get("platforms", [])
            regions = context.input_data.get("regions", [])
            variant_group = context.input_data.get("variant_group")
            variant_count = context.input_data.get("variant_count")

            self.logger.info(
                "content_generation_started",
                candidate_product_id=str(candidate_product_id),
                asset_types=asset_types,
                styles=styles,
            )

            styles, resolved_variant_group = self._resolve_variant_configuration(
                styles=styles,
                variant_count=variant_count,
                variant_group=variant_group,
            )

            # Initialize clients
            if self.comfyui_client is None:
                self.comfyui_client = get_comfyui_client()
            if self.minio_client is None:
                self.minio_client = get_minio_client()

            # Get candidate product
            candidate = await context.db.get(CandidateProduct, candidate_product_id)
            if not candidate:
                raise ValueError(f"Candidate product not found: {candidate_product_id}")

            # Update lifecycle status
            candidate.lifecycle_status = ProductLifecycle.CONTENT_GENERATING
            await context.db.commit()

            # Generate assets
            created_assets: list[ContentAsset] = []

            for asset_type in asset_types:
                for style in styles:
                    for i in range(generate_count):
                        try:
                            asset = await self._generate_single_asset(
                                context=context,
                                candidate=candidate,
                                asset_type=asset_type,
                                style=style,
                                reference_images=reference_images,
                                platforms=platforms,
                                regions=regions,
                                variant_group=resolved_variant_group,
                                index=i + 1,
                            )
                            if asset:
                                created_assets.append(asset)
                        except Exception as e:
                            self.logger.error(
                                "asset_generation_failed",
                                asset_type=asset_type,
                                style=style,
                                index=i,
                                error=str(e),
                            )
                            continue

            # Update lifecycle status
            if created_assets:
                candidate.lifecycle_status = ProductLifecycle.READY_TO_PUBLISH
            else:
                candidate.lifecycle_status = ProductLifecycle.DRAFT

            await context.db.commit()

            self.logger.info(
                "content_generation_completed",
                candidate_product_id=str(candidate_product_id),
                assets_created=len(created_assets),
            )

            return AgentResult(
                success=True,
                output_data={
                    "candidate_product_id": str(candidate_product_id),
                    "assets_created": len(created_assets),
                    "asset_ids": [str(a.id) for a in created_assets],
                    "lifecycle_status": candidate.lifecycle_status.value if candidate.lifecycle_status else None,
                    "variant_group": resolved_variant_group,
                    "variant_count": len(styles) if resolved_variant_group else None,
                },
            )

        except Exception as e:
            return await self._handle_error(e, context)

    def _resolve_variant_configuration(
        self,
        *,
        styles: list[str],
        variant_count: int | None,
        variant_group: str | None,
    ) -> tuple[list[str], str | None]:
        """Resolve style variants and variant group assignment for generation."""
        normalized_styles = list(dict.fromkeys(styles)) or ["minimalist"]

        if variant_count is None:
            return normalized_styles, variant_group

        if variant_count < 1:
            raise ValueError("variant_count must be at least 1")
        if variant_count > len(self.STYLE_PROMPTS):
            raise ValueError(
                f"variant_count exceeds available style presets ({len(self.STYLE_PROMPTS)})"
            )

        variant_styles = normalized_styles[:variant_count]
        if len(variant_styles) < variant_count:
            for style_name in self.STYLE_PROMPTS:
                if style_name in variant_styles:
                    continue
                variant_styles.append(style_name)
                if len(variant_styles) == variant_count:
                    break

        return variant_styles, variant_group or str(uuid4())

    async def _generate_single_asset(
        self,
        *,
        context: AgentContext,
        candidate: CandidateProduct,
        asset_type: str,
        style: str,
        reference_images: list[str] | None,
        platforms: list[str],
        regions: list[str],
        variant_group: str | None,
        index: int,
    ) -> ContentAsset | None:
        """Generate a single content asset."""
        # Build prompt
        prompt = self._build_prompt(
            product_title=candidate.title,
            category=candidate.category,
            asset_type=asset_type,
            style=style,
        )

        self.logger.info(
            "generating_asset",
            asset_type=asset_type,
            style=style,
            prompt=prompt[:100],
        )

        # Generate image
        image_data = await self.comfyui_client.generate_product_image(
            prompt=prompt,
            reference_images=reference_images,
            style=style,
            width=1024,
            height=1024,
        )

        # Upload to MinIO
        file_url = await self.minio_client.upload_image(
            image_data=image_data,
            product_id=candidate.id,
            asset_type=asset_type,
            style_tags=[style],
            filename=f"{style}_{index}.png",
        )

        # Create ContentAsset record
        asset = ContentAsset(
            id=uuid4(),
            candidate_product_id=candidate.id,
            asset_type=AssetType(asset_type),
            style_tags=[style],
            platform_tags=platforms,
            region_tags=regions,
            variant_group=variant_group,
            file_url=file_url,
            file_size=len(image_data),
            dimensions="1024x1024",
            format="png",
            ai_quality_score=None,  # TODO: Add quality scoring
            human_approved=False,
            usage_count=0,
            version=1,
            generation_params={
                "style": style,
                "asset_type": asset_type,
                "width": 1024,
                "height": 1024,
                "reference_images": reference_images,
            },
        )

        context.db.add(asset)
        await context.db.flush()

        self.logger.info(
            "asset_created",
            asset_id=str(asset.id),
            file_url=file_url,
            size=len(image_data),
        )

        return asset

    def _build_prompt(
        self,
        *,
        product_title: str,
        category: str | None,
        asset_type: str,
        style: str,
    ) -> str:
        """Build generation prompt for ComfyUI."""
        # Get style prompt
        style_prompt = self.STYLE_PROMPTS.get(style, self.STYLE_PROMPTS["minimalist"])

        # Get asset type prompt
        if asset_type == "detail_image":
            type_prompt = self.DETAIL_PAGE_PROMPTS.get("feature_highlight", "")
        else:
            type_prompt = "main product image, front view, centered"

        # Build final prompt
        prompt = f"{product_title}, {style_prompt}, {type_prompt}"

        if category:
            prompt += f", {category} category"

        # Add quality modifiers
        prompt += ", ultra high quality, 4k, sharp details, professional"

        return prompt

    async def _handle_error(self, error: Exception, context: AgentContext) -> AgentResult:
        """Handle errors during content generation."""
        self.logger.error(
            "content_asset_manager_error",
            error=str(error),
            error_type=type(error).__name__,
        )

        # Try to rollback lifecycle status
        try:
            candidate_product_id = context.input_data.get("candidate_product_id")
            if candidate_product_id:
                candidate = await context.db.get(CandidateProduct, UUID(candidate_product_id))
                if candidate:
                    candidate.lifecycle_status = ProductLifecycle.DRAFT
                    await context.db.commit()
        except Exception:
            pass

        return AgentResult(
            success=False,
            error_message=str(error),
        )

    async def generate_base_assets(self, context: AgentContext) -> AgentResult:
        """Generate base assets for a product variant.

        Creates base (platform-agnostic, no-text) assets for a variant
        that has been converted from a candidate.

        Input parameters:
        - variant_id: UUID of the product variant
        - candidate_product_id: UUID of the source candidate product (optional fallback)
        - asset_types: List of asset types to generate (default: ["main_image"])
        - styles: List of style presets (default: ["minimalist"])
        - generate_count: Number per style (default: 1)
        - platforms: Target platforms for tagging
        - regions: Target regions for tagging
        """
        try:
            variant_id_str = context.input_data.get("variant_id")
            candidate_product_id_str = context.input_data.get("candidate_product_id")
            asset_types = context.input_data.get("asset_types", ["main_image"])
            styles = context.input_data.get("styles", ["minimalist"])
            generate_count = context.input_data.get("generate_count", 1)
            platforms = context.input_data.get("platforms", [])
            regions = context.input_data.get("regions", [])

            # Resolve variant
            if variant_id_str:
                variant_id = UUID(variant_id_str)
                variant = await context.db.get(ProductVariant, variant_id)
                if not variant:
                    raise ValueError(f"Product variant not found: {variant_id}")
                candidate_product_id = variant.master.candidate_product_id
            elif candidate_product_id_str:
                candidate_product_id = UUID(candidate_product_id_str)
                variant = None
            else:
                raise ValueError("Either variant_id or candidate_product_id is required")

            candidate = await context.db.get(CandidateProduct, candidate_product_id)
            if not candidate:
                raise ValueError(f"Candidate product not found: {candidate_product_id}")

            self.logger.info(
                "base_asset_generation_started",
                variant_id=variant_id_str,
                candidate_product_id=str(candidate_product_id),
                asset_types=asset_types,
            )

            # Initialize clients
            if self.comfyui_client is None:
                self.comfyui_client = get_comfyui_client()
            if self.minio_client is None:
                self.minio_client = get_minio_client()

            created_assets: list[ContentAsset] = []

            for asset_type in asset_types:
                for style in styles:
                    for i in range(generate_count):
                        try:
                            asset = await self._generate_single_asset(
                                context=context,
                                candidate=candidate,
                                asset_type=asset_type,
                                style=style,
                                reference_images=None,
                                platforms=platforms,
                                regions=regions,
                                variant_group=None,
                                index=i + 1,
                            )
                            if asset:
                                # Mark as base asset
                                asset.usage_scope = ContentUsageScope.BASE
                                # Mark as no-text for platform agnosticism
                                spec = asset.generation_params or {}
                                spec["has_text"] = False
                                asset.generation_params = spec
                                # Link to variant if available
                                if variant:
                                    asset.product_variant_id = variant.id
                                created_assets.append(asset)
                        except Exception as e:
                            self.logger.error(
                                "base_asset_generation_failed",
                                asset_type=asset_type,
                                style=style,
                                index=i,
                                error=str(e),
                            )
                            continue

            self.logger.info(
                "base_asset_generation_completed",
                variant_id=variant_id_str,
                assets_created=len(created_assets),
            )

            return AgentResult(
                success=True,
                output_data={
                    "variant_id": variant_id_str,
                    "candidate_product_id": str(candidate_product_id),
                    "assets_created": len(created_assets),
                    "asset_ids": [str(a.id) for a in created_assets],
                    "usage_scope": ContentUsageScope.BASE.value,
                },
            )

        except Exception as e:
            self.logger.error(
                "base_asset_generation_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            return AgentResult(success=False, error_message=str(e))


    async def generate_platform_assets(self, context: AgentContext) -> AgentResult:
        """Generate platform-derived assets from base assets.

        Input parameters:
        - variant_id: UUID of the product variant
        - platform: Target platform (e.g., "amazon", "temu")
        - asset_types: List of asset types (default: ["main_image"])
        - language: Optional language code
        - force_regenerate: Force regeneration even if derived asset exists
        """
        from uuid import UUID

        from sqlalchemy import select

        from app.core.enums import AssetType, ContentUsageScope
        from app.db.models import ContentAsset
        from app.services.asset_derivation_service import AssetDerivationService

        try:
            variant_id = UUID(context.input_data["variant_id"])
            platform_str = context.input_data["platform"]
            from app.core.enums import TargetPlatform
            platform = TargetPlatform(platform_str)
            asset_types = context.input_data.get("asset_types", ["main_image"])
            language = context.input_data.get("language")
            force_regenerate = context.input_data.get("force_regenerate", False)

            self.logger.info(
                "platform_asset_generation_started",
                variant_id=str(variant_id),
                platform=platform.value,
                asset_types=asset_types,
                language=language,
            )

            derivation_service = AssetDerivationService()
            created_assets: list[ContentAsset] = []
            deferred_count = 0
            error_count = 0

            for asset_type_str in asset_types:
                asset_type = AssetType(asset_type_str)

                # 1. Find BASE assets for this variant
                base_asset = await self._find_best_base_asset(
                    variant_id=variant_id,
                    asset_type=asset_type,
                    db=context.db,
                )
                if not base_asset:
                    self.logger.warning(
                        "no_base_asset_found",
                        variant_id=str(variant_id),
                        asset_type=asset_type.value,
                    )
                    continue

                # 2. Check for existing derived asset
                existing = await self._find_existing_derived_asset(
                    base_asset_id=base_asset.id,
                    platform=platform,
                    language=language,
                    db=context.db,
                )
                if existing and not force_regenerate:
                    self.logger.info(
                        "existing_derived_asset_reused",
                        base_asset_id=str(base_asset.id),
                        existing_asset_id=str(existing.id),
                    )
                    created_assets.append(existing)
                    continue

                # 3. Execute derivation
                result = await derivation_service.derive_asset(
                    base_asset=base_asset,
                    platform=platform,
                    language=language,
                    db=context.db,
                )

                if result["status"] == "success":
                    created_assets.append(result["asset"])
                    await context.db.commit()
                elif result["status"] == "deferred":
                    self.logger.warning(
                        "derivation_deferred",
                        base_asset_id=str(base_asset.id),
                        reason=result.get("reason"),
                    )
                    deferred_count += 1
                else:
                    self.logger.error(
                        "derivation_failed",
                        base_asset_id=str(base_asset.id),
                        reason=result.get("reason"),
                    )
                    error_count += 1

            self.logger.info(
                "platform_asset_generation_completed",
                variant_id=str(variant_id),
                platform=platform.value,
                assets_created=len(created_assets),
                deferred=deferred_count,
                errors=error_count,
            )

            return AgentResult(
                success=True,
                output_data={
                    "variant_id": str(variant_id),
                    "platform": platform.value,
                    "assets_created": len(created_assets),
                    "deferred": deferred_count,
                    "errors": error_count,
                    "asset_ids": [str(a.id) for a in created_assets],
                    "usage_scope": ContentUsageScope.PLATFORM_DERIVED.value,
                },
            )

        except Exception as e:
            self.logger.error(
                "platform_asset_generation_error",
                error=str(e),
                error_type=type(e).__name__,
            )
            return AgentResult(success=False, error_message=str(e))

    async def _find_best_base_asset(
        self,
        *,
        variant_id: UUID,
        asset_type: AssetType,
        db,
    ) -> ContentAsset | None:
        """Find the best BASE asset for a variant and asset type."""
        from sqlalchemy import select

        stmt = select(ContentAsset).where(
            ContentAsset.product_variant_id == variant_id,
            ContentAsset.asset_type == asset_type,
            ContentAsset.usage_scope == ContentUsageScope.BASE,
            ContentAsset.archived == False,
        )
        result = await db.execute(stmt)
        assets = list(result.scalars().all())

        if not assets:
            # Fall back to any BASE asset not linked to variant
            stmt = select(ContentAsset).where(
                ContentAsset.candidate_product_id.in_(
                    select(ContentAsset.candidate_product_id).where(
                        ContentAsset.product_variant_id == variant_id
                    )
                ),
                ContentAsset.asset_type == asset_type,
                ContentAsset.usage_scope == ContentUsageScope.BASE,
                ContentAsset.archived == False,
            )
            result = await db.execute(stmt)
            assets = list(result.scalars().all())

        # Return highest quality or first
        if assets:
            return max(assets, key=lambda a: a.ai_quality_score or 0)
        return None

    async def _find_existing_derived_asset(
        self,
        *,
        base_asset_id: UUID,
        platform,
        language: str | None,
        db,
    ) -> ContentAsset | None:
        """Find an existing platform-derived asset for the given base asset."""
        from sqlalchemy import select

        stmt = select(ContentAsset).where(
            ContentAsset.parent_asset_id == base_asset_id,
            ContentAsset.usage_scope == ContentUsageScope.PLATFORM_DERIVED,
            ContentAsset.archived == False,
        )
        result = await db.execute(stmt)
        assets = list(result.scalars().all())

        for asset in assets:
            if asset.platform_tags and platform.value in asset.platform_tags:
                if language:
                    if asset.language_tags and language in asset.language_tags:
                        return asset
                else:
                    return asset

        return None


class ContentAssetQuery:
    """Query helper for content assets."""

    @staticmethod
    async def get_assets_for_product(
        db,
        product_id: UUID,
        asset_type: str | None = None,
        style: str | None = None,
        platform: str | None = None,
        approved_only: bool = True,
    ) -> list[ContentAsset]:
        """Get all content assets for a product with optional filters."""
        query = db.query(ContentAsset).filter(ContentAsset.candidate_product_id == product_id)

        if asset_type:
            query = query.filter(ContentAsset.asset_type == AssetType(asset_type))
        if style:
            query = query.filter(ContentAsset.style_tags.contains([style]))
        if platform:
            query = query.filter(ContentAsset.platform_tags.contains([platform]))
        if approved_only:
            query = query.filter(ContentAsset.human_approved == True)

        return query.order_by(ContentAsset.created_at.desc()).all()

    @staticmethod
    async def get_best_asset(
        db,
        product_id: UUID,
        asset_type: str = "main_image",
        platform: str | None = None,
    ) -> ContentAsset | None:
        """Get the best asset for a product (highest quality score)."""
        query = (
            db.query(ContentAsset)
            .filter(ContentAsset.candidate_product_id == product_id)
            .filter(ContentAsset.asset_type == AssetType(asset_type))
            .filter(ContentAsset.human_approved == True)
        )

        if platform:
            query = query.filter(ContentAsset.platform_tags.contains([platform]))

        return query.order_by(ContentAsset.ai_quality_score.desc()).first()

    @staticmethod
    async def approve_asset(db, asset_id: UUID, notes: str | None = None) -> ContentAsset | None:
        """Approve a content asset."""
        asset = await db.get(ContentAsset, asset_id)
        if asset:
            asset.human_approved = True
            asset.approval_notes = notes
            await db.commit()
        return asset

    @staticmethod
    async def increment_usage(db, asset_id: UUID) -> None:
        """Increment usage count for an asset."""
        asset = await db.get(ContentAsset, asset_id)
        if asset:
            asset.usage_count += 1
            await db.commit()
