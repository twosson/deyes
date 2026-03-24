"""Tests for Phase 1 minimum viable platform (MVP).

Tests the complete flow:
1. ContentAssetManager generates images
2. PlatformPublisher publishes to Temu
3. PlatformListing records are created
"""
from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.content_asset_manager import ContentAssetManagerAgent
from app.agents.platform_publisher import PlatformPublisherAgent
from app.agents.product_selector import ProductSelectorAgent
from app.core.enums import (
    AssetType,
    CandidateStatus,
    PlatformListingStatus,
    ProductLifecycle,
    SourcePlatform,
    StrategyRunStatus,
    TriggerType,
)
from app.db.models import CandidateProduct, ContentAsset, PlatformListing, StrategyRun, SupplierMatch
from app.services.source_adapter import ProductData, SourceAdapter


class StubAlibaba1688Adapter(SourceAdapter):
    """Minimal adapter stub that returns TMAPI-enriched 1688 products."""

    async def fetch_products(
        self,
        category: str | None = None,
        keywords: list[str] | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        limit: int = 10,
        region: str | None = None,
    ) -> list[ProductData]:
        return [
            ProductData(
                source_platform=SourcePlatform.ALIBABA_1688,
                source_product_id="tmapi-1001",
                source_url="https://detail.1688.com/offer/tmapi-1001.html",
                title="TMAPI 精选手机壳",
                category="手机配件",
                currency="USD",
                platform_price=Decimal("1.57"),
                sales_count=1800,
                rating=Decimal("4.50"),
                main_image_url="https://example.com/tmapi-1001.jpg",
                raw_payload={
                    "detail_payload": {
                        "company_name": "深圳基础工厂",
                        "shop_name": "基础店铺",
                    },
                    "matched_keyword": "手机壳",
                },
                normalized_attributes={
                    "seed_type": "explicit",
                    "detail_enriched": True,
                    "is_factory_result": True,
                    "shop_name": "基础店铺",
                    "company_name": "深圳基础工厂",
                    "discovery_score": 88.5,
                    "business_score": 24.0,
                    "final_score": 112.5,
                    "historical_seed_prior": 3.5,
                    "historical_shop_prior": 2.5,
                    "historical_supplier_prior": 1.5,
                    "historical_feedback_score": 7.5,
                },
                supplier_candidates=[
                    {
                        "supplier_name": "深圳基础工厂",
                        "supplier_url": "https://shop.example.com/1001",
                        "supplier_sku": "tmapi-1001",
                        "supplier_price": Decimal("1.57"),
                        "moq": 20,
                        "confidence_score": Decimal("0.91"),
                        "raw_payload": {
                            "source_platform": "alibaba_1688",
                            "shop_name": "基础店铺",
                            "company_name": "深圳基础工厂",
                            "is_factory_result": True,
                        },
                    },
                    {
                        "supplier_name": "东莞竞争供应商",
                        "supplier_url": "https://shop.example.com/2002",
                        "supplier_sku": "tmapi-2002",
                        "supplier_price": Decimal("1.49"),
                        "moq": 30,
                        "confidence_score": Decimal("0.84"),
                        "raw_payload": {
                            "source_platform": "alibaba_1688",
                            "shop_name": "竞争店铺A",
                            "company_name": "东莞竞争供应商",
                            "competition_source": "image_recall",
                        },
                    },
                    {
                        "supplier_name": "深圳同店备选SKU",
                        "supplier_url": "https://shop.example.com/1001",
                        "supplier_sku": "tmapi-3003",
                        "supplier_price": Decimal("1.62"),
                        "moq": 10,
                        "confidence_score": Decimal("0.70"),
                        "raw_payload": {
                            "source_platform": "alibaba_1688",
                            "shop_name": "基础店铺",
                            "company_name": "深圳基础工厂",
                            "alternative_sku": True,
                        },
                    },
                ],
            )
        ]


