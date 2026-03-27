"""Product Selector Agent."""
from decimal import Decimal
from typing import Optional
from uuid import uuid4

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.core.config import get_settings
from app.core.enums import CandidateStatus, SourcePlatform
from app.core.seasonal_calendar import get_seasonal_calendar
from app.db.models import CandidateProduct, SupplierMatch
from app.services.demand_validator import DemandValidator
from app.services.product_scoring_service import ProductScoreInput, ProductScoringService
from app.services.source_adapter import MockSourceAdapter, SourceAdapter
from app.services.supplier_matcher import SupplierMatcherService


class ProductSelectorAgent(BaseAgent):
    """Agent for discovering candidate products.

    Phase 1 Enhancement: Added demand validation before product scraping.
    - Validates search volume (>500 monthly searches)
    - Checks competition density (avoid red ocean markets)
    - Assesses trend direction (avoid declining markets)

    Phase 4 Enhancement: Added seasonal boost for event-driven selection.
    - 90-day lookahead for upcoming events
    - Category-specific boost factors
    - Prioritizes products for upcoming holidays
    """

    def __init__(
        self,
        source_adapter: Optional[SourceAdapter] = None,
        supplier_matcher: Optional[SupplierMatcherService] = None,
        demand_validator: Optional[DemandValidator] = None,
        enable_demand_validation: bool = True,
        enable_seasonal_boost: bool = True,
    ):
        super().__init__("product_selector")
        self.source_adapter = source_adapter
        self.supplier_matcher = supplier_matcher or SupplierMatcherService()
        self.demand_validator = demand_validator or DemandValidator()
        self.enable_demand_validation = enable_demand_validation
        self.enable_seasonal_boost = enable_seasonal_boost

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute product selection with demand validation and seasonal boost.

        Phase 1 Enhancement: Validate demand before scraping to avoid wasting
        resources on low-demand or high-competition products.

        Phase 4 Enhancement: Apply seasonal boost to prioritize products for
        upcoming events (90-day lookahead).
        """
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

            # Phase 1: Demand validation (if enabled)
            validation_results = []
            validated_keywords = keywords
            if self.enable_demand_validation and keywords:
                self.logger.info(
                    "demand_validation_started",
                    keywords=keywords,
                    category=category,
                    region=region,
                )

                validation_results = await self.demand_validator.validate_batch(
                    keywords=keywords,
                    category=category,
                    region=region,
                )

                # Filter to only passed keywords
                validated_keywords = [
                    result.keyword
                    for result in validation_results
                    if result.passed
                ]

                failed_keywords = [
                    result.keyword
                    for result in validation_results
                    if not result.passed
                ]

                self.logger.info(
                    "demand_validation_completed",
                    total_keywords=len(keywords),
                    passed_keywords=len(validated_keywords),
                    failed_keywords=len(failed_keywords),
                    failed_list=failed_keywords,
                )

                # If all keywords failed validation, return early
                if not validated_keywords:
                    self.logger.warning(
                        "all_keywords_failed_validation",
                        keywords=keywords,
                        returning_empty=True,
                    )
                    return AgentResult(
                        success=True,
                        output_data={
                            "candidate_ids": [],
                            "count": 0,
                            "demand_validation_results": [r.to_dict() for r in validation_results],
                            "skipped_reason": "all_keywords_failed_demand_validation",
                        },
                    )

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

            # Fetch products from source platform (using validated keywords)
            products = await self.source_adapter.fetch_products(
                category=category,
                keywords=validated_keywords,
                price_min=Decimal(str(price_min)) if price_min else None,
                price_max=Decimal(str(price_max)) if price_max else None,
                limit=max_candidates,
                region=region,
            )

            self.logger.info(
                "products_fetched",
                count=len(products),
                platform=platform.value,
                validated_keywords=validated_keywords,
            )

            # Phase 4 Enhancement: Get seasonal boost factor
            seasonal_boost = 1.0
            if self.enable_seasonal_boost and category:
                calendar = get_seasonal_calendar(lookahead_days=90)
                seasonal_boost = calendar.get_boost_factor(category=category)

                self.logger.info(
                    "seasonal_boost_applied",
                    category=category,
                    boost_factor=seasonal_boost,
                    strategy_run_id=str(context.strategy_run_id),
                )

            # Phase 4 Enhancement: Sort products by priority score
            products_with_scores = []
            if products:
                products_with_scores = self._sort_products_by_priority(
                    products=products,
                    seasonal_boost=seasonal_boost,
                    validation_results=validation_results,
                )

                self.logger.info(
                    "products_sorted_by_priority",
                    count=len(products_with_scores),
                    top_product=products_with_scores[0][0].title if products_with_scores else None,
                    top_score=round(products_with_scores[0][1], 3) if products_with_scores else None,
                    strategy_run_id=str(context.strategy_run_id),
                )

            candidate_ids = []

            # Process each product
            for rank, (product, priority_score) in enumerate(products_with_scores, start=1):
                # Phase 1 Enhancement: Get competition density for this product
                competition_density = "unknown"
                if self.enable_demand_validation and validated_keywords:
                    # Try to find matching validation result
                    for result in validation_results:
                        if result.keyword in product.title.lower():
                            competition_density = result.competition_density.value
                            break

                # Merge competition density into normalized_attributes
                normalized_attributes = product.normalized_attributes or {}
                normalized_attributes["competition_density"] = competition_density

                # Phase 4 Enhancement: Add seasonal boost, priority score, and rank
                if self.enable_seasonal_boost:
                    normalized_attributes["seasonal_boost"] = seasonal_boost
                    normalized_attributes["priority_score"] = round(priority_score, 4)
                    normalized_attributes["priority_rank"] = rank

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
                    normalized_attributes=normalized_attributes,
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

    def _sort_products_by_priority(
        self,
        products: list,
        seasonal_boost: float,
        validation_results: list,
    ) -> list[tuple]:
        """按优先级分数排序产品.

        委托给 ProductScoringService 执行评分逻辑.

        Args:
            products: List of ProductData objects
            seasonal_boost: Seasonal boost factor for category
            validation_results: Demand validation results (for competition density)

        Returns:
            List of tuples: [(product, priority_score), ...]
            Sorted by priority score (highest first)
        """
        scoring_service = ProductScoringService()

        # 从验证结果构建竞争密度映射
        competition_map = {}
        for result in validation_results:
            competition_map[result.keyword.lower()] = result.competition_density.value

        def calculate_priority_score(product) -> float:
            """计算产品优先级分数."""
            # 查找匹配的竞争密度
            competition_density = "unknown"
            for keyword in competition_map:
                if keyword in product.title.lower():
                    competition_density = competition_map[keyword]
                    break

            # 委托给服务
            score_input = ProductScoreInput(
                title=product.title,
                sales_count=product.sales_count,
                rating=product.rating,
                seasonal_boost=seasonal_boost,
                competition_density=competition_density,
            )

            score_result = scoring_service.calculate_priority_score(score_input)
            return score_result.total_score

        # 计算分数并排序
        products_with_scores = [
            (product, calculate_priority_score(product)) for product in products
        ]

        # 按分数降序排序
        products_with_scores.sort(key=lambda x: x[1], reverse=True)

        # 记录 top 5 用于调试
        self.logger.debug(
            "product_priority_scores",
            top_5=[
                {
                    "title": p.title,
                    "score": round(score, 3),
                    "sales": p.sales_count,
                    "rating": float(p.rating) if p.rating else None,
                }
                for p, score in products_with_scores[:5]
            ],
        )

        return products_with_scores
