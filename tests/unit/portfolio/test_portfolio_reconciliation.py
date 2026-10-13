"""Unit tests for portfolio reconciliation helpers."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from pmrp.portfolio import (
    RECONCILIATION_SEVERITY_UNKNOWN,
    PortfolioProjectionError,
    RecordSetReconciliationResult,
    build_reconciliation_mismatch,
    build_reconciliation_result,
    derive_reconciliation_mismatch_id,
    reconcile_fill_ids,
    reconcile_open_order_ids,
    reconcile_portfolio_snapshots,
    reconcile_record_id_sets,
    reconcile_settlement_ids,
)
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import (
    CashBalance,
    PortfolioSnapshot,
    Position,
    ReconciliationStatus,
)

pytestmark = pytest.mark.unit

STARTED_AT = datetime(2026, 9, 26, 14, 0, tzinfo=UTC)
COMPLETED_AT = datetime(2026, 9, 26, 14, 0, 1, tzinfo=UTC)
CAPTURED_AT = datetime(2026, 9, 26, 13, 59, tzinfo=UTC)
RECONCILIATION_ID = "recon_portfolio_001"


def test_reconcile_portfolio_snapshots_returns_healthy_for_exact_match() -> None:
    snapshot = _snapshot()

    result = reconcile_portfolio_snapshots(
        reconciliation_id=RECONCILIATION_ID,
        exchange="kalshi",
        account_id="acct_recon_001",
        local_snapshot=snapshot,
        external_snapshot=snapshot,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )

    assert result.status is ReconciliationStatus.HEALTHY
    assert result.trading_gate_released is True
    assert result.mismatches == ()
    assert result.positions_checked == 1
    assert result.balances_checked == 1


def test_reconcile_portfolio_snapshots_detects_position_quantity_mismatch() -> None:
    local = _snapshot(position=_position(quantity="10"))
    external = _snapshot(position=_position(quantity="11"))

    result = reconcile_portfolio_snapshots(
        reconciliation_id=RECONCILIATION_ID,
        exchange="kalshi",
        account_id="acct_recon_001",
        local_snapshot=local,
        external_snapshot=external,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )

    assert result.status is ReconciliationStatus.MISMATCH
    assert result.trading_gate_released is False
    assert len(result.mismatches) == 1
    mismatch = result.mismatches[0]
    assert mismatch.category == "position.quantity"
    assert mismatch.local_value == "10"
    assert mismatch.external_value == "11"
    assert mismatch.requires_manual_review is True


def test_reconcile_portfolio_snapshots_detects_balance_available_mismatch() -> None:
    local = _snapshot(balance=_balance(available="100.00", reserved="5.00"))
    external = _snapshot(balance=_balance(available="101.50", reserved="5.00"))

    result = reconcile_portfolio_snapshots(
        reconciliation_id=RECONCILIATION_ID,
        exchange="kalshi",
        account_id="acct_recon_001",
        local_snapshot=local,
        external_snapshot=external,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )

    assert result.status is ReconciliationStatus.MISMATCH
    assert result.trading_gate_released is False
    assert len(result.mismatches) == 2
    assert [mismatch.category for mismatch in result.mismatches] == [
        "balance.available",
        "balance.total",
    ]


def test_reconcile_portfolio_snapshots_detects_missing_external_position() -> None:
    local = _snapshot()
    external = _snapshot(positions=())

    result = reconcile_portfolio_snapshots(
        reconciliation_id=RECONCILIATION_ID,
        exchange="kalshi",
        account_id="acct_recon_001",
        local_snapshot=local,
        external_snapshot=external,
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
    )

    assert result.status is ReconciliationStatus.MISMATCH
    assert result.trading_gate_released is False
    assert result.positions_checked == 1
    assert result.mismatches[0].category == "position.missing_external"
    assert result.mismatches[0].local_value == "present"
    assert result.mismatches[0].external_value is None


def test_reconcile_open_order_ids_returns_healthy_for_matching_sets() -> None:
    record_result = reconcile_open_order_ids(
        reconciliation_id=RECONCILIATION_ID,
        local_order_ids=("order_recon_002", "order_recon_001", "order_recon_001"),
        external_order_ids=("order_recon_001", "order_recon_002"),
    )

    result = build_reconciliation_result(
        reconciliation_id=RECONCILIATION_ID,
        exchange="kalshi",
        account_id="acct_recon_001",
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        mismatches=record_result.mismatches,
        open_orders_checked=record_result.records_checked,
    )

    assert isinstance(record_result, RecordSetReconciliationResult)
    assert record_result.mismatches == ()
    assert record_result.records_checked == 2
    assert result.status is ReconciliationStatus.HEALTHY
    assert result.trading_gate_released is True
    assert result.open_orders_checked == 2


def test_reconcile_fill_ids_detects_missing_records_deterministically() -> None:
    first = reconcile_fill_ids(
        reconciliation_id=RECONCILIATION_ID,
        local_fill_ids=(
            "fill_shared",
            "fill_local_b",
            "fill_local_a",
            "fill_local_a",
        ),
        external_fill_ids=("fill_shared", "fill_external_b", "fill_external_a"),
    )
    second = reconcile_fill_ids(
        reconciliation_id=RECONCILIATION_ID,
        local_fill_ids=(
            "fill_local_a",
            "fill_local_b",
            "fill_shared",
        ),
        external_fill_ids=("fill_external_a", "fill_external_b", "fill_shared"),
    )

    result = build_reconciliation_result(
        reconciliation_id=RECONCILIATION_ID,
        exchange="kalshi",
        account_id="acct_recon_001",
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        mismatches=first.mismatches,
        fills_checked=first.records_checked,
    )

    assert first == second
    assert first.records_checked == 5
    assert [mismatch.category for mismatch in first.mismatches] == [
        "fill.missing_external",
        "fill.missing_external",
        "fill.missing_local",
        "fill.missing_local",
    ]
    assert [mismatch.local_value for mismatch in first.mismatches] == [
        "present",
        "present",
        None,
        None,
    ]
    assert [mismatch.external_value for mismatch in first.mismatches] == [
        None,
        None,
        "present",
        "present",
    ]
    assert result.status is ReconciliationStatus.MISMATCH
    assert result.trading_gate_released is False
    assert result.fills_checked == 5


def test_reconcile_settlement_ids_blocks_gate_for_missing_settlement_record() -> None:
    record_result = reconcile_settlement_ids(
        reconciliation_id=RECONCILIATION_ID,
        local_settlement_ids=(),
        external_settlement_ids=("settlement_recon_external",),
    )

    result = build_reconciliation_result(
        reconciliation_id=RECONCILIATION_ID,
        exchange="kalshi",
        account_id="acct_recon_001",
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        mismatches=record_result.mismatches,
    )

    assert record_result.records_checked == 1
    assert len(record_result.mismatches) == 1
    assert record_result.mismatches[0].category == "settlement.missing_local"
    assert record_result.mismatches[0].local_value is None
    assert record_result.mismatches[0].external_value == "present"
    assert result.status is ReconciliationStatus.MISMATCH
    assert result.trading_gate_released is False


@pytest.mark.parametrize("record_kind", ["", " fill", "fill ", "fill-record"])
def test_reconcile_record_id_sets_rejects_invalid_record_kind(record_kind: str) -> None:
    with pytest.raises(PortfolioProjectionError, match="record_kind"):
        reconcile_record_id_sets(
            reconciliation_id=RECONCILIATION_ID,
            record_kind=record_kind,
            local_ids=("record_001",),
            external_ids=("record_001",),
        )


@pytest.mark.parametrize("record_id", ["", " fill_001", "fill_001 "])
def test_reconcile_record_id_sets_rejects_empty_or_padded_record_ids(
    record_id: str,
) -> None:
    with pytest.raises(PortfolioProjectionError, match="record ID"):
        reconcile_record_id_sets(
            reconciliation_id=RECONCILIATION_ID,
            record_kind="fill",
            local_ids=(record_id,),
            external_ids=("fill_001",),
        )


def test_build_reconciliation_result_blocks_gate_for_unknown_mismatch() -> None:
    mismatch = build_reconciliation_mismatch(
        reconciliation_id=RECONCILIATION_ID,
        category="unknown",
        identity="acct_recon_001",
        local_value="unclassified",
        external_value="unclassified",
        severity=RECONCILIATION_SEVERITY_UNKNOWN,
        explanation="Unclassified portfolio mismatch.",
    )

    result = build_reconciliation_result(
        reconciliation_id=RECONCILIATION_ID,
        exchange="kalshi",
        account_id="acct_recon_001",
        started_at=STARTED_AT,
        completed_at=COMPLETED_AT,
        mismatches=(mismatch,),
    )

    assert result.status is ReconciliationStatus.UNKNOWN
    assert result.trading_gate_released is False
    assert result.mismatches == (mismatch,)


def test_reconcile_portfolio_snapshots_rejects_out_of_scope_position() -> None:
    local = _snapshot(position=_position(exchange="polymarket"))
    external = _snapshot()

    with pytest.raises(PortfolioProjectionError, match="local position exchange"):
        reconcile_portfolio_snapshots(
            reconciliation_id=RECONCILIATION_ID,
            exchange="kalshi",
            account_id="acct_recon_001",
            local_snapshot=local,
            external_snapshot=external,
            started_at=STARTED_AT,
            completed_at=COMPLETED_AT,
        )


def test_derive_reconciliation_mismatch_id_is_stable() -> None:
    first = derive_reconciliation_mismatch_id(
        reconciliation_id=RECONCILIATION_ID,
        category="balance.available",
        identity="cash_recon_001",
        local_value="100.00",
        external_value="101.50",
    )
    second = derive_reconciliation_mismatch_id(
        reconciliation_id=RECONCILIATION_ID,
        category="balance.available",
        identity="cash_recon_001",
        local_value="100.00",
        external_value="101.50",
    )
    different = derive_reconciliation_mismatch_id(
        reconciliation_id=RECONCILIATION_ID,
        category="balance.available",
        identity="cash_recon_001",
        local_value="100.00",
        external_value="102.00",
    )

    assert first == second
    assert first.startswith("recon_mismatch_")
    assert first != different


def _snapshot(
    *,
    position: Position | None = None,
    balance: CashBalance | None = None,
    positions: tuple[Position, ...] | None = None,
) -> PortfolioSnapshot:
    resolved_positions = positions if positions is not None else (position or _position(),)
    return PortfolioSnapshot(
        portfolio_id="portfolio_recon_001",
        captured_at=CAPTURED_AT,
        positions=resolved_positions,
        balances=(balance or _balance(),),
        realized_pnl=(_money("0"),),
        unrealized_pnl=(_money("0"),),
        gross_exposure=(_money("4.00"),),
        net_exposure=(_money("4.00"),),
        reconciliation_status="healthy",
    )


def _position(
    *,
    quantity: str = "10",
    average_entry_price: str = "0.40",
    exchange: str = "kalshi",
) -> Position:
    return Position(
        position_id="pos_recon_001",
        exchange=exchange,
        account_id="acct_recon_001",
        market_id="mkt_recon_001",
        contract_id="ctr_recon_001",
        outcome_id="out_yes",
        quantity=Decimal(quantity),
        average_entry_price=Decimal(average_entry_price),
        realized_pnl=_money("0"),
        unrealized_pnl=_money("0"),
        fees_paid=_money("0"),
        rebates_received=_money("0"),
        opened_at=CAPTURED_AT,
        last_updated_at=CAPTURED_AT,
        aggregate_version=1,
    )


def _balance(*, available: str = "100.00", reserved: str = "5.00") -> CashBalance:
    available_decimal = Decimal(available)
    reserved_decimal = Decimal(reserved)
    return CashBalance(
        balance_id="cash_recon_001",
        exchange="kalshi",
        account_id="acct_recon_001",
        currency="USD",
        available=available_decimal,
        reserved=reserved_decimal,
        total=available_decimal + reserved_decimal,
        captured_at=CAPTURED_AT,
    )


def _money(amount: str) -> Money:
    return Money(amount=Decimal(amount), currency="USD")