@pytest.mark.asyncio
async def test_product_selector_persists_tmapi_enriched_candidate_and_supplier(db_session: AsyncSession):
    """Selector should persist TMAPI normalized attributes and real supplier candidates."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.commit()

    from app.agents.base.agent import AgentContext

    agent = ProductSelectorAgent(source_adapter=StubAlibaba1688Adapter())
    context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={
            "platform": SourcePlatform.ALIBABA_1688.value,
            "keywords": ["手机壳"],
            "max_candidates": 1,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 1

    candidate_result = await db_session.execute(
        select(CandidateProduct).where(CandidateProduct.strategy_run_id == strategy_run.id)
    )
    candidate = candidate_result.scalar_one()

    assert candidate.source_platform == SourcePlatform.ALIBABA_1688
    assert candidate.source_product_id == "tmapi-1001"
    assert candidate.normalized_attributes["seed_type"] == "explicit"
    assert candidate.normalized_attributes["detail_enriched"] is True
    assert candidate.normalized_attributes["is_factory_result"] is True
    assert candidate.normalized_attributes["company_name"] == "深圳基础工厂"
    assert candidate.normalized_attributes["discovery_score"] == 88.5
    assert candidate.normalized_attributes["business_score"] == 24.0
    assert candidate.normalized_attributes["final_score"] == 112.5
    assert candidate.normalized_attributes["historical_seed_prior"] == 3.5
    assert candidate.normalized_attributes["historical_shop_prior"] == 2.5
    assert candidate.normalized_attributes["historical_supplier_prior"] == 1.5
    assert candidate.normalized_attributes["historical_feedback_score"] == 7.5

    supplier_result = await db_session.execute(
        select(SupplierMatch).where(SupplierMatch.candidate_product_id == candidate.id)
    )
    suppliers = list(supplier_result.scalars().all())

    assert len(suppliers) == 3
    assert suppliers[0].supplier_name == "深圳基础工厂"
    assert suppliers[0].supplier_sku == "tmapi-1001"
    assert suppliers[0].moq == 20
    assert suppliers[0].raw_payload["company_name"] == "深圳基础工厂"
    assert suppliers[0].raw_payload["is_factory_result"] is True
    assert suppliers[1].supplier_name == "东莞竞争供应商"
    assert suppliers[1].supplier_sku == "tmapi-2002"
    assert suppliers[1].raw_payload["competition_source"] == "image_recall"
    assert suppliers[2].supplier_name == "深圳同店备选SKU"
    assert suppliers[2].supplier_sku == "tmapi-3003"
    assert suppliers[2].raw_payload["alternative_sku"] is True


@pytest.mark.asyncio
async def test_product_selector_persists_historical_feedback_signals(db_session: AsyncSession):
    """Selector should persist Phase 6 historical feedback signals in normalized attributes."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.commit()

    from app.agents.base.agent import AgentContext

    agent = ProductSelectorAgent(source_adapter=StubAlibaba1688Adapter())
    context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={
            "platform": SourcePlatform.ALIBABA_1688.value,
            "keywords": ["手机壳"],
            "max_candidates": 1,
        },
    )

    result = await agent.execute(context)

    assert result.success is True

    candidate_result = await db_session.execute(
        select(CandidateProduct).where(CandidateProduct.strategy_run_id == strategy_run.id)
    )
    candidate = candidate_result.scalar_one()

    assert candidate.normalized_attributes["historical_seed_prior"] == 3.5
    assert candidate.normalized_attributes["historical_shop_prior"] == 2.5
    assert candidate.normalized_attributes["historical_supplier_prior"] == 1.5
    assert candidate.normalized_attributes["historical_feedback_score"] == 7.5


