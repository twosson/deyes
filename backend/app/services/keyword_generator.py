"""Keyword generation service for dynamic product discovery.

Phase 3 Enhancement: Automatically generate trending keywords using AlphaShop
and expand them into long-tail keywords for product selection.

Features:
- Generate trending keywords by category using AlphaShop keyword search
- Expand keywords using AlphaShop related keyword variants
- Cache results in Redis (24h TTL)
- Support multiple regions
- Preserve fallback keyword generation when AlphaShop is unavailable
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from typing import Any, Optional

from app.clients.alphashop import AlphaShopClient
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class KeywordResult:
    """Result of keyword generation."""

    keyword: str
    search_volume: int
    trend_score: int
    competition_density: str
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
    """Generate trending keywords for product discovery."""

    def __init__(
        self,
        redis_client=None,
        cache_ttl_seconds: int = 86400,
        enable_cache: bool = True,
        min_trend_score: int = 20,
        alphashop_client: AlphaShopClient | None = None,
        platform: str | None = None,
        listing_time: str | None = None,
    ):
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.enable_cache = enable_cache
        self.min_trend_score = min_trend_score
        self.logger = logger
        self.settings = get_settings().model_copy(deep=True)
        self._alphashop_client = alphashop_client
        self._created_client = False
        self.platform = platform or self.settings.keyword_generation_platform
        self.listing_time = listing_time or self.settings.keyword_generation_listing_time

    async def _get_alphashop_client(self) -> AlphaShopClient | None:
        """Get or create AlphaShop client when credentials are configured."""
        if self._alphashop_client is not None:
            return self._alphashop_client
        if not self.settings.alphashop_enabled:
            return None
        if not self.settings.alphashop_api_key or not self.settings.alphashop_secret_key:
            return None
        self._alphashop_client = AlphaShopClient()
        self._created_client = True
        return self._alphashop_client

    async def close(self) -> None:
        """Close underlying AlphaShop client when owned by this instance."""
        if self._created_client and self._alphashop_client is not None:
            await self._alphashop_client.close()
            self._alphashop_client = None
            self._created_client = False

    async def generate_trending_keywords(
        self,
        category: str,
        region: str = "US",
        limit: int = 50,
    ) -> list[KeywordResult]:
        """Generate trending keywords for a category."""
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
            platform=self.platform,
        )

        keywords = await self._generate_from_alphashop(category, region, limit)
        if not keywords:
            keywords = self._fallback_keywords(category, region, limit)

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
        """Generate keywords for real-time product selection."""
        self.logger.info(
            "selection_keyword_generation_started",
            category=category,
            region=region,
            limit=limit,
        )

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

        if expand_top_n > 0:
            expanded_keywords = []
            for keyword_result in base_keywords[:expand_top_n]:
                try:
                    related = await self.expand_keyword(
                        keyword=keyword_result.keyword,
                        region=region,
                        limit=5,
                    )
                    for related_kw in related:
                        expanded_keywords.append(
                            KeywordResult(
                                keyword=related_kw,
                                search_volume=max(keyword_result.search_volume // 2, 100),
                                trend_score=max(keyword_result.trend_score - 10, 0),
                                competition_density=keyword_result.competition_density,
                                related_keywords=[],
                                category=category,
                                region=region,
                            )
                        )
                except Exception as exc:
                    self.logger.warning(
                        "selection_keyword_expansion_failed",
                        keyword=keyword_result.keyword,
                        error=str(exc),
                    )

            all_keywords = base_keywords + expanded_keywords
            seen = set()
            unique_keywords = []
            for kw in all_keywords:
                normalized = kw.keyword.lower().strip()
                if normalized not in seen:
                    seen.add(normalized)
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
        """Expand a keyword into related long-tail keywords."""
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

    async def _generate_from_alphashop(
        self,
        category: str,
        region: str,
        limit: int,
    ) -> list[KeywordResult]:
        """Generate keywords using AlphaShop keyword search."""
        client = await self._get_alphashop_client()
        if client is None:
            self.logger.warning(
                "alphashop_keyword_generation_unavailable",
                category=category,
                region=region,
                reason="missing_configuration_or_disabled",
            )
            return []

        try:
            response = await client.search_keywords(
                platform=self.platform,
                region=region,
                keyword=category,
                listing_time=self.listing_time,
            )
        except Exception as exc:
            self.logger.error(
                "alphashop_keyword_generation_failed",
                category=category,
                region=region,
                error=str(exc),
            )
            return []

        keyword_list = response.get("keyword_list") or []
        results: list[KeywordResult] = []
        seen: set[str] = set()

        for item in keyword_list:
            keyword = self._extract_keyword_text(item)
            if not keyword:
                continue
            normalized = keyword.lower().strip()
            if normalized in seen:
                continue
            if not self._is_category_relevant(keyword, category):
                continue

            trend_score = self._extract_trend_score_from_alphashop(item)
            if trend_score < self.min_trend_score:
                continue

            seen.add(normalized)
            results.append(
                KeywordResult(
                    keyword=keyword,
                    search_volume=self._extract_search_volume_from_alphashop(item),
                    trend_score=trend_score,
                    competition_density=self._extract_competition_density_from_alphashop(item, keyword),
                    related_keywords=self._extract_related_keywords_from_item(item, keyword),
                    category=category,
                    region=region,
                )
            )

            if len(results) >= limit:
                break

        results.sort(key=lambda x: x.trend_score, reverse=True)
        return results[:limit]

    async def _generate_from_pytrends(
        self,
        category: str,
        region: str,
        limit: int,
    ) -> list[KeywordResult]:
        """Legacy compatibility shim retained for older tests and call sites."""
        return await self._generate_from_alphashop(category, region, limit)

    async def _get_related_keywords(self, keyword: str, region: str) -> list[str]:
        """Get related keywords using AlphaShop keyword search."""
        client = await self._get_alphashop_client()
        if client is None:
            return []

        try:
            response = await client.search_keywords(
                platform=self.platform,
                region=region,
                keyword=keyword,
                listing_time=self.listing_time,
            )
        except Exception as exc:
            self.logger.warning(
                "related_keywords_fetch_failed",
                keyword=keyword,
                region=region,
                error=str(exc),
            )
            return []

        related_keywords: list[str] = []
        seen = {keyword.lower().strip()}

        for item in response.get("keyword_list") or []:
            candidate = self._extract_keyword_text(item)
            if not candidate:
                continue
            normalized = candidate.lower().strip()
            if normalized in seen:
                continue
            seen.add(normalized)
            related_keywords.append(candidate)

        return related_keywords

    def _extract_keyword_text(self, item: dict[str, Any]) -> str | None:
        """Extract keyword text from AlphaShop keyword result variants."""
        for key in ("keyword", "query", "searchKeyword", "keywordName", "term", "title"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        radar = item.get("radar")
        if isinstance(radar, dict):
            for key in ("keyword", "query", "searchKeyword"):
                value = radar.get(key)
                if isinstance(value, str) and value.strip():
                    return value.strip()

        return None

    def _extract_related_keywords_from_item(self, item: dict[str, Any], keyword: str) -> list[str]:
        """Extract related keywords from a keyword result when present."""
        candidates: list[str] = []

        for key in ("relatedKeywords", "relatedKeywordList", "keywordList"):
            value = item.get(key)
            if isinstance(value, list):
                for entry in value:
                    if isinstance(entry, str) and entry.strip():
                        candidates.append(entry.strip())
                    elif isinstance(entry, dict):
                        extracted = self._extract_keyword_text(entry)
                        if extracted:
                            candidates.append(extracted)

        radar = item.get("radar")
        if isinstance(radar, dict):
            property_list = radar.get("propertyList")
            if isinstance(property_list, list):
                for entry in property_list:
                    if isinstance(entry, dict):
                        value = entry.get("value") or entry.get("name")
                        if isinstance(value, str) and value.strip():
                            candidates.append(value.strip())

        seen = {keyword.lower().strip()}
        unique: list[str] = []
        for candidate in candidates:
            normalized = candidate.lower().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                unique.append(candidate)
        return unique[:10]

    def _extract_search_volume_from_alphashop(self, item: dict[str, Any]) -> int:
        """Map AlphaShop metrics into approximate monthly search volume."""
        direct_volume = self._coerce_int(item.get("searchVolume"))
        if direct_volume is not None:
            return max(direct_volume, 100)

        sales_info = item.get("salesInfo") if isinstance(item.get("salesInfo"), dict) else {}
        sales_volume = self._coerce_int(sales_info.get("searchVolume"))
        if sales_volume is not None:
            return max(sales_volume, 100)

        sold_cnt_30d = self._coerce_int(item.get("soldCnt30d"))
        if sold_cnt_30d is None:
            sold_cnt_30d = self._coerce_int(sales_info.get("soldCnt30d"))
        if sold_cnt_30d is not None:
            return max(sold_cnt_30d * 10, 100)

        search_rank = self._coerce_int(item.get("searchRank"))
        if search_rank is not None:
            if search_rank <= 1000:
                return 10000
            if search_rank <= 5000:
                return 5000
            if search_rank <= 20000:
                return 2000
            return 500

        opp_score = self._coerce_int(item.get("oppScore"))
        if opp_score is not None:
            return self._estimate_search_volume_from_interest(opp_score)

        return 100

    def _extract_trend_score_from_alphashop(self, item: dict[str, Any]) -> int:
        """Extract a normalized 0-100 trend score from AlphaShop keyword data."""
        opp_score = self._coerce_int(item.get("oppScore"))
        if opp_score is not None:
            return max(0, min(opp_score, 100))

        rank_trends = self._extract_rank_trends(item)
        if rank_trends:
            avg_rank = sum(rank_trends) / len(rank_trends)
            if avg_rank <= 100:
                return 90
            if avg_rank <= 500:
                return 80
            if avg_rank <= 2000:
                return 65
            if avg_rank <= 10000:
                return 45
            return 25

        search_rank = self._coerce_int(item.get("searchRank"))
        if search_rank is not None:
            if search_rank <= 100:
                return 90
            if search_rank <= 1000:
                return 75
            if search_rank <= 5000:
                return 60
            if search_rank <= 20000:
                return 40
            return 20

        return self.min_trend_score

    def _extract_competition_density_from_alphashop(self, item: dict[str, Any], keyword: str) -> str:
        """Map AlphaShop keyword metrics into competition density buckets."""
        search_rank = self._coerce_int(item.get("searchRank"))
        if search_rank is not None:
            if search_rank <= 1000:
                return "high"
            if search_rank <= 10000:
                return "medium"
            return "low"

        opp_score = self._coerce_int(item.get("oppScore"))
        if opp_score is not None:
            if opp_score >= 80:
                return "high"
            if opp_score >= 50:
                return "medium"
            return "low"

        return self._heuristic_competition_assessment(keyword)

    def _extract_rank_trends(self, item: dict[str, Any]) -> list[int]:
        """Extract numeric rank trend points from AlphaShop result variants."""
        raw = item.get("rankTrends")
        if not isinstance(raw, list):
            return []

        values: list[int] = []
        for entry in raw:
            if isinstance(entry, (int, float)):
                values.append(int(entry))
            elif isinstance(entry, str):
                try:
                    values.append(int(float(entry)))
                except Exception:
                    continue
            elif isinstance(entry, dict):
                for key in ("rank", "value", "searchRank"):
                    candidate = self._coerce_int(entry.get(key))
                    if candidate is not None:
                        values.append(candidate)
                        break
        return values

    def _is_category_relevant(self, keyword: str, category: str) -> bool:
        """Check if keyword is relevant to category."""
        keyword_lower = keyword.lower()
        category_lower = category.lower()

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

        if category_lower in category_keywords:
            for cat_kw in category_keywords[category_lower]:
                if cat_kw in keyword_lower:
                    return True

        return True

    def _estimate_search_volume_from_interest(self, avg_interest: int) -> int:
        """Estimate monthly search volume from normalized interest score."""
        if avg_interest >= 80:
            return 10000
        if avg_interest >= 60:
            return 5000
        if avg_interest >= 40:
            return 2000
        if avg_interest >= 20:
            return 500
        if avg_interest >= 10:
            return 200
        return 100

    def _heuristic_competition_assessment(self, keyword: str) -> str:
        """Assess competition density using heuristic rules."""
        word_count = len(keyword.split())

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

        if word_count <= 2:
            return "high"
        if word_count <= 4:
            return "medium"
        return "low"

    def _region_to_geo(self, region: str) -> str:
        """Legacy compatibility mapping retained for tests and older code paths."""
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
        return region_map.get((region or "US").upper(), "united_states")

    def _region_to_geo_code(self, region: str) -> str:
        """Legacy compatibility mapping retained for tests and older code paths."""
        region_map = {
            "UK": "GB",
        }
        return region_map.get((region or "US").upper(), (region or "US").upper())

    def _fallback_keywords(self, category: str, region: str, limit: int) -> list[KeywordResult]:
        """Fallback keywords when AlphaShop is unavailable."""
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

        except Exception as exc:
            self.logger.warning(
                "cache_get_failed",
                category=category,
                region=region,
                error=str(exc),
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

        except Exception as exc:
            self.logger.warning(
                "cache_save_failed",
                category=category,
                region=region,
                error=str(exc),
            )

    def _coerce_int(self, value: Any) -> int | None:
        """Convert value to int when possible."""
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            try:
                return int(float(value))
            except Exception:
                return None
        return None
