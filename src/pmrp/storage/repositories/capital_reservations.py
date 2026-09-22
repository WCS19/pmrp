"""Typed repository for pre-trade capital reservation persistence."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Select, Update, func, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.risk.reservations import CapitalReservation, CapitalReservationStatus
from pmrp.schemas.enums import ExchangeName
from pmrp.schemas.identifiers import AccountId, IntentId, MarketId, StrategyId
from pmrp.schemas.numeric import validate_currency
from pmrp.schemas.time import parse_utc_datetime
from pmrp.storage.errors import classify_storage_error
from pmrp.storage.models import CapitalReservationRow


class CapitalReservationRepository:
    """Persist, query, and release durable capital reservations."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, reservation: CapitalReservation) -> None:
        """Insert a reservation and flush without committing."""

        row = capital_reservation_to_row(reservation)
        try:
            self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get(self, reservation_id: str) -> CapitalReservation | None:
        """Return a reservation by its durable reservation ID."""

        _validate_reservation_id(reservation_id)
        statement = select(CapitalReservationRow).where(
            CapitalReservationRow.reservation_id == reservation_id
        )
        return await self._one_or_none(statement)

    async def get_by_intent(self, intent_id: IntentId) -> CapitalReservation | None:
        """Return the reservation uniquely associated with an order intent."""

        intent_id = IntentId(str(intent_id))
        statement = select(CapitalReservationRow).where(
            CapitalReservationRow.intent_id == str(intent_id)
        )
        return await self._one_or_none(statement)

    async def active_notional_sum(
        self,
        *,
        as_of: datetime,
        exchange: ExchangeName | None = None,
        account_id: AccountId | None = None,
        strategy_id: StrategyId | None = None,
        market_id: MarketId | None = None,
        currency: str | None = None,
    ) -> Decimal:
        """Return active, unreleased, unexpired reserved notional for a scope."""

        as_of = parse_utc_datetime(as_of)
        statement = select(func.coalesce(func.sum(CapitalReservationRow.notional), Decimal("0")))
        statement = statement.where(
            CapitalReservationRow.status == CapitalReservationStatus.ACTIVE.value,
            CapitalReservationRow.released_at.is_(None),
            CapitalReservationRow.expires_at > as_of,
        )
        if exchange is not None:
            statement = statement.where(
                CapitalReservationRow.exchange == ExchangeName(exchange).value
            )
        if account_id is not None:
            statement = statement.where(CapitalReservationRow.account_id == str(account_id))
        if strategy_id is not None:
            statement = statement.where(CapitalReservationRow.strategy_id == str(strategy_id))
        if market_id is not None:
            statement = statement.where(CapitalReservationRow.market_id == str(market_id))
        if currency is not None:
            currency = validate_currency(currency)
            statement = statement.where(CapitalReservationRow.currency == currency)

        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return result.scalar_one()

    async def release(self, reservation_id: str, *, released_at: datetime) -> int:
        """Release one active reservation and return the updated row count."""

        _validate_reservation_id(reservation_id)
        released_at = parse_utc_datetime(released_at)
        statement = (
            update(CapitalReservationRow)
            .where(
                CapitalReservationRow.reservation_id == reservation_id,
                CapitalReservationRow.status == CapitalReservationStatus.ACTIVE.value,
                CapitalReservationRow.released_at.is_(None),
            )
            .values(
                status=CapitalReservationStatus.RELEASED.value,
                released_at=released_at,
            )
        )
        return await self._execute_update(statement)

    async def release_expired(self, *, as_of: datetime) -> int:
        """Expire active reservations whose validity window has closed."""

        as_of = parse_utc_datetime(as_of)
        statement = (
            update(CapitalReservationRow)
            .where(
                CapitalReservationRow.status == CapitalReservationStatus.ACTIVE.value,
                CapitalReservationRow.released_at.is_(None),
                CapitalReservationRow.expires_at <= as_of,
            )
            .values(
                status=CapitalReservationStatus.EXPIRED.value,
                released_at=as_of,
            )
        )
        return await self._execute_update(statement)

    async def _one_or_none(
        self,
        statement: Select[tuple[CapitalReservationRow]],
    ) -> CapitalReservation | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        row = result.scalar_one_or_none()
        if row is None:
            return None
        return capital_reservation_from_row(row)

    async def _execute_update(self, statement: Update) -> int:
        try:
            result = await self._session.execute(statement)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return int(getattr(result, "rowcount", 0) or 0)


def capital_reservation_to_row(reservation: CapitalReservation) -> CapitalReservationRow:
    """Map a risk capital reservation into its storage row."""

    return CapitalReservationRow(
        reservation_id=reservation.reservation_id,
        intent_id=str(reservation.intent_id),
        strategy_id=str(reservation.strategy_id),
        exchange=reservation.exchange.value,
        account_id=str(reservation.account_id),
        market_id=str(reservation.market_id),
        quantity=reservation.quantity,
        notional=reservation.notional,
        currency=reservation.currency,
        status=reservation.status.value,
        created_at=reservation.created_at,
        expires_at=reservation.expires_at,
        released_at=reservation.released_at,
    )


def capital_reservation_from_row(row: CapitalReservationRow) -> CapitalReservation:
    """Map a storage row into a validated risk capital reservation."""

    return CapitalReservation(
        reservation_id=row.reservation_id,
        intent_id=IntentId(row.intent_id),
        strategy_id=StrategyId(row.strategy_id),
        exchange=ExchangeName(row.exchange),
        account_id=AccountId(row.account_id),
        market_id=MarketId(row.market_id),
        quantity=row.quantity,
        notional=row.notional,
        currency=row.currency,
        status=CapitalReservationStatus(row.status),
        created_at=row.created_at,
        expires_at=row.expires_at,
        released_at=row.released_at,
    )


def _validate_reservation_id(reservation_id: str) -> None:
    if type(reservation_id) is not str:
        msg = "capital reservation ID must be a string"
        raise TypeError(msg)
    if reservation_id == "":
        raise ValueError("capital reservation ID must not be empty")
    if len(reservation_id) > 128:
        raise ValueError("capital reservation ID must be at most 128 characters")
