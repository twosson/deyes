"""AlphaShop-backed 1688 source adapter.

Replaces TMAPI 1688 client with AlphaShop intelligent supplier selection API.
Maintains the same SourceAdapter interface for seamless integration.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from app.clients.alphashop import AlphaShopClient
from app.core.config import get_settings
from app.core.enums import SourcePlatform
from app.core.logging import get_logger
from app.services.source_adapter import ProductData, SourceAdapter

logger = get_logger(__name__)


class AlphaShop1688Adapter(SourceAdapter):
    """1688 product discovery adapter using AlphaShop intelligent supplier selection API."""

    CNY_TO_USD_RATE = Decimal("0.14")

    def __init__(
        self,
        *,
        alphashop_client: AlphaShopClient | None = None,
    ):
        self.settings = get_settings().model_copy(deep=True)
        self.logger = get_logger(__name__)
        self._alphashop_client = alphashop_client
        self._created_client = False

    async def _get_alphashop_client(self) -> AlphaShopClient | None:
        """Get or create AlphaShop client."""
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
        """Close underlying AlphaShop client."""
        if self._created_client and self._alphashop_client is not None:
            await self._alphashop_client.close()
            self._alphashop_client = None
            self._created_client = False

    async def fetch_products(
        self,
        category: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        price_min: Optional[Decimal] = None,
        price_max: Optional[Decimal] = None,
        limit: int = 10,
        region: Optional[str] = None,
    ) -> list[ProductData]:
        """Fetch products from 1688 using AlphaShop intelligent supplier selection."""
        client = await self._get_alphashop_client()
        if client is None:
            self.logger.warning(
                "alphashop_1688_unavailable",
                category=category,
                region=region,
                reason="missing_configuration_or_disabled",
            )
            return []

        if not keywords:
            self.logger.warning(
                "alphashop_1688_no_keywords",
                category=category,
                region=region,
            )
            return []

        self.logger.info(
            "alphashop_1688_fetch_started",
            category=category,
            keywords=keywords,
            price_min=price_min,
            price_max=price_max,
            limit=limit,
            region=region,
        )

        products: list[ProductData] = []
        seen_item_ids: set[str] = set()

        for keyword in keywords[:limit]:
            try:
                response = await client.intelligent_supplier_selection(
                    intention=keyword,
                    query=keyword,
                )

                offer_info = response.get("offer_info") or {}
                offer_list = offer_info.get("offerList") or []

                for offer in offer_list:
                    if len(products) >= limit:
                        break

                    item_id = offer.get("itemId")
                    if not item_id or item_id in seen_item_ids:
                        continue

                    seen_item_ids.add(item_id)

                    product = self._offer_to_product_data(
                        offer=offer,
                        keyword=keyword,
                        price_min=price_min,
                        price_max=price_max,
                    )

                    if product:
                        products.append(product)

                if len(products) >= limit:
                    break

            except Exception as exc:
                self.logger.warning(
                    "alphashop_1688_keyword_fetch_failed",
                    keyword=keyword,
                    error=str(exc),
                )
                continue

        self.logger.info(
            "alphashop_1688_fetch_completed",
            count=len(products),
            keywords=keywords,
        )

        return products[:limit]

    def _offer_to_product_data(
        self,
        *,
        offer: dict[str, Any],
        keyword: str,
        price_min: Optional[Decimal],
        price_max: Optional[Decimal],
    ) -> Optional[ProductData]:
        """Convert AlphaShop offer to ProductData."""
        item_id = offer.get("itemId")
        if not item_id:
            return None

        title = offer.get("title") or ""
        if not title:
            return None

        # Extract price
        item_price = offer.get("itemPrice")
        price_cny = None
        if isinstance(item_price, dict):
            price_cny = self._coerce_decimal(item_price.get("price"))
        elif item_price is not None:
            price_cny = self._coerce_decimal(item_price)

        # Filter by price range
        if price_min is not None and price_cny is not None:
            price_usd = self._cny_to_usd(price_cny)
            if price_usd < price_min:
                return None

        if price_max is not None and price_cny is not None:
            price_usd = self._cny_to_usd(price_cny)
            if price_usd > price_max:
                return None

        platform_price_usd = self._cny_to_usd(price_cny)

        # Extract sales info
        sales_count = None
        sales_infos = offer.get("salesInfos") or []
        for sales_info in sales_infos:
            if isinstance(sales_info, dict):
                sales_count = self._coerce_int(sales_info.get("salesCount"))
                if sales_count is not None:
                    break

        # Extract images
        main_image_url = offer.get("imageUrl") or ""
        image_urls = offer.get("imageUrls") or []
        if not main_image_url and image_urls:
            main_image_url = image_urls[0] if isinstance(image_urls, list) else ""

        # Extract detail URL
        detail_url = offer.get("offerDetailUrl") or f"https://detail.1688.com/offer/{item_id}.html"

        # Build supplier candidates from provider info
        supplier_candidates = self._build_supplier_candidates(offer)

        # Extract category
        category_name = None
        core_attributes = offer.get("coreAttributes") or []
        for attr in core_attributes:
            if isinstance(attr, dict) and attr.get("name") == "类目":
                category_name = attr.get("value")
                break

        # Build normalized attributes
        normalized_attributes = {
            "category_name": category_name,
            "detail_url": detail_url,
            "matched_keyword": keyword,
            "price_cny": float(price_cny) if price_cny else None,
            "image_urls": image_urls if isinstance(image_urls, list) else [],
        }

        # Extract MOQ and other purchase info
        purchase_infos = offer.get("purchaseInfos") or []
        for purchase_info in purchase_infos:
            if isinstance(purchase_info, dict):
                moq = self._coerce_int(purchase_info.get("moq"))
                if moq is not None:
                    normalized_attributes["moq"] = moq
                    break

        return ProductData(
            source_platform=SourcePlatform.ALIBABA_1688,
            source_product_id=str(item_id),
            source_url=detail_url,
            title=title,
            category=category_name,
            currency="USD",
            platform_price=platform_price_usd,
            sales_count=sales_count,
            rating=None,  # AlphaShop doesn't provide rating in offer list
            main_image_url=main_image_url,
            raw_payload={
                "alphashop_offer": offer,
                "matched_keyword": keyword,
            },
            normalized_attributes=normalized_attributes,
            supplier_candidates=supplier_candidates,
        )

    def _build_supplier_candidates(self, offer: dict[str, Any]) -> list[dict]:
        """Build supplier candidates from AlphaShop offer provider info."""
        supplier_candidates: list[dict] = []

        provider_info = offer.get("providerInfo")
        if not provider_info or not isinstance(provider_info, dict):
            return supplier_candidates

        company_name = provider_info.get("companyName")
        shop_url = provider_info.get("shopUrl")
        item_id = offer.get("itemId")

        if not company_name and not shop_url:
            return supplier_candidates

        # Extract price for supplier
        item_price = offer.get("itemPrice")
        supplier_price_cny = None
        if isinstance(item_price, dict):
            supplier_price_cny = self._coerce_decimal(item_price.get("price"))
        elif item_price is not None:
            supplier_price_cny = self._coerce_decimal(item_price)

        supplier_price_usd = self._cny_to_usd(supplier_price_cny)

        # Extract MOQ
        moq = None
        purchase_infos = offer.get("purchaseInfos") or []
        for purchase_info in purchase_infos:
            if isinstance(purchase_info, dict):
                moq = self._coerce_int(purchase_info.get("moq"))
                if moq is not None:
                    break

        # Build supplier dict matching existing contract
        supplier_dict = {
            "supplier_name": company_name or f"1688 Supplier {item_id}",
            "supplier_url": shop_url or offer.get("offerDetailUrl") or "",
            "supplier_sku": str(item_id) if item_id else "",
            "supplier_price": supplier_price_usd,
            "moq": moq,
            "confidence_score": Decimal("0.80"),  # Default confidence for AlphaShop matches
            "raw_payload": {
                "provider_info": provider_info,
                "offer": offer,
            },
        }

        supplier_candidates.append(supplier_dict)

        return supplier_candidates

    def _cny_to_usd(self, cny: Optional[Decimal]) -> Optional[Decimal]:
        """Convert CNY to USD."""
        if cny is None:
            return None
        return cny * self.CNY_TO_USD_RATE

    def _coerce_decimal(self, value: Any) -> Optional[Decimal]:
        """Convert value to Decimal."""
        if value is None or value == "":
            return None
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            try:
                return Decimal(value)
            except Exception:
                return None
        return None

    def _coerce_int(self, value: Any) -> Optional[int]:
        """Convert value to int."""
        if value is None or value == "":
            return None
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
