"""Celery tasks for auto action engine.

Automated tasks for:
- Daily auto-reprice based on ROI
- Daily auto-pause for low-performing listings
- Daily auto-asset-switch for low CTR assets
- Temu RPA publish fallback
"""
from uuid import UUID

from sqlalchemy import select

from app.core.enums import PlatformListingStatus, TargetPlatform
from app.core.logging import get_logger
from app.db.models import CandidateProduct, PlatformListing, RunEvent
from app.db.session import get_db_context
from app.services.auto_action_engine import AutoActionEngine
from app.services.rpa_publisher import RPAPublisher, RPAResult
from app.workers import run_async
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

# System-level placeholder for strategy_run_id
SYSTEM_STRATEGY_RUN_ID = UUID("00000000-0000-0000-0000-000000000000")


async def _run_auto_reprice_all() -> dict:
    """Run auto-reprice for all active listings."""
    async with get_db_context() as db:
        # Get all active listings
        stmt = select(PlatformListing).where(PlatformListing.status == PlatformListingStatus.ACTIVE)
        result = await db.execute(stmt)
        listings = result.scalars().all()

        engine = AutoActionEngine(db)
        try:
            repriced_count = 0
            error_count = 0

            for listing in listings:
                try:
                    price_history = await engine.auto_reprice(listing.id)
                    if price_history:
                        repriced_count += 1
                except Exception as e:
                    logger.error(
                        "auto_reprice_failed",
                        listing_id=str(listing.id),
                        error=str(e),
                    )
                    error_count += 1

            return {
                "success": True,
                "total_listings": len(listings),
                "repriced_count": repriced_count,
                "error_count": error_count,
            }
        finally:
            await engine.close()


async def _run_auto_pause_all() -> dict:
    """Run auto-pause for all active listings."""
    async with get_db_context() as db:
        # Get all active listings
        stmt = select(PlatformListing).where(PlatformListing.status == PlatformListingStatus.ACTIVE)
        result = await db.execute(stmt)
        listings = result.scalars().all()

        engine = AutoActionEngine(db)
        try:
            paused_count = 0
            error_count = 0

            for listing in listings:
                try:
                    paused = await engine.auto_pause(listing.id)
                    if paused:
                        paused_count += 1
                except Exception as e:
                    logger.error(
                        "auto_pause_failed",
                        listing_id=str(listing.id),
                        error=str(e),
                    )
                    error_count += 1

            return {
                "success": True,
                "total_listings": len(listings),
                "paused_count": paused_count,
                "error_count": error_count,
            }
        finally:
            await engine.close()


async def _run_auto_asset_switch_all() -> dict:
    """Run auto-asset-switch for all active listings."""
    async with get_db_context() as db:
        # Get all active listings
        stmt = select(PlatformListing).where(PlatformListing.status == PlatformListingStatus.ACTIVE)
        result = await db.execute(stmt)
        listings = result.scalars().all()

        engine = AutoActionEngine(db)
        try:
            switched_count = 0
            error_count = 0

            for listing in listings:
                try:
                    switched = await engine.auto_asset_switch(listing.id)
                    if switched:
                        switched_count += 1
                except Exception as e:
                    logger.error(
                        "auto_asset_switch_failed",
                        listing_id=str(listing.id),
                        error=str(e),
                    )
                    error_count += 1

            return {
                "success": True,
                "total_listings": len(listings),
                "switched_count": switched_count,
                "error_count": error_count,
            }
        finally:
            await engine.close()


@celery_app.task(
    name="tasks.auto_reprice_all_listings",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 300},
    retry_backoff=True,
    retry_backoff_max=1800,
    retry_jitter=True,
)
def auto_reprice_all_listings(self) -> dict:
    """Daily task: Auto-reprice all active listings based on ROI."""
    task_id = self.request.id
    logger.info("task_started", task_id=task_id, task_name="auto_reprice_all_listings")
    try:
        result = run_async(_run_auto_reprice_all())
        logger.info(
            "task_completed",
            task_id=task_id,
            task_name="auto_reprice_all_listings",
            result=result,
        )
        return result
    except Exception:
        logger.exception("task_failed", task_id=task_id, task_name="auto_reprice_all_listings")
        raise


@celery_app.task(
    name="tasks.auto_pause_all_listings",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 300},
    retry_backoff=True,
    retry_backoff_max=1800,
    retry_jitter=True,
)
def auto_pause_all_listings(self) -> dict:
    """Daily task: Auto-pause low-performing listings."""
    task_id = self.request.id
    logger.info("task_started", task_id=task_id, task_name="auto_pause_all_listings")
    try:
        result = run_async(_run_auto_pause_all())
        logger.info(
            "task_completed",
            task_id=task_id,
            task_name="auto_pause_all_listings",
            result=result,
        )
        return result
    except Exception:
        logger.exception("task_failed", task_id=task_id, task_name="auto_pause_all_listings")
        raise


