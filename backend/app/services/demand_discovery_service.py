"""Demand discovery service for unified keyword discovery and validation.

This service orchestrates the complete demand discovery flow:
1. User-provided keywords → validate
2. If user keywords all fail and runtime generation is enabled → generate alternatives → validate
3. If no user keywords → generate trending keywords → validate
4. If generation fails or returns no valid keywords → try fallback seeds → validate
5. Return validated keywords with structured metadata

All 1688 searches MUST go through this service when demand discovery is enabled.
"""
from dataclasses import dataclass
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.services.demand_validator import DemandValidationResult, DemandValidator
from app.services.keyword_generator import KeywordGenerator
from app.services.seed_fallback_provider import SeedFallbackProvider

logger = get_logger(__name__)


@dataclass
class DemandDiscoveryKeyword:
    """A keyword with its demand validation result."""

    keyword: str
    source: str
    validation: Optional[DemandValidationResult]

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "keyword": self.keyword,
            "source": self.source,
            "validation": self.validation.to_dict() if self.validation else None,
        }


@dataclass
class DemandDiscoveryResult:
    """Result of the demand discovery process."""

    validated_keywords: list[DemandDiscoveryKeyword]
    rejected_keywords: list[DemandDiscoveryKeyword]
    discovery_mode: str
    fallback_used: bool
    degraded: bool

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "validated_keywords": [keyword.to_dict() for keyword in self.validated_keywords],
            "rejected_keywords": [keyword.to_dict() for keyword in self.rejected_keywords],
            "discovery_mode": self.discovery_mode,
            "fallback_used": self.fallback_used,
            "degraded": self.degraded,
        }


