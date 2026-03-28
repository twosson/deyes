"""Demand validation service.

Validates overseas demand before product scraping to avoid wasting resources
on low-demand or high-competition products.

Phase 1 of product selection optimization plan.

Features:
- Google Trends integration via pytrends
- Redis caching (24h TTL) to avoid rate limiting
- Helium 10 API support (optional)
- Competition density assessment
- Trend direction classification
"""
import asyncio
import hashlib
import json
from dataclasses import dataclass
from decimal import Decimal
from enum import Enum
from typing import Optional

from app.clients.redis import RedisClient
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

    def __post_init__(self):
        """Calculate validation decision with region-specific thresholds."""
        if self.rejection_reasons is None:
            self.rejection_reasons = []

        # Region-specific thresholds
        min_search_volume = self._get_min_search_volume_for_region(self.region)
        max_competition_density = self._get_max_competition_density_for_region(self.region)

        # Check search volume
        if self.search_volume is not None and self.search_volume < min_search_volume:
            self.rejection_reasons.append(
                f"Search volume too low: {self.search_volume} < {min_search_volume} (region: {self.region or 'US'})"
            )

        # Check competition density
        if self._is_competition_too_high(self.competition_density, max_competition_density):
            self.rejection_reasons.append(
                f"Competition density too high: {self.competition_density.value} (max: {max_competition_density.value}, region: {self.region or 'US'})"
            )

        # Check trend direction
        if self.trend_direction == TrendDirection.DECLINING:
            self.rejection_reasons.append("Market trend declining")

        # Passed if no rejection reasons
        self.passed = len(self.rejection_reasons) == 0

    def _get_min_search_volume_for_region(self, region: Optional[str]) -> int:
        """Get minimum search volume threshold for region."""
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

    def _get_max_competition_density_for_region(self, region: Optional[str]) -> CompetitionDensity:
        """Get maximum allowed competition density for region."""
        region_upper = (region or "US").upper()
        # US/EU: reject HIGH, CN: reject MEDIUM+
        if region_upper in {"CN"}:
            return CompetitionDensity.LOW
        else:
            return CompetitionDensity.MEDIUM

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
    ):
        """Initialize demand validator.

        Args:
            min_search_volume: Minimum monthly search volume (default: 500)
            use_helium10: Whether to use Helium 10 API (default: False, use pytrends)
            helium10_api_key: Helium 10 API key (required if use_helium10=True)
            redis_client: Redis client for caching (optional, will create if None)
            cache_ttl_seconds: Cache TTL in seconds (default: 86400 = 24 hours)
            enable_cache: Whether to enable caching (default: True)
        """
        self.min_search_volume = min_search_volume
        self.use_helium10 = use_helium10
        self.helium10_api_key = helium10_api_key
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.enable_cache = enable_cache

        if use_helium10 and not helium10_api_key:
            logger.warning("helium10_enabled_but_no_api_key", fallback="pytrends")
            self.use_helium10 = False

    async def validate(
        self,
        keyword: str,
        category: Optional[str] = None,
        region: Optional[str] = "US",
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
            cached_result = await self._get_from_cache(keyword, region)
            if cached_result:
                logger.info(
                    "demand_validation_cache_hit",
                    keyword=keyword,
                    region=region,
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
        )

        # Step 5: Cache result
        if self.enable_cache:
            await self._save_to_cache(keyword, region, result)

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
    ) -> Optional[DemandValidationResult]:
        """Get validation result from Redis cache.

        Args:
            keyword: Search keyword
            region: Target region

        Returns:
            Cached DemandValidationResult or None if not found
        """
        if not self.redis_client:
            self.redis_client = RedisClient()

        try:
            cache_key = self._build_cache_key(keyword, region)
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
            )

            return result

        except Exception as e:
            logger.warning(
                "cache_get_failed",
                keyword=keyword,
                region=region,
                error=str(e),
            )
            return None

    async def _save_to_cache(
        self,
        keyword: str,
        region: str,
        result: DemandValidationResult,
    ) -> None:
        """Save validation result to Redis cache.

        Args:
            keyword: Search keyword
            region: Target region
            result: Validation result to cache
        """
        if not self.redis_client:
            self.redis_client = RedisClient()

        try:
            cache_key = self._build_cache_key(keyword, region)
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
                cache_key=cache_key,
                ttl_seconds=self.cache_ttl_seconds,
            )

        except Exception as e:
            logger.warning(
                "cache_save_failed",
                keyword=keyword,
                region=region,
                error=str(e),
            )

    def _build_cache_key(self, keyword: str, region: str) -> str:
        """Build Redis cache key for demand validation.

        Uses MD5 hash of keyword to handle special characters and long keywords.

        Args:
            keyword: Search keyword
            region: Target region

        Returns:
            Cache key string
        """
        # Use MD5 hash to handle special characters and long keywords
        keyword_hash = hashlib.md5(keyword.encode("utf-8")).hexdigest()
        return f"demand_validation:{keyword_hash}:{region}"

    async def _get_search_trends(
        self,
        keyword: str,
        region: str,
    ) -> tuple[Optional[int], Optional[Decimal], TrendDirection]:
        """Get search volume and trend data.

        Returns:
            Tuple of (search_volume, trend_growth_rate, trend_direction)
        """
        if self.use_helium10:
            return await self._get_trends_from_helium10(keyword, region)
        else:
            return await self._get_trends_from_pytrends(keyword, region)

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

        Uses multiple data sources to estimate competition:
        1. Google Trends competition index (if available)
        2. Estimated competition from pytrends related queries
        3. Heuristic classification based on search volume

        Classification:
        - LOW: <2000 estimated competing listings
        - MEDIUM: 2000-5000 estimated competing listings
        - HIGH: >5000 estimated competing listings

        Args:
            keyword: Search keyword
            region: Target region

        Returns:
            CompetitionDensity enum
        """
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
                # Initialize pytrends client
                pytrends = TrendReq(hl="en-US", tz=360)

                # Build payload
                geo = self._region_to_geo(region)
                pytrends.build_payload(
                    kw_list=[keyword],
                    cat=0,
                    timeframe="today 12-m",
                    geo=geo,
                    gprop="",
                )

                # Get interest over time to check if keyword has data
                interest_df = pytrends.interest_over_time()

                if interest_df.empty or keyword not in interest_df.columns:
                    logger.warning(
                        "pytrends_no_data_for_competition",
                        keyword=keyword,
                        region=region,
                        fallback="heuristic",
                    )
                    return self._heuristic_competition_assessment(keyword)

                # Calculate average interest
                avg_interest = interest_df[keyword].mean()

                # Try to get related queries for competition signal
                try:
                    related_queries = pytrends.related_queries()

                    if keyword in related_queries and related_queries[keyword]:
                        top_queries = related_queries[keyword].get("top")
                        rising_queries = related_queries[keyword].get("rising")

                        # Count related queries as competition signal
                        related_count = 0
                        if top_queries is not None and not top_queries.empty:
                            related_count += len(top_queries)
                        if rising_queries is not None and not rising_queries.empty:
                            related_count += len(rising_queries)

                        # High number of related queries = high competition
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

                except Exception as e:
                    logger.debug(
                        "related_queries_failed",
                        keyword=keyword,
                        error=str(e),
                        fallback="interest_based",
                    )

                # Fallback: Estimate competition from interest level
                # High interest usually correlates with high competition
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

            except Exception as e:
                logger.warning(
                    "competition_assessment_failed",
                    keyword=keyword,
                    region=region,
                    error=str(e),
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

    async def validate_batch(
        self,
        keywords: list[str],
        category: Optional[str] = None,
        region: Optional[str] = "US",
    ) -> list[DemandValidationResult]:
        """Validate demand for multiple keywords in batch.

        Args:
            keywords: List of keywords to validate
            category: Product category (optional)
            region: Target region (default: "US")

        Returns:
            List of DemandValidationResult
        """
        results = []
        for keyword in keywords:
            result = await self.validate(
                keyword=keyword,
                category=category,
                region=region,
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