class StubAlibaba1688AdapterWith7Suppliers(SourceAdapter):
    """Stub adapter that returns 7 supplier candidates to test the 5-supplier cap."""

    async def fetch_products(
        self,
        category: str | None = None,
        keywords: list[str] | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        limit: int = 10,
        region: str | None = None,
    ) -> list[ProductData]:
        return [
            ProductData(
                source_platform=SourcePlatform.ALIBABA_1688,
                source_product_id="cap-test-1001",
                source_url="https://detail.1688.com/offer/cap-test-1001.html",
                title="Phase 3 竞争集上限测试商品",
                category="测试类目",
                currency="USD",
                platform_price=Decimal("2.00"),
                sales_count=5000,
                rating=Decimal("4.8"),
                main_image_url="https://example.com/cap-test-1001.jpg",
                raw_payload={},
                normalized_attributes={
                    "seed_type": "explicit",
                    "detail_enriched": True,
                },
                supplier_candidates=[
                    {
                        "supplier_name": f"供应商 {i}",
                        "supplier_url": f"https://shop.example.com/supplier-{i}",
                        "supplier_sku": f"sku-{i:04d}",
                        "supplier_price": Decimal("2.00") + Decimal(i * 0.1),
                        "moq": 10 + i * 5,
                        "confidence_score": Decimal("0.90") - Decimal(i * 0.02),
                        "raw_payload": {
                            "source_platform": "alibaba_1688",
                            "supplier_index": i,
                        },
                    }
                    for i in range(1, 8)
                ],
            )
        ]


@pytest.mark.asyncio
async def test_product_selector_caps_supplier_matches_at_5(db_session: AsyncSession):
    """ProductSelectorAgent should persist at most 5 SupplierMatch records per candidate."""
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)
    await db_session.commit()

    from app.agents.base.agent import AgentContext

    agent = ProductSelectorAgent(source_adapter=StubAlibaba1688AdapterWith7Suppliers())
    context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={
            "platform": SourcePlatform.ALIBABA_1688.value,
            "keywords": ["测试商品"],
            "max_candidates": 1,
        },
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["count"] == 1

    candidate_result = await db_session.execute(
        select(CandidateProduct).where(CandidateProduct.strategy_run_id == strategy_run.id)
    )
    candidate = candidate_result.scalar_one()

    supplier_result = await db_session.execute(
        select(SupplierMatch).where(SupplierMatch.candidate_product_id == candidate.id)
    )
    suppliers = list(supplier_result.scalars().all())

    assert len(suppliers) == 5, f"Expected exactly 5 SupplierMatch records, got {len(suppliers)}"
    assert suppliers[0].supplier_name == "供应商 1"
    assert suppliers[0].confidence_score == Decimal("0.90")
    assert suppliers[4].supplier_name == "供应商 5"
    assert suppliers[4].confidence_score == Decimal("0.82")
    for supplier in suppliers:
        assert supplier.raw_payload["source_platform"] == "alibaba_1688"


@pytest.fixture
async def sample_candidate_product(db_session: AsyncSession) -> CandidateProduct:
    """Create a sample candidate product."""
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=uuid4(),
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="123456",
        source_url="https://detail.1688.com/offer/123456.html",
        title="iPhone 15 Pro Phone Case - Minimalist Clear",
        category="phone accessories",
        currency="USD",
        platform_price=Decimal("5.50"),
        sales_count=1200,
        rating=Decimal("4.8"),
        main_image_url="https://example.com/image.jpg",
        status=CandidateStatus.DISCOVERED,
        lifecycle_status=ProductLifecycle.DRAFT,
        internal_sku="DEY-PH-001",
        raw_payload={
            "moq": 10,
            "supplier_name": "深圳某某电子",
            "material": "TPU",
            "size": "iPhone 15 Pro",
        },
    )
    db_session.add(candidate)
    await db_session.commit()
    return candidate


