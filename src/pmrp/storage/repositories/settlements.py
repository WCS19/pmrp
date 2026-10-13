"""Typed repository for canonical settlement lifecycle rows."""

from __future__ import annotations

from sqlalchemy import Select, Update, desc, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.identifiers import MarketId, OutcomeId, SettlementId
from pmrp.schemas.portfolio import Settlement, SettlementStatus
from pmrp.storage.errors import ConcurrencyConflictError, classify_storage_error
from pmrp.storage.models import SettlementRow

_SETTLEMENT_ID_MAX_LENGTH = 128
_EXCHANGE_MAX_LENGTH = 64
_DEFAULT_LIST_LIMIT = 500
_MAX_LIST_LIMIT = 5_000


class SettlementRepository:
    """Persist and query canonical settlement lifecycle records."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, settlement: Settlement) -> None:
        """Insert a settlement and flush without committing."""

        row = settlement_to_row(settlement)
        try:
            self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get(self, settlement_id: SettlementId | str) -> Settlement | None:
        """Return one settlement by durable settlement ID."""

        settlement_id = _validate_identifier(settlement_id, SettlementId)
        statement = select(SettlementRow).where(SettlementRow.settlement_id == str(settlement_id))
        return await self._one_or_none(statement)

    async def list_by_market(
        self,
        market_id: MarketId | str,
        *,
        exchange: str | None = None,
        limit: int = _DEFAULT_LIST_LIMIT,
    ) -> tuple[Settlement, ...]:
        """Return settlements for one market in newest-first deterministic order."""

        market_id = _validate_identifier(market_id, MarketId)
        _validate_limit(limit)
        statement = (
            select(SettlementRow)
            .where(SettlementRow.market_id == str(market_id))
            .order_by(desc(SettlementRow.created_at), desc(SettlementRow.settlement_id))
            .limit(limit)
        )
        if exchange is not None:
            exchange = _validate_text(
                exchange, field_name="exchange", max_length=_EXCHANGE_MAX_LENGTH
            )
            statement = statement.where(SettlementRow.exchange == exchange)
        return await self._many(statement)

    async def list_corrections(
        self,
        settlement_id: SettlementId | str,
        *,
        limit: int = _DEFAULT_LIST_LIMIT,
    ) -> tuple[Settlement, ...]:
        """Return corrections for one settlement in chronological order."""

        settlement_id = _validate_identifier(settlement_id, SettlementId)
        _validate_limit(limit)
        statement = (
            select(SettlementRow)
            .where(SettlementRow.correction_of_settlement_id == str(settlement_id))
            .order_by(SettlementRow.created_at, SettlementRow.settlement_id)
            .limit(limit)
        )
        return await self._many(statement)

    async def save(self, settlement: Settlement) -> None:
        """Update one settlement lifecycle row and flush without committing."""

        statement = (
            update(SettlementRow)
            .where(SettlementRow.settlement_id == str(settlement.settlement_id))
            .values(**_settlement_row_values(settlement))
        )
        row_count = await self._execute_update(statement)
        if row_count != 1:
            raise ConcurrencyConflictError(
                "settlement update conflict",
                retryable=True,
                context={"settlement_id": str(settlement.settlement_id)},
            )

    async def _one_or_none(self, statement: Select[tuple[SettlementRow]]) -> Settlement | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        row = result.scalar_one_or_none()
        if row is None:
            return None
        return settlement_from_row(row)

    async def _many(self, statement: Select[tuple[SettlementRow]]) -> tuple[Settlement, ...]:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return tuple(settlement_from_row(row) for row in result.scalars().all())

    async def _execute_update(self, statement: Update) -> int:
        try:
            result = await self._session.execute(statement)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return int(getattr(result, "rowcount", 0) or 0)


def settlement_to_row(settlement: Settlement) -> SettlementRow:
    """Map a canonical settlement into its storage row."""

    return SettlementRow(**_settlement_row_values(settlement))


def settlement_from_row(row: SettlementRow) -> Settlement:
    """Map a storage row into a validated canonical settlement."""

    return Settlement(
        settlement_id=SettlementId(row.settlement_id),
        market_id=MarketId(row.market_id),
        exchange=row.exchange,
        status=SettlementStatus(row.status),
        winning_outcome_ids=tuple(OutcomeId(outcome_id) for outcome_id in row.winning_outcome_ids),
        resolved_at=row.resolved_at,
        finalized_at=row.finalized_at,
        settled_at=row.settled_at,
        payout_per_unit=row.payout_per_unit,
        source=row.source,
        source_reference=row.source_reference,
        correction_of_settlement_id=(
            SettlementId(row.correction_of_settlement_id)
            if row.correction_of_settlement_id is not None
            else None
        ),
    )


def _settlement_row_values(settlement: Settlement) -> dict[str, object]:
    return {
        "settlement_id": str(settlement.settlement_id),
        "market_id": str(settlement.market_id),
        "exchange": settlement.exchange,
        "status": settlement.status.value,
        "winning_outcome_ids": [str(outcome_id) for outcome_id in settlement.winning_outcome_ids],
        "resolved_at": settlement.resolved_at,
        "finalized_at": settlement.finalized_at,
        "settled_at": settlement.settled_at,
        "payout_per_unit": settlement.payout_per_unit,
        "source": settlement.source,
        "source_reference": settlement.source_reference,
        "correction_of_settlement_id": (
            str(settlement.correction_of_settlement_id)
            if settlement.correction_of_settlement_id is not None
            else None
        ),
    }


def _validate_identifier[IdentifierT: MarketId | SettlementId](
    value: IdentifierT | str,
    identifier_type: type[IdentifierT],
) -> IdentifierT:
    if type(value) is identifier_type:
        return value
    return identifier_type(value)


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
        msg = "settlement list limit must be an integer"
        raise TypeError(msg)
    if limit <= 0:
        raise ValueError("settlement list limit must be positive")
    if limit > _MAX_LIST_LIMIT:
        raise ValueError("settlement list limit must be at most 5000")
