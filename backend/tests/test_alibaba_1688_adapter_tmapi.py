"""Tests for 1688 source adapter TMAPI business composition."""
from __future__ import annotations

from copy import deepcopy
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest

from app.core.enums import SourcePlatform
from app.services.alibaba_1688_adapter import Alibaba1688Adapter, Alibaba1688Candidate


class FakeSGLangClient:
    """Test double for conditional LLM query expansion."""

    def __init__(self, queries: list[str] | None = None):
        self.queries = queries or []
        self.generate_structured_json = AsyncMock(side_effect=self._generate_structured_json)

    async def _generate_structured_json(self, *, prompt, schema, temperature=0.7):
        _ = (prompt, schema, temperature)
        return {"queries": list(self.queries)}

    async def close(self):
        return None


def _build_price_band_catalog() -> dict[str, list[dict]]:
    return {
        "测试商品": [
            {
                "item_id": "p-good",
                "title": "价带友好商品",
                "price": "20.00",
                "sale_count": 4200,
                "img": "https://example.com/p-good.jpg",
                "product_url": "https://detail.1688.com/offer/p-good.html",
                "category_name": "测试类目",
                "company_name": "优质工厂",
                "shop_name": "优质店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/p-good",
                "member_id": "member-p-good",
            },
            {
                "item_id": "p-expensive",
                "title": "超价带商品",
                "price": "60.00",
                "sale_count": 4500,
                "img": "https://example.com/p-expensive.jpg",
                "product_url": "https://detail.1688.com/offer/p-expensive.html",
                "category_name": "测试类目",
                "company_name": "高价工厂",
                "shop_name": "高价店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/p-expensive",
                "member_id": "member-p-expensive",
            },
        ]
    }


def _build_moq_catalog() -> dict[str, list[dict]]:
    return {
        "测试商品": [
            {
                "item_id": "m-good",
                "title": "低MOQ商品",
                "price": "20.00",
                "sale_count": 3900,
                "img": "https://example.com/m-good.jpg",
                "product_url": "https://detail.1688.com/offer/m-good.html",
                "category_name": "测试类目",
                "company_name": "低MOQ工厂",
                "shop_name": "低MOQ店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/m-good",
                "member_id": "member-m-good",
            },
            {
                "item_id": "m-bad",
                "title": "高MOQ商品",
                "price": "20.00",
                "sale_count": 4000,
                "img": "https://example.com/m-bad.jpg",
                "product_url": "https://detail.1688.com/offer/m-bad.html",
                "category_name": "测试类目",
                "company_name": "高MOQ工厂",
                "shop_name": "高MOQ店铺",
                "moq": 500,
                "shop_url": "https://shop.example.com/m-bad",
                "member_id": "member-m-bad",
            },
        ]
    }


def _build_freight_catalog() -> dict[str, list[dict]]:
    return {
        "测试商品": [
            {
                "item_id": "f-good",
                "title": "低运费压力商品",
                "price": "20.00",
                "sale_count": 3800,
                "img": "https://example.com/f-good.jpg",
                "product_url": "https://detail.1688.com/offer/f-good.html",
                "category_name": "测试类目",
                "company_name": "低运费工厂",
                "shop_name": "低运费店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/f-good",
                "member_id": "member-f-good",
            },
            {
                "item_id": "f-bad",
                "title": "高运费压力商品",
                "price": "20.00",
                "sale_count": 4000,
                "img": "https://example.com/f-bad.jpg",
                "product_url": "https://detail.1688.com/offer/f-bad.html",
                "category_name": "测试类目",
                "company_name": "高运费工厂",
                "shop_name": "高运费店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/f-bad",
                "member_id": "member-f-bad",
            },
        ]
    }


def _build_detail_vs_business_catalog() -> dict[str, list[dict]]:
    return {
        "测试商品": [
            {
                "item_id": "d-badbiz",
                "title": "详情强但经营差商品",
                "price": "20.00",
                "sale_count": 5200,
                "img": "https://example.com/d-badbiz.jpg",
                "product_url": "https://detail.1688.com/offer/d-badbiz.html",
                "category_name": "测试类目",
                "company_name": "经营差工厂",
                "shop_name": "经营差店铺",
                "moq": 500,
                "shop_url": "https://shop.example.com/d-badbiz",
                "member_id": "member-d-badbiz",
            },
            {
                "item_id": "d-goodbiz",
                "title": "经营更优商品",
                "price": "20.00",
                "sale_count": 3600,
                "img": "https://example.com/d-goodbiz.jpg",
                "product_url": "https://detail.1688.com/offer/d-goodbiz.html",
                "category_name": "测试类目",
                "company_name": "经营优工厂",
                "shop_name": "经营优店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/d-goodbiz",
                "member_id": "member-d-goodbiz",
                "is_factory": True,
            },
        ]
    }


def _build_diversification_shop_cap_catalog() -> dict[str, list[dict]]:
    return {
        "测试商品": [
            {
                "item_id": "shop-a-1",
                "title": "同店高分商品一",
                "price": "20.00",
                "sale_count": 6000,
                "img": "https://example.com/shop-a-1.jpg",
                "product_url": "https://detail.1688.com/offer/shop-a-1.html",
                "category_name": "测试类目",
                "company_name": "店A工厂",
                "shop_name": "店A",
                "moq": 10,
                "shop_url": "https://shop.example.com/a",
                "member_id": "member-shop-a",
            },
            {
                "item_id": "shop-a-2",
                "title": "同店高分商品二",
                "price": "20.00",
                "sale_count": 5900,
                "img": "https://example.com/shop-a-2.jpg",
                "product_url": "https://detail.1688.com/offer/shop-a-2.html",
                "category_name": "测试类目",
                "company_name": "店A工厂",
                "shop_name": "店A",
                "moq": 10,
                "shop_url": "https://shop.example.com/a",
                "member_id": "member-shop-a",
            },
            {
                "item_id": "shop-a-3",
                "title": "同店高分商品三",
                "price": "20.00",
                "sale_count": 5800,
                "img": "https://example.com/shop-a-3.jpg",
                "product_url": "https://detail.1688.com/offer/shop-a-3.html",
                "category_name": "测试类目",
                "company_name": "店A工厂",
                "shop_name": "店A",
                "moq": 10,
                "shop_url": "https://shop.example.com/a",
                "member_id": "member-shop-a",
            },
            {
                "item_id": "shop-b-1",
                "title": "其他店商品一",
                "price": "20.00",
                "sale_count": 3000,
                "img": "https://example.com/shop-b-1.jpg",
                "product_url": "https://detail.1688.com/offer/shop-b-1.html",
                "category_name": "测试类目",
                "company_name": "店B工厂",
                "shop_name": "店B",
                "moq": 10,
                "shop_url": "https://shop.example.com/b",
                "member_id": "member-shop-b",
            },
            {
                "item_id": "shop-c-1",
                "title": "其他店商品二",
                "price": "20.00",
                "sale_count": 2900,
                "img": "https://example.com/shop-c-1.jpg",
                "product_url": "https://detail.1688.com/offer/shop-c-1.html",
                "category_name": "测试类目",
                "company_name": "店C工厂",
                "shop_name": "店C",
                "moq": 10,
                "shop_url": "https://shop.example.com/c",
                "member_id": "member-shop-c",
            },
        ]
    }



def _build_diversification_same_image_catalog() -> dict[str, list[dict]]:
    return {
        "测试商品": [
            {
                "item_id": "img-1",
                "title": "同图高分商品",
                "price": "20.00",
                "sale_count": 5000,
                "img": "https://cdn.example.com/Product.JPG?size=800#hero",
                "product_url": "https://detail.1688.com/offer/img-1.html",
                "category_name": "测试类目",
                "company_name": "图片店A",
                "shop_name": "图片店A",
                "moq": 10,
                "shop_url": "https://shop.example.com/img-a",
                "member_id": "member-img-a",
            },
            {
                "item_id": "img-2",
                "title": "同图低分变体",
                "price": "20.00",
                "sale_count": 4900,
                "img": "https://cdn.example.com/product.jpg?size=400",
                "product_url": "https://detail.1688.com/offer/img-2.html",
                "category_name": "测试类目",
                "company_name": "图片店B",
                "shop_name": "图片店B",
                "moq": 10,
                "shop_url": "https://shop.example.com/img-b",
                "member_id": "member-img-b",
            },
            {
                "item_id": "img-3",
                "title": "不同图商品",
                "price": "20.00",
                "sale_count": 3000,
                "img": "https://cdn.example.com/product-unique.jpg",
                "product_url": "https://detail.1688.com/offer/img-3.html",
                "category_name": "测试类目",
                "company_name": "图片店C",
                "shop_name": "图片店C",
                "moq": 10,
                "shop_url": "https://shop.example.com/img-c",
                "member_id": "member-img-c",
            },
        ]
    }



