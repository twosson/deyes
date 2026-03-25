"""Temu platform adapter.

Implements the PlatformAdapter interface for Temu marketplace.

Temu API Notes:
- Temu uses a seller API for product management
- Documentation: https://seller.temu.com/api-docs
- Key features: Social commerce, group buying, US/EU/Global markets
"""
from __future__ import annotations

import hashlib
import hmac
import time
from decimal import Decimal
from typing import Any
from uuid import UUID

import httpx

from app.core.config import get_settings
from app.core.enums import PlatformListingStatus, TargetPlatform
from app.core.logging import get_logger
from app.db.models import CandidateProduct, ContentAsset
from app.services.platforms.base import PlatformAdapter, PlatformListingData


class TemuAdapter(PlatformAdapter):
    """Temu platform adapter.

    Supports:
    - Product listing creation
    - Inventory sync
    - Price updates
    - Multi-region (US, UK, DE, FR, ES, IT, AU, CA)
    """

    # Temu API endpoints
    ENDPOINTS = {
        "us": "https://api.temu.com/seller/v1",
        "uk": "https://api.temu.co.uk/seller/v1",
        "de": "https://api.temu.de/seller/v1",
        "fr": "https://api.temu.fr/seller/v1",
        "es": "https://api.temu.es/seller/v1",
        "it": "https://api.temu.it/seller/v1",
        "au": "https://api.temu.com.au/seller/v1",
        "ca": "https://api.temu.ca/seller/v1",
    }

    # Currency mapping by region
    CURRENCIES = {
        "us": "USD",
        "uk": "GBP",
        "de": "EUR",
        "fr": "EUR",
        "es": "EUR",
        "it": "EUR",
        "au": "AUD",
        "ca": "CAD",
    }

    # Temu category mapping
    # TODO: Add full category mapping from Temu documentation
    CATEGORY_MAPPING = {
        "phone accessories": 1001,
        "home gadgets": 2001,
        "beauty tools": 3001,
        "pet supplies": 4001,
        "electronics": 5001,
        "home decor": 6001,
        "fashion": 7001,
        "sports": 8001,
    }

    # Temu-specific requirements
    MAX_TITLE_LENGTH = 200
    MAX_IMAGES = 10
    MAX_DESCRIPTION_LENGTH = 5000
    MIN_PRICE_USD = Decimal("0.50")
    MAX_PRICE_USD = Decimal("999.99")

    def __init__(
        self,
        *,
        app_key: str | None = None,
        app_secret: str | None = None,
        region: str = "us",
    ):
        super().__init__(TargetPlatform.TEMU)
        settings = get_settings()
        self.app_key = app_key or settings.temu_app_key or ""
        self.app_secret = app_secret or settings.temu_app_secret or ""
        self.region = region
        self.base_url = self.ENDPOINTS.get(region, self.ENDPOINTS["us"])
        self.timeout = 30

    async def create_listing(
        self,
        *,
        product: CandidateProduct,
        assets: list[ContentAsset],
        region: str,
        price: Decimal,
        currency: str,
        inventory: int,
        title: str | None = None,
        description: str | None = None,
        category: str | None = None,
        attributes: dict[str, Any] | None = None,
    ) -> PlatformListingData:
        """Create a new listing on Temu.

        Temu API flow:
        1. Upload images to Temu
        2. Create product with images
        3. Set price and inventory
        """
        # Validate
        is_valid, error = await self.validate_listing_data(
            product=product,
            assets=assets,
            region=region,
            price=price,
        )
        if not is_valid:
            raise ValueError(error)

        # Format title
        formatted_title = self.format_title(title or product.title, self.MAX_TITLE_LENGTH)

        # Upload images to Temu
        temu_image_ids = await self._upload_images(assets)

        # Map category
        temu_category_id = self.map_category(category or product.category)

        # Build product data
        product_data = {
            "title": formatted_title,
            "description": description or self._generate_description(product),
            "category_id": temu_category_id,
            "images": temu_image_ids,
            "price": str(price),
            "currency": currency,
            "inventory": inventory,
            "attributes": attributes or {},
            "source": "deyes",  # Mark as sourced from our system
        }

        # Call Temu API
        try:
            response = await self._call_api(
                method="product.add",
                data=product_data,
            )

            temu_sku = response.get("sku")
            temu_product_id = response.get("product_id")
            listing_url = f"https://www.temu.com/product-{temu_product_id}.html"

            self.logger.info(
                "temu_listing_created",
                temu_sku=temu_sku,
                product_id=str(product.id),
                price=str(price),
                inventory=inventory,
            )

            return PlatformListingData(
                platform_listing_id=temu_sku,
                platform_url=listing_url,
                status=PlatformListingStatus.ACTIVE,
                platform_data={
                    "temu_product_id": temu_product_id,
                    "temu_sku": temu_sku,
                    "category_id": temu_category_id,
                    "image_ids": temu_image_ids,
                },
            )

        except Exception as e:
            self.logger.error(
                "temu_listing_failed",
                product_id=str(product.id),
                error=str(e),
            )
            raise

    async def update_listing(
        self,
        *,
        platform_listing_id: str,
        price: Decimal | None = None,
        inventory: int | None = None,
        title: str | None = None,
        description: str | None = None,
        images: list[str] | None = None,
        status: PlatformListingStatus | None = None,
    ) -> bool:
        """Update an existing Temu listing."""
        update_data = {"sku": platform_listing_id}

        if price is not None:
            update_data["price"] = str(price)
        if inventory is not None:
            update_data["inventory"] = inventory
        if title is not None:
            update_data["title"] = self.format_title(title, self.MAX_TITLE_LENGTH)
        if description is not None:
            update_data["description"] = description[:self.MAX_DESCRIPTION_LENGTH]
        if status is not None:
            update_data["status"] = self._map_status_to_temu(status)

        try:
            await self._call_api(
                method="product.update",
                data=update_data,
            )

            self.logger.info(
                "temu_listing_updated",
                sku=platform_listing_id,
                updates=list(update_data.keys()),
            )

            return True

        except Exception as e:
            self.logger.error(
                "temu_update_failed",
                sku=platform_listing_id,
                error=str(e),
            )
            return False

    async def sync_inventory(
        self,
        *,
        platform_listing_id: str,
        new_inventory: int,
    ) -> bool:
        """Sync inventory to Temu."""
        return await self.update_listing(
            platform_listing_id=platform_listing_id,
            inventory=new_inventory,
        )

    async def get_listing_status(
        self,
        *,
        platform_listing_id: str,
    ) -> dict[str, Any]:
        """Get current listing status from Temu."""
        try:
            response = await self._call_api(
                method="product.get",
                data={"sku": platform_listing_id},
            )

            price = response.get("price")
            sales = response.get("sales_count")
            orders = response.get("order_count")
            units_sold = response.get("units_sold")

            return {
                "sku": response.get("sku", platform_listing_id),
                "status": response.get("status"),
                "inventory": response.get("inventory"),
                "price": Decimal(str(price)) if price is not None else None,
                "sales": sales,
                "views": response.get("view_count"),
                "clicks": response.get("click_count"),
                "orders": orders if orders is not None else sales,
                "units_sold": units_sold if units_sold is not None else sales,
            }

        except Exception as e:
            self.logger.error(
                "temu_get_status_failed",
                sku=platform_listing_id,
                error=str(e),
            )
            return {}

    async def delist_product(
        self,
        *,
        platform_listing_id: str,
    ) -> bool:
        """Remove listing from Temu (set to offline)."""
        return await self.update_listing(
            platform_listing_id=platform_listing_id,
            status=PlatformListingStatus.DELISTED,
        )

    async def _upload_images(
        self,
        assets: list[ContentAsset],
    ) -> list[str]:
        """Upload images to Temu.

        Temu requires images to be uploaded to their CDN first.
        Returns list of Temu image IDs.
        """
        temu_image_ids = []

        for asset in assets[:self.MAX_IMAGES]:
            try:
                # Get image URL (MinIO or presigned URL)
                image_url = asset.file_url

                # Call Temu image upload API
                response = await self._call_api(
                    method="image.upload",
                    data={"url": image_url},
                )

                temu_image_id = response.get("image_id")
                if temu_image_id:
                    temu_image_ids.append(temu_image_id)

            except Exception as e:
                self.logger.warning(
                    "temu_image_upload_failed",
                    asset_id=str(asset.id),
                    error=str(e),
                )

        if not temu_image_ids:
            raise ValueError("Failed to upload any images to Temu")

        return temu_image_ids

    async def _call_api(
        self,
        *,
        method: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Call Temu API with authentication.

        Temu uses HMAC-SHA256 signature for authentication.
        """
        timestamp = str(int(time.time() * 1000))

        # Build request params
        params = {
            "app_key": self.app_key,
            "method": method,
            "timestamp": timestamp,
            "version": "1.0",
            **data,
        }

        # Generate signature
        sign = self._generate_signature(params)
        params["sign"] = sign

        # Make request
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            response = await client.post(
                f"{self.base_url}/{method}",
                json=params,
            )
            response.raise_for_status()
            result = response.json()

            # Check for API errors
            if result.get("code") != 0:
                error_msg = result.get("msg", "Unknown error")
                raise RuntimeError(f"Temu API error: {error_msg}")

            return result.get("data", {})

    def _generate_signature(self, params: dict[str, Any]) -> str:
        """Generate HMAC-SHA256 signature for Temu API."""
        # Sort params
        sorted_params = sorted(params.items())
        param_string = "".join(f"{k}{v}" for k, v in sorted_params)

        # Sign with app_secret
        sign_string = f"{self.app_secret}{param_string}{self.app_secret}"

        # HMAC-SHA256
        signature = hmac.new(
            self.app_secret.encode(),
            sign_string.encode(),
            hashlib.sha256,
        ).hexdigest()

        return signature.upper()

    def map_category(self, internal_category: str | None) -> int:
        """Map internal category to Temu category ID."""
        if not internal_category:
            return 0  # Default category

        category_lower = internal_category.lower()
        return self.CATEGORY_MAPPING.get(category_lower, 0)

    def _generate_description(self, product: CandidateProduct) -> str:
        """Generate product description for Temu.

        Temu descriptions should be:
        - Simple and clear
        - Highlight key features
        - Include size/material info
        """
        parts = [product.title]

        # Add from raw_payload if available
        if product.raw_payload:
            if moq := product.raw_payload.get("moq"):
                parts.append(f"Minimum order: {moq} pieces")
            if material := product.raw_payload.get("material"):
                parts.append(f"Material: {material}")
            if size := product.raw_payload.get("size"):
                parts.append(f"Size: {size}")

        description = ". ".join(parts)
        return description[:self.MAX_DESCRIPTION_LENGTH]

    def _map_status_to_temu(self, status: PlatformListingStatus) -> str:
        """Map internal status to Temu status."""
        mapping = {
            PlatformListingStatus.ACTIVE: "online",
            PlatformListingStatus.PAUSED: "offline",
            PlatformListingStatus.OUT_OF_STOCK: "offline",
            PlatformListingStatus.DELISTED: "deleted",
        }
        return mapping.get(status, "offline")

    async def validate_listing_data(
        self,
        *,
        product: CandidateProduct,
        assets: list[ContentAsset],
        region: str,
        price: Decimal,
    ) -> tuple[bool, str | None]:
        """Validate listing data for Temu requirements."""
        # Base validation
        is_valid, error = await super().validate_listing_data(
            product=product,
            assets=assets,
            region=region,
            price=price,
        )
        if not is_valid:
            return False, error

        # Temu-specific validation
        if region not in self.ENDPOINTS:
            return False, f"Unsupported region: {region}"

        currency = self.CURRENCIES.get(region, "USD")
        if currency == "USD":
            if price < self.MIN_PRICE_USD:
                return False, f"Price must be at least ${self.MIN_PRICE_USD}"
            if price > self.MAX_PRICE_USD:
                return False, f"Price cannot exceed ${self.MAX_PRICE_USD}"

        if len(assets) > self.MAX_IMAGES:
            return False, f"Maximum {self.MAX_IMAGES} images allowed"

        return True, None


class TemuAdapterMock(TemuAdapter):
    """Mock Temu adapter for testing without real API.

    Use this in development/testing environments.
    """

    def __init__(self, *, region: str = "us"):
        super().__init__(
            app_key="mock_key",
            app_secret="mock_secret",
            region=region,
        )
        self._listings: dict[str, dict] = {}

    async def _call_api(
        self,
        *,
        method: str,
        data: dict[str, Any],
    ) -> dict[str, Any]:
        """Mock API call."""
        import uuid

        self.logger.info("mock_api_call", method=method, data_keys=list(data.keys()))

        if method == "product.add":
            sku = f"TEMU-{uuid.uuid4().hex[:10].upper()}"
            product_id = str(uuid.uuid4().int)[:12]
            self._listings[sku] = {
                "sku": sku,
                "product_id": product_id,
                "status": "online",
                "inventory": data.get("inventory"),
                "price": data.get("price"),
                "title": data.get("title"),
                "description": data.get("description"),
                "sales_count": 0,
                "view_count": 0,
                "click_count": 0,
            }
            return {"sku": sku, "product_id": product_id}

        elif method == "image.upload":
            return {"image_id": f"img_{uuid.uuid4().hex[:8]}"}

        elif method == "product.get":
            sku = data.get("sku")
            if sku in self._listings:
                return self._listings[sku]
            return {}

        elif method == "product.update":
            sku = data.get("sku")
            listing = self._listings.get(sku)
            if not listing:
                return {}

            for source_key, target_key in {
                "price": "price",
                "inventory": "inventory",
                "title": "title",
                "description": "description",
                "status": "status",
            }.items():
                if source_key in data:
                    listing[target_key] = data[source_key]
            return {}

        return {}


# Factory function
def get_temu_adapter(*, region: str = "us", mock: bool = False) -> TemuAdapter:
    """Get Temu adapter instance.

    Args:
        region: Target region
        mock: Use mock adapter for testing

    Returns:
        TemuAdapter instance
    """
    if mock:
        return TemuAdapterMock(region=region)
    return TemuAdapter(region=region)
