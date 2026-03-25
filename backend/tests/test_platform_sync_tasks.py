"""Tests for platform sync Celery task wrappers."""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.workers import tasks_platform_sync


@pytest.mark.asyncio
async def test_build_context_input_for_metrics():
    """Helper should build expected input data for metrics tasks."""
    result = tasks_platform_sync._build_context_input(
        "listing_metrics",
        start_date="2026-03-01",
        end_date="2026-03-02",
    )

    assert result == {
        "sync_type": "listing_metrics",
        "start_date": "2026-03-01",
        "end_date": "2026-03-02",
    }


def test_sync_all_listings_status_returns_agent_result(monkeypatch):
    """Status task should wrap sync helper and return serialized result."""
    run_sync_task = MagicMock(
        return_value={
            "success": True,
            "output_data": {"sync_type": "status", "synced_count": 3, "failed_count": 0},
            "error_message": None,
        }
    )
    monkeypatch.setattr(tasks_platform_sync, "_run_sync_task", run_sync_task)

    task_func = tasks_platform_sync.sync_all_listings_status.__wrapped__
    result = task_func()

    assert result == {
        "success": True,
        "output_data": {"sync_type": "status", "synced_count": 3, "failed_count": 0},
        "error_message": None,
    }
    run_sync_task.assert_called_once_with("status")


def test_sync_all_listings_inventory_passes_inventory_sync_type(monkeypatch):
    """Inventory task should invoke sync helper with inventory sync_type."""
    run_sync_task = MagicMock(
        return_value={
            "success": True,
            "output_data": {"sync_type": "inventory", "synced_count": 2, "failed_count": 0},
            "error_message": None,
        }
    )
    monkeypatch.setattr(tasks_platform_sync, "_run_sync_task", run_sync_task)

    task_func = tasks_platform_sync.sync_all_listings_inventory.__wrapped__
    result = task_func()

    assert result["success"] is True
    run_sync_task.assert_called_once_with("inventory")


def test_sync_all_listings_metrics_passes_date_range(monkeypatch):
    """Metrics task should pass sync_type and date range through to sync helper."""
    run_sync_task = MagicMock(
        return_value={
            "success": True,
            "output_data": {"sync_type": "listing_metrics", "synced_count": 5, "failed_count": 0},
            "error_message": None,
        }
    )
    monkeypatch.setattr(tasks_platform_sync, "_run_sync_task", run_sync_task)

    task_func = tasks_platform_sync.sync_all_listings_metrics.__wrapped__
    result = task_func(start_date="2026-03-01", end_date="2026-03-07")

    assert result["success"] is True
    run_sync_task.assert_called_once_with(
        "listing_metrics",
        start_date="2026-03-01",
        end_date="2026-03-07",
    )


def test_sync_all_listings_status_raises_on_agent_exception(monkeypatch):
    """Task wrapper should propagate exceptions so Celery marks task as failed."""
    run_sync_task = MagicMock(side_effect=RuntimeError("task boom"))
    monkeypatch.setattr(tasks_platform_sync, "_run_sync_task", run_sync_task)

    task_func = tasks_platform_sync.sync_all_listings_status.__wrapped__
    with pytest.raises(RuntimeError, match="task boom"):
        task_func()