def _build_diversification_same_title_catalog() -> dict[str, list[dict]]:
    return {
        "测试商品": [
            {
                "item_id": "title-1",
                "title": "Premium Bottle - Blue",
                "price": "20.00",
                "sale_count": 5100,
                "img": "https://example.com/title-1.jpg",
                "product_url": "https://detail.1688.com/offer/title-1.html",
                "category_name": "测试类目",
                "company_name": "标题店A",
                "shop_name": "标题店A",
                "moq": 10,
                "shop_url": "https://shop.example.com/title-a",
                "member_id": "member-title-a",
            },
            {
                "item_id": "title-2",
                "title": " premium bottle blue ",
                "price": "20.00",
                "sale_count": 5000,
                "img": "https://example.com/title-2.jpg",
                "product_url": "https://detail.1688.com/offer/title-2.html",
                "category_name": "测试类目",
                "company_name": "标题店B",
                "shop_name": "标题店B",
                "moq": 10,
                "shop_url": "https://shop.example.com/title-b",
                "member_id": "member-title-b",
            },
            {
                "item_id": "title-3",
                "title": "Unique Bottle Green",
                "price": "20.00",
                "sale_count": 3200,
                "img": "https://example.com/title-3.jpg",
                "product_url": "https://detail.1688.com/offer/title-3.html",
                "category_name": "测试类目",
                "company_name": "标题店C",
                "shop_name": "标题店C",
                "moq": 10,
                "shop_url": "https://shop.example.com/title-c",
                "member_id": "member-title-c",
            },
        ]
    }



def _build_diversification_fallback_catalog() -> dict[str, list[dict]]:
    return {
        "测试商品": [
            {
                "item_id": "fallback-1",
                "title": "Fallback Product",
                "price": "20.00",
                "sale_count": 5500,
                "img": "https://cdn.example.com/fallback.jpg?variant=1",
                "product_url": "https://detail.1688.com/offer/fallback-1.html",
                "category_name": "测试类目",
                "company_name": "回退店A",
                "shop_name": "回退店A",
                "moq": 10,
                "shop_url": "https://shop.example.com/fallback-a",
                "member_id": "member-fallback-a",
            },
            {
                "item_id": "fallback-2",
                "title": "Fallback Product",
                "price": "20.00",
                "sale_count": 5400,
                "img": "https://cdn.example.com/fallback.jpg?variant=2",
                "product_url": "https://detail.1688.com/offer/fallback-2.html",
                "category_name": "测试类目",
                "company_name": "回退店B",
                "shop_name": "回退店B",
                "moq": 10,
                "shop_url": "https://shop.example.com/fallback-b",
                "member_id": "member-fallback-b",
            },
            {
                "item_id": "fallback-3",
                "title": "Fallback Product",
                "price": "20.00",
                "sale_count": 5300,
                "img": "https://cdn.example.com/fallback.jpg?variant=3",
                "product_url": "https://detail.1688.com/offer/fallback-3.html",
                "category_name": "测试类目",
                "company_name": "回退店C",
                "shop_name": "回退店C",
                "moq": 10,
                "shop_url": "https://shop.example.com/fallback-c",
                "member_id": "member-fallback-c",
            },
        ]
    }



class FakeFeedbackAggregator:
    """Test double for Phase 6 historical feedback priors."""

    def __init__(self):
        self.high_performing_seeds: list[str] = ["历史爆款"]
        self.seed_priors: dict[tuple[str, str], float] = {("测试商品", "explicit"): 4.0}
        self.shop_priors: dict[str, float] = {"历史优质店铺": 3.0}
        self.supplier_priors: dict[tuple[str, str], float] = {
            ("历史优质工厂", "https://shop.example.com/h-feedback-good"): 2.5
        }

    def get_high_performing_seeds(self, category: str | None, limit: int) -> list[str]:
        _ = category
        return self.high_performing_seeds[:limit]

    def get_seed_performance_prior(self, seed: str, seed_type: str) -> float:
        return self.seed_priors.get((seed, seed_type), 0.0)

    def get_shop_performance_prior(self, shop_name: str) -> float:
        return self.shop_priors.get(shop_name, 0.0)

    def get_supplier_performance_prior(self, supplier_name: str, supplier_url: str) -> float:
        return self.supplier_priors.get((supplier_name, supplier_url), 0.0)


