"""Product Selector Agent."""
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.core.config import get_settings
from app.core.enums import CandidateStatus, SourcePlatform
from app.db.models import CandidateProduct, SupplierMatch
from app.services.source_adapter import MockSourceAdapter, SourceAdapter
from app.services.supplier_matcher import SupplierMatcherService


class ProductSelectorAgent(BaseAgent):
    """Agent for discovering candidate products."""

    def __init__(
        self,
        source_adapter: Optional[SourceAdapter] = None,
        supplier_matcher: Optional[SupplierMatcherService] = None,
    ):
        super().__init__("product_selector")
        self.source_adapter = source_adapter
        self.supplier_matcher = supplier_matcher or SupplierMatcherService()

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute product selection."""
        created_adapter = False

        try:
            # Extract input parameters
            platform = SourcePlatform(context.input_data.get("platform", "temu"))
            category = context.input_data.get("category")
            keywords = context.input_data.get("keywords", [])
            region = context.input_data.get("region")
            price_min = context.input_data.get("price_min")
            price_max = context.input_data.get("price_max")
            max_candidates = context.input_data.get("max_candidates", 10)

            # Initialize source adapter if not provided
            if not self.source_adapter:
                settings = get_settings()
                if settings.use_real_scrapers:
                    if platform == SourcePlatform.TEMU:
                        from app.services.temu_adapter_v2 import TemuSourceAdapterV2

                        self.source_adapter = TemuSourceAdapterV2()
                        created_adapter = True
                    elif platform == SourcePlatform.ALIBABA_1688:
                        from app.services.alibaba_1688_adapter import Alibaba1688Adapter

                        self.source_adapter = Alibaba1688Adapter()
                        created_adapter = True
                    else:
                        self.source_adapter = MockSourceAdapter(platform)
                else:
                    self.source_adapter = MockSourceAdapter(platform)

            # Fetch products from source platform
            products = await self.source_adapter.fetch_products(
                category=category,
                keywords=keywords,
                price_min=Decimal(str(price_min)) if price_min else None,
                price_max=Decimal(str(price_max)) if price_max else None,
                limit=max_candidates,
                region=region,
            )

            self.logger.info(
                "products_fetched",
                count=len(products),
                platform=platform.value,
            )

            candidate_ids = []

            # Process each product
            for product in products:
                # Create candidate product record
                candidate = CandidateProduct(
                    id=uuid4(),
                    strategy_run_id=context.strategy_run_id,
                    source_platform=product.source_platform,
                    source_product_id=product.source_product_id,
                    source_url=product.source_url,
                    title=product.title,
                    raw_title=product.title,
                    category=product.category,
                    currency=product.currency,
                    platform_price=product.platform_price,
                    sales_count=product.sales_count,
                    rating=product.rating,
                    main_image_url=product.main_image_url,
                    raw_payload=product.raw_payload,
                    normalized_attributes=product.normalized_attributes,
                    status=CandidateStatus.DISCOVERED,
                )
                context.db.add(candidate)

                # Find suppliers, preferring source-provided supplier candidates
                suppliers = await self.supplier_matcher.find_suppliers(
                    product_title=product.title,
                    product_category=product.category,
                    limit=5,
                    source_platform=product.source_platform,
                    supplier_candidates=product.supplier_candidates,
                    raw_payload={
                        **(product.raw_payload or {}),
                        "source_url": product.source_url,
                        "source_product_id": product.source_product_id,
                    },
                )

                # Create supplier match records
                for supplier in suppliers:
                    supplier_match = SupplierMatch(
                        id=uuid4(),
                        candidate_product_id=candidate.id,
                        supplier_name=supplier.supplier_name,
                        supplier_url=supplier.supplier_url,
                        supplier_sku=supplier.supplier_sku,
                        supplier_price=supplier.supplier_price,
                        moq=supplier.moq,
                        confidence_score=supplier.confidence_score,
                        raw_payload=supplier.raw_payload,
                        selected=False,
                    )
                    # Explicitly set the relationship to avoid lazy loading during flush
                    supplier_match.candidate = candidate
                    context.db.add(supplier_match)

                candidate_ids.append(str(candidate.id))

            await context.db.commit()

            self.logger.info(
                "candidates_created",
                count=len(candidate_ids),
                strategy_run_id=str(context.strategy_run_id),
            )

            return AgentResult(
                success=True,
                output_data={
                    "candidate_ids": candidate_ids,
                    "count": len(candidate_ids),
                },
            )

        except Exception as e:
            await context.db.rollback()
            return await self._handle_error(e, context)
        finally:
            if created_adapter and hasattr(self.source_adapter, "close"):
                await self.source_adapter.close()
                self.source_adapter = None