@pytest.fixture
def sample_content_assets(db_session: AsyncSession, sample_candidate_product: CandidateProduct):
    """Create sample content assets."""
    assets = []

    # Main image - minimalist style
    asset1 = ContentAsset(
        id=uuid4(),
        candidate_product_id=sample_candidate_product.id,
        asset_type=AssetType.MAIN_IMAGE,
        style_tags=["minimalist"],
        platform_tags=["temu", "amazon"],
        region_tags=["us", "uk"],
        file_url="https://minio.example.com/deyes-assets/products/123/main_image/minimalist/img1.png",
        file_size=512000,
        dimensions="1024x1024",
        format="png",
        ai_quality_score=Decimal("9.2"),
        human_approved=True,
        usage_count=0,
        version=1,
    )
    assets.append(asset1)

    # Detail image
    asset2 = ContentAsset(
        id=uuid4(),
        candidate_product_id=sample_candidate_product.id,
        asset_type=AssetType.DETAIL_IMAGE,
        style_tags=["minimalist"],
        platform_tags=["temu"],
        region_tags=["us"],
        file_url="https://minio.example.com/deyes-assets/products/123/detail_image/minimalist/img2.png",
        file_size=480000,
        dimensions="1024x1024",
        format="png",
        ai_quality_score=Decimal("8.8"),
        human_approved=True,
        usage_count=0,
        version=1,
    )
    assets.append(asset2)

    for asset in assets:
        db_session.add(asset)

    return assets


@pytest.mark.asyncio
async def test_content_asset_manager_mock(db_session: AsyncSession, sample_candidate_product: CandidateProduct):
    """Test ContentAssetManager with mock ComfyUI and MinIO."""
    from unittest.mock import AsyncMock, MagicMock

    # Mock ComfyUI client
    mock_comfyui = AsyncMock()
    mock_comfyui.generate_product_image = AsyncMock(return_value=b"fake_image_data")

    # Mock MinIO client
    mock_minio = AsyncMock()
    mock_minio.upload_image = AsyncMock(
        return_value="https://minio.example.com/deyes-assets/products/123/main_image/minimalist/img1.png"
    )

    # Create agent
    agent = ContentAssetManagerAgent(
        comfyui_client=mock_comfyui,
        minio_client=mock_minio,
    )

    # Create context
    from app.agents.base.agent import AgentContext

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "candidate_product_id": str(sample_candidate_product.id),
            "asset_types": ["main_image"],
            "styles": ["minimalist"],
            "generate_count": 1,
            "platforms": ["temu"],
            "regions": ["us"],
        },
    )

    # Execute
    result = await agent.execute(context)

    # Assertions
    assert result.success is True
    assert result.output_data["assets_created"] == 1
    assert len(result.output_data["asset_ids"]) == 1

    # Check database
    await db_session.commit()
    assets = await db_session.execute(
        db_session.query(ContentAsset).filter_by(candidate_product_id=sample_candidate_product.id)
    )
    assets_list = list(assets.scalars().all())
    assert len(assets_list) == 1
    assert assets_list[0].asset_type == AssetType.MAIN_IMAGE
    assert "minimalist" in assets_list[0].style_tags


@pytest.mark.asyncio
async def test_platform_publisher_temu_mock(
    db_session: AsyncSession,
    sample_candidate_product: CandidateProduct,
    sample_content_assets: list[ContentAsset],
):
    """Test PlatformPublisher with mock Temu adapter."""
    # Update product lifecycle
    sample_candidate_product.lifecycle_status = ProductLifecycle.READY_TO_PUBLISH
    await db_session.commit()

    # Create agent
    agent = PlatformPublisherAgent()

    # Create context
    from app.agents.base.agent import AgentContext

    context = AgentContext(
        strategy_run_id=uuid4(),
        db=db_session,
        input_data={
            "candidate_product_id": str(sample_candidate_product.id),
            "target_platforms": [
                {"platform": "temu", "region": "us"},
            ],
            "pricing_strategy": "standard",
            "auto_approve": True,
        },
    )

    # Execute
    result = await agent.execute(context)

    # Assertions
    assert result.success is True
    assert result.output_data["published_count"] == 1
    assert result.output_data["failed_count"] == 0
    assert len(result.output_data["listing_ids"]) == 1

    # Check database
    await db_session.commit()
    listings = await db_session.execute(
        db_session.query(PlatformListing).filter_by(candidate_product_id=sample_candidate_product.id)
    )
    listings_list = list(listings.scalars().all())
    assert len(listings_list) == 1

    listing = listings_list[0]
    assert listing.platform.value == "temu"
    assert listing.region == "us"
    assert listing.status == PlatformListingStatus.ACTIVE
    assert listing.price > Decimal("0")
    assert listing.currency == "USD"
    assert listing.inventory > 0
    assert listing.platform_listing_id.startswith("TEMU-")


