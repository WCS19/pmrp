"""Portfolio snapshot reconciliation helpers."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from decimal import Decimal
from typing import Final

from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.schemas.identifiers import AccountId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import (
    CashBalance,
    PortfolioSnapshot,
    Position,
    ReconciliationMismatch,
    ReconciliationResult,
    ReconciliationStatus,
)
from pmrp.schemas.serialization import canonical_sha256

RECONCILIATION_SEVERITY_MISMATCH: Final = "mismatch"
RECONCILIATION_SEVERITY_UNKNOWN: Final = "unknown"

_PRESENT = "present"


def reconcile_portfolio_snapshots(
    *,
    reconciliation_id: str,
    exchange: str,
    account_id: AccountId,
    local_snapshot: PortfolioSnapshot,
    external_snapshot: PortfolioSnapshot,
    started_at: datetime,
    completed_at: datetime,
) -> ReconciliationResult:
    """Compare local and exchange-authoritative portfolio snapshots."""

    _validate_snapshot_scope(
        snapshot=local_snapshot,
        exchange=exchange,
        account_id=account_id,
        label="local",
    )
    _validate_snapshot_scope(
        snapshot=external_snapshot,
        exchange=exchange,
        account_id=account_id,
        label="external",
    )

    position_mismatches = tuple(
        _compare_positions(
            reconciliation_id=reconciliation_id,
            local_positions=local_snapshot.positions,
            external_positions=external_snapshot.positions,
        )
    )
    balance_mismatches = tuple(
        _compare_balances(
            reconciliation_id=reconciliation_id,
            local_balances=local_snapshot.balances,
            external_balances=external_snapshot.balances,
        )
    )
    position_ids = {
        *(str(position.position_id) for position in local_snapshot.positions),
        *(str(position.position_id) for position in external_snapshot.positions),
    }
    balance_ids = {
        *(balance.balance_id for balance in local_snapshot.balances),
        *(balance.balance_id for balance in external_snapshot.balances),
    }

    return build_reconciliation_result(
        reconciliation_id=reconciliation_id,
        exchange=exchange,
        account_id=account_id,
        started_at=started_at,
        completed_at=completed_at,
        mismatches=(*position_mismatches, *balance_mismatches),
        positions_checked=len(position_ids),
        balances_checked=len(balance_ids),
    )


def build_reconciliation_result(
    *,
    reconciliation_id: str,
    exchange: str,
    account_id: AccountId,
    started_at: datetime,
    completed_at: datetime,
    mismatches: Iterable[ReconciliationMismatch],
    open_orders_checked: int = 0,
    positions_checked: int = 0,
    balances_checked: int = 0,
    fills_checked: int = 0,
) -> ReconciliationResult:
    """Build a reconciliation result with deterministic trading-gate status."""

    mismatch_tuple = tuple(mismatches)
    status = _status_for_mismatches(mismatch_tuple)
    return ReconciliationResult(
        reconciliation_id=reconciliation_id,
        exchange=exchange,
        account_id=account_id,
        started_at=started_at,
        completed_at=completed_at,
        status=status,
        mismatches=mismatch_tuple,
        open_orders_checked=open_orders_checked,
        positions_checked=positions_checked,
        balances_checked=balances_checked,
        fills_checked=fills_checked,
        trading_gate_released=status is ReconciliationStatus.HEALTHY,
    )


def build_reconciliation_mismatch(
    *,
    reconciliation_id: str,
    category: str,
    identity: str,
    local_value: object | None,
    external_value: object | None,
    severity: str = RECONCILIATION_SEVERITY_MISMATCH,
    explanation: str | None = None,
    requires_manual_review: bool = True,
) -> ReconciliationMismatch:
    """Build a deterministic reconciliation mismatch record."""

    formatted_local = _format_value(local_value)
    formatted_external = _format_value(external_value)
    return ReconciliationMismatch(
        mismatch_id=derive_reconciliation_mismatch_id(
            reconciliation_id=reconciliation_id,
            category=category,
            identity=identity,
            local_value=formatted_local,
            external_value=formatted_external,
        ),
        category=category,
        local_value=formatted_local,
        external_value=formatted_external,
        severity=severity,
        explanation=explanation,
        requires_manual_review=requires_manual_review,
    )


def derive_reconciliation_mismatch_id(
    *,
    reconciliation_id: str,
    category: str,
    identity: str,
    local_value: str | None,
    external_value: str | None,
) -> str:
    """Derive a stable mismatch identifier from compared values."""

    digest = canonical_sha256(
        {
            "category": category,
            "external_value": external_value,
            "identity": identity,
            "local_value": local_value,
            "reconciliation_id": reconciliation_id,
            "schema": "pmrp.reconciliation_mismatch.v1",
        }
    ).removeprefix("sha256:")
    return f"recon_mismatch_{digest[:32]}"


def _compare_positions(
    *,
    reconciliation_id: str,
    local_positions: tuple[Position, ...],
    external_positions: tuple[Position, ...],
) -> Iterable[ReconciliationMismatch]:
    local_by_id = {str(position.position_id): position for position in local_positions}
    external_by_id = {str(position.position_id): position for position in external_positions}

    for position_id in sorted(local_by_id.keys() | external_by_id.keys()):
        local = local_by_id.get(position_id)
        external = external_by_id.get(position_id)
        if local is None:
            yield build_reconciliation_mismatch(
                reconciliation_id=reconciliation_id,
                category="position.missing_local",
                identity=position_id,
                local_value=None,
                external_value=_PRESENT,
                explanation="External position is missing from local projection.",
            )
            continue
        if external is None:
            yield build_reconciliation_mismatch(
                reconciliation_id=reconciliation_id,
                category="position.missing_external",
                identity=position_id,
                local_value=_PRESENT,
                external_value=None,
                explanation="Local position is missing from external snapshot.",
            )
            continue

        yield from _compare_position_fields(
            reconciliation_id=reconciliation_id,
            position_id=position_id,
            local=local,
            external=external,
        )


def _compare_position_fields(
    *,
    reconciliation_id: str,
    position_id: str,
    local: Position,
    external: Position,
) -> Iterable[ReconciliationMismatch]:
    comparisons = (
        ("position.exchange", local.exchange, external.exchange),
        ("position.account_id", local.account_id, external.account_id),
        ("position.market_id", local.market_id, external.market_id),
        ("position.contract_id", local.contract_id, external.contract_id),
        ("position.outcome_id", local.outcome_id, external.outcome_id),
        ("position.quantity", local.quantity, external.quantity),
        ("position.average_entry_price", local.average_entry_price, external.average_entry_price),
        ("position.realized_pnl", local.realized_pnl, external.realized_pnl),
        ("position.unrealized_pnl", local.unrealized_pnl, external.unrealized_pnl),
        ("position.fees_paid", local.fees_paid, external.fees_paid),
        ("position.rebates_received", local.rebates_received, external.rebates_received),
    )
    for category, local_value, external_value in comparisons:
        if local_value != external_value:
            yield build_reconciliation_mismatch(
                reconciliation_id=reconciliation_id,
                category=category,
                identity=position_id,
                local_value=local_value,
                external_value=external_value,
            )


def _compare_balances(
    *,
    reconciliation_id: str,
    local_balances: tuple[CashBalance, ...],
    external_balances: tuple[CashBalance, ...],
) -> Iterable[ReconciliationMismatch]:
    local_by_id = {balance.balance_id: balance for balance in local_balances}
    external_by_id = {balance.balance_id: balance for balance in external_balances}

    for balance_id in sorted(local_by_id.keys() | external_by_id.keys()):
        local = local_by_id.get(balance_id)
        external = external_by_id.get(balance_id)
        if local is None:
            yield build_reconciliation_mismatch(
                reconciliation_id=reconciliation_id,
                category="balance.missing_local",
                identity=balance_id,
                local_value=None,
                external_value=_PRESENT,
                explanation="External balance is missing from local projection.",
            )
            continue
        if external is None:
            yield build_reconciliation_mismatch(
                reconciliation_id=reconciliation_id,
                category="balance.missing_external",
                identity=balance_id,
                local_value=_PRESENT,
                external_value=None,
                explanation="Local balance is missing from external snapshot.",
            )
            continue

        yield from _compare_balance_fields(
            reconciliation_id=reconciliation_id,
            balance_id=balance_id,
            local=local,
            external=external,
        )


def _compare_balance_fields(
    *,
    reconciliation_id: str,
    balance_id: str,
    local: CashBalance,
    external: CashBalance,
) -> Iterable[ReconciliationMismatch]:
    comparisons = (
        ("balance.exchange", local.exchange, external.exchange),
        ("balance.account_id", local.account_id, external.account_id),
        ("balance.currency", local.currency, external.currency),
        ("balance.available", local.available, external.available),
        ("balance.reserved", local.reserved, external.reserved),
        ("balance.total", local.total, external.total),
    )
    for category, local_value, external_value in comparisons:
        if local_value != external_value:
            yield build_reconciliation_mismatch(
                reconciliation_id=reconciliation_id,
                category=category,
                identity=balance_id,
                local_value=local_value,
                external_value=external_value,
            )


def _validate_snapshot_scope(
    *,
    snapshot: PortfolioSnapshot,
    exchange: str,
    account_id: AccountId,
    label: str,
) -> None:
    for position in snapshot.positions:
        if position.exchange != exchange:
            msg = f"{label} position exchange does not match reconciliation exchange"
            raise PortfolioProjectionError(msg)
        if position.account_id != account_id:
            msg = f"{label} position account_id does not match reconciliation account_id"
            raise PortfolioProjectionError(msg)
    for balance in snapshot.balances:
        if balance.exchange != exchange:
            msg = f"{label} balance exchange does not match reconciliation exchange"
            raise PortfolioProjectionError(msg)
        if balance.account_id != account_id:
            msg = f"{label} balance account_id does not match reconciliation account_id"
            raise PortfolioProjectionError(msg)


def _status_for_mismatches(
    mismatches: tuple[ReconciliationMismatch, ...],
) -> ReconciliationStatus:
    if not mismatches:
        return ReconciliationStatus.HEALTHY
    if any(mismatch.severity == RECONCILIATION_SEVERITY_UNKNOWN for mismatch in mismatches):
        return ReconciliationStatus.UNKNOWN
    return ReconciliationStatus.MISMATCH


def _format_value(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, Money):
        return f"{value.amount} {value.currency}"
    if isinstance(value, Decimal):
        return str(value)
    return str(value)
