"""Edge case tests for keyword research auto-trigger behavior."""
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.workers import tasks_keyword_research


def test_auto_trigger_skips_empty_keyword_set(monkeypatch):
    """Auto-trigger should not fire when keyword set is empty after deduplication."""

    async def mock_generate_for_category(category, region, limit):
        return {
            "success": True,
            "category": category,
            "region": region,
            "base_keywords": [],
            "expanded_keywords": [],
            "total_count": 0,
        }

    settings = MagicMock()
    settings.keyword_generation_auto_trigger_selection = True

    trigger_delay = MagicMock()
    monkeypatch.setattr(
        tasks_keyword_research,
        "_generate_keywords_for_category",
        mock_generate_for_category,
    )
    monkeypatch.setattr(tasks_keyword_research, "get_settings", lambda: settings)
    monkeypatch.setattr(
        tasks_keyword_research.trigger_keyword_based_selection,
        "delay",
        trigger_delay,
    )

    task_func = tasks_keyword_research.generate_trending_keywords.__wrapped__
    result = task_func(categories=["electronics"], region="US", limit=10)

    assert result["success"] is True
    trigger_delay.assert_not_called()


def test_auto_trigger_skips_on_generation_failure(monkeypatch):
    """Auto-trigger should not fire when generation fails for a category."""

    async def mock_generate_for_category(category, region, limit):
        return {
            "success": False,
            "category": category,
            "region": region,
            "error": "pytrends error",
        }

    settings = MagicMock()
    settings.keyword_generation_auto_trigger_selection = True

    trigger_delay = MagicMock()
    monkeypatch.setattr(
        tasks_keyword_research,
        "_generate_keywords_for_category",
        mock_generate_for_category,
    )
    monkeypatch.setattr(tasks_keyword_research, "get_settings", lambda: settings)
    monkeypatch.setattr(
        tasks_keyword_research.trigger_keyword_based_selection,
        "delay",
        trigger_delay,
    )

    task_func = tasks_keyword_research.generate_trending_keywords.__wrapped__
    result = task_func(categories=["electronics"], region="US", limit=10)

    assert result["success"] is True
    assert result["failed_categories"] == 1
    trigger_delay.assert_not_called()


def test_auto_trigger_deduplicates_keywords_across_base_and_expanded(monkeypatch):
    """Auto-trigger should deduplicate keywords appearing in both base and expanded."""

    async def mock_generate_for_category(category, region, limit):
        return {
            "success": True,
            "category": category,
            "region": region,
            "base_keywords": [
                {"keyword": "wireless earbuds"},
                {"keyword": "bluetooth speaker"},
            ],
            "expanded_keywords": ["wireless earbuds", "true wireless earbuds"],
            "total_count": 4,
        }

    settings = MagicMock()
    settings.keyword_generation_auto_trigger_selection = True

    trigger_delay = MagicMock()
    monkeypatch.setattr(
        tasks_keyword_research,
        "_generate_keywords_for_category",
        mock_generate_for_category,
    )
    monkeypatch.setattr(tasks_keyword_research, "get_settings", lambda: settings)
    monkeypatch.setattr(
        tasks_keyword_research.trigger_keyword_based_selection,
        "delay",
        trigger_delay,
    )

    task_func = tasks_keyword_research.generate_trending_keywords.__wrapped__
    result = task_func(categories=["electronics"], region="US", limit=10)

    assert result["success"] is True
    trigger_delay.assert_called_once()
    call_kwargs = trigger_delay.call_args.kwargs
    assert len(call_kwargs["keywords"]) == 3
    assert "wireless earbuds" in call_kwargs["keywords"]
    assert "bluetooth speaker" in call_kwargs["keywords"]
    assert "true wireless earbuds" in call_kwargs["keywords"]


def test_auto_trigger_handles_none_keyword_data_gracefully(monkeypatch):
    """Auto-trigger should handle None entries in base_keywords gracefully."""

    async def mock_generate_for_category(category, region, limit):
        return {
            "success": True,
            "category": category,
            "region": region,
            "base_keywords": [
                {"keyword": "wireless earbuds"},
                None,
                {"keyword": "phone stand"},
            ],
            "expanded_keywords": ["bluetooth earbuds"],
            "total_count": 3,
        }

    settings = MagicMock()
    settings.keyword_generation_auto_trigger_selection = True

    trigger_delay = MagicMock()
    monkeypatch.setattr(
        tasks_keyword_research,
        "_generate_keywords_for_category",
        mock_generate_for_category,
    )
    monkeypatch.setattr(tasks_keyword_research, "get_settings", lambda: settings)
    monkeypatch.setattr(
        tasks_keyword_research.trigger_keyword_based_selection,
        "delay",
        trigger_delay,
    )

    task_func = tasks_keyword_research.generate_trending_keywords.__wrapped__
    result = task_func(categories=["electronics"], region="US", limit=10)

    assert result["success"] is True
    trigger_delay.assert_called_once()
    call_kwargs = trigger_delay.call_args.kwargs
    assert len(call_kwargs["keywords"]) == 3
    assert "wireless earbuds" in call_kwargs["keywords"]
    assert "phone stand" in call_kwargs["keywords"]
    assert "bluetooth earbuds" in call_kwargs["keywords"]


def test_auto_trigger_per_category_isolation(monkeypatch):
    """Auto-trigger should fire once per successful category independently."""

    call_count = 0

    async def mock_generate_for_category(category, region, limit):
        nonlocal call_count
        call_count += 1
        if category == "electronics":
            return {
                "success": True,
                "category": category,
                "region": region,
                "base_keywords": [{"keyword": "wireless earbuds"}],
                "expanded_keywords": [],
                "total_count": 1,
            }
        elif category == "fashion":
            return {
                "success": False,
                "category": category,
                "region": region,
                "error": "no trends",
            }
        else:
            return {
                "success": True,
                "category": category,
                "region": region,
                "base_keywords": [{"keyword": "yoga mat"}],
                "expanded_keywords": [],
                "total_count": 1,
            }

    settings = MagicMock()
    settings.keyword_generation_auto_trigger_selection = True

    trigger_delay = MagicMock()
    monkeypatch.setattr(
        tasks_keyword_research,
        "_generate_keywords_for_category",
        mock_generate_for_category,
    )
    monkeypatch.setattr(tasks_keyword_research, "get_settings", lambda: settings)
    monkeypatch.setattr(
        tasks_keyword_research.trigger_keyword_based_selection,
        "delay",
        trigger_delay,
    )

    task_func = tasks_keyword_research.generate_trending_keywords.__wrapped__
    result = task_func(categories=["electronics", "fashion", "sports"], region="US", limit=10)

    assert result["success"] is True
    assert result["successful_categories"] == 2
    assert result["failed_categories"] == 1
    assert trigger_delay.call_count == 2

    calls = trigger_delay.call_args_list
    electronics_call = next(c for c in calls if c.kwargs["category"] == "electronics")
    sports_call = next(c for c in calls if c.kwargs["category"] == "sports")
    assert electronics_call.kwargs["keywords"] == ["wireless earbuds"]
    assert sports_call.kwargs["keywords"] == ["yoga mat"]
