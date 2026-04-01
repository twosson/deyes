"""AlphaShop API client.

Provides integration with AlphaShop keyword research and supplier discovery APIs.

Documentation source: local docs under `docs/ashop/`.

Features:
- JWT-based Authorization header generation using AccessKey/SecretKey
- Shared HTTP transport with retry handling
- Response normalization for keyword search, supplier selection, supplier search,
  and inquiry task APIs
- Exponential backoff with jitter for retryable errors
"""
from __future__ import annotations

import asyncio
import random
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import httpx
from jose import jwt

from app.core.config import get_settings
from app.core.logging import get_logger

logger = get_logger(__name__)


class AlphaShopClient:
    """Client for AlphaShop APIs."""

    KEYWORD_SEARCH_ENDPOINT = "/opp.selection.keyword.search/1.0"
    NEWPRODUCT_REPORT_ENDPOINT = "/opp.selection.newproduct.report/1.0"
    INTELLIGENT_SUPPLIER_SELECTION_ENDPOINT = "/ai.select.provider.search/1.0"
    SUPPLIER_INFO_SEARCH_ENDPOINT = "/inquiry.supplier.query/1.0"
    BATCH_INQUIRY_SUBMIT_ENDPOINT = "/inquiry.task.submit.batchItem/1.0"
    INQUIRY_RESULT_QUERY_ENDPOINT = "/inquiry.task.query.info/1.0"

    TOKEN_TTL_SECONDS = 1800
    TOKEN_NOT_BEFORE_SKEW_SECONDS = 5

    RETRYABLE_RESULT_CODES = {
        "FAIL_TRIGGER_QPS_LIMIT_POLICY",
        "FAIL_SERVER_INTERNAL_ERROR",
        "TIMEOUT_ERROR",
        "KEYWORD_SEARCH_ERROR",
        "NEW_PRODUCT_REPORT_ERROR",
    }

    def __init__(
        self,
        *,
        base_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        settings = get_settings()
        self.base_url = (base_url or settings.alphashop_base_url).rstrip("/")
        self.access_key = access_key or settings.alphashop_api_key
        self.secret_key = secret_key or settings.alphashop_secret_key
        self.timeout = timeout or settings.alphashop_timeout
        self.max_retries = (
            max_retries if max_retries is not None else settings.alphashop_max_retries
        )
        self._http_client: Optional[httpx.AsyncClient] = None
        self._cached_token: Optional[str] = None
        self._cached_token_expires_at: Optional[datetime] = None

        if not self.access_key:
            raise ValueError("AlphaShop access key is required")
        if not self.secret_key:
            raise ValueError("AlphaShop secret key is required")

    async def _get_http_client(self) -> httpx.AsyncClient:
        """Get or create shared HTTP client."""
        if self._http_client is None:
            self._http_client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=self.timeout,
                follow_redirects=True,
                headers={"Content-Type": "application/json"},
            )
        return self._http_client

    async def close(self) -> None:
        """Close underlying HTTP client."""
        if self._http_client is not None:
            await self._http_client.aclose()
            self._http_client = None

    async def search_keywords(
        self,
        *,
        platform: str,
        region: str,
        keyword: str,
        listing_time: str = "180",
    ) -> dict[str, Any]:
        """Call AlphaShop AI keyword query API."""
        response = await self._request(
            self.KEYWORD_SEARCH_ENDPOINT,
            {
                "platform": self._normalize_market_platform(platform),
                "region": region,
                "keyword": keyword,
                "listingTime": listing_time,
            },
        )
        return {
            "keyword_list": self._extract_keyword_list(response),
            "request_id": response.get("requestId"),
            "raw": response,
        }

    async def newproduct_report(
        self,
        *,
        target_platform: str,
        target_country: str,
        product_keyword: str,
    ) -> dict[str, Any]:
        """Call AlphaShop new product report API for a validated keyword."""
        payload: dict[str, Any] = {
            "targetPlatform": self._normalize_report_target_platform(target_platform),
            "targetCountry": target_country,
            "productKeyword": product_keyword,
        }

        response = await self._request(self.NEWPRODUCT_REPORT_ENDPOINT, payload)
        product_list = self._extract_newproduct_list(response)
        keyword_summary = self._extract_newproduct_keyword_summary(response)
        return {
            "items": product_list,
            "product_list": product_list,
            "keyword_summary": keyword_summary,
            "request_id": response.get("requestId"),
            "raw": response,
        }

    async def intelligent_supplier_selection(
        self,
        *,
        intention: str,
        query: str | None = None,
        search_image_url: str | None = None,
    ) -> dict[str, Any]:
        """Call AlphaShop intelligent supplier selection API."""
        payload: dict[str, Any] = {"intention": intention}
        if query:
            payload["query"] = query
        if search_image_url:
            payload["searchImageUrl"] = search_image_url

        response = await self._request(self.INTELLIGENT_SUPPLIER_SELECTION_ENDPOINT, payload)
        outer_result = response.get("result") or {}
        nested_result = outer_result.get("result") if isinstance(outer_result, dict) else {}
        if not isinstance(nested_result, dict):
            nested_result = {}

        return {
            "real_intention": nested_result.get("realIntention"),
            "offer_info": nested_result.get("offerInfo") or {},
            "provider_info": nested_result.get("providerInfo") or {},
            "chat_response": nested_result.get("chatResponse"),
            "session_id": nested_result.get("sessionId"),
            "task_id": nested_result.get("taskId"),
            "request_id": response.get("requestId"),
            "raw": response,
        }

    async def search_supplier_info(self, *, company: str) -> dict[str, Any]:
        """Call AlphaShop supplier info search API."""
        response = await self._request(
            self.SUPPLIER_INFO_SEARCH_ENDPOINT,
            {"company": company},
        )
        result = response.get("result") or {}
        suppliers = result.get("data") if isinstance(result, dict) else None
        if not isinstance(suppliers, list):
            suppliers = []
        return {
            "suppliers": suppliers,
            "request_id": response.get("requestId"),
            "raw": response,
        }

    async def submit_batch_inquiry(
        self,
        *,
        question_list: list[str],
        item_list: list[str],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Submit asynchronous batch inquiry task."""
        payload: dict[str, Any] = {
            "questionList": question_list,
            "itemList": item_list,
        }
        payload.update(kwargs)

        response = await self._request(self.BATCH_INQUIRY_SUBMIT_ENDPOINT, payload)
        result = response.get("result") or {}
        return {
            "task_id": result.get("data") if isinstance(result, dict) else None,
            "trace_id": result.get("traceId") if isinstance(result, dict) else None,
            "request_id": response.get("requestId"),
            "raw": response,
        }

    async def query_inquiry_result(self, *, task_id: str) -> dict[str, Any]:
        """Query asynchronous inquiry task result."""
        response = await self._request(
            self.INQUIRY_RESULT_QUERY_ENDPOINT,
            {"taskId": task_id},
        )
        result = response.get("result") or {}
        return {
            "data": result.get("data") if isinstance(result, dict) else None,
            "request_id": response.get("requestId"),
            "raw": response,
        }

    async def _request(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        """Make authenticated POST request to AlphaShop API."""
        client = await self._get_http_client()
        settings = get_settings()
        last_error: Exception | None = None

        # Log request payload for debugging
        logger.debug(
            "alphashop_request_payload",
            endpoint=endpoint,
            payload=payload,
        )

        for attempt in range(1, max(self.max_retries, 1) + 1):
            try:
                response = await client.post(
                    endpoint,
                    json=payload,
                    headers={"Authorization": self._build_authorization_header()},
                )
                response.raise_for_status()
                data = response.json()

                # Log raw response for debugging
                logger.debug(
                    "alphashop_response_raw",
                    endpoint=endpoint,
                    response=data,
                )

                self._ensure_success(data, endpoint=endpoint)
                return data
            except RuntimeError as exc:
                last_error = exc
                code = getattr(exc, "alphashop_code", None)
                logger.warning(
                    "alphashop_api_error",
                    endpoint=endpoint,
                    attempt=attempt,
                    error=str(exc),
                    code=code,
                )
                if code not in self.RETRYABLE_RESULT_CODES or attempt >= max(self.max_retries, 1):
                    raise
                # Exponential backoff with jitter for retryable errors
                base_delay = settings.alphashop_retry_base_delay_seconds
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.debug(
                    "alphashop_retry_backoff",
                    endpoint=endpoint,
                    attempt=attempt,
                    delay_seconds=round(delay, 3),
                    code=code,
                )
                await asyncio.sleep(delay)
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                logger.warning(
                    "alphashop_transport_failed",
                    endpoint=endpoint,
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt >= max(self.max_retries, 1):
                    raise
                # Exponential backoff for transport errors
                base_delay = settings.alphashop_retry_base_delay_seconds
                delay = base_delay * (2 ** (attempt - 1)) + random.uniform(0, 0.5)
                logger.debug(
                    "alphashop_retry_backoff",
                    endpoint=endpoint,
                    attempt=attempt,
                    delay_seconds=round(delay, 3),
                    error_type=type(exc).__name__,
                )
                await asyncio.sleep(delay)

        raise RuntimeError(f"AlphaShop request failed for {endpoint}: {last_error}")

    def _normalize_market_platform(self, platform: str | None) -> str:
        """Normalize market discovery platform to AlphaShop's documented values."""
        normalized = (platform or "").strip().lower()
        if normalized in {"tiktok", "tiktok_shop"}:
            return "TikTok"
        return "Amazon"

    def _normalize_report_target_platform(self, platform: str | None) -> str:
        """Normalize newproduct.report targetPlatform to AlphaShop's documented lowercase values."""
        normalized = (platform or "").strip().lower()
        if normalized in {"tiktok", "tiktok_shop"}:
            return "tiktok"
        return "amazon"

    def _build_authorization_header(self) -> str:
        """Build Bearer Authorization header value."""
        return f"Bearer {self._create_api_token()}"

    def _create_api_token(self) -> str:
        """Create or reuse cached AlphaShop JWT token."""
        now = datetime.now(timezone.utc)
        if (
            self._cached_token
            and self._cached_token_expires_at is not None
            and now < self._cached_token_expires_at - timedelta(seconds=30)
        ):
            return self._cached_token

        expires_at = now + timedelta(seconds=self.TOKEN_TTL_SECONDS)
        not_before = now - timedelta(seconds=self.TOKEN_NOT_BEFORE_SKEW_SECONDS)
        claims = {
            "iss": self.access_key,
            "exp": int(expires_at.timestamp()),
            "nbf": int(not_before.timestamp()),
        }
        token = jwt.encode(
            claims,
            self.secret_key,
            algorithm="HS256",
            headers={"alg": "HS256"},
        )
        self._cached_token = token
        self._cached_token_expires_at = expires_at
        return token

    def _ensure_success(self, data: dict[str, Any], *, endpoint: str) -> None:
        """Validate API success semantics across AlphaShop endpoints."""
        outer_code = data.get("resultCode") or data.get("code")
        outer_success = data.get("success")
        outer_message = data.get("msg") or data.get("message") or ""

        result = data.get("result") if isinstance(data.get("result"), dict) else None
        nested_code = result.get("code") if result else None
        nested_success = result.get("success") if result else None
        nested_message = result.get("msg") if result else None

        if outer_code not in (None, "SUCCESS") or outer_success is False:
            message = outer_message or nested_message or "Unknown AlphaShop API error"
            error = RuntimeError(f"AlphaShop API error [{outer_code}]: {message}")
            setattr(error, "alphashop_code", outer_code)
            raise error

        if nested_code not in (None, "SUCCESS") or nested_success is False:
            code = nested_code or outer_code or "UNKNOWN"
            message = nested_message or outer_message or "Unknown AlphaShop API error"
            error = RuntimeError(f"AlphaShop API error [{code}]: {message}")
            setattr(error, "alphashop_code", code)
            raise error

        logger.debug(
            "alphashop_request_succeeded",
            endpoint=endpoint,
            outer_code=outer_code,
            nested_code=nested_code,
        )

    def _extract_keyword_list(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract keyword list from AlphaShop keyword response variants.

        AlphaShop returns keywords in nested structure:
        response["result"]["data"]["keywordList"]
        """
        # Try result.data.keywordList (actual AlphaShop structure)
        result = response.get("result")
        if isinstance(result, dict):
            nested_data = result.get("data")
            if isinstance(nested_data, dict):
                keyword_list = nested_data.get("keywordList")
                if isinstance(keyword_list, list):
                    return [item for item in keyword_list if isinstance(item, dict)]
            # Try result.data as list
            if isinstance(nested_data, list):
                return [item for item in nested_data if isinstance(item, dict)]

        # Try model (legacy variant)
        model = response.get("model")
        if isinstance(model, list):
            return [item for item in model if isinstance(item, dict)]
        if isinstance(model, dict):
            keyword_list = model.get("keywordList")
            if isinstance(keyword_list, list):
                return [item for item in keyword_list if isinstance(item, dict)]

        # Try data as list (legacy variant)
        data = response.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        return []

    def _extract_newproduct_list(self, response: dict[str, Any]) -> list[dict[str, Any]]:
        """Extract product list from AlphaShop newproduct report response variants."""
        result = response.get("result")
        if isinstance(result, dict):
            nested_data = result.get("data")
            if isinstance(nested_data, dict):
                product_list = nested_data.get("productList")
                if isinstance(product_list, list):
                    return [item for item in product_list if isinstance(item, dict)]
            if isinstance(nested_data, list):
                return [item for item in nested_data if isinstance(item, dict)]

        model = response.get("model")
        if isinstance(model, list):
            return [item for item in model if isinstance(item, dict)]
        if isinstance(model, dict):
            product_list = model.get("productList")
            if isinstance(product_list, list):
                return [item for item in product_list if isinstance(item, dict)]

        data = response.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]

        return []

    def _extract_newproduct_keyword_summary(self, response: dict[str, Any]) -> dict[str, Any]:
        """Extract keyword summary from AlphaShop newproduct report response."""
        result = response.get("result")
        if isinstance(result, dict):
            nested_data = result.get("data")
            if isinstance(nested_data, dict):
                keyword_summary = nested_data.get("keywordSummary")
                if isinstance(keyword_summary, dict):
                    return keyword_summary

        model = response.get("model")
        if isinstance(model, dict):
            keyword_summary = model.get("keywordSummary")
            if isinstance(keyword_summary, dict):
                return keyword_summary

        return {}