class FakeTMAPIClient:
    """Test double for TMAPI1688Client."""

    def __init__(
        self,
        *,
        catalog: dict[str, list[dict]] | None = None,
        detail_overrides: dict[str, dict] | None = None,
        shipping_overrides: dict[str, dict] | None = None,
        image_products: list[dict] | None = None,
    ):
        self.catalog = deepcopy(catalog) if catalog is not None else {
            "手机壳": [
                {
                    "item_id": "1001",
                    "title": "基础手机壳",
                    "price": "5.50",
                    "sale_count": 1800,
                    "img": "https://example.com/1001.jpg",
                    "product_url": "https://detail.1688.com/offer/1001.html",
                    "category_name": "手机配件",
                    "company_name": "深圳基础工厂",
                    "shop_name": "基础店铺",
                    "moq": 20,
                    "shop_url": "https://shop.example.com/1001",
                    "member_id": "b2b-1001",
                }
            ],
            "苹果手机壳": [
                {
                    "item_id": "1001",
                    "title": "基础手机壳",
                    "price": "5.50",
                    "sale_count": 1800,
                    "img": "https://example.com/1001.jpg",
                    "product_url": "https://detail.1688.com/offer/1001.html",
                    "category_name": "手机配件",
                    "company_name": "深圳基础工厂",
                    "shop_name": "基础店铺",
                    "moq": 20,
                    "shop_url": "https://shop.example.com/1001",
                    "member_id": "b2b-1001",
                },
                {
                    "item_id": "1002",
                    "title": "苹果磁吸手机壳",
                    "price": "9.80",
                    "sale_count": 2600,
                    "img": "https://example.com/1002.jpg",
                    "product_url": "https://detail.1688.com/offer/1002.html",
                    "category_name": "手机配件",
                    "company_name": "东莞磁吸科技",
                    "shop_name": "磁吸旗舰店",
                    "moq": 10,
                    "shop_url": "https://shop.example.com/1002",
                    "member_id": "b2b-1002",
                    "is_factory": True,
                },
            ],
            "热销": [
                {
                    "item_id": "2001",
                    "title": "桌面收纳盒",
                    "price": "7.00",
                    "sale_count": 600,
                    "img": "https://example.com/2001.jpg",
                    "product_url": "https://detail.1688.com/offer/2001.html",
                    "category_name": "家居收纳",
                    "company_name": "义乌收纳厂",
                    "shop_name": "收纳之家",
                    "moq": 24,
                }
            ],
            "新品": [
                {
                    "item_id": "2002",
                    "title": "便携小风扇",
                    "price": "12.00",
                    "sale_count": 480,
                    "img": "https://example.com/2002.jpg",
                    "product_url": "https://detail.1688.com/offer/2002.html",
                    "category_name": "小家电",
                    "company_name": "宁波风扇厂",
                    "shop_name": "风扇优品",
                    "moq": 12,
                }
            ],
        }
        self.detail_overrides = deepcopy(detail_overrides) if detail_overrides is not None else {}
        self.shipping_overrides = deepcopy(shipping_overrides) if shipping_overrides is not None else {}
        self.image_products = deepcopy(image_products) if image_products is not None else [
            {
                "item_id": "3001",
                "title": "图片搜索相似商品",
                "price": "8.50",
                "sale_count": 350,
                "img": "https://example.com/3001.jpg",
                "product_url": "https://detail.1688.com/offer/3001.html",
                "category_name": "手机配件",
                "company_name": "图片搜索工厂",
                "shop_name": "图片搜索店",
                "moq": 30,
            }
        ]
        self.search_items = AsyncMock(side_effect=self._search_items)
        self.search_items_by_image = AsyncMock(side_effect=self._search_items_by_image)
        self.get_item_detail = AsyncMock(side_effect=self._get_item_detail)
        self.get_item_shipping = AsyncMock(side_effect=self._get_item_shipping)
        self.get_item_ratings = AsyncMock(side_effect=self._get_item_ratings)
        self.get_shop_info = AsyncMock(side_effect=self._get_shop_info)
        self.get_shop_items = AsyncMock(side_effect=self._get_shop_items)
        self.get_item_desc = AsyncMock(side_effect=self._get_item_desc)

    def _lookup_item(self, item_id: str) -> dict | None:
        for products in self.catalog.values():
            for product in products:
                if str(product.get("item_id")) == item_id:
                    return deepcopy(product)
        for product in self.image_products:
            if str(product.get("item_id")) == item_id:
                return deepcopy(product)
        return None

    async def _search_items(
        self,
        *,
        keyword,
        page=1,
        page_size=20,
        language="en",
        sort="default",
        price_start=None,
        price_end=None,
        cat_id=None,
        new_arrival=None,
        support_dropshipping=None,
        free_shipping=None,
        is_super_factory=None,
    ):
        return {
            "products": deepcopy(self.catalog.get(keyword, [])),
            "total": len(self.catalog.get(keyword, [])),
            "page": page,
            "page_size": page_size,
            "has_more": False,
        }

    async def _search_items_by_image(
        self,
        *,
        img_url,
        page=1,
        page_size=20,
        language="en",
        sort="default",
        support_dropshipping=None,
        is_factory=None,
        verified_supplier=None,
        free_shipping=None,
        new_arrival=None,
    ):
        return {
            "products": deepcopy(self.image_products),
            "total": len(self.image_products),
            "page": page,
            "page_size": page_size,
            "has_more": False,
        }

    async def _get_item_detail(self, *, item_id, language="en"):
        if item_id in self.detail_overrides:
            return deepcopy(self.detail_overrides[item_id])
        base_item = self._lookup_item(str(item_id)) or {}
        item_id_str = str(item_id)
        price = base_item.get("price", "11.20" if item_id_str == "1002" else "6.30")
        sale_count = base_item.get("sale_count", 5000 if item_id_str == "1002" else 900)
        return {
            "item_id": item_id,
            "title": f"详情补全商品 {item_id_str}",
            "price": price,
            "main_imgs": [
                f"https://example.com/{item_id_str}-1.jpg",
                f"https://example.com/{item_id_str}-2.jpg",
            ],
            "company_name": base_item.get("company_name", "详情公司"),
            "shop_name": base_item.get("shop_name", "详情店铺"),
            "member_id": base_item.get("member_id", f"b2b-{item_id_str}"),
            "shop_url": base_item.get("shop_url", f"https://shop.example.com/{item_id_str}"),
            "moq": base_item.get("moq", 15),
            "category_name": base_item.get("category_name", "详情类目"),
            "sale_count": sale_count,
            "product_url": base_item.get("product_url", f"https://detail.1688.com/offer/{item_id_str}.html"),
            "is_factory": base_item.get("is_factory", item_id_str == "1002"),
            "is_super_factory": base_item.get("is_super_factory", item_id_str == "1002"),
            "verified_supplier": base_item.get("verified_supplier", False),
            "support_dropshipping": base_item.get("support_dropshipping", False),
        }

    async def _get_item_shipping(self, *, item_id, province, total_quantity=1, total_weight=None):
        if item_id in self.shipping_overrides:
            return deepcopy(self.shipping_overrides[item_id])
        return {
            "total_fee": 4.20,
            "shipping_to": province,
            "item_id": item_id,
        }

    async def _get_item_ratings(self, *, item_id, page=1, sort_type="default"):
        return {
            "item_id": item_id,
            "page": page,
            "list": [
                {"rate_star": 5, "feedback": "质量很好，发货快"},
                {"rate_star": 4, "feedback": "还可以，性价比高"},
            ],
        }

    async def _get_shop_info(self, *, shop_url=None, member_id=None):
        return {
            "member_id": member_id or "b2b-default",
            "seller_id": 123456,
            "company_name": "测试店铺公司",
            "shop_url": shop_url or "https://shop.example.com/default",
            "shop_name": "测试店铺",
            "is_factory": True,
            "is_super_factory": False,
        }

    async def _get_shop_items(self, *, shop_url, page=1, page_size=20, sort="default", cat=None, cat_type=None):
        return {
            "products": [
                {
                    "item_id": "4001",
                    "title": "店铺其他商品",
                    "price": "15.00",
                    "img": "https://example.com/4001.jpg",
                }
            ],
            "total": 1,
            "page": page,
            "page_size": page_size,
        }

    async def _get_item_desc(self, *, item_id):
        return {
            "item_id": item_id,
            "detail_imgs": [
                f"https://example.com/{item_id}/desc1.jpg",
                f"https://example.com/{item_id}/desc2.jpg",
            ],
        }


@pytest.mark.asyncio
async def test_explicit_keyword_mode_uses_keyword_search():
    """Explicit keywords should drive primary keyword search."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(keywords=["手机壳"], limit=3)

    assert client.search_items.called
    assert len(products) >= 1
    assert products[0].source_platform == SourcePlatform.ALIBABA_1688
    assert products[0].normalized_attributes["seed_type"] == "explicit"
    assert products[0].supplier_candidates


@pytest.mark.asyncio
async def test_returns_empty_without_keywords():
    """Adapter should return empty results when no validated keywords are provided."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(limit=4)

    assert products == []
    assert not client.search_items.called


@pytest.mark.asyncio
async def test_demand_first_mode_returns_empty_without_keywords():
    """Demand-first mode should return empty results when no keywords provided."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(limit=4)

    assert len(products) == 0
    assert not client.search_items.called


@pytest.mark.asyncio
async def test_returns_empty_without_category_fallback_or_historical_seed_injection():
    """Adapter should not inject category or historical seeds when keywords are missing."""
    client = FakeTMAPIClient(catalog={"历史爆款": [{
        "item_id": "history-001",
        "title": "历史爆款商品",
        "price": "18.00",
        "sale_count": 3200,
        "img": "https://example.com/history-001.jpg",
        "product_url": "https://detail.1688.com/offer/history-001.html",
        "category_name": "测试类目",
        "company_name": "历史工厂",
        "shop_name": "历史店铺",
        "moq": 10,
        "shop_url": "https://shop.example.com/history-001",
        "member_id": "member-history-001",
    }]})
    adapter = Alibaba1688Adapter(tmapi_client=client, feedback_aggregator=FakeFeedbackAggregator())
    adapter.settings.tmapi_1688_enable_historical_feedback = True
    adapter.settings.tmapi_1688_suggest_limit_per_seed = 3

    products = await adapter.fetch_products(category="测试类目", limit=3)

    assert products == []
    assert not client.search_items.called


@pytest.mark.asyncio
async def test_top_k_detail_enrichment_improves_output_shape():
    """Adapter should call get_item_detail on shortlist candidates and emit richer normalized fields."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(keywords=["手机壳"], limit=2)

    assert client.get_item_detail.called
    assert len(products) >= 1
    for product in products:
        assert product.normalized_attributes["detail_enriched"] is True
        assert product.normalized_attributes["image_urls"]
        assert product.supplier_candidates
        assert "discovery_score" in product.normalized_attributes
        assert "business_score" in product.normalized_attributes
        assert "final_score" in product.normalized_attributes
        assert product.normalized_attributes["final_score"] == pytest.approx(
            product.normalized_attributes["discovery_score"] + product.normalized_attributes["business_score"]
        )


