"""Source adapter interface and mock implementation."""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from app.core.enums import SourcePlatform
from app.core.logging import get_logger

logger = get_logger(__name__)


class ProductData:
    """Product data from source platform."""

    def __init__(
        self,
        source_platform: SourcePlatform,
        source_product_id: str,
        source_url: str,
        title: str,
        category: Optional[str] = None,
        currency: str = "USD",
        platform_price: Optional[Decimal] = None,
        sales_count: Optional[int] = None,
        rating: Optional[Decimal] = None,
        main_image_url: Optional[str] = None,
        raw_payload: Optional[dict] = None,
        normalized_attributes: Optional[dict] = None,
        supplier_candidates: Optional[list[dict]] = None,
    ):
        self.source_platform = source_platform
        self.source_product_id = source_product_id
        self.source_url = source_url
        self.title = title
        self.category = category
        self.currency = currency
        self.platform_price = platform_price
        self.sales_count = sales_count
        self.rating = rating
        self.main_image_url = main_image_url
        self.raw_payload = raw_payload or {}
        self.normalized_attributes = normalized_attributes or {}
        self.supplier_candidates = supplier_candidates or []


class SourceAdapter(ABC):
    """Abstract interface for product source adapters."""

    @abstractmethod
    async def fetch_products(
        self,
        category: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        price_min: Optional[Decimal] = None,
        price_max: Optional[Decimal] = None,
        limit: int = 10,
        region: Optional[str] = None,
    ) -> list[ProductData]:
        """Fetch products from source platform."""
        pass


class MockSourceAdapter(SourceAdapter):
    """Mock source adapter for testing."""

    MOCK_PRODUCTS = [
        {
            "title": "MagSafe Adjustable Phone Stand",
            "category": "phone accessories",
            "price": Decimal("24.99"),
            "sales": 1250,
            "rating": Decimal("4.5"),
        },
        {
            "title": "Wireless Charging Pad 15W Fast Charge",
            "category": "phone accessories",
            "price": Decimal("19.99"),
            "sales": 890,
            "rating": Decimal("4.3"),
        },
        {
            "title": "USB-C Hub 7-in-1 Multiport Adapter",
            "category": "computer accessories",
            "price": Decimal("34.99"),
            "sales": 2100,
            "rating": Decimal("4.7"),
        },
        {
            "title": "Bluetooth Earbuds Noise Cancelling",
            "category": "audio",
            "price": Decimal("49.99"),
            "sales": 3500,
            "rating": Decimal("4.6"),
        },
        {
            "title": "Portable Power Bank 20000mAh",
            "category": "phone accessories",
            "price": Decimal("29.99"),
            "sales": 1800,
            "rating": Decimal("4.4"),
        },
        {
            "title": "LED Desk Lamp with USB Charging",
            "category": "home office",
            "price": Decimal("39.99"),
            "sales": 650,
            "rating": Decimal("4.2"),
        },
        {
            "title": "Mechanical Keyboard RGB Backlit",
            "category": "computer accessories",
            "price": Decimal("59.99"),
            "sales": 1100,
            "rating": Decimal("4.5"),
        },
        {
            "title": "Webcam 1080P HD with Microphone",
            "category": "computer accessories",
            "price": Decimal("44.99"),
            "sales": 920,
            "rating": Decimal("4.3"),
        },
    ]

    def __init__(self, platform: SourcePlatform = SourcePlatform.TEMU):
        self.platform = platform

    async def fetch_products(
        self,
        category: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        price_min: Optional[Decimal] = None,
        price_max: Optional[Decimal] = None,
        limit: int = 10,
        region: Optional[str] = None,
    ) -> list[ProductData]:
        """Fetch mock products."""
        products = []

        for mock_product in self.MOCK_PRODUCTS[:limit]:
            # Filter by category
            if category and category.lower() not in mock_product["category"].lower():
                continue

            # Filter by price range
            if price_min and mock_product["price"] < price_min:
                continue
            if price_max and mock_product["price"] > price_max:
                continue

            # Filter by keywords
            if keywords:
                title_lower = mock_product["title"].lower()
                if not any(kw.lower() in title_lower for kw in keywords):
                    continue

            product = ProductData(
                source_platform=self.platform,
                source_product_id=f"mock_{uuid4().hex[:8]}",
                source_url=f"https://{self.platform.value}.com/product/{uuid4().hex[:8]}",
                title=mock_product["title"],
                category=mock_product["category"],
                platform_price=mock_product["price"],
                sales_count=mock_product["sales"],
                rating=mock_product["rating"],
                main_image_url=f"https://example.com/images/{uuid4().hex[:8]}.jpg",
            )
            products.append(product)

        logger.info(
            "mock_products_fetched",
            platform=self.platform.value,
            count=len(products),
            category=category,
            keywords=keywords,
        )

        return products
