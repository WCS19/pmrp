import json
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pmrp.schemas.portfolio import (
    AccountingJournalEntry,
    CashBalance,
    JournalLine,
    PnlAttribution,
    PortfolioSnapshot,
    Position,
    PositionLot,
    ReconciliationMismatch,
    ReconciliationResult,
    ReconciliationStatus,
    Settlement,
    SettlementStatus,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _money(amount: str, currency: str = "USD") -> dict[str, str]:
    return {"amount": amount, "currency": currency}


def _position_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "position_id": "pos_01j00000000000000000000000",
        "exchange": "kalshi",
        "account_id": "acct_paper_001",
        "market_id": "mkt_01j00000000000000000000000",
        "contract_id": "ctr_01j00000000000000000000000",
        "outcome_id": "out_yes",
        "quantity": "12",
        "average_entry_price": "0.42",
        "realized_pnl": _money("3.25"),
        "unrealized_pnl": _money("1.10"),
        "fees_paid": _money("0.12"),
        "rebates_received": _money("0.03"),
        "opened_at": "2026-07-28T15:00:00Z",
        "last_updated_at": "2026-07-28T15:30:00Z",
        "aggregate_version": 4,
    }
    payload.update(overrides)
    return payload


def _position_lot_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "lot_id": "lot_001",
        "position_id": "pos_01j00000000000000000000000",
        "source_fill_id": "fill_01j00000000000000000000000",
        "quantity": "10",
        "remaining_quantity": "6",
        "entry_price": "0.42",
        "opened_at": "2026-07-28T15:00:02Z",
        "strategy_id": "strat_threshold_v1",
    }
    payload.update(overrides)
    return payload


def _cash_balance_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "balance_id": "balance_usd_001",
        "exchange": "kalshi",
        "account_id": "acct_paper_001",
        "currency": "USD",
        "available": "800.25",
        "reserved": "199.75",
        "total": "1000.00",
        "captured_at": "2026-07-28T15:30:00Z",
    }
    payload.update(overrides)
    return payload


def _portfolio_snapshot_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "portfolio_id": "portfolio_main",
        "captured_at": "2026-07-28T15:30:00Z",
        "positions": (_position_payload(),),
        "balances": (_cash_balance_payload(),),
        "realized_pnl": (_money("3.25"),),
        "unrealized_pnl": (_money("1.10"),),
        "gross_exposure": (_money("12.00"),),
        "net_exposure": (_money("12.00"),),
        "reconciliation_status": "healthy",
    }
    payload.update(overrides)
    return payload


def _journal_line_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "account_code": "cash",
        "amount": "-4.20",
        "currency": "USD",
        "description": "Cash paid for fill.",
    }
    payload.update(overrides)
    return payload


def _journal_entry_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "journal_entry_id": "journal_001",
        "occurred_at": "2026-07-28T15:00:02Z",
        "source_event_id": "evt_01j00000000000000000000000",
        "reference_type": "fill",
        "reference_id": "fill_01j00000000000000000000000",
        "lines": (
            _journal_line_payload(account_code="cash", amount="-4.20"),
            _journal_line_payload(account_code="contracts", amount="4.20"),
        ),
        "description": "Buy fill accounting entry.",
        "created_at": "2026-07-28T15:00:03Z",
    }
    payload.update(overrides)
    return payload


def _pnl_attribution_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "attribution_id": "pnl_001",
        "strategy_id": "strat_threshold_v1",
        "market_id": "mkt_01j00000000000000000000000",
        "exchange": "kalshi",
        "starts_at": "2026-07-28T15:00:00Z",
        "ends_at": "2026-07-28T16:00:00Z",
        "realized_trading_pnl": _money("2.00"),
        "unrealized_pnl_change": _money("1.00"),
        "fees": _money("0.10"),
        "rebates": _money("0.02"),
        "slippage": _money("-0.03"),
        "settlement_pnl": None,
        "total_pnl": _money("2.89"),
        "calculation_version": "avg-cost-v1",
    }
    payload.update(overrides)
    return payload


def _settlement_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "settlement_id": "set_01j00000000000000000000000",
        "market_id": "mkt_01j00000000000000000000000",
        "exchange": "kalshi",
        "status": SettlementStatus.SETTLED,
        "winning_outcome_ids": ("out_yes",),
        "resolved_at": "2026-07-28T18:00:00Z",
        "finalized_at": "2026-07-28T18:10:00Z",
        "settled_at": "2026-07-28T18:15:00Z",
        "payout_per_unit": "1.00",
        "source": "exchange_settlement",
        "source_reference": "settlement-feed-001",
        "correction_of_settlement_id": None,
    }
    payload.update(overrides)
    return payload