@pytest.mark.asyncio
async def test_item_shipping_only_runs_when_province_mapping_exists():
    """Shipping enrichment should only run when region to province mapping is configured."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_region_province_map = {"cn": "广东"}

    products = await adapter.fetch_products(keywords=["手机壳"], limit=2, region="cn")

    assert client.get_item_shipping.called
    assert any(product.normalized_attributes["freight_cny"] is not None for product in products)


@pytest.mark.asyncio
async def test_dedupe_and_ranking_favor_enriched_high_signal_candidates():
    """Adapter should dedupe repeated offers and rank strong candidates first."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(keywords=["手机壳"], limit=3)

    ids = [product.source_product_id for product in products]
    assert len(ids) == len(set(ids))
    for product in products:
        attrs = product.normalized_attributes
        assert "discovery_score" in attrs
        assert "business_score" in attrs
        assert "final_score" in attrs
        assert attrs["final_score"] == pytest.approx(attrs["discovery_score"] + attrs["business_score"])
    assert products[0].normalized_attributes["final_score"] >= products[-1].normalized_attributes["final_score"]


@pytest.mark.asyncio
async def test_partial_lane_failure_still_returns_candidates():
    """A single recall lane failure should not fail the whole discovery flow."""
    client = FakeTMAPIClient()
    client.search_items_by_image = AsyncMock(side_effect=RuntimeError("image search down"))
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(keywords=["手机壳"], limit=3)

    assert len(products) >= 1
    assert client.search_items.called


@pytest.mark.asyncio
async def test_price_filter_conversion_to_cny():
    """USD price filters should be converted to CNY before hitting search lanes."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    await adapter.fetch_products(
        keywords=["手机壳"],
        price_min=Decimal("1.0"),
        price_max=Decimal("10.0"),
        limit=2,
    )

    kwargs = client.search_items.call_args.kwargs
    assert kwargs["price_start"] is not None
    assert kwargs["price_end"] is not None
    assert kwargs["price_start"] > 5
    assert kwargs["price_end"] > 50


@pytest.mark.asyncio
async def test_factory_filter_applied_in_recall():
    """Adapter should apply factory filter to boost factory results."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(keywords=["苹果手机壳"], limit=3)

    assert client.search_items.called
    factory_call_found = False
    for call in client.search_items.call_args_list:
        if call.kwargs.get("is_super_factory") is True:
            factory_call_found = True
            break
    assert factory_call_found
    assert any(product.normalized_attributes.get("is_factory_result") for product in products)


@pytest.mark.asyncio
async def test_shop_info_and_ratings_enrichment():
    """Adapter should enrich with shop info and ratings when available."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_enable_ratings = True
    adapter.settings.tmapi_1688_enable_shop_info = True

    products = await adapter.fetch_products(keywords=["手机壳"], limit=2)

    assert client.get_item_ratings.called
    assert client.get_shop_info.called




@pytest.mark.asyncio
async def test_image_search_lane_used_for_top_candidates():
    """Adapter should use image search lane for top candidates with images."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(keywords=["手机壳"], limit=5)

    assert client.search_items_by_image.called
    image_products = [p for p in products if "image" in p.normalized_attributes.get("seed_type", "")]
    assert len(image_products) >= 0


@pytest.mark.asyncio
async def test_price_band_business_score_downranks_expensive_candidates():
    """High-discovery candidates outside the target price band should fall in final ranking."""
    client = FakeTMAPIClient(catalog=_build_price_band_catalog())
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(
        keywords=["测试商品"],
        price_min=Decimal("2.0"),
        price_max=Decimal("4.0"),
        limit=2,
    )

    assert [product.source_product_id for product in products] == ["p-good", "p-expensive"]
    top_attrs = products[0].normalized_attributes
    low_attrs = products[1].normalized_attributes
    assert low_attrs["discovery_score"] >= top_attrs["discovery_score"]
    assert top_attrs["business_score"] > low_attrs["business_score"]
    assert top_attrs["final_score"] > low_attrs["final_score"]


@pytest.mark.asyncio
async def test_high_moq_candidates_drop_in_final_rank():
    """Candidates with high MOQ should be demoted by business score."""
    client = FakeTMAPIClient(catalog=_build_moq_catalog())
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(keywords=["测试商品"], limit=2)

    assert [product.source_product_id for product in products] == ["m-good", "m-bad"]
    top_attrs = products[0].normalized_attributes
    low_attrs = products[1].normalized_attributes
    assert top_attrs["business_score"] > low_attrs["business_score"]
    assert top_attrs["final_score"] > low_attrs["final_score"]


@pytest.mark.asyncio
async def test_freight_pressure_affects_final_ranking():
    """High freight-to-price ratio should materially reduce final score."""
    client = FakeTMAPIClient(
        catalog=_build_freight_catalog(),
        shipping_overrides={
            "f-good": {"total_fee": 3.00, "item_id": "f-good", "shipping_to": "广东"},
            "f-bad": {"total_fee": 28.00, "item_id": "f-bad", "shipping_to": "广东"},
        },
    )
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_region_province_map = {"cn": "广东"}

    products = await adapter.fetch_products(keywords=["测试商品"], limit=2, region="cn")

    assert [product.source_product_id for product in products] == ["f-good", "f-bad"]
    top_attrs = products[0].normalized_attributes
    low_attrs = products[1].normalized_attributes
    assert top_attrs["freight_cny"] < low_attrs["freight_cny"]
    assert top_attrs["business_score"] > low_attrs["business_score"]
    assert top_attrs["final_score"] > low_attrs["final_score"]


@pytest.mark.asyncio
async def test_detail_rich_but_business_weak_candidate_does_not_stay_first():
    """Detail enrichment alone should not keep a commercially weak product at rank one."""
    client = FakeTMAPIClient(
        catalog=_build_detail_vs_business_catalog(),
        shipping_overrides={
            "d-badbiz": {"total_fee": 32.00, "item_id": "d-badbiz", "shipping_to": "广东"},
            "d-goodbiz": {"total_fee": 2.50, "item_id": "d-goodbiz", "shipping_to": "广东"},
        },
    )
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_region_province_map = {"cn": "广东"}

    products = await adapter.fetch_products(keywords=["测试商品"], limit=2, region="cn")

    assert products[0].source_product_id == "d-goodbiz"
    assert products[1].source_product_id == "d-badbiz"
    assert products[1].normalized_attributes["discovery_score"] >= products[0].normalized_attributes["discovery_score"]
    assert products[0].normalized_attributes["business_score"] > products[1].normalized_attributes["business_score"]
    assert products[0].normalized_attributes["final_score"] > products[1].normalized_attributes["final_score"]


@pytest.mark.asyncio
async def test_diversification_shop_cap_limits_same_shop_in_final_top_n():
    """Final shortlist should not be dominated by a single shop beyond the configured cap."""
    client = FakeTMAPIClient(catalog=_build_diversification_shop_cap_catalog())
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_diversification_shop_cap = 2
    adapter.settings.tmapi_1688_diversification_enable_image_dedupe = False
    adapter.settings.tmapi_1688_diversification_enable_title_dedupe = False
    adapter.settings.tmapi_1688_diversification_seed_min_quota = 0

    products = await adapter.fetch_products(keywords=["测试商品"], limit=4)

    shop_counts: dict[str, int] = {}
    for product in products:
        shop_key = product.normalized_attributes["member_id"]
        shop_counts[shop_key] = shop_counts.get(shop_key, 0) + 1
    assert max(shop_counts.values()) <= 2
    assert len(products) == 4


@pytest.mark.asyncio
async def test_diversification_same_image_keeps_highest_score_variant_only():
    """Same-image variants should collapse to the highest final-score representative."""
    client = FakeTMAPIClient(catalog=_build_diversification_same_image_catalog())
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_diversification_enable_title_dedupe = False
    adapter.settings.tmapi_1688_diversification_seed_min_quota = 0

    products = await adapter.fetch_products(keywords=["测试商品"], limit=2)

    ids = [product.source_product_id for product in products]
    assert "img-1" in ids
    assert "img-2" not in ids
    assert len(products) == 2


