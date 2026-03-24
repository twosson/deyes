"""TMAPI 1688 API client.

This client provides direct access to TMAPI's 1688 marketplace integration endpoints.
It handles transport, authentication, retry logic, and endpoint-level response normalization.

Official documentation: https://tmapi.top/docs/ali/
"""
from __future__ import annotations

import asyncio
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.logging import get_logger


class TMAPI1688Client:
    """Client for TMAPI 1688 API integration.

    Responsibilities:
    - TMAPI gateway transport (base URL, auth, timeout, retry)
    - 1688 endpoint wrappers (search, detail, shipping, ratings, shop, desc, image search)
    - Endpoint-level response normalization (extract stable structures)

    Does NOT handle:
    - Business-level selection strategy
    - Cross-endpoint orchestration
    - Ranking or filtering logic
    """

    SUCCESS_CODE = 200
    PLATFORM = "1688"

    def __init__(
        self,
        *,
        api_token: str | None = None,
        base_url: str | None = None,
        timeout: int | None = None,
        max_retries: int | None = None,
    ):
        settings = get_settings()
        self.api_token = api_token or settings.tmapi_api_token
        self.base_url = (base_url or settings.tmapi_base_url).rstrip("/")
        self.timeout = timeout or settings.tmapi_timeout
        self.max_retries = max_retries if max_retries is not None else settings.tmapi_max_retries
        self.logger = get_logger(__name__)

        if not self.api_token:
            raise ValueError("TMAPI API token is required")

    async def search_items(
        self,
        *,
        keyword: str | None = None,
        page: int = 1,
        page_size: int = 20,
        language: str = "en",
        sort: str = "default",
        price_start: float | None = None,
        price_end: float | None = None,
        cat_id: int | None = None,
        new_arrival: bool | None = None,
        support_dropshipping: bool | None = None,
        free_shipping: bool | None = None,
        is_super_factory: bool | None = None,
    ) -> dict[str, Any]:
        """Search 1688 products by keyword.

        Returns normalized search envelope.
        """
        params: dict[str, Any] = {
            "page": page,
            "page_size": page_size,
            "language": language,
            "sort": sort,
        }
        if keyword:
            params["keyword"] = keyword
        if price_start is not None:
            params["price_start"] = str(price_start)
        if price_end is not None:
            params["price_end"] = str(price_end)
        if cat_id is not None:
            params["cat_id"] = cat_id
        if new_arrival is not None:
            params["new_arrival"] = new_arrival
        if support_dropshipping is not None:
            params["support_dropshipping"] = support_dropshipping
        if free_shipping is not None:
            params["free_shipping"] = free_shipping
        if is_super_factory is not None:
            params["is_super_factory"] = is_super_factory

        response = await self._request("/1688/global/search/items", params)
        return self._normalize_search_response(response, page=page, page_size=page_size)

    async def search_items_by_image(
        self,
        *,
        img_url: str,
        page: int = 1,
        page_size: int = 20,
        language: str = "en",
        sort: str = "default",
        support_dropshipping: bool | None = None,
        is_factory: bool | None = None,
        verified_supplier: bool | None = None,
        free_shipping: bool | None = None,
        new_arrival: bool | None = None,
    ) -> dict[str, Any]:
        """Search 1688 products by image.

        Returns normalized search envelope.
        """
        params: dict[str, Any] = {
            "img_url": img_url,
            "page": page,
            "page_size": page_size,
            "language": language,
            "sort": sort,
        }
        if support_dropshipping is not None:
            params["support_dropshipping"] = support_dropshipping
        if is_factory is not None:
            params["is_factory"] = is_factory
        if verified_supplier is not None:
            params["verified_supplier"] = verified_supplier
        if free_shipping is not None:
            params["free_shipping"] = free_shipping
        if new_arrival is not None:
            params["new_arrival"] = new_arrival

        response = await self._request("/1688/global/search/image", params)
        return self._normalize_search_response(response, page=page, page_size=page_size)

    async def get_item_detail(
        self,
        *,
        item_id: str,
        language: str = "en",
    ) -> dict[str, Any]:
        """Get detailed product information.

        Returns normalized item detail mapping.
        """
        response = await self._request("/1688/global/item_detail", {"item_id": item_id, "language": language})
        return self._extract_data(response)

    async def get_item_shipping(
        self,
        *,
        item_id: str,
        province: str,
        total_quantity: int = 1,
        total_weight: float | None = None,
    ) -> dict[str, Any]:
        """Get shipping fees for a product.

        Returns normalized shipping mapping.
        """
        params: dict[str, Any] = {
            "item_id": item_id,
            "province": province,
            "total_quantity": total_quantity,
        }
        if total_weight is not None:
            params["total_weight"] = total_weight

        response = await self._request("/1688/item/shipping", params)
        return self._extract_data(response)

    async def get_item_ratings(
        self,
        *,
        item_id: str,
        page: int = 1,
        sort_type: str = "default",
    ) -> dict[str, Any]:
        """Get product ratings/reviews.

        Returns normalized ratings mapping.
        """
        response = await self._request(
            "/1688/item/rating",
            {
                "item_id": item_id,
                "page": page,
                "sort_type": sort_type,
            },
        )
        return self._extract_data(response)

    async def get_shop_info(
        self,
        *,
        shop_url: str | None = None,
        member_id: str | None = None,
    ) -> dict[str, Any]:
        """Get shop information.

        Returns normalized shop info mapping.
        """
        if not shop_url and not member_id:
            raise ValueError("Either shop_url or member_id is required")

        params: dict[str, Any] = {}
        if shop_url:
            params["shop_url"] = shop_url
        if member_id:
            params["member_id"] = member_id

        response = await self._request("/1688/shop/shop_info", params)
        return self._extract_data(response)

    async def get_shop_items(
        self,
        *,
        shop_url: str,
        page: int = 1,
        page_size: int = 20,
        sort: str = "default",
        cat: str | None = None,
        cat_type: str | None = None,
    ) -> dict[str, Any]:
        """Get shop items.

        Returns normalized search envelope.
        """
        params: dict[str, Any] = {
            "shop_url": shop_url,
            "page": page,
            "page_size": page_size,
            "sort": sort,
        }
        if cat:
            params["cat"] = cat
        if cat_type:
            params["cat_type"] = cat_type

        response = await self._request("/1688/shop/items/v2", params)
        return self._normalize_shop_items_response(response, page=page, page_size=page_size)

    async def get_item_desc(
        self,
        *,
        item_id: str,
    ) -> dict[str, Any]:
        """Get item description images.

        Returns normalized desc mapping.
        """
        response = await self._request("/1688/item_desc", {"item_id": item_id})
        return self._extract_data(response)

    async def _request(
        self,
        endpoint: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Make authenticated request to TMAPI gateway."""
        query_params = {
            "apiToken": self.api_token,
            **(params or {}),
        }
        url = f"{self.base_url}{endpoint}"

        self.logger.debug(
            "tmapi_api_request",
            platform=self.PLATFORM,
            endpoint=endpoint,
            url=url,
            params={key: value for key, value in query_params.items() if key != "apiToken"},
        )

        last_exception: Exception | None = None
        async with httpx.AsyncClient(timeout=self.timeout, follow_redirects=True) as client:
            for attempt in range(1, max(self.max_retries, 1) + 1):
                try:
                    response = await client.get(url, params=query_params)
                    response.raise_for_status()
                    data = response.json()
                    self._ensure_success(data, endpoint=endpoint)
                    return data
                except RuntimeError:
                    raise
                except (httpx.HTTPError, ValueError) as exc:
                    last_exception = exc
                    self.logger.warning(
                        "tmapi_api_transport_failed",
                        platform=self.PLATFORM,
                        endpoint=endpoint,
                        attempt=attempt,
                        error=str(exc),
                    )
                    if attempt >= max(self.max_retries, 1):
                        raise
                    await asyncio.sleep(min(attempt, 3))

        raise RuntimeError(f"TMAPI API request failed for {self.PLATFORM}{endpoint}: {last_exception}")

    def _ensure_success(self, data: dict[str, Any], *, endpoint: str) -> None:
        """Validate TMAPI success semantics."""
        code = data.get("code")

        if code == self.SUCCESS_CODE:
            return

        error_message = data.get("msg") or data.get("message") or "Unknown API error"

        self.logger.error(
            "tmapi_api_error",
            platform=self.PLATFORM,
            endpoint=endpoint,
            code=code,
            message=error_message,
        )
        raise RuntimeError(f"TMAPI API error [{code}]: {error_message}")

    def _normalize_search_response(
        self,
        response: dict[str, Any],
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """Normalize TMAPI search payloads into a stable shape."""
        data = self._extract_data(response)
        items = data.get("items") or []
        current_page = data.get("page") or page
        current_page_size = data.get("page_size") or page_size
        has_next_page = data.get("has_next_page", False)
        total_count = data.get("total_count")

        return {
            "products": items,
            "total": total_count if total_count is not None else len(items),
            "page": current_page,
            "page_size": current_page_size,
            "has_more": has_next_page,
        }

    def _normalize_shop_items_response(
        self,
        response: dict[str, Any],
        *,
        page: int,
        page_size: int,
    ) -> dict[str, Any]:
        """Normalize TMAPI shop items payloads into a stable shape."""
        data = self._extract_data(response)
        items = data.get("items") or []
        current_page = data.get("page") or page
        current_page_size = data.get("page_size") or page_size
        total_count = data.get("total_count")

        has_more = False
        if total_count is not None:
            has_more = current_page * current_page_size < total_count
        elif current_page_size > 0:
            has_more = len(items) >= current_page_size

        return {
            "products": items,
            "total": total_count if total_count is not None else len(items),
            "page": current_page,
            "page_size": current_page_size,
            "has_more": has_more,
        }

    def _extract_data(self, response: dict[str, Any]) -> dict[str, Any]:
        """Extract data payload from TMAPI response."""
        data = response.get("data")
        if isinstance(data, dict):
            return data
        return {}
