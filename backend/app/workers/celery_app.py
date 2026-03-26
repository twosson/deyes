"""Celery application configuration."""
from celery import Celery
from celery.schedules import crontab

from app.core.config import get_settings

settings = get_settings()

celery_app = Celery(
    "deyes",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[
        "app.workers.tasks_agent_pipeline",
        "app.workers.tasks_platform_sync",
        "app.workers.tasks_keyword_research",
    ],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    task_soft_time_limit=3300,  # 55 minutes
    worker_prefetch_multiplier=1,
    worker_max_tasks_per_child=100,
    beat_schedule={
        "sync-all-listings-status": {
            "task": "tasks.sync_all_listings_status",
            "schedule": crontab(minute="*/15"),
        },
        "sync-all-listings-inventory": {
            "task": "tasks.sync_all_listings_inventory",
            "schedule": crontab(minute="*/30"),
        },
        "sync-all-listings-metrics": {
            "task": "tasks.sync_all_listings_metrics",
            "schedule": crontab(minute=0, hour=0),
        },
        "generate-trending-keywords": {
            "task": "tasks.generate_trending_keywords",
            "schedule": crontab(minute=0, hour=23),  # Run at 23:00 UTC daily
        },
    },
)
