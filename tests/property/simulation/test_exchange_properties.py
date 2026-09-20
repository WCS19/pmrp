"""Property tests for simulated exchange admission."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.enums import MarketStatus, OrderType, Side, TimeInForce
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.serialization import to_canonical_data
from pmrp.simulation import (
    BoundedRejectionModel,
    DeterministicSimulatedExchange,
    FixedLatencyModel,
    RejectionReason,
)

pytestmark = pytest.mark.property

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)

_LATENCY_MS = st.integers(min_value=0, max_value=60_000)
_PRICE = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("0.9999"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)
_QUANTITY = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("10000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


@given(latency_ms=_LATENCY_MS, price=_PRICE, quantity=_QUANTITY)
def test_simulated_exchange_admission_is_deterministic(
    latency_ms: int,
    price: Decimal,
    quantity: Decimal,
) -> None:
    exchange = DeterministicSimulatedExchange(
        rejection_model=BoundedRejectionModel(),
        latency_model=FixedLatencyModel.from_milliseconds(latency_ms),
    )
    intent = _intent(price=price, quantity=quantity)
    required_balance = price * quantity

    first = exchange.admit_order(
        intent=intent,
        market_status=MarketStatus.OPEN,
        submitted_at=NOW,
        required_balance=required_balance,
        available_balance=required_balance,
    )
    second = exchange.admit_order(
        intent=intent,
        market_status=MarketStatus.OPEN,
        submitted_at=NOW,
        required_balance=required_balance,
        available_balance=required_balance,
    )

    assert first == second
    assert first.admission_hash == second.admission_hash
    assert first.accepted
    assert first.activates_at == NOW + timedelta(milliseconds=latency_ms)


@given(price=_PRICE, quantity=_QUANTITY)
def test_simulated_exchange_rejection_is_deterministic_without_activation(
    price: Decimal,
    quantity: Decimal,
) -> None:
    exchange = DeterministicSimulatedExchange(
        rejection_model=BoundedRejectionModel(),
        latency_model=FixedLatencyModel.from_milliseconds(1),
    )
    intent = _intent(price=price, quantity=quantity)

    first = exchange.admit_order(
        intent=intent,
        market_status=MarketStatus.CLOSED,
        submitted_at=NOW,
    )
    second = exchange.admit_order(
        intent=intent,
        market_status=MarketStatus.CLOSED,
        submitted_at=NOW,
    )

    assert first == second
    assert first.rejected
    assert first.rejection_decision.reason_code is RejectionReason.MARKET_CLOSED
    assert first.accepted_at is None
    assert first.activates_at is None


@given(price=_PRICE, quantity=_QUANTITY)
def test_simulated_exchange_payload_preserves_exact_decimals(
    price: Decimal,
    quantity: Decimal,
) -> None:
    exchange = DeterministicSimulatedExchange(
        rejection_model=BoundedRejectionModel(),
        latency_model=FixedLatencyModel.from_milliseconds(0),
    )
    required_balance = price * quantity

    admission = exchange.admit_order(
        intent=_intent(price=price, quantity=quantity),
        market_status=MarketStatus.OPEN,
        submitted_at=NOW,
        required_balance=required_balance,
        available_balance=required_balance,
    )
    payload = to_canonical_data(admission.canonical_payload())

    assert payload["required_balance"] == str(required_balance)  # type: ignore[index]
    assert payload["available_balance"] == str(required_balance)  # type: ignore[index]
    assert payload["intent"]["quantity"] == str(quantity)  # type: ignore[index]
    assert payload["intent"]["limit_price"] == str(price)  # type: ignore[index]


def _intent(*, price: Decimal, quantity: Decimal) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_exchange_property",
            "strategy_id": "strat_exchange_property",
            "market_id": "mkt_exchange_property",
            "contract_id": "ctr_exchange_property",
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": quantity,
            "limit_price": price,
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_exchange_property",
            "idempotency_key": "idem-exchange-property",
        }
    )
