"""Typed repository for durable risk input snapshot persistence."""

from __future__ import annotations

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.risk import RiskInputSnapshot
from pmrp.schemas.serialization import canonical_sha256
from pmrp.schemas.time import parse_utc_datetime
from pmrp.storage.errors import InvariantViolationError, classify_storage_error
from pmrp.storage.models import RiskInputSnapshotRow


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

    return RiskInputSnapshotRow(
        risk_input_snapshot_id=snapshot.risk_input_snapshot_id,
        captured_at=snapshot.captured_at,
        strategy_id=str(snapshot.strategy_id),
        exchange=snapshot.exchange,
        account_id=str(snapshot.account_id),
        market_id=str(snapshot.market_id),
        current_position=snapshot.current_position,
        open_order_quantity=snapshot.open_order_quantity,
        available_balance=snapshot.available_balance,
        gross_exposure=snapshot.gross_exposure,
        net_exposure=snapshot.net_exposure,
        daily_realized_pnl=snapshot.daily_realized_pnl,
        daily_unrealized_pnl=snapshot.daily_unrealized_pnl,
        market_data_age_ms=snapshot.market_data_age_ms,
        reconciliation_healthy=snapshot.reconciliation_healthy,
        kill_switch_clear=snapshot.kill_switch_clear,
        payload_hash=canonical_sha256(snapshot),
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
            "current_position": row.current_position,
            "open_order_quantity": row.open_order_quantity,
            "available_balance": row.available_balance,
            "gross_exposure": row.gross_exposure,
            "net_exposure": row.net_exposure,
            "daily_realized_pnl": row.daily_realized_pnl,
            "daily_unrealized_pnl": row.daily_unrealized_pnl,
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
