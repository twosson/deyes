"""Auto Action Engine - Core automation service.

This service implements the automatic execution layer for the Deyes system,
replacing manual recommendation analysis with automated actions.

Key Features:
- Auto-publish: Automatically publish high-quality candidates to platforms
- Auto-reprice: Adjust prices based on ROI performance
- Auto-pause: Pause low-performing listings
- Auto-asset-switch: Switch to better-performing assets
- Approval boundaries: Require human approval for high-risk actions

Design Principles:
- API-first, RPA-second: Prefer platform APIs, fallback to RPA
- Performance-driven: Base decisions on real conversion/ROI data
- Human approval fallback: High-risk actions require approval
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Optional
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.clients.aliexpress_api import AliExpressAPIClient
from app.clients.amazon_api import AmazonAPIClient
from app.clients.platform_api_base import PlatformActionResult, PlatformAPIBase
from app.clients.temu_api import TemuAPIClient
from app.core.config import get_settings
from app.core.enums import InventoryMode, PlatformListingStatus, TargetPlatform
from app.core.logging import get_logger
from app.db.models import (
    AssetPerformanceDaily,
    CandidateProduct,
    ContentAsset,
    ListingAssetAssociation,
    ListingPerformanceDaily,
    PlatformListing,
    PriceHistory,
    PricingAssessment,
    ProductMaster,
    ProductVariant,
    RiskAssessment,
    RunEvent,
)

from app.services.performance_calculator import PerformanceCalculator

logger = get_logger(__name__)


class AutoActionEngine:
    """Core automation engine for platform actions."""

    def __init__(self, db: AsyncSession):
        self.db = db
        self.settings = get_settings()

        # Platform API clients
        self._temu_client: Optional[TemuAPIClient] = None
        self._amazon_client: Optional[AmazonAPIClient] = None
        self._aliexpress_client: Optional[AliExpressAPIClient] = None

    def _get_platform_client(self, platform: TargetPlatform) -> PlatformAPIBase:
        """Get platform API client."""
        if platform == TargetPlatform.TEMU:
            if self._temu_client is None:
                self._temu_client = TemuAPIClient()
            return self._temu_client
        elif platform == TargetPlatform.AMAZON:
            if self._amazon_client is None:
                self._amazon_client = AmazonAPIClient()
            return self._amazon_client
        elif platform == TargetPlatform.ALIEXPRESS:
            if self._aliexpress_client is None:
                self._aliexpress_client = AliExpressAPIClient()
            return self._aliexpress_client
        else:
            raise ValueError(f"Unsupported platform: {platform}")

    async def close(self):
        """Close all platform clients."""
        if self._temu_client:
            await self._temu_client.close()
        if self._amazon_client:
            await self._amazon_client.close()
        if self._aliexpress_client:
            await self._aliexpress_client.close()

    def _is_variant_candidate(self, candidate: CandidateProduct) -> bool:
        """Check if candidate is a variant (not a master).

        A candidate is a variant if it has a master_sku reference in normalized_attributes.
        Masters have internal_sku set but no master_sku reference.

        Args:
            candidate: Candidate to check

        Returns:
            True if candidate is a variant, False if master or unknown
        """
        if not candidate.normalized_attributes:
            return False

        # Check for master_sku reference (indicates this is a variant)
        return "master_sku" in candidate.normalized_attributes

    async def _recompute_approval_inputs(
        self,
        candidate: CandidateProduct,
    ) -> tuple[float, int, Decimal]:
        """从 source-of-truth 重新计算审批输入指标.

        Returns:
            (recommendation_score, risk_score, margin_percentage)
        """
        # 1. 从 PricingAssessment 获取 margin_percentage
        pricing_stmt = select(PricingAssessment).where(
            PricingAssessment.candidate_product_id == candidate.id
        )
        pricing_result = await self.db.execute(pricing_stmt)
        pricing_assessment = pricing_result.scalar_one_or_none()

        margin_percentage = (
            pricing_assessment.margin_percentage
            if pricing_assessment and pricing_assessment.margin_percentage is not None
            else Decimal("0")
        )

        # 2. 从 RiskAssessment 获取 risk_score
        risk_stmt = select(RiskAssessment).where(
            RiskAssessment.candidate_product_id == candidate.id
        )
        risk_result = await self.db.execute(risk_stmt)
        risk_assessment = risk_result.scalar_one_or_none()

        risk_score = (
            risk_assessment.score
            if risk_assessment and risk_assessment.score is not None
            else 50  # 默认中等风险
        )

        # 3. 从 normalized_attributes 计算 recommendation_score
        attrs = candidate.normalized_attributes or {}
        priority_score = attrs.get("priority_score", 0.5)

        # 转换为 0-100 scale
        recommendation_score = float(priority_score) * 100.0

        # 根据竞争密度调整
        competition_density = attrs.get("competition_density", "unknown")
        if competition_density == "high":
            recommendation_score *= 0.7  # -30% 惩罚
        elif competition_density == "low":
            recommendation_score *= 1.2  # +20% 加成

        recommendation_score = min(100.0, max(0.0, recommendation_score))

        # 4. Variant-aware adjustment: if candidate is variant, apply variant penalty
        if self._is_variant_candidate(candidate):
            # Variants get -10% recommendation score penalty
            recommendation_score *= 0.9
            logger.info(
                "variant_candidate_score_adjusted",
                candidate_id=str(candidate.id),
                original_score=float(priority_score) * 100.0,
                adjusted_score=recommendation_score,
            )

        return (recommendation_score, risk_score, margin_percentage)

    def _check_approval_required(
        self,
        candidate: CandidateProduct,
        recommendation_score: float,
        risk_score: int,
        margin_percentage: Decimal,
        price: Decimal,
    ) -> tuple[bool, Optional[str]]:
        """Check if listing requires human approval.

        Returns:
            (approval_required, reason)
        """
        reasons = []

        # First-time product (no historical data)
        if self.settings.auto_publish_require_approval_first_time:
            # Check if this candidate has been published before
            # For now, assume all are first-time (can enhance later)
            reasons.append("first_time_product")

        # High risk category
        if self.settings.auto_publish_require_approval_high_risk and risk_score >= 50:
            reasons.append(f"high_risk_score_{risk_score}")

        # Price above threshold
        if price > Decimal(str(self.settings.auto_publish_require_approval_price_above)):
            reasons.append(f"high_price_{price}")

        # Margin below threshold
        # Note: margin_percentage is stored as percentage (e.g., 35.0 = 35%)
        # Config thresholds are ratios (e.g., 0.25 = 25%), so multiply by 100
        margin_threshold_pct = Decimal(str(self.settings.auto_publish_require_approval_margin_below)) * 100
        if margin_percentage < margin_threshold_pct:
            reasons.append(f"low_margin_{margin_percentage}")

        if reasons:
            return True, ", ".join(reasons)

        # Auto-execute if meets criteria
        auto_execute_margin_threshold_pct = (
            Decimal(str(self.settings.auto_publish_auto_execute_margin_above)) * 100
        )
        if (
            recommendation_score >= self.settings.auto_publish_auto_execute_score_above
            and risk_score < self.settings.auto_publish_auto_execute_risk_below
            and margin_percentage >= auto_execute_margin_threshold_pct
        ):
            return False, None

        # Default: require approval if doesn't meet auto-execute criteria
        return True, "does_not_meet_auto_execute_criteria"

    async def _resolve_variant_linkage(
        self,
        candidate_id: UUID,
    ) -> tuple[Optional[UUID], Optional[InventoryMode]]:
        """Resolve product variant linkage for a candidate.

        Returns:
            (variant_id, inventory_mode) if candidate has been converted, else (None, None)
        """
        master_stmt = select(ProductMaster).where(
            ProductMaster.candidate_product_id == candidate_id
        )
        master_result = await self.db.execute(master_stmt)
        master = master_result.scalar_one_or_none()
        if not master:
            return None, None

        variant_stmt = select(ProductVariant).where(
            ProductVariant.master_id == master.id
        ).order_by(ProductVariant.created_at)
        variant_result = await self.db.execute(variant_stmt)
        variant = variant_result.scalars().first()
        if not variant:
            return None, None

        return variant.id, variant.inventory_mode

    async def auto_publish(
        self,
        candidate_id: UUID,
        platform: TargetPlatform,
        region: str,
        price: Decimal,
        currency: str,
        recommendation_score: float,
        risk_score: int,
        margin_percentage: Decimal,
    ) -> PlatformListing:
        """Automatically publish candidate to platform.

        Note: recommendation_score, risk_score, and margin_percentage arguments are
        deprecated and ignored. These values are recomputed from source-of-truth data
        (PricingAssessment, RiskAssessment, and CandidateProduct.normalized_attributes)
        to prevent client tampering.

        Args:
            candidate_id: Candidate product ID
            platform: Target platform
            region: Target region
            price: Listing price
            currency: Currency code
            recommendation_score: Deprecated, ignored and recomputed from DB
            risk_score: Deprecated, ignored and recomputed from DB
            margin_percentage: Deprecated, ignored and recomputed from DB

        Returns:
            Created PlatformListing
        """
        # Load candidate
        candidate = await self.db.get(CandidateProduct, candidate_id)
        if not candidate:
            raise ValueError(f"Candidate {candidate_id} not found")

        # Check idempotency for publish action
        idempotency_key = f"auto_publish:{candidate_id}:{platform.value}:{region}"
        existing_stmt = select(PlatformListing).where(PlatformListing.idempotency_key == idempotency_key)
        existing_result = await self.db.execute(existing_stmt)
        existing_listing = existing_result.scalar_one_or_none()
        if existing_listing:
            logger.info(
                "operation_already_executed",
                idempotency_key=idempotency_key,
                listing_id=str(existing_listing.id),
            )
            return existing_listing

        # Recompute approval inputs from source-of-truth data
        recommendation_score, risk_score, margin_percentage = await self._recompute_approval_inputs(
            candidate=candidate,
        )

        # Resolve variant linkage if candidate has been converted
        variant_id, inventory_mode = await self._resolve_variant_linkage(candidate_id)

        # Check approval boundary
        approval_required, approval_reason = self._check_approval_required(
            candidate, recommendation_score, risk_score, margin_percentage, price
        )

        # Create listing
        listing = PlatformListing(
            id=uuid4(),
            candidate_product_id=candidate_id,
            product_variant_id=variant_id,
            inventory_mode=inventory_mode,
            platform=platform,
            region=region,
            price=price,
            currency=currency,
            inventory=0,  # Will be synced later
            status=PlatformListingStatus.DRAFT,
            idempotency_key=idempotency_key,
            approval_required=approval_required,
            approval_reason=approval_reason,
            auto_action_metadata={
                "recommendation_score": recommendation_score,
                "risk_score": risk_score,
                "margin_percentage": float(margin_percentage),
                "created_by": "auto_action_engine",
                "created_at": datetime.utcnow().isoformat(),
                "product_variant_id": str(variant_id) if variant_id else None,
                "inventory_mode": inventory_mode.value if inventory_mode else None,
            },
        )

        self.db.add(listing)

        # Record event
        event = RunEvent(
            id=uuid4(),
            strategy_run_id=candidate.strategy_run_id,
            event_type="auto_publish_initiated",
            event_payload={
                "candidate_id": str(candidate_id),
                "platform": platform.value,
                "region": region,
                "approval_required": approval_required,
                "approval_reason": approval_reason,
                "listing_id": str(listing.id),
            },
        )
        self.db.add(event)

        if approval_required:
            # Set status to pending_approval
            listing.status = PlatformListingStatus.PENDING_APPROVAL
            logger.info(
                f"Listing {listing.id} requires approval: {approval_reason}",
                extra={"listing_id": str(listing.id), "reason": approval_reason},
            )
        else:
            # Auto-execute: publish to platform
            listing.status = PlatformListingStatus.APPROVED
            await self._execute_publish(listing)

        await self.db.commit()
        await self.db.refresh(listing)

        return listing

    async def _enqueue_temu_fallback(
        self,
        listing: PlatformListing,
        candidate: Optional[CandidateProduct],
        error_message: str,
        error_type: Optional[str] = None,
    ) -> None:
        """Enqueue Temu RPA fallback task."""
        from app.workers.celery_app import celery_app

        metadata = dict(listing.auto_action_metadata or {})
        publish_attempts = dict(metadata.get("publish_attempts") or {})
        api_attempt_count = int(publish_attempts.get("api", {}).get("count", 0)) + 1
        publish_attempts["api"] = {
            "count": api_attempt_count,
            "last_attempted_at": datetime.utcnow().isoformat(),
            "last_error_message": error_message,
            "last_error_type": error_type,
        }
        metadata["publish_attempts"] = publish_attempts
        metadata["last_publish_channel"] = "api"
        metadata["last_error_stage"] = "api_publish"
        listing.auto_action_metadata = metadata
        listing.sync_error = error_message
        listing.status = PlatformListingStatus.FALLBACK_QUEUED

        # Dispatch Celery task using send_task to avoid circular import
        async_result = celery_app.send_task("tasks.temu_rpa_publish_fallback", args=[str(listing.id)])
        metadata["last_celery_task_id"] = async_result.id
        listing.auto_action_metadata = metadata

        if candidate:
            self.db.add(
                RunEvent(
                    id=uuid4(),
                    strategy_run_id=candidate.strategy_run_id,
                    event_type="temu_api_publish_failed",
                    event_payload={
                        "listing_id": str(listing.id),
                        "platform": listing.platform.value,
                        "error_message": error_message,
                        "error_type": error_type,
                    },
                )
            )
            self.db.add(
                RunEvent(
                    id=uuid4(),
                    strategy_run_id=candidate.strategy_run_id,
                    event_type="temu_rpa_fallback_queued",
                    event_payload={
                        "listing_id": str(listing.id),
                        "platform": listing.platform.value,
                        "status": PlatformListingStatus.FALLBACK_QUEUED.value,
                        "task_id": async_result.id,
                    },
                )
            )

    async def _execute_publish(self, listing: PlatformListing) -> None:
        """Execute platform publish action (internal).

        This is called after approval or for auto-execute listings.
        """
        # Check activation eligibility before publishing
        from app.services.listing_activation_service import ListingActivationService

        activation_service = ListingActivationService()
        eligibility = await activation_service.check_activation_eligibility(self.db, listing.id)

        if not eligibility.eligible:
            listing.status = PlatformListingStatus.MANUAL_INTERVENTION_REQUIRED
            listing.sync_error = f"Activation check failed: {eligibility.reason}"
            logger.warning(
                "listing_activation_check_failed",
                listing_id=str(listing.id),
                reason=eligibility.reason,
                inventory_mode=eligibility.inventory_mode.value if eligibility.inventory_mode else None,
                available_quantity=eligibility.available_quantity,
                min_inventory_required=eligibility.min_inventory_required,
            )
            return

        listing.status = PlatformListingStatus.PUBLISHING

        # Get platform client
        client = self._get_platform_client(listing.platform)

        # Build payload (simplified)
        payload = {
            "candidate_product_id": str(listing.candidate_product_id),
            "title": "Product Title",  # TODO: Get from candidate
            "price": str(listing.price),
            "currency": listing.currency,
            "region": listing.region,
        }

        candidate = await self.db.get(CandidateProduct, listing.candidate_product_id)

        try:
            # Call platform API
            result: PlatformActionResult = await client.create_product(payload)

            if result.success:
                listing.platform_listing_id = result.platform_listing_id
                listing.platform_url = result.platform_url
                listing.status = PlatformListingStatus.ACTIVE
                listing.last_synced_at = datetime.utcnow()
                logger.info(
                    f"Successfully published listing {listing.id} to {listing.platform}",
                    extra={"listing_id": str(listing.id), "platform_listing_id": result.platform_listing_id},
                )
            elif listing.platform == TargetPlatform.TEMU:
                await self._enqueue_temu_fallback(
                    listing=listing,
                    candidate=candidate,
                    error_message=result.error_message or "Temu API publish failed",
                )
            else:
                listing.status = PlatformListingStatus.REJECTED
                listing.sync_error = result.error_message
                logger.error(
                    f"Failed to publish listing {listing.id}: {result.error_message}",
                    extra={"listing_id": str(listing.id), "error": result.error_message},
                )

                if candidate:
                    event = RunEvent(
                        id=uuid4(),
                        strategy_run_id=candidate.strategy_run_id,
                        event_type="auto_publish_failed",
                        event_payload={
                            "listing_id": str(listing.id),
                            "platform": listing.platform.value,
                            "error_message": result.error_message,
                            "status": "failed",
                        },
                    )
                    self.db.add(event)

        except Exception as e:
            if listing.platform == TargetPlatform.TEMU:
                await self._enqueue_temu_fallback(
                    listing=listing,
                    candidate=candidate,
                    error_message=str(e),
                    error_type=type(e).__name__,
                )
                logger.exception(f"Exception publishing listing {listing.id}", extra={"listing_id": str(listing.id)})
                return

            listing.status = PlatformListingStatus.REJECTED
            listing.sync_error = str(e)
            logger.exception(f"Exception publishing listing {listing.id}", extra={"listing_id": str(listing.id)})

            # Record failure event
            if candidate:
                event = RunEvent(
                    id=uuid4(),
                    strategy_run_id=candidate.strategy_run_id,
                    event_type="auto_publish_failed",
                    event_payload={
                        "listing_id": str(listing.id),
                        "platform": listing.platform.value,
                        "error_message": str(e),
                        "error_type": type(e).__name__,
                        "status": "failed",
                    },
                )
                self.db.add(event)

    async def approve_listing(self, listing_id: UUID, approved_by: str) -> PlatformListing:
        """Approve a pending listing and publish it.

        Args:
            listing_id: Listing ID
            approved_by: User who approved

        Returns:
            Updated listing
        """
        listing = await self.db.get(PlatformListing, listing_id)
        if not listing:
            raise ValueError(f"Listing {listing_id} not found")

        if listing.status != PlatformListingStatus.PENDING_APPROVAL:
            raise ValueError(f"Listing {listing_id} is not pending approval (status: {listing.status})")

        # Get candidate for strategy_run_id
        candidate = await self.db.get(CandidateProduct, listing.candidate_product_id)

        listing.status = PlatformListingStatus.APPROVED
        listing.approved_at = datetime.utcnow()
        listing.approved_by = approved_by

        # Execute publish
        await self._execute_publish(listing)

        # Record event
        if candidate:
            event = RunEvent(
                id=uuid4(),
                strategy_run_id=candidate.strategy_run_id,
                event_type="listing_approved",
                event_payload={
                    "listing_id": str(listing_id),
                    "approved_by": approved_by,
                },
            )
            self.db.add(event)

        await self.db.commit()
        await self.db.refresh(listing)

        return listing

    async def reject_listing(self, listing_id: UUID, rejected_by: str, reason: str) -> PlatformListing:
        """Reject a pending listing.

        Args:
            listing_id: Listing ID
            rejected_by: User who rejected
            reason: Rejection reason

        Returns:
            Updated listing
        """
        listing = await self.db.get(PlatformListing, listing_id)
        if not listing:
            raise ValueError(f"Listing {listing_id} not found")

        if listing.status != PlatformListingStatus.PENDING_APPROVAL:
            raise ValueError(f"Listing {listing_id} is not pending approval (status: {listing.status})")

        # Get candidate for strategy_run_id
        candidate = await self.db.get(CandidateProduct, listing.candidate_product_id)

        listing.status = PlatformListingStatus.REJECTED
        listing.rejected_at = datetime.utcnow()
        listing.rejected_by = rejected_by
        listing.rejection_reason = reason

        # Record event
        if candidate:
            event = RunEvent(
                id=uuid4(),
                strategy_run_id=candidate.strategy_run_id,
                event_type="listing_rejected",
                event_payload={
                    "listing_id": str(listing_id),
                    "rejected_by": rejected_by,
                    "reason": reason,
                },
            )
            self.db.add(event)

        await self.db.commit()
        await self.db.refresh(listing)

        return listing

    async def auto_reprice(self, listing_id: UUID) -> Optional[PriceHistory]:
        """Automatically adjust listing price based on ROI.

        Args:
            listing_id: Listing ID

        Returns:
            PriceHistory record if price was changed, None otherwise
        """
        if not self.settings.auto_reprice_enable:
            logger.info("Auto-reprice is disabled")
            return None

        listing = await self.db.get(PlatformListing, listing_id)
        if not listing:
            raise ValueError(f"Listing {listing_id} not found")

        if listing.status != PlatformListingStatus.ACTIVE:
            logger.info(f"Listing {listing_id} is not active, skipping reprice")
            return None

        # Get aggregated 7-day metrics using shared calculator
        metrics = await PerformanceCalculator.get_listing_7day_metrics(
            self.db,
            listing_id,
            lookback_days=self.settings.auto_reprice_lookback_days,
        )

        if not metrics or metrics["data_points"] == 0:
            logger.info(f"No performance data for listing {listing_id}, skipping reprice")
            return None

        # Use ROI from calculator
        avg_roi = metrics["roi"]

        # Determine price adjustment
        target_roi = Decimal(str(self.settings.auto_reprice_target_roi))
        low_threshold = Decimal(str(self.settings.auto_reprice_low_roi_threshold))
        high_threshold = Decimal(str(self.settings.auto_reprice_high_roi_threshold))

        new_price = None
        reason = None

        if avg_roi < low_threshold:
            # ROI too low, decrease price
            decrease_pct = Decimal(str(self.settings.auto_reprice_decrease_percentage))
            new_price = listing.price * (Decimal(1) - decrease_pct)
            reason = f"low_roi_{avg_roi:.2f}"
        elif avg_roi > high_threshold:
            # ROI too high, increase price
            increase_pct = Decimal(str(self.settings.auto_reprice_increase_percentage))
            new_price = listing.price * (Decimal(1) + increase_pct)
            reason = f"high_roi_{avg_roi:.2f}"

        if new_price is None:
            logger.info(f"ROI {avg_roi:.2f} within target range, no reprice needed")
            return None

        # Check if change exceeds max threshold (requires approval)
        price_change_pct = abs(new_price - listing.price) / listing.price
        max_change = Decimal(str(self.settings.auto_reprice_max_change_percentage))

        if price_change_pct > max_change:
            logger.warning(
                f"Price change {price_change_pct:.2%} exceeds max {max_change:.2%}, requires approval",
                extra={"listing_id": str(listing_id), "old_price": str(listing.price), "new_price": str(new_price)},
            )
            # TODO: Create approval request
            return None

        # Execute price update
        old_price = listing.price

        # Call platform API
        client = self._get_platform_client(listing.platform)
        result = await client.update_price(listing.platform_listing_id, new_price, listing.currency)

        if not result.success:
            logger.error(f"Failed to update price on platform: {result.error_message}")

            # Record failure event
            candidate = await self.db.get(CandidateProduct, listing.candidate_product_id)
            if candidate:
                event = RunEvent(
                    id=uuid4(),
                    strategy_run_id=candidate.strategy_run_id,
                    event_type="auto_reprice_failed",
                    event_payload={
                        "listing_id": str(listing_id),
                        "old_price": str(old_price),
                        "new_price": str(new_price),
                        "error_message": result.error_message,
                        "status": "failed",
                    },
                )
                self.db.add(event)
                await self.db.commit()
            return None

        listing.price = new_price

        # Get candidate for strategy_run_id
        candidate = await self.db.get(CandidateProduct, listing.candidate_product_id)

        # Record price history
        price_history = PriceHistory(
            id=uuid4(),
            listing_id=listing_id,
            old_price=old_price,
            new_price=new_price,
            reason=reason,
            changed_by="auto_action_engine",
            changed_at=datetime.utcnow(),
        )
        self.db.add(price_history)

        # Record event
        if candidate:
            event = RunEvent(
                id=uuid4(),
                strategy_run_id=candidate.strategy_run_id,
                event_type="auto_reprice",
                event_payload={
                    "listing_id": str(listing_id),
                    "old_price": str(old_price),
                    "new_price": str(new_price),
                    "avg_roi": str(avg_roi),
                    "reason": reason,
                },
            )
            self.db.add(event)

        listing.last_auto_action_at = datetime.utcnow()
        await self.db.commit()
        await self.db.refresh(price_history)

        logger.info(
            f"Auto-repriced listing {listing_id}: {old_price} -> {new_price} (ROI: {avg_roi:.2f})",
            extra={"listing_id": str(listing_id), "old_price": str(old_price), "new_price": str(new_price)},
        )

        return price_history

    async def auto_pause(self, listing_id: UUID) -> bool:
        """Automatically pause low-performing listing.

        Args:
            listing_id: Listing ID

        Returns:
            True if paused, False otherwise
        """
        if not self.settings.auto_pause_enable:
            logger.info("Auto-pause is disabled")
            return False

        listing = await self.db.get(PlatformListing, listing_id)
        if not listing:
            raise ValueError(f"Listing {listing_id} not found")

        if listing.status != PlatformListingStatus.ACTIVE:
            logger.info(f"Listing {listing_id} is not active, skipping pause")
            return False

        # Get aggregated 7-day metrics using shared calculator
        metrics = await PerformanceCalculator.get_listing_7day_metrics(
            self.db,
            listing_id,
            lookback_days=self.settings.auto_pause_lookback_days,
        )

        if not metrics or metrics["data_points"] < self.settings.auto_pause_min_data_points:
            logger.info(f"Insufficient data for listing {listing_id}, skipping pause")
            return False

        # Use ROI from calculator
        avg_roi = metrics["roi"]
        roi_threshold = Decimal(str(self.settings.auto_pause_roi_threshold))

        if avg_roi >= roi_threshold:
            logger.info(f"ROI {avg_roi:.2f} above threshold {roi_threshold}, no pause needed")
            return False

        # Call platform API
        client = self._get_platform_client(listing.platform)
        result = await client.pause_product(listing.platform_listing_id)

        if not result.success:
            logger.error(f"Failed to pause on platform: {result.error_message}")

            # Record failure event
            candidate = await self.db.get(CandidateProduct, listing.candidate_product_id)
            if candidate:
                event = RunEvent(
                    id=uuid4(),
                    strategy_run_id=candidate.strategy_run_id,
                    event_type="auto_pause_failed",
                    event_payload={
                        "listing_id": str(listing_id),
                        "avg_roi": str(avg_roi),
                        "threshold": str(roi_threshold),
                        "error_message": result.error_message,
                        "status": "failed",
                    },
                )
                self.db.add(event)
                await self.db.commit()
            return False

        listing.status = PlatformListingStatus.PAUSED

        # Get candidate for strategy_run_id
        candidate = await self.db.get(CandidateProduct, listing.candidate_product_id)

        # Record event
        if candidate:
            event = RunEvent(
                id=uuid4(),
                strategy_run_id=candidate.strategy_run_id,
                event_type="auto_pause",
                event_payload={
                    "listing_id": str(listing_id),
                    "avg_roi": str(avg_roi),
                    "threshold": str(roi_threshold),
                    "reason": "low_roi_7days",
                },
            )
            self.db.add(event)

        listing.last_auto_action_at = datetime.utcnow()
        await self.db.commit()

        logger.info(
            f"Auto-paused listing {listing_id} due to low ROI: {avg_roi:.2f}",
            extra={"listing_id": str(listing_id), "avg_roi": str(avg_roi)},
        )

        return True

    async def auto_asset_switch(self, listing_id: UUID) -> bool:
        """Automatically switch to better-performing asset.

        Args:
            listing_id: Listing ID

        Returns:
            True if asset was switched, False otherwise
        """
        try:
            if not self.settings.auto_asset_switch_enable:
                logger.info("Auto-asset-switch is disabled")
                return False

            listing = await self.db.get(PlatformListing, listing_id)
            if not listing:
                raise ValueError(f"Listing {listing_id} not found")

            if listing.status != PlatformListingStatus.ACTIVE:
                logger.info(f"Listing {listing_id} is not active, skipping asset switch")
                return False

            # Find current main asset association
            current_assoc_stmt = select(ListingAssetAssociation).where(
                ListingAssetAssociation.listing_id == listing_id,
                ListingAssetAssociation.is_main.is_(True),
            )
            current_assoc_result = await self.db.execute(current_assoc_stmt)
            current_assoc = current_assoc_result.scalar_one_or_none()
            if current_assoc is None:
                logger.info(f"No main asset association for listing {listing_id}")
                return False

            current_asset = await self.db.get(ContentAsset, current_assoc.asset_id)
            if current_asset is None:
                logger.info(f"Current main asset not found for listing {listing_id}")
                return False

            # Get candidate for related assets and event logging
            candidate = await self.db.get(CandidateProduct, listing.candidate_product_id)
            if candidate is None:
                logger.info(f"Candidate not found for listing {listing_id}")
                return False

            lookback_date = date.today() - timedelta(days=self.settings.auto_asset_switch_lookback_days)

            # Current asset CTR over lookback window
            current_perf_stmt = select(AssetPerformanceDaily).where(
                AssetPerformanceDaily.asset_id == current_asset.id,
                AssetPerformanceDaily.listing_id == listing_id,
                AssetPerformanceDaily.metric_date >= lookback_date,
            )
            current_perf_result = await self.db.execute(current_perf_stmt)
            current_perf_rows = current_perf_result.scalars().all()

            current_clicks = sum(row.clicks for row in current_perf_rows)
            current_impressions = sum(row.impressions for row in current_perf_rows)
            current_ctr = (current_clicks / current_impressions) if current_impressions > 0 else 0.0

            # Approximate platform average CTR from listing performance
            listing_perf_stmt = select(ListingPerformanceDaily).where(
                ListingPerformanceDaily.listing_id == listing_id,
                ListingPerformanceDaily.metric_date >= lookback_date,
            )
            listing_perf_result = await self.db.execute(listing_perf_stmt)
            listing_perf_rows = listing_perf_result.scalars().all()
            total_listing_clicks = sum(row.clicks for row in listing_perf_rows)
            total_listing_impressions = sum(row.impressions for row in listing_perf_rows)
            platform_avg_ctr = (
                total_listing_clicks / total_listing_impressions if total_listing_impressions > 0 else current_ctr
            )

            threshold = self.settings.auto_asset_switch_ctr_threshold
            if platform_avg_ctr > 0 and current_ctr >= platform_avg_ctr * threshold:
                logger.info(
                    f"Current asset CTR {current_ctr:.4f} is within threshold for listing {listing_id}",
                    extra={"listing_id": str(listing_id), "current_ctr": current_ctr},
                )
                return False

            # Candidate alternative assets: same candidate, not archived, not current asset
            alt_stmt = select(ContentAsset).where(
                ContentAsset.candidate_product_id == listing.candidate_product_id,
                ContentAsset.id != current_asset.id,
                ContentAsset.archived.is_(False),
            )
            alt_result = await self.db.execute(alt_stmt)
            alternatives = alt_result.scalars().all()
            if not alternatives:
                logger.info(f"No alternative assets found for listing {listing_id}")
                return False

            # Pick best alternative by AI quality score, fallback to version recency
            def _score(asset: ContentAsset) -> tuple[float, int]:
                quality = float(asset.ai_quality_score) if asset.ai_quality_score is not None else 0.0
                return (quality, asset.version or 0)

            best_asset = max(alternatives, key=_score)
            if best_asset.id == current_asset.id:
                return False

            # Switch main association
            current_assoc.is_main = False

            best_assoc_stmt = select(ListingAssetAssociation).where(
                ListingAssetAssociation.listing_id == listing_id,
                ListingAssetAssociation.asset_id == best_asset.id,
            )
            best_assoc_result = await self.db.execute(best_assoc_stmt)
            best_assoc = best_assoc_result.scalar_one_or_none()
            if best_assoc is None:
                best_assoc = ListingAssetAssociation(
                    listing_id=listing_id,
                    asset_id=best_asset.id,
                    display_order=0,
                    is_main=True,
                )
                self.db.add(best_assoc)
            else:
                best_assoc.is_main = True

            event = RunEvent(
                id=uuid4(),
                strategy_run_id=candidate.strategy_run_id,
                event_type="auto_asset_switch",
                event_payload={
                    "listing_id": str(listing_id),
                    "from_asset_id": str(current_asset.id),
                    "to_asset_id": str(best_asset.id),
                    "current_ctr": current_ctr,
                    "platform_avg_ctr": platform_avg_ctr,
                },
            )
            self.db.add(event)

            listing.last_auto_action_at = datetime.utcnow()
            await self.db.commit()

            logger.info(
                f"Auto-switched asset for listing {listing_id}: {current_asset.id} -> {best_asset.id}",
                extra={"listing_id": str(listing_id), "from_asset": str(current_asset.id), "to_asset": str(best_asset.id)},
            )
            return True

        except Exception as e:
            logger.exception("auto_asset_switch_failed", listing_id=str(listing_id), error=str(e))
            await self.db.rollback()

            # Record failure event
            listing = await self.db.get(PlatformListing, listing_id)
            if listing:
                candidate = await self.db.get(CandidateProduct, listing.candidate_product_id)
                if candidate:
                    event = RunEvent(
                        id=uuid4(),
                        strategy_run_id=candidate.strategy_run_id,
                        event_type="auto_asset_switch_failed",
                        event_payload={
                            "listing_id": str(listing_id),
                            "error_message": str(e),
                            "error_type": type(e).__name__,
                            "status": "failed",
                        },
                    )
                    self.db.add(event)
                    await self.db.commit()
            return False
