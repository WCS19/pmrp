"""Typed repository for current portfolio position projections."""

from __future__ import annotations

from sqlalchemy import Select, Update, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.identifiers import AccountId, ContractId, MarketId, OutcomeId, PositionId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import Position
from pmrp.storage.errors import (
    ConcurrencyConflictError,
    InvariantViolationError,
    classify_storage_error,
)
from pmrp.storage.models import PositionRow

_TEXT_FILTER_MAX_LENGTH = 128
_EXCHANGE_MAX_LENGTH = 64
_DEFAULT_LIST_LIMIT = 500
_MAX_LIST_LIMIT = 5_000


class PositionRepository:
    """Persist, query, and optimistic-concurrency-save position projections."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, position: Position) -> None:
        """Insert a position projection and flush without committing."""

        row = position_to_row(position)
        try:
            self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get(self, position_id: PositionId | str) -> Position | None:
        """Return a position by durable position ID."""

        position_id = _validate_identifier(position_id, PositionId)
        statement = select(PositionRow).where(PositionRow.position_id == str(position_id))
        return await self._one_or_none(statement)

    async def get_by_contract(
        self,
        *,
        exchange: str,
        account_id: AccountId | str,
        contract_id: ContractId | str,
    ) -> Position | None:
        """Return the unique position for an exchange account and contract."""

        exchange = _validate_text(exchange, field_name="exchange", max_length=_EXCHANGE_MAX_LENGTH)
        account_id = _validate_identifier(account_id, AccountId)
        contract_id = _validate_identifier(contract_id, ContractId)
        statement = select(PositionRow).where(
            PositionRow.exchange == exchange,
            PositionRow.account_id == str(account_id),
            PositionRow.contract_id == str(contract_id),
        )
        return await self._one_or_none(statement)

    async def list_for_account_market(
        self,
        *,
        exchange: str,
        account_id: AccountId | str,
        market_id: MarketId | str | None = None,
        limit: int = _DEFAULT_LIST_LIMIT,
    ) -> tuple[Position, ...]:
        """Return account positions, optionally scoped to one market."""

        exchange = _validate_text(exchange, field_name="exchange", max_length=_EXCHANGE_MAX_LENGTH)
        account_id = _validate_identifier(account_id, AccountId)
        _validate_limit(limit)
        statement = (
            select(PositionRow)
            .where(
                PositionRow.exchange == exchange,
                PositionRow.account_id == str(account_id),
            )
            .order_by(PositionRow.market_id, PositionRow.contract_id, PositionRow.position_id)
            .limit(limit)
        )
        if market_id is not None:
            market_id = _validate_identifier(market_id, MarketId)
            statement = statement.where(PositionRow.market_id == str(market_id))
        return await self._many(statement)

    async def save(self, position: Position, *, expected_version: int) -> None:
        """Save a position only when the durable version matches."""

        _validate_expected_version(expected_version)
        if position.aggregate_version != expected_version + 1:
            raise InvariantViolationError(
                "position aggregate_version must increment expected_version by one",
                context={"position_id": str(position.position_id)},
            )

        statement = (
            update(PositionRow)
            .where(
                PositionRow.position_id == str(position.position_id),
                PositionRow.aggregate_version == expected_version,
            )
            .values(**_position_row_values(position))
        )
        row_count = await self._execute_update(statement)
        if row_count != 1:
            raise ConcurrencyConflictError(
                "position version conflict",
                retryable=True,
                context={"position_id": str(position.position_id)},
            )

    async def _one_or_none(self, statement: Select[tuple[PositionRow]]) -> Position | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        row = result.scalar_one_or_none()
        if row is None:
            return None
        return position_from_row(row)

    async def _many(self, statement: Select[tuple[PositionRow]]) -> tuple[Position, ...]:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return tuple(position_from_row(row) for row in result.scalars().all())

    async def _execute_update(self, statement: Update) -> int:
        try:
            result = await self._session.execute(statement)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return int(getattr(result, "rowcount", 0) or 0)


def position_to_row(position: Position) -> PositionRow:
    """Map a canonical position into its storage row."""

    return PositionRow(**_position_row_values(position))


def position_from_row(row: PositionRow) -> Position:
    """Map a storage row into a validated canonical position."""

    currency = row.currency
    return Position(
        position_id=PositionId(row.position_id),
        exchange=row.exchange,
        account_id=AccountId(row.account_id),
        market_id=MarketId(row.market_id),
        contract_id=ContractId(row.contract_id),
        outcome_id=OutcomeId(row.outcome_id),
        quantity=row.quantity,
        average_entry_price=row.average_entry_price,
        realized_pnl=Money(amount=row.realized_pnl_amount, currency=currency),
        unrealized_pnl=Money(amount=row.unrealized_pnl_amount, currency=currency),
        fees_paid=Money(amount=row.fees_paid_amount, currency=currency),
        rebates_received=Money(amount=row.rebates_received_amount, currency=currency),
        opened_at=row.opened_at,
        last_updated_at=row.last_updated_at,
        aggregate_version=row.aggregate_version,
    )


def _position_row_values(position: Position) -> dict[str, object]:
    currency = _position_currency(position)
    return {
        "position_id": str(position.position_id),
        "exchange": position.exchange,
        "account_id": str(position.account_id),
        "market_id": str(position.market_id),
        "contract_id": str(position.contract_id),
        "outcome_id": str(position.outcome_id),
        "quantity": position.quantity,
        "average_entry_price": position.average_entry_price,
        "realized_pnl_amount": position.realized_pnl.amount,
        "unrealized_pnl_amount": position.unrealized_pnl.amount,
        "currency": currency,
        "fees_paid_amount": position.fees_paid.amount,
        "rebates_received_amount": position.rebates_received.amount,
        "opened_at": position.opened_at,
        "last_updated_at": position.last_updated_at,
        "aggregate_version": position.aggregate_version,
    }


def _position_currency(position: Position) -> str:
    currencies = {
        position.realized_pnl.currency,
        position.unrealized_pnl.currency,
        position.fees_paid.currency,
        position.rebates_received.currency,
    }
    if len(currencies) != 1:
        raise InvariantViolationError(
            "position monetary fields must share one currency",
            context={"position_id": str(position.position_id)},
        )
    return next(iter(currencies))


def _validate_identifier[
    IdentifierT: AccountId | ContractId | MarketId | OutcomeId | PositionId,
](
    value: IdentifierT | str,
    identifier_type: type[IdentifierT],
) -> IdentifierT:
    if type(value) is identifier_type:
        return value
    return identifier_type(value)


def _validate_text(
    value: str,
    *,
    field_name: str,
    max_length: int = _TEXT_FILTER_MAX_LENGTH,
) -> str:
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
        msg = "position list limit must be an integer"
        raise TypeError(msg)
    if limit <= 0:
        raise ValueError("position list limit must be positive")
    if limit > _MAX_LIST_LIMIT:
        raise ValueError("position list limit must be at most 5000")


def _validate_expected_version(expected_version: int) -> None:
    if type(expected_version) is not int:
        msg = "expected_version must be an integer"
        raise TypeError(msg)
    if expected_version < 0:
        raise ValueError("expected_version must be nonnegative")