@celery_app.task(
    name="tasks.auto_asset_switch_all_listings",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 300},
    retry_backoff=True,
    retry_backoff_max=1800,
    retry_jitter=True,
)
def auto_asset_switch_all_listings(self) -> dict:
    """Daily task: Auto-switch assets for low CTR listings."""
    task_id = self.request.id
    logger.info("task_started", task_id=task_id, task_name="auto_asset_switch_all_listings")
    try:
        result = run_async(_run_auto_asset_switch_all())
        logger.info(
            "task_completed",
            task_id=task_id,
            task_name="auto_asset_switch_all_listings",
            result=result,
        )
        return result
    except Exception:
        logger.exception("task_failed", task_id=task_id, task_name="auto_asset_switch_all_listings")
        raise


async def _run_temu_rpa_fallback(listing_id: UUID) -> dict:
    """Run Temu RPA fallback for a single listing."""
    from datetime import datetime
    from uuid import uuid4

    async with get_db_context() as db:
        listing = await db.get(PlatformListing, listing_id)
        if not listing:
            logger.error("temu_rpa_fallback_listing_not_found", listing_id=str(listing_id))
            return {"success": False, "error": "Listing not found"}

        if listing.status == PlatformListingStatus.ACTIVE:
            logger.info("temu_rpa_fallback_already_active", listing_id=str(listing_id))
            return {"success": True, "status": "already_active"}

        candidate = await db.get(CandidateProduct, listing.candidate_product_id)
        if not candidate:
            logger.error("temu_rpa_fallback_candidate_not_found", listing_id=str(listing_id))
            return {"success": False, "error": "Candidate not found"}

        if candidate:
            event = RunEvent(
                id=uuid4(),
                strategy_run_id=candidate.strategy_run_id,
                event_type="temu_rpa_fallback_started",
                event_payload={
                    "listing_id": str(listing_id),
                    "platform": listing.platform.value,
                },
            )
            db.add(event)

        if listing.platform != TargetPlatform.TEMU:
            logger.warning("temu_rpa_fallback_wrong_platform", listing_id=str(listing_id), platform=listing.platform.value)
            return {"success": False, "error": "Temu fallback only supports Temu listings"}

        rpa_publisher = RPAPublisher()
        payload = {
            "candidate_product_id": str(listing.candidate_product_id),
            "title": candidate.title,
            "price": str(listing.price) if listing.price is not None else None,
            "currency": listing.currency,
            "inventory": listing.inventory,
            "region": listing.region,
            "description": (candidate.raw_payload or {}).get("description"),
            "main_image_url": candidate.main_image_url,
            "category": (listing.platform_data or {}).get("category") or candidate.category,
            "leaf_category": (listing.platform_data or {}).get("leaf_category"),
            "core_attributes": (listing.platform_data or {}).get("core_attributes"),
            "logistics_template": (listing.platform_data or {}).get("logistics_template"),
        }
        missing_fields = rpa_publisher.get_missing_prerequisites(TargetPlatform.TEMU, payload)

        if missing_fields:
            listing.status = PlatformListingStatus.MANUAL_INTERVENTION_REQUIRED
            listing.sync_error = "Temu RPA prerequisites missing"
            metadata = dict(listing.auto_action_metadata or {})
            metadata["missing_fields"] = missing_fields
            metadata["manual_intervention_reason"] = "Temu RPA prerequisites missing"
            metadata["last_publish_channel"] = "rpa"
            metadata["last_error_stage"] = "rpa_prerequisite_check"
            listing.auto_action_metadata = metadata

            if candidate:
                event = RunEvent(
                    id=uuid4(),
                    strategy_run_id=candidate.strategy_run_id,
                    event_type="temu_rpa_prerequisite_missing",
                    event_payload={
                        "listing_id": str(listing_id),
                        "missing_fields": missing_fields,
                    },
                )
                db.add(event)

            await db.commit()
            logger.warning("temu_rpa_fallback_missing_prerequisites", listing_id=str(listing_id), missing_fields=missing_fields)
            return {"success": False, "status": "missing_prerequisites", "missing_fields": missing_fields}

        listing.status = PlatformListingStatus.FALLBACK_RUNNING
        metadata = dict(listing.auto_action_metadata or {})
        metadata["last_publish_channel"] = "rpa"
        metadata["last_error_stage"] = None
        listing.auto_action_metadata = metadata
        await db.commit()

        rpa_result: RPAResult = await rpa_publisher.publish(TargetPlatform.TEMU, payload)

        if rpa_result.success:
            listing.platform_listing_id = rpa_result.platform_listing_id
            listing.platform_url = rpa_result.platform_url
            listing.status = PlatformListingStatus.ACTIVE
            listing.last_synced_at = datetime.utcnow()
            metadata = dict(listing.auto_action_metadata or {})
            publish_attempts = dict(metadata.get("publish_attempts") or {})
            rpa_attempt_count = int(publish_attempts.get("rpa", {}).get("count", 0)) + 1
            publish_attempts["rpa"] = {
                "count": rpa_attempt_count,
                "last_attempted_at": datetime.utcnow().isoformat(),
                "status": "succeeded",
            }
            metadata["publish_attempts"] = publish_attempts
            metadata["last_publish_channel"] = "rpa"
            metadata["last_error_stage"] = None
            metadata["manual_intervention_reason"] = None
            listing.auto_action_metadata = metadata

            if candidate:
                event = RunEvent(
                    id=uuid4(),
                    strategy_run_id=candidate.strategy_run_id,
                    event_type="temu_rpa_publish_succeeded",
                    event_payload={
                        "listing_id": str(listing_id),
                        "platform_listing_id": rpa_result.platform_listing_id,
                        "platform_url": rpa_result.platform_url,
                    },
                )
                db.add(event)

            await db.commit()
            logger.info("temu_rpa_fallback_succeeded", listing_id=str(listing_id), platform_listing_id=rpa_result.platform_listing_id)
            return {"success": True, "status": "active", "platform_listing_id": rpa_result.platform_listing_id}

        elif rpa_result.requires_manual_intervention:
            listing.status = PlatformListingStatus.MANUAL_INTERVENTION_REQUIRED
            manual_reason = rpa_result.manual_intervention_reason or rpa_result.error_message
            listing.sync_error = manual_reason
            metadata = dict(listing.auto_action_metadata or {})
            publish_attempts = dict(metadata.get("publish_attempts") or {})
            rpa_attempt_count = int(publish_attempts.get("rpa", {}).get("count", 0)) + 1
            publish_attempts["rpa"] = {
                "count": rpa_attempt_count,
                "last_attempted_at": datetime.utcnow().isoformat(),
                "status": "manual_intervention_required",
                "error_code": rpa_result.error_code,
            }
            metadata["publish_attempts"] = publish_attempts
            metadata["manual_intervention_reason"] = manual_reason
            metadata["last_publish_channel"] = "rpa"
            metadata["last_error_stage"] = "rpa_manual_intervention"
            if rpa_result.missing_fields:
                metadata["missing_fields"] = rpa_result.missing_fields
            listing.auto_action_metadata = metadata

            if candidate:
                event = RunEvent(
                    id=uuid4(),
                    strategy_run_id=candidate.strategy_run_id,
                    event_type="temu_manual_intervention_required",
                    event_payload={
                        "listing_id": str(listing_id),
                        "reason": manual_reason,
                    },
                )
                db.add(event)

            await db.commit()
            logger.warning("temu_rpa_fallback_requires_manual_intervention", listing_id=str(listing_id), reason=manual_reason)
            return {"success": False, "status": "manual_intervention_required", "reason": manual_reason}

        else:
            listing.status = PlatformListingStatus.REJECTED
            listing.sync_error = rpa_result.error_message
            metadata = dict(listing.auto_action_metadata or {})
            publish_attempts = dict(metadata.get("publish_attempts") or {})
            rpa_attempt_count = int(publish_attempts.get("rpa", {}).get("count", 0)) + 1
            publish_attempts["rpa"] = {
                "count": rpa_attempt_count,
                "last_attempted_at": datetime.utcnow().isoformat(),
                "status": "failed",
                "error_code": rpa_result.error_code,
            }
            metadata["publish_attempts"] = publish_attempts
            metadata["last_publish_channel"] = "rpa"
            metadata["last_error_stage"] = "rpa_publish"
            listing.auto_action_metadata = metadata

            if candidate:
                event = RunEvent(
                    id=uuid4(),
                    strategy_run_id=candidate.strategy_run_id,
                    event_type="temu_rpa_publish_failed",
                    event_payload={
                        "listing_id": str(listing_id),
                        "error_message": rpa_result.error_message,
                    },
                )
                db.add(event)

            await db.commit()
            logger.error("temu_rpa_fallback_failed", listing_id=str(listing_id), error=rpa_result.error_message)
            return {"success": False, "status": "rejected", "error": rpa_result.error_message}


@celery_app.task(
    name="tasks.temu_rpa_publish_fallback",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 2, "countdown": 60},
    retry_backoff=True,
    retry_backoff_max=300,
    retry_jitter=True,
)
def temu_rpa_publish_fallback(self, listing_id: str) -> dict:
    """Temu RPA publish fallback task."""
    task_id = self.request.id
    logger.info("task_started", task_id=task_id, task_name="temu_rpa_publish_fallback", listing_id=listing_id)
    try:
        result = run_async(_run_temu_rpa_fallback(UUID(listing_id)))
        logger.info(
            "task_completed",
            task_id=task_id,
            task_name="temu_rpa_publish_fallback",
            listing_id=listing_id,
            result=result,
        )
        return result
    except Exception:
        logger.exception("task_failed", task_id=task_id, task_name="temu_rpa_publish_fallback", listing_id=listing_id)
        raise
