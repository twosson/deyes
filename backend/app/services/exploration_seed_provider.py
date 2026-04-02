"""Exploration seed provider for broad listing / general store mode.

Provides exploration seeds when no category or keywords are provided by the user.
Unlike SeedFallbackProvider (weak signal fallback), this service implements a
structured exploration strategy with feedback loops and quality signals.

Exploration mode is designed for:
- Broad listing / general store business model
- Automated product discovery without manual category/keyword input
- Continuous market exploration and opportunity mining

Seed sources (priority order):
1. Historical signal seeds (proven performers from past selections)
2. Merchandising template signals (category/theme templates)
3. Market trend signals (seasonal, trending, platform-specific)
4. Supply signals (1688 hot categories, supplier trends)
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

from app.core.config import get_settings
from app.core.logging import get_logger
from app.core.seasonal_calendar import get_seasonal_calendar
from app.services.seasonal_seed_expander import SeasonalSeedExpander

logger = get_logger(__name__)


@dataclass
class ExplorationSeed:
    """A seed candidate for exploration mode."""

    term: str
    source: str  # "historical", "template", "trend", "supply"
    confidence: float  # 0.0-1.0
    metadata: dict


@dataclass
class ExplorationBrief:
    """Exploration context and constraints."""

    region: Optional[str] = None
    platform: Optional[str] = None
    max_seeds: int = 10
    min_confidence: float = 0.3
    enable_historical: bool = True
    enable_template: bool = True
    enable_trend: bool = True
    enable_supply: bool = True


class ExplorationSeedProvider:
    """Provide exploration seeds for broad listing mode.

    This service generates seeds when:
    - User provides no category or keywords
    - System needs to autonomously explore market opportunities
    - Broad listing / general store business model is active

    Unlike SeedFallbackProvider (weak fallback), this implements:
    - Feedback loop integration (historical signal seeds)
    - Structured exploration strategy
    - Quality confidence scoring
    - Multi-source seed fusion
    """

    # Market trend seeds (seasonal, platform-specific)
    TREND_SEEDS = {
        "spring": ["spring essentials", "outdoor gear", "gardening tools"],
        "summer": ["summer accessories", "cooling products", "beach essentials"],
        "autumn": ["back to school", "fall decor", "cozy home"],
        "winter": ["winter warmers", "holiday gifts", "indoor comfort"],
    }

    # Supply signal seeds (1688 hot categories)
    SUPPLY_SEEDS = {
        "US": ["phone accessories", "home organization", "kitchen gadgets"],
        "UK": ["home decor", "pet supplies", "fitness accessories"],
        "DE": ["tech accessories", "home improvement", "outdoor tools"],
        "FR": ["beauty tools", "fashion accessories", "home textiles"],
        "JP": ["stationery", "small appliances", "lifestyle goods"],
        "CN": ["数码配件", "家居收纳", "厨房用品"],
    }

    def __init__(
        self,
        seasonal_seed_expander: Optional[SeasonalSeedExpander] = None,
    ):
        """Initialize exploration seed provider."""
        self.logger = logger
        self.settings = get_settings()
        self.seasonal_seed_expander = seasonal_seed_expander or SeasonalSeedExpander()

    async def get_exploration_seeds(
        self,
        brief: ExplorationBrief,
    ) -> list[ExplorationSeed]:
        """Get exploration seeds based on brief.

        Args:
            brief: Exploration context and constraints

        Returns:
            List of exploration seeds sorted by confidence (high to low)
        """
        candidates: list[ExplorationSeed] = []

        # 1. Historical signal seeds (highest confidence)
        if brief.enable_historical:
            historical = await self._get_historical_seeds(brief)
            candidates.extend(historical)

        # 2. Merchandising template signals
        if brief.enable_template:
            template = await self._get_template_seeds(brief)
            candidates.extend(template)

        # 3. Market trend signals
        if brief.enable_trend:
            trend = await self._get_trend_seeds(brief)
            candidates.extend(trend)

        # 4. Supply signals
        if brief.enable_supply:
            supply = await self._get_supply_seeds(brief)
            candidates.extend(supply)

        # Filter by confidence threshold
        filtered = [s for s in candidates if s.confidence >= brief.min_confidence]

        # Sort by confidence (high to low)
        filtered.sort(key=lambda s: s.confidence, reverse=True)

        # Limit to max_seeds
        result = filtered[: brief.max_seeds]

        self.logger.info(
            "exploration_seeds_generated",
            total_candidates=len(candidates),
            filtered_count=len(filtered),
            final_count=len(result),
            sources=[s.source for s in result],
            confidence_range=(
                f"{min(s.confidence for s in result):.2f}-{max(s.confidence for s in result):.2f}"
                if result
                else "N/A"
            ),
        )

        return result

    async def _get_historical_seeds(self, brief: ExplorationBrief) -> list[ExplorationSeed]:
        """Get seeds from historical performance signals.

        Phase 1: Return empty list (no historical data yet)
        Phase 2+: Query FeedbackAggregator for proven performers

        Returns:
            List of historical signal seeds with confidence 0.7-0.9
        """
        # Phase 1: No historical data integration yet
        # Phase 2+: Query feedback aggregator for:
        # - Seeds with high legitimization pass rate
        # - Seeds with high opportunity yield
        # - Seeds with high candidate conversion rate
        return []

    async def _get_template_seeds(self, brief: ExplorationBrief) -> list[ExplorationSeed]:
        """Get seeds from merchandising templates.

        Phase 1: Return empty list (no template system yet)
        Phase 2+: Query template service for:
        - Category templates (e.g., "home essentials", "tech gadgets")
        - Theme templates (e.g., "gift ideas", "trending now")
        - Platform-specific templates

        Returns:
            List of template seeds with confidence 0.5-0.7
        """
        # Phase 1: No template system yet
        # Phase 2+: Query merchandising template service
        return []

    async def _get_trend_seeds(self, brief: ExplorationBrief) -> list[ExplorationSeed]:
        """Get seeds from market trend signals.

        Returns seasonal LLM-generated seeds from upcoming events.
        Falls back to static trend seeds if LLM expansion fails.

        Returns:
            List of trend seeds with confidence 0.4-0.6
        """
        seeds: list[ExplorationSeed] = []
        region = (brief.region or "US").upper()

        # Try seasonal LLM expansion first
        if self.settings.seed_enable_seasonal_llm_expansion:
            try:
                calendar = get_seasonal_calendar(lookahead_days=90)
                upcoming_events = calendar.get_upcoming_events(category=None)

                for event in upcoming_events:
                    # Get top 2 categories by boost factor for each event
                    event_categories = sorted(
                        event.categories.keys(),
                        key=lambda c: event.categories[c],
                        reverse=True
                    )[:2]

                    for category in event_categories:
                        expanded_phrases = await self.seasonal_seed_expander.expand(
                            event=event,
                            category=category,
                            region=region,
                            limit=min(3, brief.max_seeds),  # Conservative for exploration mode
                        )

                        for phrase in expanded_phrases:
                            seeds.append(
                                ExplorationSeed(
                                    term=phrase,
                                    source="trend",
                                    confidence=0.5,
                                    metadata={
                                        "signal_type": "seasonal_llm",
                                        "event_name": event.name,
                                        "category": category,
                                        "region": region,
                                    },
                                )
                            )

                if seeds:
                    self.logger.info(
                        "exploration_seasonal_llm_seeds_generated",
                        count=len(seeds),
                        region=region,
                        upcoming_events=[e.name for e in upcoming_events],
                    )
                    return seeds
            except Exception as exc:
                self.logger.warning(
                    "exploration_seasonal_llm_failed",
                    region=region,
                    error=str(exc),
                )

        # Fallback to static seasonal trends
        month = datetime.now(timezone.utc).month
        if month in {3, 4, 5}:
            season = "spring"
        elif month in {6, 7, 8}:
            season = "summer"
        elif month in {9, 10, 11}:
            season = "autumn"
        else:
            season = "winter"

        seasonal_terms = self.TREND_SEEDS.get(season, [])
        for term in seasonal_terms:
            seeds.append(
                ExplorationSeed(
                    term=term,
                    source="trend",
                    confidence=0.5,
                    metadata={"signal_type": "seasonal", "season": season},
                )
            )

        return seeds

    async def _get_supply_seeds(self, brief: ExplorationBrief) -> list[ExplorationSeed]:
        """Get seeds from supply signals (1688 hot categories).

        Returns region-specific supply seeds.

        Returns:
            List of supply seeds with confidence 0.3-0.5
        """
        seeds: list[ExplorationSeed] = []

        region = (brief.region or "US").upper()
        supply_terms = self.SUPPLY_SEEDS.get(region, self.SUPPLY_SEEDS.get("US", []))

        for term in supply_terms:
            seeds.append(
                ExplorationSeed(
                    term=term,
                    source="supply",
                    confidence=0.4,
                    metadata={"signal_type": "supply", "region": region},
                )
            )

        return seeds
