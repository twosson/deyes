"""Seed pool builder service for seller-first product selection.

Converts category + user keywords into a seed pool for keyword legitimization.

Refactored 2026-04-02: Integrated AlphaShop trending keywords as primary source,
demoted static category seeds to fallback-only.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.seasonal_calendar import get_seasonal_calendar
from app.services.feedback_aggregator import FeedbackAggregator
from app.services.keyword_generator import KeywordGenerator
from app.services.seasonal_seed_expander import SeasonalSeedExpander

logger = get_logger(__name__)


@dataclass
class Seed:
    """A seed keyword candidate for legitimization."""

    term: str
    source: str  # "user" / "alphashop_trending" / "historical" / "seasonal" / "seasonal_llm" / "category_static"
    confidence: float  # 0.0-1.0
    category: Optional[str] = None
    region: Optional[str] = None
    platform: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "term": self.term,
            "source": self.source,
            "confidence": self.confidence,
            "category": self.category,
            "region": self.region,
            "platform": self.platform,
        }


class SeedPoolBuilderService:
    """Build seed pool from category, user keywords, historical data, and seasonal events."""

    # Static category seed mappings (Phase 1 simple rules)
    CATEGORY_SEEDS = {
        "electronics": [
            "wireless charger",
            "phone case",
            "bluetooth speaker",
            "usb cable",
            "power bank",
        ],
        "fashion": [
            "summer dress",
            "running shoes",
            "leather bag",
            "sunglasses",
            "watch",
        ],
        "home": [
            "storage box",
            "led lamp",
            "kitchen organizer",
            "throw pillow",
            "wall art",
        ],
        "beauty": [
            "face cream",
            "makeup brush",
            "hair serum",
            "nail polish",
            "perfume",
        ],
        "sports": [
            "yoga mat",
            "resistance band",
            "water bottle",
            "gym bag",
            "fitness tracker",
        ],
    }

    def __init__(
        self,
        feedback_aggregator: Optional[FeedbackAggregator] = None,
        keyword_generator: Optional[KeywordGenerator] = None,
        seasonal_seed_expander: Optional[SeasonalSeedExpander] = None,
    ):
        self.feedback_aggregator = feedback_aggregator
        self.keyword_generator = keyword_generator or KeywordGenerator()
        self.seasonal_seed_expander = seasonal_seed_expander or SeasonalSeedExpander()
        self.settings = get_settings()
        self.logger = logger

    async def build_seed_pool(
        self,
        *,
        category: Optional[str] = None,
        user_keywords: Optional[list[str]] = None,
        region: Optional[str] = None,
        platform: Optional[str] = None,
        max_seeds: int = 20,
    ) -> list[Seed]:
        """Build seed pool from multiple sources.

        Source priority:
        1. user (1.0) - explicit user intent
        2. historical (0.8) - validated prior winners
        3. alphashop_trending (0.75) - real-time market demand
        4. seasonal (0.7) - event-driven exploration
        5. category_static (0.5) - fallback only when dynamic sources are unavailable
        """
        seeds: list[Seed] = []
        seen: set[str] = set()

        def add_seed(term: str, source: str, confidence: float) -> None:
            normalized = term.lower().strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                seeds.append(
                    Seed(
                        term=term,
                        source=source,
                        confidence=confidence,
                        category=category,
                        region=region,
                        platform=platform,
                    )
                )

        # 1. User-provided keywords (highest priority)
        if user_keywords:
            for keyword in user_keywords:
                add_seed(keyword, "user", 1.0)

        # 2. Historical优胜词 (if feedback aggregator available)
        if self.feedback_aggregator and category:
            try:
                historical_keywords = self.feedback_aggregator.get_high_performing_seeds(
                    category=category,
                    limit=10,
                )
                for keyword in historical_keywords:
                    add_seed(keyword, "historical", 0.8)
            except Exception as exc:
                self.logger.warning(
                    "seed_pool_historical_fetch_failed",
                    category=category,
                    error=str(exc),
                )

        # 3. AlphaShop trending seeds (primary dynamic source)
        alphashop_seed_count = 0
        if category and region:
            try:
                trending_keywords = await self.keyword_generator.generate_selection_keywords(
                    category=category,
                    region=region,
                    limit=min(max_seeds, 20),
                    expand_top_n=3,
                )
                for keyword_result in trending_keywords:
                    add_seed(keyword_result.keyword, "alphashop_trending", 0.75)
                    alphashop_seed_count += 1
            except Exception as exc:
                self.logger.warning(
                    "seed_pool_alphashop_fetch_failed",
                    category=category,
                    region=region,
                    error=str(exc),
                )

        # 4. Seasonal/event seeds
        seasonal_llm_count = 0
        seasonal_fallback_count = 0
        if category and region:
            calendar = get_seasonal_calendar(lookahead_days=90)
            upcoming_events = calendar.get_upcoming_events(category=category)
            for event in upcoming_events:
                # Try LLM expansion first if enabled
                if self.settings.seed_enable_seasonal_llm_expansion:
                    try:
                        expanded_phrases = await self.seasonal_seed_expander.expand(
                            event=event,
                            category=category,
                            region=region,
                            limit=self.settings.seed_seasonal_llm_max_queries,
                        )
                        if expanded_phrases:
                            for phrase in expanded_phrases:
                                add_seed(phrase, "seasonal_llm", 0.72)
                                seasonal_llm_count += 1
                        else:
                            # LLM returned empty, fallback to template
                            event_seed = f"{event.name.lower()} {category}"
                            add_seed(event_seed, "seasonal", 0.7)
                            seasonal_fallback_count += 1
                    except Exception as exc:
                        self.logger.warning(
                            "seasonal_llm_expansion_failed",
                            event_name=event.name,
                            category=category,
                            error=str(exc),
                        )
                        # Fallback to template on exception
                        event_seed = f"{event.name.lower()} {category}"
                        add_seed(event_seed, "seasonal", 0.7)
                        seasonal_fallback_count += 1
                else:
                    # Feature flag disabled, use template
                    event_seed = f"{event.name.lower()} {category}"
                    add_seed(event_seed, "seasonal", 0.7)
                    seasonal_fallback_count += 1
        elif category:
            # No region provided, use template-only approach
            calendar = get_seasonal_calendar(lookahead_days=90)
            upcoming_events = calendar.get_upcoming_events(category=category)
            for event in upcoming_events:
                event_seed = f"{event.name.lower()} {category}"
                add_seed(event_seed, "seasonal", 0.7)
                seasonal_fallback_count += 1

        # 5. Category static seeds (fallback only)
        # Only use static seeds when AlphaShop dynamic discovery produced nothing.
        if category and alphashop_seed_count == 0:
            category_lower = category.lower().strip()
            static_seeds = self.CATEGORY_SEEDS.get(category_lower, [])
            for keyword in static_seeds:
                add_seed(keyword, "category_static", 0.5)

        # Sort by confidence descending, then limit
        seeds.sort(key=lambda s: s.confidence, reverse=True)
        seeds = seeds[:max_seeds]

        source_breakdown = {
            "user": sum(1 for s in seeds if s.source == "user"),
            "historical": sum(1 for s in seeds if s.source == "historical"),
            "alphashop_trending": sum(1 for s in seeds if s.source == "alphashop_trending"),
            "seasonal": sum(1 for s in seeds if s.source == "seasonal"),
            "seasonal_llm": sum(1 for s in seeds if s.source == "seasonal_llm"),
            "category_static": sum(1 for s in seeds if s.source == "category_static"),
        }

        avg_confidence = sum(s.confidence for s in seeds) / len(seeds) if seeds else 0.0

        self.logger.info(
            "seed_pool_built",
            category=category,
            region=region,
            platform=platform,
            total_seeds=len(seeds),
            source_breakdown=source_breakdown,
            avg_confidence=round(avg_confidence, 3),
            user_seeds=source_breakdown["user"],
            historical_seeds=source_breakdown["historical"],
            alphashop_trending_seeds=source_breakdown["alphashop_trending"],
            seasonal_seeds=source_breakdown["seasonal"],
            seasonal_llm_seeds=source_breakdown["seasonal_llm"],
            seasonal_llm_count=seasonal_llm_count,
            seasonal_fallback_count=seasonal_fallback_count,
            static_seeds=source_breakdown["category_static"],
            used_static_fallback=alphashop_seed_count == 0,
        )

        return seeds
