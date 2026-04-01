"""Demand discovery service for unified keyword discovery and validation.

Opportunity-first facade:
1. Build seed pool from user/category context
2. Legitimize seeds into AlphaShop-valid keywords when available
3. Validate demand quality
4. Return backward-compatible validated_keywords plus rich metadata

All 1688 searches MUST go through this service when demand discovery is enabled.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.demand_validator import DemandValidationResult, DemandValidator
from app.services.keyword_generator import KeywordGenerator
from app.services.keyword_legitimizer import KeywordLegitimizerService, ValidKeyword
from app.services.seed_pool_builder import Seed, SeedPoolBuilderService

logger = get_logger(__name__)


def map_business_platform_to_alphashop(business_platform: Optional[str]) -> str:
    """Map business platform to AlphaShop-supported platform.

    AlphaShop keyword.search and newproduct.report only support:
    - amazon
    - tiktok

    This function maps all business platforms to one of these two.
    """
    if not business_platform:
        return "amazon"

    platform_lower = business_platform.lower().strip()

    # Direct mapping
    if platform_lower in ("amazon", "tiktok"):
        return platform_lower

    # TikTok family
    if platform_lower in ("tiktok_shop",):
        return "tiktok"

    # Everything else defaults to amazon
    # (temu, alibaba_1688, aliexpress, ozon, mercado_libre, rakuten, etc.)
    return "amazon"



@dataclass
class DemandDiscoveryKeyword:
    """A keyword with its demand validation result."""

    keyword: str
    source: str
    validation: Optional[DemandValidationResult]
    metadata: Optional[dict] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        payload = {
            "keyword": self.keyword,
            "source": self.source,
            "validation": self.validation.to_dict() if self.validation else None,
        }
        if self.metadata is not None:
            payload["metadata"] = self.metadata
        return payload


@dataclass
class DemandDiscoveryResult:
    """Result of the demand discovery process."""

    validated_keywords: list[DemandDiscoveryKeyword]
    rejected_keywords: list[DemandDiscoveryKeyword]
    discovery_mode: str
    fallback_used: bool
    degraded: bool
    seeds: list[dict] = field(default_factory=list)
    valid_keywords: list[dict] = field(default_factory=list)
    seed_to_keyword_mapping: list[dict] = field(default_factory=list)
    degraded_reason: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "validated_keywords": [keyword.to_dict() for keyword in self.validated_keywords],
            "rejected_keywords": [keyword.to_dict() for keyword in self.rejected_keywords],
            "discovery_mode": self.discovery_mode,
            "fallback_used": self.fallback_used,
            "degraded": self.degraded,
            "seeds": self.seeds,
            "valid_keywords": self.valid_keywords,
            "seed_to_keyword_mapping": self.seed_to_keyword_mapping,
            "degraded_reason": self.degraded_reason,
        }


class DemandDiscoveryService:
    """Unified demand discovery and validation service."""

    def __init__(
        self,
        demand_validator: Optional[DemandValidator] = None,
        keyword_generator: Optional[KeywordGenerator] = None,
        seed_pool_builder: Optional[SeedPoolBuilderService] = None,
        keyword_legitimizer: Optional[KeywordLegitimizerService] = None,
    ):
        self.settings = get_settings().model_copy(deep=True)
        self.demand_validator = demand_validator or DemandValidator(
            min_search_volume=self.settings.demand_validation_min_search_volume,
            use_helium10=self.settings.demand_validation_use_helium10,
            helium10_api_key=self.settings.demand_validation_helium10_api_key or None,
            cache_ttl_seconds=self.settings.demand_validation_cache_ttl_seconds,
            enable_cache=self.settings.enable_demand_validation,
        )
        self.keyword_generator = keyword_generator or KeywordGenerator(
            cache_ttl_seconds=self.settings.keyword_generation_cache_ttl_seconds,
            enable_cache=self.settings.enable_keyword_generation,
            min_trend_score=self.settings.keyword_generation_min_trend_score,
        )
        self.seed_pool_builder = seed_pool_builder or SeedPoolBuilderService()
        self.keyword_legitimizer = keyword_legitimizer or KeywordLegitimizerService()
        self.logger = logger

    async def discover_keywords(
        self,
        *,
        category: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        region: Optional[str] = None,
        platform: Optional[str] = None,
        max_keywords: int = 10,
    ) -> DemandDiscoveryResult:
        """Discover and validate keywords for product selection."""
        normalized_region = region or self.settings.keyword_generation_region or "US"
        normalized_platform = map_business_platform_to_alphashop(
            platform or self.settings.keyword_generation_platform
        )
        normalized_keywords = self._normalize_keywords(keywords)

        self.logger.info(
            "demand_discovery_started",
            category=category,
            keywords=normalized_keywords,
            region=normalized_region,
            platform=platform,
            max_keywords=max_keywords,
            user_keywords_count=len(normalized_keywords),
        )

        accumulated_rejections: list[DemandDiscoveryKeyword] = []
        prior_results: list[DemandDiscoveryResult] = []

        # 1. User-provided keywords first: treat them as seeds, not final AlphaShop queries.
        if normalized_keywords:
            user_seeds = [
                Seed(
                    term=keyword,
                    source="user",
                    confidence=1.0,
                    category=category,
                    region=normalized_region,
                    platform=normalized_platform,
                )
                for keyword in normalized_keywords
            ]
            user_result = await self._discover_from_seeds(
                seeds=user_seeds,
                category=category,
                region=normalized_region,
                platform=platform,
                max_keywords=max_keywords,
                discovery_mode="user",
            )
            if user_result.validated_keywords:
                self._log_metrics(
                    category=category,
                    region=normalized_region,
                    platform=platform,
                    result=user_result,
                    success=True,
                    skip=False,
                    generated_recovery=False,
                )
                return user_result

            accumulated_rejections.extend(user_result.rejected_keywords)
            prior_results.append(user_result)

        # 2. Runtime generation / seed expansion.
        if self.settings.product_selection_enable_runtime_keyword_generation:
            generated_result = await self._discover_from_generated_keywords(
                category=category,
                region=normalized_region,
                platform=platform,
                max_keywords=max_keywords,
            )
            if generated_result.validated_keywords:
                merged_result = self._merge_results(
                    discovery_mode=generated_result.discovery_mode,
                    fallback_used=False,
                    degraded=bool(normalized_keywords) or generated_result.degraded,
                    results=prior_results + [generated_result],
                    rejected_keywords=accumulated_rejections + generated_result.rejected_keywords,
                )
                self._log_metrics(
                    category=category,
                    region=normalized_region,
                    platform=platform,
                    result=merged_result,
                    success=True,
                    skip=False,
                    generated_recovery=bool(normalized_keywords),
                )
                return merged_result

            accumulated_rejections.extend(generated_result.rejected_keywords)
            prior_results.append(generated_result)

        # 3. Nothing validated.
        self.logger.warning(
            "demand_discovery_no_valid_keywords",
            category=category,
            region=normalized_region,
            platform=platform,
            rejected=len(accumulated_rejections),
        )

        final_result = self._merge_results(
            discovery_mode="none",
            fallback_used=False,
            degraded=True,
            results=prior_results,
            rejected_keywords=accumulated_rejections,
            degraded_reason=self._first_degraded_reason(prior_results) or "no_valid_keywords",
        )
        self._log_metrics(
            category=category,
            region=normalized_region,
            platform=platform,
            result=final_result,
            success=False,
            skip=True,
            generated_recovery=False,
        )
        return final_result

    async def _discover_from_generated_keywords(
        self,
        *,
        category: Optional[str],
        region: str,
        platform: Optional[str],
        max_keywords: int,
    ) -> DemandDiscoveryResult:
        """Discover keywords by seed pool building plus optional legacy keyword expansion."""
        self.logger.info(
            "demand_discovery_generating_keywords",
            category=category,
            region=region,
        )

        base_seeds = await self.seed_pool_builder.build_seed_pool(
            category=category,
            user_keywords=None,
            region=region,
            platform=platform,
            max_seeds=max_keywords * 2,
        )

        generated_seeds: list[Seed] = []
        try:
            keyword_results = await self.keyword_generator.generate_selection_keywords(
                category=category,
                region=region,
                limit=max_keywords * 2,
                expand_top_n=min(5, max_keywords),
            )
            for result in keyword_results:
                generated_seeds.append(
                    Seed(
                        term=result.keyword,
                        source="generated",
                        confidence=0.6,
                        category=category,
                        region=region,
                        platform=platform,
                    )
                )
        except Exception as exc:
            self.logger.warning(
                "demand_discovery_generation_failed",
                category=category,
                region=region,
                error=str(exc),
            )

        seeds_for_discovery = generated_seeds or base_seeds
        all_metadata_seeds = self._merge_seed_lists(base_seeds, generated_seeds)

        if not seeds_for_discovery:
            return DemandDiscoveryResult(
                validated_keywords=[],
                rejected_keywords=[],
                discovery_mode="generated",
                fallback_used=False,
                degraded=True,
                seeds=[seed.to_dict() for seed in all_metadata_seeds],
                valid_keywords=[],
                seed_to_keyword_mapping=[],
                degraded_reason="no_seed_candidates_available",
            )

        result = await self._discover_from_seeds(
            seeds=seeds_for_discovery,
            category=category,
            region=region,
            platform=platform,
            max_keywords=max_keywords,
            discovery_mode="generated",
            degraded=not bool(generated_seeds),
            degraded_reason=None if generated_seeds else "seed_pool_only",
        )
        result.seeds = [seed.to_dict() for seed in all_metadata_seeds]
        return result

    async def _discover_from_seeds(
        self,
        *,
        seeds: list[Seed],
        category: Optional[str],
        region: str,
        platform: Optional[str],
        max_keywords: int,
        discovery_mode: str,
        fallback_used: bool = False,
        degraded: bool = False,
        degraded_reason: Optional[str] = None,
    ) -> DemandDiscoveryResult:
        """Run opportunity-first discovery front-half: seed -> legitimized keyword -> validation."""
        serialized_seeds = [seed.to_dict() for seed in seeds]

        valid_keyword_results = await self.keyword_legitimizer.legitimize_seeds(
            seeds=seeds,
            region=region,
            platform=map_business_platform_to_alphashop(
                platform or self.settings.keyword_generation_platform
            ),
        )
        valid_keyword_payload = [item.to_dict() for item in valid_keyword_results]
        mapping_payload = [
            {
                "seed": item.seed.to_dict(),
                "matched_keyword": item.matched_keyword,
                "match_type": item.match_type,
                "is_valid_for_report": item.is_valid_for_report,
            }
            for item in valid_keyword_results
        ]

        report_safe_keywords = [
            item for item in valid_keyword_results if item.is_valid_for_report and item.matched_keyword
        ]

        if report_safe_keywords:
            validated, rejected = await self._validate_legitimized_keywords(
                valid_keywords=report_safe_keywords,
                category=category,
                region=region,
                platform=platform,
                max_keywords=max_keywords,
                discovery_mode=discovery_mode,
                fallback_used=fallback_used,
                degraded=degraded,
            )
            return DemandDiscoveryResult(
                validated_keywords=validated,
                rejected_keywords=rejected,
                discovery_mode=discovery_mode,
                fallback_used=fallback_used,
                degraded=degraded,
                seeds=serialized_seeds,
                valid_keywords=valid_keyword_payload,
                seed_to_keyword_mapping=mapping_payload,
                degraded_reason=degraded_reason,
            )

        # Compatibility fallback: if legitimization is unavailable, validate seeds directly.
        direct_result = await self._validate_keywords(
            keywords=[seed.term for seed in seeds],
            source=discovery_mode,
            category=category,
            region=region,
            platform=platform,
            max_keywords=max_keywords,
            discovery_mode=discovery_mode,
            source_map={seed.term: seed.source for seed in seeds},
            fallback_used=fallback_used,
            degraded=True,
            metadata_map={},
        )
        direct_result.seeds = serialized_seeds
        direct_result.valid_keywords = valid_keyword_payload
        direct_result.seed_to_keyword_mapping = mapping_payload
        direct_result.degraded_reason = degraded_reason or "no_report_safe_keywords"
        return direct_result

    async def _validate_legitimized_keywords(
        self,
        *,
        valid_keywords: list[ValidKeyword],
        category: Optional[str],
        region: str,
        platform: Optional[str],
        max_keywords: int,
        discovery_mode: str,
        fallback_used: bool,
        degraded: bool,
    ) -> tuple[list[DemandDiscoveryKeyword], list[DemandDiscoveryKeyword]]:
        """Validate already-legitimized keywords, avoiding duplicate discovery calls when possible."""
        metadata_map = {item.matched_keyword: item.to_dict() for item in valid_keywords}
        source_map = {item.matched_keyword: item.seed.source for item in valid_keywords}

        if isinstance(self.demand_validator, DemandValidator):
            validation_results = await self.demand_validator.validate_legitimized_batch(
                valid_keywords=valid_keywords,
                category=category,
                region=region,
                platform=platform,
            )
        else:
            validation_results = await self.demand_validator.validate_batch(
                keywords=[item.matched_keyword for item in valid_keywords],
                category=category,
                region=region,
                platform=platform,
            )

        validated: list[DemandDiscoveryKeyword] = []
        rejected: list[DemandDiscoveryKeyword] = []
        for result in validation_results:
            keyword_source = source_map.get(result.keyword, discovery_mode)
            keyword_result = DemandDiscoveryKeyword(
                keyword=result.keyword,
                source=keyword_source,
                validation=result,
                metadata=metadata_map.get(result.keyword),
            )
            if result.passed:
                validated.append(keyword_result)
            else:
                rejected.append(keyword_result)

        return validated[:max_keywords], rejected

    async def _validate_keywords(
        self,
        *,
        keywords: list[str],
        source: str,
        category: Optional[str],
        region: str,
        platform: Optional[str] = None,
        max_keywords: int,
        discovery_mode: Optional[str] = None,
        source_map: Optional[dict[str, str]] = None,
        fallback_used: bool = False,
        degraded: bool = False,
        metadata_map: Optional[dict[str, dict]] = None,
    ) -> DemandDiscoveryResult:
        """Validate a set of keywords and split them into passed/failed lists."""
        if not keywords:
            return DemandDiscoveryResult(
                validated_keywords=[],
                rejected_keywords=[],
                discovery_mode=discovery_mode or source,
                fallback_used=fallback_used,
                degraded=degraded,
            )

        validation_results = await self.demand_validator.validate_batch(
            keywords=keywords,
            category=category,
            region=region,
            platform=platform,
        )

        validated: list[DemandDiscoveryKeyword] = []
        rejected: list[DemandDiscoveryKeyword] = []

        for result in validation_results:
            keyword_source = source_map.get(result.keyword, source) if source_map else source
            keyword_result = DemandDiscoveryKeyword(
                keyword=result.keyword,
                source=keyword_source,
                validation=result,
                metadata=(metadata_map or {}).get(result.keyword),
            )
            if result.passed:
                validated.append(keyword_result)
            else:
                rejected.append(keyword_result)

        return DemandDiscoveryResult(
            validated_keywords=validated[:max_keywords],
            rejected_keywords=rejected,
            discovery_mode=discovery_mode or source,
            fallback_used=fallback_used,
            degraded=degraded,
        )

    def _merge_results(
        self,
        *,
        discovery_mode: str,
        fallback_used: bool,
        degraded: bool,
        results: list[DemandDiscoveryResult],
        rejected_keywords: list[DemandDiscoveryKeyword],
        degraded_reason: Optional[str] = None,
    ) -> DemandDiscoveryResult:
        """Merge multiple discovery attempts into one final result."""
        validated_keywords: list[DemandDiscoveryKeyword] = []
        seeds: list[dict] = []
        valid_keywords: list[dict] = []
        mappings: list[dict] = []

        seen_validated: set[str] = set()
        seen_seeds: set[tuple[str, str]] = set()
        seen_valid_keyword_rows: set[tuple[str, str]] = set()
        seen_mapping_rows: set[tuple[str, str]] = set()

        for result in results:
            for item in result.validated_keywords:
                key = (item.keyword or "").strip().lower()
                if key and key not in seen_validated:
                    seen_validated.add(key)
                    validated_keywords.append(item)

            for seed in result.seeds:
                seed_term = ((seed or {}).get("term") or "").strip().lower()
                seed_source = ((seed or {}).get("source") or "").strip().lower()
                key = (seed_term, seed_source)
                if seed_term and key not in seen_seeds:
                    seen_seeds.add(key)
                    seeds.append(seed)

            for item in result.valid_keywords:
                matched_keyword = ((item or {}).get("matched_keyword") or "").strip().lower()
                seed_term = (((item or {}).get("seed") or {}).get("term") or "").strip().lower()
                key = (matched_keyword, seed_term)
                if matched_keyword and key not in seen_valid_keyword_rows:
                    seen_valid_keyword_rows.add(key)
                    valid_keywords.append(item)

            for item in result.seed_to_keyword_mapping:
                matched_keyword = ((item or {}).get("matched_keyword") or "").strip().lower()
                seed_term = ((((item or {}).get("seed") or {}).get("term")) or "").strip().lower()
                key = (matched_keyword, seed_term)
                if key not in seen_mapping_rows:
                    seen_mapping_rows.add(key)
                    mappings.append(item)

        return DemandDiscoveryResult(
            validated_keywords=validated_keywords,
            rejected_keywords=rejected_keywords,
            discovery_mode=discovery_mode,
            fallback_used=fallback_used,
            degraded=degraded,
            seeds=seeds,
            valid_keywords=valid_keywords,
            seed_to_keyword_mapping=mappings,
            degraded_reason=degraded_reason,
        )

    def _merge_seed_lists(self, *seed_groups: list[Seed]) -> list[Seed]:
        """Merge seed lists while preserving order and deduplicating."""
        merged: list[Seed] = []
        seen: set[tuple[str, str]] = set()
        for group in seed_groups:
            for seed in group:
                key = (seed.term.strip().lower(), seed.source.strip().lower())
                if key not in seen:
                    seen.add(key)
                    merged.append(seed)
        return merged

    def _first_degraded_reason(self, results: list[DemandDiscoveryResult]) -> Optional[str]:
        """Return first available degraded reason."""
        for result in results:
            if result.degraded_reason:
                return result.degraded_reason
        return None

    def _log_metrics(
        self,
        *,
        category: Optional[str],
        region: str,
        platform: Optional[str],
        result: DemandDiscoveryResult,
        success: bool,
        skip: bool,
        generated_recovery: bool,
    ) -> None:
        """Log discovery metrics in the existing structured format."""
        self.logger.info(
            "demand_discovery_metrics",
            category=category,
            region=region,
            platform=platform,
            discovery_mode=result.discovery_mode,
            success=success,
            skip=skip,
            fallback_used=result.fallback_used,
            degraded=result.degraded,
            generated_recovery=generated_recovery,
            validated_fallback=False,
            validated_keywords_count=len(result.validated_keywords),
            rejected_keywords_count=len(result.rejected_keywords),
            avg_validated_keywords_count=len(result.validated_keywords),
            discovery_success_rate=1.0 if success else 0.0,
            generated_recovery_rate=1.0 if generated_recovery else 0.0,
            validated_fallback_rate=0.0,
            skip_rate=1.0 if skip else 0.0,
            selection_triggered_per_category=0 if skip else 1,
        )

    def _normalize_keywords(self, keywords: Optional[list[str]]) -> list[str]:
        """Normalize, deduplicate, and filter empty keywords."""
        if not keywords:
            return []

        seen: set[str] = set()
        normalized: list[str] = []
        for keyword in keywords:
            candidate = (keyword or "").strip()
            key = candidate.lower()
            if not candidate or key in seen:
                continue
            seen.add(key)
            normalized.append(candidate)
        return normalized
