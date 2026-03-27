"""AliExpress API client skeleton for auto actions."""
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


class AliExpressAPIClient(PlatformAPIBase):
    """AliExpress API lightweight client skeleton."""

    def __init__(self):
        settings = get_settings()
        self.base_url = settings.aliexpress_api_base_url
        self.timeout = settings.aliexpress_api_timeout
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
            error_message="AliExpress API integration not configured yet",
        )

    async def update_price(
        self,
        platform_listing_id: str,
        price: Decimal,
        currency: str,
    ) -> PlatformActionResult:
        return PlatformActionResult(
            success=False,
            error_message="AliExpress API integration not configured yet",
        )

    async def pause_product(self, platform_listing_id: str) -> PlatformActionResult:
        return PlatformActionResult(
            success=False,
            error_message="AliExpress API pause not configured yet",
        )

    async def resume_product(self, platform_listing_id: str) -> PlatformActionResult:
        return PlatformActionResult(
            success=False,
            error_message="AliExpress API resume not configured yet",
        )

    async def get_listing_metrics(self, platform_listing_id: str, metric_date: date) -> PlatformMetrics:
        """Fetch daily listing metrics from AliExpress."""
        if self.use_mock:
            seed = f"aliexpress:{platform_listing_id}:{metric_date.isoformat()}"
            rng = random.Random(seed)
            impressions = rng.randint(700, 5000)
            clicks = rng.randint(max(1, impressions // 45), max(2, impressions // 9))
            orders = rng.randint(0, max(1, clicks // 4))
            units_sold = orders + rng.randint(0, max(1, orders // 2 + 1))
            revenue = Decimal(units_sold) * Decimal(str(rng.uniform(15, 55))).quantize(Decimal("0.01"))
            ad_spend = Decimal(clicks) * Decimal(str(rng.uniform(0.12, 1.0))).quantize(Decimal("0.01"))
            return PlatformMetrics(
                impressions=impressions,
                clicks=clicks,
                orders=orders,
                units_sold=units_sold,
                revenue=revenue,
                ad_spend=ad_spend,
                returns_count=min(orders, rng.randint(0, 2)),
                refund_amount=Decimal(rng.randint(0, max(0, orders))) * Decimal("2.75"),
            )

        client = await self._get_http_client()
        response = await client.get(
            f"/products/{platform_listing_id}/metrics",
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
