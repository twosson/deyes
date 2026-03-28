"""Seed fallback provider for demand discovery.

Provides candidate fallback keywords when user-provided or generated keywords
are unavailable. All outputs must be validated by DemandDiscoveryService before
use in 1688 search.

This service encapsulates the legacy seed generation logic (seasonal, category
hotwords, cold-start) but does NOT authorize their use. It only provides candidates.
"""
from datetime import datetime, timezone
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


class SeedFallbackProvider:
    """Provide candidate fallback keywords for demand discovery.

    This service provides fallback keyword candidates when:
    1. User provides no keywords
    2. Keyword generation fails or returns no results
    3. All generated keywords fail demand validation

    All outputs are candidates only - they must be validated by DemandDiscoveryService
    before being used in 1688 search.
    """

    # Seasonal seed map (from alibaba_1688_adapter.py)
    SEASONAL_SEED_MAP = {
        "spring": ["春季新品", "春装", "春季热销"],
        "summer": ["夏季新品", "夏装", "夏季热销"],
        "autumn": ["秋季新品", "秋装", "秋季热销"],
        "winter": ["冬季新品", "冬装", "冬季热销"],
    }

    # Category hotword map (from alibaba_1688_adapter.py)
    CATEGORY_HOTWORD_MAP = {
        "手机配件": ["磁吸手机壳", "透明手机壳", "防摔手机壳"],
        "家居收纳": ["桌面收纳盒", "衣柜收纳", "厨房收纳"],
        "小家电": ["便携小风扇", "迷你加湿器", "桌面暖风机"],
    }

    # Cold start seeds (from config)
    DEFAULT_COLD_START_SEEDS = ["热销", "新品", "爆款", "推荐"]

    def __init__(
        self,
        cold_start_seeds: Optional[list[str]] = None,
        seasonal_seed_limit: int = 1,
        category_hotword_limit: int = 3,
    ):
        """Initialize seed fallback provider.

        Args:
            cold_start_seeds: Cold start seed list (default: ["热销", "新品", "爆款", "推荐"])
            seasonal_seed_limit: Maximum seasonal seeds to return (default: 1)
            category_hotword_limit: Maximum category hotwords to return (default: 3)
        """
        self.cold_start_seeds = cold_start_seeds or self.DEFAULT_COLD_START_SEEDS
        self.seasonal_seed_limit = seasonal_seed_limit
        self.category_hotword_limit = category_hotword_limit
        self.logger = logger

    async def get_candidate_fallback_keywords(
        self,
        *,
        category: Optional[str] = None,
        region: Optional[str] = None,
        limit: int = 10,
    ) -> list[tuple[str, str]]:
        """Get candidate fallback keywords.

        Returns candidate keywords with their source types. These are NOT validated
        and must be passed through DemandDiscoveryService before use.

        Priority order:
        1. Category hotwords (if category provided)
        2. Seasonal seeds (current season)
        3. Cold start seeds (generic fallback)

        Args:
            category: Product category (optional)
            region: Target region (optional, for future use)
            limit: Maximum keywords to return

        Returns:
            List of (keyword, source_type) tuples
            source_type: "category_hotword", "seasonal", "cold_start"
        """
        _ = region  # Reserved for future use
        candidates: list[tuple[str, str]] = []

        # 1. Category hotwords (if category provided)
        if category:
            hotwords = self._get_category_hotwords(category)
            for hotword in hotwords[: self.category_hotword_limit]:
                candidates.append((hotword, "category_hotword"))
                if len(candidates) >= limit:
                    return candidates

        # 2. Seasonal seeds
        month = datetime.now(timezone.utc).month
        if month in {3, 4, 5}:
            season = "spring"
        elif month in {6, 7, 8}:
            season = "summer"
        elif month in {9, 10, 11}:
            season = "autumn"
        else:
            season = "winter"

        seasonal_seeds = self.SEASONAL_SEED_MAP.get(season, [])
        for seed in seasonal_seeds[: self.seasonal_seed_limit]:
            candidates.append((seed, "seasonal"))
            if len(candidates) >= limit:
                return candidates

        # 3. Cold start seeds
        for seed in self.cold_start_seeds:
            candidates.append((seed, "cold_start"))
            if len(candidates) >= limit:
                return candidates

        self.logger.info(
            "fallback_keywords_generated",
            category=category,
            count=len(candidates),
            sources=[source for _, source in candidates],
        )

        return candidates

    def _get_category_hotwords(self, category: str) -> list[str]:
        """Get category-specific hotwords.

        Args:
            category: Product category

        Returns:
            List of hotword strings
        """
        # Normalize category
        normalized_category = category.strip().lower() if category else ""

        # Direct lookup
        direct_match = self.CATEGORY_HOTWORD_MAP.get(normalized_category)
        if direct_match:
            return direct_match

        # Fallback: return empty list (no hotwords for unknown categories)
        return []
