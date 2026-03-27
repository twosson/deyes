"""Tests for keyword research Celery tasks."""
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.workers import tasks_keyword_research


def test_generate_trending_keywords_uses_default_categories(monkeypatch):
    """Task should use default categories if none provided."""

    async def mock_run():
        return {
            "success": True,
            "results": [],
            "total_categories": 5,
            "successful_categories": 5,
            "failed_categories": 0,
        }

    mock_asyncio_run = MagicMock(return_value=mock_run())
    monkeypatch.setattr("asyncio.run", mock_asyncio_run)

    task_func = tasks_keyword_research.generate_trending_keywords.__wrapped__
    result = task_func(categories=None, region="US", limit=50)

    assert result["success"] is True
    assert result["total_categories"] == 5


def test_generate_trending_keywords_uses_custom_categories(monkeypatch):
    """Task should use custom categories if provided."""

    async def mock_run():
        return {
            "success": True,
            "results": [],
            "total_categories": 2,
            "successful_categories": 2,
            "failed_categories": 0,
        }

    mock_asyncio_run = MagicMock(return_value=mock_run())
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


def test_trigger_keyword_based_selection_returns_result(monkeypatch):
    """Selection task should wrap agent execution and return result."""

    async def mock_run():
        return {
            "success": True,
            "output_data": {"candidate_ids": ["id1", "id2"], "count": 2},
            "error_message": None,
        }

    mock_asyncio_run = MagicMock(return_value=mock_run())
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
