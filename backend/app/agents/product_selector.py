"""Product Selector Agent.

Seller-first refactor (Phase 1):
- For AlphaShop / 1688 platform: demand discovery produces search intelligence,
  which drives supply validation via the source adapter.
- `newproduct.report.product_list` remains an optional enhancement source and is
  merged with supply-validation products before downstream scoring.
- For other platforms: source adapter fetch_products is used with validated
  keywords as before.
- All candidates retain provenance in demand_discovery_metadata and
  normalized_attributes.
"""
from decimal import Decimal
import re
from typing import Any, Optional
from uuid import uuid4

from app.agents.base.agent import AgentContext, AgentResult, BaseAgent
from app.core.config import get_settings
from app.core.enums import CandidateStatus, SourcePlatform
from app.core.seasonal_calendar import get_seasonal_calendar
from app.db.models import CandidateProduct, SupplierMatch
from app.services.demand_discovery_service import DemandDiscoveryService
from app.services.demand_validator import DemandValidator
from app.services.opportunity_discovery_service import OpportunityDiscoveryService, OpportunityDraft
from app.services.product_scoring_service import ProductScoreInput, ProductScoringService
from app.services.source_adapter import MockSourceAdapter, ProductData, SourceAdapter
from app.services.supplier_matcher import SupplierMatcherService


