"""1688 source adapter built on TMAPI 1688 endpoints.

Business flow:
- Stage A: build search seeds from explicit keywords, category, or cold-start seeds
- Stage B: multi-lane recall via keyword, sales, factory, and image-similar lanes
- Stage C: shortlist enrichment via detail, desc, ratings, shop info, and shop items
- Stage D: optional shipping enrichment via province mapping

The adapter keeps the existing SourceAdapter.fetch_products(...) boundary intact while
moving business strategy into a TMAPI-oriented, selection-focused orchestration layer.
"""
from __future__ import annotations

from datetime import UTC, datetime
import re
import unicodedata
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from app.clients.sglang import SGLangClient
from app.core.config import get_settings
from app.core.enums import SourcePlatform
from app.core.logging import get_logger
from app.services.feedback_aggregator import FeedbackAggregator
from app.services.source_adapter import ProductData, SourceAdapter
from app.services.tmapi_1688_client import TMAPI1688Client


@dataclass
class SearchSeed:
    """Search seed used to drive recall lanes."""

    keyword: str
    seed_type: str
    source_keyword: str | None = None


@dataclass
class Alibaba1688Candidate:
    """Normalized internal 1688 candidate structure used before ProductData mapping."""

    item_id: str
    title: str
    category_name: str | None = None
    detail_url: str | None = None
    main_image_url: str | None = None
    image_urls: list[str] = field(default_factory=list)
    detail_image_urls: list[str] = field(default_factory=list)
    price_cny_min: Decimal | None = None
    price_cny_max: Decimal | None = None
    sales_count: int | None = None
    moq: int | None = None
    member_id: str | None = None
    seller_id: str | None = None
    shop_url: str | None = None
    shop_name: str | None = None
    company_name: str | None = None
    location_str: str | None = None
    support_dropshipping: bool = False
    verified_supplier: bool = False
    is_factory_result: bool = False
    is_super_factory: bool = False
    matched_keyword: str | None = None
    seed_type: str | None = None
    detail_enriched: bool = False
    description_enriched: bool = False
    freight_cny: Decimal | None = None
    shipping_province: str | None = None
    shop_item_count: int | None = None
    rating: Decimal | None = None
    review_count: int | None = None
    review_sample: list[str] = field(default_factory=list)
    review_defect_flags: dict[str, int] = field(default_factory=dict)
    review_risk_score: float = 0.0
    shop_focus_ratio: float | None = None
    shop_intelligence_score: float = 0.0
    historical_seed_prior: float = 0.0
    historical_shop_prior: float = 0.0
    historical_supplier_prior: float = 0.0
    historical_feedback_score: float = 0.0
    source_endpoints: list[str] = field(default_factory=list)
    raw_payload: dict[str, Any] = field(default_factory=dict)
    discovery_score: float = 0.0
    business_score: float = 0.0
    final_score: float = 0.0


