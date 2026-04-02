"""Celery tasks for keyword research and generation.

Phase 3 Enhancement: Nightly keyword generation for automated product discovery.
"""
from typing import Optional
from uuid import UUID

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.keyword_generator import KeywordGenerator
from app.workers import run_async
from app.workers.celery_app import celery_app

logger = get_logger(__name__)

# System-level placeholder for strategy_run_id
SYSTEM_STRATEGY_RUN_ID = UUID("00000000-0000-0000-0000-000000000000")
NIGHTLY_SELECTION_PLATFORM = "alibaba_1688"


def _get_redis_client():
    """Get Redis client for caching."""
    try:
        import redis.asyncio as redis

        settings = get_settings()
        return redis.from_url(settings.redis_url, decode_responses=True)
    except Exception as e:
        logger.warning("redis_client_creation_failed", error=str(e))
        return None


async def _generate_keywords_for_category(
    category: str,
    region: str = "US",
    limit: int = 50,
) -> dict:
    """Generate keywords for a single category.

    Args:
        category: Product category (e.g., "electronics", "fashion")
        region: Region code (default: "US")
        limit: Maximum number of keywords to generate (default: 50)

    Returns:
        Dict with success status and generated keywords
    """
    redis_client = _get_redis_client()

    try:
        generator = KeywordGenerator(
            redis_client=redis_client,
            cache_ttl_seconds=86400,  # 24 hours
            enable_cache=True,
            min_trend_score=20,
        )

        keywords = await generator.generate_selection_keywords(
            category=category,
            region=region,
            limit=limit,
            expand_top_n=10,
        )

        expanded_keywords = []
        for keyword_result in keywords:
            expanded_keywords.extend(keyword_result.related_keywords)

        logger.info(
            "keywords_generated",
            category=category,
            region=region,
            base_keywords=len(keywords),
            expanded_keywords=len(expanded_keywords),
        )

        return {
            "success": True,
            "category": category,
            "region": region,
            "base_keywords": [kw.to_dict() for kw in keywords],
            "expanded_keywords": expanded_keywords,
            "total_count": len(keywords) + len(expanded_keywords),
        }

    except Exception as e:
        logger.error(
            "keyword_generation_failed",
            category=category,
            region=region,
            error=str(e),
        )
        return {
            "success": False,
            "category": category,
            "region": region,
            "error": str(e),
        }
    finally:
        if redis_client:
            await redis_client.close()


