"""
Seasonal Seed Expander Service

Converts seasonal event + category into specific, searchable product phrases
using local Qwen3.5 via SGLang. Falls back to template-based generation on failure.

Example:
    Input: Father's Day + electronics
    Output: ["wireless earbuds for dad", "desk gadget gift", "portable power bank"]
"""

from typing import Optional

from app.clients.redis import RedisClient
from app.clients.sglang import SGLangClient
from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.seasonal_calendar import SeasonalEvent

logger = get_logger(__name__)


class SeasonalSeedExpander:
    """Expands seasonal events into specific product search phrases using LLM."""

    def __init__(
        self,
        sglang_client: Optional[SGLangClient] = None,
        redis_client: Optional[RedisClient] = None,
    ):
        self.sglang = sglang_client or SGLangClient()
        self.redis = redis_client or RedisClient()
        self.settings = get_settings()

    async def expand(
        self,
        event: SeasonalEvent,
        category: str,
        region: str = "US",
        limit: int = 5,
    ) -> list[str]:
        """
        Generate specific product search phrases for a seasonal event + category.

        Args:
            event: Seasonal event with name, description, date
            category: Product category (e.g., "electronics", "jewelry")
            region: Target region for localization
            limit: Maximum number of phrases to generate

        Returns:
            List of specific search phrases, or empty list on failure
        """
        if not self.settings.seed_enable_seasonal_llm_expansion:
            logger.debug("seasonal_seed_llm_disabled")
            return []

        cache_key = self._build_cache_key(event, category, region)
        cached = await self._get_cached(cache_key)
        if cached is not None:
            logger.debug(
                "seasonal_seed_cache_hit",
                cache_key=cache_key,
                event_name=event.name,
                category=category,
                region=region,
                count=len(cached),
            )
            return cached[:limit]

        try:
            queries = await self._generate_via_llm(event, category, region, limit)
            if queries:
                await self._set_cached(cache_key, queries)
                logger.info(
                    "seasonal_seed_generated",
                    event_name=event.name,
                    category=category,
                    region=region,
                    count=len(queries),
                )
                return queries[:limit]

            logger.warning(
                "seasonal_seed_empty_result",
                event_name=event.name,
                category=category,
                region=region,
            )
            return []
        except Exception as exc:
            logger.error(
                "seasonal_seed_expansion_failed",
                event_name=event.name,
                category=category,
                region=region,
                error=str(exc),
                exc_info=True,
            )
            return []

    async def _generate_via_llm(
        self,
        event: SeasonalEvent,
        category: str,
        region: str,
        limit: int,
    ) -> list[str]:
        """Call SGLang to generate seasonal product phrases."""
        prompt = self._build_prompt(event, category, region, limit)
        schema = self._build_json_schema(limit)

        result = await self.sglang.generate_structured_json(
            prompt=prompt,
            schema=schema,
            temperature=self.settings.seed_seasonal_llm_temperature,
        )

        queries = result.get("queries", [])
        # Normalize and deduplicate
        normalized = []
        seen = set()
        for q in queries:
            q_clean = q.strip().lower()
            if q_clean and q_clean not in seen and len(q_clean) > 3:
                normalized.append(q_clean)
                seen.add(q_clean)

        return normalized

    def _build_prompt(
        self,
        event: SeasonalEvent,
        category: str,
        region: str,
        limit: int,
    ) -> str:
        """Build LLM prompt for seasonal phrase generation."""
        return f"""You are an e-commerce search expert. Generate {limit} specific, short product search phrases that shoppers would use when looking for {category} products related to {event.name}.

Event: {event.name}
Description: {event.description}
Category: {category}
Region: {region}

Requirements:
- Generate SHORT search phrases (2-5 words), NOT full sentences
- Focus on SPECIFIC products, not generic terms
- Avoid brand names
- Avoid just combining event name + category (e.g., avoid "father's day electronics")
- Think about what actual shoppers would type into a search box
- Phrases should be suitable for product search on e-commerce platforms

Examples of GOOD phrases for "Father's Day + electronics":
- wireless earbuds for dad
- desk gadget gift
- portable power bank
- phone stand gift

Examples of BAD phrases:
- father's day electronics (too generic)
- Best Father's Day Gifts (too broad, sentence-like)
- Apple AirPods (brand name)

Generate {limit} specific product search phrases:"""

    def _build_json_schema(self, limit: int) -> dict:
        """Build JSON schema for structured output."""
        return {
            "name": "seasonal_seed_expansion",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 0,
                        "maxItems": min(limit * 2, 8),  # Allow some buffer
                    }
                },
                "required": ["queries"],
                "additionalProperties": False,
            },
        }

    def _build_cache_key(
        self,
        event: SeasonalEvent,
        category: str,
        region: str,
    ) -> str:
        """Build Redis cache key."""
        event_date_str = event.date.strftime("%Y-%m-%d")
        return f"seasonal_seed_expander:{region}:{category}:{event.name}:{event_date_str}"

    async def _get_cached(self, key: str) -> Optional[list[str]]:
        """Get cached expansion result."""
        try:
            cached = await self.redis.get(key)
            if cached:
                return cached.split("||")
            return None
        except Exception as exc:
            logger.warning("seasonal_seed_cache_get_failed", key=key, error=str(exc))
            return None

    async def _set_cached(self, key: str, queries: list[str]) -> None:
        """Cache expansion result."""
        try:
            value = "||".join(queries)
            await self.redis.set(key, value, ex=self.settings.seed_seasonal_llm_cache_ttl_seconds)
        except Exception as exc:
            logger.warning("seasonal_seed_cache_set_failed", key=key, error=str(exc))
