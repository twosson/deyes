"""Amazon SP-API client skeleton for auto actions."""
from __future__ import annotations

import asyncio
import random
from datetime import date
from decimal import Decimal
from typing import Any, Optional

import httpx

from app.clients.platform_api_base import PlatformAPIBase, PlatformActionResult, PlatformMetrics
from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AmazonAPIClient(PlatformAPIBase):
    """Amazon SP-API lightweight client skeleton."""

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.amazon_sp_api_base_url
        self.timeout = settings.amazon_sp_api_timeout
        self.max_retries = settings.platform_api_max_retries
        self.use_mock = settings.temu_use_mock
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self._http_client

    async def create_product(self, payload: dict[str, Any]) -> PlatformActionResult:
        return PlatformActionResult(
            success=False,
            error_message="Amazon SP-API integration not configured yet",
        )

    async def update_price(
        self,
        platform_listing_id: str,
        price: Decimal,
        currency: str,
    ) -> PlatformActionResult:
        return PlatformActionResult(
            success=False,
            error_message="Amazon SP-API integration not configured yet",
        )

    async def pause_product(self, platform_listing_id: str) -> PlatformActionResult:
        return PlatformActionResult(
            success=False,
            error_message="Amazon SP-API pause not configured yet",
        )

    async def resume_product(self, platform_listing_id: str) -> PlatformActionResult:
        return PlatformActionResult(
            success=False,
            error_message="Amazon SP-API resume not configured yet",
        )

    async def get_listing_metrics(self, platform_listing_id: str, metric_date: date) -> PlatformMetrics:
        """Fetch daily listing metrics from Amazon."""
        if self.use_mock:
            seed = f"amazon:{platform_listing_id}:{metric_date.isoformat()}"
            rng = random.Random(seed)
            impressions = rng.randint(1200, 6500)
            clicks = rng.randint(max(1, impressions // 50), max(2, impressions // 10))
            orders = rng.randint(0, max(1, clicks // 5))
            units_sold = orders + rng.randint(0, max(1, orders))
            revenue = Decimal(units_sold) * Decimal(str(rng.uniform(22, 90))).quantize(Decimal("0.01"))
            ad_spend = Decimal(clicks) * Decimal(str(rng.uniform(0.2, 1.8))).quantize(Decimal("0.01"))
            return PlatformMetrics(
                impressions=impressions,
                clicks=clicks,
                orders=orders,
                units_sold=units_sold,
                revenue=revenue,
                ad_spend=ad_spend,
                returns_count=min(orders, rng.randint(0, 3)),
                refund_amount=Decimal(rng.randint(0, max(0, orders))) * Decimal("4.25"),
            )

        client = await self._get_http_client()
        response = await client.get(
            f"/listings/{platform_listing_id}/metrics",
            params={"date": metric_date.isoformat()},
        )
        response.raise_for_status()
        payload = response.json() or {}
        return PlatformMetrics(
            impressions=int(payload.get("impressions", 0) or 0),
            clicks=int(payload.get("clicks", 0) or 0),
            orders=int(payload.get("orders", 0) or 0),
            units_sold=int(payload.get("units_sold", payload.get("orders", 0)) or 0),
            revenue=Decimal(str(payload.get("revenue", "0") or "0")),
            ad_spend=Decimal(str(payload.get("ad_spend", "0") or "0")),
            returns_count=int(payload.get("returns_count", 0) or 0),
            refund_amount=Decimal(str(payload.get("refund_amount", "0") or "0")),
        )

    async def close(self) -> None:
        if self._http_client:
            await self._http_client.aclose()
            self._http_client = None