@celery_app.task(name="tasks.generate_trending_keywords", bind=True)
def generate_trending_keywords(
    self,
    categories: Optional[list[str]] = None,
    region: str = "US",
    limit: int = 50,
) -> dict:
    """Generate trending keywords for product categories.

    This task runs nightly to discover trending keywords for automated
    product selection.

    Args:
        categories: List of categories to generate keywords for.
                   If None, uses default categories.
        region: Region code (default: "US")
        limit: Maximum keywords per category (default: 50)

    Returns:
        Dict with generation results for each category
    """
    task_id = self.request.id
    logger.info(
        "task_started",
        task_id=task_id,
        task_name="generate_trending_keywords",
        categories=categories,
        region=region,
        limit=limit,
    )

    # Default categories if not specified
    if not categories:
        categories = ["electronics", "fashion", "home", "beauty", "sports"]

    async def run_generation():
        results = []
        settings = get_settings()
        triggered_categories: list[str] = []
        triggered_selection_task_ids: list[str] = []
        trigger_success_count = 0
        trigger_skip_count = 0
        trigger_failure_count = 0

        for category in categories:
            result = await _generate_keywords_for_category(
                category=category,
                region=region,
                limit=limit,
            )

            auto_trigger_audit = {
                "status": "disabled",
                "reason": "auto_trigger_disabled",
                "selection_task_id": None,
                "keywords_count": 0,
            }

            if settings.keyword_generation_auto_trigger_selection and result.get("success"):
                auto_keywords: list[str] = []
                seen: set[str] = set()

                for keyword_data in result.get("base_keywords", []):
                    keyword = (keyword_data or {}).get("keyword")
                    if keyword and keyword not in seen:
                        seen.add(keyword)
                        auto_keywords.append(keyword)

                for keyword in result.get("expanded_keywords", []):
                    if keyword and keyword not in seen:
                        seen.add(keyword)
                        auto_keywords.append(keyword)

                if auto_keywords:
                    try:
                        selection_task = trigger_keyword_based_selection.delay(
                            category=category,
                            keywords=auto_keywords,
                            region=region,
                            max_candidates=limit,
                        )
                        selection_task_id = str(selection_task.id)
                        triggered_categories.append(category)
                        triggered_selection_task_ids.append(selection_task_id)
                        trigger_success_count += 1
                        auto_trigger_audit = {
                            "status": "triggered",
                            "reason": None,
                            "selection_task_id": selection_task_id,
                            "keywords_count": len(auto_keywords),
                        }
                        logger.info(
                            "selection_task_triggered",
                            category=category,
                            keywords_count=len(auto_keywords),
                            selection_task_id=selection_task_id,
                        )
                    except Exception as exc:
                        trigger_failure_count += 1
                        auto_trigger_audit = {
                            "status": "failed",
                            "reason": "trigger_dispatch_failed",
                            "selection_task_id": None,
                            "keywords_count": len(auto_keywords),
                            "error": str(exc),
                        }
                        logger.error(
                            "selection_task_trigger_failed",
                            category=category,
                            keywords_count=len(auto_keywords),
                            error=str(exc),
                        )
                else:
                    trigger_skip_count += 1
                    auto_trigger_audit = {
                        "status": "skipped",
                        "reason": "no_keywords_after_deduplication",
                        "selection_task_id": None,
                        "keywords_count": 0,
                    }
                    logger.info(
                        "selection_task_skipped",
                        category=category,
                        reason="no_keywords_after_deduplication",
                    )
            elif settings.keyword_generation_auto_trigger_selection and not result.get("success"):
                trigger_skip_count += 1
                auto_trigger_audit = {
                    "status": "skipped",
                    "reason": "keyword_generation_failed",
                    "selection_task_id": None,
                    "keywords_count": 0,
                }
                logger.info(
                    "selection_task_skipped",
                    category=category,
                    reason="keyword_generation_failed",
                )

            result["auto_trigger"] = auto_trigger_audit
            results.append(result)

        return {
            "success": True,
            "results": results,
            "total_categories": len(categories),
            "successful_categories": sum(1 for r in results if r["success"]),
            "failed_categories": sum(1 for r in results if not r["success"]),
            "triggered_categories": triggered_categories,
            "triggered_selection_task_ids": triggered_selection_task_ids,
            "trigger_success_count": trigger_success_count,
            "trigger_skip_count": trigger_skip_count,
            "trigger_failure_count": trigger_failure_count,
        }

    try:
        result = run_async(run_generation())
        logger.info(
            "task_completed",
            task_id=task_id,
            task_name="generate_trending_keywords",
            result=result,
        )
        return result
    except Exception as e:
        logger.error(
            "task_failed",
            task_id=task_id,
            task_name="generate_trending_keywords",
            error=str(e),
        )
        raise


@celery_app.task(name="tasks.trigger_keyword_based_selection", bind=True)
def trigger_keyword_based_selection(
    self,
    category: str,
    keywords: list[str],
    region: str = "US",
    max_candidates: int = 10,
) -> dict:
    """Trigger product selection based on generated keywords.

    This task is called after keyword generation to automatically start
    product discovery for trending keywords.

    Seller-first refactor: Uses alibaba_1688 platform to leverage
    AlphaShop search intelligence and optional opportunity enhancement.

    Args:
        category: Product category
        keywords: List of keywords to search for
        region: Region code
        max_candidates: Maximum candidates per keyword

    Returns:
        Dict with selection results
    """
    task_id = self.request.id
    logger.info(
        "task_started",
        task_id=task_id,
        task_name="trigger_keyword_based_selection",
        category=category,
        keywords_count=len(keywords),
        region=region,
    )

    async def run_selection():
        from app.agents.base.agent import AgentContext
        from app.agents.product_selector import ProductSelectorAgent
        from app.db.session import get_db_context

        async with get_db_context() as db:
            agent = ProductSelectorAgent(enable_demand_validation=True)

            context = AgentContext(
                strategy_run_id=SYSTEM_STRATEGY_RUN_ID,
                db=db,
                input_data={
                    "platform": NIGHTLY_SELECTION_PLATFORM,
                    "category": category,
                    "keywords": keywords,
                    "region": region,
                    "max_candidates": max_candidates,
                },
            )

            result = await agent.execute(context)

            return {
                "success": result.success,
                "output_data": result.output_data,
                "error_message": result.error_message,
            }

    try:
        result = run_async(run_selection())
        logger.info(
            "task_completed",
            task_id=task_id,
            task_name="trigger_keyword_based_selection",
            result=result,
        )
        return result
    except Exception as e:
        logger.error(
            "task_failed",
            task_id=task_id,
            task_name="trigger_keyword_based_selection",
            error=str(e),
        )
        raise