@pytest.mark.asyncio
async def test_diversification_same_title_variant_is_deduped_conservatively():
    """Minor title variants should not both remain in the final shortlist."""
    client = FakeTMAPIClient(catalog=_build_diversification_same_title_catalog())
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_diversification_enable_image_dedupe = False
    adapter.settings.tmapi_1688_diversification_seed_min_quota = 0

    products = await adapter.fetch_products(keywords=["测试商品"], limit=2)

    ids = [product.source_product_id for product in products]
    assert "title-1" in ids
    assert "title-2" not in ids
    assert len(products) == 2


@pytest.mark.asyncio
async def test_diversification_preserves_non_primary_lane_representation_when_limit_allows():
    """Lane soft quotas should keep some non-primary lane representation in the final list."""
    client = FakeTMAPIClient(catalog=_build_diversification_shop_cap_catalog())
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_diversification_enable_image_dedupe = False
    adapter.settings.tmapi_1688_diversification_enable_title_dedupe = False
    adapter.settings.tmapi_1688_diversification_shop_cap = 10
    adapter.settings.tmapi_1688_diversification_seed_min_quota = 1
    adapter.settings.tmapi_1688_diversification_seed_quota_max_lanes = 3

    ranked = [
        Alibaba1688Candidate(
            item_id="explicit-1",
            title="显式高分一",
            member_id="member-explicit-1",
            shop_url="https://shop.example.com/explicit-1",
            shop_name="显式店1",
            main_image_url="https://example.com/explicit-1.jpg",
            image_urls=["https://example.com/explicit-1.jpg"],
            seed_type="explicit",
            source_endpoints=["search_items"],
            final_score=100.0,
        ),
        Alibaba1688Candidate(
            item_id="explicit-2",
            title="显式高分二",
            member_id="member-explicit-2",
            shop_url="https://shop.example.com/explicit-2",
            shop_name="显式店2",
            main_image_url="https://example.com/explicit-2.jpg",
            image_urls=["https://example.com/explicit-2.jpg"],
            seed_type="explicit",
            source_endpoints=["search_items"],
            final_score=99.0,
        ),
        Alibaba1688Candidate(
            item_id="category-1",
            title="类目代表",
            member_id="member-category-1",
            shop_url="https://shop.example.com/category-1",
            shop_name="类目店1",
            main_image_url="https://example.com/category-1.jpg",
            image_urls=["https://example.com/category-1.jpg"],
            seed_type="category",
            source_endpoints=["search_items"],
            final_score=60.0,
        ),
        Alibaba1688Candidate(
            item_id="image-1",
            title="图片代表",
            member_id="member-image-1",
            shop_url="https://shop.example.com/image-1",
            shop_name="图片店1",
            main_image_url="https://example.com/image-1.jpg",
            image_urls=["https://example.com/image-1.jpg"],
            seed_type="image",
            source_endpoints=["search_items_by_image"],
            final_score=55.0,
        ),
    ]

    selected = adapter._select_diversified_candidates(ranked=ranked, limit=3)

    lanes = {adapter._resolve_seed_lane(candidate) for candidate in selected}
    assert "explicit" in lanes
    assert any(lane in lanes for lane in {"category", "image"})
    assert len(selected) == 3


@pytest.mark.asyncio
async def test_diversification_relaxation_fills_limit_when_pool_is_homogeneous():
    """Selector should relax constraints and still fill the requested limit."""
    client = FakeTMAPIClient(catalog=_build_diversification_fallback_catalog())
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_diversification_shop_cap = 2
    adapter.settings.tmapi_1688_diversification_enable_image_dedupe = True
    adapter.settings.tmapi_1688_diversification_enable_title_dedupe = True
    adapter.settings.tmapi_1688_diversification_seed_min_quota = 0
    adapter.settings.tmapi_1688_diversification_relaxation_passes = 2

    products = await adapter.fetch_products(keywords=["测试商品"], limit=3)

    assert len(products) == 3
    assert [product.source_product_id for product in products] == ["fallback-1", "fallback-2", "fallback-3"]


@pytest.mark.asyncio
async def test_diversification_does_not_change_phase1_score_formula():
    """Diversification should only affect final selection, not score computation semantics."""
    client = FakeTMAPIClient(catalog=_build_diversification_shop_cap_catalog())
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(keywords=["测试商品"], limit=4)

    for product in products:
        attrs = product.normalized_attributes
        assert attrs["final_score"] == pytest.approx(attrs["discovery_score"] + attrs["business_score"])


def _build_supplier_competition_catalog() -> dict[str, list[dict]]:
    """Build a catalog with similar items for supplier competition set testing."""
    return {
        "测试商品": [
            {
                "item_id": "comp-primary",
                "title": "Premium Water Bottle Blue",
                "price": "20.00",
                "sale_count": 5000,
                "img": "https://cdn.example.com/bottle-blue.jpg?size=800",
                "product_url": "https://detail.1688.com/offer/comp-primary.html",
                "category_name": "测试类目",
                "company_name": "主供应商工厂",
                "shop_name": "主供应商店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/primary",
                "member_id": "member-primary",
                "is_factory": True,
            },
            {
                "item_id": "comp-similar-1",
                "title": "Premium Water Bottle Blue",
                "price": "19.50",
                "sale_count": 4800,
                "img": "https://cdn.example.com/bottle-blue.jpg?size=400",
                "product_url": "https://detail.1688.com/offer/comp-similar-1.html",
                "category_name": "测试类目",
                "company_name": "竞争供应商A",
                "shop_name": "竞争店铺A",
                "moq": 15,
                "shop_url": "https://shop.example.com/similar-1",
                "member_id": "member-similar-1",
            },
            {
                "item_id": "comp-similar-2",
                "title": "premium water bottle blue",
                "price": "21.00",
                "sale_count": 4600,
                "img": "https://cdn.example.com/bottle-blue-alt.jpg",
                "product_url": "https://detail.1688.com/offer/comp-similar-2.html",
                "category_name": "测试类目",
                "company_name": "竞争供应商B",
                "shop_name": "竞争店铺B",
                "moq": 12,
                "shop_url": "https://shop.example.com/similar-2",
                "member_id": "member-similar-2",
                "is_factory": True,
            },
            {
                "item_id": "comp-different",
                "title": "Unique Product",
                "price": "30.00",
                "sale_count": 3000,
                "img": "https://cdn.example.com/unique.jpg",
                "product_url": "https://detail.1688.com/offer/comp-different.html",
                "category_name": "测试类目",
                "company_name": "不同供应商",
                "shop_name": "不同店铺",
                "moq": 20,
                "shop_url": "https://shop.example.com/different",
                "member_id": "member-different",
            },
        ]
    }


@pytest.mark.asyncio
async def test_supplier_competition_set_includes_multiple_suppliers():
    """Final candidates should include 3-5 supplier candidates when similar items exist in recall pool."""
    client = FakeTMAPIClient(
        catalog=_build_supplier_competition_catalog(),
        image_products=[
            {
                "item_id": "comp-image-similar",
                "title": "Premium Water Bottle Blue",
                "price": "20.50",
                "sale_count": 4500,
                "img": "https://cdn.example.com/bottle-blue.jpg?size=600",
                "product_url": "https://detail.1688.com/offer/comp-image-similar.html",
                "category_name": "测试类目",
                "company_name": "图片搜索供应商",
                "shop_name": "图片搜索店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/image-similar",
                "member_id": "member-image-similar",
            }
        ],
    )
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_supplier_competition_set_size = 5
    adapter.settings.tmapi_1688_supplier_similarity_threshold = 0.5

    products = await adapter.fetch_products(keywords=["测试商品"], limit=1)

    assert len(products) >= 1
    product = products[0]
    assert len(product.supplier_candidates) >= 3
    supplier_skus = [supplier["supplier_sku"] for supplier in product.supplier_candidates]
    assert len(supplier_skus) == len(set(supplier_skus))
    primary_supplier = product.supplier_candidates[0]
    assert primary_supplier["supplier_sku"] == product.source_product_id
    assert primary_supplier["confidence_score"] >= Decimal("0.76")
    for supplier in product.supplier_candidates[1:]:
        assert supplier["confidence_score"] <= Decimal("0.85")


