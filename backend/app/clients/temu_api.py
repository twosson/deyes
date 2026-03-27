"""Temu seller API client for auto actions."""
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


class TemuAPIClient(PlatformAPIBase):
    """Temu seller API client.

    This implementation intentionally keeps a lightweight skeleton because
    actual Temu seller API payloads vary by seller account integration.
    """

    def __init__(self, base_url: Optional[str] = None, timeout: Optional[int] = None):
        settings = get_settings()
        self.base_url = base_url or settings.temu_api_base_url
        self.timeout = timeout or settings.temu_api_timeout
        self.use_mock = settings.temu_use_mock
        self.max_retries = settings.platform_api_max_retries
        self._http_client: Optional[httpx.AsyncClient] = None

    async def _get_http_client(self) -> httpx.AsyncClient:
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout)
        return self._http_client

    async def create_product(self, payload: dict[str, Any]) -> PlatformActionResult:
        if self.use_mock:
            return PlatformActionResult(
                success=True,
                platform_listing_id=f"temu_{payload.get('candidate_product_id', 'mock')}",
                platform_url="https://www.temu.com/mock-product.html",
                raw_response={"mock": True, "action": "create_product"},
            )

        max_retries = self.max_retries
        last_exception = None

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            for attempt in range(1, max(max_retries, 1) + 1):
                try:
                    response = await client.post("/products", json=payload)
                    response.raise_for_status()
                    data = response.json()
                    return PlatformActionResult(
                        success=True,
                        platform_listing_id=data.get("product_id"),
                        platform_url=data.get("product_url"),
                        raw_response=data,
                    )
                except httpx.HTTPError as exc:
                    last_exception = exc
                    logger.warning(
                        "platform_api_retry",
                        platform="temu",
                        method="create_product",
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt >= max(max_retries, 1):
                        return PlatformActionResult(success=False, error_message=str(exc))
                    await asyncio.sleep(min(attempt, 3))

        return PlatformActionResult(success=False, error_message=str(last_exception))

    async def update_price(
        self,
        platform_listing_id: str,
        price: Decimal,
        currency: str,
    ) -> PlatformActionResult:
        if self.use_mock:
            return PlatformActionResult(success=True, raw_response={"mock": True, "price": str(price)})

        max_retries = self.max_retries
        last_exception = None

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            for attempt in range(1, max(max_retries, 1) + 1):
                try:
                    response = await client.patch(
                        f"/products/{platform_listing_id}/price",
                        json={"price": str(price), "currency": currency},
                    )
                    response.raise_for_status()
                    return PlatformActionResult(success=True, raw_response=response.json())
                except httpx.HTTPError as exc:
                    last_exception = exc
                    logger.warning(
                        "platform_api_retry",
                        platform="temu",
                        method="update_price",
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt >= max(max_retries, 1):
                        return PlatformActionResult(success=False, error_message=str(exc))
                    await asyncio.sleep(min(attempt, 3))

        return PlatformActionResult(success=False, error_message=str(last_exception))

    async def pause_product(self, platform_listing_id: str) -> PlatformActionResult:
        if self.use_mock:
            return PlatformActionResult(success=True, raw_response={"mock": True, "paused": True})

        max_retries = self.max_retries
        last_exception = None

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            for attempt in range(1, max(max_retries, 1) + 1):
                try:
                    response = await client.post(f"/products/{platform_listing_id}/pause")
                    response.raise_for_status()
                    return PlatformActionResult(success=True, raw_response=response.json())
                except httpx.HTTPError as exc:
                    last_exception = exc
                    logger.warning(
                        "platform_api_retry",
                        platform="temu",
                        method="pause_product",
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt >= max(max_retries, 1):
                        return PlatformActionResult(success=False, error_message=str(exc))
                    await asyncio.sleep(min(attempt, 3))

        return PlatformActionResult(success=False, error_message=str(last_exception))

    async def resume_product(self, platform_listing_id: str) -> PlatformActionResult:
        if self.use_mock:
            return PlatformActionResult(success=True, raw_response={"mock": True, "resumed": True})

        max_retries = self.max_retries
        last_exception = None

        async with httpx.AsyncClient(base_url=self.base_url, timeout=self.timeout) as client:
            for attempt in range(1, max(max_retries, 1) + 1):
                try:
                    response = await client.post(f"/products/{platform_listing_id}/resume")
                    response.raise_for_status()
                    return PlatformActionResult(success=True, raw_response=response.json())
                except httpx.HTTPError as exc:
                    last_exception = exc
                    logger.warning(
                        "platform_api_retry",
                        platform="temu",
                        method="resume_product",
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt >= max(max_retries, 1):
                        return PlatformActionResult(success=False, error_message=str(exc))
                    await asyncio.sleep(min(attempt, 3))

        return PlatformActionResult(success=False, error_message=str(last_exception))

    async def get_listing_metrics(self, platform_listing_id: str, metric_date: date) -> PlatformMetrics:
        """Fetch daily listing metrics from Temu."""
        if self.use_mock:
            seed = f"temu:{platform_listing_id}:{metric_date.isoformat()}"
            rng = random.Random(seed)
            impressions = rng.randint(800, 4000)
            clicks = rng.randint(max(1, impressions // 40), max(2, impressions // 8))
            orders = rng.randint(0, max(1, clicks // 4))
            units_sold = max(orders, orders + rng.randint(0, max(1, orders)))
            revenue = Decimal(units_sold) * Decimal(str(rng.uniform(18, 65))).quantize(Decimal("0.01"))
            ad_spend = Decimal(clicks) * Decimal(str(rng.uniform(0.15, 1.2))).quantize(Decimal("0.01"))
            refund_amount = Decimal(rng.randint(0, max(0, orders))) * Decimal("3.50")
            return PlatformMetrics(
                impressions=impressions,
                clicks=clicks,
                orders=orders,
                units_sold=units_sold,
                revenue=revenue,
                ad_spend=ad_spend,
                returns_count=min(orders, rng.randint(0, 2)),
                refund_amount=refund_amount,
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
