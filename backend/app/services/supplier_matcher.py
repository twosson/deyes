"""Supplier matching service.

Behavior:
- For 1688 candidates, prefer extracting supplier candidates from adapter-provided data
- For other platforms, retain the existing mock fallback behavior
"""
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from app.core.enums import SourcePlatform
from app.core.logging import get_logger

logger = get_logger(__name__)


class SupplierMatch:
    """Matched supplier data."""

    def __init__(
        self,
        supplier_name: str,
        supplier_url: str,
        supplier_sku: str,
        supplier_price: Optional[Decimal],
        moq: Optional[int],
        confidence_score: Decimal,
        raw_payload: Optional[dict] = None,
    ):
        self.supplier_name = supplier_name
        self.supplier_url = supplier_url
        self.supplier_sku = supplier_sku
        self.supplier_price = supplier_price
        self.moq = moq
        self.confidence_score = confidence_score
        self.raw_payload = raw_payload or {}


class SupplierMatcherService:
    """Service for matching products with suppliers."""

    async def find_suppliers(
        self,
        product_title: str,
        product_category: Optional[str] = None,
        limit: int = 3,
        source_platform: SourcePlatform | None = None,
        supplier_candidates: Optional[list[dict]] = None,
        raw_payload: Optional[dict] = None,
    ) -> list[SupplierMatch]:
        """Find matching suppliers.

        For 1688, prefer real supplier data already present on the discovered candidate.
        For other platforms, or when no extractable supplier info exists, fall back to mock data.
        """
        extracted = self._extract_suppliers(
            source_platform=source_platform,
            supplier_candidates=supplier_candidates or [],
            raw_payload=raw_payload or {},
            limit=limit,
        )
        if extracted:
            logger.info(
                "suppliers_extracted_from_source",
                product_title=product_title,
                source_platform=source_platform.value if source_platform else None,
                count=len(extracted),
            )
            return extracted

        suppliers = self._build_mock_suppliers(product_title=product_title, limit=limit)
        logger.info(
            "suppliers_matched_with_fallback",
            product_title=product_title,
            source_platform=source_platform.value if source_platform else None,
            count=len(suppliers),
        )
        return suppliers

    def _extract_suppliers(
        self,
        *,
        source_platform: SourcePlatform | None,
        supplier_candidates: list[dict],
        raw_payload: dict,
        limit: int,
    ) -> list[SupplierMatch]:
        """Extract supplier matches from source-provided data."""
        if source_platform == SourcePlatform.ALIBABA_1688:
            direct = self._extract_from_supplier_candidates(supplier_candidates=supplier_candidates, limit=limit)
            if direct:
                return direct

            extracted_from_payload = self._extract_from_1688_payload(raw_payload=raw_payload)
            if extracted_from_payload:
                return extracted_from_payload[:limit]

        return []

    def _extract_from_supplier_candidates(
        self,
        *,
        supplier_candidates: list[dict],
        limit: int,
    ) -> list[SupplierMatch]:
        """Convert adapter-provided supplier candidate dicts into service objects."""
        matches: list[SupplierMatch] = []
        for candidate in supplier_candidates[:limit]:
            supplier_name = candidate.get("supplier_name") or candidate.get("company_name")
            supplier_url = candidate.get("supplier_url") or candidate.get("detail_url") or ""
            supplier_sku = candidate.get("supplier_sku") or candidate.get("item_id") or ""
            if not supplier_name and not supplier_url:
                continue

            matches.append(
                SupplierMatch(
                    supplier_name=supplier_name or f"1688 Supplier {supplier_sku or len(matches) + 1}",
                    supplier_url=supplier_url,
                    supplier_sku=str(supplier_sku) if supplier_sku else "",
                    supplier_price=self._coerce_decimal(candidate.get("supplier_price")),
                    moq=self._coerce_int(candidate.get("moq")),
                    confidence_score=self._coerce_decimal(candidate.get("confidence_score")) or Decimal("0.80"),
                    raw_payload=candidate.get("raw_payload") or candidate,
                )
            )
        return matches

    def _extract_from_1688_payload(self, *, raw_payload: dict) -> list[SupplierMatch]:
        """Extract supplier information from raw 1688 payloads as a fallback.

        Handles two payload structures:
        1. Traditional structure: flat keys like company_name, source_url, etc.
        2. Opportunity-first structure: alphashop_report_item with nested providerInfo.
        """
        # Handle opportunity-first structure: extract from AlphaShop report item
        alphashop_item = raw_payload.get("alphashop_report_item")
        if alphashop_item and isinstance(alphashop_item, dict):
            provider_info = alphashop_item.get("providerInfo")
            if isinstance(provider_info, dict):
                company_name = provider_info.get("companyName")
                shop_url = provider_info.get("shopUrl")

                if company_name or shop_url:
                    # Extract price from the report item
                    supplier_price = None
                    item_price = alphashop_item.get("itemPrice")
                    if isinstance(item_price, dict):
                        supplier_price = self._coerce_decimal(item_price.get("price"))

                    # Extract MOQ from purchaseInfos
                    moq = None
                    purchase_infos = alphashop_item.get("purchaseInfos") or []
                    for pi in purchase_infos:
                        if isinstance(pi, dict):
                            moq = self._coerce_int(pi.get("moq"))
                            if moq is not None:
                                break

                    return [
                        SupplierMatch(
                            supplier_name=company_name or f"1688 Supplier {alphashop_item.get('itemId', 'unknown')}",
                            supplier_url=shop_url or alphashop_item.get("offerDetailUrl") or "",
                            supplier_sku=str(alphashop_item.get("itemId") or alphashop_item.get("productId") or ""),
                            supplier_price=supplier_price,
                            moq=moq,
                            confidence_score=Decimal("0.80"),
                            raw_payload={
                                "source": "alphashop_report_item",
                                "alphashop_report_item": alphashop_item,
                                "provider_info": provider_info,
                            },
                        )
                    ]

        detail_payload = raw_payload.get("detail_payload") or {}
        supplier_name = (
            detail_payload.get("company_name")
            or detail_payload.get("shop_name")
            or detail_payload.get("seller_name")
            or raw_payload.get("company_name")
            or raw_payload.get("shop_name")
            or raw_payload.get("seller_name")
        )
        supplier_url = (
            detail_payload.get("detail_url")
            or raw_payload.get("detail_url")
            or raw_payload.get("source_url")
            or ""
        )
        supplier_sku = (
            detail_payload.get("num_iid")
            or raw_payload.get("source_product_id")
            or raw_payload.get("item_id")
            or ""
        )
        supplier_price = self._coerce_decimal(
            raw_payload.get("price_cny") or detail_payload.get("price") or raw_payload.get("price")
        )
        moq = self._coerce_int(raw_payload.get("moq") or detail_payload.get("moq") or detail_payload.get("min_num"))

        if not supplier_name and not supplier_url:
            return []

        return [
            SupplierMatch(
                supplier_name=supplier_name or f"1688 Supplier {supplier_sku}",
                supplier_url=supplier_url,
                supplier_sku=str(supplier_sku),
                supplier_price=supplier_price,
                moq=moq,
                confidence_score=Decimal("0.75"),
                raw_payload={
                    "source": "raw_payload",
                    "raw_payload": raw_payload,
                },
            )
        ]

    def _build_mock_suppliers(self, *, product_title: str, limit: int) -> list[SupplierMatch]:
        """Build fallback mock suppliers for non-1688 or missing supplier data."""
        suppliers = []
        for i in range(min(limit, 3)):
            base_price = Decimal("10.00") + Decimal(i * 5)
            confidence = Decimal("0.85") - Decimal(i * Decimal("0.10"))
            suppliers.append(
                SupplierMatch(
                    supplier_name=f"Mock Supplier {i + 1}",
                    supplier_url=f"https://1688.com/offer/{uuid4().hex[:12]}.html",
                    supplier_sku=f"SKU-{uuid4().hex[:8].upper()}",
                    supplier_price=base_price,
                    moq=50 + (i * 50),
                    confidence_score=confidence,
                    raw_payload={
                        "mock": True,
                        "product_title": product_title,
                    },
                )
            )
        return suppliers

    def _coerce_decimal(self, value) -> Optional[Decimal]:
        """Convert supplier numeric fields to Decimal when possible."""
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

    def _coerce_int(self, value) -> int | None:
        """Convert supplier integer fields when possible."""
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
