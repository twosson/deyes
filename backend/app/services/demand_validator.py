"""Demand validation service.

Validates overseas demand before product scraping to avoid wasting resources
on low-demand or high-competition products.

Phase 1 of product selection optimization plan.

Features:
- AlphaShop keyword search integration (primary, replaces pytrends)
- Redis caching (24h TTL)
- Helium 10 API support (optional, retained for enhanced validation)
- Competition density assessment
- Trend direction classification
"""
import asyncio
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING, Optional

if TYPE_CHECKING:
    from app.services.keyword_legitimizer import ValidKeyword

from app.clients.alphashop import AlphaShopClient
from app.clients.redis import RedisClient
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class CompetitionDensity(str, Enum):
    """Competition density level."""
    LOW = "low"  # <2000 search results
    MEDIUM = "medium"  # 2000-5000 search results
    HIGH = "high"  # >5000 search results
    UNKNOWN = "unknown"  # Unable to determine


class TrendDirection(str, Enum):
    """Trend direction."""
    RISING = "rising"  # +20% YoY or more
    STABLE = "stable"  # -20% to +20% YoY
    DECLINING = "declining"  # -20% YoY or more
    UNKNOWN = "unknown"  # Unable to determine


@dataclass
class DemandValidationResult:
    """Demand validation result."""

    keyword: str
    search_volume: Optional[int]  # Monthly search volume
    competition_density: CompetitionDensity
    trend_direction: TrendDirection
    trend_growth_rate: Optional[Decimal]  # YoY growth rate (e.g., 0.25 = 25%)

    # 1688 cross-border signals (future enhancement)
    hot_sell_rank: Optional[int] = None
    repurchase_rate: Optional[Decimal] = None
    lead_time_days: Optional[int] = None

    # Validation decision
    passed: bool = False
    rejection_reasons: list[str] = None

    # Region-specific context (2026-03-28)
    region: Optional[str] = None

    # Category-specific context (2026-03-28)
    category: Optional[str] = None

    # Platform-specific context (2026-03-28)
    platform: Optional[str] = None

    def __post_init__(self):
        """Calculate validation decision with region, category, and platform-specific thresholds."""
        if self.rejection_reasons is None:
            self.rejection_reasons = []

        # Region, category, and platform-specific thresholds
        min_search_volume = self._get_min_search_volume(self.region, self.category, self.platform)
        max_competition_density = self._get_max_competition_density(self.region, self.category, self.platform)

        # Check search volume
        if self.search_volume is not None and self.search_volume < min_search_volume:
            self.rejection_reasons.append(
                f"Search volume too low: {self.search_volume} < {min_search_volume} (region: {self.region or 'US'}, category: {self.category or 'general'}, platform: {self.platform or 'general'})"
            )

        # Check competition density
        if self._is_competition_too_high(self.competition_density, max_competition_density):
            self.rejection_reasons.append(
                f"Competition density too high: {self.competition_density.value} (max: {max_competition_density.value}, region: {self.region or 'US'}, category: {self.category or 'general'}, platform: {self.platform or 'general'})"
            )

        # Check trend direction
        if self.trend_direction == TrendDirection.DECLINING:
            self.rejection_reasons.append("Market trend declining")

        # Passed if no rejection reasons
        self.passed = len(self.rejection_reasons) == 0

    def _get_min_search_volume(
        self,
        region: Optional[str],
        category: Optional[str],
        platform: Optional[str],
    ) -> int:
        """Get minimum search volume threshold for region, category, and platform."""
        region_baseline = self._get_region_baseline_search_volume(region)
        category_multiplier = self._get_category_search_volume_multiplier(category)
        platform_multiplier = self._get_platform_search_volume_multiplier(platform)
        return int(region_baseline * category_multiplier * platform_multiplier)

    def _get_region_baseline_search_volume(self, region: Optional[str]) -> int:
        """Get baseline search volume threshold for region."""
        region_upper = (region or "US").upper()
        thresholds = {
            "US": 500,
            "UK": 350,
            "GB": 350,
            "DE": 400,
            "FR": 400,
            "ES": 350,
            "IT": 350,
            "CA": 400,
            "AU": 400,
            "JP": 600,
            "CN": 800,
            "BR": 300,
            "MX": 300,
            "RU": 400,
        }
        return thresholds.get(region_upper, 500)

    def _get_category_search_volume_multiplier(self, category: Optional[str]) -> float:
        """Get search volume multiplier for category."""
        if not category:
            return 1.0

        category_lower = category.lower().strip()
        multipliers = {
            "electronics": 0.5,
            "fashion": 0.7,
            "home": 0.8,
            "beauty": 0.9,
            "jewelry": 1.5,
            "sports": 0.8,
        }
        return multipliers.get(category_lower, 1.0)

    def _get_platform_search_volume_multiplier(self, platform: Optional[str]) -> float:
        """Get search volume multiplier for platform.

        Platform demand strictness:
        - Amazon: 1.3x (high fees, high competition, need stronger demand)
        - Rakuten: 1.2x (higher fees)
        - Temu: 0.9x (price-sensitive, fast-moving)
        - AliExpress: 1.0x (baseline)
        - Ozon / Mercado Libre: 1.0x (baseline)
        """
        if not platform:
            return 1.0

        platform_lower = platform.lower().strip()
        multipliers = {
            "amazon": 1.3,
            "rakuten": 1.2,
            "temu": 0.9,
            "aliexpress": 1.0,
            "ozon": 1.0,
            "mercado_libre": 1.0,
            "alibaba_1688": 1.0,
        }
        return multipliers.get(platform_lower, 1.0)

    def _get_max_competition_density(
        self,
        region: Optional[str],
        category: Optional[str],
        platform: Optional[str],
    ) -> CompetitionDensity:
        """Get maximum allowed competition density for region, category, and platform.

        Platform competition tolerance:
        - Amazon / Rakuten: LOW (avoid high-competition markets)
        - Temu / AliExpress / Ozon / Mercado Libre: MEDIUM
        """
        region_upper = (region or "US").upper()

        # Region baseline
        if region_upper in {"CN"}:
            threshold = CompetitionDensity.LOW
        else:
            threshold = CompetitionDensity.MEDIUM

        # Category override
        if category:
            category_lower = category.lower().strip()
            category_overrides = {
                "jewelry": CompetitionDensity.LOW,
                "beauty": CompetitionDensity.LOW,
            }
            if category_lower in category_overrides:
                threshold = self._stricter_competition_density(
                    threshold,
                    category_overrides[category_lower],
                )

        # Platform override
        if platform:
            platform_lower = platform.lower().strip()
            platform_overrides = {
                "amazon": CompetitionDensity.LOW,
                "rakuten": CompetitionDensity.LOW,
            }
            if platform_lower in platform_overrides:
                threshold = self._stricter_competition_density(
                    threshold,
                    platform_overrides[platform_lower],
                )

        return threshold

    def _stricter_competition_density(
        self,
        first: CompetitionDensity,
        second: CompetitionDensity,
    ) -> CompetitionDensity:
        """Return the stricter of two competition thresholds."""
        density_order = {
            CompetitionDensity.LOW: 1,
            CompetitionDensity.MEDIUM: 2,
            CompetitionDensity.HIGH: 3,
            CompetitionDensity.UNKNOWN: 4,
        }
        return first if density_order[first] <= density_order[second] else second

    def _is_competition_too_high(
        self,
        actual: CompetitionDensity,
        max_allowed: CompetitionDensity,
    ) -> bool:
        """Check if competition density exceeds threshold."""
        density_order = {
            CompetitionDensity.LOW: 1,
            CompetitionDensity.MEDIUM: 2,
            CompetitionDensity.HIGH: 3,
            CompetitionDensity.UNKNOWN: 0,
        }
        return density_order.get(actual, 0) > density_order.get(max_allowed, 3)

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "keyword": self.keyword,
            "search_volume": self.search_volume,
            "competition_density": self.competition_density.value,
            "trend_direction": self.trend_direction.value,
            "trend_growth_rate": float(self.trend_growth_rate) if self.trend_growth_rate else None,
            "hot_sell_rank": self.hot_sell_rank,
            "repurchase_rate": float(self.repurchase_rate) if self.repurchase_rate else None,
            "lead_time_days": self.lead_time_days,
            "passed": self.passed,
            "rejection_reasons": self.rejection_reasons,
        }