@pytest.mark.asyncio
async def test_supplier_competition_set_sorted_by_confidence():
    """Supplier candidates should be sorted by confidence score in descending order."""
    client = FakeTMAPIClient(catalog=_build_supplier_competition_catalog())
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_supplier_competition_set_size = 5

    products = await adapter.fetch_products(keywords=["测试商品"], limit=1)

    assert len(products) >= 1
    product = products[0]
    assert len(product.supplier_candidates) >= 2
    confidences = [supplier["confidence_score"] for supplier in product.supplier_candidates]
    assert confidences == sorted(confidences, reverse=True)


@pytest.mark.asyncio
async def test_titles_are_similar_detects_variants():
    """Title similarity detection should identify conservative variants."""
    client = FakeTMAPIClient()
    adapter = Alibaba1688Adapter(tmapi_client=client)

    assert adapter._titles_are_similar("Premium Bottle - Blue", "Premium Bottle - Blue")
    assert adapter._titles_are_similar("Premium Bottle - Blue", " premium bottle blue ")
    assert adapter._titles_are_similar("Premium Bottle", "Premium Bottle - Blue")
    assert not adapter._titles_are_similar("Premium Bottle", "Unique Product")
    assert not adapter._titles_are_similar(None, "Premium Bottle")
    assert not adapter._titles_are_similar("Premium Bottle", None)


@pytest.mark.asyncio
async def test_llm_expansion_runs_only_when_first_pass_recall_is_low():
    """LLM expansion should trigger only for underperforming first-pass recall."""
    low_recall_client = FakeTMAPIClient(
        catalog={
            "手机配件": [
                {
                    "item_id": "low-1",
                    "title": "低召回类目商品",
                    "price": "8.00",
                    "sale_count": 200,
                    "img": "https://example.com/low-1.jpg",
                    "product_url": "https://detail.1688.com/offer/low-1.html",
                    "category_name": "手机配件",
                    "company_name": "低召回工厂",
                    "shop_name": "低召回店",
                    "moq": 10,
                    "shop_url": "https://shop.example.com/low-1",
                    "member_id": "member-low-1",
                }
            ],
            "磁吸手机壳": [
                {
                    "item_id": "llm-1",
                    "title": "LLM扩词候选",
                    "price": "9.50",
                    "sale_count": 2100,
                    "img": "https://example.com/llm-1.jpg",
                    "product_url": "https://detail.1688.com/offer/llm-1.html",
                    "category_name": "手机配件",
                    "company_name": "LLM工厂",
                    "shop_name": "LLM店",
                    "moq": 8,
                    "shop_url": "https://shop.example.com/llm-1",
                    "member_id": "member-llm-1",
                }
            ],
        },
        image_products=[],
    )
    low_recall_llm = FakeSGLangClient(queries=["磁吸手机壳"])
    low_recall_adapter = Alibaba1688Adapter(tmapi_client=low_recall_client, sglang_client=low_recall_llm)
    low_recall_adapter.settings.tmapi_1688_enable_llm_query_expansion = True
    low_recall_adapter.settings.tmapi_1688_suggest_limit_per_seed = 0
    low_recall_adapter.settings.tmapi_1688_llm_query_limit = 2
    low_recall_adapter.settings.tmapi_1688_llm_expansion_min_recall_threshold = 3
    low_recall_adapter.settings.tmapi_1688_llm_expansion_min_quality_threshold = 999.0

    low_products = await low_recall_adapter.fetch_products(keywords=["手机配件"], limit=2)

    low_keywords = [call.kwargs["keyword"] for call in low_recall_client.search_items.call_args_list]
    assert low_recall_llm.generate_structured_json.called
    assert "磁吸手机壳" in low_keywords
    assert any(product.normalized_attributes["seed_type"] == "llm" for product in low_products)

    high_recall_client = FakeTMAPIClient(
        catalog={
            "手机配件": [
                {
                    "item_id": "high-1",
                    "title": "高质量类目商品A",
                    "price": "8.00",
                    "sale_count": 5000,
                    "img": "https://example.com/high-1.jpg",
                    "product_url": "https://detail.1688.com/offer/high-1.html",
                    "category_name": "手机配件",
                    "company_name": "高质量工厂A",
                    "shop_name": "高质量店A",
                    "moq": 10,
                    "shop_url": "https://shop.example.com/high-1",
                    "member_id": "member-high-1",
                    "is_factory": True,
                    "is_super_factory": True,
                    "verified_supplier": True,
                    "support_dropshipping": True,
                },
                {
                    "item_id": "high-2",
                    "title": "高质量类目商品B",
                    "price": "9.00",
                    "sale_count": 4800,
                    "img": "https://example.com/high-2.jpg",
                    "product_url": "https://detail.1688.com/offer/high-2.html",
                    "category_name": "手机配件",
                    "company_name": "高质量工厂B",
                    "shop_name": "高质量店B",
                    "moq": 10,
                    "shop_url": "https://shop.example.com/high-2",
                    "member_id": "member-high-2",
                    "is_factory": True,
                    "is_super_factory": True,
                    "verified_supplier": True,
                    "support_dropshipping": True,
                },
                {
                    "item_id": "high-3",
                    "title": "高质量类目商品C",
                    "price": "10.00",
                    "sale_count": 4600,
                    "img": "https://example.com/high-3.jpg",
                    "product_url": "https://detail.1688.com/offer/high-3.html",
                    "category_name": "手机配件",
                    "company_name": "高质量工厂C",
                    "shop_name": "高质量店C",
                    "moq": 10,
                    "shop_url": "https://shop.example.com/high-3",
                    "member_id": "member-high-3",
                    "is_factory": True,
                    "is_super_factory": True,
                    "verified_supplier": True,
                    "support_dropshipping": True,
                },
            ]
        },
        image_products=[],
    )
    high_recall_llm = FakeSGLangClient(queries=["磁吸手机壳"])
    high_recall_adapter = Alibaba1688Adapter(tmapi_client=high_recall_client, sglang_client=high_recall_llm)
    high_recall_adapter.settings.tmapi_1688_enable_llm_query_expansion = True
    high_recall_adapter.settings.tmapi_1688_suggest_limit_per_seed = 0
    high_recall_adapter.settings.tmapi_1688_llm_query_limit = 2
    high_recall_adapter.settings.tmapi_1688_llm_expansion_min_recall_threshold = 3
    high_recall_adapter.settings.tmapi_1688_llm_expansion_min_quality_threshold = 20.0

    high_products = await high_recall_adapter.fetch_products(keywords=["手机配件"], limit=2)

    high_keywords = [call.kwargs["keyword"] for call in high_recall_client.search_items.call_args_list]
    assert not high_recall_llm.generate_structured_json.called
    assert "磁吸手机壳" not in high_keywords
    assert all(product.normalized_attributes["seed_type"] != "llm" for product in high_products)


def test_seed_priority_prefers_category_hotword_and_seasonal_over_cold_start_and_llm():
    """Seed merge priority should follow the new Phase 4 ordering."""
    adapter = Alibaba1688Adapter(tmapi_client=FakeTMAPIClient())

    merged: dict[str, Alibaba1688Candidate] = {}
    base_candidate = Alibaba1688Candidate(
        item_id="priority-1",
        title="同一商品",
        matched_keyword="热销",
        seed_type="cold_start",
        source_endpoints=["search_items"],
    )
    adapter._merge_candidate(merged, base_candidate)

    adapter._merge_candidate(
        merged,
        Alibaba1688Candidate(
            item_id="priority-1",
            title="同一商品",
            matched_keyword="夏季新品",
            seed_type="seasonal",
            source_endpoints=["search_items"],
        ),
    )
    assert merged["priority-1"].seed_type == "seasonal"

    adapter._merge_candidate(
        merged,
        Alibaba1688Candidate(
            item_id="priority-1",
            title="同一商品",
            matched_keyword="磁吸手机壳",
            seed_type="category_hotword",
            source_endpoints=["search_items"],
        ),
    )
    assert merged["priority-1"].seed_type == "category_hotword"

    adapter._merge_candidate(
        merged,
        Alibaba1688Candidate(
            item_id="priority-1",
            title="同一商品",
            matched_keyword="扩词候选",
            seed_type="llm",
            source_endpoints=["search_items"],
        ),
    )
    assert merged["priority-1"].seed_type == "category_hotword"

    adapter._merge_candidate(
        merged,
        Alibaba1688Candidate(
            item_id="priority-1",
            title="同一商品",
            matched_keyword="手机配件",
            seed_type="category",
            source_endpoints=["search_items"],
        ),
    )
    assert merged["priority-1"].seed_type == "category"


