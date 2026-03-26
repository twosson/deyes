"""Tests for seasonal calendar."""
import pytest
from datetime import date, timedelta

from app.core.seasonal_calendar import (
    SeasonalCalendar,
    SeasonalEvent,
    get_seasonal_calendar,
)


class TestSeasonalEvent:
    """Test SeasonalEvent dataclass."""

    def test_create_event(self):
        """Test creating a seasonal event."""
        event = SeasonalEvent(
            name="Test Event",
            date=date(2026, 12, 25),
            categories={"electronics": 1.5, "toys": 1.4},
            description="Test description",
            region="US",
        )

        assert event.name == "Test Event"
        assert event.date == date(2026, 12, 25)
        assert event.categories["electronics"] == 1.5
        assert event.categories["toys"] == 1.4
        assert event.description == "Test description"
        assert event.region == "US"


class TestSeasonalCalendar:
    """Test SeasonalCalendar."""

    def test_init_default(self):
        """Test initialization with defaults."""
        calendar = SeasonalCalendar()

        assert calendar.lookahead_days == 90
        assert len(calendar.events) > 0

    def test_init_custom_lookahead(self):
        """Test initialization with custom lookahead."""
        calendar = SeasonalCalendar(lookahead_days=60)

        assert calendar.lookahead_days == 60

    def test_get_upcoming_events_christmas(self):
        """Test getting upcoming events for Christmas."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: 90 days before Christmas
        reference_date = date(2026, 9, 26)  # 90 days before Dec 25

        upcoming = calendar.get_upcoming_events(reference_date=reference_date)

        # Should include Halloween, Black Friday, Cyber Monday, Christmas
        event_names = [e.name for e in upcoming]
        assert "Halloween" in event_names
        assert "Black Friday" in event_names
        assert "Cyber Monday" in event_names
        assert "Christmas" in event_names

    def test_get_upcoming_events_by_category(self):
        """Test getting upcoming events filtered by category."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: before Valentine's Day
        reference_date = date(2026, 1, 1)

        upcoming = calendar.get_upcoming_events(
            category="jewelry",
            reference_date=reference_date,
        )

        # Should include Valentine's Day (jewelry boost)
        event_names = [e.name for e in upcoming]
        assert "Valentine's Day" in event_names

    def test_get_upcoming_events_sorted(self):
        """Test that upcoming events are sorted by date."""
        calendar = SeasonalCalendar(lookahead_days=365)

        reference_date = date(2026, 1, 1)
        upcoming = calendar.get_upcoming_events(reference_date=reference_date)

        # Check that events are sorted
        for i in range(len(upcoming) - 1):
            assert upcoming[i].date <= upcoming[i + 1].date

    def test_get_boost_factor_no_events(self):
        """Test boost factor when no events are upcoming."""
        calendar = SeasonalCalendar(lookahead_days=30)

        # Reference date: far from any events
        reference_date = date(2026, 3, 1)

        boost = calendar.get_boost_factor(
            category="electronics",
            reference_date=reference_date,
        )

        # Should be 1.0 (no boost)
        assert boost == 1.0

    def test_get_boost_factor_christmas(self):
        """Test boost factor for electronics before Christmas."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: 30 days before Christmas
        reference_date = date(2026, 11, 25)

        boost = calendar.get_boost_factor(
            category="electronics",
            reference_date=reference_date,
        )

        # Should be boosted (Christmas has electronics boost of 1.5)
        assert boost > 1.0
        assert boost <= 1.6  # Max boost from Black Friday/Christmas

    def test_get_boost_factor_valentines(self):
        """Test boost factor for jewelry before Valentine's Day."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: 30 days before Valentine's Day
        reference_date = date(2026, 1, 15)

        boost = calendar.get_boost_factor(
            category="jewelry",
            reference_date=reference_date,
        )

        # Should be boosted (Valentine's has jewelry boost of 1.5)
        assert boost > 1.0
        assert boost <= 1.5

    def test_get_boost_factor_proximity_weight(self):
        """Test that closer events have higher weight."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: 10 days before Christmas
        reference_date_close = date(2026, 12, 15)

        # Reference date: 80 days before Christmas
        reference_date_far = date(2026, 10, 6)

        boost_close = calendar.get_boost_factor(
            category="electronics",
            reference_date=reference_date_close,
        )

        boost_far = calendar.get_boost_factor(
            category="electronics",
            reference_date=reference_date_far,
        )

        # Closer event should have higher boost
        assert boost_close > boost_far

    def test_get_boost_factor_multiple_events(self):
        """Test boost factor with multiple upcoming events."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: before Black Friday and Christmas
        reference_date = date(2026, 10, 1)

        boost = calendar.get_boost_factor(
            category="electronics",
            reference_date=reference_date,
        )

        # Should be boosted by both events
        assert boost > 1.0

    def test_get_next_event(self):
        """Test getting next upcoming event."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: before Valentine's Day
        reference_date = date(2026, 1, 1)

        next_event = calendar.get_next_event(reference_date=reference_date)

        assert next_event is not None
        assert next_event.name == "Valentine's Day"

    def test_get_next_event_by_category(self):
        """Test getting next event for specific category."""
        calendar = SeasonalCalendar(lookahead_days=365)

        # Reference date: start of year
        reference_date = date(2026, 1, 1)

        next_event = calendar.get_next_event(
            category="jewelry",
            reference_date=reference_date,
        )

        assert next_event is not None
        assert "jewelry" in next_event.categories

    def test_get_next_event_no_events(self):
        """Test getting next event when none are upcoming."""
        calendar = SeasonalCalendar(lookahead_days=30)

        # Reference date: far from any events
        reference_date = date(2026, 3, 1)

        next_event = calendar.get_next_event(reference_date=reference_date)

        # Should be None (no events in 30-day window)
        assert next_event is None

    def test_get_event_by_name(self):
        """Test getting event by name."""
        calendar = SeasonalCalendar()

        event = calendar.get_event_by_name("Christmas")

        assert event is not None
        assert event.name == "Christmas"
        assert event.date == date(2026, 12, 25)

    def test_get_event_by_name_case_insensitive(self):
        """Test getting event by name is case insensitive."""
        calendar = SeasonalCalendar()

        event = calendar.get_event_by_name("christmas")

        assert event is not None
        assert event.name == "Christmas"

    def test_get_event_by_name_not_found(self):
        """Test getting non-existent event."""
        calendar = SeasonalCalendar()

        event = calendar.get_event_by_name("Nonexistent Event")

        assert event is None

    def test_is_event_upcoming_true(self):
        """Test checking if event is upcoming."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: before Christmas
        reference_date = date(2026, 10, 1)

        is_upcoming = calendar.is_event_upcoming(
            event_name="Christmas",
            reference_date=reference_date,
        )

        assert is_upcoming is True

    def test_is_event_upcoming_false(self):
        """Test checking if event is not upcoming."""
        calendar = SeasonalCalendar(lookahead_days=30)

        # Reference date: far from Christmas
        reference_date = date(2026, 3, 1)

        is_upcoming = calendar.is_event_upcoming(
            event_name="Christmas",
            reference_date=reference_date,
        )

        assert is_upcoming is False

    def test_is_event_upcoming_nonexistent(self):
        """Test checking if non-existent event is upcoming."""
        calendar = SeasonalCalendar()

        is_upcoming = calendar.is_event_upcoming(
            event_name="Nonexistent Event",
            reference_date=date(2026, 1, 1),
        )

        assert is_upcoming is False

    def test_get_all_categories(self):
        """Test getting all categories with seasonal events."""
        calendar = SeasonalCalendar()

        categories = calendar.get_all_categories()

        # Should include major categories
        assert "electronics" in categories
        assert "jewelry" in categories
        assert "toys" in categories
        assert "fashion" in categories
        assert "home" in categories

    def test_events_2026_defined(self):
        """Test that 2026 events are defined."""
        calendar = SeasonalCalendar()

        # Check major events
        event_names = [e.name for e in calendar.EVENTS_2026]

        assert "New Year" in event_names
        assert "Valentine's Day" in event_names
        assert "Easter" in event_names
        assert "Mother's Day" in event_names
        assert "Father's Day" in event_names
        assert "Prime Day" in event_names
        assert "Back to School" in event_names
        assert "Halloween" in event_names
        assert "Black Friday" in event_names
        assert "Cyber Monday" in event_names
        assert "Christmas" in event_names

    def test_events_2027_defined(self):
        """Test that 2027 events are defined for lookahead."""
        calendar = SeasonalCalendar()

        # Check that 2027 events exist
        event_names = [e.name for e in calendar.EVENTS_2027]

        assert "New Year" in event_names
        assert "Valentine's Day" in event_names


