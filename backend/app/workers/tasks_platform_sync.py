"""Celery tasks for platform sync."""
from uuid import UUID

from app.agents.base.agent import AgentContext
from app.agents.platform_publisher import PlatformSyncAgent
from app.core.logging import get_logger
from app.db.session import get_db_context
from app.workers import run_async
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

# System-level placeholder for strategy_run_id used when tasks are triggered
# by beat scheduler rather than an explicit strategy run.
SYSTEM_STRATEGY_RUN_ID = UUID("00000000-0000-0000-0000-000000000000")


def _build_context_input(
    sync_type: str, start_date: str | None = None, end_date: str | None = None
) -> dict:
    """Build input_data dict for a platform sync task.

    Args:
        sync_type: One of "status", "inventory", "listing_metrics".
        start_date: ISO date string for metrics sync (defaults to today via agent).
        end_date: ISO date string for metrics sync (defaults to today via agent).

    Returns:
        input_data dict for AgentContext; platform_listing_ids=None syncs all active.
    """
    input_data: dict = {"sync_type": sync_type}
    if start_date:
        input_data["start_date"] = start_date
    if end_date:
        input_data["end_date"] = end_date
    return input_data


def _run_sync_task(
    sync_type: str, start_date: str | None = None, end_date: str | None = None
) -> dict:
    """Execute a platform sync task on the worker process async loop."""
    async def run():
        async with get_db_context() as db:
            agent = PlatformSyncAgent()
            context = AgentContext(
                strategy_run_id=SYSTEM_STRATEGY_RUN_ID,
                db=db,
                input_data=_build_context_input(sync_type, start_date, end_date),
            )
            result = await agent.execute(context)
            return {
                "success": result.success,
                "output_data": result.output_data,
                "error_message": result.error_message,
            }

    return run_async(run())


@celery_app.task(name="tasks.sync_all_listings_status", bind=True)
def sync_all_listings_status(self) -> dict:
    """Sync status for all active listings."""
    task_id = self.request.id
    logger.info("task_started", task_id=task_id, task_name="sync_all_listings_status")
    try:
        result = _run_sync_task("status")
        logger.info(
            "task_completed",
            task_id=task_id,
            task_name="sync_all_listings_status",
            result=result,
        )
        return result
    except Exception as e:
        logger.error(
            "task_failed",
            task_id=task_id,
            task_name="sync_all_listings_status",
            error=str(e),
        )
        raise


@celery_app.task(name="tasks.sync_all_listings_inventory", bind=True)
def sync_all_listings_inventory(self) -> dict:
    """Sync inventory levels for all active listings."""
    task_id = self.request.id
    logger.info("task_started", task_id=task_id, task_name="sync_all_listings_inventory")
    try:
        result = _run_sync_task("inventory")
        logger.info(
            "task_completed",
            task_id=task_id,
            task_name="sync_all_listings_inventory",
            result=result,
        )
        return result
    except Exception as e:
        logger.error(
            "task_failed",
            task_id=task_id,
            task_name="sync_all_listings_inventory",
            error=str(e),
        )
        raise


@celery_app.task(name="tasks.sync_all_listings_metrics", bind=True)
def sync_all_listings_metrics(
    self, start_date: str | None = None, end_date: str | None = None
) -> dict:
    """Sync performance metrics for all active listings.

    Args:
        start_date: ISO date string for the metrics range start (defaults to today).
        end_date: ISO date string for the metrics range end (defaults to today).
    """
    task_id = self.request.id
    logger.info(
        "task_started",
        task_id=task_id,
        task_name="sync_all_listings_metrics",
        start_date=start_date,
        end_date=end_date,
    )
    try:
        result = _run_sync_task("listing_metrics", start_date=start_date, end_date=end_date)
        logger.info(
            "task_completed",
            task_id=task_id,
            task_name="sync_all_listings_metrics",
            result=result,
        )
        return result
    except Exception as e:
        logger.error(
            "task_failed",
            task_id=task_id,
            task_name="sync_all_listings_metrics",
            error=str(e),
        )
        raise

