"""Celery tasks for agent pipeline."""
from uuid import UUID

from app.agents.director_workflow import DirectorWorkflow
from app.core.logging import get_logger
from app.db.session import get_db_context
from app.workers import run_async
from app.workers.celery_app import celery_app

logger = get_logger(__name__)


@celery_app.task(name="tasks.start_discovery_pipeline", bind=True)
def start_discovery_pipeline(self, strategy_run_id: str):
    """Start the discovery pipeline for a strategy run."""
    logger.info("task_started", task_id=self.request.id, strategy_run_id=strategy_run_id)

    async def run_pipeline():
        async with get_db_context() as db:
            workflow = DirectorWorkflow()
            result = await workflow.execute_pipeline(
                strategy_run_id=UUID(strategy_run_id),
                db=db,
            )
            return result

    try:
        result = run_async(run_pipeline())
        logger.info(
            "task_completed",
            task_id=self.request.id,
            strategy_run_id=strategy_run_id,
            result=result,
        )
        return result
    except Exception as e:
        logger.error(
            "task_failed",
            task_id=self.request.id,
            strategy_run_id=strategy_run_id,
            error=str(e),
        )
        raise
