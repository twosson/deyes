"""Platform Publisher Agent.

This agent is responsible for:
1. Reading product and content assets
2. Calculating platform-specific pricing
3. Publishing to target platforms (Temu, Amazon, etc.)
4. Creating PlatformListing records
5. Handling publish failures and retries
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import select

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.core.config import get_settings
from app.core.enums import AssetType, PlatformListingStatus, ProductLifecycle, TargetPlatform
from app.core.logging import get_logger
from app.db.models import CandidateProduct, ContentAsset, ListingAssetAssociation, PlatformListing
from app.services.listing_metrics_service import ListingMetricsService
from app.services.platforms.base import MockPlatformAdapter, PlatformAdapter
from app.services.platforms.temu import get_temu_adapter


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
        self.settings = get_settings()
        self._adapters: dict[str, PlatformAdapter] = {}

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

        # Filter assets for this platform
        platform_assets = self._filter_assets_for_platform(assets, platform_name, region)

        if not platform_assets:
            self.logger.warning(
                "no_assets_for_platform",
                platform=platform_name,
                region=region,
            )
            platform_assets = assets  # Fallback to all assets

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
        """Get or create platform adapter."""
        key = f"{platform}_{region}"

        if key not in self._adapters:
            if platform == "temu":
                self._adapters[key] = get_temu_adapter(
                    region=region,
                    mock=self.settings.temu_use_mock,
                )
            elif platform == "amazon":
                # TODO: Implement Amazon adapter
                self._adapters[key] = MockPlatformAdapter(TargetPlatform.AMAZON)
            elif platform == "ozon":
                # TODO: Implement Ozon adapter
                self._adapters[key] = MockPlatformAdapter(TargetPlatform.OZON)
            else:
                # Default to mock adapter
                self._adapters[key] = MockPlatformAdapter(TargetPlatform(platform))

        return self._adapters[key]

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


class PlatformSyncAgent(BaseAgent):
    """Agent for syncing inventory/price to platforms.

    This is a separate agent that runs periodically to sync data.
    """

    def __init__(self):
        super().__init__("platform_sync")

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute platform sync.

        Input parameters:
        - sync_type: "inventory" or "price"
        - platform_listing_ids: Optional list of specific listings to sync
        """
        try:
            sync_type = context.input_data.get("sync_type", "inventory")
            listing_ids = context.input_data.get("platform_listing_ids")

            self.logger.info(
                "platform_sync_started",
                sync_type=sync_type,
                listing_count=len(listing_ids) if listing_ids else "all",
            )

            # Get listings to sync
            if listing_ids:
                query = select(PlatformListing).where(
                    PlatformListing.id.in_([UUID(lid) for lid in listing_ids])
                )
            else:
                # Sync all active listings
                query = select(PlatformListing).where(
                    PlatformListing.status == PlatformListingStatus.ACTIVE
                )

            result = await context.db.execute(query)
            listings = list(result.scalars().all())

            # Sync each listing
            synced_count = 0
            failed_count = 0

            for listing in listings:
                try:
                    if sync_type == "inventory":
                        success = await self._sync_inventory(listing)
                    elif sync_type == "price":
                        success = await self._sync_price(listing)
                    else:
                        continue

                    if success:
                        synced_count += 1
                    else:
                        failed_count += 1

                except Exception as e:
                    self.logger.error(
                        "listing_sync_failed",
                        listing_id=str(listing.id),
                        error=str(e),
                    )
                    failed_count += 1

            await context.db.commit()

            self.logger.info(
                "platform_sync_completed",
                sync_type=sync_type,
                synced_count=synced_count,
                failed_count=failed_count,
            )

            return AgentResult(
                success=True,
                output_data={
                    "sync_type": sync_type,
                    "synced_count": synced_count,
                    "failed_count": failed_count,
                },
            )

        except Exception as e:
            self.logger.error("platform_sync_error", error=str(e))
            return AgentResult(success=False, error_message=str(e))

    async def _sync_inventory(self, listing: PlatformListing) -> bool:
        """Sync inventory for a listing."""
        # TODO: Implement inventory sync logic
        # 1. Query 1688 for current stock
        # 2. Calculate allocation for this platform
        # 3. Call platform API to update
        return True

    async def _sync_price(self, listing: PlatformListing) -> bool:
        """Sync price for a listing."""
        # TODO: Implement price sync logic
        # 1. Check exchange rate
        # 2. Check supplier price changes
        # 3. Recalculate and update if needed
        return True
