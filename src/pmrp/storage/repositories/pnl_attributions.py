"""Typed repository for portfolio PnL attribution rows."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, Update, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.identifiers import MarketId, StrategyId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import PnlAttribution
from pmrp.schemas.time import parse_utc_datetime
from pmrp.storage.errors import (
    ConcurrencyConflictError,
    InvariantViolationError,
    classify_storage_error,
)
from pmrp.storage.models import PnlAttributionRow

_ATTRIBUTION_ID_MAX_LENGTH = 128
_EXCHANGE_MAX_LENGTH = 64
_DEFAULT_LIST_LIMIT = 500
_MAX_LIST_LIMIT = 5_000


class PnlAttributionRepository:
    """Persist and query exact portfolio PnL attribution records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, attribution: PnlAttribution) -> None:
        """Insert one PnL attribution and flush without committing."""

        row = pnl_attribution_to_row(attribution)
        try:
            self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get(self, attribution_id: str) -> PnlAttribution | None:
        """Return one PnL attribution by durable attribution ID."""

        attribution_id = _validate_text(
            attribution_id,
            field_name="attribution_id",
            max_length=_ATTRIBUTION_ID_MAX_LENGTH,
        )
        statement = select(PnlAttributionRow).where(
            PnlAttributionRow.attribution_id == attribution_id
        )
        return await self._one_or_none(statement)

    async def list_by_strategy_period(
        self,
        *,
        strategy_id: StrategyId | str,
        starts_at: datetime,
        ends_at: datetime,
        limit: int = _DEFAULT_LIST_LIMIT,
    ) -> tuple[PnlAttribution, ...]:
        """Return strategy PnL attribution rows fully contained in a period."""

        strategy_id = _validate_identifier(strategy_id, StrategyId)
        starts_at, ends_at = _validate_period(starts_at=starts_at, ends_at=ends_at)
        _validate_limit(limit)
        statement = (
            select(PnlAttributionRow)
            .where(
                PnlAttributionRow.strategy_id == str(strategy_id),
                PnlAttributionRow.starts_at >= starts_at,
                PnlAttributionRow.ends_at <= ends_at,
            )
            .order_by(
                PnlAttributionRow.starts_at,
                PnlAttributionRow.ends_at,
                PnlAttributionRow.attribution_id,
            )
            .limit(limit)
        )
        return await self._many(statement)

    async def list_by_market(
        self,
        market_id: MarketId | str,
        *,
        exchange: str | None = None,
        limit: int = _DEFAULT_LIST_LIMIT,
    ) -> tuple[PnlAttribution, ...]:
        """Return market PnL attribution rows in deterministic period order."""

        market_id = _validate_identifier(market_id, MarketId)
        _validate_limit(limit)
        statement = (
            select(PnlAttributionRow)
            .where(PnlAttributionRow.market_id == str(market_id))
            .order_by(
                PnlAttributionRow.starts_at,
                PnlAttributionRow.ends_at,
                PnlAttributionRow.attribution_id,
            )
            .limit(limit)
        )
        if exchange is not None:
            exchange = _validate_text(
                exchange,
                field_name="exchange",
                max_length=_EXCHANGE_MAX_LENGTH,
            )
            statement = statement.where(PnlAttributionRow.exchange == exchange)
        return await self._many(statement)

    async def save(self, attribution: PnlAttribution) -> None:
        """Update one PnL attribution row and flush without committing."""

        statement = (
            update(PnlAttributionRow)
            .where(PnlAttributionRow.attribution_id == attribution.attribution_id)
            .values(**_pnl_attribution_row_values(attribution))
        )
        row_count = await self._execute_update(statement)
        if row_count != 1:
            raise ConcurrencyConflictError(
                "PnL attribution update conflict",
                retryable=True,
                context={"attribution_id": attribution.attribution_id},
            )

    async def _one_or_none(
        self,
        statement: Select[tuple[PnlAttributionRow]],
    ) -> PnlAttribution | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        row = result.scalar_one_or_none()
        if row is None:
            return None
        return pnl_attribution_from_row(row)

    async def _many(
        self,
        statement: Select[tuple[PnlAttributionRow]],
    ) -> tuple[PnlAttribution, ...]:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return tuple(pnl_attribution_from_row(row) for row in result.scalars().all())

    async def _execute_update(self, statement: Update) -> int:
        try:
            result = await self._session.execute(statement)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return int(getattr(result, "rowcount", 0) or 0)


