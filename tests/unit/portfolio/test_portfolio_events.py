"""Unit tests for canonical portfolio event builders."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.clock import FrozenClock
from pmrp.events import (
    DeterministicEventIdentifierGenerator,
    EventFactory,
    default_event_type_registry,
)
from pmrp.portfolio import PortfolioEventFactory
from pmrp.schemas.events import (
    PORTFOLIO_CASH_BALANCE_CHANGED_EVENT_TYPE,
    PORTFOLIO_MISMATCH_DETECTED_EVENT_TYPE,
    PORTFOLIO_PNL_UPDATED_EVENT_TYPE,
    PORTFOLIO_POSITION_CHANGED_EVENT_TYPE,
    PORTFOLIO_RECONCILED_EVENT_TYPE,
    CashBalanceChangedEvent,
    PnlUpdatedEvent,
    PortfolioMismatchDetectedEvent,
    PortfolioReconciledEvent,
    PositionChangedEvent,
)
from pmrp.schemas.identifiers import AccountId, ContractId, MarketId, OutcomeId, StrategyId
from pmrp.schemas.numeric import Money
from pmrp.schemas.portfolio import (
    CashBalance,
    PnlAttribution,
    Position,
    ReconciliationMismatch,
    ReconciliationResult,
    ReconciliationStatus,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
ACCOUNT_ID = AccountId("acct_portfolio_event")
MARKET_ID = MarketId("mkt_portfolio_event")
CONTRACT_ID = ContractId("ctr_portfolio_event")
OUTCOME_ID = OutcomeId("out_yes")
STRATEGY_ID = StrategyId("strat_portfolio_event")


def test_portfolio_event_factory_builds_position_changed_event_with_lineage() -> None:
    previous_position = _position(quantity=Decimal("4"), aggregate_version=1)
    current_position = _position(quantity=Decimal("5"), aggregate_version=2)

    event = _portfolio_event_factory().build_position_changed_event(
        previous_position=previous_position,
        current_position=current_position,
        source_fill_id="fill_portfolio_event",
        correlation_id="corr_portfolio_event",
        causation_id="evt_portfolio_event_source",
    )

    assert isinstance(event, PositionChangedEvent)
    assert event.envelope.event_id == "evt_test_000000000000000000000001"
    assert event.envelope.event_type == PORTFOLIO_POSITION_CHANGED_EVENT_TYPE
    assert event.envelope.schema_version == 1
    assert event.envelope.producer == "portfolio"
    assert event.envelope.occurred_at == current_position.last_updated_at
    assert event.envelope.published_at == NOW
    assert event.envelope.exchange == current_position.exchange
    assert event.envelope.market_id == current_position.market_id
    assert event.envelope.account_id == current_position.account_id
    assert event.envelope.correlation_id == "corr_portfolio_event"
    assert event.envelope.causation_id == "evt_portfolio_event_source"
    assert event.previous_position == previous_position
    assert event.current_position == current_position
    assert event.source_fill_id == "fill_portfolio_event"


def test_portfolio_event_factory_builds_cash_balance_changed_event_with_lineage() -> None:
    previous_balance = _cash_balance(available=Decimal("90.00"), total=Decimal("100.00"))
    current_balance = _cash_balance(available=Decimal("95.00"), total=Decimal("105.00"))

    event = _portfolio_event_factory().build_cash_balance_changed_event(
        previous_balance=previous_balance,
        current_balance=current_balance,
        reason="balance_correction",
    )

    assert isinstance(event, CashBalanceChangedEvent)
    assert event.envelope.event_type == PORTFOLIO_CASH_BALANCE_CHANGED_EVENT_TYPE
    assert event.envelope.occurred_at == current_balance.captured_at
    assert event.envelope.exchange == current_balance.exchange
    assert event.envelope.account_id == current_balance.account_id
    assert event.previous_balance == previous_balance
    assert event.current_balance == current_balance
    assert event.reason == "balance_correction"


def test_portfolio_event_factory_builds_pnl_updated_event_with_lineage() -> None:
    attribution = _pnl_attribution()

    event = _portfolio_event_factory().build_pnl_updated_event(
        attribution,
        correlation_id="corr_portfolio_pnl_event",
    )

    assert isinstance(event, PnlUpdatedEvent)
    assert event.envelope.event_type == PORTFOLIO_PNL_UPDATED_EVENT_TYPE
    assert event.envelope.occurred_at == attribution.ends_at
    assert event.envelope.exchange == attribution.exchange
    assert event.envelope.market_id == attribution.market_id
    assert event.envelope.strategy_id == attribution.strategy_id
    assert event.envelope.correlation_id == "corr_portfolio_pnl_event"
    assert event.attribution == attribution


def test_portfolio_event_factory_builds_reconciled_event_for_healthy_result() -> None:
    result = _reconciliation_result()

    event = _portfolio_event_factory().build_reconciliation_event(result)

    assert isinstance(event, PortfolioReconciledEvent)
    assert event.envelope.event_type == PORTFOLIO_RECONCILED_EVENT_TYPE
    assert event.envelope.occurred_at == result.completed_at
    assert event.envelope.exchange == result.exchange
    assert event.envelope.account_id == result.account_id
    assert event.result == result


def test_portfolio_event_factory_builds_mismatch_event_for_mismatch_result() -> None:
    result = _reconciliation_result(
        status=ReconciliationStatus.MISMATCH,
        mismatches=(_reconciliation_mismatch(),),
        trading_gate_released=False,
    )

    event = _portfolio_event_factory().build_reconciliation_event(result)

    assert isinstance(event, PortfolioMismatchDetectedEvent)
    assert event.envelope.event_type == PORTFOLIO_MISMATCH_DETECTED_EVENT_TYPE
    assert event.envelope.occurred_at == result.completed_at
    assert event.envelope.exchange == result.exchange
    assert event.envelope.account_id == result.account_id
    assert event.result == result


def test_portfolio_event_factory_rejects_nonhealthy_result_without_mismatches() -> None:
    result = _reconciliation_result(
        status=ReconciliationStatus.UNKNOWN,
        mismatches=(),
        trading_gate_released=False,
    )

    with pytest.raises(ValueError, match="at least one reconciliation mismatch"):
        _portfolio_event_factory().build_reconciliation_event(result)


def _portfolio_event_factory() -> PortfolioEventFactory:
    return PortfolioEventFactory(
        event_factory=EventFactory(
            clock=FrozenClock(NOW),
            registry=default_event_type_registry(),
            identifier_generator=DeterministicEventIdentifierGenerator(),
        )
    )


def _position(**overrides: object) -> Position:
    payload: dict[str, object] = {
        "position_id": "pos_portfolio_event",
        "exchange": "kalshi",
        "account_id": ACCOUNT_ID,
        "market_id": MARKET_ID,
        "contract_id": CONTRACT_ID,
        "outcome_id": OUTCOME_ID,
        "quantity": Decimal("5"),
        "average_entry_price": Decimal("0.42"),
        "realized_pnl": Money(amount=Decimal("1.00"), currency="USD"),
        "unrealized_pnl": Money(amount=Decimal("0.50"), currency="USD"),
        "fees_paid": Money(amount=Decimal("0.10"), currency="USD"),
        "rebates_received": Money(amount=Decimal("0.05"), currency="USD"),
        "opened_at": NOW - timedelta(minutes=5),
        "last_updated_at": NOW - timedelta(seconds=1),
        "aggregate_version": 2,
    }
    payload.update(overrides)
    return Position.model_validate(payload)


def _cash_balance(**overrides: object) -> CashBalance:
    payload: dict[str, object] = {
        "balance_id": "cash_portfolio_event",
        "exchange": "kalshi",
        "account_id": ACCOUNT_ID,
        "currency": "USD",
        "available": Decimal("95.00"),
        "reserved": Decimal("10.00"),
        "total": Decimal("105.00"),
        "captured_at": NOW - timedelta(seconds=1),
    }
    payload.update(overrides)
    return CashBalance.model_validate(payload)


def _pnl_attribution(**overrides: object) -> PnlAttribution:
    payload: dict[str, object] = {
        "attribution_id": "pnl_portfolio_event",
        "strategy_id": STRATEGY_ID,
        "market_id": MARKET_ID,
        "exchange": "kalshi",
        "starts_at": NOW - timedelta(hours=1),
        "ends_at": NOW,
        "realized_trading_pnl": Money(amount=Decimal("3.00"), currency="USD"),
        "unrealized_pnl_change": Money(amount=Decimal("1.00"), currency="USD"),
        "fees": Money(amount=Decimal("0.25"), currency="USD"),
        "rebates": Money(amount=Decimal("0.10"), currency="USD"),
        "slippage": Money(amount=Decimal("-0.50"), currency="USD"),
        "settlement_pnl": Money(amount=Decimal("2.00"), currency="USD"),
        "total_pnl": Money(amount=Decimal("5.35"), currency="USD"),
        "calculation_version": "journal_pnl_attribution_v1",
    }
    payload.update(overrides)
    return PnlAttribution.model_validate(payload)


def _reconciliation_result(**overrides: object) -> ReconciliationResult:
    payload: dict[str, object] = {
        "reconciliation_id": "recon_portfolio_event",
        "exchange": "kalshi",
        "account_id": ACCOUNT_ID,
        "started_at": NOW - timedelta(seconds=3),
        "completed_at": NOW - timedelta(seconds=1),
        "status": ReconciliationStatus.HEALTHY,
        "mismatches": (),
        "open_orders_checked": 1,
        "positions_checked": 2,
        "balances_checked": 1,
        "fills_checked": 3,
        "trading_gate_released": True,
    }
    payload.update(overrides)
    return ReconciliationResult.model_validate(payload)


def _reconciliation_mismatch(**overrides: object) -> ReconciliationMismatch:
    payload: dict[str, object] = {
        "mismatch_id": "mismatch_portfolio_event",
        "category": "position.quantity",
        "local_value": "5",
        "external_value": "4",
        "severity": "mismatch",
        "explanation": "Position quantity differs.",
        "requires_manual_review": True,
    }
    payload.update(overrides)
    return ReconciliationMismatch.model_validate(payload)
