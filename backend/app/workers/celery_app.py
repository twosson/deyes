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
        "app.workers.tasks_auto_actions",
        "app.workers.tasks_performance_collection",
    ],
)

# Build beat schedule dynamically based on enabled features
beat_schedule = {
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
    "collect-listing-performance-daily": {
        "task": "tasks.collect_listing_performance_daily",
        "schedule": crontab(hour=1, minute=0),
    },
    "collect-asset-performance-daily": {
        "task": "tasks.collect_asset_performance_daily",
        "schedule": crontab(hour=1, minute=30),
    },
    "generate-trending-keywords": {
        "task": "tasks.generate_trending_keywords",
        "schedule": crontab(minute=0, hour=23),  # Run at 23:00 UTC daily
    },
}

# Add auto action tasks if enabled
if settings.enable_auto_actions:
    if settings.auto_reprice_enable:
        beat_schedule["auto-reprice-daily"] = {
            "task": "tasks.auto_reprice_all_listings",
            "schedule": crontab(hour=2, minute=0),  # Run at 02:00 UTC daily
        }
    if settings.auto_pause_enable:
        beat_schedule["auto-pause-daily"] = {
            "task": "tasks.auto_pause_all_listings",
            "schedule": crontab(hour=3, minute=0),  # Run at 03:00 UTC daily
        }
    if settings.auto_asset_switch_enable:
        beat_schedule["auto-asset-switch-daily"] = {
            "task": "tasks.auto_asset_switch_all_listings",
            "schedule": crontab(hour=4, minute=0),  # Run at 04:00 UTC daily
        }

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
    beat_schedule=beat_schedule,
)