@pytest.mark.asyncio
async def test_complete_flow_mock(db_session: AsyncSession):
    """Test complete flow: Product → Assets → Publish."""
    # 1. Create candidate product
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=uuid4(),
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="789012",
        title="Wireless Earbuds - Premium Sound",
        category="electronics",
        currency="USD",
        platform_price=Decimal("8.00"),
        status=CandidateStatus.DISCOVERED,
        lifecycle_status=ProductLifecycle.DRAFT,
        internal_sku="DEY-EL-002",
    )
    db_session.add(candidate)
    await db_session.commit()

    # 2. Generate content assets (mock)
    from unittest.mock import AsyncMock

    mock_comfyui = AsyncMock()
    mock_comfyui.generate_product_image = AsyncMock(return_value=b"fake_image_data")

    mock_minio = AsyncMock()
    mock_minio.upload_image = AsyncMock(
        return_value=f"https://minio.example.com/deyes-assets/products/{candidate.id}/main_image/minimalist/img1.png"
    )

    content_agent = ContentAssetManagerAgent(
        comfyui_client=mock_comfyui,
        minio_client=mock_minio,
    )

    from app.agents.base.agent import AgentContext

    content_context = AgentContext(
        strategy_run_id=candidate.strategy_run_id,
        db=db_session,
        input_data={
            "candidate_product_id": str(candidate.id),
            "asset_types": ["main_image", "detail_image"],
            "styles": ["minimalist"],
            "generate_count": 1,
            "platforms": ["temu"],
            "regions": ["us"],
        },
    )

    content_result = await content_agent.execute(content_context)
    assert content_result.success is True
    assert content_result.output_data["assets_created"] == 2

    # Approve assets
    await db_session.commit()
    assets = await db_session.execute(
        db_session.query(ContentAsset).filter_by(candidate_product_id=candidate.id)
    )
    for asset in assets.scalars().all():
        asset.human_approved = True
    await db_session.commit()

    # 3. Publish to platform
    publish_agent = PlatformPublisherAgent()

    publish_context = AgentContext(
        strategy_run_id=candidate.strategy_run_id,
        db=db_session,
        input_data={
            "candidate_product_id": str(candidate.id),
            "target_platforms": [
                {"platform": "temu", "region": "us"},
                {"platform": "temu", "region": "uk"},
            ],
            "pricing_strategy": "standard",
            "auto_approve": True,
        },
    )

    publish_result = await publish_agent.execute(publish_context)
    assert publish_result.success is True
    assert publish_result.output_data["published_count"] == 2

    # 4. Verify final state
    await db_session.commit()

    # Check product lifecycle
    await db_session.refresh(candidate)
    assert candidate.lifecycle_status == ProductLifecycle.PUBLISHED

    # Check listings
    listings = await db_session.execute(
        db_session.query(PlatformListing).filter_by(candidate_product_id=candidate.id)
    )
    listings_list = list(listings.scalars().all())
    assert len(listings_list) == 2

    # Check US listing
    us_listing = next(l for l in listings_list if l.region == "us")
    assert us_listing.platform.value == "temu"
    assert us_listing.currency == "USD"
    assert us_listing.status == PlatformListingStatus.ACTIVE

    # Check UK listing
    uk_listing = next(l for l in listings_list if l.region == "uk")
    assert uk_listing.platform.value == "temu"
    assert uk_listing.currency == "GBP"
    assert uk_listing.status == PlatformListingStatus.ACTIVE