@pytest.mark.asyncio
async def test_diversification_seed_targets_include_new_lane_priority():
    """Diversification quotas should recognize new Phase 4 lanes in priority order."""
    adapter = Alibaba1688Adapter(tmapi_client=FakeTMAPIClient())
    adapter.settings.tmapi_1688_diversification_seed_min_quota = 1
    adapter.settings.tmapi_1688_diversification_seed_quota_max_lanes = 4

    ranked = [
        Alibaba1688Candidate(item_id="history-1", title="历史", seed_type="historical", source_endpoints=["search_items"], final_score=100.0),
        Alibaba1688Candidate(item_id="category-1", title="类目", seed_type="category", source_endpoints=["search_items"], final_score=95.0),
        Alibaba1688Candidate(item_id="hotword-1", title="热词", seed_type="category_hotword", source_endpoints=["search_items"], final_score=90.0),
        Alibaba1688Candidate(item_id="season-1", title="季节", seed_type="seasonal", source_endpoints=["search_items"], final_score=85.0),
        Alibaba1688Candidate(item_id="cold-1", title="冷启动", seed_type="cold_start", source_endpoints=["search_items"], final_score=80.0),
    ]

    lane_targets = adapter._compute_seed_lane_targets(ranked=ranked, limit=4)

    assert list(lane_targets.keys()) == ["historical", "category", "category_hotword", "seasonal"]


@pytest.mark.asyncio
async def test_explicit_keywords_have_stable_normalized_attributes_output():
    """Explicit keyword seed types should be preserved in normalized output."""
    client = FakeTMAPIClient(
        catalog={
            "磁吸手机壳": [
                {
                    "item_id": "attr-1",
                    "title": "属性输出商品",
                    "price": "9.00",
                    "sale_count": 1200,
                    "img": "https://example.com/attr-1.jpg",
                    "product_url": "https://detail.1688.com/offer/attr-1.html",
                    "category_name": "手机配件",
                    "company_name": "属性工厂",
                    "shop_name": "属性店",
                    "moq": 8,
                    "shop_url": "https://shop.example.com/attr-1",
                    "member_id": "member-attr-1",
                }
            ]
        },
        image_products=[],
    )
    adapter = Alibaba1688Adapter(tmapi_client=client)

    products = await adapter.fetch_products(keywords=["磁吸手机壳"], limit=1)

    assert len(products) == 1
    assert products[0].normalized_attributes["seed_type"] == "explicit"


@pytest.mark.asyncio
async def test_phase1_phase2_phase3_regression_with_phase4_seed_changes():
    """Phase 4 should not change score formula or supplier/diversification behavior."""
    client = FakeTMAPIClient(catalog=_build_diversification_shop_cap_catalog(), image_products=[])
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_diversification_shop_cap = 2
    adapter.settings.tmapi_1688_supplier_competition_set_size = 5
    adapter.settings.tmapi_1688_suggest_limit_per_seed = 0

    products = await adapter.fetch_products(keywords=["测试商品"], limit=4)

    for product in products:
        attrs = product.normalized_attributes
        assert attrs["seed_type"] == "explicit"
        assert attrs["final_score"] == pytest.approx(attrs["discovery_score"] + attrs["business_score"])
        assert len(product.supplier_candidates) >= 1

    shop_counts: dict[str, int] = {}
    for product in products:
        shop_key = product.normalized_attributes["member_id"]
        shop_counts[shop_key] = shop_counts.get(shop_key, 0) + 1
    assert max(shop_counts.values()) <= 2


def _build_review_defect_catalog() -> dict[str, list[dict]]:
    return {
        "测试商品": [
            {
                "item_id": "r-clean",
                "title": "评论干净商品",
                "price": "20.00",
                "sale_count": 4000,
                "img": "https://example.com/r-clean.jpg",
                "product_url": "https://detail.1688.com/offer/r-clean.html",
                "category_name": "测试类目",
                "company_name": "评论优质工厂",
                "shop_name": "评论优质店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/r-clean",
                "member_id": "member-r-clean",
            },
            {
                "item_id": "r-defect",
                "title": "评论有缺陷商品",
                "price": "20.00",
                "sale_count": 4200,
                "img": "https://example.com/r-defect.jpg",
                "product_url": "https://detail.1688.com/offer/r-defect.html",
                "category_name": "测试类目",
                "company_name": "评论差工厂",
                "shop_name": "评论差店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/r-defect",
                "member_id": "member-r-defect",
            },
        ]
    }


def _build_shop_focus_catalog() -> dict[str, list[dict]]:
    return {
        "测试商品": [
            {
                "item_id": "s-focused",
                "title": "专营店商品",
                "price": "20.00",
                "sale_count": 3800,
                "img": "https://example.com/s-focused.jpg",
                "product_url": "https://detail.1688.com/offer/s-focused.html",
                "category_name": "手机配件",
                "company_name": "专营工厂",
                "shop_name": "专营店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/s-focused",
                "member_id": "member-s-focused",
            },
            {
                "item_id": "s-general",
                "title": "杂货铺商品",
                "price": "20.00",
                "sale_count": 4000,
                "img": "https://example.com/s-general.jpg",
                "product_url": "https://detail.1688.com/offer/s-general.html",
                "category_name": "手机配件",
                "company_name": "杂货工厂",
                "shop_name": "杂货店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/s-general",
                "member_id": "member-s-general",
            },
        ]
    }


class FakeTMAPIClientWithReviewDefects(FakeTMAPIClient):
    """Extended fake client with review defect payloads."""

    async def _get_item_ratings(self, *, item_id, page=1, sort_type="default"):
        if item_id == "r-clean":
            return {
                "item_id": item_id,
                "page": page,
                "list": [
                    {"rate_star": 5, "feedback": "质量很好，发货快"},
                    {"rate_star": 5, "feedback": "非常满意，推荐购买"},
                ],
            }
        if item_id == "r-defect":
            return {
                "item_id": item_id,
                "page": page,
                "list": [
                    {"rate_star": 5, "feedback": "还可以"},
                    {"rate_star": 2, "feedback": "质量差，做工粗糙，有异味"},
                    {"rate_star": 3, "feedback": "发货慢，包装破损"},
                ],
            }
        return await super()._get_item_ratings(item_id=item_id, page=page, sort_type=sort_type)


class FakeTMAPIClientWithShopFocus(FakeTMAPIClient):
    """Extended fake client with shop focus payloads."""

    async def _get_shop_items(self, *, shop_url, page=1, page_size=20, sort="default", cat=None, cat_type=None):
        if "s-focused" in shop_url:
            return {
                "products": [
                    {
                        "item_id": "s-focused-alt-1",
                        "title": "专营店其他手机壳",
                        "price": "18.00",
                        "img": "https://example.com/s-focused-alt-1.jpg",
                        "category_name": "手机配件",
                    },
                    {
                        "item_id": "s-focused-alt-2",
                        "title": "专营店手机支架",
                        "price": "12.00",
                        "img": "https://example.com/s-focused-alt-2.jpg",
                        "category_name": "手机配件",
                    },
                ],
                "total": 15,
                "page": page,
                "page_size": page_size,
            }
        if "s-general" in shop_url:
            return {
                "products": [
                    {
                        "item_id": "s-general-alt-1",
                        "title": "杂货铺厨房用品",
                        "price": "25.00",
                        "img": "https://example.com/s-general-alt-1.jpg",
                        "category_name": "厨房用品",
                    },
                    {
                        "item_id": "s-general-alt-2",
                        "title": "杂货铺文具",
                        "price": "8.00",
                        "img": "https://example.com/s-general-alt-2.jpg",
                        "category_name": "办公文教",
                    },
                ],
                "total": 500,
                "page": page,
                "page_size": page_size,
            }
        return await super()._get_shop_items(
            shop_url=shop_url,
            page=page,
            page_size=page_size,
            sort=sort,
            cat=cat,
            cat_type=cat_type,
        )


