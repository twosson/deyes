"""Listing activation eligibility service.

Determines whether a listing can be activated based on inventory mode and platform requirements.
"""
from dataclasses import dataclass
from typing import Optional
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import InventoryMode, PlatformListingStatus, TargetPlatform
from app.core.logging import get_logger
from app.db.models import InventoryLevel, PlatformListing, ProductVariant, SupplierOffer

logger = get_logger(__name__)


# Platform-specific minimum inventory thresholds for stock_first mode
PLATFORM_INVENTORY_THRESHOLDS = {
    TargetPlatform.TEMU: 10,
    TargetPlatform.AMAZON: 50,
    TargetPlatform.ALIEXPRESS: 20,
    TargetPlatform.OZON: 30,
    TargetPlatform.WILDBERRIES: 25,
    TargetPlatform.SHOPEE: 15,
    TargetPlatform.MERCADO_LIBRE: 20,
    TargetPlatform.TIKTOK_SHOP: 10,
    TargetPlatform.EBAY: 5,
    TargetPlatform.WALMART: 40,
    TargetPlatform.RAKUTEN: 20,
    TargetPlatform.ALLEGRO: 15,
}


@dataclass
class ActivationEligibility:
    """Result of activation eligibility check."""

    eligible: bool
    reason: Optional[str]
    inventory_mode: Optional[InventoryMode]
    available_quantity: int
    min_inventory_required: int
    has_supplier_offer: bool


class ListingActivationService:
    """Service for checking listing activation eligibility."""

    def __init__(self):
        self.logger = get_logger(__name__)

    async def check_activation_eligibility(
        self,
        db: AsyncSession,
        listing_id: UUID,
    ) -> ActivationEligibility:
        """Check if a listing is eligible for activation.

        Args:
            db: Database session
            listing_id: Listing ID to check

        Returns:
            ActivationEligibility with eligibility status and details
        """
        # Get listing
        listing = await db.get(PlatformListing, listing_id)
        if not listing:
            return ActivationEligibility(
                eligible=False,
                reason="listing_not_found",
                inventory_mode=None,
                available_quantity=0,
                min_inventory_required=0,
                has_supplier_offer=False,
            )

        # Check variant linkage
        if not listing.product_variant_id:
            return ActivationEligibility(
                eligible=False,
                reason="no_variant_linkage",
                inventory_mode=None,
                available_quantity=0,
                min_inventory_required=0,
                has_supplier_offer=False,
            )

        # Get variant
        variant = await db.get(ProductVariant, listing.product_variant_id)
        if not variant:
            return ActivationEligibility(
                eligible=False,
                reason="variant_not_found",
                inventory_mode=None,
                available_quantity=0,
                min_inventory_required=0,
                has_supplier_offer=False,
            )

        # Determine inventory_mode: prioritize listing mode, fall back to variant mode
        inventory_mode = listing.inventory_mode or variant.inventory_mode
        if not inventory_mode:
            return ActivationEligibility(
                eligible=False,
                reason="unknown_inventory_mode",
                inventory_mode=None,
                available_quantity=0,
                min_inventory_required=0,
                has_supplier_offer=False,
            )

        # Get inventory level
        level_stmt = select(InventoryLevel).where(InventoryLevel.variant_id == variant.id)
        level_result = await db.execute(level_stmt)
        level = level_result.scalar_one_or_none()
        available_quantity = level.available_quantity if level else 0

        # Check supplier offer
        offer_stmt = select(SupplierOffer).where(SupplierOffer.variant_id == variant.id)
        offer_result = await db.execute(offer_stmt)
        has_supplier_offer = offer_result.scalar_one_or_none() is not None

        # Apply activation rules based on inventory mode
        if inventory_mode == InventoryMode.PRE_ORDER:
            # Pre-order mode: requires supplier offer, allows 0 inventory
            eligible = has_supplier_offer
            reason = None if eligible else "no_supplier_offer"
            min_inventory_required = 0

        elif inventory_mode == InventoryMode.STOCK_FIRST:
            # Stock-first mode: requires inventory >= platform threshold
            min_inventory_required = PLATFORM_INVENTORY_THRESHOLDS.get(listing.platform, 10)
            eligible = available_quantity >= min_inventory_required
            reason = None if eligible else f"insufficient_inventory (need {min_inventory_required}, have {available_quantity})"

        else:
            # Unknown mode
            eligible = False
            reason = f"unsupported_inventory_mode: {inventory_mode}"
            min_inventory_required = 0

        return ActivationEligibility(
            eligible=eligible,
            reason=reason,
            inventory_mode=inventory_mode,
            available_quantity=available_quantity,
            min_inventory_required=min_inventory_required,
            has_supplier_offer=has_supplier_offer,
        )

    async def activate_listing_if_eligible(
        self,
        db: AsyncSession,
        listing_id: UUID,
    ) -> tuple[bool, Optional[str]]:
        """Activate listing if eligible.

        Args:
            db: Database session
            listing_id: Listing ID to activate

        Returns:
            (activated, reason) tuple
        """
        eligibility = await self.check_activation_eligibility(db, listing_id)

        if not eligibility.eligible:
            self.logger.warning(
                "listing_activation_failed",
                listing_id=str(listing_id),
                reason=eligibility.reason,
                inventory_mode=eligibility.inventory_mode.value if eligibility.inventory_mode else None,
                available_quantity=eligibility.available_quantity,
                min_inventory_required=eligibility.min_inventory_required,
            )
            return False, eligibility.reason

        # Update listing status to ACTIVE
        listing = await db.get(PlatformListing, listing_id)
        if listing:
            listing.status = PlatformListingStatus.ACTIVE
            await db.commit()

            self.logger.info(
                "listing_activated",
                listing_id=str(listing_id),
                inventory_mode=eligibility.inventory_mode.value,
                available_quantity=eligibility.available_quantity,
            )

        return True, None