@pytest.mark.asyncio
async def test_pricing_calculation():
    """Test pricing calculation logic."""
    from app.agents.platform_publisher import PlatformPublisherAgent
    from app.core.enums import TargetPlatform

    agent = PlatformPublisherAgent()

    # Create mock candidate
    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=uuid4(),
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="test",
        title="Test Product",
        platform_price=Decimal("5.00"),  # $5 cost
        status=CandidateStatus.DISCOVERED,
    )

    # Test standard pricing
    price, currency = agent._calculate_price(
        candidate=candidate,
        platform=TargetPlatform.TEMU,
        region="us",
        strategy="standard",
    )

    assert price > Decimal("5.00")  # Must be higher than cost
    assert price < Decimal("50.00")  # Reasonable range
    assert currency == "USD"

    # Test aggressive pricing (lower)
    price_aggressive, _ = agent._calculate_price(
        candidate=candidate,
        platform=TargetPlatform.TEMU,
        region="us",
        strategy="aggressive",
    )

    assert price_aggressive < price  # Aggressive should be cheaper

    # Test premium pricing (higher)
    price_premium, _ = agent._calculate_price(
        candidate=candidate,
        platform=TargetPlatform.TEMU,
        region="us",
        strategy="premium",
    )

    assert price_premium > price  # Premium should be more expensive


@pytest.mark.asyncio
async def test_psychological_pricing():
    """Test psychological price rounding."""
    from app.agents.platform_publisher import PlatformPublisherAgent

    agent = PlatformPublisherAgent()

    # Test under $10
    assert agent._round_to_psychological_price(Decimal("7.23")) == Decimal("7.99")
    assert agent._round_to_psychological_price(Decimal("9.50")) == Decimal("9.99")

    # Test $10-$50
    assert agent._round_to_psychological_price(Decimal("15.67")) == Decimal("19.99")
    assert agent._round_to_psychological_price(Decimal("23.45")) == Decimal("29.99")

    # Test over $50
    assert agent._round_to_psychological_price(Decimal("67.89")) == Decimal("69.99")
    assert agent._round_to_psychological_price(Decimal("123.45")) == Decimal("124.99")


@pytest.mark.asyncio
async def test_pricing_analyst_selects_best_supplier_from_competition_set(db_session: AsyncSession):
    """PricingAnalystAgent should select the best supplier path from multiple matches."""
    from app.agents.base.agent import AgentContext
    from app.agents.pricing_analyst import PricingAnalystAgent

    # Create strategy run and candidate
    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="pricing-test-001",
        source_url="https://detail.1688.com/offer/pricing-test-001.html",
        title="Pricing Test Product",
        category="test",
        currency="USD",
        platform_price=Decimal("25.00"),
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    # Create multiple supplier matches with different characteristics
    supplier_a = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="Cheapest But Low Confidence",
        supplier_url="https://shop.example.com/supplier-a",
        supplier_sku="sku-a",
        supplier_price=Decimal("8.00"),
        moq=100,
        confidence_score=Decimal("0.50"),
        raw_payload={},
        selected=False,
    )
    db_session.add(supplier_a)

    supplier_b = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="High Confidence Factory",
        supplier_url="https://shop.example.com/supplier-b",
        supplier_sku="sku-b",
        supplier_price=Decimal("8.50"),
        moq=20,
        confidence_score=Decimal("0.92"),
        raw_payload={
            "is_factory_result": True,
            "verified_supplier": True,
        },
        selected=False,
    )
    db_session.add(supplier_b)

    supplier_c = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="Alternative SKU Fallback",
        supplier_url="https://shop.example.com/supplier-c",
        supplier_sku="sku-c",
        supplier_price=Decimal("8.20"),
        moq=50,
        confidence_score=Decimal("0.70"),
        raw_payload={
            "alternative_sku": True,
        },
        selected=False,
    )
    db_session.add(supplier_c)

    await db_session.commit()

    # Execute pricing analyst agent
    agent = PricingAnalystAgent()
    context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={"candidate_ids": [str(candidate.id)]},
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["assessed_count"] == 1

    # Verify candidate status
    await db_session.refresh(candidate)
    assert candidate.status == CandidateStatus.PRICED

    # Verify only one supplier is selected
    supplier_result = await db_session.execute(
        select(SupplierMatch).where(SupplierMatch.candidate_product_id == candidate.id)
    )
    suppliers = list(supplier_result.scalars().all())
    selected_suppliers = [s for s in suppliers if s.selected]

    assert len(selected_suppliers) == 1
    selected = selected_suppliers[0]

    # Verify the selected supplier is the high-confidence factory (supplier_b)
    # despite not being the absolute cheapest
    assert selected.supplier_name == "High Confidence Factory"
    assert selected.supplier_price == Decimal("8.50")

    # Verify pricing assessment exists and includes supplier selection explanation
    from app.db.models import PricingAssessment

    assessment_result = await db_session.execute(
        select(PricingAssessment).where(PricingAssessment.candidate_product_id == candidate.id)
    )
    assessment = assessment_result.scalar_one()

    assert assessment is not None
    assert assessment.explanation is not None
    assert "supplier_selection" in assessment.explanation

    supplier_selection = assessment.explanation["supplier_selection"]
    assert supplier_selection["competition_set_size"] == 3
    assert supplier_selection["considered_supplier_count"] == 3
    assert supplier_selection["selected_supplier"] is not None
    assert supplier_selection["selected_supplier"]["supplier_match_id"] == str(selected.id)
    assert "ranked_supplier_paths" in supplier_selection
    assert len(supplier_selection["ranked_supplier_paths"]) == 3
    assert "selection_reason" in supplier_selection