class ProductSelectorAgent(BaseAgent):
    """Agent for discovering candidate products.

    Seller-first selection flow:
    - All 1688 searches must go through demand discovery first
    - User/category inputs are normalized into strict search intelligence
    - Search intelligence drives supply validation as the primary candidate path
    - Opportunity products are optional enhancement inputs, not a hard gate

    Seasonal enhancement:
    - 90-day lookahead for upcoming events
    - Category-specific boost factors
    - Prioritizes products for upcoming holidays
    - Skips cleanly when no validated keywords are available
    """

    def __init__(
        self,
        source_adapter: Optional[SourceAdapter] = None,
        supplier_matcher: Optional[SupplierMatcherService] = None,
        demand_validator: Optional[DemandValidator] = None,
        demand_discovery_service: Optional[DemandDiscoveryService] = None,
        opportunity_discovery_service: Optional[OpportunityDiscoveryService] = None,
        enable_demand_validation: bool = True,
        enable_seasonal_boost: bool = True,
    ):
        super().__init__("product_selector")
        self.settings = get_settings().model_copy(deep=True)
        self.source_adapter = source_adapter
        self.supplier_matcher = supplier_matcher or SupplierMatcherService()
        self.demand_validator = demand_validator or DemandValidator(
            min_search_volume=self.settings.demand_validation_min_search_volume,
            use_helium10=self.settings.demand_validation_use_helium10,
            helium10_api_key=self.settings.demand_validation_helium10_api_key or None,
            cache_ttl_seconds=self.settings.demand_validation_cache_ttl_seconds,
            enable_cache=self.settings.enable_demand_validation,
        )
        self.demand_discovery_service = demand_discovery_service or DemandDiscoveryService(
            demand_validator=self.demand_validator,
        )
        self.opportunity_discovery_service = opportunity_discovery_service or OpportunityDiscoveryService()
        self.enable_demand_validation = enable_demand_validation
        self.enable_seasonal_boost = enable_seasonal_boost
        self.require_demand_discovery = (
            self.settings.product_selection_require_demand_discovery and enable_demand_validation
        )

    async def execute(self, context: AgentContext) -> AgentResult:
        """Execute product selection with demand discovery and seasonal boost."""
        created_adapter = False

        try:
            # Extract input parameters
            platform = SourcePlatform(context.input_data.get("platform", "temu"))
            category = context.input_data.get("category")
            keywords = context.input_data.get("keywords") or []
            region = context.input_data.get("region")
            price_min = context.input_data.get("price_min")
            price_max = context.input_data.get("price_max")
            max_candidates = context.input_data.get("max_candidates", 10)

            demand_discovery_payload = None
            validation_results = []
            validated_keywords = keywords
            skipped_reason = None
            opportunities = []

            # Seller-first keyword discovery
            if self.require_demand_discovery:
                discovery_result = await self.demand_discovery_service.discover_keywords(
                    category=category,
                    keywords=keywords,
                    region=region,
                    platform=platform.value,
                    max_keywords=max_candidates,
                )
                demand_discovery_payload = discovery_result.to_dict()
                validated_keywords = [item.keyword for item in discovery_result.validated_keywords]
                validation_results = [
                    item.validation
                    for item in (discovery_result.validated_keywords + discovery_result.rejected_keywords)
                    if item.validation is not None
                ]

                self.logger.info(
                    "demand_discovery_completed",
                    strategy_run_id=str(context.strategy_run_id),
                    category=category,
                    region=region,
                    platform=platform.value,
                    discovery_mode=discovery_result.discovery_mode,
                    validated=len(discovery_result.validated_keywords),
                    rejected=len(discovery_result.rejected_keywords),
                    fallback_used=discovery_result.fallback_used,
                    degraded=discovery_result.degraded,
                )

                # Opportunity discovery (Phase 1: optional enhancement for 1688)
                if validated_keywords and discovery_result.valid_keywords:
                    try:
                        from app.services.keyword_legitimizer import ValidKeyword
                        from app.services.seed_pool_builder import Seed

                        # Reconstruct ValidKeyword objects from metadata
                        valid_keyword_objects: list[ValidKeyword] = []
                        for vk_dict in discovery_result.valid_keywords:
                            if not vk_dict.get("is_valid_for_report"):
                                continue
                            seed_dict = vk_dict.get("seed") or {}
                            seed = Seed(
                                term=seed_dict.get("term", ""),
                                source=seed_dict.get("source", "unknown"),
                                confidence=seed_dict.get("confidence", 0.0),
                                category=seed_dict.get("category"),
                                region=seed_dict.get("region"),
                                platform=seed_dict.get("platform"),
                            )
                            valid_kw = ValidKeyword(
                                seed=seed,
                                matched_keyword=vk_dict.get("matched_keyword", ""),
                                match_type=vk_dict.get("match_type", "unknown"),
                                opp_score=vk_dict.get("opp_score"),
                                search_volume=vk_dict.get("search_volume"),
                                competition_density=vk_dict.get("competition_density", "unknown"),
                                is_valid_for_report=vk_dict.get("is_valid_for_report", False),
                                raw=vk_dict.get("raw", {}),
                                report_keyword=vk_dict.get("report_keyword"),
                                keyword_cn=vk_dict.get("keyword_cn"),
                                sold_cnt_30d=vk_dict.get("sold_cnt_30d"),
                                sold_amt_30d=vk_dict.get("sold_amt_30d"),
                                search_rank=vk_dict.get("search_rank"),
                                growth_rate=vk_dict.get("growth_rate"),
                                rank_trends=vk_dict.get("rank_trends"),
                                radar_scores=vk_dict.get("radar_scores"),
                            )
                            valid_keyword_objects.append(valid_kw)

                        if valid_keyword_objects:
                            from app.services.demand_discovery_service import map_business_platform_to_alphashop

                            opportunities = await self.opportunity_discovery_service.discover_opportunities(
                                valid_keywords=valid_keyword_objects,
                                region=region or "US",
                                platform=map_business_platform_to_alphashop(platform.value),
                                max_reports=3,
                                report_size=5,
                            )
                            self.logger.info(
                                "opportunity_discovery_integration_completed",
                                strategy_run_id=str(context.strategy_run_id),
                                opportunities_found=len(opportunities),
                                valid_keywords_input=len(valid_keyword_objects),
                                discovery_success_rate=round(len(opportunities) / len(valid_keyword_objects), 3) if valid_keyword_objects else 0.0,
                            )
                        else:
                            self.logger.info(
                                "opportunity_discovery_skipped",
                                strategy_run_id=str(context.strategy_run_id),
                                reason="no_report_safe_keywords",
                            )
                    except Exception as exc:
                        self.logger.warning(
                            "opportunity_discovery_integration_failed",
                            strategy_run_id=str(context.strategy_run_id),
                            error=str(exc),
                            error_type=type(exc).__name__,
                        )

                if not validated_keywords:
                    self.logger.warning(
                        "no_validated_keywords_available",
                        strategy_run_id=str(context.strategy_run_id),
                        category=category,
                        region=region,
                        platform=platform.value,
                    )
                    self.logger.info(
                        "product_selection_metrics",
                        strategy_run_id=str(context.strategy_run_id),
                        category=category,
                        region=region,
                        platform=platform.value,
                        discovery_mode=discovery_result.discovery_mode,
                        skipped=True,
                        skip_rate=1.0,
                        selection_triggered_per_category=0,
                        candidate_count_per_discovery_mode=0,
                        validated_keywords_count=len(discovery_result.validated_keywords),
                    )
                    skipped_reason = "no_validated_keywords_available"
                    output_data = {
                        "candidate_ids": [],
                        "count": 0,
                        "skipped_reason": skipped_reason,
                    }
                    if demand_discovery_payload is not None:
                        output_data["demand_discovery"] = demand_discovery_payload
                    return AgentResult(success=True, output_data=output_data)

            # Initialize source adapter if not provided
            if not self.source_adapter:
                if self.settings.use_real_scrapers:
                    if platform == SourcePlatform.TEMU:
                        from app.services.temu_adapter_v2 import TemuSourceAdapterV2

                        self.source_adapter = TemuSourceAdapterV2()
                        created_adapter = True
                    elif platform == SourcePlatform.ALIBABA_1688:
                        # For AlphaShop seller-first path, the adapter handles
                        # supply validation and can also normalize opportunity report items.
                        from app.services.alphashop_1688_adapter import AlphaShop1688Adapter

                        self.source_adapter = AlphaShop1688Adapter()
                        created_adapter = True
                    else:
                        self.source_adapter = MockSourceAdapter(platform)
                else:
                    self.source_adapter = MockSourceAdapter(platform)

            # Fetch products from source platform
            # Seller-first approach for AlphaShop/1688:
            # - Primary: supply validation via search intelligence (keywordCn)
            # - Enhancement: opportunity products from newproduct.report (if available)
            if platform == SourcePlatform.ALIBABA_1688:
                products = []

                # 1. Opportunity products (optional enhancement)
                if opportunities:
                    if isinstance(self.source_adapter, SourceAdapter) and hasattr(
                        self.source_adapter, "normalize_report_products"
                    ):
                        opportunity_products = self.source_adapter.normalize_report_products(
                            opportunities=[opp.to_dict() for opp in opportunities],
                            price_min=Decimal(str(price_min)) if price_min else None,
                            price_max=Decimal(str(price_max)) if price_max else None,
                            limit=max_candidates * 2,
                        )
                    else:
                        opportunity_products = self._normalize_opportunity_products(
                            opportunities=opportunities,
                            price_min=Decimal(str(price_min)) if price_min else None,
                            price_max=Decimal(str(price_max)) if price_max else None,
                            limit=max_candidates * 2,
                        )
                    products.extend(opportunity_products)
                    self.logger.info(
                        "products_from_opportunities",
                        count=len(opportunity_products),
                        platform=platform.value,
                        opportunities_count=len(opportunities),
                        strategy_run_id=str(context.strategy_run_id),
                    )

                # 2. Supply validation via search intelligence (primary path)
                supply_queries = self._build_supply_queries_from_search_intelligence(
                    demand_discovery_payload or {}
                )
                if supply_queries:
                    supply_products = await self.source_adapter.fetch_products(
                        category=category,
                        keywords=supply_queries,
                        price_min=Decimal(str(price_min)) if price_min else None,
                        price_max=Decimal(str(price_max)) if price_max else None,
                        limit=max_candidates * 2,
                        region=region,
                    )
                    products.extend(supply_products)
                    self.logger.info(
                        "products_from_search_intelligence_supply_validation",
                        count=len(supply_products),
                        supply_queries=supply_queries,
                        platform=platform.value,
                        strategy_run_id=str(context.strategy_run_id),
                    )

                # Deduplicate by source_product_id
                seen_ids: set[str] = set()
                deduplicated_products: list[ProductData] = []
                for product in products:
                    if product.source_product_id not in seen_ids:
                        seen_ids.add(product.source_product_id)
                        deduplicated_products.append(product)
                products = deduplicated_products

                self.logger.info(
                    "products_merged_for_1688",
                    total_count=len(products),
                    platform=platform.value,
                    strategy_run_id=str(context.strategy_run_id),
                )

                if not products:
                    self.logger.warning(
                        "no_supply_candidates_available",
                        strategy_run_id=str(context.strategy_run_id),
                        platform=platform.value,
                        validated_keywords_count=len(validated_keywords),
                        opportunities_count=len(opportunities),
                    )
                    skipped_reason = "no_supply_candidates_available"
                    output_data = {
                        "candidate_ids": [],
                        "count": 0,
                        "skipped_reason": skipped_reason,
                    }
                    if demand_discovery_payload is not None:
                        output_data["demand_discovery"] = demand_discovery_payload
                    return AgentResult(success=True, output_data=output_data)
            else:
                # For non-1688 platforms, use traditional adapter fetch
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
                    strategy_run_id=str(context.strategy_run_id),
                )

            # Seasonal boost factor
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

            # Strict opportunity relevance filtering for AlphaShop/1688
            if platform == SourcePlatform.ALIBABA_1688 and products:
                products = self._filter_products_by_opportunity_relevance(
                    products=products,
                    opportunities=opportunities,
                    discovery_mode=(demand_discovery_payload or {}).get("discovery_mode"),
                    limit=max_candidates * 2,
                )
                self.logger.info(
                    "products_filtered_by_opportunity_relevance",
                    count=len(products),
                    platform=platform.value,
                    strategy_run_id=str(context.strategy_run_id),
                )

                if not products:
                    return AgentResult(
                        success=False,
                        error_message="No relevant products remained after strict opportunity relevance filtering.",
                        output_data={
                            "candidate_ids": [],
                            "count": 0,
                            "skipped_reason": "no_relevant_products_after_opportunity_filter",
                            "demand_discovery": demand_discovery_payload,
                        },
                    )

            # Sort products by priority score
            products_with_scores = []
            if products:
                products_with_scores = self._sort_products_by_priority(
                    products=products,
                    seasonal_boost=seasonal_boost,
                    validation_results=validation_results,
                )

                # Apply diversity constraints after scoring
                if platform == SourcePlatform.ALIBABA_1688:
                    products_with_scores = self._apply_product_diversity_constraints(
                        products_with_scores=products_with_scores,
                        max_candidates=max_candidates,
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
                competition_density = "unknown"
                if validation_results:
                    for result in validation_results:
                        if result.keyword.lower() in product.title.lower():
                            competition_density = result.competition_density.value
                            break

                normalized_attributes = dict(product.normalized_attributes or {})
                normalized_attributes["competition_density"] = competition_density

                if platform == SourcePlatform.ALIBABA_1688 and demand_discovery_payload:
                    search_intelligence = self._match_search_intelligence_for_product(
                        product=product,
                        demand_discovery_payload=demand_discovery_payload,
                    )
                    if search_intelligence:
                        normalized_attributes["search_intelligence"] = search_intelligence
                        normalized_attributes.setdefault(
                            "matched_keyword", search_intelligence.get("matched_keyword")
                        )
                        normalized_attributes.setdefault(
                            "report_keyword", search_intelligence.get("report_keyword")
                        )
                        if search_intelligence.get("keyword_cn"):
                            normalized_attributes["supply_query"] = search_intelligence.get("keyword_cn")

                opportunity_provenance = normalized_attributes.get("opportunity_provenance")
                if opportunity_provenance:
                    normalized_attributes["opportunity_keyword"] = opportunity_provenance.get("keyword")
                    normalized_attributes["opportunity_score"] = opportunity_provenance.get("opportunity_score")
                    normalized_attributes["opportunity_title"] = opportunity_provenance.get("title")

                if self.enable_seasonal_boost:
                    normalized_attributes["seasonal_boost"] = seasonal_boost
                    normalized_attributes["priority_score"] = round(priority_score, 4)
                    normalized_attributes["priority_rank"] = rank

                # Build demand discovery metadata
                demand_metadata = None
                if demand_discovery_payload:
                    demand_metadata = {**demand_discovery_payload}
                    if opportunity_provenance:
                        demand_metadata["opportunity"] = opportunity_provenance
                    if opportunities:
                        demand_metadata["opportunities"] = [opp.to_dict() for opp in opportunities]
                    if skipped_reason:
                        demand_metadata["skipped_reason"] = skipped_reason

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
                    demand_discovery_metadata=demand_metadata,
                    status=CandidateStatus.DISCOVERED,
                )
                context.db.add(candidate)

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
                    supplier_match.candidate = candidate
                    context.db.add(supplier_match)

                candidate_ids.append(str(candidate.id))

            await context.db.commit()

            self.logger.info(
                "candidates_created",
                count=len(candidate_ids),
                strategy_run_id=str(context.strategy_run_id),
            )
            self.logger.info(
                "product_selection_metrics",
                strategy_run_id=str(context.strategy_run_id),
                category=category,
                region=region,
                platform=platform.value,
                discovery_mode=demand_discovery_payload["discovery_mode"] if demand_discovery_payload else "direct",
                skipped=False,
                skip_rate=0.0,
                selection_triggered_per_category=1,
                candidate_count_per_discovery_mode=len(candidate_ids),
                validated_keywords_count=len(validated_keywords),
            )

            output_data = {
                "candidate_ids": candidate_ids,
                "count": len(candidate_ids),
            }
            if demand_discovery_payload is not None:
                output_data["demand_discovery"] = demand_discovery_payload

            return AgentResult(success=True, output_data=output_data)

        except Exception as e:
            await context.db.rollback()
            return await self._handle_error(e, context)
        finally:
            if created_adapter and hasattr(self.source_adapter, "close"):
                await self.source_adapter.close()
                self.source_adapter = None

    def _match_search_intelligence_for_product(
        self,
        *,
        product: ProductData,
        demand_discovery_payload: dict[str, Any],
    ) -> Optional[dict[str, Any]]:
        """Match product to its source search intelligence metadata.

        Uses matched_keyword from product normalized_attributes to find the
        corresponding valid_keyword entry in demand_discovery_payload.
        """
        matched_keyword = (product.normalized_attributes or {}).get("matched_keyword")
        if not matched_keyword:
            return None

        normalized_query = matched_keyword.lower().strip()
        for item in demand_discovery_payload.get("valid_keywords") or []:
            for candidate_key in ("keyword_cn", "report_keyword", "matched_keyword"):
                candidate = (item.get(candidate_key) or "").strip()
                if candidate.lower() == normalized_query:
                    return item
        return None

    def _build_supply_queries_from_search_intelligence(self, demand_discovery_payload: dict[str, Any]) -> list[str]:
        """Build 1688 supply queries from search intelligence.

        Prefer `keyword_cn` because it is the strongest bridge from market
        intelligence to 1688 supplier recall. Fall back to report/matched keyword
        only when a stronger query is unavailable for that intelligence item.
        """
        queries: list[str] = []
        seen: set[str] = set()

        for item in demand_discovery_payload.get("valid_keywords") or []:
            selected_query = None
            for candidate in (
                item.get("keyword_cn"),
                item.get("report_keyword"),
                item.get("matched_keyword"),
            ):
                query = (candidate or "").strip()
                normalized = query.lower()
                if not query or normalized in seen:
                    continue
                selected_query = query
                seen.add(normalized)
                break

            if selected_query:
                queries.append(selected_query)

        return queries

    def _normalize_opportunity_products(
        self,
        opportunities: list[OpportunityDraft],
        price_min: Optional[Decimal] = None,
        price_max: Optional[Decimal] = None,
        limit: int = 10,
    ) -> list[ProductData]:
        """Convert AlphaShop opportunity report items into ProductData candidates.

        Applies price filtering and limit to match source adapter behavior.
        """
        products: list[ProductData] = []
        seen_product_ids: set[str] = set()

        for opportunity in opportunities:
            if len(products) >= limit:
                break

            opportunity_dict = opportunity.to_dict()
            for item in opportunity.product_list:
                if len(products) >= limit:
                    break

                product = self._normalize_opportunity_product(
                    item=item,
                    opportunity=opportunity_dict,
                )
                if not product:
                    continue
                if product.source_product_id in seen_product_ids:
                    continue

                # Apply price filtering
                if price_min is not None and product.platform_price is not None:
                    if product.platform_price < price_min:
                        continue
                if price_max is not None and product.platform_price is not None:
                    if product.platform_price > price_max:
                        continue

                seen_product_ids.add(product.source_product_id)
                products.append(product)

        return products

    def _normalize_opportunity_product(
        self,
        *,
        item: dict[str, Any],
        opportunity: dict[str, Any],
    ) -> ProductData | None:
        """Convert a single newproduct.report item into ProductData."""
        source_product_id = self._extract_opportunity_product_id(item)
        title = self._extract_opportunity_product_title(item)
        if not source_product_id or not title:
            return None

        source_url = self._extract_opportunity_product_url(item, source_product_id)
        platform_price = self._extract_opportunity_product_price(item)
        sales_count = self._extract_opportunity_product_sales(item)
        main_image_url = self._extract_opportunity_product_image(item)
        category = self._extract_opportunity_product_category(item)

        normalized_attributes = {
            "matched_keyword": opportunity.get("keyword"),
            "report_keyword": (opportunity.get("evidence") or {}).get("report_keyword"),
            "opportunity_provenance": {
                "keyword": opportunity.get("keyword"),
                "title": opportunity.get("title"),
                "opportunity_score": opportunity.get("opportunity_score"),
                "keyword_summary": opportunity.get("keyword_summary"),
                "evidence": opportunity.get("evidence"),
            },
            "report_item_id": source_product_id,
        }

        return ProductData(
            source_platform=SourcePlatform.ALIBABA_1688,
            source_product_id=source_product_id,
            source_url=source_url,
            title=title,
            category=category,
            currency="USD",
            platform_price=platform_price,
            sales_count=sales_count,
            rating=None,
            main_image_url=main_image_url,
            raw_payload={
                "opportunity": opportunity,
                "alphashop_report_item": item,
            },
            normalized_attributes=normalized_attributes,
            supplier_candidates=[],
        )

    def _extract_opportunity_product_id(self, item: dict[str, Any]) -> str | None:
        """Extract stable product identifier from newproduct.report item."""
        for key in ("productId", "itemId", "offerId", "id"):
            value = item.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    def _extract_opportunity_product_title(self, item: dict[str, Any]) -> str:
        """Extract title from newproduct.report item."""
        for key in ("title", "productTitle", "name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return ""

    def _extract_opportunity_product_url(self, item: dict[str, Any], source_product_id: str) -> str:
        """Extract detail URL from newproduct.report item."""
        for key in ("detailUrl", "productUrl", "offerDetailUrl", "url"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return f"https://detail.1688.com/offer/{source_product_id}.html"

    def _extract_opportunity_product_image(self, item: dict[str, Any]) -> str | None:
        """Extract primary image URL from newproduct.report item."""
        for key in ("imageUrl", "mainImageUrl", "productImage"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

        image_urls = item.get("imageUrls")
        if isinstance(image_urls, list):
            for value in image_urls:
                if isinstance(value, str) and value.strip():
                    return value.strip()
        return None

    def _extract_opportunity_product_category(self, item: dict[str, Any]) -> str | None:
        """Extract category from newproduct.report item when available."""
        for key in ("category", "categoryName", "category_name"):
            value = item.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _extract_opportunity_product_price(self, item: dict[str, Any]) -> Decimal | None:
        """Extract platform price from newproduct.report item.

        Priority:
        1. spInfo.spPriceMin/Max midpoint (target platform selling price in USD)
        2. Fallback to top-level price field (legacy compatibility)

        Note: spItmMidPrice is 1688 supplier price (CNY), NOT target platform price.
        """
        # Try spInfo price range first (recommended)
        sp_info = item.get("spInfo", {})
        min_price_obj = sp_info.get("spPriceMin", {}).get("value", {})
        max_price_obj = sp_info.get("spPriceMax", {}).get("value", {})

        min_price = self._coerce_decimal(min_price_obj.get("amount"))
        max_price = self._coerce_decimal(max_price_obj.get("amount"))

        # Use midpoint of min/max range as target selling price
        if min_price is not None and max_price is not None:
            return (min_price + max_price) / Decimal("2")
        elif min_price is not None:
            return min_price
        elif max_price is not None:
            return max_price

        # Fallback to legacy price field
        value = item.get("price")
        if isinstance(value, dict):
            value = value.get("price") or value.get("amount")
        return self._coerce_decimal(value)

    def _extract_opportunity_product_sales(self, item: dict[str, Any]) -> int | None:
        """Extract sales count from newproduct.report item."""
        for key in ("salesCount", "sales", "orderCount"):
            value = self._coerce_int(item.get(key))
            if value is not None:
                return value
        return None

    def _coerce_decimal(self, value: Any) -> Decimal | None:
        """Convert arbitrary value to Decimal."""
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

    def _coerce_int(self, value: Any) -> int | None:
        """Convert arbitrary value to int."""
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

    def _sort_products_by_priority(
        self,
        products: list,
        seasonal_boost: float,
        validation_results: list,
    ) -> list[tuple]:
        """按优先级分数排序产品.

        增强版排序：在原有销量/评分/季节性基础上，加入
        - opportunity score
        - keyword relevance
        - exploration 模式服饰惩罚
        """
        scoring_service = ProductScoringService()

        competition_map = {}
        for result in validation_results:
            competition_map[result.keyword.lower()] = result.competition_density.value

        def calculate_priority_score(product) -> float:
            competition_density = "unknown"
            for keyword in competition_map:
                if keyword in product.title.lower():
                    competition_density = competition_map[keyword]
                    break

            score_input = ProductScoreInput(
                title=product.title,
                sales_count=product.sales_count,
                rating=product.rating,
                seasonal_boost=seasonal_boost,
                competition_density=competition_density,
            )

            base_score = scoring_service.calculate_priority_score(score_input).total_score

            normalized_attributes = dict(product.normalized_attributes or {})
            opportunity_provenance = normalized_attributes.get("opportunity_provenance") or {}
            relevance_score = self._calculate_product_relevance_score(product)
            opportunity_score = self._safe_float(opportunity_provenance.get("opportunity_score"))
            opportunity_component = min(opportunity_score / 100.0, 1.0) * 0.25 if opportunity_score is not None else 0.0
            relevance_component = relevance_score * 0.35
            apparel_penalty = self._get_exploration_apparel_penalty(product)

            return base_score + opportunity_component + relevance_component + apparel_penalty

        products_with_scores = [
            (product, calculate_priority_score(product)) for product in products
        ]
        products_with_scores.sort(key=lambda x: x[1], reverse=True)

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

    def _filter_products_by_opportunity_relevance(
        self,
        *,
        products: list[ProductData],
        opportunities: list[OpportunityDraft],
        discovery_mode: Optional[str],
        limit: int,
    ) -> list[ProductData]:
        """Filter products strictly by opportunity relevance.

        Supply-only products (without opportunity_provenance) are exempt from
        the strict threshold since they were already validated by 1688 recall.
        """
        filtered: list[ProductData] = []
        for product in products:
            normalized_attributes = dict(product.normalized_attributes or {})
            opportunity_provenance = normalized_attributes.get("opportunity_provenance")

            # Supply-only products: skip strict threshold, already validated by recall
            if not opportunity_provenance and normalized_attributes.get("matched_keyword"):
                filtered.append(product)
                if len(filtered) >= limit:
                    break
                continue

            # Opportunity products: apply strict relevance threshold
            relevance_score = self._calculate_product_relevance_score(product)
            if relevance_score < 0.2:
                continue
            if discovery_mode == "exploration" and self._is_apparel_product(product) and relevance_score < 0.5:
                continue
            filtered.append(product)
            if len(filtered) >= limit:
                break
        return filtered

    def _calculate_product_relevance_score(self, product: ProductData) -> float:
        """Calculate strict relevance between product and opportunity keyword."""
        normalized_attributes = dict(product.normalized_attributes or {})
        opportunity_provenance = normalized_attributes.get("opportunity_provenance") or {}
        keyword = (opportunity_provenance.get("keyword") or normalized_attributes.get("matched_keyword") or "").strip().lower()
        report_keyword = (normalized_attributes.get("report_keyword") or "").strip().lower()
        title = (product.title or "").strip().lower()
        category = (product.category or "").strip().lower()

        if not title:
            return 0.0

        keyword_tokens = self._tokenize_text(keyword)
        report_tokens = self._tokenize_text(report_keyword)
        title_tokens = self._tokenize_text(title)
        category_tokens = self._tokenize_text(category)
        expected_tokens = keyword_tokens | report_tokens
        if not expected_tokens:
            return 0.0

        title_overlap = len(expected_tokens & title_tokens) / len(expected_tokens)
        category_overlap = len(expected_tokens & category_tokens) / len(expected_tokens) if category_tokens else 0.0
        exact_phrase_bonus = 0.25 if keyword and keyword in title else 0.0
        report_phrase_bonus = 0.25 if report_keyword and report_keyword in title else 0.0

        return min(1.0, title_overlap * 0.7 + category_overlap * 0.2 + exact_phrase_bonus + report_phrase_bonus)

    def _apply_product_diversity_constraints(
        self,
        *,
        products_with_scores: list[tuple],
        max_candidates: int,
    ) -> list[tuple]:
        """Apply diversity constraints to avoid single-category collapse."""
        selected: list[tuple] = []
        category_counts: dict[str, int] = {}
        title_fingerprints: set[str] = set()

        for product, score in products_with_scores:
            category_key = (product.category or "unknown").strip().lower()
            if category_counts.get(category_key, 0) >= 3:
                continue

            fingerprint = self._fingerprint_title(product.title)
            if fingerprint in title_fingerprints:
                continue

            category_counts[category_key] = category_counts.get(category_key, 0) + 1
            title_fingerprints.add(fingerprint)
            selected.append((product, score))

            if len(selected) >= max_candidates:
                break

        return selected

    def _get_exploration_apparel_penalty(self, product: ProductData) -> float:
        """Penalize apparel in exploration mode unless strongly relevant."""
        normalized_attributes = dict(product.normalized_attributes or {})
        opportunity_provenance = normalized_attributes.get("opportunity_provenance") or {}
        discovery_hint = opportunity_provenance.get("evidence", {}).get("seed", {}).get("source")
        if discovery_hint != "trend" and discovery_hint != "supply":
            return 0.0
        if self._is_apparel_product(product):
            return -0.2
        return 0.0

    def _is_apparel_product(self, product: ProductData) -> bool:
        text = f"{product.title or ''} {(product.category or '')}".lower()
        apparel_terms = {
            "hoodie", "hoodies", "sweatshirt", "sweatshirts", "shirt", "shirts",
            "t-shirt", "tee", "tees", "jacket", "jackets", "coat", "coats",
            "dress", "dresses", "pants", "jeans", "shorts", "skirt", "apparel",
            "clothing", "fashion", "wear", "卫衣", "服装", "上衣"
        }
        return any(term in text for term in apparel_terms)

    def _tokenize_text(self, text: str) -> set[str]:
        return {token for token in re.split(r"[^a-z0-9\u4e00-\u9fff]+", text.lower()) if token and len(token) >= 2}

    def _fingerprint_title(self, title: str) -> str:
        tokens = sorted(self._tokenize_text(title))
        return " ".join(tokens[:8])

    def _safe_float(self, value: Any) -> float | None:
        if value is None:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
