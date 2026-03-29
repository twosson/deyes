"""Platform Publisher Agent.

This agent is responsible for:
1. Reading product and content assets
2. Calculating platform-specific pricing
3. Publishing to target platforms (Temu, Amazon, etc.)
4. Creating PlatformListing records
5. Handling publish failures and retries
"""
from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.core.enums import AssetType, ContentUsageScope, PlatformListingStatus, ProductLifecycle, TargetPlatform
from app.db.models import CandidateProduct, ContentAsset, ListingAssetAssociation, PlatformListing
from app.services.listing_metrics_service import ListingMetricsService
from app.services.platform_sync_service import PlatformSyncService
from app.services.platforms import PlatformAdapter, get_platform_adapter


class PlatformPublisherAgent(BaseAgent):
    """Agent for publishing products to target platforms.

    Input parameters:
    - candidate_product_id: UUID of the candidate product
    - target_platforms: List of platforms to publish to
      [{"platform": "temu", "region": "us"}, {"platform": "amazon", "region": "us"}]
    - pricing_strategy: Pricing strategy to use (default: "standard")
    - auto_approve: Skip manual approval (default: False)
    """

    # Pricing strategies
    PRICING_STRATEGIES = {
        "standard": {
            "markup": Decimal("2.5"),  # 2.5x markup
            "min_margin": Decimal("0.25"),  # 25% minimum margin
        },
        "aggressive": {
            "markup": Decimal("2.0"),  # 2.0x markup
            "min_margin": Decimal("0.20"),  # 20% minimum margin
        },
        "premium": {
            "markup": Decimal("3.0"),  # 3.0x markup
            "min_margin": Decimal("0.30"),  # 30% minimum margin
        },
    }

    # Platform-specific commission rates
    COMMISSION_RATES = {
        TargetPlatform.TEMU: Decimal("0.08"),  # 8%
        TargetPlatform.AMAZON: Decimal("0.15"),  # 15%
        TargetPlatform.OZON: Decimal("0.10"),  # 10%
        TargetPlatform.SHOPEE: Decimal("0.06"),  # 6%
        TargetPlatform.TIKTOK_SHOP: Decimal("0.05"),  # 5%
    }

    # Currency by region
    REGION_CURRENCIES = {
        "us": "USD",
        "uk": "GBP",
        "de": "EUR",
        "fr": "EUR",
        "es": "EUR",
        "it": "EUR",
        "au": "AUD",
        "ca": "CAD",
        "ru": "RUB",
        "jp": "JPY",
    }

    def __init__(self):
        super().__init__("platform_publisher")

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute platform publishing.

        Publishes product to multiple platforms and creates PlatformListing records.
        """
        try:
            # Get input parameters
            candidate_product_id = UUID(context.input_data.get("candidate_product_id"))
            target_platforms = context.input_data.get("target_platforms", [])
            pricing_strategy = context.input_data.get("pricing_strategy", "standard")
            auto_approve = context.input_data.get("auto_approve", False)

            if not target_platforms:
                raise ValueError("No target platforms specified")

            self.logger.info(
                "platform_publishing_started",
                candidate_product_id=str(candidate_product_id),
                platforms=[p["platform"] for p in target_platforms],
            )

            # Get candidate product
            candidate = await context.db.get(CandidateProduct, candidate_product_id)
            if not candidate:
                raise ValueError(f"Candidate product not found: {candidate_product_id}")

            # Check lifecycle status
            if candidate.lifecycle_status != ProductLifecycle.READY_TO_PUBLISH:
                if not auto_approve:
                    raise ValueError(
                        f"Product not ready to publish. Current status: {candidate.lifecycle_status}"
                    )

            # Get content assets
            assets_query = select(ContentAsset).where(
                ContentAsset.candidate_product_id == candidate_product_id,
                ContentAsset.human_approved == True,
            )
            result = await context.db.execute(assets_query)
            assets = list(result.scalars().all())

            if not assets:
                raise ValueError("No approved content assets found")

            # Publish to each platform
            published_listings: list[PlatformListing] = []
            failed_platforms: list[dict] = []

            for platform_config in target_platforms:
                try:
                    listing = await self._publish_to_platform(
                        context=context,
                        candidate=candidate,
                        assets=assets,
                        platform_config=platform_config,
                        pricing_strategy=pricing_strategy,
                    )
                    if listing:
                        published_listings.append(listing)
                except Exception as e:
                    self.logger.error(
                        "platform_publish_failed",
                        platform=platform_config.get("platform"),
                        region=platform_config.get("region"),
                        error=str(e),
                    )
                    failed_platforms.append(
                        {
                            "platform": platform_config.get("platform"),
                            "region": platform_config.get("region"),
                            "error": str(e),
                        }
                    )

            # Update lifecycle status
            if published_listings:
                candidate.lifecycle_status = ProductLifecycle.PUBLISHED
                await context.db.commit()

            self.logger.info(
                "platform_publishing_completed",
                candidate_product_id=str(candidate_product_id),
                published_count=len(published_listings),
                failed_count=len(failed_platforms),
            )

            return AgentResult(
                success=len(published_listings) > 0,
                output_data={
                    "candidate_product_id": str(candidate_product_id),
                    "published_count": len(published_listings),
                    "failed_count": len(failed_platforms),
                    "listing_ids": [str(listing.id) for listing in published_listings],
                    "failed_platforms": failed_platforms,
                },
            )

        except Exception as e:
            return await self._handle_error(e, context)

    async def _publish_to_platform(
        self,
        *,
        context: AgentContext,
        candidate: CandidateProduct,
        assets: list[ContentAsset],
        platform_config: dict[str, Any],
        pricing_strategy: str,
    ) -> PlatformListing | None:
        """Publish product to a single platform."""
        platform_name = platform_config.get("platform")
        region = platform_config.get("region", "us")

        self.logger.info(
            "publishing_to_platform",
            platform=platform_name,
            region=region,
            product_id=str(candidate.id),
        )

        # Get platform adapter
        adapter = self._get_adapter(platform_name, region)

        # Calculate price
        price, currency = self._calculate_price(
            candidate=candidate,
            platform=TargetPlatform(platform_name),
            region=region,
            strategy=pricing_strategy,
        )

        # Get initial inventory
        inventory = self._calculate_initial_inventory(candidate, platform_name)

        # Resolve variant_id for asset selection
        variant_id = await self._resolve_variant_id(candidate, context.db)

        # Select best assets using PlatformAssetAdapter
        platform_assets = await self._select_platform_assets(
            variant_id=variant_id,
            candidate=candidate,
            platform=TargetPlatform(platform_name),
            region=region,
            fallback_assets=assets,
            context=context,
        )

        if not platform_assets:
            raise ValueError(f"No compliant assets available for platform {platform_name}")

        # Create listing on platform
        listing_data = await adapter.create_listing(
            product=candidate,
            assets=platform_assets,
            region=region,
            price=price,
            currency=currency,
            inventory=inventory,
            title=candidate.title,
            description=None,  # TODO: Get from ListingDraft
            category=candidate.category,
        )

        # Create PlatformListing record
        listing = PlatformListing(
            id=uuid4(),
            candidate_product_id=candidate.id,
            product_variant_id=variant_id,
            platform=TargetPlatform(platform_name),
            region=region,
            platform_listing_id=listing_data.platform_listing_id,
            platform_url=listing_data.platform_url,
            price=price,
            currency=currency,
            inventory=inventory,
            status=listing_data.status,
            platform_data=listing_data.platform_data,
        )

        context.db.add(listing)
        await context.db.flush()

        # Create asset associations
        for i, asset in enumerate(platform_assets):
            association = ListingAssetAssociation(
                listing_id=listing.id,
                asset_id=asset.id,
                display_order=i,
                is_main=(i == 0),  # First asset is main image
            )
            context.db.add(association)

        await context.db.flush()

        await self._initialize_listing_metrics(context=context, listing=listing)

        self.logger.info(
            "platform_listing_created",
            listing_id=str(listing.id),
            platform=platform_name,
            region=region,
            platform_listing_id=listing_data.platform_listing_id,
            price=str(price),
        )

        return listing

    def _get_adapter(self, platform: str, region: str) -> PlatformAdapter:
        """Get platform adapter using shared resolution logic."""
        return get_platform_adapter(platform, region)

    def _calculate_price(
        self,
        *,
        candidate: CandidateProduct,
        platform: TargetPlatform,
        region: str,
        strategy: str,
    ) -> tuple[Decimal, str]:
        """Calculate selling price for platform.

        Formula:
        price = (cost + shipping) / (1 - commission - payment_fee - target_margin)
        """
        # Get cost (supplier price in USD)
        cost = candidate.platform_price or Decimal("5.0")

        # Get strategy params
        strategy_params = self.PRICING_STRATEGIES.get(strategy, self.PRICING_STRATEGIES["standard"])
        markup = strategy_params["markup"]
        min_margin = strategy_params["min_margin"]

        # Get commission rate
        commission_rate = self.COMMISSION_RATES.get(platform, Decimal("0.10"))

        # Calculate costs
        shipping_rate = Decimal("0.15")  # 15% shipping
        payment_fee_rate = Decimal("0.02")  # 2% payment fee
        return_rate = Decimal("0.05")  # 5% return cost

        # Calculate price
        total_cost = cost * (1 + shipping_rate)
        price = total_cost / (1 - commission_rate - payment_fee_rate - return_rate - min_margin)

        # Apply markup
        price = price * markup

        # Round to psychological price
        price = self._round_to_psychological_price(price)

        # Get currency
        currency = self.REGION_CURRENCIES.get(region, "USD")

        # TODO: Apply exchange rate if currency != USD

        return price, currency

    def _round_to_psychological_price(self, price: Decimal) -> Decimal:
        """Round to psychological price points (e.g., $9.99, $19.99)."""
        if price < Decimal("10"):
            # Round to X.99
            return Decimal(int(price)) + Decimal("0.99")
        elif price < Decimal("50"):
            # Round to X9.99
            return Decimal(int(price / 10) * 10) + Decimal("9.99")
        else:
            # Round to nearest 5
            return Decimal(int(price / 5) * 5) + Decimal("4.99")

    def _calculate_initial_inventory(
        self,
        candidate: CandidateProduct,
        platform: str,
    ) -> int:
        """Calculate initial inventory allocation for platform.

        Strategy:
        - Start conservative (10-50 units)
        - Based on supplier MOQ and stock
        """
        # Get supplier info
        supplier_moq = 1
        if candidate.raw_payload:
            supplier_moq = candidate.raw_payload.get("moq", 1)

        # Conservative initial allocation
        if supplier_moq <= 10:
            return 10
        elif supplier_moq <= 50:
            return supplier_moq
        else:
            return 50  # Cap at 50 for initial listing

    def _filter_assets_for_platform(
        self,
        assets: list[ContentAsset],
        platform: str,
        region: str,
    ) -> list[ContentAsset]:
        """Filter assets suitable for platform/region."""
        filtered = []

        for asset in assets:
            # Check platform tags
            if asset.platform_tags and platform not in asset.platform_tags:
                continue

            # Check region tags
            if asset.region_tags and region not in asset.region_tags:
                continue

            # Prefer main images
            if asset.asset_type == AssetType.MAIN_IMAGE:
                filtered.insert(0, asset)
            else:
                filtered.append(asset)

        return filtered

    async def _initialize_listing_metrics(
        self,
        *,
        context: AgentContext,
        listing: PlatformListing,
    ) -> None:
        """Initialize a zeroed daily metrics row for a newly created listing."""
        try:
            service = ListingMetricsService()
            await service.record_daily_metrics(
                context.db,
                listing_id=listing.id,
                metric_date=date.today(),
                impressions=0,
                clicks=0,
                orders=0,
                units_sold=0,
                revenue=Decimal("0.00"),
            )
        except Exception as exc:
            self.logger.warning(
                "listing_metrics_initialization_failed",
                listing_id=str(listing.id),
                error=str(exc),
            )

    async def _handle_error(self, error: Exception, context: AgentContext) -> AgentResult:
        """Handle errors during publishing."""
        self.logger.error(
            "platform_publisher_error",
            error=str(error),
            error_type=type(error).__name__,
        )

        return AgentResult(
            success=False,
            error_message=str(error),
        )

    async def _resolve_variant_id(
        self,
        candidate: CandidateProduct,
        db,
    ) -> UUID | None:
        """Resolve variant_id from candidate product.

        Returns:
            variant_id if found, None otherwise
        """
        from sqlalchemy import select

        from app.db.models import ProductMaster, ProductVariant

        # Try to find variant via master
        stmt = select(ProductVariant).join(ProductMaster).where(
            ProductMaster.candidate_product_id == candidate.id
        )
        result = await db.execute(stmt)
        variant = result.scalar_one_or_none()

        return variant.id if variant else None

    def _infer_language_from_region(self, region: str) -> str:
        """Infer language code from region.

        Args:
            region: Region code (e.g., "us", "uk", "de")

        Returns:
            Language code (e.g., "en", "de", "ja")
        """
        region_language_map = {
            "us": "en",
            "uk": "en",
            "ca": "en",
            "au": "en",
            "de": "de",
            "fr": "fr",
            "es": "es",
            "it": "it",
            "ru": "ru",
            "jp": "ja",
            "cn": "zh",
            "br": "pt",
            "mx": "es",
        }
        return region_language_map.get(region, "en")

    async def _select_platform_assets(
        self,
        *,
        variant_id: UUID | None,
        candidate: CandidateProduct,
        platform: TargetPlatform,
        region: str,
        fallback_assets: list[ContentAsset],
        context: AgentContext,
    ) -> list[ContentAsset]:
        """Select best assets for platform using PlatformAssetAdapter.

        Strategy:
        1. If variant_id exists, use select_best_asset() for MAIN_IMAGE
        2. If no compliant asset, trigger on-demand derivation
        3. Fall back to legacy filter if no variant or derivation fails
        """
        from app.services.platform_asset_adapter import PlatformAssetAdapter

        selected_assets = []

        # If no variant, fall back to legacy filter
        if not variant_id:
            self.logger.warning(
                "no_variant_id_fallback_to_legacy",
                candidate_id=str(candidate.id),
                platform=platform.value,
            )
            return self._filter_assets_for_platform(fallback_assets, platform.value, region)

        # Infer language from region
        language = self._infer_language_from_region(region)

        # Use PlatformAssetAdapter to select best asset
        adapter = PlatformAssetAdapter()
        main_asset = await adapter.select_best_asset(
            variant_id=variant_id,
            platform=platform,
            asset_type=AssetType.MAIN_IMAGE,
            db=context.db,
            language=language,
        )

        # If no asset found or asset is BASE and not compliant, try derivation
        if not main_asset or main_asset.usage_scope == ContentUsageScope.BASE:
            if main_asset:
                # Validate BASE asset compliance
                validation = await adapter.validate_asset_compliance(
                    asset=main_asset,
                    platform=platform,
                    db=context.db,
                )

                if not validation["valid"]:
                    self.logger.info(
                        "base_asset_not_compliant_triggering_derivation",
                        asset_id=str(main_asset.id),
                        platform=platform.value,
                        violations=validation["violations"],
                    )

                    # Trigger on-demand derivation
                    derivation_result = await self._derive_asset_on_demand(
                        variant_id=variant_id,
                        platform=platform,
                        language=language,
                        context=context,
                    )

                    if derivation_result["success"]:
                        # Re-select after derivation
                        main_asset = await adapter.select_best_asset(
                            variant_id=variant_id,
                            platform=platform,
                            asset_type=AssetType.MAIN_IMAGE,
                            db=context.db,
                            language=language,
                        )

        if main_asset:
            selected_assets.append(main_asset)
        else:
            # Final fallback to legacy filter
            self.logger.warning(
                "no_compliant_asset_fallback_to_legacy",
                variant_id=str(variant_id),
                platform=platform.value,
            )
            return self._filter_assets_for_platform(fallback_assets, platform.value, region)

        return selected_assets

    async def _derive_asset_on_demand(
        self,
        *,
        variant_id: UUID,
        platform: TargetPlatform,
        language: str,
        context: AgentContext,
    ) -> dict:
        """Trigger on-demand asset derivation.

        Returns:
            Dict with {"success": bool, "asset_id": str | None}
        """
        from app.agents.content_asset_manager import ContentAssetManagerAgent

        try:
            self.logger.info(
                "on_demand_derivation_started",
                variant_id=str(variant_id),
                platform=platform.value,
                language=language,
            )

            # Create ContentAssetManagerAgent
            asset_manager = ContentAssetManagerAgent()

            # Create derivation context
            derivation_context = AgentContext(
                strategy_run_id=context.strategy_run_id,
                db=context.db,
                input_data={
                    "action": "generate_platform_assets",
                    "variant_id": str(variant_id),
                    "platform": platform.value,
                    "asset_types": ["main_image"],
                    "language": language,
                },
            )

            # Execute derivation
            result = await asset_manager.execute(derivation_context)

            if result.success and result.output_data.get("assets_created", 0) > 0:
                asset_ids = result.output_data.get("asset_ids", [])
                self.logger.info(
                    "on_demand_derivation_success",
                    variant_id=str(variant_id),
                    platform=platform.value,
                    asset_ids=asset_ids,
                )
                return {
                    "success": True,
                    "asset_id": asset_ids[0] if asset_ids else None,
                }
            else:
                self.logger.warning(
                    "on_demand_derivation_failed",
                    variant_id=str(variant_id),
                    platform=platform.value,
                    error=result.error_message,
                )
                return {"success": False}

        except Exception as e:
            self.logger.error(
                "on_demand_derivation_error",
                variant_id=str(variant_id),
                platform=platform.value,
                error=str(e),
            )
            return {"success": False}


class PlatformSyncAgent(BaseAgent):
    """Agent for syncing listing performance data via PlatformSyncService."""

    def __init__(self):
        super().__init__("platform_sync")
        self.sync_service = PlatformSyncService()

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute platform sync.

        Input parameters:
        - sync_type: "listing_metrics" (preferred), "inventory", or "price"
        - platform_listing_ids: Optional list of specific listings to sync
        - start_date: Optional start date in ISO format (defaults to today)
        - end_date: Optional end date in ISO format (defaults to today)
        """
        try:
            sync_type = context.input_data.get("sync_type", "listing_metrics")
            listing_ids = context.input_data.get("platform_listing_ids")
            start_date = self._parse_sync_date(context.input_data.get("start_date"))
            end_date = self._parse_sync_date(context.input_data.get("end_date"))

            if end_date < start_date:
                raise ValueError("end_date cannot be earlier than start_date")

            self.logger.info(
                "platform_sync_started",
                sync_type=sync_type,
                listing_count=len(listing_ids) if listing_ids else "all",
                start_date=str(start_date),
                end_date=str(end_date),
            )

            if listing_ids:
                query = select(PlatformListing).where(
                    PlatformListing.id.in_([UUID(lid) for lid in listing_ids])
                )
            else:
                query = select(PlatformListing).where(
                    PlatformListing.status == PlatformListingStatus.ACTIVE
                )

            result = await context.db.execute(query)
            listings = list(result.scalars().all())

            synced_count = 0
            failed_count = 0

            for listing in listings:
                try:
                    if sync_type == "listing_metrics":
                        await self.sync_service.sync_listing_metrics(
                            context.db,
                            listing_id=listing.id,
                            start_date=start_date,
                            end_date=end_date,
                        )
                    elif sync_type == "inventory":
                        await self.sync_service.sync_listing_inventory(
                            context.db,
                            listing_id=listing.id,
                        )
                    elif sync_type == "price":
                        await self.sync_service.sync_listing_price(
                            context.db,
                            listing_id=listing.id,
                        )
                    elif sync_type == "status":
                        await self.sync_service.sync_listing_status(
                            context.db,
                            listing_id=listing.id,
                        )
                    else:
                        raise ValueError(f"Unsupported sync_type: {sync_type}")

                    listing.last_synced_at = datetime.now(UTC)
                    listing.sync_error = None
                    synced_count += 1
                except Exception as e:
                    self.logger.error(
                        "listing_sync_failed",
                        listing_id=str(listing.id),
                        error=str(e),
                    )
                    listing.sync_error = str(e)
                    failed_count += 1

            await context.db.commit()

            self.logger.info(
                "platform_sync_completed",
                sync_type=sync_type,
                synced_count=synced_count,
                failed_count=failed_count,
            )

            return AgentResult(
                success=failed_count == 0,
                output_data={
                    "sync_type": sync_type,
                    "synced_count": synced_count,
                    "failed_count": failed_count,
                    "start_date": str(start_date),
                    "end_date": str(end_date),
                },
            )

        except Exception as e:
            self.logger.error("platform_sync_error", error=str(e))
            return AgentResult(success=False, output_data={}, error_message=str(e))

    def _parse_sync_date(self, value: str | None) -> date:
        """Parse an ISO date string, defaulting to today when absent."""
        if not value:
            return date.today()
        return date.fromisoformat(value)