class Alibaba1688Adapter(SourceAdapter):
    """1688 product discovery adapter using TMAPI 1688 endpoints."""

    CNY_TO_USD_RATE = Decimal("0.14")
    CATEGORY_HOTWORD_MAP: dict[str, list[str]] = {
        "手机配件": ["磁吸手机壳", "支架手机壳", "防摔手机壳", "镜头膜"],
        "家居收纳": ["桌面收纳", "抽屉分隔盒", "厨房收纳架", "衣柜收纳盒"],
        "小家电": ["便携风扇", "桌面风扇", "迷你加湿器", "车载风扇"],
        "服饰配件": ["发夹", "项链", "耳饰", "丝巾"],
        "美妆工具": ["化妆刷", "粉扑", "收纳化妆包", "美甲工具"],
        "宠物用品": ["宠物牵引绳", "宠物玩具", "宠物凉垫", "宠物食盆"],
        "户外用品": ["露营灯", "折叠收纳箱", "野餐垫", "保温杯"],
        "办公文教": ["桌面摆件", "便签贴", "笔袋", "文件收纳"],
    }
    CATEGORY_HOTWORD_FALLBACKS: tuple[tuple[str, list[str]], ...] = (
        ("手机", ["磁吸", "防摔", "支架", "镜头保护"]),
        ("收纳", ["桌面", "抽屉", "分层", "折叠"]),
        ("风扇", ["便携", "桌面", "静音", "usb"]),
        ("宠物", ["凉垫", "玩具", "食盆", "外出"]),
        ("美妆", ["化妆刷", "粉扑", "收纳", "便携"]),
        ("服饰", ["发夹", "耳饰", "项链", "丝巾"]),
    )
    SEASONAL_SEED_MAP: dict[str, list[str]] = {
        "spring": ["春季新品", "防晒用品", "露营好物", "收纳换季"],
        "summer": ["夏季新品", "便携风扇", "防晒冰袖", "清凉家居"],
        "autumn": ["秋季新品", "开学用品", "保温杯", "居家收纳"],
        "winter": ["冬季新品", "保暖用品", "节庆礼品", "加热小家电"],
    }
    SEED_PRIORITY: dict[str, int] = {
        "historical": 8,
        "explicit": 7,
        "category": 6,
        "category_hotword": 5,
        "seasonal": 4,
        "llm": 3,
        "image": 2,
        "cold_start": 1,
    }
    REVIEW_DEFECT_KEYWORDS: dict[str, list[str]] = {
        "quality": [
            "质量差", "质量不好", "质量问题", "做工差", "做工粗糙", "粗制滥造",
            "容易坏", "不耐用", "用不了", "坏了", "有瑕疵", "有缺陷",
            "假货", "仿品", "山寨", "不是正品", "货不对板",
        ],
        "logistics": [
            "发货慢", "物流慢", "迟迟不发货", "等了很久", "催了好几次",
            "包装差", "包装破损", "快递暴力", "运输损坏",
        ],
        "sizing": [
            "尺寸不对", "尺码不准", "偏大", "偏小", "太大", "太小",
            "与描述不符", "图片不符", "实物不符",
        ],
        "odor": [
            "有异味", "味道大", "刺鼻", "臭", "难闻", "气味重",
            "甲醛", "化学味", "塑料味",
        ],
        "damage": [
            "破了", "裂了", "断了", "碎了", "漏了", "掉色", "褪色",
            "生锈", "变形", "开胶", "脱线",
        ],
    }

    def __init__(
        self,
        *,
        tmapi_client: TMAPI1688Client | None = None,
        sglang_client: SGLangClient | None = None,
        feedback_aggregator: FeedbackAggregator | None = None,
    ):
        self.settings = get_settings().model_copy(deep=True)
        self.logger = get_logger(__name__)
        self._tmapi_client = tmapi_client
        self._sglang_client = sglang_client
        self._feedback_aggregator = feedback_aggregator
        self._created_sglang_client = False
        self._recall_pool: dict[str, Alibaba1688Candidate] = {}

    async def _get_tmapi_client(self) -> TMAPI1688Client:
        """Get or create TMAPI 1688 client."""
        if self._tmapi_client is None:
            self._tmapi_client = TMAPI1688Client()
        return self._tmapi_client

    async def _get_sglang_client(self) -> SGLangClient | None:
        """Get or create SGLang client when LLM query expansion is enabled."""
        if not self.settings.tmapi_1688_enable_llm_query_expansion:
            return None
        if self._sglang_client is None:
            self._sglang_client = SGLangClient()
            self._created_sglang_client = True
        return self._sglang_client

    async def fetch_products(
        self,
        category: str | None = None,
        keywords: list[str] | None = None,
        price_min: Decimal | None = None,
        price_max: Decimal | None = None,
        limit: int = 10,
        region: str | None = None,
    ) -> list[ProductData]:
        """Fetch products from 1688 using TMAPI business-oriented orchestration."""
        client = await self._get_tmapi_client()
        price_min_cny = self._usd_to_cny(price_min)
        price_max_cny = self._usd_to_cny(price_max)

        if self.settings.tmapi_1688_enable_historical_feedback:
            try:
                if self._feedback_aggregator is None:
                    self._feedback_aggregator = FeedbackAggregator(
                        lookback_days=self.settings.tmapi_1688_historical_feedback_lookback_days,
                        prior_cap=self.settings.tmapi_1688_historical_feedback_prior_cap,
                    )
                    from app.db.session import get_db_context

                    async with get_db_context() as db:
                        await self._feedback_aggregator.refresh(db)
                elif isinstance(self._feedback_aggregator, FeedbackAggregator):
                    from app.db.session import get_db_context

                    async with get_db_context() as db:
                        await self._feedback_aggregator.refresh(db)
            except Exception as exc:
                self.logger.warning("alibaba_1688_feedback_refresh_failed", error=str(exc))

        self.logger.info(
            "alibaba_1688_fetch_started",
            category=category,
            keywords=keywords or [],
            price_min_cny=price_min_cny,
            price_max_cny=price_max_cny,
            limit=limit,
            region=region,
        )

        try:
            seeds, discovery_mode = await self._build_search_seeds(
                category=category,
                keywords=keywords or [],
            )
            if not seeds:
                return []

            recall_pool = await self._run_recall(
                client=client,
                seeds=seeds,
                discovery_mode=discovery_mode,
                category=category,
                price_min_cny=price_min_cny,
                price_max_cny=price_max_cny,
                limit=limit,
            )
            if not recall_pool:
                return []

            shortlisted = self._shortlist_candidates(
                candidates=recall_pool,
                limit=limit,
                price_min_cny=price_min_cny,
                price_max_cny=price_max_cny,
            )
            enriched = await self._enrich_shortlist(
                client=client,
                candidates=shortlisted,
                region=region,
            )
            final_candidates = self._finalize_candidates(
                candidates=enriched,
                limit=limit,
                price_min_cny=price_min_cny,
                price_max_cny=price_max_cny,
            )
            products = [self._to_product_data(candidate) for candidate in final_candidates]

            self.logger.info(
                "alibaba_1688_fetch_completed",
                count=len(products),
                discovery_mode=discovery_mode,
            )
            return products

        except Exception as exc:
            self.logger.error(
                "alibaba_1688_fetch_failed",
                error=str(exc),
                category=category,
                keywords=keywords or [],
            )
            return []

    async def get_product_detail(self, item_id: str) -> dict[str, Any]:
        """Get detailed product information."""
        client = await self._get_tmapi_client()
        return await client.get_item_detail(item_id=item_id, language=self.settings.tmapi_1688_search_language)

    async def get_shipping_fee(self, item_id: str, province: str) -> dict[str, Any]:
        """Get shipping fee for a product."""
        client = await self._get_tmapi_client()
        return await client.get_item_shipping(item_id=item_id, province=province)

    async def _build_search_seeds(
        self,
        *,
        category: str | None,
        keywords: list[str],
    ) -> tuple[list[SearchSeed], str]:
        """Build search seeds from pre-validated keywords only.

        Demand-first contract:
        - When legacy mode is disabled, all search seeds must come from upstream
          demand discovery / validation.
        - When legacy mode is enabled, fall back to the historical seed generation
          path for temporary compatibility.
        """
        seeds: list[SearchSeed] = []
        seen_keywords: set[str] = set()

        def add_seed(keyword: str, seed_type: str, source_keyword: str | None = None) -> None:
            normalized = self._normalize_keyword(keyword)
            if not normalized or normalized in seen_keywords:
                return
            seen_keywords.add(normalized)
            seeds.append(SearchSeed(keyword=normalized, seed_type=seed_type, source_keyword=source_keyword))

        for keyword in keywords:
            normalized = self._normalize_keyword(keyword)
            if normalized:
                add_seed(normalized, "explicit", normalized)

        if seeds:
            return seeds, "validated"

        if not self.settings.product_selection_adapter_legacy_seed_mode:
            self.logger.warning(
                "alibaba_1688_no_validated_keywords",
                category=category,
                legacy_mode=False,
            )
            return [], "validated"

        self.logger.warning(
            "alibaba_1688_legacy_seed_mode_enabled",
            category=category,
            reason="empty_keywords",
        )
        return self._build_legacy_search_seeds(category=category)

    def _build_legacy_search_seeds(
        self,
        *,
        category: str | None,
    ) -> tuple[list[SearchSeed], str]:
        """Legacy seed generation path kept for temporary compatibility."""
        seeds: list[SearchSeed] = []
        seen_keywords: set[str] = set()

        def add_seed(keyword: str, seed_type: str, source_keyword: str | None = None) -> None:
            normalized = self._normalize_keyword(keyword)
            if not normalized or normalized in seen_keywords:
                return
            seen_keywords.add(normalized)
            seeds.append(SearchSeed(keyword=normalized, seed_type=seed_type, source_keyword=source_keyword))

        normalized_category = self._normalize_keyword(category)
        if normalized_category:
            add_seed(normalized_category, "category", normalized_category)
            hotword_limit = max(0, self.settings.tmapi_1688_suggest_limit_per_seed)
            for hotword in self._get_category_hotwords(normalized_category)[:hotword_limit]:
                add_seed(hotword, "category_hotword", normalized_category)
            for historical_seed in self._get_historical_high_performing_seeds(
                category=normalized_category,
                keywords=[],
            ):
                add_seed(historical_seed, "historical", normalized_category)
            return seeds, "category"

        seasonal_limit = max(0, self.settings.tmapi_1688_seasonal_seed_limit)
        min_seed_count = max(1, self.settings.tmapi_1688_min_seed_count)
        season = self._get_current_season()
        for seasonal_seed in self._get_seasonal_seeds(season)[:seasonal_limit]:
            add_seed(seasonal_seed, "seasonal", season)

        for historical_seed in self._get_historical_high_performing_seeds(category=None, keywords=[]):
            add_seed(historical_seed, "historical", "cold_start")

        if len(seeds) < min_seed_count:
            for cold_seed in self.settings.tmapi_1688_cold_start_seeds:
                normalized_seed = self._normalize_keyword(cold_seed)
                if normalized_seed:
                    add_seed(normalized_seed, "cold_start", normalized_seed)
                if len(seeds) >= min_seed_count:
                    break

        if not seeds:
            for cold_seed in self.settings.tmapi_1688_cold_start_seeds:
                normalized_seed = self._normalize_keyword(cold_seed)
                if normalized_seed:
                    add_seed(normalized_seed, "cold_start", normalized_seed)

        return seeds, "cold_start"

    def _get_category_hotwords(self, category: str) -> list[str]:
        """Return lightweight static hotwords for a category."""
        normalized_category = self._normalize_keyword(category)
        if not normalized_category:
            return []

        direct = self.CATEGORY_HOTWORD_MAP.get(normalized_category)
        if direct:
            return [self._normalize_keyword(keyword) for keyword in direct if self._normalize_keyword(keyword)]

        results: list[str] = []
        seen: set[str] = set()
        lower_category = normalized_category.lower()
        for token, suffixes in self.CATEGORY_HOTWORD_FALLBACKS:
            if token not in normalized_category and token not in lower_category:
                continue
            for suffix in suffixes:
                candidate = self._normalize_keyword(f"{suffix}{normalized_category}" if self._contains_cjk(normalized_category) else f"{suffix} {normalized_category}")
                if candidate and candidate not in seen:
                    seen.add(candidate)
                    results.append(candidate)
        return results

    def _get_current_season(self) -> str:
        """Return the current season for seed generation."""
        month = datetime.now(UTC).month
        if month in {3, 4, 5}:
            return "spring"
        if month in {6, 7, 8}:
            return "summer"
        if month in {9, 10, 11}:
            return "autumn"
        return "winter"

    def _get_seasonal_seeds(self, season: str) -> list[str]:
        """Return seasonal seeds for cold-start mode."""
        seasonal = self.SEASONAL_SEED_MAP.get(season, [])
        return [self._normalize_keyword(keyword) for keyword in seasonal if self._normalize_keyword(keyword)]

    def _get_historical_high_performing_seeds(
        self,
        *,
        category: str | None,
        keywords: list[str],
    ) -> list[str]:
        """Phase 6: closed-loop historical seed feedback."""
        _ = keywords
        if not self.settings.tmapi_1688_enable_historical_feedback:
            return []
        if self._feedback_aggregator is None:
            return []

        limit = max(1, self.settings.tmapi_1688_suggest_limit_per_seed)
        return self._feedback_aggregator.get_high_performing_seeds(
            category=category,
            limit=limit,
        )

    async def _generate_llm_queries(
        self,
        *,
        category: str | None,
        keywords: list[str],
        limit: int,
    ) -> list[str]:
        """Optionally use the local LLM to expand cold-start or category queries."""
        client = await self._get_sglang_client()
        if client is None or limit <= 0:
            return []

        schema = {
            "name": "alibaba_1688_query_expansion",
            "strict": True,
            "schema": {
                "type": "object",
                "properties": {
                    "queries": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 0,
                        "maxItems": limit,
                    }
                },
                "required": ["queries"],
                "additionalProperties": False,
            },
        }
        prompt = (
            "You are generating high-signal 1688 wholesale product discovery queries. "
            "Return short Chinese noun phrases suitable for B2B sourcing. "
            "Avoid brands, punctuation, and long sentences.\n\n"
            f"Category: {category or 'None'}\n"
            f"Current keywords: {', '.join(keywords) if keywords else 'None'}\n"
            f"Return up to {limit} distinct queries."
        )

        try:
            result = await client.generate_structured_json(
                prompt=prompt,
                schema=schema,
                temperature=0.3,
            )
        except Exception as exc:
            self.logger.warning("alibaba_1688_llm_query_expansion_failed", error=str(exc))
            return []

        queries = result.get("queries") or []
        normalized: list[str] = []
        for query in queries:
            normalized_query = self._normalize_keyword(query)
            if normalized_query:
                normalized.append(normalized_query)
        return normalized[:limit]

    async def _run_recall(
        self,
        *,
        client: TMAPI1688Client,
        seeds: list[SearchSeed],
        discovery_mode: str,
        category: str | None,
        price_min_cny: float | None,
        price_max_cny: float | None,
        limit: int,
    ) -> list[Alibaba1688Candidate]:
        """Run recall lanes, then conditionally expand with LLM when the first pass underperforms."""
        if not seeds:
            self._recall_pool = {}
            return []

        merged = await self._execute_recall_for_seeds(
            client=client,
            seeds=seeds,
            discovery_mode=discovery_mode,
            price_min_cny=price_min_cny,
            price_max_cny=price_max_cny,
            limit=limit,
        )

        if self._should_expand_with_llm(
            candidates=list(merged.values()),
            limit=limit,
            price_min_cny=price_min_cny,
            price_max_cny=price_max_cny,
        ):
            llm_queries = await self._generate_llm_queries(
                category=self._normalize_keyword(category),
                keywords=[seed.keyword for seed in seeds],
                limit=self.settings.tmapi_1688_llm_query_limit,
            )
            llm_seeds = self._build_llm_expansion_seeds(seeds=seeds, llm_queries=llm_queries)
            if llm_seeds:
                merged = await self._execute_recall_for_seeds(
                    client=client,
                    seeds=llm_seeds,
                    discovery_mode=discovery_mode,
                    price_min_cny=price_min_cny,
                    price_max_cny=price_max_cny,
                    limit=limit,
                    merged=merged,
                )

        self._recall_pool = merged.copy()
        return list(merged.values())

    async def _execute_recall_for_seeds(
        self,
        *,
        client: TMAPI1688Client,
        seeds: list[SearchSeed],
        discovery_mode: str,
        price_min_cny: float | None,
        price_max_cny: float | None,
        limit: int,
        merged: dict[str, Alibaba1688Candidate] | None = None,
    ) -> dict[str, Alibaba1688Candidate]:
        """Execute keyword, sales, factory, and image recall lanes for the provided seeds."""
        if not seeds:
            return merged or {}

        recall_target = max(limit * max(self.settings.tmapi_1688_recall_multiplier, 2), limit)
        per_seed_page_size = max(10, min(20, recall_target // max(len(seeds), 1)))
        merged_candidates = merged or {}

        for seed in seeds:
            language = self._infer_language(seed.keyword)

            default_response = await self._safe_search_items(
                client=client,
                keyword=seed.keyword,
                page=1,
                page_size=per_seed_page_size,
                language=language,
                sort="default",
                price_start=price_min_cny,
                price_end=price_max_cny,
                is_super_factory=None,
            )
            for raw in default_response.get("products", []):
                candidate = self._candidate_from_search_row(
                    raw=raw,
                    endpoint="search_items",
                    matched_keyword=seed.keyword,
                    seed_type=seed.seed_type,
                    is_factory_result=False,
                    is_super_factory=False,
                )
                if candidate:
                    self._merge_candidate(merged_candidates, candidate)

            sales_response = await self._safe_search_items(
                client=client,
                keyword=seed.keyword,
                page=1,
                page_size=max(6, per_seed_page_size // 2),
                language=language,
                sort="sales",
                price_start=price_min_cny,
                price_end=price_max_cny,
                is_super_factory=None,
            )
            for raw in sales_response.get("products", []):
                candidate = self._candidate_from_search_row(
                    raw=raw,
                    endpoint="search_items_sales",
                    matched_keyword=seed.keyword,
                    seed_type=seed.seed_type,
                    is_factory_result=False,
                    is_super_factory=False,
                )
                if candidate:
                    self._merge_candidate(merged_candidates, candidate)

            factory_response = await self._safe_search_items(
                client=client,
                keyword=seed.keyword,
                page=1,
                page_size=max(5, per_seed_page_size // 2),
                language=language,
                sort="sales" if discovery_mode != "explicit" else "default",
                price_start=price_min_cny,
                price_end=price_max_cny,
                is_super_factory=True,
            )
            for raw in factory_response.get("products", []):
                candidate = self._candidate_from_search_row(
                    raw=raw,
                    endpoint="search_items_factory",
                    matched_keyword=seed.keyword,
                    seed_type=seed.seed_type,
                    is_factory_result=True,
                    is_super_factory=True,
                )
                if candidate:
                    self._merge_candidate(merged_candidates, candidate)

        image_seed_candidates = list(merged_candidates.values())
        for candidate in image_seed_candidates:
            self._compute_candidate_scores(
                candidate,
                price_min_cny=price_min_cny,
                price_max_cny=price_max_cny,
            )
        ranked_for_image = sorted(image_seed_candidates, key=lambda item: item.discovery_score, reverse=True)

        for seed_candidate in ranked_for_image[: min(2, len(ranked_for_image))]:
            if not seed_candidate.main_image_url:
                continue
            image_response = await self._safe_search_items_by_image(
                client=client,
                img_url=seed_candidate.main_image_url,
                page=1,
                page_size=max(5, per_seed_page_size // 2),
                language=self._infer_language(seed_candidate.title or seed_candidate.matched_keyword or ""),
                sort="sales",
            )
            for raw in image_response.get("products", []):
                candidate = self._candidate_from_search_row(
                    raw=raw,
                    endpoint="search_items_by_image",
                    matched_keyword=seed_candidate.matched_keyword or seed_candidate.title,
                    seed_type="image",
                    is_factory_result=self._extract_bool(raw.get("is_factory")),
                    is_super_factory=self._extract_bool(raw.get("is_super_factory")),
                )
                if candidate:
                    self._merge_candidate(merged_candidates, candidate)

        return merged_candidates

    def _build_llm_expansion_seeds(self, *, seeds: list[SearchSeed], llm_queries: list[str]) -> list[SearchSeed]:
        """Convert LLM-expanded queries into second-pass search seeds."""
        existing_keywords = {self._normalize_keyword(seed.keyword) for seed in seeds}
        llm_seeds: list[SearchSeed] = []
        for query in llm_queries:
            normalized_query = self._normalize_keyword(query)
            if not normalized_query or normalized_query in existing_keywords:
                continue
            existing_keywords.add(normalized_query)
            llm_seeds.append(
                SearchSeed(
                    keyword=normalized_query,
                    seed_type="llm",
                    source_keyword=seeds[0].source_keyword if seeds else None,
                )
            )
        return llm_seeds

    def _should_expand_with_llm(
        self,
        *,
        candidates: list[Alibaba1688Candidate],
        limit: int,
        price_min_cny: float | None,
        price_max_cny: float | None,
    ) -> bool:
        """Decide whether to run a second-pass LLM query expansion recall."""
        if not self.settings.tmapi_1688_enable_llm_query_expansion:
            return False
        if self.settings.tmapi_1688_llm_query_limit <= 0:
            return False
        if not candidates:
            return True

        for candidate in candidates:
            self._compute_candidate_scores(
                candidate,
                price_min_cny=price_min_cny,
                price_max_cny=price_max_cny,
            )

        recall_threshold = max(1, self.settings.tmapi_1688_llm_expansion_min_recall_threshold)
        if len(candidates) < recall_threshold:
            return True

        top_k = min(len(candidates), max(1, limit))
        top_candidates = sorted(candidates, key=lambda item: item.discovery_score, reverse=True)[:top_k]
        if not top_candidates:
            return True
        average_quality = sum(candidate.discovery_score for candidate in top_candidates) / len(top_candidates)
        return average_quality < self.settings.tmapi_1688_llm_expansion_min_quality_threshold

    def _shortlist_candidates(
        self,
        *,
        candidates: list[Alibaba1688Candidate],
        limit: int,
        price_min_cny: float | None,
        price_max_cny: float | None,
    ) -> list[Alibaba1688Candidate]:
        """Apply coarse ranking and keep the shortlist for enrichment."""
        for candidate in candidates:
            self._compute_candidate_scores(
                candidate,
                price_min_cny=price_min_cny,
                price_max_cny=price_max_cny,
            )

        shortlist_size = max(limit, min(len(candidates), max(limit * 2, self.settings.tmapi_1688_detail_top_k)))
        ranked = sorted(candidates, key=lambda item: item.discovery_score, reverse=True)
        return ranked[:shortlist_size]

    async def _enrich_shortlist(
        self,
        *,
        client: TMAPI1688Client,
        candidates: list[Alibaba1688Candidate],
        region: str | None,
    ) -> list[Alibaba1688Candidate]:
        """Enrich top-ranked candidates with detail, desc, ratings, shop, and shipping."""
        top_k = min(len(candidates), max(0, self.settings.tmapi_1688_detail_top_k))
        province = self.settings.tmapi_1688_region_province_map.get(region or "") if region else None

        for candidate in candidates[:top_k]:
            language = self._infer_language(candidate.title or candidate.matched_keyword or "")

            try:
                detail = await client.get_item_detail(item_id=candidate.item_id, language=language)
                self._merge_detail(candidate, detail)
            except Exception as exc:
                self.logger.warning(
                    "alibaba_1688_detail_enrichment_failed",
                    item_id=candidate.item_id,
                    error=str(exc),
                )

            try:
                desc = await client.get_item_desc(item_id=candidate.item_id)
                self._merge_desc(candidate, desc)
            except Exception as exc:
                self.logger.warning(
                    "alibaba_1688_desc_enrichment_failed",
                    item_id=candidate.item_id,
                    error=str(exc),
                )

            if self.settings.tmapi_1688_enable_ratings:
                try:
                    ratings = await client.get_item_ratings(item_id=candidate.item_id, page=1, sort_type="default")
                    self._merge_ratings(candidate, ratings)
                except Exception as exc:
                    self.logger.warning(
                        "alibaba_1688_ratings_enrichment_failed",
                        item_id=candidate.item_id,
                        error=str(exc),
                    )

            if self.settings.tmapi_1688_enable_shop_info and (candidate.shop_url or candidate.member_id):
                try:
                    shop_info = await client.get_shop_info(shop_url=candidate.shop_url, member_id=candidate.member_id)
                    self._merge_shop_info(candidate, shop_info)
                except Exception as exc:
                    self.logger.warning(
                        "alibaba_1688_shop_info_enrichment_failed",
                        item_id=candidate.item_id,
                        error=str(exc),
                    )

            if self.settings.tmapi_1688_enable_shop_info and candidate.shop_url:
                try:
                    shop_items = await client.get_shop_items(
                        shop_url=candidate.shop_url,
                        page=1,
                        page_size=5,
                        sort="sales",
                    )
                    self._merge_shop_items(candidate, shop_items)
                except Exception as exc:
                    self.logger.warning(
                        "alibaba_1688_shop_items_enrichment_failed",
                        item_id=candidate.item_id,
                        error=str(exc),
                    )

            if self.settings.tmapi_1688_enable_shipping and province:
                try:
                    shipping = await client.get_item_shipping(
                        item_id=candidate.item_id,
                        province=province,
                        total_quantity=max(candidate.moq or 1, 1),
                        total_weight=self._extract_weight(candidate.raw_payload.get("detail_payload") or {}),
                    )
                    self._merge_shipping(candidate, shipping, province=province)
                except Exception as exc:
                    self.logger.warning(
                        "alibaba_1688_shipping_enrichment_failed",
                        item_id=candidate.item_id,
                        province=province,
                        error=str(exc),
                    )

        return candidates

    def _finalize_candidates(
        self,
        *,
        candidates: list[Alibaba1688Candidate],
        limit: int,
        price_min_cny: float | None,
        price_max_cny: float | None,
    ) -> list[Alibaba1688Candidate]:
        """Re-score after enrichment and return the final ranked candidate list."""
        for candidate in candidates:
            self._compute_candidate_scores(
                candidate,
                price_min_cny=price_min_cny,
                price_max_cny=price_max_cny,
            )

        ranked = sorted(candidates, key=lambda item: item.final_score, reverse=True)
        if not self.settings.tmapi_1688_enable_diversification:
            return ranked[:limit]
        return self._select_diversified_candidates(ranked=ranked, limit=limit)

    def _select_diversified_candidates(
        self,
        *,
        ranked: list[Alibaba1688Candidate],
        limit: int,
    ) -> list[Alibaba1688Candidate]:
        """Apply diversification constraints to the final ranked list."""
        if limit <= 0 or not ranked:
            return []

        lane_targets = self._compute_seed_lane_targets(ranked=ranked, limit=limit)
        relaxation_passes = max(0, self.settings.tmapi_1688_diversification_relaxation_passes)

        strict_strategy = {
            "enforce_shop_cap": True,
            "enforce_image_dedupe": self.settings.tmapi_1688_diversification_enable_image_dedupe,
            "enforce_title_dedupe": self.settings.tmapi_1688_diversification_enable_title_dedupe,
        }

        strict_selection = self._select_candidates_with_constraints(
            ranked=ranked,
            limit=limit,
            lane_targets=lane_targets,
            **strict_strategy,
        )
        if len(strict_selection) >= limit:
            return strict_selection[:limit]

        strategy_candidates = [strict_strategy]
        if relaxation_passes >= 1 and self.settings.tmapi_1688_diversification_enable_title_dedupe:
            strategy_candidates.append(
                {
                    "enforce_shop_cap": True,
                    "enforce_image_dedupe": self.settings.tmapi_1688_diversification_enable_image_dedupe,
                    "enforce_title_dedupe": False,
                }
            )
        if relaxation_passes >= 2 and (
            self.settings.tmapi_1688_diversification_enable_image_dedupe
            or self.settings.tmapi_1688_diversification_enable_title_dedupe
        ):
            strategy_candidates.append(
                {
                    "enforce_shop_cap": True,
                    "enforce_image_dedupe": False,
                    "enforce_title_dedupe": False,
                }
            )
        if relaxation_passes >= 3:
            strategy_candidates.append(
                {
                    "enforce_shop_cap": False,
                    "enforce_image_dedupe": False,
                    "enforce_title_dedupe": False,
                }
            )

        best_selection = strict_selection
        best_score = sum(candidate.final_score for candidate in strict_selection)
        seen_strategies: set[tuple[bool, bool, bool]] = {
            (
                strict_strategy["enforce_shop_cap"],
                strict_strategy["enforce_image_dedupe"],
                strict_strategy["enforce_title_dedupe"],
            )
        }

        for strategy in strategy_candidates[1:]:
            strategy_key = (
                strategy["enforce_shop_cap"],
                strategy["enforce_image_dedupe"],
                strategy["enforce_title_dedupe"],
            )
            if strategy_key in seen_strategies:
                continue
            seen_strategies.add(strategy_key)

            selection = self._select_candidates_with_constraints(
                ranked=ranked,
                limit=limit,
                lane_targets=lane_targets,
                **strategy,
            )
            if len(selection) >= limit:
                return selection[:limit]

            selection_score = sum(candidate.final_score for candidate in selection)
            if len(selection) > len(best_selection) or (
                len(selection) == len(best_selection) and selection_score > best_score
            ):
                best_selection = selection
                best_score = selection_score

        if len(best_selection) < limit:
            selected_ids = {candidate.item_id for candidate in best_selection}
            for candidate in ranked:
                if candidate.item_id in selected_ids:
                    continue
                best_selection.append(candidate)
                selected_ids.add(candidate.item_id)
                if len(best_selection) >= limit:
                    break

        return best_selection[:limit]

    def _select_candidates_with_constraints(
        self,
        *,
        ranked: list[Alibaba1688Candidate],
        limit: int,
        lane_targets: dict[str, int],
        enforce_shop_cap: bool,
        enforce_image_dedupe: bool,
        enforce_title_dedupe: bool,
    ) -> list[Alibaba1688Candidate]:
        """Select candidates from scratch under one diversification strategy."""
        selected: list[Alibaba1688Candidate] = []
        selected_ids: set[str] = set()
        selected_shop_counts: dict[str, int] = {}
        selected_image_clusters: set[str] = set()
        selected_title_clusters: set[str] = set()

        for lane, quota in lane_targets.items():
            lane_selected = 0
            for candidate in ranked:
                if self._resolve_seed_lane(candidate) != lane:
                    continue
                if self._try_select_candidate(
                    candidate=candidate,
                    selected=selected,
                    selected_ids=selected_ids,
                    selected_shop_counts=selected_shop_counts,
                    selected_image_clusters=selected_image_clusters,
                    selected_title_clusters=selected_title_clusters,
                    enforce_shop_cap=enforce_shop_cap,
                    enforce_image_dedupe=enforce_image_dedupe,
                    enforce_title_dedupe=enforce_title_dedupe,
                    limit=limit,
                ):
                    lane_selected += 1
                if lane_selected >= quota or len(selected) >= limit:
                    break
            if len(selected) >= limit:
                return self._order_selected_candidates(ranked=ranked, selected_ids=selected_ids, limit=limit)

        self._fill_remaining_candidates(
            ranked=ranked,
            selected=selected,
            selected_ids=selected_ids,
            selected_shop_counts=selected_shop_counts,
            selected_image_clusters=selected_image_clusters,
            selected_title_clusters=selected_title_clusters,
            limit=limit,
            enforce_shop_cap=enforce_shop_cap,
            enforce_image_dedupe=enforce_image_dedupe,
            enforce_title_dedupe=enforce_title_dedupe,
        )
        return self._order_selected_candidates(ranked=ranked, selected_ids=selected_ids, limit=limit)

    def _order_selected_candidates(
        self,
        *,
        ranked: list[Alibaba1688Candidate],
        selected_ids: set[str],
        limit: int,
    ) -> list[Alibaba1688Candidate]:
        """Restore global final_score rank order for the diversified selection."""
        return [candidate for candidate in ranked if candidate.item_id in selected_ids][:limit]

    def _compute_seed_lane_targets(
        self,
        *,
        ranked: list[Alibaba1688Candidate],
        limit: int,
    ) -> dict[str, int]:
        """Compute soft per-lane representation targets for the final shortlist."""
        min_quota = max(0, self.settings.tmapi_1688_diversification_seed_min_quota)
        if limit < 3 or min_quota <= 0:
            return {}

        lane_priority = ("historical", "explicit", "category", "category_hotword", "seasonal", "llm", "image", "cold_start")
        available_lanes = [
            lane for lane in lane_priority if any(self._resolve_seed_lane(candidate) == lane for candidate in ranked)
        ]
        if not available_lanes:
            return {}

        max_lanes = min(
            len(available_lanes),
            max(0, self.settings.tmapi_1688_diversification_seed_quota_max_lanes),
            limit,
        )
        if max_lanes <= 0:
            return {}

        quota_safe_lanes = max(1, limit // min_quota)
        max_lanes = min(max_lanes, quota_safe_lanes)
        return {lane: min_quota for lane in available_lanes[:max_lanes]}

    def _fill_remaining_candidates(
        self,
        *,
        ranked: list[Alibaba1688Candidate],
        selected: list[Alibaba1688Candidate],
        selected_ids: set[str],
        selected_shop_counts: dict[str, int],
        selected_image_clusters: set[str],
        selected_title_clusters: set[str],
        limit: int,
        enforce_shop_cap: bool,
        enforce_image_dedupe: bool,
        enforce_title_dedupe: bool,
    ) -> None:
        """Fill remaining slots under the currently active diversification constraints."""
        for candidate in ranked:
            if self._try_select_candidate(
                candidate=candidate,
                selected=selected,
                selected_ids=selected_ids,
                selected_shop_counts=selected_shop_counts,
                selected_image_clusters=selected_image_clusters,
                selected_title_clusters=selected_title_clusters,
                enforce_shop_cap=enforce_shop_cap,
                enforce_image_dedupe=enforce_image_dedupe,
                enforce_title_dedupe=enforce_title_dedupe,
                limit=limit,
            ):
                if len(selected) >= limit:
                    return

    def _try_select_candidate(
        self,
        *,
        candidate: Alibaba1688Candidate,
        selected: list[Alibaba1688Candidate],
        selected_ids: set[str],
        selected_shop_counts: dict[str, int],
        selected_image_clusters: set[str],
        selected_title_clusters: set[str],
        enforce_shop_cap: bool,
        enforce_image_dedupe: bool,
        enforce_title_dedupe: bool,
        limit: int,
    ) -> bool:
        """Try to add a candidate under the current diversification constraints."""
        if candidate.item_id in selected_ids or len(selected) >= limit:
            return False
        if self._candidate_conflicts_with_selection(
            candidate=candidate,
            selected_shop_counts=selected_shop_counts,
            selected_image_clusters=selected_image_clusters,
            selected_title_clusters=selected_title_clusters,
            enforce_shop_cap=enforce_shop_cap,
            enforce_image_dedupe=enforce_image_dedupe,
            enforce_title_dedupe=enforce_title_dedupe,
        ):
            return False

        self._register_selected_candidate(
            candidate=candidate,
            selected=selected,
            selected_ids=selected_ids,
            selected_shop_counts=selected_shop_counts,
            selected_image_clusters=selected_image_clusters,
            selected_title_clusters=selected_title_clusters,
        )
        return True

    def _register_selected_candidate(
        self,
        *,
        candidate: Alibaba1688Candidate,
        selected: list[Alibaba1688Candidate],
        selected_ids: set[str],
        selected_shop_counts: dict[str, int],
        selected_image_clusters: set[str],
        selected_title_clusters: set[str],
    ) -> None:
        """Record a candidate in the current diversified selection state."""
        if candidate.item_id in selected_ids:
            return

        selected.append(candidate)
        selected_ids.add(candidate.item_id)

        shop_key = self._resolve_shop_key(candidate)
        if shop_key:
            selected_shop_counts[shop_key] = selected_shop_counts.get(shop_key, 0) + 1

        selected_image_clusters.update(self._resolve_image_cluster_keys(candidate))
        title_cluster = self._resolve_title_cluster_key(candidate)
        if title_cluster:
            selected_title_clusters.add(title_cluster)

    def _candidate_conflicts_with_selection(
        self,
        *,
        candidate: Alibaba1688Candidate,
        selected_shop_counts: dict[str, int],
        selected_image_clusters: set[str],
        selected_title_clusters: set[str],
        enforce_shop_cap: bool,
        enforce_image_dedupe: bool,
        enforce_title_dedupe: bool,
    ) -> bool:
        """Check whether a candidate violates the current diversified shortlist constraints."""
        if enforce_shop_cap:
            shop_cap = self.settings.tmapi_1688_diversification_shop_cap
            shop_key = self._resolve_shop_key(candidate)
            if shop_key and shop_cap > 0 and selected_shop_counts.get(shop_key, 0) >= shop_cap:
                return True

        image_keys = self._resolve_image_cluster_keys(candidate)
        if enforce_image_dedupe and image_keys and any(key in selected_image_clusters for key in image_keys):
            return True

        title_cluster = self._resolve_title_cluster_key(candidate)
        if enforce_title_dedupe and title_cluster and title_cluster in selected_title_clusters:
            return True

        return False

    def _resolve_shop_key(self, candidate: Alibaba1688Candidate) -> str:
        """Resolve a stable shop identity key for final-result shop caps."""
        if candidate.member_id:
            return f"member:{candidate.member_id.strip().lower()}"
        if candidate.seller_id:
            return f"seller:{candidate.seller_id.strip().lower()}"
        if candidate.shop_url:
            normalized_shop_url = self._normalize_image_url(candidate.shop_url)
            if normalized_shop_url:
                return f"shop_url:{normalized_shop_url}"
        if candidate.shop_name:
            normalized_shop_name = self._normalize_title_for_diversity(candidate.shop_name)
            if normalized_shop_name:
                return f"shop_name:{normalized_shop_name}"
        return f"item:{candidate.item_id}"

    def _normalize_image_url(self, url: str | None) -> str | None:
        """Normalize an image URL for exact cluster-based dedupe."""
        if not url:
            return None

        cleaned = str(url).strip()
        if not cleaned:
            return None

        split = urlsplit(cleaned)
        if split.scheme or split.netloc:
            normalized = urlunsplit(
                (
                    split.scheme.lower(),
                    split.netloc.lower(),
                    split.path.lower(),
                    "",
                    "",
                )
            )
        else:
            normalized = cleaned.split("#", 1)[0].split("?", 1)[0].strip().lower()

        return normalized.rstrip("/") or None

    def _resolve_image_cluster_keys(self, candidate: Alibaba1688Candidate) -> list[str]:
        """Resolve exact-normalized image keys used for same-image dedupe."""
        image_keys: list[str] = []
        seen: set[str] = set()
        for url in [candidate.main_image_url, *candidate.image_urls]:
            normalized = self._normalize_image_url(url)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            image_keys.append(normalized)
        return image_keys

    def _normalize_title_for_diversity(self, value: str | None) -> str | None:
        """Normalize titles conservatively for duplicate-variant detection."""
        if not value:
            return None

        normalized = unicodedata.normalize("NFKC", str(value)).lower().strip()
        if not normalized:
            return None

        normalized = re.sub(r"[\W_]+", " ", normalized, flags=re.UNICODE)
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized or None

    def _resolve_title_cluster_key(self, candidate: Alibaba1688Candidate) -> str | None:
        """Resolve a conservative title cluster key for secondary dedupe."""
        normalized_title = self._normalize_title_for_diversity(candidate.title)
        if not normalized_title:
            return None
        return f"title:{normalized_title}"

    def _resolve_seed_lane(self, candidate: Alibaba1688Candidate) -> str:
        """Resolve the candidate's dominant seed lane for diversity quotas."""
        if candidate.seed_type in {
            "historical",
            "explicit",
            "category",
            "category_hotword",
            "seasonal",
            "llm",
            "image",
            "cold_start",
        }:
            return candidate.seed_type
        if "search_items_by_image" in candidate.source_endpoints:
            return "image"
        return "cold_start"

    async def _safe_search_items(
        self,
        *,
        client: TMAPI1688Client,
        keyword: str,
        page: int,
        page_size: int,
        language: str,
        sort: str,
        price_start: float | None,
        price_end: float | None,
        is_super_factory: bool | None,
    ) -> dict[str, Any]:
        """Safely call the TMAPI keyword search lane."""
        try:
            return await client.search_items(
                keyword=keyword,
                page=page,
                page_size=page_size,
                language=language,
                sort=sort,
                price_start=price_start,
                price_end=price_end,
                is_super_factory=is_super_factory,
            )
        except Exception as exc:
            self.logger.warning(
                "alibaba_1688_search_lane_failed",
                endpoint="search_items",
                keyword=keyword,
                sort=sort,
                is_super_factory=is_super_factory,
                error=str(exc),
            )
            return {"products": [], "total": 0, "page": page, "page_size": page_size, "has_more": False}

    async def _safe_search_items_by_image(
        self,
        *,
        client: TMAPI1688Client,
        img_url: str,
        page: int,
        page_size: int,
        language: str,
        sort: str,
    ) -> dict[str, Any]:
        """Safely call the TMAPI image search lane."""
        try:
            return await client.search_items_by_image(
                img_url=img_url,
                page=page,
                page_size=page_size,
                language=language,
                sort=sort,
            )
        except Exception as exc:
            self.logger.warning(
                "alibaba_1688_search_lane_failed",
                endpoint="search_items_by_image",
                img_url=img_url,
                error=str(exc),
            )
            return {"products": [], "total": 0, "page": page, "page_size": page_size, "has_more": False}

    def _candidate_from_search_row(
        self,
        *,
        raw: dict[str, Any],
        endpoint: str,
        matched_keyword: str,
        seed_type: str,
        is_factory_result: bool,
        is_super_factory: bool,
    ) -> Alibaba1688Candidate | None:
        """Normalize a TMAPI search row into an internal candidate structure."""
        item_id = self._extract_item_id(raw)
        title = self._extract_title(raw)
        if not item_id or not title:
            return None

        images = self._extract_image_urls(raw)
        return Alibaba1688Candidate(
            item_id=item_id,
            title=title,
            category_name=self._first_non_empty(raw.get("category_name"), raw.get("category")),
            detail_url=self._extract_detail_url(raw, item_id),
            main_image_url=self._first_non_empty(raw.get("img"), raw.get("image_url"), raw.get("pic_url")),
            image_urls=images,
            detail_image_urls=[],
            price_cny_min=self._extract_price_min(raw),
            price_cny_max=self._extract_price_max(raw),
            sales_count=self._extract_sales(raw),
            moq=self._extract_moq(raw),
            member_id=self._first_non_empty(raw.get("member_id"), raw.get("seller_member_id")),
            seller_id=self._stringify(self._first_non_empty(raw.get("seller_id"), raw.get("shop_id"))),
            shop_url=self._extract_shop_url(raw),
            shop_name=self._first_non_empty(raw.get("shop_name"), raw.get("store_name")),
            company_name=self._first_non_empty(raw.get("company_name"), raw.get("company")),
            location_str=self._first_non_empty(raw.get("location_str"), raw.get("location")),
            support_dropshipping=self._extract_bool(raw.get("support_dropshipping")),
            verified_supplier=self._extract_bool(raw.get("verified_supplier")),
            is_factory_result=is_factory_result or self._extract_bool(raw.get("is_factory")),
            is_super_factory=is_super_factory or self._extract_bool(raw.get("is_super_factory")),
            matched_keyword=matched_keyword,
            seed_type=seed_type,
            detail_enriched=False,
            description_enriched=False,
            freight_cny=None,
            shipping_province=None,
            shop_item_count=None,
            rating=self._extract_rating(raw),
            review_count=self._extract_int(raw.get("review_count") or raw.get("comment_count")),
            review_sample=[],
            source_endpoints=[endpoint],
            raw_payload={"search_payload": raw},
        )

    def _merge_candidate(
        self,
        merged: dict[str, Alibaba1688Candidate],
        candidate: Alibaba1688Candidate,
    ) -> None:
        """Merge deduped candidate data across recall lanes."""
        existing = merged.get(candidate.item_id)
        if existing is None:
            merged[candidate.item_id] = candidate
            return

        existing.is_factory_result = existing.is_factory_result or candidate.is_factory_result
        existing.is_super_factory = existing.is_super_factory or candidate.is_super_factory
        existing.support_dropshipping = existing.support_dropshipping or candidate.support_dropshipping
        existing.verified_supplier = existing.verified_supplier or candidate.verified_supplier
        existing.detail_enriched = existing.detail_enriched or candidate.detail_enriched
        existing.description_enriched = existing.description_enriched or candidate.description_enriched
        existing.source_endpoints = sorted(set(existing.source_endpoints + candidate.source_endpoints))

        if self.SEED_PRIORITY.get(candidate.seed_type or "", 0) > self.SEED_PRIORITY.get(existing.seed_type or "", 0):
            existing.seed_type = candidate.seed_type
            existing.matched_keyword = candidate.matched_keyword
        elif not existing.matched_keyword and candidate.matched_keyword:
            existing.matched_keyword = candidate.matched_keyword

        for field_name in (
            "category_name",
            "detail_url",
            "main_image_url",
            "price_cny_min",
            "price_cny_max",
            "sales_count",
            "moq",
            "member_id",
            "seller_id",
            "shop_url",
            "shop_name",
            "company_name",
            "location_str",
            "shop_item_count",
            "rating",
            "review_count",
            "freight_cny",
            "shipping_province",
        ):
            if getattr(existing, field_name) in (None, "", []):
                setattr(existing, field_name, getattr(candidate, field_name))

        if not existing.image_urls and candidate.image_urls:
            existing.image_urls = candidate.image_urls
        if not existing.detail_image_urls and candidate.detail_image_urls:
            existing.detail_image_urls = candidate.detail_image_urls
        if not existing.review_sample and candidate.review_sample:
            existing.review_sample = candidate.review_sample

        existing.raw_payload.update(candidate.raw_payload)

    def _merge_detail(self, candidate: Alibaba1688Candidate, detail: dict[str, Any]) -> None:
        """Merge item detail payload into the candidate."""
        detail_images = self._extract_image_urls(detail)
        detail_title = self._extract_title(detail)
        if detail_title and not candidate.title:
            candidate.title = detail_title
        candidate.category_name = self._first_non_empty(
            candidate.category_name,
            detail.get("category_name"),
            detail.get("category"),
        )
        candidate.detail_url = self._extract_detail_url(detail, candidate.item_id) or candidate.detail_url
        detail_main_image = self._first_non_empty(
            detail.get("img"),
            detail.get("image_url"),
            detail.get("pic_url"),
        )
        if detail_main_image and not candidate.main_image_url:
            candidate.main_image_url = detail_main_image
        if detail_images and not candidate.image_urls:
            candidate.image_urls = detail_images

        candidate.price_cny_min = self._extract_price_min(detail) or candidate.price_cny_min
        candidate.price_cny_max = self._extract_price_max(detail) or candidate.price_cny_max
        candidate.sales_count = self._extract_sales(detail) or candidate.sales_count
        candidate.moq = self._extract_moq(detail) or candidate.moq
        candidate.member_id = self._first_non_empty(detail.get("member_id"), candidate.member_id)
        candidate.seller_id = self._stringify(self._first_non_empty(detail.get("seller_id"), candidate.seller_id))
        candidate.shop_url = self._first_non_empty(self._extract_shop_url(detail), candidate.shop_url)
        candidate.shop_name = self._first_non_empty(detail.get("shop_name"), detail.get("store_name"), candidate.shop_name)
        candidate.company_name = self._first_non_empty(detail.get("company_name"), detail.get("company"), candidate.company_name)
        candidate.location_str = self._first_non_empty(detail.get("location_str"), detail.get("location"), candidate.location_str)
        candidate.support_dropshipping = candidate.support_dropshipping or self._extract_bool(detail.get("support_dropshipping"))
        candidate.verified_supplier = candidate.verified_supplier or self._extract_bool(detail.get("verified_supplier"))
        candidate.is_factory_result = candidate.is_factory_result or self._extract_bool(detail.get("is_factory"))
        candidate.is_super_factory = candidate.is_super_factory or self._extract_bool(detail.get("is_super_factory"))
        candidate.rating = self._extract_rating(detail) or candidate.rating
        candidate.detail_enriched = True
        if "item_detail" not in candidate.source_endpoints:
            candidate.source_endpoints.append("item_detail")
        candidate.raw_payload["detail_payload"] = detail

    def _merge_desc(self, candidate: Alibaba1688Candidate, desc: dict[str, Any]) -> None:
        """Merge item description image payload into the candidate."""
        detail_imgs = desc.get("detail_imgs") or []
        normalized_imgs = [str(url) for url in detail_imgs if isinstance(url, str) and url]
        if normalized_imgs:
            candidate.detail_image_urls = normalized_imgs
            candidate.description_enriched = True
            if "item_desc" not in candidate.source_endpoints:
                candidate.source_endpoints.append("item_desc")
            candidate.raw_payload["desc_payload"] = desc

    def _merge_ratings(self, candidate: Alibaba1688Candidate, ratings: dict[str, Any]) -> None:
        """Merge ratings payload into the candidate."""
        reviews = ratings.get("list") or []
        stars: list[Decimal] = []
        samples: list[str] = []
        for review in reviews:
            if not isinstance(review, dict):
                continue
            star = self._parse_decimal(review.get("rate_star"))
            if star is not None:
                stars.append(star)
            feedback = self._first_non_empty(review.get("feedback"), review.get("content"), review.get("text"))
            if isinstance(feedback, str) and feedback.strip():
                samples.append(feedback.strip())

        if stars:
            average = sum(stars) / Decimal(len(stars))
            candidate.rating = average.quantize(Decimal("0.01"))
        candidate.review_count = self._extract_int(ratings.get("total_count")) or len(reviews) or candidate.review_count
        if samples:
            candidate.review_sample = samples[:3]
        if "item_rating" not in candidate.source_endpoints:
            candidate.source_endpoints.append("item_rating")
        candidate.raw_payload["ratings_payload"] = ratings

    def _extract_review_defect_signals(self, review_sample: list[str]) -> dict[str, int]:
        """Extract conservative defect counts from review text samples."""
        defect_counts = {key: 0 for key in self.REVIEW_DEFECT_KEYWORDS}
        if not review_sample:
            return defect_counts

        for review in review_sample:
            if not isinstance(review, str):
                continue
            text = review.strip().lower()
            if not text:
                continue
            for defect_type, keywords in self.REVIEW_DEFECT_KEYWORDS.items():
                if any(keyword in text for keyword in keywords):
                    defect_counts[defect_type] += 1

        return defect_counts

    def _score_review_risk(self, candidate: Alibaba1688Candidate) -> float:
        """Score review-derived defect risk as a capped business penalty."""
        if not self.settings.tmapi_1688_enable_review_risk_analysis:
            candidate.review_defect_flags = {}
            candidate.review_risk_score = 0.0
            return 0.0

        defect_counts = self._extract_review_defect_signals(candidate.review_sample)
        candidate.review_defect_flags = defect_counts
        weighted_penalty = (
            defect_counts.get("quality", 0) * 3.0
            + defect_counts.get("logistics", 0) * 2.0
            + defect_counts.get("damage", 0) * 2.0
            + defect_counts.get("sizing", 0) * 1.5
            + defect_counts.get("odor", 0) * 1.0
        )
        penalty_cap = max(0.0, float(self.settings.tmapi_1688_review_risk_penalty_cap))
        penalty = min(weighted_penalty, penalty_cap)
        candidate.review_risk_score = -penalty
        return candidate.review_risk_score

    def _merge_shop_info(self, candidate: Alibaba1688Candidate, shop_info: dict[str, Any]) -> None:
        """Merge shop info payload into the candidate."""
        candidate.member_id = self._first_non_empty(shop_info.get("member_id"), candidate.member_id)
        candidate.seller_id = self._stringify(self._first_non_empty(shop_info.get("seller_id"), candidate.seller_id))
        candidate.company_name = self._first_non_empty(shop_info.get("company_name"), candidate.company_name)
        candidate.shop_url = self._first_non_empty(shop_info.get("shop_url"), candidate.shop_url)
        candidate.shop_name = self._first_non_empty(shop_info.get("shop_name"), candidate.shop_name)
        candidate.location_str = self._first_non_empty(shop_info.get("location_str"), candidate.location_str)
        candidate.is_factory_result = candidate.is_factory_result or self._extract_bool(shop_info.get("is_factory"))
        candidate.is_super_factory = candidate.is_super_factory or self._extract_bool(shop_info.get("is_super_factory"))
        if "shop_info" not in candidate.source_endpoints:
            candidate.source_endpoints.append("shop_info")
        candidate.raw_payload["shop_info_payload"] = shop_info

    def _merge_shop_items(self, candidate: Alibaba1688Candidate, shop_items: dict[str, Any]) -> None:
        """Merge shop items payload into the candidate."""
        candidate.shop_item_count = self._extract_int(shop_items.get("total")) or candidate.shop_item_count
        if "shop_items" not in candidate.source_endpoints:
            candidate.source_endpoints.append("shop_items")
        candidate.raw_payload["shop_items_payload"] = shop_items

    def _estimate_shop_focus_ratio(self, candidate: Alibaba1688Candidate) -> float | None:
        """Estimate whether the shop inventory is focused around the current candidate."""
        shop_items_payload = candidate.raw_payload.get("shop_items_payload") or {}
        products = shop_items_payload.get("products") or []
        if not isinstance(products, list) or not products:
            candidate.shop_focus_ratio = None
            return None

        matches = 0
        comparable_count = 0
        candidate_category = self._first_non_empty(candidate.category_name)

        for raw in products:
            if not isinstance(raw, dict):
                continue
            raw_item_id = self._extract_item_id(raw)
            if raw_item_id and raw_item_id == candidate.item_id:
                continue
            comparable_count += 1
            shop_category = self._first_non_empty(raw.get("category_name"), raw.get("category"))
            if (
                candidate_category
                and shop_category
                and str(candidate_category).strip().lower() == str(shop_category).strip().lower()
            ):
                matches += 1
                continue

            if self._titles_are_similar(candidate.title, self._extract_title(raw)):
                matches += 1

        if comparable_count <= 0:
            candidate.shop_focus_ratio = None
            return None

        ratio = matches / comparable_count
        candidate.shop_focus_ratio = ratio
        return ratio

    def _score_shop_intelligence(self, candidate: Alibaba1688Candidate) -> float:
        """Score shop structure quality and penalize unfocused general-store patterns."""
        if not self.settings.tmapi_1688_enable_shop_intelligence:
            candidate.shop_intelligence_score = 0.0
            candidate.shop_focus_ratio = None
            return 0.0

        score = 0.0
        focus_ratio = self._estimate_shop_focus_ratio(candidate)
        shop_item_count = candidate.shop_item_count or 0

        if focus_ratio is not None:
            bonus_cap = max(0.0, float(self.settings.tmapi_1688_shop_focus_bonus_cap))
            if focus_ratio >= 0.6:
                score += min(2.0 + (focus_ratio * 4.0), bonus_cap)
            elif focus_ratio >= 0.3:
                score += min(0.5 + (focus_ratio * 2.0), bonus_cap)
            elif shop_item_count >= 50:
                score -= 4.0
            else:
                score -= 1.5

        if 5 <= shop_item_count <= 80:
            score += 1.5
        elif 81 <= shop_item_count <= 200:
            score += 0.5
        elif shop_item_count >= 500:
            score -= 2.0

        if candidate.is_factory_result:
            score += 1.5
        if candidate.is_super_factory:
            score += 1.5
        if candidate.verified_supplier:
            score += 1.0

        if focus_ratio is not None and focus_ratio < 0.25 and shop_item_count >= 200:
            score -= 2.5

        candidate.shop_intelligence_score = score
        return score

    def _merge_shipping(self, candidate: Alibaba1688Candidate, shipping: dict[str, Any], *, province: str) -> None:
        """Merge shipping payload into the candidate."""
        freight = self._extract_freight(shipping)
        if freight is not None:
            candidate.freight_cny = freight
            candidate.shipping_province = province
            if "item_shipping" not in candidate.source_endpoints:
                candidate.source_endpoints.append("item_shipping")
            candidate.raw_payload["shipping_payload"] = shipping

    def _compute_candidate_scores(
        self,
        candidate: Alibaba1688Candidate,
        *,
        price_min_cny: float | None,
        price_max_cny: float | None,
    ) -> None:
        """Compute all ranking scores for a candidate."""
        candidate.discovery_score = self._score_discovery_candidate(
            candidate,
            price_min_cny=price_min_cny,
            price_max_cny=price_max_cny,
        )
        candidate.business_score = self._score_business_candidate(
            candidate,
            price_min_cny=price_min_cny,
            price_max_cny=price_max_cny,
        )
        candidate.final_score = candidate.discovery_score + candidate.business_score

    def _score_discovery_candidate(
        self,
        candidate: Alibaba1688Candidate,
        *,
        price_min_cny: float | None,
        price_max_cny: float | None,
    ) -> float:
        """Compute discovery-layer score for recall and shortlist ranking."""
        score = 0.0

        if candidate.seed_type == "historical":
            score += 32
        elif candidate.seed_type == "explicit":
            score += 30
        elif candidate.seed_type == "category":
            score += 24
        elif candidate.seed_type == "category_hotword":
            score += 20
        elif candidate.seed_type == "seasonal":
            score += 19
        elif candidate.seed_type == "llm":
            score += 18
        elif candidate.seed_type == "image":
            score += 15
        else:
            score += 10

        if candidate.sales_count:
            score += min(candidate.sales_count / 200, 25)

        if candidate.detail_enriched:
            score += 10
        if candidate.description_enriched:
            score += 3
        if candidate.main_image_url:
            score += 4
        if candidate.image_urls:
            score += 3
        if candidate.detail_image_urls:
            score += 2
        if candidate.category_name:
            score += 3

        if candidate.rating is not None:
            score += float(candidate.rating) * 1.5
        if candidate.review_count:
            score += min(candidate.review_count / 20, 6)

        if not candidate.detail_url:
            score -= 5

        return score

    def _score_business_candidate(
        self,
        candidate: Alibaba1688Candidate,
        *,
        price_min_cny: float | None,
        price_max_cny: float | None,
    ) -> float:
        """Compute business-layer score for final ranking."""
        score = 0.0

        price = candidate.price_cny_min or candidate.price_cny_max
        if price is None:
            score -= 6
        else:
            score += self._score_price_band_fit(price, price_min_cny=price_min_cny, price_max_cny=price_max_cny)

        score += self._score_moq_fit(candidate.moq)
        score += self._score_freight_fit(price=price, freight_cny=candidate.freight_cny)
        score += self._score_supply_identity(candidate)
        score += self._score_review_risk(candidate)
        score += self._score_shop_intelligence(candidate)
        score += self._score_historical_feedback_prior(candidate)

        supplier_candidates = self._build_supplier_candidates(candidate)
        score += self._score_supplier_candidates_quality(supplier_candidates)

        return score

    def _score_historical_feedback_prior(self, candidate: Alibaba1688Candidate) -> float:
        """Score historical feedback prior for seed, shop, and supplier."""
        candidate.historical_seed_prior = 0.0
        candidate.historical_shop_prior = 0.0
        candidate.historical_supplier_prior = 0.0
        candidate.historical_feedback_score = 0.0

        if not self.settings.tmapi_1688_enable_historical_feedback:
            return 0.0
        if self._feedback_aggregator is None:
            return 0.0

        score = 0.0

        if candidate.matched_keyword and candidate.seed_type:
            candidate.historical_seed_prior = self._feedback_aggregator.get_seed_performance_prior(
                seed=candidate.matched_keyword,
                seed_type=candidate.seed_type,
            )
            score += candidate.historical_seed_prior

        if candidate.shop_name:
            candidate.historical_shop_prior = self._feedback_aggregator.get_shop_performance_prior(
                shop_name=candidate.shop_name,
            )
            score += candidate.historical_shop_prior

        supplier_candidates = self._build_supplier_candidates(candidate)
        if supplier_candidates:
            best_supplier_prior = 0.0
            for supplier in supplier_candidates:
                supplier_prior = self._feedback_aggregator.get_supplier_performance_prior(
                    supplier_name=str(supplier.get("supplier_name") or ""),
                    supplier_url=str(supplier.get("supplier_url") or ""),
                )
                best_supplier_prior = max(best_supplier_prior, supplier_prior)
            candidate.historical_supplier_prior = best_supplier_prior
            score += best_supplier_prior

        candidate.historical_feedback_score = score
        return score

    def _score_price_band_fit(
        self,
        price: Decimal,
        *,
        price_min_cny: float | None,
        price_max_cny: float | None,
    ) -> float:
        """Score how well the candidate price fits the requested band."""
        if price_min_cny is None and price_max_cny is None:
            return 2.0

        if self._price_in_range(price, price_min_cny, price_max_cny):
            return 14.0

        if price_min_cny is not None and price < Decimal(str(price_min_cny)):
            gap_ratio = self._relative_gap(reference=Decimal(str(price_min_cny)), value=price)
            return 4.0 if gap_ratio <= Decimal("0.20") else -2.0

        if price_max_cny is not None and price > Decimal(str(price_max_cny)):
            gap_ratio = self._relative_gap(reference=Decimal(str(price_max_cny)), value=price)
            if gap_ratio <= Decimal("0.10"):
                return -4.0
            if gap_ratio <= Decimal("0.30"):
                return -10.0
            return -18.0

        return 0.0

    def _score_moq_fit(self, moq: int | None) -> float:
        """Score MOQ suitability for cross-border validation."""
        if moq is None:
            return -2.0
        if 1 <= moq <= 20:
            return 10.0
        if moq <= 50:
            return 6.0
        if moq <= 200:
            return -1.0
        return -10.0

    def _score_freight_fit(self, *, price: Decimal | None, freight_cny: Decimal | None) -> float:
        """Score freight pressure relative to product price."""
        if price is None:
            return 0.0
        if freight_cny is None:
            return 0.0
        if price <= 0:
            return -4.0

        ratio = freight_cny / price
        if ratio <= Decimal("0.20"):
            return 6.0
        if ratio <= Decimal("0.50"):
            return 1.0
        if ratio <= Decimal("1.00"):
            return -6.0
        return -12.0

    def _score_supply_identity(self, candidate: Alibaba1688Candidate) -> float:
        """Score supplier identity completeness and trust signals."""
        score = 0.0

        if candidate.shop_name:
            score += 2.0
        if candidate.company_name:
            score += 3.0
        if candidate.member_id:
            score += 2.0
        if candidate.shop_url:
            score += 2.0
        if candidate.is_factory_result:
            score += 4.0
        if candidate.is_super_factory:
            score += 3.0
        if candidate.verified_supplier:
            score += 3.0
        if candidate.support_dropshipping:
            score += 2.0

        return score

    def _score_supplier_candidates_quality(self, supplier_candidates: list[dict[str, Any]]) -> float:
        """Score whether supplier candidates provide credible fulfillment paths."""
        if not supplier_candidates:
            return -5.0

        best_score = 0.0
        for supplier in supplier_candidates:
            supplier_score = 3.0
            if supplier.get("supplier_name"):
                supplier_score += 2.0
            if supplier.get("supplier_url"):
                supplier_score += 1.5
            if supplier.get("supplier_sku"):
                supplier_score += 1.0
            if supplier.get("supplier_price") is not None:
                supplier_score += 1.5
            if supplier.get("moq") is not None:
                supplier_score += 1.0

            confidence = supplier.get("confidence_score")
            confidence_decimal = self._parse_decimal(confidence)
            if confidence_decimal is not None:
                supplier_score += float(confidence_decimal) * 4

            raw_payload = supplier.get("raw_payload") or {}
            if self._extract_bool(raw_payload.get("is_factory_result")):
                supplier_score += 1.5
            if self._extract_bool(raw_payload.get("is_super_factory")):
                supplier_score += 1.0
            if self._extract_bool(raw_payload.get("verified_supplier")):
                supplier_score += 1.0

            best_score = max(best_score, supplier_score)

        return best_score

    def _to_product_data(self, candidate: Alibaba1688Candidate) -> ProductData:
        """Convert internal candidate to ProductData for downstream pipeline consumption."""
        platform_price_cny = candidate.price_cny_min or candidate.price_cny_max
        platform_price_usd = self._cny_to_usd(platform_price_cny)
        supplier_candidates = self._build_supplier_candidates(candidate)
        normalized_attributes = {
            "category_name": candidate.category_name,
            "detail_url": candidate.detail_url,
            "shop_url": candidate.shop_url,
            "main_image_url": candidate.main_image_url,
            "image_urls": candidate.image_urls,
            "detail_image_urls": candidate.detail_image_urls,
            "price_cny_min": self._decimal_to_float(candidate.price_cny_min),
            "price_cny_max": self._decimal_to_float(candidate.price_cny_max),
            "sales_count": candidate.sales_count,
            "moq": candidate.moq,
            "member_id": candidate.member_id,
            "seller_id": candidate.seller_id,
            "shop_name": candidate.shop_name,
            "company_name": candidate.company_name,
            "location_str": candidate.location_str,
            "support_dropshipping": candidate.support_dropshipping,
            "verified_supplier": candidate.verified_supplier,
            "is_factory_result": candidate.is_factory_result,
            "is_super_factory": candidate.is_super_factory,
            "matched_keyword": candidate.matched_keyword,
            "seed_type": candidate.seed_type,
            "detail_enriched": candidate.detail_enriched,
            "description_enriched": candidate.description_enriched,
            "freight_cny": self._decimal_to_float(candidate.freight_cny),
            "shipping_province": candidate.shipping_province,
            "shop_item_count": candidate.shop_item_count,
            "review_count": candidate.review_count,
            "review_sample": candidate.review_sample,
            "review_defect_flags": candidate.review_defect_flags,
            "review_risk_score": candidate.review_risk_score,
            "shop_focus_ratio": candidate.shop_focus_ratio,
            "shop_intelligence_score": candidate.shop_intelligence_score,
            "historical_seed_prior": candidate.historical_seed_prior,
            "historical_shop_prior": candidate.historical_shop_prior,
            "historical_supplier_prior": candidate.historical_supplier_prior,
            "historical_feedback_score": candidate.historical_feedback_score,
            "source_endpoints": candidate.source_endpoints,
            "discovery_score": candidate.discovery_score,
            "business_score": candidate.business_score,
            "final_score": candidate.final_score,
        }

        return ProductData(
            source_platform=SourcePlatform.ALIBABA_1688,
            source_product_id=candidate.item_id,
            source_url=candidate.detail_url or self._extract_detail_url({}, candidate.item_id),
            title=candidate.title,
            category=candidate.category_name,
            currency="USD",
            platform_price=platform_price_usd,
            sales_count=candidate.sales_count,
            rating=candidate.rating,
            main_image_url=candidate.main_image_url,
            raw_payload={
                **candidate.raw_payload,
                "source_endpoints": candidate.source_endpoints,
                "matched_keyword": candidate.matched_keyword,
                "seed_type": candidate.seed_type,
                "is_factory_result": candidate.is_factory_result,
                "is_super_factory": candidate.is_super_factory,
            },
            normalized_attributes=normalized_attributes,
            supplier_candidates=supplier_candidates,
        )

    def _build_supplier_candidates(self, candidate: Alibaba1688Candidate) -> list[dict]:
        """Build a 3-5 supplier competition set for the candidate when possible."""
        competition_set_size = max(1, self.settings.tmapi_1688_supplier_competition_set_size)
        suppliers: list[dict] = []
        seen_skus: set[str] = set()

        primary_supplier = self._candidate_to_supplier_dict(candidate)
        primary_supplier_confidence: Decimal | None = None
        primary_supplier_sku: str | None = None
        if primary_supplier:
            suppliers.append(primary_supplier)
            primary_supplier_sku = str(primary_supplier["supplier_sku"])
            primary_supplier_confidence = self._parse_decimal(primary_supplier.get("confidence_score"))
            seen_skus.add(primary_supplier_sku)

        if len(suppliers) < competition_set_size:
            similar_candidates = self._find_similar_candidates_in_recall(
                candidate,
                limit=max(competition_set_size - len(suppliers), 0),
            )
            for similar_candidate, similarity_score in similar_candidates:
                supplier = self._candidate_to_supplier_dict(
                    similar_candidate,
                    similarity_score=similarity_score,
                )
                if not supplier:
                    continue
                supplier_sku = str(supplier["supplier_sku"])
                if supplier_sku in seen_skus:
                    continue
                suppliers.append(supplier)
                seen_skus.add(supplier_sku)
                if len(suppliers) >= competition_set_size:
                    break

        if len(suppliers) < competition_set_size:
            shop_suppliers = self._extract_suppliers_from_shop_items(
                candidate,
                limit=competition_set_size - len(suppliers),
            )
            for supplier in shop_suppliers:
                supplier_sku = str(supplier["supplier_sku"])
                if supplier_sku in seen_skus:
                    continue
                suppliers.append(supplier)
                seen_skus.add(supplier_sku)
                if len(suppliers) >= competition_set_size:
                    break

        if primary_supplier_confidence is not None and primary_supplier_sku is not None:
            epsilon = Decimal("0.0001")
            for supplier in suppliers:
                supplier_sku = str(supplier.get("supplier_sku") or "")
                if supplier_sku == primary_supplier_sku:
                    continue
                supplier_confidence = self._parse_decimal(supplier.get("confidence_score"))
                if supplier_confidence is None:
                    continue
                if supplier_confidence >= primary_supplier_confidence:
                    supplier["confidence_score"] = max(primary_supplier_confidence - epsilon, Decimal("0"))

        suppliers.sort(
            key=lambda item: (
                item.get("confidence_score") is not None,
                item.get("confidence_score") or Decimal("0"),
            ),
            reverse=True,
        )
        return suppliers[:competition_set_size]

    def _candidate_to_supplier_dict(
        self,
        candidate: Alibaba1688Candidate,
        *,
        similarity_score: float | None = None,
    ) -> dict[str, Any] | None:
        """Convert an Alibaba1688 candidate into the stable supplier_candidates payload shape."""
        supplier_name = self._first_non_empty(candidate.company_name, candidate.shop_name)
        supplier_url = self._first_non_empty(candidate.shop_url, candidate.detail_url)
        supplier_sku = self._stringify(candidate.item_id)
        if not supplier_sku or (not supplier_name and not supplier_url):
            return None

        if similarity_score is None:
            confidence = self._compute_primary_supplier_confidence(candidate)
        else:
            confidence = self._compute_competitor_supplier_confidence(candidate, similarity_score)

        raw_payload = {
            "source_platform": SourcePlatform.ALIBABA_1688.value,
            "member_id": candidate.member_id,
            "seller_id": candidate.seller_id,
            "shop_url": candidate.shop_url,
            "shop_name": candidate.shop_name,
            "company_name": candidate.company_name,
            "location_str": candidate.location_str,
            "is_factory_result": candidate.is_factory_result,
            "is_super_factory": candidate.is_super_factory,
            "verified_supplier": candidate.verified_supplier,
            "support_dropshipping": candidate.support_dropshipping,
            "shop_item_count": candidate.shop_item_count,
            "review_count": candidate.review_count,
            "source_endpoints": candidate.source_endpoints,
        }
        if similarity_score is not None:
            raw_payload["similarity_score"] = round(similarity_score, 4)
            raw_payload["competition_source"] = self._resolve_competition_source(candidate)

        return {
            "supplier_name": supplier_name or f"1688 Supplier {supplier_sku}",
            "supplier_url": supplier_url,
            "supplier_sku": supplier_sku,
            "supplier_price": self._cny_to_usd(candidate.price_cny_min or candidate.price_cny_max),
            "moq": candidate.moq,
            "confidence_score": confidence,
            "raw_payload": raw_payload,
        }

    def _compute_primary_supplier_confidence(self, candidate: Alibaba1688Candidate) -> Decimal:
        """Compute confidence for the candidate's own supplier record."""
        confidence = Decimal("0.76")
        if candidate.is_factory_result:
            confidence += Decimal("0.08")
        if candidate.is_super_factory:
            confidence += Decimal("0.04")
        if candidate.verified_supplier:
            confidence += Decimal("0.04")
        if candidate.review_count:
            confidence += Decimal("0.03")
        return min(confidence, Decimal("0.95"))

    def _compute_competitor_supplier_confidence(
        self,
        candidate: Alibaba1688Candidate,
        similarity_score: float,
    ) -> Decimal:
        """Compute confidence for a competing supplier from the recall pool."""
        confidence = Decimal("0.55") + (Decimal(str(similarity_score)) * Decimal("0.30"))
        if "search_items_by_image" in candidate.source_endpoints:
            confidence += Decimal("0.03")
        if candidate.is_factory_result:
            confidence += Decimal("0.03")
        if candidate.is_super_factory:
            confidence += Decimal("0.02")
        if candidate.verified_supplier:
            confidence += Decimal("0.02")
        return min(confidence, Decimal("0.85"))

    def _resolve_competition_source(self, candidate: Alibaba1688Candidate) -> str:
        """Resolve the dominant source lane for a competing supplier."""
        if "search_items_by_image" in candidate.source_endpoints:
            return "image_recall"
        if "search_items_factory" in candidate.source_endpoints:
            return "factory_recall"
        if "search_items_sales" in candidate.source_endpoints:
            return "sales_recall"
        return "keyword_recall"

    def _titles_are_similar(self, title1: str | None, title2: str | None) -> bool:
        """Determine whether two titles are conservatively similar enough to compete."""
        if not title1 or not title2:
            return False

        normalized_1 = self._normalize_title_for_diversity(title1)
        normalized_2 = self._normalize_title_for_diversity(title2)
        if not normalized_1 or not normalized_2:
            return False
        if normalized_1 == normalized_2:
            return True
        if normalized_1 in normalized_2 or normalized_2 in normalized_1:
            return True
        return False

    def _images_are_similar(
        self,
        candidate1: Alibaba1688Candidate,
        candidate2: Alibaba1688Candidate,
    ) -> bool:
        """Determine whether two candidates share the same normalized image cluster."""
        image_keys_1 = set(self._resolve_image_cluster_keys(candidate1))
        image_keys_2 = set(self._resolve_image_cluster_keys(candidate2))
        return bool(image_keys_1 & image_keys_2)

    def _price_ranges_overlap(
        self,
        candidate1: Alibaba1688Candidate,
        candidate2: Alibaba1688Candidate,
    ) -> bool:
        """Determine whether two candidates have overlapping CNY price ranges."""
        price1_min = candidate1.price_cny_min or candidate1.price_cny_max
        price1_max = candidate1.price_cny_max or candidate1.price_cny_min
        price2_min = candidate2.price_cny_min or candidate2.price_cny_max
        price2_max = candidate2.price_cny_max or candidate2.price_cny_min

        if not all([price1_min, price1_max, price2_min, price2_max]):
            return False
        return not (price1_max < price2_min or price2_max < price1_min)

    def _find_similar_candidates_in_recall(
        self,
        candidate: Alibaba1688Candidate,
        *,
        limit: int,
    ) -> list[tuple[Alibaba1688Candidate, float]]:
        """Find similar candidates in the recall pool for multi-supplier competition sets."""
        if limit <= 0 or not self._recall_pool:
            return []

        threshold = max(0.0, min(1.0, self.settings.tmapi_1688_supplier_similarity_threshold))
        similar: list[tuple[Alibaba1688Candidate, float]] = []

        for other_id, other in self._recall_pool.items():
            if other_id == candidate.item_id:
                continue

            similarity_score = 0.0
            if self._titles_are_similar(candidate.title, other.title):
                similarity_score += 0.5
            if self._images_are_similar(candidate, other):
                similarity_score += 0.3
            if self._price_ranges_overlap(candidate, other):
                similarity_score += 0.2
            if "search_items_by_image" in other.source_endpoints:
                similarity_score += 0.05

            if similarity_score >= threshold:
                similar.append((other, similarity_score))

        similar.sort(
            key=lambda item: (
                item[1],
                "search_items_by_image" in item[0].source_endpoints,
                item[0].final_score,
                item[0].discovery_score,
            ),
            reverse=True,
        )
        return similar[:limit]

    def _extract_suppliers_from_shop_items(
        self,
        candidate: Alibaba1688Candidate,
        *,
        limit: int,
    ) -> list[dict[str, Any]]:
        """Extract fallback supplier candidates from same-shop items already present in raw payload."""
        if limit <= 0:
            return []

        shop_items_payload = candidate.raw_payload.get("shop_items_payload") or {}
        products = shop_items_payload.get("products") or []
        suppliers: list[dict[str, Any]] = []
        seen_skus: set[str] = set()

        for raw in products:
            if not isinstance(raw, dict):
                continue
            item_id = self._extract_item_id(raw)
            if not item_id or item_id == candidate.item_id or item_id in seen_skus:
                continue

            supplier_name = self._first_non_empty(candidate.company_name, candidate.shop_name)
            supplier_url = self._first_non_empty(candidate.shop_url, candidate.detail_url)
            if not supplier_name and not supplier_url:
                continue

            suppliers.append(
                {
                    "supplier_name": supplier_name or f"1688 Supplier {item_id}",
                    "supplier_url": supplier_url,
                    "supplier_sku": item_id,
                    "supplier_price": self._cny_to_usd(self._extract_price_min(raw) or self._extract_price_max(raw)),
                    "moq": self._extract_moq(raw),
                    "confidence_score": Decimal("0.70"),
                    "raw_payload": {
                        "source_platform": SourcePlatform.ALIBABA_1688.value,
                        "member_id": candidate.member_id,
                        "seller_id": candidate.seller_id,
                        "shop_url": candidate.shop_url,
                        "shop_name": candidate.shop_name,
                        "company_name": candidate.company_name,
                        "alternative_sku": True,
                        "source_endpoints": ["shop_items"],
                    },
                }
            )
            seen_skus.add(item_id)
            if len(suppliers) >= limit:
                break

        return suppliers

    def _extract_item_id(self, raw: dict[str, Any]) -> str | None:
        """Extract stable 1688 item id from payload."""
        item_id = self._first_non_empty(raw.get("item_id"), raw.get("offer_id"), raw.get("num_iid"), raw.get("product_id"))
        return self._stringify(item_id)

    def _extract_title(self, raw: dict[str, Any]) -> str | None:
        """Extract title from payload."""
        title = self._first_non_empty(raw.get("title"), raw.get("title_origin"), raw.get("name"), raw.get("subject"))
        return str(title).strip() if title else None

    def _extract_detail_url(self, raw: dict[str, Any], item_id: str) -> str:
        """Extract or synthesize detail URL."""
        detail_url = self._first_non_empty(raw.get("product_url"), raw.get("detail_url"), raw.get("offer_url"), raw.get("url"))
        return str(detail_url) if detail_url else f"https://detail.1688.com/offer/{item_id}.html"

    def _extract_shop_url(self, raw: dict[str, Any]) -> str | None:
        """Extract shop URL from payload."""
        shop_url = self._first_non_empty(raw.get("shop_url"), raw.get("store_url"), raw.get("seller_url"))
        return str(shop_url) if shop_url else None

    def _extract_image_urls(self, raw: dict[str, Any]) -> list[str]:
        """Extract image URLs from payload."""
        urls: list[str] = []
        for key in ("main_imgs", "detail_imgs", "item_imgs", "images", "image_list"):
            images = raw.get(key)
            if isinstance(images, list):
                for image in images:
                    if isinstance(image, dict):
                        url = self._first_non_empty(image.get("url"), image.get("img"), image.get("image"))
                        if url:
                            urls.append(str(url))
                    elif isinstance(image, str) and image:
                        urls.append(str(image))
        main_image = self._first_non_empty(raw.get("img"), raw.get("image_url"), raw.get("pic_url"))
        if main_image:
            main_image_str = str(main_image)
            if main_image_str not in urls:
                urls.insert(0, main_image_str)
        deduped: list[str] = []
        seen: set[str] = set()
        for url in urls:
            normalized = url.strip()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            deduped.append(normalized)
        return deduped

    def _extract_price_min(self, raw: dict[str, Any]) -> Decimal | None:
        """Extract minimum CNY price."""
        price = raw.get("price") or raw.get("sale_price") or raw.get("zk_price")
        parsed_price = self._parse_decimal(price)
        if parsed_price is not None:
            return parsed_price

        price_range = raw.get("price_range") or raw.get("priceRange")
        if isinstance(price_range, dict):
            return self._parse_decimal(
                self._first_non_empty(price_range.get("min"), price_range.get("start"), price_range.get("price"))
            )
        if isinstance(price_range, str):
            values = self._extract_decimal_values(price_range)
            return values[0] if values else None

        prices = raw.get("prices")
        if isinstance(prices, list) and prices:
            parsed_values = [self._parse_decimal(value) for value in prices]
            parsed_values = [value for value in parsed_values if value is not None]
            if parsed_values:
                return min(parsed_values)

        return None

    def _extract_price_max(self, raw: dict[str, Any]) -> Decimal | None:
        """Extract maximum CNY price."""
        price_range = raw.get("price_range") or raw.get("priceRange")
        if isinstance(price_range, dict):
            return self._parse_decimal(
                self._first_non_empty(price_range.get("max"), price_range.get("end"), price_range.get("price"))
            )
        if isinstance(price_range, str):
            values = self._extract_decimal_values(price_range)
            return values[-1] if values else self._extract_price_min(raw)

        prices = raw.get("prices")
        if isinstance(prices, list) and prices:
            parsed_values = [self._parse_decimal(value) for value in prices]
            parsed_values = [value for value in parsed_values if value is not None]
            if parsed_values:
                return max(parsed_values)

        return self._extract_price_min(raw)

    def _extract_sales(self, raw: dict[str, Any]) -> int | None:
        """Extract sales count from payload."""
        sales = self._first_non_empty(
            raw.get("sale_count"),
            raw.get("sales"),
            raw.get("sold_count"),
            raw.get("sold_quantity"),
            raw.get("quantity_sold"),
            raw.get("monthly_sales"),
            raw.get("sale_num"),
        )
        return self._extract_int(sales)

    def _extract_moq(self, raw: dict[str, Any]) -> int | None:
        """Extract MOQ from payload."""
        moq = self._first_non_empty(
            raw.get("moq"),
            raw.get("min_order_num"),
            raw.get("min_num"),
            raw.get("min_sale_num"),
            raw.get("min_quantity"),
        )
        return self._extract_int(moq)

    def _extract_rating(self, raw: dict[str, Any]) -> Decimal | None:
        """Extract rating from payload."""
        rating = self._first_non_empty(raw.get("rating"), raw.get("score"), raw.get("dsr_score"))
        return self._parse_decimal(rating)

    def _extract_freight(self, raw: dict[str, Any]) -> Decimal | None:
        """Extract freight CNY from shipping payload."""
        return self._parse_decimal(
            self._first_non_empty(raw.get("total_fee"), raw.get("freight"), raw.get("price"), raw.get("first_unit_fee"))
        )

    def _extract_weight(self, raw: dict[str, Any]) -> float | None:
        """Extract weight from detail payload when available."""
        weight = self._first_non_empty(raw.get("weight"), raw.get("total_weight"))
        if weight is None:
            return None
        if isinstance(weight, (int, float)):
            return float(weight)
        if isinstance(weight, str):
            digits = "".join(ch for ch in weight if ch.isdigit() or ch == ".")
            if not digits:
                return None
            try:
                return float(digits)
            except ValueError:
                return None
        return None

    def _extract_int(self, value: Any) -> int | None:
        """Convert API integer-like values when possible."""
        if value is None or value == "":
            return None
        if isinstance(value, bool):
            return int(value)
        if isinstance(value, int):
            return value
        if isinstance(value, float):
            return int(value)
        if isinstance(value, str):
            clean = value.replace(",", "").replace("+", "").strip()
            if not clean:
                return None
            try:
                if "万" in clean:
                    return int(float(clean.replace("万", "")) * 10000)
                return int(float(clean))
            except ValueError:
                return None
        return None

    def _extract_bool(self, value: Any) -> bool:
        """Convert API boolean-like values when possible."""
        if isinstance(value, bool):
            return value
        if isinstance(value, (int, float)):
            return bool(value)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "y"}
        return False

    def _price_in_range(
        self,
        value: Decimal,
        price_min_cny: float | None,
        price_max_cny: float | None,
    ) -> bool:
        """Check whether price is within requested range."""
        if price_min_cny is not None and value < Decimal(str(price_min_cny)):
            return False
        if price_max_cny is not None and value > Decimal(str(price_max_cny)):
            return False
        return True

    def _relative_gap(self, *, reference: Decimal, value: Decimal) -> Decimal:
        """Compute normalized gap between a value and reference."""
        if reference <= 0:
            return Decimal("0")
        return abs(value - reference) / reference

    def _parse_decimal(self, value: Any) -> Decimal | None:
        """Parse decimal-like values from API payloads."""
        if value is None or value == "":
            return None
        if isinstance(value, Decimal):
            return value
        if isinstance(value, (int, float)):
            return Decimal(str(value))
        if isinstance(value, str):
            clean = (
                value.replace(",", "")
                .replace("¥", "")
                .replace("￥", "")
                .replace("元", "")
                .strip()
            )
            if not clean:
                return None
            try:
                return Decimal(clean)
            except Exception:
                values = self._extract_decimal_values(clean)
                return values[0] if values else None
        return None

    def _extract_decimal_values(self, text: str) -> list[Decimal]:
        """Extract decimal numbers from a text fragment."""
        current = ""
        values: list[Decimal] = []
        for char in text:
            if char.isdigit() or char == ".":
                current += char
                continue
            if current:
                try:
                    values.append(Decimal(current))
                except Exception:
                    pass
                current = ""
        if current:
            try:
                values.append(Decimal(current))
            except Exception:
                pass
        return values

    def _normalize_keyword(self, value: str | None) -> str:
        """Normalize keyword strings."""
        return (value or "").strip()

    def _infer_language(self, text: str) -> str:
        """Infer TMAPI language parameter from query text."""
        return "zh" if self._contains_cjk(text) else self.settings.tmapi_1688_search_language

    def _contains_cjk(self, text: str) -> bool:
        """Check whether text contains CJK characters."""
        return any("\u4e00" <= char <= "\u9fff" for char in text or "")

    def _stringify(self, value: Any) -> str | None:
        """Convert a value to string when present."""
        if value in (None, ""):
            return None
        return str(value)

    def _usd_to_cny(self, value: Decimal | None) -> float | None:
        """Convert USD to CNY using the project-fixed estimate."""
        if value is None:
            return None
        return float(value / self.CNY_TO_USD_RATE)

    def _cny_to_usd(self, value: Decimal | None) -> Decimal | None:
        """Convert CNY to USD using the project-fixed estimate."""
        if value is None:
            return None
        return (value * self.CNY_TO_USD_RATE).quantize(Decimal("0.01"))

    def _decimal_to_float(self, value: Decimal | None) -> float | None:
        """Convert Decimal to float for JSON-friendly normalized attributes."""
        return float(value) if value is not None else None

    def _first_non_empty(self, *values: Any) -> Any:
        """Return first non-empty value."""
        for value in values:
            if value not in (None, "", [], {}):
                return value
        return None

    async def close(self) -> None:
        """Close adapter resources."""
        if self._created_sglang_client and self._sglang_client is not None:
            await self._sglang_client.close()
            self._sglang_client = None
            self._created_sglang_client = False
