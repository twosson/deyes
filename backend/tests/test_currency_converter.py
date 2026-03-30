"""Tests for currency converter service."""
from datetime import date, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ExchangeRate
from app.services.currency_converter import CurrencyConverter


@pytest.mark.asyncio
async def test_get_rate_returns_same_currency_as_one(db_session: AsyncSession):
    """CurrencyConverter should return 1.0 for same currency."""
    service = CurrencyConverter()

    rate = await service.get_rate(
        db=db_session,
        base_currency="USD",
        quote_currency="USD",
    )

    assert rate == Decimal("1.0")


@pytest.mark.asyncio
async def test_get_rate_returns_exchange_rate(db_session: AsyncSession):
    """CurrencyConverter should return exchange rate from DB."""
    service = CurrencyConverter()

    exchange_rate = ExchangeRate(
        id=uuid4(),
        base_currency="USD",
        quote_currency="EUR",
        rate=Decimal("0.85"),
        rate_date=date.today(),
        is_active=True,
    )
    db_session.add(exchange_rate)
    await db_session.commit()

    rate = await service.get_rate(
        db=db_session,
        base_currency="USD",
        quote_currency="EUR",
    )

    assert rate == Decimal("0.85")


@pytest.mark.asyncio
async def test_get_rate_uses_most_recent_rate(db_session: AsyncSession):
    """CurrencyConverter should use most recent rate on or before rate_date."""
    service = CurrencyConverter()

    # Older rate
    old_rate = ExchangeRate(
        id=uuid4(),
        base_currency="USD",
        quote_currency="GBP",
        rate=Decimal("0.75"),
        rate_date=date.today() - timedelta(days=7),
        is_active=True,
    )
    db_session.add(old_rate)

    # Recent rate
    recent_rate = ExchangeRate(
        id=uuid4(),
        base_currency="USD",
        quote_currency="GBP",
        rate=Decimal("0.78"),
        rate_date=date.today() - timedelta(days=1),
        is_active=True,
    )
    db_session.add(recent_rate)
    await db_session.commit()

    rate = await service.get_rate(
        db=db_session,
        base_currency="USD",
        quote_currency="GBP",
    )

    assert rate == Decimal("0.78")


@pytest.mark.asyncio
async def test_get_rate_tries_inverse_rate(db_session: AsyncSession):
    """CurrencyConverter should try inverse rate if direct rate not found."""
    service = CurrencyConverter()

    # Only EUR/USD exists (inverse of USD/EUR)
    exchange_rate = ExchangeRate(
        id=uuid4(),
        base_currency="EUR",
        quote_currency="USD",
        rate=Decimal("1.20"),
        rate_date=date.today(),
        is_active=True,
    )
    db_session.add(exchange_rate)
    await db_session.commit()

    rate = await service.get_rate(
        db=db_session,
        base_currency="USD",
        quote_currency="EUR",
    )

    # Should return 1/1.20 = 0.8333...
    assert rate == Decimal("1.0") / Decimal("1.20")


@pytest.mark.asyncio
async def test_get_rate_raises_when_not_found(db_session: AsyncSession):
    """CurrencyConverter should raise ValueError when no rate found."""
    service = CurrencyConverter()

    with pytest.raises(ValueError, match="No exchange rate found"):
        await service.get_rate(
            db=db_session,
            base_currency="USD",
            quote_currency="JPY",
        )


@pytest.mark.asyncio
async def test_convert_amount_returns_same_currency(db_session: AsyncSession):
    """convert_amount should return same amount for same currency."""
    service = CurrencyConverter()

    converted = await service.convert_amount(
        db=db_session,
        amount=Decimal("100.00"),
        from_currency="USD",
        to_currency="USD",
    )

    assert converted == Decimal("100.00")


@pytest.mark.asyncio
async def test_convert_amount_converts_correctly(db_session: AsyncSession):
    """convert_amount should convert amount using exchange rate."""
    service = CurrencyConverter()

    exchange_rate = ExchangeRate(
        id=uuid4(),
        base_currency="USD",
        quote_currency="EUR",
        rate=Decimal("0.85"),
        rate_date=date.today(),
        is_active=True,
    )
    db_session.add(exchange_rate)
    await db_session.commit()

    converted = await service.convert_amount(
        db=db_session,
        amount=Decimal("100.00"),
        from_currency="USD",
        to_currency="EUR",
    )

    assert converted == Decimal("85.00")


@pytest.mark.asyncio
async def test_convert_amount_quantizes_to_cents(db_session: AsyncSession):
    """convert_amount should quantize result to 0.01."""
    service = CurrencyConverter()

    exchange_rate = ExchangeRate(
        id=uuid4(),
        base_currency="USD",
        quote_currency="EUR",
        rate=Decimal("0.8567"),
        rate_date=date.today(),
        is_active=True,
    )
    db_session.add(exchange_rate)
    await db_session.commit()

    converted = await service.convert_amount(
        db=db_session,
        amount=Decimal("100.00"),
        from_currency="USD",
        to_currency="EUR",
    )

    # 100 * 0.8567 = 85.67
    assert converted == Decimal("85.67")


@pytest.mark.asyncio
async def test_convert_snapshot_amounts_converts_multiple_fields(db_session: AsyncSession):
    """convert_snapshot_amounts should convert multiple fields in dict."""
    service = CurrencyConverter()

    exchange_rate = ExchangeRate(
        id=uuid4(),
        base_currency="USD",
        quote_currency="EUR",
        rate=Decimal("0.85"),
        rate_date=date.today(),
        is_active=True,
    )
    db_session.add(exchange_rate)
    await db_session.commit()

    payload = {
        "price": 100.0,
        "revenue": 500.0,
        "cost": 300.0,
        "other_field": "unchanged",
    }

    converted = await service.convert_snapshot_amounts(
        db=db_session,
        payload=payload,
        from_currency="USD",
        to_currency="EUR",
        fields=["price", "revenue", "cost"],
    )

    assert converted["price"] == 85.0
    assert converted["revenue"] == 425.0
    assert converted["cost"] == 255.0
    assert converted["other_field"] == "unchanged"


@pytest.mark.asyncio
async def test_convert_snapshot_amounts_returns_copy_for_same_currency(db_session: AsyncSession):
    """convert_snapshot_amounts should return copy for same currency."""
    service = CurrencyConverter()

    payload = {"price": 100.0, "revenue": 500.0}

    converted = await service.convert_snapshot_amounts(
        db=db_session,
        payload=payload,
        from_currency="USD",
        to_currency="USD",
        fields=["price", "revenue"],
    )

    assert converted == payload
    assert converted is not payload  # Should be a copy