@pytest.mark.asyncio
async def test_pricing_analyst_rerun_keeps_single_selected_supplier_and_single_assessment(
    db_session: AsyncSession,
):
    """PricingAnalystAgent reruns should remain idempotent at the DB boundary."""
    from app.agents.base.agent import AgentContext
    from app.agents.pricing_analyst import PricingAnalystAgent
    from app.db.models import PricingAssessment

    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="pricing-rerun-001",
        source_url="https://detail.1688.com/offer/pricing-rerun-001.html",
        title="Pricing Rerun Test Product",
        category="test",
        currency="USD",
        platform_price=Decimal("30.00"),
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    suppliers = [
        SupplierMatch(
            id=uuid4(),
            candidate_product_id=candidate.id,
            supplier_name="Low Confidence Cheapest",
            supplier_url="https://shop.example.com/rerun-a",
            supplier_sku="rerun-a",
            supplier_price=Decimal("9.00"),
            moq=120,
            confidence_score=Decimal("0.40"),
            raw_payload={},
            selected=True,
        ),
        SupplierMatch(
            id=uuid4(),
            candidate_product_id=candidate.id,
            supplier_name="Best Composite Supplier",
            supplier_url="https://shop.example.com/rerun-b",
            supplier_sku="rerun-b",
            supplier_price=Decimal("9.60"),
            moq=20,
            confidence_score=Decimal("0.93"),
            raw_payload={"is_factory_result": True, "verified_supplier": True},
            selected=False,
        ),
        SupplierMatch(
            id=uuid4(),
            candidate_product_id=candidate.id,
            supplier_name="Alternative SKU Backup",
            supplier_url="https://shop.example.com/rerun-c",
            supplier_sku="rerun-c",
            supplier_price=Decimal("9.20"),
            moq=40,
            confidence_score=Decimal("0.70"),
            raw_payload={"alternative_sku": True},
            selected=True,
        ),
    ]
    for supplier in suppliers:
        db_session.add(supplier)

    await db_session.commit()

    agent = PricingAnalystAgent()
    context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={"candidate_ids": [str(candidate.id)]},
    )

    first_result = await agent.execute(context)
    second_result = await agent.execute(context)

    assert first_result.success is True
    assert second_result.success is True
    assert first_result.output_data["assessed_count"] == 1
    assert second_result.output_data["assessed_count"] == 1

    supplier_result = await db_session.execute(
        select(SupplierMatch).where(SupplierMatch.candidate_product_id == candidate.id)
    )
    persisted_suppliers = list(supplier_result.scalars().all())
    selected_suppliers = [supplier for supplier in persisted_suppliers if supplier.selected]

    assert len(selected_suppliers) == 1
    assert selected_suppliers[0].supplier_name == "Best Composite Supplier"

    assessment_result = await db_session.execute(
        select(PricingAssessment).where(PricingAssessment.candidate_product_id == candidate.id)
    )
    assessments = list(assessment_result.scalars().all())

    assert len(assessments) == 1
    assert assessments[0].explanation is not None
    assert assessments[0].explanation["supplier_selection"]["selected_supplier"]["supplier_name"] == (
        "Best Composite Supplier"
    )


