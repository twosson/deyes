"""Tests for keyword research Celery tasks."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers import tasks_keyword_research


def test_generate_trending_keywords_uses_default_categories(monkeypatch):
    """Task should use default categories if none provided."""

    mock_asyncio_run = MagicMock(return_value={
        "success": True,
        "results": [],
        "total_categories": 5,
        "successful_categories": 5,
        "failed_categories": 0,
    })
    monkeypatch.setattr("asyncio.run", mock_asyncio_run)

    task_func = tasks_keyword_research.generate_trending_keywords.__wrapped__
    result = task_func(categories=None, region="US", limit=50)

    assert result["success"] is True
    assert result["total_categories"] == 5


def test_generate_trending_keywords_uses_custom_categories(monkeypatch):
    """Task should use custom categories if provided."""

    mock_asyncio_run = MagicMock(return_value={
        "success": True,
        "results": [],
        "total_categories": 2,
        "successful_categories": 2,
        "failed_categories": 0,
    })
    monkeypatch.setattr("asyncio.run", mock_asyncio_run)

    task_func = tasks_keyword_research.generate_trending_keywords.__wrapped__
    result = task_func(categories=["electronics", "fashion"], region="US", limit=50)

    assert result["success"] is True
    assert result["total_categories"] == 2


def test_generate_trending_keywords_raises_on_exception(monkeypatch):
    """Task wrapper should propagate exceptions."""
    mock_asyncio_run = MagicMock(side_effect=RuntimeError("task boom"))
    monkeypatch.setattr("asyncio.run", mock_asyncio_run)

    task_func = tasks_keyword_research.generate_trending_keywords.__wrapped__
    with pytest.raises(RuntimeError, match="task boom"):
        task_func(categories=["electronics"], region="US", limit=50)


def test_generate_trending_keywords_auto_triggers_selection(monkeypatch):
    """Task should auto-trigger downstream selection when enabled."""

    async def mock_generate_for_category(category, region, limit):
        return {
            "success": True,
            "category": category,
            "region": region,
            "base_keywords": [
                {"keyword": "wireless earbuds"},
                {"keyword": "phone stand"},
            ],
            "expanded_keywords": ["bluetooth earbuds", "wireless earbuds"],
            "total_count": 4,
        }

    settings = MagicMock()
    settings.keyword_generation_auto_trigger_selection = True

    trigger_delay = MagicMock()
    trigger_delay.return_value = MagicMock(id="task-id-123")
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
    assert result["trigger_success_count"] == 1
    assert result["trigger_skip_count"] == 0
    assert len(result["triggered_selection_task_ids"]) == 1
    assert result["triggered_selection_task_ids"][0] == "task-id-123"
    trigger_delay.assert_called_once_with(
        category="electronics",
        keywords=["wireless earbuds", "phone stand", "bluetooth earbuds"],
        region="US",
        max_candidates=10,
    )


def test_generate_trending_keywords_skips_auto_trigger_when_disabled(monkeypatch):
    """Task should not auto-trigger downstream selection when disabled."""

    async def mock_generate_for_category(category, region, limit):
        return {
            "success": True,
            "category": category,
            "region": region,
            "base_keywords": [{"keyword": "wireless earbuds"}],
            "expanded_keywords": ["bluetooth earbuds"],
            "total_count": 2,
        }

    settings = MagicMock()
    settings.keyword_generation_auto_trigger_selection = False

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
    assert result["trigger_success_count"] == 0
    assert result["trigger_skip_count"] == 0
    assert result["triggered_selection_task_ids"] == []
    trigger_delay.assert_not_called()


def test_generate_trending_keywords_counts_skipped_triggers(monkeypatch):
    """Task should count skipped triggers when generation fails or returns no keywords."""

    async def mock_generate_for_category(category, region, limit):
        if category == "electronics":
            return {
                "success": False,
                "category": category,
                "region": region,
                "error": "pytrends error",
            }
        else:
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
    result = task_func(categories=["electronics", "fashion"], region="US", limit=10)

    assert result["success"] is True
    assert result["trigger_success_count"] == 0
    assert result["trigger_skip_count"] == 2
    assert result["trigger_failure_count"] == 0
    assert result["triggered_selection_task_ids"] == []
    assert result["triggered_categories"] == []
    trigger_delay.assert_not_called()


def test_generate_trending_keywords_includes_per_category_audit(monkeypatch):
    """Task should include per-category auto_trigger audit in results."""

    async def mock_generate_for_category(category, region, limit):
        return {
            "success": True,
            "category": category,
            "region": region,
            "base_keywords": [{"keyword": "wireless earbuds"}],
            "expanded_keywords": [],
            "total_count": 1,
        }

    settings = MagicMock()
    settings.keyword_generation_auto_trigger_selection = True

    trigger_delay = MagicMock()
    trigger_delay.return_value = MagicMock(id="task-id-456")
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
    assert len(result["results"]) == 1
    assert "auto_trigger" in result["results"][0]
    audit = result["results"][0]["auto_trigger"]
    assert audit["status"] == "triggered"
    assert audit["selection_task_id"] == "task-id-456"
    assert audit["keywords_count"] == 1
    assert audit["reason"] is None


def test_generate_trending_keywords_handles_trigger_dispatch_failure(monkeypatch):
    """Task should handle trigger dispatch failures gracefully and continue."""

    async def mock_generate_for_category(category, region, limit):
        return {
            "success": True,
            "category": category,
            "region": region,
            "base_keywords": [{"keyword": "wireless earbuds"}],
            "expanded_keywords": [],
            "total_count": 1,
        }

    settings = MagicMock()
    settings.keyword_generation_auto_trigger_selection = True

    trigger_delay = MagicMock(side_effect=RuntimeError("celery broker down"))
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
    assert result["trigger_success_count"] == 0
    assert result["trigger_skip_count"] == 0
    assert result["trigger_failure_count"] == 1
    assert result["triggered_selection_task_ids"] == []
    assert result["triggered_categories"] == []
    audit = result["results"][0]["auto_trigger"]
    assert audit["status"] == "failed"
    assert audit["reason"] == "trigger_dispatch_failed"
    assert "celery broker down" in audit["error"]


def test_trigger_keyword_based_selection_returns_result(monkeypatch):
    """Selection task should wrap agent execution and return result."""

    mock_asyncio_run = MagicMock(return_value={
        "success": True,
        "output_data": {"candidate_ids": ["id1", "id2"], "count": 2},
        "error_message": None,
    })
    monkeypatch.setattr("asyncio.run", mock_asyncio_run)

    task_func = tasks_keyword_research.trigger_keyword_based_selection.__wrapped__
    result = task_func(
        category="electronics",
        keywords=["wireless earbuds", "phone case"],
        region="US",
        max_candidates=10,
    )

    assert result["success"] is True
    assert result["output_data"]["count"] == 2


def test_trigger_keyword_based_selection_uses_alibaba_1688_platform():
    """Nightly keyword-triggered selection should target alibaba_1688."""
    assert tasks_keyword_research.NIGHTLY_SELECTION_PLATFORM == "alibaba_1688"



def test_trigger_keyword_based_selection_raises_on_exception(monkeypatch):
    """Selection task should propagate exceptions."""
    mock_asyncio_run = MagicMock(side_effect=RuntimeError("selection boom"))
    monkeypatch.setattr("asyncio.run", mock_asyncio_run)

    task_func = tasks_keyword_research.trigger_keyword_based_selection.__wrapped__
    with pytest.raises(RuntimeError, match="selection boom"):
        task_func(
            category="electronics",
            keywords=["wireless earbuds"],
            region="US",
            max_candidates=10,
        )


@pytest.mark.asyncio
async def test_generate_keywords_for_category_success():
    """Helper should generate keywords for a category using generate_selection_keywords."""
    from app.services.keyword_generator import KeywordResult

    mock_results = [
        KeywordResult(
            keyword="wireless earbuds",
            search_volume=5000,
            trend_score=75,
            competition_density="medium",
            related_keywords=["bluetooth earbuds", "true wireless earbuds"],
            category="electronics",
            region="US",
        )
    ]

    with patch(
        "app.workers.tasks_keyword_research.KeywordGenerator"
    ) as mock_generator_class:
        mock_generator = MagicMock()
        mock_generator.generate_selection_keywords = AsyncMock(return_value=mock_results)
        mock_generator_class.return_value = mock_generator

        result = await tasks_keyword_research._generate_keywords_for_category(
            category="electronics",
            region="US",
            limit=50,
        )

    assert result["success"] is True
    assert result["category"] == "electronics"
    assert result["region"] == "US"
    assert len(result["base_keywords"]) == 1
    assert result["base_keywords"][0]["keyword"] == "wireless earbuds"
    assert len(result["expanded_keywords"]) == 2
    assert "bluetooth earbuds" in result["expanded_keywords"]


@pytest.mark.asyncio
async def test_generate_keywords_for_category_failure():
    """Helper should handle exceptions gracefully."""
    with patch(
        "app.workers.tasks_keyword_research.KeywordGenerator"
    ) as mock_generator_class:
        mock_generator = MagicMock()
        mock_generator.generate_selection_keywords = AsyncMock(
            side_effect=RuntimeError("pytrends error")
        )
        mock_generator_class.return_value = mock_generator

        result = await tasks_keyword_research._generate_keywords_for_category(
            category="electronics",
            region="US",
            limit=50,
        )

    assert result["success"] is False
    assert result["category"] == "electronics"
    assert "error" in result
    assert "pytrends error" in result["error"]