class DemandDiscoveryService:
    """Unified demand discovery and validation service."""

    def __init__(
        self,
        demand_validator: Optional[DemandValidator] = None,
        keyword_generator: Optional[KeywordGenerator] = None,
        seed_fallback_provider: Optional[SeedFallbackProvider] = None,
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
        self.seed_fallback_provider = seed_fallback_provider or SeedFallbackProvider(
            cold_start_seeds=self.settings.tmapi_1688_cold_start_seeds,
            seasonal_seed_limit=self.settings.tmapi_1688_seasonal_seed_limit,
            category_hotword_limit=self.settings.tmapi_1688_suggest_limit_per_seed,
        )
        self.logger = logger

    async def discover_keywords(
        self,
        *,
        category: Optional[str] = None,
        keywords: Optional[list[str]] = None,
        region: Optional[str] = None,
        platform: Optional[str] = None,
        allow_fallback: bool = True,
        max_keywords: int = 10,
    ) -> DemandDiscoveryResult:
        """Discover and validate keywords for product selection."""
        normalized_region = region or self.settings.keyword_generation_region or "US"
        normalized_keywords = self._normalize_keywords(keywords)

        self.logger.info(
            "demand_discovery_started",
            category=category,
            keywords=normalized_keywords,
            region=normalized_region,
            platform=platform,
            allow_fallback=allow_fallback,
            max_keywords=max_keywords,
            user_keywords_count=len(normalized_keywords),
        )

        accumulated_rejections: list[DemandDiscoveryKeyword] = []

        # 1. Validate user-provided keywords first.
        if normalized_keywords:
            user_result = await self._validate_keywords(
                keywords=normalized_keywords,
                source="user",
                category=category,
                region=normalized_region,
                platform=platform,
                max_keywords=max_keywords,
            )
            if user_result.validated_keywords:
                self.logger.info(
                    "demand_discovery_metrics",
                    category=category,
                    region=normalized_region,
                    platform=platform,
                    discovery_mode=user_result.discovery_mode,
                    success=True,
                    skip=False,
                    fallback_used=user_result.fallback_used,
                    degraded=user_result.degraded,
                    generated_recovery=False,
                    validated_fallback=False,
                    validated_keywords_count=len(user_result.validated_keywords),
                    rejected_keywords_count=len(user_result.rejected_keywords),
                    avg_validated_keywords_count=len(user_result.validated_keywords),
                    discovery_success_rate=1.0,
                    generated_recovery_rate=0.0,
                    validated_fallback_rate=0.0,
                    skip_rate=0.0,
                    selection_triggered_per_category=1,
                )
                return user_result
            accumulated_rejections.extend(user_result.rejected_keywords)

        # 2. Runtime keyword generation.
        if self.settings.product_selection_enable_runtime_keyword_generation:
            generated_result = await self._discover_from_generated_keywords(
                category=category,
                region=normalized_region,
                platform=platform,
                max_keywords=max_keywords,
            )
            if generated_result.validated_keywords:
                result = DemandDiscoveryResult(
                    validated_keywords=generated_result.validated_keywords,
                    rejected_keywords=accumulated_rejections + generated_result.rejected_keywords,
                    discovery_mode=generated_result.discovery_mode,
                    fallback_used=False,
                    degraded=bool(normalized_keywords) or generated_result.degraded,
                )
                self.logger.info(
                    "demand_discovery_metrics",
                    category=category,
                    region=normalized_region,
                    platform=platform,
                    discovery_mode=result.discovery_mode,
                    success=True,
                    skip=False,
                    fallback_used=result.fallback_used,
                    degraded=result.degraded,
                    generated_recovery=bool(normalized_keywords),
                    validated_fallback=False,
                    validated_keywords_count=len(result.validated_keywords),
                    rejected_keywords_count=len(result.rejected_keywords),
                    avg_validated_keywords_count=len(result.validated_keywords),
                    discovery_success_rate=1.0,
                    generated_recovery_rate=1.0 if normalized_keywords else 0.0,
                    validated_fallback_rate=0.0,
                    skip_rate=0.0,
                    selection_triggered_per_category=1,
                )
                return result
            accumulated_rejections.extend(generated_result.rejected_keywords)

        # 3. Validated fallback seeds.
        if allow_fallback and self.settings.product_selection_allow_validated_seed_fallback:
            fallback_result = await self._discover_from_fallback_seeds(
                category=category,
                region=normalized_region,
                platform=platform,
                max_keywords=max_keywords,
            )
            result = DemandDiscoveryResult(
                validated_keywords=fallback_result.validated_keywords,
                rejected_keywords=accumulated_rejections + fallback_result.rejected_keywords,
                discovery_mode=fallback_result.discovery_mode,
                fallback_used=fallback_result.fallback_used,
                degraded=True,
            )
            self.logger.info(
                "demand_discovery_metrics",
                category=category,
                region=normalized_region,
                platform=platform,
                discovery_mode=result.discovery_mode,
                success=bool(result.validated_keywords),
                skip=not bool(result.validated_keywords),
                fallback_used=result.fallback_used,
                degraded=result.degraded,
                generated_recovery=False,
                validated_fallback=bool(result.validated_keywords),
                validated_keywords_count=len(result.validated_keywords),
                rejected_keywords_count=len(result.rejected_keywords),
                avg_validated_keywords_count=len(result.validated_keywords),
                discovery_success_rate=1.0 if result.validated_keywords else 0.0,
                generated_recovery_rate=0.0,
                validated_fallback_rate=1.0 if result.validated_keywords else 0.0,
                skip_rate=1.0 if not result.validated_keywords else 0.0,
                selection_triggered_per_category=1 if result.validated_keywords else 0,
            )
            return result

        # 4. Nothing validated.
        self.logger.warning(
            "demand_discovery_no_valid_keywords",
            category=category,
            region=normalized_region,
            platform=platform,
            rejected=len(accumulated_rejections),
        )
        self.logger.info(
            "demand_discovery_metrics",
            category=category,
            region=normalized_region,
            platform=platform,
            discovery_mode="none",
            success=False,
            skip=True,
            fallback_used=False,
            degraded=True,
            generated_recovery=False,
            validated_fallback=False,
            validated_keywords_count=0,
            rejected_keywords_count=len(accumulated_rejections),
            avg_validated_keywords_count=0,
            discovery_success_rate=0.0,
            generated_recovery_rate=0.0,
            validated_fallback_rate=0.0,
            skip_rate=1.0,
            selection_triggered_per_category=0,
        )
        return DemandDiscoveryResult(
            validated_keywords=[],
            rejected_keywords=accumulated_rejections,
            discovery_mode="none",
            fallback_used=False,
            degraded=True,
        )

    async def _discover_from_generated_keywords(
        self,
        *,
        category: Optional[str],
        region: str,
        platform: Optional[str],
        max_keywords: int,
    ) -> DemandDiscoveryResult:
        """Discover keywords by generating real-time selection keywords."""
        self.logger.info(
            "demand_discovery_generating_keywords",
            category=category,
            region=region,
        )

        try:
            keyword_results = await self.keyword_generator.generate_selection_keywords(
                category=category,
                region=region,
                limit=max_keywords * 2,
                expand_top_n=min(5, max_keywords),
            )
        except Exception as exc:
            self.logger.error(
                "demand_discovery_generation_failed",
                category=category,
                region=region,
                error=str(exc),
            )
            return DemandDiscoveryResult(
                validated_keywords=[],
                rejected_keywords=[],
                discovery_mode="generated",
                fallback_used=False,
                degraded=True,
            )

        if not keyword_results:
            self.logger.warning(
                "demand_discovery_generation_returned_empty",
                category=category,
                region=region,
            )
            return DemandDiscoveryResult(
                validated_keywords=[],
                rejected_keywords=[],
                discovery_mode="generated",
                fallback_used=False,
                degraded=True,
            )

        return await self._validate_keywords(
            keywords=[result.keyword for result in keyword_results],
            source="generated",
            category=category,
            region=region,
            platform=platform,
            max_keywords=max_keywords,
            discovery_mode="generated",
        )

    async def _discover_from_fallback_seeds(
        self,
        *,
        category: Optional[str],
        region: str,
        platform: Optional[str],
        max_keywords: int,
    ) -> DemandDiscoveryResult:
        """Discover keywords from fallback seed candidates and validate them."""
        self.logger.info(
            "demand_discovery_using_fallback_seeds",
            category=category,
            region=region,
        )

        try:
            seed_candidates = await self.seed_fallback_provider.get_candidate_fallback_keywords(
                category=category,
                region=region,
                limit=max_keywords * 2,
            )
        except Exception as exc:
            self.logger.error(
                "demand_discovery_fallback_failed",
                category=category,
                region=region,
                error=str(exc),
            )
            return DemandDiscoveryResult(
                validated_keywords=[],
                rejected_keywords=[],
                discovery_mode="fallback",
                fallback_used=True,
                degraded=True,
            )

        if not seed_candidates:
            return DemandDiscoveryResult(
                validated_keywords=[],
                rejected_keywords=[],
                discovery_mode="fallback",
                fallback_used=True,
                degraded=True,
            )

        source_map = {keyword: f"fallback_{source}" for keyword, source in seed_candidates}
        return await self._validate_keywords(
            keywords=[keyword for keyword, _ in seed_candidates],
            source="fallback",
            category=category,
            region=region,
            platform=platform,
            max_keywords=max_keywords,
            discovery_mode="fallback",
            source_map=source_map,
            fallback_used=True,
            degraded=True,
        )

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

    def _normalize_keywords(self, keywords: Optional[list[str]]) -> list[str]:
        """Normalize, deduplicate, and filter empty keywords."""
        if not keywords:
            return []

        seen: set[str] = set()
        normalized: list[str] = []
        for keyword in keywords:
            candidate = (keyword or "").strip()
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        return normalized