def _reconciliation_mismatch_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "mismatch_id": "mismatch_001",
        "category": "balance_mismatch",
        "local_value": "1000.00",
        "external_value": "999.99",
        "severity": "critical",
        "explanation": "Exchange balance differs from local projection.",
        "requires_manual_review": True,
    }
    payload.update(overrides)
    return payload


def _reconciliation_result_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "reconciliation_id": "recon_001",
        "exchange": "kalshi",
        "account_id": "acct_paper_001",
        "started_at": "2026-07-28T15:30:00Z",
        "completed_at": "2026-07-28T15:31:00Z",
        "status": ReconciliationStatus.HEALTHY,
        "mismatches": (),
        "open_orders_checked": 3,
        "positions_checked": 1,
        "balances_checked": 1,
        "fills_checked": 4,
        "trading_gate_released": True,
    }
    payload.update(overrides)
    return payload


def test_position_accepts_valid_payload_and_exact_decimal() -> None:
    position = Position.model_validate(_position_payload())

    assert position.position_id == "pos_01j00000000000000000000000"
    assert position.quantity == Decimal("12")
    assert position.fees_paid.amount == Decimal("0.12")


def test_position_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        Position.model_validate(_position_payload(unexpected=True))


def test_position_rejects_float_quantity() -> None:
    with pytest.raises(TypeError, match="float input"):
        Position.model_validate(_position_payload(quantity=12.0))


def test_position_accepts_short_quantity_sign() -> None:
    position = Position.model_validate(_position_payload(quantity="-3", average_entry_price="0.41"))

    assert position.quantity == Decimal("-3")


def test_position_rejects_negative_fees() -> None:
    with pytest.raises(ValidationError, match="fees_paid amount must be nonnegative"):
        Position.model_validate(_position_payload(fees_paid=_money("-0.01")))


def test_position_rejects_last_updated_before_opened() -> None:
    with pytest.raises(ValidationError, match="last_updated_at must not be before opened_at"):
        Position.model_validate(_position_payload(last_updated_at="2026-07-28T14:59:59Z"))


def test_position_rejects_naive_last_updated_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        Position.model_validate(
            _position_payload(last_updated_at=datetime.fromisoformat("2026-07-28T15:30:00"))
        )


def test_position_lot_accepts_valid_short_lot() -> None:
    lot = PositionLot.model_validate(_position_lot_payload(quantity="-10", remaining_quantity="-4"))

    assert lot.remaining_quantity == Decimal("-4")


def test_position_lot_rejects_zero_quantity() -> None:
    with pytest.raises(ValidationError, match="quantity must be nonzero"):
        PositionLot.model_validate(_position_lot_payload(quantity="0"))


def test_position_lot_rejects_remaining_quantity_larger_than_original() -> None:
    with pytest.raises(ValidationError, match="magnitude must not exceed"):
        PositionLot.model_validate(_position_lot_payload(remaining_quantity="11"))


def test_position_lot_rejects_remaining_quantity_sign_mismatch() -> None:
    with pytest.raises(ValidationError, match="sign must match"):
        PositionLot.model_validate(_position_lot_payload(quantity="-10", remaining_quantity="4"))


def test_cash_balance_accepts_valid_payload() -> None:
    balance = CashBalance.model_validate(_cash_balance_payload())

    assert balance.available + balance.reserved == balance.total
    assert balance.currency == "USD"


def test_cash_balance_rejects_float_reserved() -> None:
    with pytest.raises(TypeError, match="float input"):
        CashBalance.model_validate(_cash_balance_payload(reserved=199.75))


def test_cash_balance_rejects_invalid_currency() -> None:
    with pytest.raises(ValidationError, match="currency must be"):
        CashBalance.model_validate(_cash_balance_payload(currency="usd"))


def test_cash_balance_rejects_identity_mismatch() -> None:
    with pytest.raises(ValidationError, match="available plus reserved"):
        CashBalance.model_validate(_cash_balance_payload(total="999.99"))


def test_cash_balance_rejects_negative_reserved_amount() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        CashBalance.model_validate(_cash_balance_payload(available="1001.00", reserved="-1.00"))


def test_portfolio_snapshot_accepts_valid_payload() -> None:
    snapshot = PortfolioSnapshot.model_validate(_portfolio_snapshot_payload())

    assert snapshot.positions[0].position_id == "pos_01j00000000000000000000000"
    assert snapshot.balances[0].balance_id == "balance_usd_001"


def test_portfolio_snapshot_rejects_duplicate_position_ids() -> None:
    with pytest.raises(ValidationError, match="positions must not contain duplicate"):
        PortfolioSnapshot.model_validate(
            _portfolio_snapshot_payload(positions=(_position_payload(), _position_payload()))
        )


