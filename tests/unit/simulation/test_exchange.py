"""Simulated exchange admission tests."""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

import pmrp.simulation.exchange as exchange_module
from pmrp.schemas.enums import MarketStatus, OrderType, Side, TimeInForce
from pmrp.schemas.orders import OrderIntent
from pmrp.simulation import (
    SIMULATED_EXCHANGE_ADMISSION_MODEL_NAME,
    BoundedRejectionModel,
    DeterministicSimulatedExchange,
    FixedLatencyModel,
    RejectionReason,
    SimulatedExchange,
    SimulatedExchangeOrderAdmission,
    SimulationConfigurationError,
    SimulationInputError,
    SimulationSourceType,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def test_deterministic_simulated_exchange_accepts_and_schedules_activation() -> None:
    exchange = DeterministicSimulatedExchange(
        rejection_model=BoundedRejectionModel(),
        latency_model=FixedLatencyModel.from_milliseconds(125),
    )

    admission = exchange.admit_order(
        intent=_intent(),
        market_status=MarketStatus.OPEN,
        submitted_at=NOW,
        required_balance=Decimal("4.30"),
        available_balance=Decimal("10.00"),
    )

    assert isinstance(exchange, SimulatedExchange)
    assert admission.accepted
    assert not admission.rejected
    assert admission.rejection_decision.reason_code is RejectionReason.ACCEPTED
    assert admission.accepted_at == NOW
    assert admission.activates_at == NOW + timedelta(milliseconds=125)
    assert admission.required_balance == Decimal("4.30")
    assert admission.available_balance == Decimal("10.00")
    assert admission.source_type is SimulationSourceType.SIMULATED_OUTPUT
    assert admission.canonical_payload()["admission_model"] == (
        SIMULATED_EXCHANGE_ADMISSION_MODEL_NAME
    )
    assert admission.admission_hash == admission.admission_hash


def test_deterministic_simulated_exchange_rejects_without_activation() -> None:
    exchange = DeterministicSimulatedExchange(
        rejection_model=BoundedRejectionModel(),
        latency_model=FixedLatencyModel.from_milliseconds(125),
    )

    closed_market = exchange.admit_order(
        intent=_intent(),
        market_status=MarketStatus.CLOSED,
        submitted_at=NOW,
    )
    insufficient_balance = exchange.admit_order(
        intent=_intent(),
        market_status=MarketStatus.OPEN,
        submitted_at=NOW,
        required_balance=Decimal("4.30"),
        available_balance=Decimal("4.29"),
    )

    assert closed_market.rejected
    assert closed_market.rejection_decision.reason_code is RejectionReason.MARKET_CLOSED
    assert closed_market.accepted_at is None
    assert closed_market.activates_at is None
    assert insufficient_balance.rejected
    assert insufficient_balance.rejection_decision.reason_code is (
        RejectionReason.INSUFFICIENT_BALANCE
    )


def test_simulated_exchange_admission_constructor_enforces_invariants() -> None:
    accepted_decision = BoundedRejectionModel().evaluate(
        market_status=MarketStatus.OPEN,
        price=Decimal("0.43"),
        quantity=Decimal("10"),
    )
    rejected_decision = BoundedRejectionModel().evaluate(
        market_status=MarketStatus.CLOSED,
        price=Decimal("0.43"),
        quantity=Decimal("10"),
    )

    with pytest.raises(SimulationConfigurationError) as missing_activation_error:
        SimulatedExchangeOrderAdmission(
            intent=_intent(),
            market_status=MarketStatus.OPEN,
            rejection_decision=accepted_decision,
            submitted_at=NOW,
            accepted_at=NOW,
            activates_at=None,
        )

    assert missing_activation_error.value.reason_code == "simulation_exchange_activation_missing"

    with pytest.raises(SimulationConfigurationError) as rejected_activation_error:
        SimulatedExchangeOrderAdmission(
            intent=_intent(),
            market_status=MarketStatus.CLOSED,
            rejection_decision=rejected_decision,
            submitted_at=NOW,
            accepted_at=NOW,
            activates_at=NOW,
        )

    assert rejected_activation_error.value.reason_code == (
        "simulation_exchange_rejected_activation_invalid"
    )

    with pytest.raises(SimulationConfigurationError) as activation_order_error:
        SimulatedExchangeOrderAdmission(
            intent=_intent(),
            market_status=MarketStatus.OPEN,
            rejection_decision=accepted_decision,
            submitted_at=NOW,
            accepted_at=NOW,
            activates_at=NOW - timedelta(milliseconds=1),
        )

    assert activation_order_error.value.reason_code == (
        "simulation_exchange_activation_order_invalid"
    )

    with pytest.raises(SimulationConfigurationError) as source_error:
        SimulatedExchangeOrderAdmission(
            intent=_intent(),
            market_status=MarketStatus.OPEN,
            rejection_decision=accepted_decision,
            submitted_at=NOW,
            accepted_at=NOW,
            activates_at=NOW,
            source_type=SimulationSourceType.OBSERVED_FACT,
        )

    assert source_error.value.reason_code == "simulation_exchange_source_type_invalid"


def test_deterministic_simulated_exchange_rejects_invalid_inputs() -> None:
    with pytest.raises(TypeError, match="rejection_model"):
        DeterministicSimulatedExchange(
            rejection_model=object(),  # type: ignore[arg-type]
            latency_model=FixedLatencyModel.from_milliseconds(0),
        )

    exchange = DeterministicSimulatedExchange(
        rejection_model=BoundedRejectionModel(),
        latency_model=FixedLatencyModel.from_milliseconds(0),
    )

    with pytest.raises(SimulationInputError) as intent_error:
        exchange.admit_order(
            intent="intent",  # type: ignore[arg-type]
            market_status=MarketStatus.OPEN,
            submitted_at=NOW,
        )

    assert intent_error.value.reason_code == "simulation_exchange_intent_invalid"

    with pytest.raises(SimulationInputError) as status_error:
        exchange.admit_order(
            intent=_intent(),
            market_status="open",  # type: ignore[arg-type]
            submitted_at=NOW,
        )

    assert status_error.value.reason_code == "simulation_exchange_market_status_invalid"

    with pytest.raises(ValueError, match="timezone-aware"):
        exchange.admit_order(
            intent=_intent(),
            market_status=MarketStatus.OPEN,
            submitted_at=datetime.fromisoformat("2026-08-01T15:00:00"),
        )

    with pytest.raises(TypeError, match="float input"):
        exchange.admit_order(
            intent=_intent(),
            market_status=MarketStatus.OPEN,
            submitted_at=NOW,
            required_balance=1.0,  # type: ignore[arg-type]
        )


def test_simulated_exchange_module_has_no_live_dependencies() -> None:
    source = inspect.getsource(exchange_module)

    assert "pmrp.adapters" not in source
    assert "requests" not in source
    assert "httpx" not in source
    assert "asyncpg" not in source
    assert "sqlalchemy" not in source


def _intent(
    *,
    intent_id: str = "intent_exchange_admission_001",
    quantity: Decimal | str = "10",
    limit_price: Decimal | str = "0.43",
) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": intent_id,
            "strategy_id": "strat_exchange_admission",
            "market_id": "mkt_exchange_admission",
            "contract_id": "ctr_exchange_admission",
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": quantity,
            "limit_price": limit_price,
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_exchange_admission",
            "idempotency_key": f"idem-{intent_id}",
        }
    )
