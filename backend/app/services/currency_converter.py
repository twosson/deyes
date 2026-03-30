"""Currency converter service for multi-currency operations.

Provides exchange rate lookup and amount conversion with fallback handling.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.logging import get_logger
from app.db.models import ExchangeRate


class CurrencyConverter:
    """Service for currency conversion using exchange rates.

    Provides rate lookup and amount conversion with graceful fallback.
    """

    def __init__(self):
        self.logger = get_logger(__name__)

    async def get_rate(
        self,
        db: AsyncSession,
        base_currency: str,
        quote_currency: str,
        rate_date: Optional[date] = None,
    ) -> Decimal:
        """Get exchange rate for currency pair.

        Args:
            db: Database session
            base_currency: Base currency code (e.g., "USD")
            quote_currency: Quote currency code (e.g., "EUR")
            rate_date: Rate date (defaults to today)

        Returns:
            Exchange rate as Decimal

        Raises:
            ValueError: If no rate found for currency pair
        """
        # Same currency = 1.0
        if base_currency == quote_currency:
            return Decimal("1.0")

        if rate_date is None:
            rate_date = date.today()

        # Query for rate on or before rate_date
        stmt = (
            select(ExchangeRate)
            .where(
                and_(
                    ExchangeRate.base_currency == base_currency,
                    ExchangeRate.quote_currency == quote_currency,
                    ExchangeRate.rate_date <= rate_date,
                    ExchangeRate.is_active == True,
                )
            )
            .order_by(ExchangeRate.rate_date.desc())
            .limit(1)
        )

        result = await db.execute(stmt)
        rate_record = result.scalar_one_or_none()

        if rate_record:
            self.logger.info(
                "exchange_rate_found",
                base_currency=base_currency,
                quote_currency=quote_currency,
                rate_date=str(rate_date),
                rate=str(rate_record.rate),
                actual_date=str(rate_record.rate_date),
            )
            return rate_record.rate

        # Try inverse rate
        stmt_inverse = (
            select(ExchangeRate)
            .where(
                and_(
                    ExchangeRate.base_currency == quote_currency,
                    ExchangeRate.quote_currency == base_currency,
                    ExchangeRate.rate_date <= rate_date,
                    ExchangeRate.is_active == True,
                )
            )
            .order_by(ExchangeRate.rate_date.desc())
            .limit(1)
        )

        result_inverse = await db.execute(stmt_inverse)
        rate_record_inverse = result_inverse.scalar_one_or_none()

        if rate_record_inverse:
            inverse_rate = Decimal("1.0") / rate_record_inverse.rate
            self.logger.info(
                "exchange_rate_found_inverse",
                base_currency=base_currency,
                quote_currency=quote_currency,
                rate_date=str(rate_date),
                rate=str(inverse_rate),
                actual_date=str(rate_record_inverse.rate_date),
            )
            return inverse_rate

        # No rate found
        self.logger.warning(
            "exchange_rate_not_found",
            base_currency=base_currency,
            quote_currency=quote_currency,
            rate_date=str(rate_date),
        )
        raise ValueError(
            f"No exchange rate found for {base_currency}/{quote_currency} on or before {rate_date}"
        )

    async def convert_amount(
        self,
        db: AsyncSession,
        amount: Decimal,
        from_currency: str,
        to_currency: str,
        rate_date: Optional[date] = None,
    ) -> Decimal:
        """Convert amount between currencies.

        Args:
            db: Database session
            amount: Amount to convert
            from_currency: Source currency code
            to_currency: Target currency code
            rate_date: Rate date (defaults to today)

        Returns:
            Converted amount as Decimal (quantized to 0.01)

        Raises:
            ValueError: If no rate found for currency pair
        """
        # Same currency = no conversion
        if from_currency == to_currency:
            return amount.quantize(Decimal("0.01"))

        # Get rate
        rate = await self.get_rate(
            db=db,
            base_currency=from_currency,
            quote_currency=to_currency,
            rate_date=rate_date,
        )

        # Convert and quantize
        converted = (amount * rate).quantize(Decimal("0.01"))

        self.logger.info(
            "amount_converted",
            amount=str(amount),
            from_currency=from_currency,
            to_currency=to_currency,
            rate=str(rate),
            converted=str(converted),
        )

        return converted

    async def convert_snapshot_amounts(
        self,
        db: AsyncSession,
        payload: dict,
        from_currency: str,
        to_currency: str,
        fields: list[str],
        rate_date: Optional[date] = None,
    ) -> dict:
        """Convert multiple fields in a snapshot dict.

        Args:
            db: Database session
            payload: Snapshot dict to convert
            from_currency: Source currency code
            to_currency: Target currency code
            fields: List of field names to convert
            rate_date: Rate date (defaults to today)

        Returns:
            New dict with converted amounts (original dict unchanged)

        Raises:
            ValueError: If no rate found for currency pair
        """
        # Same currency = return copy
        if from_currency == to_currency:
            return payload.copy()

        # Get rate once
        rate = await self.get_rate(
            db=db,
            base_currency=from_currency,
            quote_currency=to_currency,
            rate_date=rate_date,
        )

        # Convert fields
        converted_payload = payload.copy()
        for field in fields:
            if field in converted_payload and converted_payload[field] is not None:
                original_value = Decimal(str(converted_payload[field]))
                converted_value = (original_value * rate).quantize(Decimal("0.01"))
                converted_payload[field] = float(converted_value)

        self.logger.info(
            "snapshot_amounts_converted",
            from_currency=from_currency,
            to_currency=to_currency,
            fields=fields,
            rate=str(rate),
        )

        return converted_payload


__all__ = ["CurrencyConverter"]