def test_portfolio_snapshot_rejects_duplicate_balance_ids() -> None:
    with pytest.raises(ValidationError, match="balances must not contain duplicate"):
        PortfolioSnapshot.model_validate(
            _portfolio_snapshot_payload(balances=(_cash_balance_payload(), _cash_balance_payload()))
        )


def test_journal_line_rejects_float_amount() -> None:
    with pytest.raises(TypeError, match="float input"):
        JournalLine.model_validate(_journal_line_payload(amount=1.0))


def test_accounting_journal_entry_accepts_balanced_payload() -> None:
    journal = AccountingJournalEntry.model_validate(_journal_entry_payload())

    assert sum(line.amount for line in journal.lines) == Decimal("0")


def test_accounting_journal_entry_rejects_empty_lines() -> None:
    with pytest.raises(ValidationError, match="requires at least one line"):
        AccountingJournalEntry.model_validate(_journal_entry_payload(lines=()))


def test_accounting_journal_entry_rejects_unbalanced_currency() -> None:
    with pytest.raises(ValidationError, match="balance to zero by currency"):
        AccountingJournalEntry.model_validate(
            _journal_entry_payload(
                lines=(
                    _journal_line_payload(account_code="cash", amount="-4.20"),
                    _journal_line_payload(account_code="contracts", amount="4.19"),
                )
            )
        )


def test_accounting_journal_entry_rejects_created_before_occurred() -> None:
    with pytest.raises(ValidationError, match="created_at must not be before occurred_at"):
        AccountingJournalEntry.model_validate(
            _journal_entry_payload(created_at="2026-07-28T15:00:01Z")
        )


def test_pnl_attribution_accepts_valid_payload() -> None:
    attribution = PnlAttribution.model_validate(_pnl_attribution_payload())

    assert attribution.total_pnl.amount == Decimal("2.89")


def test_pnl_attribution_rejects_invalid_window() -> None:
    with pytest.raises(ValidationError, match="ends_at must be after"):
        PnlAttribution.model_validate(_pnl_attribution_payload(ends_at="2026-07-28T15:00:00Z"))


def test_pnl_attribution_rejects_mixed_currencies() -> None:
    with pytest.raises(ValidationError, match="must use one currency"):
        PnlAttribution.model_validate(
            _pnl_attribution_payload(total_pnl=_money("2.89", currency="EUR"))
        )


def test_pnl_attribution_rejects_negative_fees() -> None:
    with pytest.raises(ValidationError, match="fees amount must be nonnegative"):
        PnlAttribution.model_validate(_pnl_attribution_payload(fees=_money("-0.10")))


def test_pnl_attribution_rejects_total_mismatch() -> None:
    with pytest.raises(ValidationError, match="total_pnl must equal"):
        PnlAttribution.model_validate(_pnl_attribution_payload(total_pnl=_money("999.99")))


def test_settlement_accepts_valid_payload() -> None:
    settlement = Settlement.model_validate(_settlement_payload())

    assert settlement.status is SettlementStatus.SETTLED
    assert settlement.payout_per_unit == Decimal("1.00")


def test_settlement_accepts_unresolved_payload_without_resolution_fields() -> None:
    settlement = Settlement.model_validate(
        _settlement_payload(
            status=SettlementStatus.UNRESOLVED,
            winning_outcome_ids=(),
            resolved_at=None,
            finalized_at=None,
            settled_at=None,
            payout_per_unit=None,
            source_reference=None,
        )
    )

    assert settlement.status is SettlementStatus.UNRESOLVED
    assert settlement.winning_outcome_ids == ()


def test_settlement_accepts_corrected_payload_with_reference() -> None:
    settlement = Settlement.model_validate(
        _settlement_payload(
            status=SettlementStatus.CORRECTED,
            correction_of_settlement_id="set_01j11111111111111111111111",
        )
    )

    assert settlement.correction_of_settlement_id == "set_01j11111111111111111111111"


def test_settlement_rejects_float_payout() -> None:
    with pytest.raises(TypeError, match="float input"):
        Settlement.model_validate(_settlement_payload(payout_per_unit=1.0))


def test_settlement_rejects_unresolved_with_resolution_fields() -> None:
    with pytest.raises(ValidationError, match="cannot contain resolution fields"):
        Settlement.model_validate(_settlement_payload(status=SettlementStatus.UNRESOLVED))


def test_settlement_rejects_settled_without_winning_outcomes() -> None:
    with pytest.raises(ValidationError, match="require winning outcomes"):
        Settlement.model_validate(_settlement_payload(winning_outcome_ids=()))


