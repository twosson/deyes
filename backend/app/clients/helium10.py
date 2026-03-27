"""Helium 10 API client.

Provides integration with Helium 10 Magnet API for keyword research and demand validation.

API Documentation: https://developer.helium10.com/docs/magnet-api

Features:
- Keyword search volume data
- Competition metrics
- Trend analysis
- Redis caching (24h TTL)
- Automatic fallback on errors
"""
import hashlib
from decimal import Decimal
from typing import Optional

import httpx

from app.clients.redis import RedisClient
from app.core.logging import get_logger

logger = get_logger(__name__)


class Helium10Client:
    """Client for Helium 10 Magnet API.

    Provides keyword research data including search volume, competition,
    and trend analysis for Amazon marketplace.

    Usage:
        client = Helium10Client(api_key="your_api_key")
        result = await client.get_keyword_data(
            keyword="phone case",
            marketplace="US",
        )

        if result:
            search_volume = result["search_volume"]
            competition = result["competition_score"]
    """

    BASE_URL = "https://api.helium10.com/v1"
    TIMEOUT = 30  # seconds

    def __init__(
        self,
        api_key: str,
        redis_client: Optional[RedisClient] = None,
        cache_ttl_seconds: int = 86400,
        enable_cache: bool = True,
    ):
        """Initialize Helium 10 client.

        Args:
            api_key: Helium 10 API key
            redis_client: Redis client for caching (optional, will create if None)
            cache_ttl_seconds: Cache TTL in seconds (default: 86400 = 24 hours)
            enable_cache: Whether to enable caching (default: True)
        """
        self.api_key = api_key
        self.redis_client = redis_client
        self.cache_ttl_seconds = cache_ttl_seconds
        self.enable_cache = enable_cache
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.BASE_URL,
                timeout=self.TIMEOUT,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
            )
        return self._http_client

    async def close(self):
        """Close HTTP client."""
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None

    async def get_keyword_data(
        self,
        keyword: str,
        marketplace: str = "US",
    ) -> Optional[dict]:
        """Get keyword data from Helium 10 Magnet API.

        Args:
            keyword: Search keyword
            marketplace: Amazon marketplace (default: "US")

        Returns:
            Dictionary with keyword data:
            {
                "search_volume": int,  # Monthly search volume
                "competition_score": int,  # 0-100, higher = more competition
                "trend_direction": str,  # "rising", "stable", "declining"
                "trend_growth_rate": float,  # YoY growth rate (e.g., 0.25 = 25%)
            }

            Returns None if API call fails or keyword not found.
        """
        logger.info(
            "helium10_keyword_data_requested",
            keyword=keyword,
            marketplace=marketplace,
        )

        # Step 1: Check cache
        if self.enable_cache:
            cached_data = await self._get_from_cache(keyword, marketplace)
            if cached_data:
                logger.info(
                    "helium10_cache_hit",
                    keyword=keyword,
                    marketplace=marketplace,
                )
                return cached_data

        # Step 2: Call Helium 10 API
        try:
            client = await self._get_http_client()

            # Helium 10 Magnet API endpoint
            # Note: This is a simplified example. Actual API may differ.
            response = await client.post(
                "/magnet/keyword-data",
                json={
                    "keyword": keyword,
                    "marketplace": marketplace,
                },
            )

            if response.status_code == 401:
                logger.error(
                    "helium10_unauthorized",
                    keyword=keyword,
                    marketplace=marketplace,
                    message="Invalid API key",
                )
                return None

            if response.status_code == 429:
                logger.warning(
                    "helium10_rate_limited",
                    keyword=keyword,
                    marketplace=marketplace,
                )
                return None

            if response.status_code != 200:
                logger.warning(
                    "helium10_api_error",
                    keyword=keyword,
                    marketplace=marketplace,
                    status_code=response.status_code,
                    response=response.text,
                )
                return None

            data = response.json()

            # Extract relevant fields from API response
            # Note: Field names may differ in actual API
            keyword_data = {
                "search_volume": data.get("search_volume", 0),
                "competition_score": data.get("competition_score", 50),
                "trend_direction": data.get("trend_direction", "stable"),
                "trend_growth_rate": data.get("trend_growth_rate", 0.0),
            }

            # Step 3: Cache result
            if self.enable_cache:
                await self._save_to_cache(keyword, marketplace, keyword_data)

            logger.info(
                "helium10_keyword_data_fetched",
                keyword=keyword,
                marketplace=marketplace,
                search_volume=keyword_data["search_volume"],
                competition_score=keyword_data["competition_score"],
            )

            return keyword_data

        except httpx.TimeoutException:
            logger.warning(
                "helium10_timeout",
                keyword=keyword,
                marketplace=marketplace,
            )
            return None

        except httpx.RequestError as e:
            logger.warning(
                "helium10_request_error",
                keyword=keyword,
                marketplace=marketplace,
                error=str(e),
            )
            return None

        except Exception as e:
            logger.error(
                "helium10_unexpected_error",
                keyword=keyword,
                marketplace=marketplace,
                error=str(e),
            )
            return None

    async def _get_from_cache(
        self,
        keyword: str,
        marketplace: str,
    ) -> Optional[dict]:
        """Get keyword data from Redis cache.

        Args:
            keyword: Search keyword
            marketplace: Amazon marketplace

        Returns:
            Cached keyword data or None if not found
        """
        if not self.redis_client:
            self.redis_client = RedisClient()

        try:
            cache_key = self._build_cache_key(keyword, marketplace)
            cached_json = await self.redis_client.get(cache_key)

            if not cached_json:
                return None

            # Deserialize from JSON
            import json
            cached_data = json.loads(cached_json)

            return cached_data

        except Exception as e:
            logger.warning(
                "helium10_cache_get_failed",
                keyword=keyword,
                marketplace=marketplace,
                error=str(e),
            )
            return None

    async def _save_to_cache(
        self,
        keyword: str,
        marketplace: str,
        data: dict,
    ) -> None:
        """Save keyword data to Redis cache.

        Args:
            keyword: Search keyword
            marketplace: Amazon marketplace
            data: Keyword data to cache
        """
        if not self.redis_client:
            self.redis_client = RedisClient()

        try:
            cache_key = self._build_cache_key(keyword, marketplace)

            # Serialize to JSON
            import json
            cached_json = json.dumps(data)

            # Save to Redis with TTL
            await self.redis_client.set(
                cache_key,
                cached_json,
                ex=self.cache_ttl_seconds,
            )

            logger.info(
                "helium10_cache_saved",
                keyword=keyword,
                marketplace=marketplace,
                cache_key=cache_key,
                ttl_seconds=self.cache_ttl_seconds,
            )

        except Exception as e:
            logger.warning(
                "helium10_cache_save_failed",
                keyword=keyword,
                marketplace=marketplace,
                error=str(e),
            )

    def _build_cache_key(self, keyword: str, marketplace: str) -> str:
        """Build Redis cache key for Helium 10 data.

        Uses MD5 hash of keyword to handle special characters and long keywords.

        Args:
            keyword: Search keyword
            marketplace: Amazon marketplace

        Returns:
            Cache key string
        """
        # Use MD5 hash to handle special characters and long keywords
        keyword_hash = hashlib.md5(keyword.encode("utf-8")).hexdigest()
        return f"helium10:{keyword_hash}:{marketplace}"
