"""Typed repository for completed account reconciliation results."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from sqlalchemy import Select, desc, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.identifiers import AccountId
from pmrp.schemas.portfolio import (
    ReconciliationMismatch,
    ReconciliationResult,
    ReconciliationStatus,
)
from pmrp.storage.errors import InvariantViolationError, classify_storage_error
from pmrp.storage.models import ReconciliationMismatchRow, ReconciliationRunRow

_RECONCILIATION_ID_MAX_LENGTH = 128
_EXCHANGE_MAX_LENGTH = 64
_INITIATED_BY_MAX_LENGTH = 128
_REASON_MAX_LENGTH = 1024
_DEFAULT_LIST_LIMIT = 500
_MAX_LIST_LIMIT = 5_000


class ReconciliationResultRepository:
    """Persist and query completed canonical reconciliation results."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(
        self,
        result: ReconciliationResult,
        *,
        initiated_by: str,
        reason: str | None = None,
    ) -> None:
        """Insert a completed reconciliation result and flush without committing."""

        run_row, mismatch_rows = reconciliation_result_to_rows(
            result,
            initiated_by=initiated_by,
            reason=reason,
        )
        try:
            self._session.add(run_row)
            for mismatch_row in mismatch_rows:
                self._session.add(mismatch_row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get(self, reconciliation_id: str) -> ReconciliationResult | None:
        """Return one reconciliation result by durable reconciliation ID."""

        reconciliation_id = _validate_text(
            reconciliation_id,
            field_name="reconciliation_id",
            max_length=_RECONCILIATION_ID_MAX_LENGTH,
        )
        statement = select(ReconciliationRunRow).where(
            ReconciliationRunRow.reconciliation_id == reconciliation_id
        )
        return await self._one_or_none(statement)

    async def latest_for_account(
        self,
        *,
        exchange: str,
        account_id: AccountId | str,
    ) -> ReconciliationResult | None:
        """Return the newest reconciliation result for one exchange account."""

        exchange = _validate_text(exchange, field_name="exchange", max_length=_EXCHANGE_MAX_LENGTH)
        account_id = _validate_account_id(account_id)
        statement = (
            select(ReconciliationRunRow)
            .where(
                ReconciliationRunRow.exchange == exchange,
                ReconciliationRunRow.account_id == str(account_id),
                ReconciliationRunRow.completed_at.is_not(None),
            )
            .order_by(
                desc(ReconciliationRunRow.started_at),
                desc(ReconciliationRunRow.reconciliation_id),
            )
            .limit(1)
        )
        return await self._one_or_none(statement)

    async def list_by_status(
        self,
        status: ReconciliationStatus | str,
        *,
        limit: int = _DEFAULT_LIST_LIMIT,
    ) -> tuple[ReconciliationResult, ...]:
        """Return reconciliation results for one status in newest-first order."""

        status = _validate_status(status)
        _validate_limit(limit)
        statement = (
            select(ReconciliationRunRow)
            .where(
                ReconciliationRunRow.status == status.value,
                ReconciliationRunRow.completed_at.is_not(None),
            )
            .order_by(
                desc(ReconciliationRunRow.started_at),
                desc(ReconciliationRunRow.reconciliation_id),
            )
            .limit(limit)
        )
        return await self._all(statement)

    async def _one_or_none(
        self,
        statement: Select[tuple[ReconciliationRunRow]],
    ) -> ReconciliationResult | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        run_row = result.scalar_one_or_none()
        if run_row is None:
            return None
        mismatch_rows = await self._mismatch_rows_for((run_row.reconciliation_id,))
        return reconciliation_result_from_rows(run_row, mismatch_rows)

    async def _all(
        self,
        statement: Select[tuple[ReconciliationRunRow]],
    ) -> tuple[ReconciliationResult, ...]:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        run_rows = tuple(result.scalars().all())
        if not run_rows:
            return ()
        mismatch_rows = await self._mismatch_rows_for(row.reconciliation_id for row in run_rows)
        return _reconciliation_results_from_rows(run_rows, mismatch_rows)

    async def _mismatch_rows_for(
        self,
        reconciliation_ids: Iterable[str],
    ) -> tuple[ReconciliationMismatchRow, ...]:
        ids = tuple(reconciliation_ids)
        if not ids:
            return ()

        statement = (
            select(ReconciliationMismatchRow)
            .where(ReconciliationMismatchRow.reconciliation_id.in_(ids))
            .order_by(
                ReconciliationMismatchRow.reconciliation_id,
                ReconciliationMismatchRow.severity,
                ReconciliationMismatchRow.mismatch_id,
            )
        )
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc
        return tuple(result.scalars().all())


def reconciliation_result_to_rows(
    result: ReconciliationResult,
    *,
    initiated_by: str,
    reason: str | None = None,
) -> tuple[ReconciliationRunRow, tuple[ReconciliationMismatchRow, ...]]:
    """Map a canonical reconciliation result into storage rows."""

    initiated_by = _validate_text(
        initiated_by,
        field_name="initiated_by",
        max_length=_INITIATED_BY_MAX_LENGTH,
    )
    if reason is not None:
        reason = _validate_text(reason, field_name="reason", max_length=_REASON_MAX_LENGTH)

    run_row = ReconciliationRunRow(
        reconciliation_id=result.reconciliation_id,
        exchange=result.exchange,
        account_id=str(result.account_id),
        started_at=result.started_at,
        completed_at=result.completed_at,
        status=result.status.value,
        open_orders_checked=result.open_orders_checked,
        positions_checked=result.positions_checked,
        balances_checked=result.balances_checked,
        fills_checked=result.fills_checked,
        trading_gate_released=result.trading_gate_released,
        initiated_by=initiated_by,
        reason=reason,
    )
    mismatch_rows = tuple(
        ReconciliationMismatchRow(
            mismatch_id=mismatch.mismatch_id,
            reconciliation_id=result.reconciliation_id,
            category=mismatch.category,
            local_value=mismatch.local_value,
            external_value=mismatch.external_value,
            severity=mismatch.severity,
            explanation=mismatch.explanation,
            requires_manual_review=mismatch.requires_manual_review,
        )
        for mismatch in result.mismatches
    )
    return run_row, mismatch_rows


def reconciliation_result_from_rows(
    run_row: ReconciliationRunRow,
    mismatch_rows: Iterable[ReconciliationMismatchRow],
) -> ReconciliationResult:
    """Map storage rows into a validated canonical reconciliation result."""

    if run_row.completed_at is None:
        raise InvariantViolationError(
            "reconciliation run is not complete",
            context={"reconciliation_id": run_row.reconciliation_id},
        )
    mismatches = tuple(_mismatch_from_row(run_row, row) for row in mismatch_rows)
    return ReconciliationResult(
        reconciliation_id=run_row.reconciliation_id,
        exchange=run_row.exchange,
        account_id=AccountId(run_row.account_id),
        started_at=run_row.started_at,
        completed_at=run_row.completed_at,
        status=ReconciliationStatus(run_row.status),
        mismatches=mismatches,
        open_orders_checked=run_row.open_orders_checked,
        positions_checked=run_row.positions_checked,
        balances_checked=run_row.balances_checked,
        fills_checked=run_row.fills_checked,
        trading_gate_released=run_row.trading_gate_released,
    )


def _reconciliation_results_from_rows(
    run_rows: Iterable[ReconciliationRunRow],
    mismatch_rows: Iterable[ReconciliationMismatchRow],
) -> tuple[ReconciliationResult, ...]:
    mismatches_by_run: defaultdict[str, list[ReconciliationMismatchRow]] = defaultdict(list)
    for mismatch_row in mismatch_rows:
        mismatches_by_run[mismatch_row.reconciliation_id].append(mismatch_row)

    return tuple(
        reconciliation_result_from_rows(
            run_row,
            mismatches_by_run[run_row.reconciliation_id],
        )
        for run_row in run_rows
    )


def _mismatch_from_row(
    run_row: ReconciliationRunRow,
    mismatch_row: ReconciliationMismatchRow,
) -> ReconciliationMismatch:
    if mismatch_row.reconciliation_id != run_row.reconciliation_id:
        raise InvariantViolationError(
            "reconciliation mismatch belongs to a different run",
            context={"reconciliation_id": run_row.reconciliation_id},
        )
    return ReconciliationMismatch(
        mismatch_id=mismatch_row.mismatch_id,
        category=mismatch_row.category,
        local_value=mismatch_row.local_value,
        external_value=mismatch_row.external_value,
        severity=mismatch_row.severity,
        explanation=mismatch_row.explanation,
        requires_manual_review=mismatch_row.requires_manual_review,
    )


def _validate_account_id(value: AccountId | str) -> AccountId:
    if type(value) is AccountId:
        return value
    return AccountId(value)


def _validate_status(value: ReconciliationStatus | str) -> ReconciliationStatus:
    if type(value) is ReconciliationStatus:
        return value
    return ReconciliationStatus(value)


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
        msg = "reconciliation result list limit must be an integer"
        raise TypeError(msg)
    if limit <= 0:
        raise ValueError("reconciliation result list limit must be positive")
    if limit > _MAX_LIST_LIMIT:
        raise ValueError("reconciliation result list limit must be at most 5000")