@pytest.mark.asyncio
async def test_pricing_analyst_skips_candidate_without_supplier_matches(db_session: AsyncSession):
    """PricingAnalystAgent should skip candidates that have no supplier competition set."""
    from app.agents.base.agent import AgentContext
    from app.agents.pricing_analyst import PricingAnalystAgent
    from app.db.models import PricingAssessment

    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="pricing-nosupplier-001",
        source_url="https://detail.1688.com/offer/pricing-nosupplier-001.html",
        title="Pricing No Supplier Test Product",
        category="test",
        currency="USD",
        platform_price=Decimal("19.99"),
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)
    await db_session.commit()

    agent = PricingAnalystAgent()
    context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={"candidate_ids": [str(candidate.id)]},
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["assessed_count"] == 0

    await db_session.refresh(candidate)
    assert candidate.status == CandidateStatus.DISCOVERED

    assessment_result = await db_session.execute(
        select(PricingAssessment).where(PricingAssessment.candidate_product_id == candidate.id)
    )
    assert assessment_result.scalar_one_or_none() is None


@pytest.mark.asyncio
async def test_pricing_analyst_skips_candidate_with_invalid_platform_price(db_session: AsyncSession):
    """PricingAnalystAgent should skip candidates with missing or invalid platform_price."""
    from app.agents.base.agent import AgentContext
    from app.agents.pricing_analyst import PricingAnalystAgent
    from app.db.models import PricingAssessment

    strategy_run = StrategyRun(
        id=uuid4(),
        trigger_type=TriggerType.API,
        source_platform=SourcePlatform.ALIBABA_1688,
        status=StrategyRunStatus.QUEUED,
        max_candidates=5,
    )
    db_session.add(strategy_run)

    candidate = CandidateProduct(
        id=uuid4(),
        strategy_run_id=strategy_run.id,
        source_platform=SourcePlatform.ALIBABA_1688,
        source_product_id="pricing-noplatform-001",
        source_url="https://detail.1688.com/offer/pricing-noplatform-001.html",
        title="Pricing Missing Platform Price",
        category="test",
        currency="USD",
        platform_price=None,
        status=CandidateStatus.DISCOVERED,
    )
    db_session.add(candidate)

    supplier = SupplierMatch(
        id=uuid4(),
        candidate_product_id=candidate.id,
        supplier_name="Valid Supplier",
        supplier_url="https://shop.example.com/platform-missing",
        supplier_sku="platform-missing-1",
        supplier_price=Decimal("7.50"),
        moq=20,
        confidence_score=Decimal("0.90"),
        raw_payload={"is_factory_result": True},
        selected=False,
    )
    db_session.add(supplier)
    await db_session.commit()

    agent = PricingAnalystAgent()
    context = AgentContext(
        strategy_run_id=strategy_run.id,
        db=db_session,
        input_data={"candidate_ids": [str(candidate.id)]},
    )

    result = await agent.execute(context)

    assert result.success is True
    assert result.output_data["assessed_count"] == 0

    await db_session.refresh(candidate)
    assert candidate.status == CandidateStatus.DISCOVERED
    assert supplier.selected is False

    assessment_result = await db_session.execute(
        select(PricingAssessment).where(PricingAssessment.candidate_product_id == candidate.id)
    )
    assert assessment_result.scalar_one_or_none() is None
