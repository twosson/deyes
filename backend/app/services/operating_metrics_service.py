"""Operating metrics service for unified read-only aggregation layer."""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from decimal import Decimal
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.services.currency_converter import CurrencyConverter
from app.services.listing_metrics_service import ListingMetricsService
from app.services.profit_ledger_service import ProfitLedgerService
from app.services.refund_analysis_service import RefundAnalysisService
from app.services.unified_listing_service import UnifiedListingService


class OperatingMetricsService:
    """Unified read-only aggregation layer for operating metrics."""

    def __init__(self):
        self.logger = get_logger(__name__)
        self.profit_service = ProfitLedgerService()
        self.refund_service = RefundAnalysisService()
        self.listing_metrics_service = ListingMetricsService()
        self.unified_listing_service = UnifiedListingService()
        self.currency_converter = CurrencyConverter()

    async def get_sku_operating_snapshot(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get SKU-level operating snapshot.

        Args:
            db: Database session
            product_variant_id: Product variant ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            {
                "profit_snapshot": {...},
                "refund_rate": {...},
                "refund_reasons": [...],
            }
        """
        # Get profit snapshot
        profit_snapshot = await self.profit_service.get_profit_snapshot(
            db=db,
            product_variant_id=product_variant_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Get refund rate
        refund_rate = await self.refund_service.get_refund_rate(
            db=db,
            product_variant_id=product_variant_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Get refund reasons
        refund_reasons = await self.refund_service.summarize_refund_reasons(
            db=db,
            product_variant_id=product_variant_id,
            start_date=start_date,
            end_date=end_date,
        )

        self.logger.info(
            "sku_operating_snapshot_generated",
            variant_id=str(product_variant_id),
            profit_entries=profit_snapshot["entry_count"],
            refund_rate=refund_rate["refund_rate"],
        )

        return {
            "variant_id": str(product_variant_id),
            "profit_snapshot": profit_snapshot,
            "refund_rate": refund_rate,
            "refund_reasons": refund_reasons,
        }

    async def get_listing_operating_snapshot(
        self,
        db: AsyncSession,
        platform_listing_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get listing-level operating snapshot.

        Args:
            db: Database session
            platform_listing_id: Platform listing ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            {
                "profit_snapshot": {...},
                "refund_rate": {...},
                "refund_reasons": [...],
                "listing_performance": {...},
            }
        """
        # Get profit snapshot
        profit_snapshot = await self.profit_service.get_listing_profitability(
            db=db,
            platform_listing_id=platform_listing_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Get refund rate
        refund_rate = await self.refund_service.get_refund_rate(
            db=db,
            platform_listing_id=platform_listing_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Get refund reasons
        refund_reasons = await self.refund_service.summarize_refund_reasons(
            db=db,
            platform_listing_id=platform_listing_id,
            start_date=start_date,
            end_date=end_date,
        )

        # Get listing performance
        listing_performance = await self.listing_metrics_service.get_metrics_summary(
            db=db,
            listing_id=platform_listing_id,
            start_date=start_date,
            end_date=end_date,
        )

        self.logger.info(
            "listing_operating_snapshot_generated",
            listing_id=str(platform_listing_id),
            profit_entries=profit_snapshot["entry_count"],
            refund_rate=refund_rate["refund_rate"],
        )

        return {
            "listing_id": str(platform_listing_id),
            "profit_snapshot": profit_snapshot,
            "refund_rate": refund_rate,
            "refund_reasons": refund_reasons,
            "listing_performance": listing_performance,
        }

    async def get_supplier_operating_snapshot(
        self,
        db: AsyncSession,
        supplier_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> dict:
        """Get supplier-level operating snapshot.

        Args:
            db: Database session
            supplier_id: Supplier ID
            start_date: Filter by start date
            end_date: Filter by end date

        Returns:
            {
                "profit_snapshot": {...},
            }
        """
        # Get profit snapshot
        profit_snapshot = await self.profit_service.get_supplier_profitability(
            db=db,
            supplier_id=supplier_id,
            start_date=start_date,
            end_date=end_date,
        )

        self.logger.info(
            "supplier_operating_snapshot_generated",
            supplier_id=str(supplier_id),
            profit_entries=profit_snapshot["entry_count"],
        )

        return {
            "supplier_id": str(supplier_id),
            "profit_snapshot": profit_snapshot,
        }

    async def get_sku_multiplatform_snapshot(
        self,
        db: AsyncSession,
        product_variant_id: UUID,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        base_currency: Optional[str] = None,
    ) -> dict:
        """Get SKU-level cross-platform operating snapshot.

        Aggregates status, inventory, price, performance, and profit across
        all platform listings for a given product variant (SKU).

        Args:
            db: Database session
            product_variant_id: Product variant ID
            start_date: Filter by start date (optional)
            end_date: Filter by end date (optional)
            base_currency: Convert all amounts to this currency (optional)

        Returns:
            Cross-platform snapshot dict with summary, platform_breakdown,
            and listing details. Each listing carries its own profit_snapshot
            and listing_performance data.
        """
        # 1. Get all listings for this SKU
        listings = await self.unified_listing_service.get_sku_listings(
            db=db,
            product_variant_id=product_variant_id,
        )

        # 2. Group listings by (platform, region)
        platform_groups: dict = defaultdict(lambda: defaultdict(list))
        for listing in listings:
            platform_groups[listing.platform.value][listing.region].append(listing)

        # 3. Build listing-level details
        listing_details = []
        for listing in listings:
            listing_id = str(listing.id)

            # Profit snapshot for this listing
            profit_snapshot = await self.profit_service.get_listing_profitability(
                db=db,
                platform_listing_id=listing.id,
                start_date=start_date,
                end_date=end_date,
            )

            # Listing performance metrics
            listing_performance = await self.listing_metrics_service.get_metrics_summary(
                db=db,
                listing_id=listing.id,
                start_date=start_date,
                end_date=end_date,
            )

            # Optional currency conversion
            snapshot_data = {
                "listing_id": listing_id,
                "platform": listing.platform.value,
                "region": listing.region,
                "status": listing.status.value,
                "price": float(listing.price),
                "currency": listing.currency,
                "inventory": listing.inventory,
            }

            if base_currency and base_currency != listing.currency:
                try:
                    snapshot_data = await self.currency_converter.convert_snapshot_amounts(
                        db=db,
                        payload=snapshot_data,
                        from_currency=listing.currency,
                        to_currency=base_currency,
                        fields=["price"],
                    )
                except ValueError:
                    self.logger.warning(
                        "currency_conversion_skipped",
                        listing_id=listing_id,
                        from_currency=listing.currency,
                        to_currency=base_currency,
                    )

            snapshot_data["profit_snapshot"] = profit_snapshot
            snapshot_data["listing_performance"] = listing_performance
            listing_details.append(snapshot_data)

        # 4. Build platform/region breakdown
        platform_breakdown = []
        total_inventory = 0
        all_platforms = set()
        all_regions = set()

        for platform, regions_dict in sorted(platform_groups.items()):
            platform_entry: dict = {
                "platform": platform,
                "regions": [],
            }

            for region, region_listings in sorted(regions_dict.items()):
                all_platforms.add(platform)
                all_regions.add(region)

                # Aggregate region-level metrics
                region_inventory = sum(l.inventory or 0 for l in region_listings)
                total_inventory += region_inventory

                status_breakdown = defaultdict(int)
                for l in region_listings:
                    status_breakdown[l.status.value] += 1

                prices = [float(l.price) for l in region_listings]
                currencies = list(set(l.currency for l in region_listings))

                # Aggregate performance
                region_performance = {
                    "total_impressions": 0,
                    "total_clicks": 0,
                    "total_orders": 0,
                    "total_revenue": Decimal("0.00"),
                }
                region_profit_entries = []

                for l in region_listings:
                    lp = await self.listing_metrics_service.get_metrics_summary(
                        db=db,
                        listing_id=l.id,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    region_performance["total_impressions"] += lp.get("total_impressions", 0)
                    region_performance["total_clicks"] += lp.get("total_clicks", 0)
                    region_performance["total_orders"] += lp.get("total_orders", 0)
                    revenue_val = lp.get("total_revenue")
                    if revenue_val is not None:
                        region_performance["total_revenue"] += Decimal(str(revenue_val))

                    # Aggregate profit
                    lp_profit = await self.profit_service.get_listing_profitability(
                        db=db,
                        platform_listing_id=l.id,
                        start_date=start_date,
                        end_date=end_date,
                    )
                    region_profit_entries.append(lp_profit)

                ctr = (
                    region_performance["total_clicks"] / region_performance["total_impressions"]
                    if region_performance["total_impressions"] > 0
                    else 0.0
                )

                # Price range
                price_range = {
                    "min": min(prices) if prices else 0.0,
                    "max": max(prices) if prices else 0.0,
                    "currency": currencies[0] if currencies else "USD",
                }

                # Optional currency conversion for price range and revenue
                if base_currency and price_range["currency"] != base_currency:
                    try:
                        price_range = await self.currency_converter.convert_snapshot_amounts(
                            db=db,
                            payload=price_range,
                            from_currency=price_range["currency"],
                            to_currency=base_currency,
                            fields=["min", "max"],
                        )
                        region_performance["total_revenue"] = await self.currency_converter.convert_amount(
                            db=db,
                            amount=region_performance["total_revenue"],
                            from_currency=price_range["currency"],
                            to_currency=base_currency,
                        )
                    except ValueError:
                        self.logger.warning(
                            "currency_conversion_skipped_for_region",
                            platform=platform,
                            region=region,
                            from_currency=price_range["currency"],
                            to_currency=base_currency,
                        )

                region_entry = {
                    "region": region,
                    "listing_count": len(region_listings),
                    "inventory": region_inventory,
                    "status_breakdown": dict(status_breakdown),
                    "price_range": price_range,
                    "performance": {
                        **region_performance,
                        "total_revenue": float(region_performance["total_revenue"]),
                        "ctr": round(ctr, 4),
                    },
                }

                # Aggregate refund rate for region
                region_refund_rate = await self.refund_service.get_refund_rate(
                    db=db,
                    platform_listing_id=region_listings[0].id,
                    start_date=start_date,
                    end_date=end_date,
                )
                region_entry["refund_rate"] = region_refund_rate

                # Sum profit entries
                region_profit = {
                    "total_gross_revenue": Decimal("0.00"),
                    "total_platform_fees": Decimal("0.00"),
                    "total_refund_loss": Decimal("0.00"),
                    "total_ad_cost": Decimal("0.00"),
                    "total_fulfillment_cost": Decimal("0.00"),
                    "total_net_profit": Decimal("0.00"),
                    "entry_count": 0,
                }
                for pe in region_profit_entries:
                    region_profit["total_gross_revenue"] += Decimal(str(pe.get("total_gross_revenue", 0)))
                    region_profit["total_platform_fees"] += Decimal(str(pe.get("total_platform_fees", 0)))
                    region_profit["total_refund_loss"] += Decimal(str(pe.get("total_refund_loss", 0)))
                    region_profit["total_ad_cost"] += Decimal(str(pe.get("total_ad_cost", 0)))
                    region_profit["total_fulfillment_cost"] += Decimal(str(pe.get("total_fulfillment_cost", 0)))
                    region_profit["total_net_profit"] += Decimal(str(pe.get("total_net_profit", 0)))
                    region_profit["entry_count"] += pe.get("entry_count", 0)

                # Convert profit totals
                if base_currency:
                    for field in [
                        "total_gross_revenue",
                        "total_platform_fees",
                        "total_refund_loss",
                        "total_ad_cost",
                        "total_fulfillment_cost",
                        "total_net_profit",
                    ]:
                        try:
                            region_profit[field] = await self.currency_converter.convert_amount(
                                db=db,
                                amount=region_profit[field],
                                from_currency=listing.currency,
                                to_currency=base_currency,
                            )
                        except ValueError:
                            pass

                region_entry["profit_snapshot"] = {
                    k: float(v) if isinstance(v, Decimal) else v
                    for k, v in region_profit.items()
                }
                platform_entry["regions"].append(region_entry)

            platform_breakdown.append(platform_entry)

        # 5. SKU-level summary
        active_listing_count = sum(
            1 for l in listings if l.status.value == "active"
        )

        # SKU-level refund rate
        sku_refund_rate = await self.refund_service.get_refund_rate(
            db=db,
            product_variant_id=product_variant_id,
            start_date=start_date,
            end_date=end_date,
        )

        # SKU-level profit snapshot
        sku_profit = await self.profit_service.get_profit_snapshot(
            db=db,
            product_variant_id=product_variant_id,
            start_date=start_date,
            end_date=end_date,
        )

        summary = {
            "listing_count": len(listings),
            "active_listing_count": active_listing_count,
            "total_inventory": total_inventory,
            "platforms": sorted(all_platforms),
            "regions": sorted(all_regions),
            "profit_snapshot": sku_profit,
            "refund_rate": sku_refund_rate,
        }

        self.logger.info(
            "sku_multiplatform_snapshot_generated",
            variant_id=str(product_variant_id),
            listing_count=len(listings),
            platform_count=len(platform_groups),
        )

        return {
            "variant_id": str(product_variant_id),
            "base_currency": base_currency or "original",
            "summary": summary,
            "platform_breakdown": platform_breakdown,
            "listings": listing_details,
        }

    async def get_region_performance(
        self,
        db: AsyncSession,
        region: str,
        platform: Optional[str] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        base_currency: Optional[str] = None,
    ) -> dict:
        """Get region-level performance aggregation across all SKUs/listings.

        Aggregates performance metrics for all listings in a specific region,
        optionally filtered by platform.

        Args:
            db: Database session
            region: Region code (e.g., "us", "uk", "de")
            platform: Optional platform filter (e.g., "temu", "amazon")
            start_date: Filter by start date
            end_date: Filter by end date
            base_currency: Convert all amounts to this currency

        Returns:
            {
                "region": "us",
                "platforms": [...],
                "total_listings": 10,
                "active_listings": 8,
                "total_inventory": 500,
                "performance": {
                    "total_impressions": 10000,
                    "total_clicks": 500,
                    "total_orders": 50,
                    "total_revenue": 5000.00,
                    "ctr": 0.05,
                    "conversion_rate": 0.10,
                },
                "profit_snapshot": {...},
                "refund_rate": {...},
                "currency": "USD",
            }
        """
        from sqlalchemy import select

        from app.core.enums import PlatformListingStatus, TargetPlatform
        from app.db.models import PlatformListing

        # Build query for listings in region
        stmt = select(PlatformListing).where(PlatformListing.region == region)

        if platform:
            platform_enum = TargetPlatform(platform)
            stmt = stmt.where(PlatformListing.platform == platform_enum)

        result = await db.execute(stmt)
        listings = list(result.scalars().all())

        if not listings:
            return {
                "region": region,
                "platform": platform,
                "platforms": [],
                "total_listings": 0,
                "active_listings": 0,
                "total_inventory": 0,
                "performance": {
                    "total_impressions": 0,
                    "total_clicks": 0,
                    "total_orders": 0,
                    "total_revenue": 0.0,
                    "ctr": 0.0,
                    "conversion_rate": 0.0,
                },
                "profit_snapshot": {
                    "total_gross_revenue": 0.0,
                    "total_platform_fees": 0.0,
                    "total_refund_loss": 0.0,
                    "total_ad_cost": 0.0,
                    "total_fulfillment_cost": 0.0,
                    "total_net_profit": 0.0,
                    "entry_count": 0,
                },
                "refund_rate": {"refund_rate": 0.0, "refund_count": 0, "order_count": 0},
                "currency": base_currency or "USD",
            }

        # Aggregate metrics
        platforms = set()
        total_inventory = 0
        active_count = 0
        total_impressions = 0
        total_clicks = 0
        total_orders = 0
        total_revenue = Decimal("0.00")
        currencies = set()

        # Profit aggregation
        total_gross_revenue = Decimal("0.00")
        total_platform_fees = Decimal("0.00")
        total_refund_loss = Decimal("0.00")
        total_ad_cost = Decimal("0.00")
        total_fulfillment_cost = Decimal("0.00")
        total_net_profit = Decimal("0.00")
        profit_entry_count = 0

        # Refund aggregation
        total_refund_count = 0
        total_order_count = 0

        for listing in listings:
            platforms.add(listing.platform.value)
            total_inventory += listing.inventory or 0
            currencies.add(listing.currency)

            if listing.status == PlatformListingStatus.ACTIVE:
                active_count += 1

            # Performance metrics
            perf = await self.listing_metrics_service.get_metrics_summary(
                db=db,
                listing_id=listing.id,
                start_date=start_date,
                end_date=end_date,
            )
            total_impressions += perf.get("total_impressions", 0)
            total_clicks += perf.get("total_clicks", 0)
            total_orders += perf.get("total_orders", 0)
            revenue_val = perf.get("total_revenue")
            if revenue_val is not None:
                total_revenue += Decimal(str(revenue_val))

            # Profit metrics
            profit = await self.profit_service.get_listing_profitability(
                db=db,
                platform_listing_id=listing.id,
                start_date=start_date,
                end_date=end_date,
            )
            total_gross_revenue += Decimal(str(profit.get("total_gross_revenue", 0)))
            total_platform_fees += Decimal(str(profit.get("total_platform_fees", 0)))
            total_refund_loss += Decimal(str(profit.get("total_refund_loss", 0)))
            total_ad_cost += Decimal(str(profit.get("total_ad_cost", 0)))
            total_fulfillment_cost += Decimal(str(profit.get("total_fulfillment_cost", 0)))
            total_net_profit += Decimal(str(profit.get("total_net_profit", 0)))
            profit_entry_count += profit.get("entry_count", 0)

            # Refund metrics
            refund = await self.refund_service.get_refund_rate(
                db=db,
                platform_listing_id=listing.id,
                start_date=start_date,
                end_date=end_date,
            )
            total_refund_count += refund.get("refund_count", 0)
            total_order_count += refund.get("order_count", 0)

        # Currency conversion
        primary_currency = list(currencies)[0] if currencies else "USD"

        if base_currency and base_currency != primary_currency:
            try:
                total_revenue = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_revenue,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_gross_revenue = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_gross_revenue,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_platform_fees = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_platform_fees,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_refund_loss = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_refund_loss,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_ad_cost = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_ad_cost,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_fulfillment_cost = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_fulfillment_cost,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_net_profit = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_net_profit,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
            except ValueError:
                self.logger.warning(
                    "currency_conversion_skipped_for_region",
                    region=region,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )

        ctr = total_clicks / total_impressions if total_impressions > 0 else 0.0
        conversion_rate = total_orders / total_clicks if total_clicks > 0 else 0.0
        refund_rate = total_refund_count / total_order_count if total_order_count > 0 else 0.0

        self.logger.info(
            "region_performance_generated",
            region=region,
            platform=platform,
            listing_count=len(listings),
            active_count=active_count,
        )

        return {
            "region": region,
            "platform": platform,
            "platforms": sorted(platforms),
            "total_listings": len(listings),
            "active_listings": active_count,
            "total_inventory": total_inventory,
            "performance": {
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "total_orders": total_orders,
                "total_revenue": float(total_revenue),
                "ctr": round(ctr, 4),
                "conversion_rate": round(conversion_rate, 4),
            },
            "profit_snapshot": {
                "total_gross_revenue": float(total_gross_revenue),
                "total_platform_fees": float(total_platform_fees),
                "total_refund_loss": float(total_refund_loss),
                "total_ad_cost": float(total_ad_cost),
                "total_fulfillment_cost": float(total_fulfillment_cost),
                "total_net_profit": float(total_net_profit),
                "entry_count": profit_entry_count,
            },
            "refund_rate": {
                "refund_rate": round(refund_rate, 4),
                "refund_count": total_refund_count,
                "order_count": total_order_count,
            },
            "currency": base_currency or primary_currency,
        }

    async def get_platform_region_snapshot(
        self,
        db: AsyncSession,
        platform: str,
        region: str,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
        base_currency: Optional[str] = None,
    ) -> dict:
        """Get platform-region level snapshot with SKU breakdown.

        Provides detailed breakdown of all SKUs/listings for a specific
        platform-region combination.

        Args:
            db: Database session
            platform: Platform name (e.g., "temu", "amazon")
            region: Region code (e.g., "us", "uk")
            start_date: Filter by start date
            end_date: Filter by end date
            base_currency: Convert all amounts to this currency

        Returns:
            {
                "platform": "temu",
                "region": "us",
                "summary": {
                    "listing_count": 5,
                    "active_listing_count": 4,
                    "total_inventory": 200,
                    "total_skus": 3,
                },
                "performance": {...},
                "profit_snapshot": {...},
                "refund_rate": {...},
                "sku_breakdown": [...],
                "listings": [...],
                "currency": "USD",
            }
        """
        from sqlalchemy import select

        from app.core.enums import PlatformListingStatus, TargetPlatform
        from app.db.models import PlatformListing

        platform_enum = TargetPlatform(platform)

        # Query listings for platform-region
        stmt = select(PlatformListing).where(
            PlatformListing.platform == platform_enum,
            PlatformListing.region == region,
        )
        result = await db.execute(stmt)
        listings = list(result.scalars().all())

        if not listings:
            return {
                "platform": platform,
                "region": region,
                "summary": {
                    "listing_count": 0,
                    "active_listing_count": 0,
                    "total_inventory": 0,
                    "total_skus": 0,
                },
                "performance": {
                    "total_impressions": 0,
                    "total_clicks": 0,
                    "total_orders": 0,
                    "total_revenue": 0.0,
                    "ctr": 0.0,
                    "conversion_rate": 0.0,
                },
                "profit_snapshot": {
                    "total_gross_revenue": 0.0,
                    "total_platform_fees": 0.0,
                    "total_refund_loss": 0.0,
                    "total_ad_cost": 0.0,
                    "total_fulfillment_cost": 0.0,
                    "total_net_profit": 0.0,
                    "entry_count": 0,
                },
                "refund_rate": {"refund_rate": 0.0, "refund_count": 0, "order_count": 0},
                "sku_breakdown": [],
                "listings": [],
                "currency": base_currency or "USD",
            }

        # Aggregate metrics
        total_inventory = 0
        active_count = 0
        unique_skus = set()
        total_impressions = 0
        total_clicks = 0
        total_orders = 0
        total_revenue = Decimal("0.00")
        currencies = set()

        # Profit aggregation
        total_gross_revenue = Decimal("0.00")
        total_platform_fees = Decimal("0.00")
        total_refund_loss = Decimal("0.00")
        total_ad_cost = Decimal("0.00")
        total_fulfillment_cost = Decimal("0.00")
        total_net_profit = Decimal("0.00")
        profit_entry_count = 0

        # Refund aggregation
        total_refund_count = 0
        total_order_count = 0

        # SKU breakdown
        sku_data: dict = defaultdict(lambda: {
            "inventory": 0,
            "listings": [],
            "revenue": Decimal("0.00"),
            "profit": Decimal("0.00"),
        })

        # Listing details
        listing_details = []

        for listing in listings:
            currencies.add(listing.currency)
            total_inventory += listing.inventory or 0

            if listing.product_variant_id:
                unique_skus.add(str(listing.product_variant_id))
                sku_data[str(listing.product_variant_id)]["inventory"] += listing.inventory or 0

            if listing.status == PlatformListingStatus.ACTIVE:
                active_count += 1

            # Performance metrics
            perf = await self.listing_metrics_service.get_metrics_summary(
                db=db,
                listing_id=listing.id,
                start_date=start_date,
                end_date=end_date,
            )
            total_impressions += perf.get("total_impressions", 0)
            total_clicks += perf.get("total_clicks", 0)
            total_orders += perf.get("total_orders", 0)
            revenue_val = perf.get("total_revenue")
            if revenue_val is not None:
                total_revenue += Decimal(str(revenue_val))
                if listing.product_variant_id:
                    sku_data[str(listing.product_variant_id)]["revenue"] += Decimal(str(revenue_val))

            # Profit metrics
            profit = await self.profit_service.get_listing_profitability(
                db=db,
                platform_listing_id=listing.id,
                start_date=start_date,
                end_date=end_date,
            )
            total_gross_revenue += Decimal(str(profit.get("total_gross_revenue", 0)))
            total_platform_fees += Decimal(str(profit.get("total_platform_fees", 0)))
            total_refund_loss += Decimal(str(profit.get("total_refund_loss", 0)))
            total_ad_cost += Decimal(str(profit.get("total_ad_cost", 0)))
            total_fulfillment_cost += Decimal(str(profit.get("total_fulfillment_cost", 0)))
            net_profit = Decimal(str(profit.get("total_net_profit", 0)))
            total_net_profit += net_profit
            profit_entry_count += profit.get("entry_count", 0)

            if listing.product_variant_id:
                sku_data[str(listing.product_variant_id)]["profit"] += net_profit

            # Refund metrics
            refund = await self.refund_service.get_refund_rate(
                db=db,
                platform_listing_id=listing.id,
                start_date=start_date,
                end_date=end_date,
            )
            total_refund_count += refund.get("refund_count", 0)
            total_order_count += refund.get("order_count", 0)

            # Listing detail
            listing_detail = {
                "listing_id": str(listing.id),
                "variant_id": str(listing.product_variant_id) if listing.product_variant_id else None,
                "status": listing.status.value,
                "price": float(listing.price),
                "currency": listing.currency,
                "inventory": listing.inventory,
                "performance": perf,
                "profit_snapshot": profit,
            }
            listing_details.append(listing_detail)

            if listing.product_variant_id:
                sku_data[str(listing.product_variant_id)]["listings"].append(listing_detail)

        # Currency conversion
        primary_currency = list(currencies)[0] if currencies else "USD"

        if base_currency and base_currency != primary_currency:
            try:
                total_revenue = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_revenue,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_gross_revenue = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_gross_revenue,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_platform_fees = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_platform_fees,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_refund_loss = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_refund_loss,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_ad_cost = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_ad_cost,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_fulfillment_cost = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_fulfillment_cost,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                total_net_profit = await self.currency_converter.convert_amount(
                    db=db,
                    amount=total_net_profit,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )

                # Convert SKU breakdown
                for sku_id, sku_info in sku_data.items():
                    sku_info["revenue"] = float(await self.currency_converter.convert_amount(
                        db=db,
                        amount=sku_info["revenue"],
                        from_currency=primary_currency,
                        to_currency=base_currency,
                    ))
                    sku_info["profit"] = float(await self.currency_converter.convert_amount(
                        db=db,
                        amount=sku_info["profit"],
                        from_currency=primary_currency,
                        to_currency=base_currency,
                    ))
            except ValueError:
                self.logger.warning(
                    "currency_conversion_skipped_for_platform_region",
                    platform=platform,
                    region=region,
                    from_currency=primary_currency,
                    to_currency=base_currency,
                )
                # Convert to float without currency conversion
                for sku_id, sku_info in sku_data.items():
                    sku_info["revenue"] = float(sku_info["revenue"])
                    sku_info["profit"] = float(sku_info["profit"])
        else:
            # Convert to float without currency conversion
            for sku_id, sku_info in sku_data.items():
                sku_info["revenue"] = float(sku_info["revenue"])
                sku_info["profit"] = float(sku_info["profit"])

        ctr = total_clicks / total_impressions if total_impressions > 0 else 0.0
        conversion_rate = total_orders / total_clicks if total_clicks > 0 else 0.0
        refund_rate = total_refund_count / total_order_count if total_order_count > 0 else 0.0

        # Build SKU breakdown
        sku_breakdown = [
            {
                "variant_id": sku_id,
                "listing_count": len(sku_info["listings"]),
                "inventory": sku_info["inventory"],
                "revenue": sku_info["revenue"],
                "profit": sku_info["profit"],
            }
            for sku_id, sku_info in sku_data.items()
        ]

        # Sort by profit descending
        sku_breakdown.sort(key=lambda x: x["profit"], reverse=True)

        self.logger.info(
            "platform_region_snapshot_generated",
            platform=platform,
            region=region,
            listing_count=len(listings),
            sku_count=len(unique_skus),
        )

        return {
            "platform": platform,
            "region": region,
            "summary": {
                "listing_count": len(listings),
                "active_listing_count": active_count,
                "total_inventory": total_inventory,
                "total_skus": len(unique_skus),
            },
            "performance": {
                "total_impressions": total_impressions,
                "total_clicks": total_clicks,
                "total_orders": total_orders,
                "total_revenue": float(total_revenue),
                "ctr": round(ctr, 4),
                "conversion_rate": round(conversion_rate, 4),
            },
            "profit_snapshot": {
                "total_gross_revenue": float(total_gross_revenue),
                "total_platform_fees": float(total_platform_fees),
                "total_refund_loss": float(total_refund_loss),
                "total_ad_cost": float(total_ad_cost),
                "total_fulfillment_cost": float(total_fulfillment_cost),
                "total_net_profit": float(total_net_profit),
                "entry_count": profit_entry_count,
            },
            "refund_rate": {
                "refund_rate": round(refund_rate, 4),
                "refund_count": total_refund_count,
                "order_count": total_order_count,
            },
            "sku_breakdown": sku_breakdown,
            "listings": listing_details,
            "currency": base_currency or primary_currency,
        }
