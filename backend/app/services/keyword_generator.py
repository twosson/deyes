"""Keyword generation service for dynamic product discovery.

Phase 3 Enhancement: Automatically generate trending keywords using Google Trends
and expand them into long-tail keywords for product selection.

Features:
- Generate trending keywords by category using pytrends
- Expand keywords using related queries
- Cache results in Redis (24h TTL)
- Support multiple regions
"""
import asyncio
import hashlib
import json
from dataclasses import dataclass, field
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class KeywordResult:
    """Result of keyword generation."""

    keyword: str
    search_volume: int
    trend_score: int  # 0-100, based on Google Trends interest
    competition_density: str  # "low", "medium", "high"
    related_keywords: list[str] = field(default_factory=list)
    category: Optional[str] = None
    region: str = "US"

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "keyword": self.keyword,
            "search_volume": self.search_volume,
            "trend_score": self.trend_score,
            "competition_density": self.competition_density,
            "related_keywords": self.related_keywords,
            "category": self.category,
            "region": self.region,
        }


class KeywordGenerator:
    """Generate trending keywords for product discovery.

    Uses Google Trends (pytrends) to identify trending keywords and expand them
    into long-tail variations for better product discovery.
    """

    def __init__(
        self,
        redis_client=None,
        cache_ttl_seconds: int = 86400,  # 24 hours
        enable_cache: bool = True,
        min_trend_score: int = 20,  # Minimum trend score to include
    ):
        """Initialize keyword generator.

        Args:
            redis_client: Redis client for caching (optional)
            cache_ttl_seconds: Cache TTL in seconds (default: 24 hours)
            enable_cache: Whether to enable caching (default: True)
            min_trend_score: Minimum trend score to include keyword (default: 20)
        """
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.enable_cache = enable_cache
        self.min_trend_score = min_trend_score
        self.logger = logger

    async def generate_trending_keywords(
        self,
        category: str,
        region: str = "US",
        limit: int = 50,
    ) -> list[KeywordResult]:
        """Generate trending keywords for a category.

        Args:
            category: Product category (e.g., "electronics", "fashion")
            region: Region code (e.g., "US", "UK", "JP")
            limit: Maximum number of keywords to return

        Returns:
            List of KeywordResult objects sorted by trend score (descending)
        """
        # Check cache first
        if self.enable_cache and self.redis_client:
            cached_results = await self._get_from_cache(category, region)
            if cached_results:
                self.logger.info(
                    "keyword_generation_cache_hit",
                    category=category,
                    region=region,
                    count=len(cached_results),
                )
                return cached_results[:limit]

        self.logger.info(
            "keyword_generation_started",
            category=category,
            region=region,
            limit=limit,
        )

        # Generate keywords using pytrends
        keywords = await self._generate_from_pytrends(category, region, limit)

        # Save to cache
        if self.enable_cache and self.redis_client:
            await self._save_to_cache(category, region, keywords)

        self.logger.info(
            "keyword_generation_completed",
            category=category,
            region=region,
            count=len(keywords),
        )

        return keywords

    async def generate_selection_keywords(
        self,
        *,
        category: Optional[str] = None,
        region: str = "US",
        limit: int = 20,
        expand_top_n: int = 5,
    ) -> list[KeywordResult]:
        """Generate keywords for real-time product selection.

        This method is optimized for product selection flow (vs nightly research).
        It generates fewer keywords and optionally expands top results.

        Args:
            category: Product category (optional, defaults to "electronics")
            region: Region code (default: "US")
            limit: Maximum base keywords to generate (default: 20)
            expand_top_n: Number of top keywords to expand (default: 5)

        Returns:
            List of KeywordResult objects
        """
        self.logger.info(
            "selection_keyword_generation_started",
            category=category,
            region=region,
            limit=limit,
        )

        # Generate base keywords
        base_keywords = await self.generate_trending_keywords(
            category=category or "electronics",
            region=region,
            limit=limit,
        )

        if not base_keywords:
            self.logger.warning(
                "selection_keyword_generation_no_base_keywords",
                category=category,
                region=region,
            )
            return []

        # Optionally expand top keywords
        if expand_top_n > 0:
            expanded_keywords = []
            for keyword_result in base_keywords[:expand_top_n]:
                try:
                    related = await self.expand_keyword(
                        keyword=keyword_result.keyword,
                        region=region,
                        limit=5,  # Limit expansions per keyword
                    )
                    # Convert related strings to KeywordResult objects
                    for related_kw in related:
                        expanded_keywords.append(
                            KeywordResult(
                                keyword=related_kw,
                                search_volume=keyword_result.search_volume // 2,  # Estimate
                                trend_score=keyword_result.trend_score - 10,  # Slightly lower
                                competition_density=keyword_result.competition_density,
                                related_keywords=[],
                                category=category,
                                region=region,
                            )
                        )
                except Exception as e:
                    self.logger.warning(
                        "selection_keyword_expansion_failed",
                        keyword=keyword_result.keyword,
                        error=str(e),
                    )

            # Combine base and expanded, deduplicate
            all_keywords = base_keywords + expanded_keywords
            seen = set()
            unique_keywords = []
            for kw in all_keywords:
                if kw.keyword not in seen:
                    seen.add(kw.keyword)
                    unique_keywords.append(kw)

            self.logger.info(
                "selection_keyword_generation_completed",
                category=category,
                base_count=len(base_keywords),
                expanded_count=len(expanded_keywords),
                total_unique=len(unique_keywords),
            )

            return unique_keywords[:limit]

        return base_keywords

    async def expand_keyword(
        self,
        keyword: str,
        region: str = "US",
        limit: int = 20,
    ) -> list[str]:
        """Expand a keyword into related long-tail keywords.

        Args:
            keyword: Base keyword to expand
            region: Region code
            limit: Maximum number of related keywords to return

        Returns:
            List of related keywords
        """
        self.logger.info(
            "keyword_expansion_started",
            keyword=keyword,
            region=region,
            limit=limit,
        )

        related_keywords = await self._get_related_keywords(keyword, region)

        self.logger.info(
            "keyword_expansion_completed",
            keyword=keyword,
            count=len(related_keywords),
        )

        return related_keywords[:limit]

    async def _generate_from_pytrends(
        self,
        category: str,
        region: str,
        limit: int,
    ) -> list[KeywordResult]:
        """Generate keywords using pytrends.

        Strategy:
        1. Get trending searches for the region
        2. Filter by category relevance
        3. Get interest over time for each keyword
        4. Expand with related queries
        5. Assess competition density
        """

        def _fetch_trending_keywords():
            try:
                from pytrends.request import TrendReq

                pytrends = TrendReq(hl="en-US", tz=360)

                # Get trending searches
                geo = self._region_to_geo(region)
                trending_df = pytrends.trending_searches(pn=geo)

                if trending_df.empty:
                    self.logger.warning(
                        "no_trending_searches",
                        region=region,
                        category=category,
                    )
                    return []

                # Get top trending keywords
                trending_keywords = trending_df[0].tolist()[:limit * 2]  # Get more for filtering

                results = []
                for kw in trending_keywords:
                    # Filter by category relevance (simple heuristic)
                    if not self._is_category_relevant(kw, category):
                        continue

                    # Get interest over time
                    try:
                        geo_code = self._region_to_geo_code(region)
                        pytrends.build_payload([kw], timeframe="today 3-m", geo=geo_code)
                        interest_df = pytrends.interest_over_time()

                        if interest_df.empty or kw not in interest_df.columns:
                            continue

                        # Calculate trend score (average interest)
                        avg_interest = int(interest_df[kw].mean())

                        if avg_interest < self.min_trend_score:
                            continue

                        # Estimate search volume
                        search_volume = self._estimate_search_volume_from_interest(avg_interest)

                        # Get related queries
                        related_queries = pytrends.related_queries()
                        related_keywords = []
                        if kw in related_queries and related_queries[kw]["top"] is not None:
                            related_keywords = (
                                related_queries[kw]["top"]["query"].head(10).tolist()
                            )

                        # Assess competition density (heuristic based on keyword length)
                        competition_density = self._heuristic_competition_assessment(kw)

                        results.append(
                            KeywordResult(
                                keyword=kw,
                                search_volume=search_volume,
                                trend_score=avg_interest,
                                competition_density=competition_density,
                                related_keywords=related_keywords,
                                category=category,
                                region=region,
                            )
                        )

                        if len(results) >= limit:
                            break

                    except Exception as e:
                        self.logger.warning(
                            "keyword_interest_fetch_failed",
                            keyword=kw,
                            error=str(e),
                        )
                        continue

                # Sort by trend score (descending)
                results.sort(key=lambda x: x.trend_score, reverse=True)
                return results

            except ImportError:
                self.logger.error("pytrends_not_installed")
                return self._fallback_keywords(category, region, limit)
            except Exception as e:
                self.logger.error(
                    "pytrends_fetch_failed",
                    category=category,
                    region=region,
                    error=str(e),
                )
                return self._fallback_keywords(category, region, limit)

        return await asyncio.to_thread(_fetch_trending_keywords)

    async def _get_related_keywords(self, keyword: str, region: str) -> list[str]:
        """Get related keywords using pytrends."""

        def _fetch_related():
            try:
                from pytrends.request import TrendReq

                pytrends = TrendReq(hl="en-US", tz=360)
                geo_code = self._region_to_geo_code(region)

                pytrends.build_payload([keyword], timeframe="today 3-m", geo=geo_code)
                related_queries = pytrends.related_queries()

                if keyword not in related_queries or related_queries[keyword]["top"] is None:
                    return []

                # Get top related queries
                related_keywords = related_queries[keyword]["top"]["query"].tolist()
                return related_keywords

            except Exception as e:
                self.logger.warning(
                    "related_keywords_fetch_failed",
                    keyword=keyword,
                    error=str(e),
                )
                return []

        return await asyncio.to_thread(_fetch_related)

    def _is_category_relevant(self, keyword: str, category: str) -> bool:
        """Check if keyword is relevant to category (simple heuristic).

        This is a basic implementation. In production, you might want to use
        a more sophisticated approach (e.g., LLM classification, keyword mapping).
        """
        keyword_lower = keyword.lower()
        category_lower = category.lower()

        # Category-specific keywords
        category_keywords = {
            "electronics": [
                "phone",
                "laptop",
                "tablet",
                "headphone",
                "speaker",
                "charger",
                "cable",
                "camera",
                "watch",
                "earbuds",
            ],
            "fashion": [
                "dress",
                "shirt",
                "pants",
                "shoes",
                "bag",
                "jacket",
                "hat",
                "jewelry",
                "watch",
                "sunglasses",
            ],
            "home": [
                "furniture",
                "decor",
                "kitchen",
                "bedding",
                "storage",
                "lighting",
                "rug",
                "curtain",
                "pillow",
                "organizer",
            ],
            "beauty": [
                "makeup",
                "skincare",
                "perfume",
                "hair",
                "nail",
                "cosmetic",
                "serum",
                "cream",
                "lipstick",
                "foundation",
            ],
            "sports": [
                "fitness",
                "yoga",
                "running",
                "gym",
                "exercise",
                "bike",
                "ball",
                "equipment",
                "outdoor",
                "camping",
            ],
        }

        # Check if any category keyword is in the search keyword
        if category_lower in category_keywords:
            for cat_kw in category_keywords[category_lower]:
                if cat_kw in keyword_lower:
                    return True

        # Default: accept all (can be made stricter)
        return True

    def _estimate_search_volume_from_interest(self, avg_interest: int) -> int:
        """Estimate monthly search volume from Google Trends interest score.

        This is a rough estimation. Actual search volume requires Google Ads API.
        """
        if avg_interest >= 80:
            return 10000
        elif avg_interest >= 60:
            return 5000
        elif avg_interest >= 40:
            return 2000
        elif avg_interest >= 20:
            return 500
        elif avg_interest >= 10:
            return 200
        else:
            return 100

    def _heuristic_competition_assessment(self, keyword: str) -> str:
        """Assess competition density using heuristic rules.

        Rules:
        - Generic keywords (1-2 words) → HIGH
        - Specific keywords (3-4 words) → MEDIUM
        - Long-tail keywords (5+ words) → LOW
        - Brand names → HIGH
        """
        word_count = len(keyword.split())

        # Check for brand names (common brands)
        brand_keywords = [
            "iphone",
            "samsung",
            "nike",
            "adidas",
            "apple",
            "sony",
            "lg",
            "dell",
            "hp",
        ]
        if any(brand in keyword.lower() for brand in brand_keywords):
            return "high"

        # Word count heuristic
        if word_count <= 2:
            return "high"
        elif word_count <= 4:
            return "medium"
        else:
            return "low"

    def _region_to_geo(self, region: str) -> str:
        """Convert region code to pytrends geo code for trending_searches.

        trending_searches uses country names like 'united_states'.
        """
        region_map = {
            "US": "united_states",
            "UK": "united_kingdom",
            "GB": "united_kingdom",
            "JP": "japan",
            "DE": "germany",
            "FR": "france",
            "CA": "canada",
            "AU": "australia",
        }
        return region_map.get(region.upper(), "united_states")

    def _region_to_geo_code(self, region: str) -> str:
        """Convert region code to pytrends geo code for build_payload.

        build_payload uses ISO country codes like 'US', 'GB'.
        """
        region_map = {
            "UK": "GB",  # UK → GB
        }
        return region_map.get(region.upper(), region.upper())

    def _fallback_keywords(self, category: str, region: str, limit: int) -> list[KeywordResult]:
        """Fallback keywords when pytrends fails.

        Returns a predefined list of popular keywords by category.
        """
        self.logger.warning(
            "using_fallback_keywords",
            category=category,
            region=region,
        )

        fallback_data = {
            "electronics": [
                ("wireless earbuds", 5000, 75, "medium"),
                ("phone case", 8000, 80, "high"),
                ("laptop stand", 2000, 60, "medium"),
                ("usb c cable", 6000, 70, "high"),
                ("bluetooth speaker", 4000, 65, "medium"),
            ],
            "fashion": [
                ("summer dress", 3000, 70, "medium"),
                ("running shoes", 7000, 80, "high"),
                ("leather bag", 2500, 60, "medium"),
                ("sunglasses", 5000, 75, "high"),
                ("winter jacket", 4000, 65, "medium"),
            ],
            "home": [
                ("storage organizer", 2000, 60, "medium"),
                ("led lights", 4000, 70, "medium"),
                ("kitchen gadgets", 3000, 65, "medium"),
                ("throw pillow", 2500, 55, "medium"),
                ("wall decor", 3500, 60, "medium"),
            ],
        }

        keywords_data = fallback_data.get(category.lower(), fallback_data["electronics"])

        results = []
        for kw, vol, score, comp in keywords_data[:limit]:
            results.append(
                KeywordResult(
                    keyword=kw,
                    search_volume=vol,
                    trend_score=score,
                    competition_density=comp,
                    related_keywords=[],
                    category=category,
                    region=region,
                )
            )

        return results

    def _build_cache_key(self, category: str, region: str) -> str:
        """Build cache key for keyword generation results."""
        category_hash = hashlib.md5(category.encode("utf-8")).hexdigest()
        return f"keyword_generation:{category_hash}:{region}"

    async def _get_from_cache(
        self, category: str, region: str
    ) -> Optional[list[KeywordResult]]:
        """Get keyword generation results from cache."""
        if not self.redis_client:
            return None

        try:
            cache_key = self._build_cache_key(category, region)
            cached_data = await self.redis_client.get(cache_key)

            if cached_data:
                results_data = json.loads(cached_data)
                results = [
                    KeywordResult(
                        keyword=r["keyword"],
                        search_volume=r["search_volume"],
                        trend_score=r["trend_score"],
                        competition_density=r["competition_density"],
                        related_keywords=r.get("related_keywords", []),
                        category=r.get("category"),
                        region=r.get("region", region),
                    )
                    for r in results_data
                ]
                return results

        except Exception as e:
            self.logger.warning(
                "cache_get_failed",
                category=category,
                region=region,
                error=str(e),
            )

        return None

    async def _save_to_cache(
        self, category: str, region: str, results: list[KeywordResult]
    ) -> None:
        """Save keyword generation results to cache."""
        if not self.redis_client:
            return

        try:
            cache_key = self._build_cache_key(category, region)
            results_data = [r.to_dict() for r in results]
            cached_data = json.dumps(results_data)

            await self.redis_client.set(
                cache_key,
                cached_data,
                ex=self.cache_ttl_seconds,
            )

            self.logger.info(
                "cache_saved",
                category=category,
                region=region,
                count=len(results),
                ttl=self.cache_ttl_seconds,
            )

        except Exception as e:
            self.logger.warning(
                "cache_save_failed",
                category=category,
                region=region,
                error=str(e),
            )
