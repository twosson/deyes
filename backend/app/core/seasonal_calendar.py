"""Seasonal calendar for event-driven product selection.

Phase 4 Enhancement: Define annual events with category-specific boost factors
to prioritize products for upcoming holidays and shopping events.

Features:
- 90-day lookahead for event planning
- Category-specific boost factors
- Major shopping events (Prime Day, Black Friday, etc.)
- Holiday events (Valentine's, Christmas, etc.)
- Regional event support
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Optional

from app.core.logging import get_logger

logger = get_logger(__name__)


@dataclass
class SeasonalEvent:
    """Seasonal event definition."""

    name: str
    date: date
    categories: dict[str, float]  # category -> boost factor
    description: str = ""
    region: str = "US"  # Default to US


class SeasonalCalendar:
    """Seasonal calendar for event-driven product selection.

    Provides boost factors for product categories based on upcoming events.
    Uses 90-day lookahead to prioritize products for future events.
    """

    # Annual events (2026)
    EVENTS_2026 = [
        SeasonalEvent(
            name="New Year",
            date=date(2026, 1, 1),
            categories={
                "home": 1.3,
                "fitness": 1.5,
                "electronics": 1.2,
            },
            description="New Year's resolutions drive fitness and home organization",
        ),
        SeasonalEvent(
            name="Valentine's Day",
            date=date(2026, 2, 14),
            categories={
                "jewelry": 1.5,
                "fashion": 1.3,
                "beauty": 1.4,
                "home": 1.2,  # Home decor
            },
            description="Gifts for loved ones",
        ),
        SeasonalEvent(
            name="Easter",
            date=date(2026, 4, 5),
            categories={
                "toys": 1.3,
                "home": 1.2,  # Easter decorations
                "fashion": 1.2,
            },
            description="Easter gifts and decorations",
        ),
        SeasonalEvent(
            name="Mother's Day",
            date=date(2026, 5, 10),
            categories={
                "jewelry": 1.4,
                "beauty": 1.5,
                "fashion": 1.3,
                "home": 1.2,
            },
            description="Gifts for mothers",
        ),
        SeasonalEvent(
            name="Father's Day",
            date=date(2026, 6, 21),
            categories={
                "electronics": 1.4,
                "sports": 1.3,
                "fashion": 1.2,
            },
            description="Gifts for fathers",
        ),
        SeasonalEvent(
            name="Prime Day",
            date=date(2026, 7, 15),
            categories={
                "electronics": 1.5,
                "home": 1.4,
                "fashion": 1.3,
                "beauty": 1.2,
                "sports": 1.2,
            },
            description="Amazon Prime Day - major shopping event",
        ),
        SeasonalEvent(
            name="Back to School",
            date=date(2026, 8, 15),
            categories={
                "electronics": 1.4,
                "fashion": 1.3,
                "home": 1.2,  # Dorm supplies
            },
            description="Back to school shopping season",
        ),
        SeasonalEvent(
            name="Halloween",
            date=date(2026, 10, 31),
            categories={
                "toys": 1.3,
                "home": 1.4,  # Halloween decorations
                "fashion": 1.2,  # Costumes
            },
            description="Halloween costumes and decorations",
        ),
        SeasonalEvent(
            name="Black Friday",
            date=date(2026, 11, 27),
            categories={
                "electronics": 1.6,
                "toys": 1.5,
                "fashion": 1.4,
                "home": 1.3,
                "beauty": 1.3,
                "sports": 1.2,
            },
            description="Black Friday - biggest shopping event of the year",
        ),
        SeasonalEvent(
            name="Cyber Monday",
            date=date(2026, 11, 30),
            categories={
                "electronics": 1.6,
                "fashion": 1.4,
                "home": 1.3,
                "beauty": 1.3,
            },
            description="Cyber Monday - online shopping event",
        ),
        SeasonalEvent(
            name="Christmas",
            date=date(2026, 12, 25),
            categories={
                "toys": 1.6,
                "electronics": 1.5,
                "jewelry": 1.5,
                "fashion": 1.4,
                "home": 1.4,
                "beauty": 1.3,
                "sports": 1.2,
            },
            description="Christmas gifts and decorations",
        ),
    ]

    # Annual events (2027) - for lookahead beyond 2026
    EVENTS_2027 = [
        SeasonalEvent(
            name="New Year",
            date=date(2027, 1, 1),
            categories={
                "home": 1.3,
                "fitness": 1.5,
                "electronics": 1.2,
            },
            description="New Year's resolutions drive fitness and home organization",
        ),
        SeasonalEvent(
            name="Valentine's Day",
            date=date(2027, 2, 14),
            categories={
                "jewelry": 1.5,
                "fashion": 1.3,
                "beauty": 1.4,
                "home": 1.2,
            },
            description="Gifts for loved ones",
        ),
        # Add more 2027 events as needed
    ]

    def __init__(self, lookahead_days: int = 90):
        """Initialize seasonal calendar.

        Args:
            lookahead_days: Number of days to look ahead for events (default: 90)
        """
        self.lookahead_days = lookahead_days
        self.events = self.EVENTS_2026 + self.EVENTS_2027
        self.logger = logger

    def get_upcoming_events(
        self,
        category: Optional[str] = None,
        reference_date: Optional[date] = None,
    ) -> list[SeasonalEvent]:
        """Get upcoming events within lookahead window.

        Args:
            category: Filter by category (optional)
            reference_date: Reference date for lookahead (default: today)

        Returns:
            List of upcoming events sorted by date
        """
        if reference_date is None:
            reference_date = date.today()

        end_date = reference_date + timedelta(days=self.lookahead_days)

        upcoming = []
        for event in self.events:
            if reference_date <= event.date <= end_date:
                # Filter by category if specified
                if category is None or category.lower() in event.categories:
                    upcoming.append(event)

        # Sort by date
        upcoming.sort(key=lambda e: e.date)
        return upcoming

    def get_boost_factor(
        self,
        category: str,
        reference_date: Optional[date] = None,
    ) -> float:
        """Get seasonal boost factor for a category.

        Calculates boost based on upcoming events within lookahead window.
        Closer events have higher weight.

        Args:
            category: Product category
            reference_date: Reference date for lookahead (default: today)

        Returns:
            Boost factor (1.0 = no boost, >1.0 = boosted)
        """
        if reference_date is None:
            reference_date = date.today()

        category_lower = category.lower()
        upcoming = self.get_upcoming_events(category=category_lower, reference_date=reference_date)

        if not upcoming:
            return 1.0

        # Calculate weighted boost based on proximity
        total_boost = 0.0
        total_weight = 0.0

        for event in upcoming:
            days_until = (event.date - reference_date).days
            boost = event.categories.get(category_lower, 1.0)

            # Weight: closer events have higher weight
            # Linear decay: 90 days = 0.1 weight, 1 day = 1.0 weight
            weight = max(0.1, 1.0 - (days_until / self.lookahead_days) * 0.9)

            total_boost += boost * weight
            total_weight += weight

            self.logger.debug(
                "seasonal_boost_calculation",
                event_name=event.name,
                category=category,
                days_until=days_until,
                boost=boost,
                weight=weight,
            )

        # Calculate weighted average
        if total_weight > 0:
            final_boost = total_boost / total_weight
        else:
            final_boost = 1.0

        self.logger.info(
            "seasonal_boost_calculated",
            category=category,
            reference_date=str(reference_date),
            upcoming_events=[e.name for e in upcoming],
            final_boost=final_boost,
        )

        return final_boost

    def get_next_event(
        self,
        category: Optional[str] = None,
        reference_date: Optional[date] = None,
    ) -> Optional[SeasonalEvent]:
        """Get the next upcoming event.

        Args:
            category: Filter by category (optional)
            reference_date: Reference date (default: today)

        Returns:
            Next upcoming event or None
        """
        upcoming = self.get_upcoming_events(category=category, reference_date=reference_date)
        return upcoming[0] if upcoming else None

    def get_event_by_name(self, name: str) -> Optional[SeasonalEvent]:
        """Get event by name.

        Args:
            name: Event name

        Returns:
            Event or None
        """
        for event in self.events:
            if event.name.lower() == name.lower():
                return event
        return None

    def is_event_upcoming(
        self,
        event_name: str,
        reference_date: Optional[date] = None,
    ) -> bool:
        """Check if an event is upcoming within lookahead window.

        Args:
            event_name: Event name
            reference_date: Reference date (default: today)

        Returns:
            True if event is upcoming
        """
        event = self.get_event_by_name(event_name)
        if not event:
            return False

        if reference_date is None:
            reference_date = date.today()

        end_date = reference_date + timedelta(days=self.lookahead_days)
        return reference_date <= event.date <= end_date

    def get_all_categories(self) -> set[str]:
        """Get all categories with seasonal events.

        Returns:
            Set of category names
        """
        categories = set()
        for event in self.events:
            categories.update(event.categories.keys())
        return categories


# Global instance
_calendar = None


def get_seasonal_calendar(lookahead_days: int = 90) -> SeasonalCalendar:
    """Get global seasonal calendar instance.

    Args:
        lookahead_days: Number of days to look ahead (default: 90)

    Returns:
        SeasonalCalendar instance
    """
    global _calendar
    if _calendar is None or _calendar.lookahead_days != lookahead_days:
        _calendar = SeasonalCalendar(lookahead_days=lookahead_days)
    return _calendar
