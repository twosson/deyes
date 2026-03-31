"""Celery tasks for performance data collection.

Automated tasks for:
- Daily listing performance metrics collection from platform APIs
- Daily asset performance metrics collection (stub for future)
"""
from datetime import date, timedelta
from uuid import UUID

from sqlalchemy import select

from app.clients.aliexpress_api import AliExpressAPIClient
from app.clients.amazon_api import AmazonAPIClient
from app.clients.platform_api_base import PlatformMetrics
from app.clients.temu_api import TemuAPIClient
from app.core.enums import PlatformListingStatus, TargetPlatform
from app.core.logging import get_logger
from app.db.models import PlatformListing
from app.db.session import get_db_context
from app.services.listing_metrics_service import ListingMetricsService
from app.workers import run_async
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


def _get_platform_client(platform: TargetPlatform):
    """Get platform API client for metrics collection."""
    if platform == TargetPlatform.TEMU:
        return TemuAPIClient()
    elif platform == TargetPlatform.AMAZON:
        return AmazonAPIClient()
    elif platform == TargetPlatform.ALIEXPRESS:
        return AliExpressAPIClient()
    else:
        raise ValueError(f"Unsupported platform: {platform}")


async def _collect_listing_performance_daily() -> dict:
    """Collect yesterday's performance metrics for all active/paused listings."""
    yesterday = date.today() - timedelta(days=1)

    async with get_db_context() as db:
        # Get all active and paused listings
        stmt = select(PlatformListing).where(
            PlatformListing.status.in_([
                PlatformListingStatus.ACTIVE,
                PlatformListingStatus.PAUSED,
            ])
        )
        result = await db.execute(stmt)
        listings = result.scalars().all()

        metrics_service = ListingMetricsService()
        collected_count = 0
        error_count = 0
        skipped_count = 0

        for listing in listings:
            if not listing.platform_listing_id:
                logger.warning(
                    "listing_missing_platform_id",
                    listing_id=str(listing.id),
                    platform=listing.platform.value,
                )
                skipped_count += 1
                continue

            try:
                client = _get_platform_client(listing.platform)
                metrics: PlatformMetrics = await client.get_listing_metrics(
                    platform_listing_id=listing.platform_listing_id,
                    metric_date=yesterday,
                )

                await metrics_service.record_daily_metrics(
                    db,
                    listing_id=listing.id,
                    metric_date=yesterday,
                    impressions=metrics.impressions,
                    clicks=metrics.clicks,
                    orders=metrics.orders,
                    units_sold=metrics.units_sold,
                    revenue=metrics.revenue,
                    ad_spend=metrics.ad_spend,
                    returns_count=metrics.returns_count,
                    refund_amount=metrics.refund_amount,
                )

                collected_count += 1
                logger.info(
                    "listing_metrics_collected",
                    listing_id=str(listing.id),
                    platform=listing.platform.value,
                    metric_date=str(yesterday),
                    impressions=metrics.impressions,
                    orders=metrics.orders,
                )

                # Close client if it has resources
                if hasattr(client, "close"):
                    await client.close()

            except Exception as e:
                logger.error(
                    "listing_metrics_collection_failed",
                    listing_id=str(listing.id),
                    platform=listing.platform.value,
                    error=str(e),
                )
                error_count += 1

        await db.commit()

        return {
            "success": True,
            "metric_date": str(yesterday),
            "total_listings": len(listings),
            "collected_count": collected_count,
            "error_count": error_count,
            "skipped_count": skipped_count,
        }


async def _collect_asset_performance_daily() -> dict:
    """Collect yesterday's asset performance metrics (stub for future implementation)."""
    yesterday = date.today() - timedelta(days=1)

    logger.info(
        "asset_performance_collection_stub",
        metric_date=str(yesterday),
        status="not_implemented",
    )

    return {
        "success": True,
        "metric_date": str(yesterday),
        "status": "stub_not_implemented",
        "collected_count": 0,
    }


@celery_app.task(
    name="tasks.collect_listing_performance_daily",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 300},
    retry_backoff=True,
    retry_backoff_max=1800,
    retry_jitter=True,
)
def collect_listing_performance_daily(self) -> dict:
    """Daily task: Collect listing performance metrics from platform APIs."""
    task_id = self.request.id
    logger.info("task_started", task_id=task_id, task_name="collect_listing_performance_daily")
    try:
        result = run_async(_collect_listing_performance_daily())
        logger.info(
            "task_completed",
            task_id=task_id,
            task_name="collect_listing_performance_daily",
            result=result,
        )
        return result
    except Exception:
        logger.exception("task_failed", task_id=task_id, task_name="collect_listing_performance_daily")
        raise


@celery_app.task(
    name="tasks.collect_asset_performance_daily",
    bind=True,
    autoretry_for=(Exception,),
    retry_kwargs={"max_retries": 3, "countdown": 300},
    retry_backoff=True,
    retry_backoff_max=1800,
    retry_jitter=True,
)
def collect_asset_performance_daily(self) -> dict:
    """Daily task: Collect asset performance metrics (stub for future)."""
    task_id = self.request.id
    logger.info("task_started", task_id=task_id, task_name="collect_asset_performance_daily")
    try:
        result = run_async(_collect_asset_performance_daily())
        logger.info(
            "task_completed",
            task_id=task_id,
            task_name="collect_asset_performance_daily",
            result=result,
        )
        return result
    except Exception:
        logger.exception("task_failed", task_id=task_id, task_name="collect_asset_performance_daily")
        raise