class TestGetSeasonalCalendar:
    """Test get_seasonal_calendar function."""

    def test_get_global_instance(self):
        """Test getting global calendar instance."""
        calendar1 = get_seasonal_calendar()
        calendar2 = get_seasonal_calendar()

        # Should return same instance
        assert calendar1 is calendar2

    def test_get_with_custom_lookahead(self):
        """Test getting calendar with custom lookahead."""
        calendar = get_seasonal_calendar(lookahead_days=60)

        assert calendar.lookahead_days == 60

    def test_get_recreates_on_different_lookahead(self):
        """Test that calendar is recreated with different lookahead."""
        calendar1 = get_seasonal_calendar(lookahead_days=90)
        calendar2 = get_seasonal_calendar(lookahead_days=60)

        # Should be different instances
        assert calendar1 is not calendar2
        assert calendar1.lookahead_days == 90
        assert calendar2.lookahead_days == 60


class TestSeasonalBoostScenarios:
    """Test realistic seasonal boost scenarios."""

    def test_black_friday_electronics_boost(self):
        """Test electronics boost during Black Friday season."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: October 1 (Black Friday is Nov 27)
        reference_date = date(2026, 10, 1)

        boost = calendar.get_boost_factor(
            category="electronics",
            reference_date=reference_date,
        )

        # Should have significant boost (Black Friday + Cyber Monday + Christmas)
        assert boost > 1.3

    def test_valentines_jewelry_boost(self):
        """Test jewelry boost before Valentine's Day."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: January 1 (Valentine's is Feb 14)
        reference_date = date(2026, 1, 1)

        boost = calendar.get_boost_factor(
            category="jewelry",
            reference_date=reference_date,
        )

        # Should have boost from Valentine's Day
        assert boost > 1.0
        assert boost <= 1.5

    def test_summer_no_boost(self):
        """Test no boost during summer (few events)."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: May 1 (after Mother's Day, before Prime Day)
        reference_date = date(2026, 5, 15)

        boost = calendar.get_boost_factor(
            category="electronics",
            reference_date=reference_date,
        )

        # Should have some boost from Prime Day
        assert boost >= 1.0

    def test_christmas_toys_boost(self):
        """Test toys boost before Christmas."""
        calendar = SeasonalCalendar(lookahead_days=90)

        # Reference date: October 1 (Christmas is Dec 25)
        reference_date = date(2026, 10, 1)

        boost = calendar.get_boost_factor(
            category="toys",
            reference_date=reference_date,
        )

        # Should have significant boost (Black Friday + Christmas)
        assert boost > 1.3