def test_settlement_rejects_settled_without_payout() -> None:
    with pytest.raises(ValidationError, match="require payout_per_unit"):
        Settlement.model_validate(_settlement_payload(payout_per_unit=None))


def test_settlement_rejects_resolved_with_finalization_fields() -> None:
    with pytest.raises(ValidationError, match="cannot contain finalization fields"):
        Settlement.model_validate(_settlement_payload(status=SettlementStatus.RESOLVED))


def test_settlement_rejects_finalized_without_resolution() -> None:
    with pytest.raises(ValidationError, match="require resolved_at"):
        Settlement.model_validate(_settlement_payload(resolved_at=None))


def test_settlement_rejects_settled_without_finalization() -> None:
    with pytest.raises(ValidationError, match="requires finalized_at"):
        Settlement.model_validate(_settlement_payload(finalized_at=None))


def test_settlement_rejects_correction_without_reference() -> None:
    with pytest.raises(ValidationError, match="corrected settlement requires"):
        Settlement.model_validate(
            _settlement_payload(status=SettlementStatus.CORRECTED, correction_of_settlement_id=None)
        )


def test_reconciliation_mismatch_accepts_valid_payload() -> None:
    mismatch = ReconciliationMismatch.model_validate(_reconciliation_mismatch_payload())

    assert mismatch.requires_manual_review is True


def test_reconciliation_result_accepts_healthy_payload() -> None:
    result = ReconciliationResult.model_validate(_reconciliation_result_payload())

    assert result.status is ReconciliationStatus.HEALTHY
    assert result.trading_gate_released is True


def test_reconciliation_result_accepts_mismatch_payload() -> None:
    result = ReconciliationResult.model_validate(
        _reconciliation_result_payload(
            status=ReconciliationStatus.MISMATCH,
            mismatches=(_reconciliation_mismatch_payload(),),
            trading_gate_released=False,
        )
    )

    assert result.mismatches[0].category == "balance_mismatch"


def test_reconciliation_result_rejects_healthy_with_mismatches() -> None:
    with pytest.raises(ValidationError, match="healthy reconciliation cannot contain"):
        ReconciliationResult.model_validate(
            _reconciliation_result_payload(mismatches=(_reconciliation_mismatch_payload(),))
        )


def test_reconciliation_result_rejects_mismatch_without_mismatches() -> None:
    with pytest.raises(ValidationError, match="requires at least one mismatch"):
        ReconciliationResult.model_validate(
            _reconciliation_result_payload(
                status=ReconciliationStatus.MISMATCH,
                trading_gate_released=False,
            )
        )


def test_reconciliation_result_rejects_non_healthy_gate_release() -> None:
    with pytest.raises(ValidationError, match="cannot release the trading gate"):
        ReconciliationResult.model_validate(
            _reconciliation_result_payload(
                status=ReconciliationStatus.FAILED,
                trading_gate_released=True,
            )
        )


def test_reconciliation_result_rejects_invalid_time_window() -> None:
    with pytest.raises(ValidationError, match="completed_at must be after"):
        ReconciliationResult.model_validate(
            _reconciliation_result_payload(completed_at="2026-07-28T15:30:00Z")
        )


def test_portfolio_json_round_trip_and_stable_hash() -> None:
    snapshot = PortfolioSnapshot.model_validate_json(
        json.dumps(
            {
                **_portfolio_snapshot_payload(),
                "positions": [_position_payload()],
                "balances": [_cash_balance_payload()],
                "realized_pnl": [_money("3.25")],
                "unrealized_pnl": [_money("1.10")],
                "gross_exposure": [_money("12.00")],
                "net_exposure": [_money("12.00")],
            }
        )
    )
    canonical = canonical_json(snapshot)

    assert PortfolioSnapshot.model_validate_json(canonical) == snapshot
    assert canonical_sha256(snapshot) == canonical_sha256(
        PortfolioSnapshot.model_validate_json(canonical)
    )


def test_portfolio_json_schema_generation() -> None:
    json_schema = PortfolioSnapshot.model_json_schema()

    assert json_schema["title"] == "PortfolioSnapshot"
    assert "positions" in json_schema["properties"]


def test_portfolio_schema_registry_entries_exist() -> None:
    assert get_schema_model("position", 1) is Position
    assert get_schema_model("cash_balance", 1) is CashBalance
    assert get_schema_model("portfolio_snapshot", 1) is PortfolioSnapshot
    assert get_schema_model("accounting_journal_entry", 1) is AccountingJournalEntry
    assert get_schema_model("settlement", 1) is Settlement
    assert get_schema_model("reconciliation_result", 1) is ReconciliationResult
    registration = get_schema_registration("portfolio_snapshot", 1)

    assert registration.model_path == "pmrp.schemas.portfolio.PortfolioSnapshot"