@pytest.mark.asyncio
async def test_review_defect_penalties_reduce_business_score():
    """Candidates with quality/logistics defects in reviews should be penalized in business score."""
    client = FakeTMAPIClientWithReviewDefects(catalog=_build_review_defect_catalog())
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_enable_ratings = True
    adapter.settings.tmapi_1688_enable_review_risk_analysis = True

    products = await adapter.fetch_products(keywords=["测试商品"], limit=2)

    assert [product.source_product_id for product in products] == ["r-clean", "r-defect"]
    clean_attrs = products[0].normalized_attributes
    defect_attrs = products[1].normalized_attributes
    assert clean_attrs["review_risk_score"] > defect_attrs["review_risk_score"]
    assert clean_attrs["business_score"] > defect_attrs["business_score"]
    assert clean_attrs["final_score"] > defect_attrs["final_score"]
    assert defect_attrs["review_defect_flags"]["quality"] >= 1
    assert defect_attrs["review_defect_flags"]["logistics"] >= 1


@pytest.mark.asyncio
async def test_shop_focus_bonus_for_specialized_shops():
    """Specialized shops with focused inventory should receive shop intelligence bonus."""
    client = FakeTMAPIClientWithShopFocus(catalog=_build_shop_focus_catalog())
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_enable_shop_info = True
    adapter.settings.tmapi_1688_enable_shop_intelligence = True

    products = await adapter.fetch_products(keywords=["测试商品"], limit=2)

    assert [product.source_product_id for product in products] == ["s-focused", "s-general"]
    focused_attrs = products[0].normalized_attributes
    general_attrs = products[1].normalized_attributes
    assert focused_attrs["shop_focus_ratio"] is not None
    assert general_attrs["shop_focus_ratio"] is not None
    assert focused_attrs["shop_focus_ratio"] > general_attrs["shop_focus_ratio"]
    assert focused_attrs["shop_intelligence_score"] > general_attrs["shop_intelligence_score"]
    assert focused_attrs["business_score"] > general_attrs["business_score"]
    assert focused_attrs["final_score"] > general_attrs["final_score"]


@pytest.mark.asyncio
async def test_phase5_does_not_break_phase1_to_phase4_semantics():
    """Phase 5 should not change score formula or existing phase behavior."""
    client = FakeTMAPIClient(catalog=_build_diversification_shop_cap_catalog(), image_products=[])
    adapter = Alibaba1688Adapter(tmapi_client=client)
    adapter.settings.tmapi_1688_diversification_shop_cap = 2
    adapter.settings.tmapi_1688_supplier_competition_set_size = 5
    adapter.settings.tmapi_1688_enable_ratings = True
    adapter.settings.tmapi_1688_enable_shop_info = True
    adapter.settings.tmapi_1688_enable_review_risk_analysis = True
    adapter.settings.tmapi_1688_enable_shop_intelligence = True

    products = await adapter.fetch_products(keywords=["测试商品"], limit=4)

    for product in products:
        attrs = product.normalized_attributes
        assert attrs["seed_type"] == "explicit"
        assert attrs["final_score"] == pytest.approx(attrs["discovery_score"] + attrs["business_score"])
        assert len(product.supplier_candidates) >= 1
        assert "review_risk_score" in attrs
        assert "shop_intelligence_score" in attrs

    shop_counts: dict[str, int] = {}
    for product in products:
        shop_key = product.normalized_attributes["member_id"]
        shop_counts[shop_key] = shop_counts.get(shop_key, 0) + 1
    assert max(shop_counts.values()) <= 2


@pytest.mark.asyncio
async def test_historical_feedback_prior_boosts_business_score():
    """Candidates with high historical feedback priors should rank higher in business score."""
    catalog = {
        "测试商品": [
            {
                "item_id": "h-feedback-good",
                "title": "历史表现优秀商品",
                "price": "20.00",
                "sale_count": 4000,
                "img": "https://example.com/h-feedback-good.jpg",
                "product_url": "https://detail.1688.com/offer/h-feedback-good.html",
                "category_name": "测试类目",
                "company_name": "历史优质工厂",
                "shop_name": "历史优质店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/h-feedback-good",
                "member_id": "member-h-feedback-good",
            },
            {
                "item_id": "h-feedback-neutral",
                "title": "历史表现一般商品",
                "price": "20.00",
                "sale_count": 4100,
                "img": "https://example.com/h-feedback-neutral.jpg",
                "product_url": "https://detail.1688.com/offer/h-feedback-neutral.html",
                "category_name": "测试类目",
                "company_name": "一般工厂",
                "shop_name": "一般店铺",
                "moq": 10,
                "shop_url": "https://shop.example.com/h-feedback-neutral",
                "member_id": "member-h-feedback-neutral",
            },
        ]
    }
    client = FakeTMAPIClient(catalog=catalog, image_products=[])
    aggregator = FakeFeedbackAggregator()
    adapter = Alibaba1688Adapter(tmapi_client=client, feedback_aggregator=aggregator)
    adapter.settings.tmapi_1688_enable_historical_feedback = True
    adapter.settings.tmapi_1688_enable_shop_info = False

    products = await adapter.fetch_products(keywords=["测试商品"], limit=2)

    assert [product.source_product_id for product in products] == ["h-feedback-good", "h-feedback-neutral"]
    good_attrs = products[0].normalized_attributes
    neutral_attrs = products[1].normalized_attributes
    assert good_attrs["historical_shop_prior"] > neutral_attrs["historical_shop_prior"]
    assert good_attrs["historical_supplier_prior"] > neutral_attrs["historical_supplier_prior"]
    assert good_attrs["historical_feedback_score"] > neutral_attrs["historical_feedback_score"]
    assert good_attrs["business_score"] > neutral_attrs["business_score"]
    assert good_attrs["final_score"] > neutral_attrs["final_score"]


@pytest.mark.asyncio
async def test_phase6_does_not_break_phase1_to_phase5_semantics():
    """Phase 6 should not change score formula or existing phase behavior."""
    client = FakeTMAPIClient(catalog=_build_diversification_shop_cap_catalog(), image_products=[])
    aggregator = FakeFeedbackAggregator()
    adapter = Alibaba1688Adapter(tmapi_client=client, feedback_aggregator=aggregator)
    adapter.settings.tmapi_1688_diversification_shop_cap = 2
    adapter.settings.tmapi_1688_supplier_competition_set_size = 5
    adapter.settings.tmapi_1688_enable_ratings = True
    adapter.settings.tmapi_1688_enable_shop_info = True
    adapter.settings.tmapi_1688_enable_review_risk_analysis = True
    adapter.settings.tmapi_1688_enable_shop_intelligence = True
    adapter.settings.tmapi_1688_enable_historical_feedback = True

    products = await adapter.fetch_products(keywords=["测试商品"], limit=4)

    for product in products:
        attrs = product.normalized_attributes
        assert attrs["seed_type"] == "explicit"
        assert attrs["final_score"] == pytest.approx(attrs["discovery_score"] + attrs["business_score"])
        assert len(product.supplier_candidates) >= 1
        assert "review_risk_score" in attrs
        assert "shop_intelligence_score" in attrs
        assert "historical_feedback_score" in attrs

    shop_counts: dict[str, int] = {}
    for product in products:
        shop_key = product.normalized_attributes["member_id"]
        shop_counts[shop_key] = shop_counts.get(shop_key, 0) + 1
    assert max(shop_counts.values()) <= 2

