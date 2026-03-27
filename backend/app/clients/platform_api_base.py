"""Base platform API client interfaces for auto actions."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any, Optional


@dataclass
class PlatformActionResult:
    """Unified result for platform actions."""

    success: bool
    platform_listing_id: Optional[str] = None
    platform_url: Optional[str] = None
    raw_response: Optional[dict[str, Any]] = None
    error_message: Optional[str] = None


@dataclass
class PlatformMetrics:
    """Daily performance metrics from platform API."""

    impressions: int
    clicks: int
    orders: int
    units_sold: int
    revenue: Decimal
    ad_spend: Decimal
    returns_count: int = 0
    refund_amount: Decimal = Decimal("0.00")


class PlatformAPIError(Exception):
    """Raised when platform API action fails."""


class PlatformAPIBase(ABC):
    """Abstract base class for platform API clients."""

    @abstractmethod
    async def create_product(self, payload: dict[str, Any]) -> PlatformActionResult:
        """Create/publish a product on the platform."""

    @abstractmethod
    async def update_price(
        self,
        platform_listing_id: str,
        price: Decimal,
        currency: str,
    ) -> PlatformActionResult:
        """Update listing price on the platform."""

    @abstractmethod
    async def pause_product(self, platform_listing_id: str) -> PlatformActionResult:
        """Pause listing on the platform."""

    @abstractmethod
    async def resume_product(self, platform_listing_id: str) -> PlatformActionResult:
        """Resume listing on the platform."""

    @abstractmethod
    async def get_listing_metrics(self, platform_listing_id: str, metric_date: date) -> PlatformMetrics:
        """Fetch daily performance metrics for a listing."""

    async def close(self) -> None:
        """Close any underlying resources."""
        return None
