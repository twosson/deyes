"""Redis client wrapper."""
from typing import Optional

import redis.asyncio as redis

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class RedisClient:
    """Async Redis client wrapper."""

    def __init__(self, url: Optional[str] = None):
        settings = get_settings()
        self.url = url or settings.redis_url
        self._client: Optional[redis.Redis] = None

    async def get_client(self) -> redis.Redis:
        """Get or create Redis client."""
        if self._client is None:
            self._client = await redis.from_url(
                self.url,
                encoding="utf-8",
                decode_responses=True,
            )
        return self._client

    async def close(self):
        """Close Redis connection."""
        if self._client:
            await self._client.close()

    async def set(self, key: str, value: str, ex: Optional[int] = None) -> bool:
        """Set a key-value pair."""
        client = await self.get_client()
        return await client.set(key, value, ex=ex)

    async def get(self, key: str) -> Optional[str]:
        """Get a value by key."""
        client = await self.get_client()
        return await client.get(key)

    async def delete(self, key: str) -> int:
        """Delete a key."""
        client = await self.get_client()
        return await client.delete(key)

    async def exists(self, key: str) -> bool:
        """Check if key exists."""
        client = await self.get_client()
        return await client.exists(key) > 0