def pnl_attribution_to_row(attribution: PnlAttribution) -> PnlAttributionRow:
    """Map a canonical PnL attribution into its storage row."""

    return PnlAttributionRow(**_pnl_attribution_row_values(attribution))


def pnl_attribution_from_row(row: PnlAttributionRow) -> PnlAttribution:
    """Map a storage row into a validated canonical PnL attribution."""

    currency = row.currency
    return PnlAttribution(
        attribution_id=row.attribution_id,
        strategy_id=StrategyId(row.strategy_id) if row.strategy_id is not None else None,
        market_id=MarketId(row.market_id) if row.market_id is not None else None,
        exchange=row.exchange,
        starts_at=row.starts_at,
        ends_at=row.ends_at,
        realized_trading_pnl=Money(amount=row.realized_trading_pnl, currency=currency),
        unrealized_pnl_change=Money(amount=row.unrealized_pnl_change, currency=currency),
        fees=Money(amount=row.fees, currency=currency),
        rebates=Money(amount=row.rebates, currency=currency),
        slippage=(
            Money(amount=row.slippage, currency=currency) if row.slippage is not None else None
        ),
        settlement_pnl=(
            Money(amount=row.settlement_pnl, currency=currency)
            if row.settlement_pnl is not None
            else None
        ),
        total_pnl=Money(amount=row.total_pnl, currency=currency),
        calculation_version=row.calculation_version,
    )


def _pnl_attribution_row_values(attribution: PnlAttribution) -> dict[str, object]:
    currency = _pnl_attribution_currency(attribution)
    return {
        "attribution_id": attribution.attribution_id,
        "strategy_id": (
            str(attribution.strategy_id) if attribution.strategy_id is not None else None
        ),
        "market_id": str(attribution.market_id) if attribution.market_id is not None else None,
        "exchange": attribution.exchange,
        "starts_at": attribution.starts_at,
        "ends_at": attribution.ends_at,
        "currency": currency,
        "realized_trading_pnl": attribution.realized_trading_pnl.amount,
        "unrealized_pnl_change": attribution.unrealized_pnl_change.amount,
        "fees": attribution.fees.amount,
        "rebates": attribution.rebates.amount,
        "slippage": _optional_money_amount(attribution.slippage),
        "settlement_pnl": _optional_money_amount(attribution.settlement_pnl),
        "total_pnl": attribution.total_pnl.amount,
        "calculation_version": attribution.calculation_version,
    }


def _pnl_attribution_currency(attribution: PnlAttribution) -> str:
    money_components = (
        attribution.realized_trading_pnl,
        attribution.unrealized_pnl_change,
        attribution.fees,
        attribution.rebates,
        attribution.slippage,
        attribution.settlement_pnl,
        attribution.total_pnl,
    )
    currencies = {money.currency for money in money_components if money is not None}
    if len(currencies) != 1:
        raise InvariantViolationError(
            "PnL attribution monetary fields must share one currency",
            context={"attribution_id": attribution.attribution_id},
        )
    return next(iter(currencies))


def _optional_money_amount(value: Money | None) -> Decimal | None:
    if value is None:
        return None
    return value.amount


def _validate_identifier[IdentifierT: MarketId | StrategyId](
    value: IdentifierT | str,
    identifier_type: type[IdentifierT],
) -> IdentifierT:
    if type(value) is identifier_type:
        return value
    return identifier_type(value)


def _validate_period(*, starts_at: datetime, ends_at: datetime) -> tuple[datetime, datetime]:
    starts_at = parse_utc_datetime(starts_at)
    ends_at = parse_utc_datetime(ends_at)
    if ends_at <= starts_at:
        raise ValueError("ends_at must be after starts_at")
    return starts_at, ends_at


def _validate_text(value: str, *, field_name: str, max_length: int) -> str:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if value == "":
        raise ValueError(f"{field_name} must not be empty")
    if len(value) > max_length:
        raise ValueError(f"{field_name} must be at most {max_length} characters")
    return value


def _validate_limit(limit: int) -> None:
    if type(limit) is not int:
        msg = "PnL attribution list limit must be an integer"
        raise TypeError(msg)
    if limit <= 0:
        raise ValueError("PnL attribution list limit must be positive")
    if limit > _MAX_LIST_LIMIT:
        raise ValueError("PnL attribution list limit must be at most 5000")
