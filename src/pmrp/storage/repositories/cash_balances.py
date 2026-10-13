"""Typed repository for current portfolio cash balance projections."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import Select, Update, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.identifiers import AccountId
from pmrp.schemas.numeric import validate_currency
from pmrp.schemas.portfolio import CashBalance
from pmrp.storage.errors import ConcurrencyConflictError, classify_storage_error
from pmrp.storage.models import CashBalanceRow

_BALANCE_ID_MAX_LENGTH = 128
_EXCHANGE_MAX_LENGTH = 64
_DEFAULT_LIST_LIMIT = 500
_MAX_LIST_LIMIT = 5_000


@dataclass(frozen=True, slots=True)
class CashBalanceRecord:
    """Cash balance projection plus its storage aggregate version."""

    balance: CashBalance
    aggregate_version: int


class CashBalanceRepository:
    """Persist, query, and optimistic-concurrency-save cash balance projections."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, balance: CashBalance) -> None:
        """Insert a cash balance projection and flush without committing."""

        row = cash_balance_to_row(balance)
        try:
            self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get(self, balance_id: str) -> CashBalance | None:
        """Return a cash balance by durable balance ID."""

        record = await self.get_record(balance_id)
        if record is None:
            return None
        return record.balance

    async def get_record(self, balance_id: str) -> CashBalanceRecord | None:
        """Return a cash balance and its durable aggregate version."""

        balance_id = _validate_text(
            balance_id,
            field_name="balance_id",
            max_length=_BALANCE_ID_MAX_LENGTH,
        )
        statement = select(CashBalanceRow).where(CashBalanceRow.balance_id == balance_id)
        return await self._one_or_none_record(statement)

    async def get_by_account_currency(
        self,
        *,
        exchange: str,
        account_id: AccountId | str,
        currency: str,
    ) -> CashBalance | None:
        """Return the unique cash balance for an exchange account and currency."""

        record = await self.get_by_account_currency_record(
            exchange=exchange,
            account_id=account_id,
            currency=currency,
        )
        if record is None:
            return None
        return record.balance

    async def get_by_account_currency_record(
        self,
        *,
        exchange: str,
        account_id: AccountId | str,
        currency: str,
    ) -> CashBalanceRecord | None:
        """Return a unique cash balance and its durable aggregate version."""

        exchange = _validate_text(exchange, field_name="exchange", max_length=_EXCHANGE_MAX_LENGTH)
        account_id = _validate_account_id(account_id)
        currency = validate_currency(currency)
        statement = select(CashBalanceRow).where(
            CashBalanceRow.exchange == exchange,
            CashBalanceRow.account_id == str(account_id),
            CashBalanceRow.currency == currency,
        )
        return await self._one_or_none_record(statement)

    async def list_for_account(
        self,
        *,
        exchange: str,
        account_id: AccountId | str,
        limit: int = _DEFAULT_LIST_LIMIT,
    ) -> tuple[CashBalance, ...]:
        """Return account cash balances in deterministic currency order."""

        exchange = _validate_text(exchange, field_name="exchange", max_length=_EXCHANGE_MAX_LENGTH)
        account_id = _validate_account_id(account_id)
        _validate_limit(limit)
        statement = (
            select(CashBalanceRow)
            .where(
                CashBalanceRow.exchange == exchange,
                CashBalanceRow.account_id == str(account_id),
            )
            .order_by(CashBalanceRow.currency, CashBalanceRow.balance_id)
            .limit(limit)
        )
        return await self._many(statement)

    async def save(self, balance: CashBalance, *, expected_version: int) -> None:
        """Save a cash balance only when the durable version matches."""

        _validate_aggregate_version(expected_version, field_name="expected_version")
        next_version = expected_version + 1
        statement = (
            update(CashBalanceRow)
            .where(
                CashBalanceRow.balance_id == balance.balance_id,
                CashBalanceRow.aggregate_version == expected_version,
            )
            .values(**_cash_balance_row_values(balance, aggregate_version=next_version))
        )
        row_count = await self._execute_update(statement)
        if row_count != 1:
            raise ConcurrencyConflictError(
                "cash balance version conflict",
                retryable=True,
                context={"balance_id": balance.balance_id},
            )

    async def _one_or_none_record(
        self,
        statement: Select[tuple[CashBalanceRow]],
    ) -> CashBalanceRecord | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        row = result.scalar_one_or_none()
        if row is None:
            return None
        return cash_balance_record_from_row(row)

    async def _many(self, statement: Select[tuple[CashBalanceRow]]) -> tuple[CashBalance, ...]:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return tuple(cash_balance_from_row(row) for row in result.scalars().all())

    async def _execute_update(self, statement: Update) -> int:
        try:
            result = await self._session.execute(statement)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return int(getattr(result, "rowcount", 0) or 0)


def cash_balance_to_row(
    balance: CashBalance,
    *,
    aggregate_version: int = 0,
) -> CashBalanceRow:
    """Map a canonical cash balance into its storage row."""

    return CashBalanceRow(**_cash_balance_row_values(balance, aggregate_version=aggregate_version))


def cash_balance_from_row(row: CashBalanceRow) -> CashBalance:
    """Map a storage row into a validated canonical cash balance."""

    return CashBalance(
        balance_id=row.balance_id,
        exchange=row.exchange,
        account_id=AccountId(row.account_id),
        currency=row.currency,
        available=row.available,
        reserved=row.reserved,
        total=row.total,
        captured_at=row.captured_at,
    )


def cash_balance_record_from_row(row: CashBalanceRow) -> CashBalanceRecord:
    """Map a storage row into a canonical cash balance plus storage version."""

    return CashBalanceRecord(
        balance=cash_balance_from_row(row),
        aggregate_version=row.aggregate_version,
    )


def _cash_balance_row_values(
    balance: CashBalance,
    *,
    aggregate_version: int,
) -> dict[str, object]:
    _validate_aggregate_version(aggregate_version, field_name="aggregate_version")
    return {
        "balance_id": balance.balance_id,
        "exchange": balance.exchange,
        "account_id": str(balance.account_id),
        "currency": balance.currency,
        "available": balance.available,
        "reserved": balance.reserved,
        "total": balance.total,
        "captured_at": balance.captured_at,
        "aggregate_version": aggregate_version,
    }


def _validate_account_id(value: AccountId | str) -> AccountId:
    if type(value) is AccountId:
        return value
    return AccountId(value)


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
        msg = "cash balance list limit must be an integer"
        raise TypeError(msg)
    if limit <= 0:
        raise ValueError("cash balance list limit must be positive")
    if limit > _MAX_LIST_LIMIT:
        raise ValueError("cash balance list limit must be at most 5000")


def _validate_aggregate_version(value: int, *, field_name: str) -> None:
    if type(value) is not int:
        msg = f"{field_name} must be an integer"
        raise TypeError(msg)
    if value < 0:
        raise ValueError(f"{field_name} must be nonnegative")