class DemandValidator:
    """Service for validating overseas demand before product scraping.

    This service implements Phase 1 of the product selection optimization plan:
    - Validate search volume (Google Trends, Helium 10 API)
    - Check trend growth (YoY comparison)
    - Assess competition density (search result count)
    - Extract 1688 cross-border signals (future enhancement)

    Usage:
        validator = DemandValidator()
        result = await validator.validate(
            keyword="phone case",
            category="electronics",
            region="US",
        )

        if result.passed:
            # Proceed with product scraping
            products = await source_adapter.fetch_products(...)
        else:
            # Skip this keyword
            logger.info("demand_validation_failed", reasons=result.rejection_reasons)
    """

    def __init__(
        self,
        min_search_volume: int = 500,
        use_helium10: bool = False,
        helium10_api_key: Optional[str] = None,
        redis_client: Optional[RedisClient] = None,
        cache_ttl_seconds: int = 86400,
        enable_cache: bool = True,
        alphashop_client: AlphaShopClient | None = None,
        platform: str | None = None,
        listing_time: str | None = None,
    ):
        """Initialize demand validator.

        Args:
            min_search_volume: Minimum monthly search volume (default: 500)
            use_helium10: Whether to use Helium 10 API (default: False, use AlphaShop)
            helium10_api_key: Helium 10 API key (required if use_helium10=True)
            redis_client: Redis client for caching (optional, will create if None)
            cache_ttl_seconds: Cache TTL in seconds (default: 86400 = 24 hours)
            enable_cache: Whether to enable caching (default: True)
            alphashop_client: AlphaShop client (optional, will create if None)
            platform: AlphaShop platform (default: from settings)
            listing_time: AlphaShop listing time (default: from settings)
        """
        self.min_search_volume = min_search_volume
        self.use_helium10 = use_helium10
        self.helium10_api_key = helium10_api_key
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.enable_cache = enable_cache
        self.settings = get_settings().model_copy(deep=True)
        self._alphashop_client = alphashop_client
        self._created_client = False
        self.platform = platform or self.settings.keyword_generation_platform
        self.listing_time = listing_time or self.settings.keyword_generation_listing_time

        if use_helium10 and not helium10_api_key:
            logger.warning("helium10_enabled_but_no_api_key", fallback="alphashop")
            self.use_helium10 = False

    async def validate(
        self,
        keyword: str,
        category: Optional[str] = None,
        region: Optional[str] = "US",
        platform: Optional[str] = None,
    ) -> DemandValidationResult:
        """Validate demand for a keyword.

        Uses Redis cache to avoid repeated API calls to Google Trends.
        Cache key format: demand_validation:{keyword}:{region}
        Cache TTL: 24 hours (configurable)

        Args:
            keyword: Search keyword to validate
            category: Product category (optional, for category-specific thresholds)
            region: Target region (default: "US")

        Returns:
            DemandValidationResult with validation decision
        """
        logger.info(
            "demand_validation_started",
            keyword=keyword,
            category=category,
            region=region,
        )

        # Step 1: Check cache
        if self.enable_cache:
            cached_result = await self._get_from_cache(keyword, region, category, platform)
            if cached_result:
                logger.info(
                    "demand_validation_cache_hit",
                    keyword=keyword,
                    region=region,
                    category=category,
                    platform=platform,
                )
                return cached_result

        # Step 2: Get search volume and trend
        search_volume, trend_growth_rate, trend_direction = await self._get_search_trends(
            keyword=keyword,
            region=region,
        )

        # Step 3: Assess competition density
        competition_density = await self._assess_competition_density(
            keyword=keyword,
            region=region,
        )

        # Step 4: Extract 1688 cross-border signals (future enhancement)
        # For now, return None for these fields
        hot_sell_rank = None
        repurchase_rate = None
        lead_time_days = None

        result = DemandValidationResult(
            keyword=keyword,
            search_volume=search_volume,
            competition_density=competition_density,
            trend_direction=trend_direction,
            trend_growth_rate=trend_growth_rate,
            hot_sell_rank=hot_sell_rank,
            repurchase_rate=repurchase_rate,
            lead_time_days=lead_time_days,
            region=region,
            category=category,
            platform=platform,
        )

        # Step 5: Cache result
        if self.enable_cache:
            await self._save_to_cache(keyword, region, result, category, platform)

        logger.info(
            "demand_validation_completed",
            keyword=keyword,
            passed=result.passed,
            search_volume=search_volume,
            competition_density=competition_density.value,
            trend_direction=trend_direction.value,
            rejection_reasons=result.rejection_reasons,
        )

        return result

    async def _get_from_cache(
        self,
        keyword: str,
        region: str,
        category: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> Optional[DemandValidationResult]:
        """Get validation result from Redis cache.

        Args:
            keyword: Search keyword
            region: Target region
            category: Product category
            platform: Target platform

        Returns:
            Cached DemandValidationResult or None if not found
        """
        if not self.redis_client:
            self.redis_client = RedisClient()

        try:
            cache_key = self._build_cache_key(keyword, region, category, platform)
            cached_json = await self.redis_client.get(cache_key)

            if not cached_json:
                return None

            # Deserialize from JSON
            cached_data = json.loads(cached_json)

            # Reconstruct DemandValidationResult
            result = DemandValidationResult(
                keyword=cached_data["keyword"],
                search_volume=cached_data.get("search_volume"),
                competition_density=CompetitionDensity(cached_data["competition_density"]),
                trend_direction=TrendDirection(cached_data["trend_direction"]),
                trend_growth_rate=Decimal(str(cached_data["trend_growth_rate"])) if cached_data.get("trend_growth_rate") else None,
                hot_sell_rank=cached_data.get("hot_sell_rank"),
                repurchase_rate=Decimal(str(cached_data["repurchase_rate"])) if cached_data.get("repurchase_rate") else None,
                lead_time_days=cached_data.get("lead_time_days"),
                region=region,
                category=category,
                platform=platform,
            )

            return result

        except Exception as e:
            logger.warning(
                "cache_get_failed",
                keyword=keyword,
                region=region,
                category=category,
                platform=platform,
                error=str(e),
            )
            return None

    async def _save_to_cache(
        self,
        keyword: str,
        region: str,
        result: DemandValidationResult,
        category: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> None:
        """Save validation result to Redis cache.

        Args:
            keyword: Search keyword
            region: Target region
            result: Validation result to cache
            category: Product category
            platform: Target platform
        """
        if not self.redis_client:
            self.redis_client = RedisClient()

        try:
            cache_key = self._build_cache_key(keyword, region, category, platform)
            result_dict = result.to_dict()

            # Serialize to JSON
            cached_json = json.dumps(result_dict)

            # Save to Redis with TTL
            await self.redis_client.set(
                cache_key,
                cached_json,
                ex=self.cache_ttl_seconds,
            )

            logger.info(
                "cache_saved",
                keyword=keyword,
                region=region,
                category=category,
                platform=platform,
                cache_key=cache_key,
                ttl_seconds=self.cache_ttl_seconds,
            )

        except Exception as e:
            logger.warning(
                "cache_save_failed",
                keyword=keyword,
                region=region,
                category=category,
                platform=platform,
                error=str(e),
            )

    def _build_cache_key(
        self,
        keyword: str,
        region: str,
        category: Optional[str] = None,
        platform: Optional[str] = None,
    ) -> str:
        """Build Redis cache key for demand validation.

        Uses MD5 hash of keyword to handle special characters and long keywords.
        Includes category and platform to avoid cross-context cache pollution.

        Args:
            keyword: Search keyword
            region: Target region
            category: Product category
            platform: Target platform

        Returns:
            Cache key string
        """
        # Use MD5 hash to handle special characters and long keywords
        keyword_hash = hashlib.md5(keyword.encode("utf-8")).hexdigest()
        category_suffix = f":{category}" if category else ""
        platform_suffix = f":{platform}" if platform else ""
        return f"demand_validation:{keyword_hash}:{region}{category_suffix}{platform_suffix}"

    async def _get_search_trends(
        self,
        keyword: str,
        region: str,
    ) -> tuple[Optional[int], Optional[Decimal], TrendDirection]:
        """Get search volume and trend data.

        Priority order:
        1. AlphaShop keyword search (primary)
        2. Helium 10 API (optional enhancement)
        3. pytrends (legacy fallback)

        Returns:
            Tuple of (search_volume, trend_growth_rate, trend_direction)
        """
        trends = await self._get_trends_from_alphashop(keyword, region)
        if trends[0] is not None:
            return trends

        if self.use_helium10:
            trends = await self._get_trends_from_helium10(keyword, region)
            if trends[0] is not None:
                return trends

        return await self._get_trends_from_pytrends(keyword, region)

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

    async def _get_trends_from_alphashop(
        self,
        keyword: str,
        region: str,
    ) -> tuple[Optional[int], Optional[Decimal], TrendDirection]:
        """Get trends from AlphaShop keyword search API.

        Uses AlphaShop to fetch search volume, sales data, and rank trends.

        Returns:
            Tuple of (search_volume, trend_growth_rate, trend_direction)
        """
        client = await self._get_alphashop_client()
        if client is None:
            logger.debug(
                "alphashop_trends_unavailable",
                keyword=keyword,
                region=region,
                reason="missing_configuration_or_disabled",
            )
            return None, None, TrendDirection.UNKNOWN

        try:
            response = await client.search_keywords(
                platform=self.platform,
                region=region,
                keyword=keyword,
                listing_time=self.listing_time,
            )
        except Exception as exc:
            logger.warning(
                "alphashop_trends_fetch_failed",
                keyword=keyword,
                region=region,
                error=str(exc),
            )
            return None, None, TrendDirection.UNKNOWN

        keyword_list = response.get("keyword_list") or []
        if not keyword_list:
            logger.debug(
                "alphashop_no_keyword_data",
                keyword=keyword,
                region=region,
            )
            return None, None, TrendDirection.UNKNOWN

        best_match = self._select_best_keyword_match(keyword_list, keyword)
        search_volume = self._extract_search_volume_from_alphashop(best_match)
        trend_growth_rate, trend_direction = self._extract_trend_from_alphashop(best_match)

        logger.info(
            "alphashop_trends_fetched",
            keyword=keyword,
            region=region,
            search_volume=search_volume,
            trend_growth_rate=float(trend_growth_rate) if trend_growth_rate else None,
            trend_direction=trend_direction.value,
        )

        return search_volume, trend_growth_rate, trend_direction

    def _select_best_keyword_match(self, keyword_list: list[dict], query: str) -> dict:
        """Select the best AlphaShop keyword result for a query.

        Prefer exact match, then singular/plural normalized match, then substring match,
        then fall back to the first result.
        """
        normalized_query = query.lower().strip()

        def normalize(value: str) -> str:
            value = value.lower().strip()
            if value.endswith("es"):
                return value[:-2]
            if value.endswith("s"):
                return value[:-1]
            return value

        normalized_query_simple = normalize(normalized_query)

        for item in keyword_list:
            keyword = item.get("keyword")
            if isinstance(keyword, str) and keyword.lower().strip() == normalized_query:
                return item

        for item in keyword_list:
            keyword = item.get("keyword")
            if isinstance(keyword, str) and normalize(keyword) == normalized_query_simple:
                return item

        for item in keyword_list:
            keyword = item.get("keyword")
            if isinstance(keyword, str):
                keyword_norm = keyword.lower().strip()
                if normalized_query in keyword_norm or keyword_norm in normalized_query:
                    return item

        return keyword_list[0]

    def _extract_search_volume_from_alphashop(self, item: dict) -> int:
        """Extract search volume from AlphaShop keyword result."""
        direct_volume = self._coerce_int(item.get("searchVolume"))
        if direct_volume is not None:
            return max(direct_volume, 100)

        sales_info = item.get("salesInfo") if isinstance(item.get("salesInfo"), dict) else {}
        sales_volume = self._coerce_int(sales_info.get("searchVolume"))
        if sales_volume is not None:
            return max(sales_volume, 100)

        sold_cnt_30d_obj = sales_info.get("soldCnt30d")
        if isinstance(sold_cnt_30d_obj, dict):
            sold_cnt_30d_str = sold_cnt_30d_obj.get("value")
            sold_cnt_30d = self._parse_chinese_number(sold_cnt_30d_str)
            if sold_cnt_30d is not None:
                return max(sold_cnt_30d * 10, 100)
        else:
            sold_cnt_30d = self._coerce_int(item.get("soldCnt30d"))
            if sold_cnt_30d is None:
                sold_cnt_30d = self._coerce_int(sales_info.get("soldCnt30d"))
            if sold_cnt_30d is not None:
                return max(sold_cnt_30d * 10, 100)

        demand_info = item.get("demandInfo") if isinstance(item.get("demandInfo"), dict) else {}
        search_rank_str = demand_info.get("searchRank")
        search_rank = self._parse_chinese_number(search_rank_str)
        if search_rank is None:
            search_rank = self._coerce_int(item.get("searchRank"))
        if search_rank is not None:
            if search_rank <= 1000:
                return 10000
            if search_rank <= 5000:
                return 5000
            if search_rank <= 20000:
                return 2000
            return 500

        opp_score = self._coerce_float(item.get("oppScore"))
        if opp_score is not None:
            return self._estimate_search_volume_from_interest(float(opp_score))

        return 100

    def _extract_trend_from_alphashop(self, item: dict) -> tuple[Optional[Decimal], TrendDirection]:
        """Extract trend growth rate and direction from AlphaShop keyword result."""
        sold_cnt_30d_obj = (item.get("salesInfo") or {}).get("soldCnt30d") if isinstance(item.get("salesInfo"), dict) else None
        if isinstance(sold_cnt_30d_obj, dict):
            growth_rate_obj = sold_cnt_30d_obj.get("growthRate")
            if isinstance(growth_rate_obj, dict):
                growth_rate_str = growth_rate_obj.get("value")
                growth_rate = self._parse_percentage(growth_rate_str)
                direction_raw = (growth_rate_obj.get("direction") or "").upper()
                if growth_rate is not None:
                    if direction_raw == "UP":
                        return growth_rate, TrendDirection.RISING
                    if direction_raw == "DOWN":
                        return -growth_rate, TrendDirection.DECLINING
                    return growth_rate, self._classify_trend_direction(growth_rate)

        demand_info = item.get("demandInfo") if isinstance(item.get("demandInfo"), dict) else {}
        rank_trends = self._extract_rank_trends(demand_info)
        if len(rank_trends) >= 2:
            first_half = rank_trends[: len(rank_trends) // 2]
            second_half = rank_trends[len(rank_trends) // 2 :]

            first_avg = sum(first_half) / len(first_half)
            second_avg = sum(second_half) / len(second_half)

            if first_avg == 0:
                if second_avg > 0:
                    return Decimal("1.0"), TrendDirection.RISING
                return Decimal("0"), TrendDirection.STABLE

            growth_rate_float = (first_avg - second_avg) / first_avg
            growth_rate = Decimal(str(round(growth_rate_float, 4)))
            direction = self._classify_trend_direction(growth_rate)
            return growth_rate, direction

        opp_score = self._coerce_float(item.get("oppScore"))
        if opp_score is not None:
            if opp_score >= 70:
                return Decimal("0.25"), TrendDirection.RISING
            if opp_score >= 40:
                return Decimal("0.05"), TrendDirection.STABLE
            return Decimal("-0.10"), TrendDirection.DECLINING

        return Decimal("0"), TrendDirection.STABLE

    def _extract_rank_trends(self, item: dict) -> list[int]:
        """Extract numeric rank trend points from AlphaShop result."""
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
                for key in ("y", "rank", "value", "searchRank"):
                    candidate = self._coerce_int(entry.get(key))
                    if candidate is not None:
                        values.append(candidate)
                        break
        return values

    async def _get_trends_from_pytrends(
        self,
        keyword: str,
        region: str,
    ) -> tuple[Optional[int], Optional[Decimal], TrendDirection]:
        """Get trends from Google Trends via pytrends.

        Uses pytrends to fetch interest over time for the past 12 months and
        estimates demand signals from the relative interest data.

        Note: Google Trends provides relative interest (0-100), not absolute
        search volume. We use the average interest as a proxy for search volume:
        - avg_interest >= 50 → estimated 5000 monthly searches
        - avg_interest >= 30 → estimated 2000 monthly searches
        - avg_interest >= 10 → estimated 500 monthly searches
        - avg_interest < 10 → estimated 100 monthly searches

        Trend growth is calculated by comparing the first 6 months average to
        the last 6 months average.

        Returns:
            Tuple of (estimated_search_volume, trend_growth_rate, trend_direction)
        """
        def _fetch_pytrends_data() -> tuple[Optional[int], Optional[Decimal], TrendDirection]:
            try:
                from pytrends.request import TrendReq
            except ImportError:
                logger.warning(
                    "pytrends_not_installed",
                    keyword=keyword,
                    region=region,
                    fallback="mock_data",
                )
                return 1500, Decimal("0.15"), TrendDirection.STABLE

            try:
                # Initialize pytrends client
                pytrends = TrendReq(hl="en-US", tz=360)

                # Build payload for past 12 months
                geo = self._region_to_geo(region)
                pytrends.build_payload(
                    kw_list=[keyword],
                    cat=0,
                    timeframe="today 12-m",
                    geo=geo,
                    gprop="",
                )

                # Get interest over time
                interest_df = pytrends.interest_over_time()

                if interest_df.empty or keyword not in interest_df.columns:
                    logger.warning(
                        "pytrends_no_data",
                        keyword=keyword,
                        region=region,
                        geo=geo,
                    )
                    return 100, Decimal("0"), TrendDirection.UNKNOWN

                # Extract interest values
                interest_values = interest_df[keyword].tolist()
                if not interest_values:
                    return 100, Decimal("0"), TrendDirection.UNKNOWN

                # Calculate average interest (0-100)
                avg_interest = sum(interest_values) / len(interest_values)

                # Estimate search volume from average interest
                estimated_search_volume = self._estimate_search_volume_from_interest(avg_interest)

                # Calculate trend growth rate by comparing first half vs second half
                mid_point = len(interest_values) // 2
                first_half = interest_values[:mid_point]
                second_half = interest_values[mid_point:]

                if not first_half or not second_half:
                    return estimated_search_volume, Decimal("0"), TrendDirection.UNKNOWN

                first_half_avg = sum(first_half) / len(first_half)
                second_half_avg = sum(second_half) / len(second_half)

                if first_half_avg == 0:
                    if second_half_avg > 0:
                        trend_growth_rate = Decimal("1.0")  # 100% growth from zero
                        trend_direction = TrendDirection.RISING
                    else:
                        trend_growth_rate = Decimal("0")
                        trend_direction = TrendDirection.STABLE
                else:
                    growth_rate_float = (second_half_avg - first_half_avg) / first_half_avg
                    trend_growth_rate = Decimal(str(round(growth_rate_float, 4)))
                    trend_direction = self._classify_trend_direction(trend_growth_rate)

                logger.info(
                    "pytrends_data_fetched",
                    keyword=keyword,
                    region=region,
                    geo=geo,
                    avg_interest=round(avg_interest, 2),
                    estimated_search_volume=estimated_search_volume,
                    trend_growth_rate=float(trend_growth_rate),
                    trend_direction=trend_direction.value,
                )

                return estimated_search_volume, trend_growth_rate, trend_direction

            except Exception as e:
                logger.warning(
                    "pytrends_fetch_failed",
                    keyword=keyword,
                    region=region,
                    error=str(e),
                    fallback="mock_data",
                )
                # Fallback to mock data to avoid breaking the pipeline
                return 1500, Decimal("0.15"), TrendDirection.STABLE

        return await asyncio.to_thread(_fetch_pytrends_data)

    def _region_to_geo(self, region: str) -> str:
        """Convert region code to Google Trends geo code.

        Args:
            region: Region code (e.g., "US", "UK", "JP")

        Returns:
            Google Trends geo code
        """
        if not region:
            return "US"

        region_upper = region.upper()
        region_map = {
            "US": "US",
            "UK": "GB",
            "GB": "GB",
            "JP": "JP",
            "DE": "DE",
            "FR": "FR",
            "ES": "ES",
            "IT": "IT",
            "BR": "BR",
            "MX": "MX",
            "CA": "CA",
            "AU": "AU",
            "RU": "RU",
        }
        return region_map.get(region_upper, region_upper)

    def _region_to_marketplace(self, region: str) -> str:
        """Convert region code to Amazon marketplace code.

        Args:
            region: Region code (e.g., "US", "UK", "JP")

        Returns:
            Amazon marketplace code
        """
        if not region:
            return "US"

        region_upper = region.upper()
        marketplace_map = {
            "US": "US",
            "UK": "UK",
            "GB": "UK",
            "JP": "JP",
            "DE": "DE",
            "FR": "FR",
            "ES": "ES",
            "IT": "IT",
            "BR": "BR",
            "MX": "MX",
            "CA": "CA",
            "AU": "AU",
        }
        return marketplace_map.get(region_upper, "US")

    def _estimate_search_volume_from_interest(self, avg_interest: float) -> int:
        """Estimate monthly search volume from Google Trends relative interest.

        This is a heuristic mapping from relative interest (0-100) to estimated
        monthly search volume. It's not exact, but provides a useful proxy for
        demand validation.

        Args:
            avg_interest: Average Google Trends interest (0-100)

        Returns:
            Estimated monthly search volume
        """
        if avg_interest >= 70:
            return 10000
        elif avg_interest >= 50:
            return 5000
        elif avg_interest >= 30:
            return 2000
        elif avg_interest >= 10:
            return 500
        elif avg_interest >= 5:
            return 200
        else:
            return 100

    def _classify_trend_direction(self, growth_rate: Decimal) -> TrendDirection:
        """Classify trend direction from growth rate.

        Args:
            growth_rate: Growth rate as decimal (e.g., 0.25 = 25%)

        Returns:
            TrendDirection enum
        """
        if growth_rate >= Decimal("0.20"):
            return TrendDirection.RISING
        elif growth_rate <= Decimal("-0.20"):
            return TrendDirection.DECLINING
        else:
            return TrendDirection.STABLE

    async def _get_trends_from_helium10(
        self,
        keyword: str,
        region: str,
    ) -> tuple[Optional[int], Optional[Decimal], TrendDirection]:
        """Get trends from Helium 10 API.

        Uses Helium 10 Magnet API for keyword data including:
        - Monthly search volume
        - Competition score
        - Trend direction and growth rate

        Falls back to pytrends if Helium 10 API fails or returns no data.

        Args:
            keyword: Search keyword
            region: Target region (e.g., "US", "UK", "JP")

        Returns:
            Tuple of (search_volume, trend_growth_rate, trend_direction)
        """
        from app.clients.helium10 import Helium10Client

        try:
            # Initialize Helium 10 client
            client = Helium10Client(
                api_key=self.helium10_api_key,
                redis_client=self.redis_client,
                cache_ttl_seconds=self.cache_ttl_seconds,
                enable_cache=self.enable_cache,
            )

            # Convert region to marketplace code
            marketplace = self._region_to_marketplace(region)

            # Get keyword data from Helium 10
            keyword_data = await client.get_keyword_data(
                keyword=keyword,
                marketplace=marketplace,
            )

            # Close HTTP client
            await client.close()

            if not keyword_data:
                logger.warning(
                    "helium10_no_data",
                    keyword=keyword,
                    region=region,
                    marketplace=marketplace,
                    fallback="pytrends",
                )
                # Fallback to pytrends
                return await self._get_trends_from_pytrends(keyword, region)

            # Extract data from Helium 10 response
            search_volume = keyword_data.get("search_volume", 0)
            trend_growth_rate_float = keyword_data.get("trend_growth_rate", 0.0)
            trend_direction_str = keyword_data.get("trend_direction", "stable")

            # Convert to expected types
            trend_growth_rate = Decimal(str(trend_growth_rate_float))

            # Map trend direction string to enum
            trend_direction_map = {
                "rising": TrendDirection.RISING,
                "stable": TrendDirection.STABLE,
                "declining": TrendDirection.DECLINING,
            }
            trend_direction = trend_direction_map.get(
                trend_direction_str.lower(),
                TrendDirection.STABLE,
            )

            logger.info(
                "helium10_trends_fetched",
                keyword=keyword,
                region=region,
                marketplace=marketplace,
                search_volume=search_volume,
                trend_growth_rate=float(trend_growth_rate),
                trend_direction=trend_direction.value,
            )

            return search_volume, trend_growth_rate, trend_direction

        except Exception as e:
            logger.warning(
                "helium10_fetch_failed",
                keyword=keyword,
                region=region,
                error=str(e),
                fallback="pytrends",
            )
            # Fallback to pytrends
            return await self._get_trends_from_pytrends(keyword, region)

    async def _assess_competition_density(
        self,
        keyword: str,
        region: str,
    ) -> CompetitionDensity:
        """Assess competition density by search result count.

        Priority order:
        1. AlphaShop keyword metrics
        2. pytrends legacy fallback
        3. Heuristic classification
        """
        client = await self._get_alphashop_client()
        if client is not None:
            try:
                response = await client.search_keywords(
                    platform=self.platform,
                    region=region,
                    keyword=keyword,
                    listing_time=self.listing_time,
                )
                keyword_list = response.get("keyword_list") or []
                if keyword_list:
                    first_item = keyword_list[0]
                    opp_score = self._coerce_float(first_item.get("oppScore"))

                    # Use oppScore as primary competition signal (higher oppScore = lower competition)
                    if opp_score is not None:
                        if opp_score >= 70:
                            return CompetitionDensity.LOW  # High opportunity = low competition
                        if opp_score >= 40:
                            return CompetitionDensity.MEDIUM
                        return CompetitionDensity.HIGH  # Low opportunity = high competition
            except Exception as exc:
                logger.debug(
                    "alphashop_competition_assessment_failed",
                    keyword=keyword,
                    region=region,
                    error=str(exc),
                )

        def _assess_competition() -> CompetitionDensity:
            try:
                from pytrends.request import TrendReq
            except ImportError:
                logger.warning(
                    "pytrends_not_installed_for_competition",
                    keyword=keyword,
                    region=region,
                    fallback="heuristic",
                )
                return self._heuristic_competition_assessment(keyword)

            try:
                pytrends = TrendReq(hl="en-US", tz=360)
                geo = self._region_to_geo(region)
                pytrends.build_payload(
                    kw_list=[keyword],
                    cat=0,
                    timeframe="today 12-m",
                    geo=geo,
                    gprop="",
                )

                interest_df = pytrends.interest_over_time()

                if interest_df.empty or keyword not in interest_df.columns:
                    logger.warning(
                        "pytrends_no_data_for_competition",
                        keyword=keyword,
                        region=region,
                        fallback="heuristic",
                    )
                    return self._heuristic_competition_assessment(keyword)

                avg_interest = interest_df[keyword].mean()

                try:
                    related_queries = pytrends.related_queries()

                    if keyword in related_queries and related_queries[keyword]:
                        top_queries = related_queries[keyword].get("top")
                        rising_queries = related_queries[keyword].get("rising")

                        related_count = 0
                        if top_queries is not None and not top_queries.empty:
                            related_count += len(top_queries)
                        if rising_queries is not None and not rising_queries.empty:
                            related_count += len(rising_queries)

                        if related_count >= 20:
                            competition = CompetitionDensity.HIGH
                        elif related_count >= 10:
                            competition = CompetitionDensity.MEDIUM
                        else:
                            competition = CompetitionDensity.LOW

                        logger.info(
                            "competition_assessed_from_related_queries",
                            keyword=keyword,
                            region=region,
                            related_count=related_count,
                            competition=competition.value,
                        )

                        return competition

                except Exception as exc:
                    logger.debug(
                        "related_queries_failed",
                        keyword=keyword,
                        error=str(exc),
                        fallback="interest_based",
                    )

                if avg_interest >= 60:
                    competition = CompetitionDensity.HIGH
                elif avg_interest >= 30:
                    competition = CompetitionDensity.MEDIUM
                else:
                    competition = CompetitionDensity.LOW

                logger.info(
                    "competition_assessed_from_interest",
                    keyword=keyword,
                    region=region,
                    avg_interest=round(avg_interest, 2),
                    competition=competition.value,
                )

                return competition

            except Exception as exc:
                logger.warning(
                    "competition_assessment_failed",
                    keyword=keyword,
                    region=region,
                    error=str(exc),
                    fallback="heuristic",
                )
                return self._heuristic_competition_assessment(keyword)

        return await asyncio.to_thread(_assess_competition)

    def _heuristic_competition_assessment(self, keyword: str) -> CompetitionDensity:
        """Heuristic competition assessment based on keyword characteristics.

        Uses simple heuristics when API data is unavailable:
        - Generic keywords (1-2 words) = HIGH competition
        - Specific keywords (3-4 words) = MEDIUM competition
        - Long-tail keywords (5+ words) = LOW competition
        - Brand names = HIGH competition

        Args:
            keyword: Search keyword

        Returns:
            CompetitionDensity enum
        """
        keyword_lower = keyword.lower().strip()
        word_count = len(keyword_lower.split())

        # Check for common high-competition indicators
        high_competition_terms = [
            "phone", "iphone", "samsung", "apple", "nike", "adidas",
            "laptop", "computer", "watch", "shoes", "bag", "dress",
        ]

        for term in high_competition_terms:
            if term in keyword_lower:
                logger.info(
                    "heuristic_competition_high",
                    keyword=keyword,
                    reason="contains_high_competition_term",
                    term=term,
                )
                return CompetitionDensity.HIGH

        # Word count based heuristic
        if word_count <= 2:
            # Generic keywords = high competition
            competition = CompetitionDensity.HIGH
            reason = "generic_keyword"
        elif word_count <= 4:
            # Specific keywords = medium competition
            competition = CompetitionDensity.MEDIUM
            reason = "specific_keyword"
        else:
            # Long-tail keywords = low competition
            competition = CompetitionDensity.LOW
            reason = "long_tail_keyword"

        logger.info(
            "heuristic_competition_assessed",
            keyword=keyword,
            word_count=word_count,
            competition=competition.value,
            reason=reason,
        )

        return competition

    def _coerce_int(self, value) -> int | None:
        """Convert supplier numeric fields when possible."""
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

    def _coerce_float(self, value) -> float | None:
        """Convert value to float when possible."""
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return float(value)
        if isinstance(value, (int, float)):
            return float(value)
        if isinstance(value, str):
            try:
                return float(value)
            except Exception:
                return None
        return None

    def _parse_chinese_number(self, value) -> int | None:
        """Parse Chinese-formatted numbers like '13.9w+', '# 99.6w+', '837.8w+'.

        AlphaShop returns numbers in Chinese format:
        - w (万) = 10,000
        - k (千) = 1,000
        - '+' suffix indicates approximate/minimum
        - '#' prefix is stripped
        """
        if not isinstance(value, str):
            return None

        # Strip whitespace and '#' prefix
        value = value.strip().lstrip('#').strip()
        if not value:
            return None

        # Remove '+' suffix
        value = value.rstrip('+')

        # Parse multiplier
        multiplier = 1
        if value.endswith('w') or value.endswith('W') or value.endswith('万'):
            multiplier = 10000
            value = value.rstrip('wW万')
        elif value.endswith('k') or value.endswith('K') or value.endswith('千'):
            multiplier = 1000
            value = value.rstrip('kK千')

        # Parse numeric part
        try:
            numeric = float(value)
            return int(numeric * multiplier)
        except Exception:
            return None

    def _parse_percentage(self, value) -> Decimal | None:
        """Parse percentage strings like '20.0%', '4.0%' to Decimal."""
        if not isinstance(value, str):
            return None

        value = value.strip().rstrip('%')
        try:
            return Decimal(value) / Decimal("100")
        except Exception:
            return None

    async def validate_batch(
        self,
        keywords: list[str],
        category: Optional[str] = None,
        region: Optional[str] = "US",
        platform: Optional[str] = None,
    ) -> list[DemandValidationResult]:
        """Validate demand for multiple keywords in batch.

        Args:
            keywords: List of keywords to validate
            category: Product category (optional)
            region: Target region (default: "US")
            platform: Target platform (optional)

        Returns:
            List of DemandValidationResult
        """
        results = []
        for keyword in keywords:
            result = await self.validate(
                keyword=keyword,
                category=category,
                region=region,
                platform=platform,
            )
            results.append(result)

        passed_count = sum(1 for r in results if r.passed)
        logger.info(
            "demand_validation_batch_completed",
            total=len(keywords),
            passed=passed_count,
            failed=len(keywords) - passed_count,
        )

        return results

    async def validate_legitimized_batch(
        self,
        valid_keywords: list["ValidKeyword"],
        category: Optional[str] = None,
        region: Optional[str] = "US",
        platform: Optional[str] = None,
    ) -> list[DemandValidationResult]:
        """Validate already-legitimized keywords without re-running AlphaShop discovery.

        This path is used by the seller-first discovery facade after seed -> search intelligence
        legitimization. It reuses AlphaShop-derived metrics already present on the valid keyword
        objects and only falls back to provider lookup when needed.
        """
        results: list[DemandValidationResult] = []
        reused_raw_metrics_count = 0
        refetched_trends_count = 0

        for valid_keyword in valid_keywords:
            raw_item = valid_keyword.raw if isinstance(valid_keyword.raw, dict) else {}
            raw_has_demand_signals = bool(raw_item) and any(
                key in raw_item for key in ("searchVolume", "salesInfo", "demandInfo", "soldCnt30d", "searchRank", "oppScore")
            )

            search_volume = valid_keyword.search_volume
            if search_volume is None and raw_has_demand_signals:
                search_volume = self._extract_search_volume_from_alphashop(raw_item)

            if raw_has_demand_signals:
                trend_growth_rate, trend_direction = self._extract_trend_from_alphashop(raw_item)
                reused_raw_metrics_count += 1
            elif search_volume is None:
                search_volume, trend_growth_rate, trend_direction = await self._get_search_trends(
                    keyword=valid_keyword.matched_keyword,
                    region=region or "US",
                )
                refetched_trends_count += 1
            else:
                opp_score = valid_keyword.opp_score or 0.0
                if opp_score >= 70:
                    trend_growth_rate = Decimal("0.25")
                    trend_direction = TrendDirection.RISING
                elif opp_score >= 40:
                    trend_growth_rate = Decimal("0.05")
                    trend_direction = TrendDirection.STABLE
                else:
                    trend_growth_rate = Decimal("-0.10")
                    trend_direction = TrendDirection.DECLINING

            competition_value = (valid_keyword.competition_density or "unknown").lower()
            competition_map = {
                "low": CompetitionDensity.LOW,
                "medium": CompetitionDensity.MEDIUM,
                "high": CompetitionDensity.HIGH,
                "unknown": CompetitionDensity.UNKNOWN,
            }
            competition_density = competition_map.get(competition_value, CompetitionDensity.UNKNOWN)
            if competition_density == CompetitionDensity.UNKNOWN:
                competition_density = await self._assess_competition_density(
                    keyword=valid_keyword.matched_keyword,
                    region=region or "US",
                )

            result = DemandValidationResult(
                keyword=valid_keyword.matched_keyword,
                search_volume=search_volume,
                competition_density=competition_density,
                trend_direction=trend_direction,
                trend_growth_rate=trend_growth_rate,
                hot_sell_rank=None,
                repurchase_rate=None,
                lead_time_days=None,
                region=region,
                category=category,
                platform=platform,
            )
            results.append(result)

        passed_count = sum(1 for r in results if r.passed)
        logger.info(
            "demand_validation_legitimized_batch_completed",
            total=len(valid_keywords),
            passed=passed_count,
            failed=len(valid_keywords) - passed_count,
            reused_raw_metrics_count=reused_raw_metrics_count,
            refetched_trends_count=refetched_trends_count,
        )
        return results
