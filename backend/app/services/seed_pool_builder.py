"""Seed pool builder service for seller-first product selection.

Converts category + user keywords into a seed pool for keyword legitimization.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from app.core.logging import get_logger
from app.core.seasonal_calendar import get_seasonal_calendar
from app.services.feedback_aggregator import FeedbackAggregator

logger = get_logger(__name__)


@dataclass
class Seed:
    """A seed keyword candidate for legitimization."""

    term: str
    source: str  # "user" / "category_static" / "historical" / "seasonal"
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
    ):
        self.feedback_aggregator = feedback_aggregator
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
        """Build seed pool from multiple sources."""
        seeds: list[Seed] = []
        seen: set[str] = set()

        # 1. User-provided keywords (highest priority)
        if user_keywords:
            for keyword in user_keywords:
                normalized = keyword.lower().strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    seeds.append(
                        Seed(
                            term=keyword,
                            source="user",
                            confidence=1.0,
                            category=category,
                            region=region,
                            platform=platform,
                        )
                    )

        # 2. Historical优胜词 (if feedback aggregator available)
        if self.feedback_aggregator and category:
            try:
                historical_keywords = self.feedback_aggregator.get_high_performing_seeds(
                    category=category,
                    limit=10,
                )
                for keyword in historical_keywords:
                    normalized = keyword.lower().strip()
                    if normalized and normalized not in seen:
                        seen.add(normalized)
                        seeds.append(
                            Seed(
                                term=keyword,
                                source="historical",
                                confidence=0.8,
                                category=category,
                                region=region,
                                platform=platform,
                            )
                        )
            except Exception as exc:
                self.logger.warning(
                    "seed_pool_historical_fetch_failed",
                    category=category,
                    error=str(exc),
                )

        # 3. Seasonal/event seeds
        if category:
            calendar = get_seasonal_calendar(lookahead_days=90)
            upcoming_events = calendar.get_upcoming_events(category=category)
            for event in upcoming_events:
                # Use event name as seed (e.g., "valentine's day gifts")
                event_seed = f"{event.name.lower()} {category}"
                normalized = event_seed.lower().strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    seeds.append(
                        Seed(
                            term=event_seed,
                            source="seasonal",
                            confidence=0.7,
                            category=category,
                            region=region,
                            platform=platform,
                        )
                    )

        # 4. Category static seeds (lowest priority, fallback)
        if category:
            category_lower = category.lower().strip()
            static_seeds = self.CATEGORY_SEEDS.get(category_lower, [])
            for keyword in static_seeds:
                normalized = keyword.lower().strip()
                if normalized and normalized not in seen:
                    seen.add(normalized)
                    seeds.append(
                        Seed(
                            term=keyword,
                            source="category_static",
                            confidence=0.5,
                            category=category,
                            region=region,
                            platform=platform,
                        )
                    )

        # Sort by confidence descending, then limit
        seeds.sort(key=lambda s: s.confidence, reverse=True)
        seeds = seeds[:max_seeds]

        source_breakdown = {
            "user": sum(1 for s in seeds if s.source == "user"),
            "historical": sum(1 for s in seeds if s.source == "historical"),
            "seasonal": sum(1 for s in seeds if s.source == "seasonal"),
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
            seasonal_seeds=source_breakdown["seasonal"],
            static_seeds=source_breakdown["category_static"],
        )

        return seeds
