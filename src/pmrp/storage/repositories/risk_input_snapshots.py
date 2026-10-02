"""Typed repository for durable risk input snapshot persistence."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, localcontext

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.risk import RiskInputSnapshot
from pmrp.schemas.serialization import canonical_sha256
from pmrp.schemas.time import parse_utc_datetime
from pmrp.storage.errors import InvariantViolationError, classify_storage_error
from pmrp.storage.models import RiskInputSnapshotRow

_DATABASE_DECIMAL_QUANTUM = Decimal("0.000000000000000001")
_DECIMAL_FIELD_NAMES = (
    "current_position",
    "open_order_quantity",
    "available_balance",
    "gross_exposure",
    "net_exposure",
    "daily_realized_pnl",
    "daily_unrealized_pnl",
)


class RiskInputSnapshotRepository:
    """Persist and query canonical risk input snapshots."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, snapshot: RiskInputSnapshot) -> None:
        """Insert a canonical risk input snapshot and flush without committing."""

        row = risk_input_snapshot_to_row(snapshot)
        try:
            self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get(self, risk_input_snapshot_id: str) -> RiskInputSnapshot | None:
        """Return a risk input snapshot by its canonical ID."""

        statement = select(RiskInputSnapshotRow).where(
            RiskInputSnapshotRow.risk_input_snapshot_id == risk_input_snapshot_id
        )
        return await self._one_or_none(statement)

    async def _one_or_none(
        self,
        statement: Select[tuple[RiskInputSnapshotRow]],
    ) -> RiskInputSnapshot | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        row = result.scalar_one_or_none()
        if row is None:
            return None
        return risk_input_snapshot_from_row(row)


def risk_input_snapshot_to_row(snapshot: RiskInputSnapshot) -> RiskInputSnapshotRow:
    """Map a canonical risk input snapshot into its immutable storage row."""

    database_snapshot = _snapshot_with_database_decimals(snapshot)
    return RiskInputSnapshotRow(
        risk_input_snapshot_id=database_snapshot.risk_input_snapshot_id,
        captured_at=database_snapshot.captured_at,
        strategy_id=str(database_snapshot.strategy_id),
        exchange=database_snapshot.exchange,
        account_id=str(database_snapshot.account_id),
        market_id=str(database_snapshot.market_id),
        current_position=database_snapshot.current_position,
        open_order_quantity=database_snapshot.open_order_quantity,
        available_balance=database_snapshot.available_balance,
        gross_exposure=database_snapshot.gross_exposure,
        net_exposure=database_snapshot.net_exposure,
        daily_realized_pnl=database_snapshot.daily_realized_pnl,
        daily_unrealized_pnl=database_snapshot.daily_unrealized_pnl,
        market_data_age_ms=database_snapshot.market_data_age_ms,
        reconciliation_healthy=database_snapshot.reconciliation_healthy,
        kill_switch_clear=database_snapshot.kill_switch_clear,
        payload_hash=canonical_sha256(database_snapshot),
    )


def risk_input_snapshot_from_row(row: RiskInputSnapshotRow) -> RiskInputSnapshot:
    """Map a storage row back into a validated canonical risk input snapshot."""

    snapshot = RiskInputSnapshot.model_validate(
        {
            "risk_input_snapshot_id": row.risk_input_snapshot_id,
            "captured_at": parse_utc_datetime(row.captured_at),
            "strategy_id": row.strategy_id,
            "exchange": row.exchange,
            "account_id": row.account_id,
            "market_id": row.market_id,
            "current_position": _database_decimal(row.current_position, "current_position"),
            "open_order_quantity": _database_decimal(
                row.open_order_quantity,
                "open_order_quantity",
            ),
            "available_balance": _database_decimal(row.available_balance, "available_balance"),
            "gross_exposure": _database_decimal(row.gross_exposure, "gross_exposure"),
            "net_exposure": _database_decimal(row.net_exposure, "net_exposure"),
            "daily_realized_pnl": _database_decimal(
                row.daily_realized_pnl,
                "daily_realized_pnl",
            ),
            "daily_unrealized_pnl": _database_decimal(
                row.daily_unrealized_pnl,
                "daily_unrealized_pnl",
            ),
            "market_data_age_ms": row.market_data_age_ms,
            "reconciliation_healthy": row.reconciliation_healthy,
            "kill_switch_clear": row.kill_switch_clear,
        }
    )
    expected_hash = canonical_sha256(snapshot)
    if row.payload_hash != expected_hash:
        raise InvariantViolationError(
            "risk input snapshot payload hash mismatch",
            context={"risk_input_snapshot_id": row.risk_input_snapshot_id},
        )
    return snapshot


def _snapshot_with_database_decimals(snapshot: RiskInputSnapshot) -> RiskInputSnapshot:
    return snapshot.model_copy(
        update={
            field_name: _database_decimal(
                getattr(snapshot, field_name),
                field_name,
            )
            for field_name in _DECIMAL_FIELD_NAMES
        }
    )


def _database_decimal(value: Decimal, field_name: str) -> Decimal:
    with localcontext() as context:
        context.prec = 80
        try:
            quantized = value.quantize(_DATABASE_DECIMAL_QUANTUM)
        except InvalidOperation as exc:
            raise InvariantViolationError(
                "risk input snapshot decimal exceeds database scale",
                context={"field_name": field_name},
            ) from exc

    if quantized != value:
        raise InvariantViolationError(
            "risk input snapshot decimal exceeds database scale",
            context={"field_name": field_name},
        )
    return quantized
