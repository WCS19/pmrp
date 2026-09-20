"""Property tests for simulation scenarios."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.enums import LiquidityRole, OrderType, Side, TimeInForce
from pmrp.schemas.market_data import OrderBookDelta, OrderBookDeltaAction, OrderBookSnapshot
from pmrp.schemas.orders import Fill, OrderIntent
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation import (
    ExpectedSimulationFill,
    ScheduledMarketEvent,
    ScheduledOrderAction,
    SimulationScenario,
)

pytestmark = pytest.mark.property

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)

_SEED = st.integers(min_value=0, max_value=2**31 - 1)
_QUANTITY = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("10000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)
_PRICE = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("0.9999"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


@given(seed=_SEED)
def test_simulation_scenario_hash_is_deterministic(seed: int) -> None:
    scenario = _scenario(configuration=_configuration(random_seed=seed))

    assert scenario.scenario_hash == scenario.scenario_hash
    assert (
        scenario.scenario_hash
        == SimulationScenario(
            scenario_id=scenario.scenario_id,
            name=scenario.name,
            configuration=scenario.configuration,
            initial_book=scenario.initial_book,
            market_events=scenario.market_events,
            order_actions=scenario.order_actions,
            expected_fills=scenario.expected_fills,
            expected_final_book=scenario.expected_final_book,
            expected_final_book_source_type=scenario.expected_final_book_source_type,
            tags=scenario.tags,
            metadata=dict(scenario.metadata),
        ).scenario_hash
    )


@given(quantity=_QUANTITY, price=_PRICE)
def test_simulation_scenario_preserves_exact_expected_fill_decimals(
    quantity: Decimal,
    price: Decimal,
) -> None:
    scenario = _scenario(
        expected_fills=(
            ExpectedSimulationFill(
                sequence=0,
                fill=_fill(price=price, quantity=quantity),
            ),
        )
    )

    payload = scenario.canonical_payload()
    expected_fill = scenario.expected_fills[0].fill

    assert expected_fill.price == price
    assert expected_fill.quantity == quantity
    assert payload["expected_fills"][0]["fill"]["price"] == str(price)  # type: ignore[index]
    assert payload["expected_fills"][0]["fill"]["quantity"] == str(quantity)  # type: ignore[index]


@given(seed=_SEED)
def test_simulation_scenario_hash_changes_when_configuration_changes(seed: int) -> None:
    first = _scenario(configuration=_configuration(random_seed=seed))
    second = _scenario(configuration=_configuration(random_seed=seed + 1))

    assert first.scenario_hash != second.scenario_hash


def test_simulation_scenario_hash_is_stable_across_input_order() -> None:
    first_event = ScheduledMarketEvent(
        sequence=1,
        scheduled_at=NOW + timedelta(seconds=1),
        event=_delta(sequence=2, previous_sequence=1),
    )
    second_event = ScheduledMarketEvent(
        sequence=2,
        scheduled_at=NOW + timedelta(seconds=2),
        event=_delta(sequence=3, previous_sequence=2),
    )
    first_action = ScheduledOrderAction(
        sequence=1,
        scheduled_at=NOW,
        action=_intent(intent_id="intent_scenario_property_001"),
    )
    second_action = ScheduledOrderAction(
        sequence=2,
        scheduled_at=NOW + timedelta(milliseconds=1),
        action=_intent(intent_id="intent_scenario_property_002"),
    )

    first = _scenario(
        market_events=(first_event, second_event),
        order_actions=(first_action, second_action),
        tags=("beta", "alpha"),
    )
    second = _scenario(
        market_events=(second_event, first_event),
        order_actions=(second_action, first_action),
        tags=("alpha", "beta"),
    )

    assert first.scenario_hash == second.scenario_hash


def _scenario(
    *,
    configuration: SimulationConfiguration | None = None,
    market_events: tuple[ScheduledMarketEvent, ...] = (),
    order_actions: tuple[ScheduledOrderAction, ...] = (),
    expected_fills: tuple[ExpectedSimulationFill, ...] = (),
    tags: tuple[str, ...] = (),
) -> SimulationScenario:
    return SimulationScenario(
        scenario_id="SIM-001",
        name="limit order immediately marketable",
        configuration=configuration or _configuration(),
        initial_book=_snapshot(),
        market_events=market_events,
        order_actions=order_actions,
        expected_fills=expected_fills,
        tags=tags,
        metadata={"catalog_id": "SIM-001"},
    )


def _configuration(**overrides: object) -> SimulationConfiguration:
    payload: dict[str, object] = {
        "simulation_version": "sim-v1",
        "fill_model": "touch_fill_v1",
        "queue_model": "immediate_touch_v1",
        "latency_model": "fixed_latency_v1",
        "fee_model": "fee_table_v1",
        "rejection_model": "bounded_rejection_v1",
        "slippage_model": "bps_slippage_v1",
        "settlement_model": "binary_settlement_v1",
        "random_seed": 42,
        "fixed_latency_ms": 125,
        "taker_slippage_bps": "1.50",
        "parameters": {},
    }
    payload.update(overrides)
    return SimulationConfiguration.model_validate(payload)


def _snapshot() -> OrderBookSnapshot:
    return OrderBookSnapshot.model_validate(
        {
            "market_id": "mkt_scenario_property",
            "contract_id": "ctr_scenario_property",
            "exchange": "kalshi",
            "sequence": 1,
            "exchange_occurred_at": NOW,
            "received_at": NOW,
            "bids": ({"price": "0.41", "quantity": "10"},),
            "asks": ({"price": "0.43", "quantity": "12"},),
            "is_valid": True,
            "snapshot_reason": "scenario_property",
        }
    )


def _delta(*, sequence: int, previous_sequence: int) -> OrderBookDelta:
    return OrderBookDelta.model_validate(
        {
            "market_id": "mkt_scenario_property",
            "contract_id": "ctr_scenario_property",
            "exchange": "kalshi",
            "sequence": sequence,
            "previous_sequence": previous_sequence,
            "exchange_occurred_at": NOW + timedelta(seconds=sequence),
            "received_at": NOW + timedelta(seconds=sequence),
            "changes": (
                {
                    "side": Side.BUY,
                    "price": "0.41",
                    "quantity": "8",
                    "action": OrderBookDeltaAction.UPSERT,
                },
            ),
        }
    )


def _intent(*, intent_id: str = "intent_scenario_property_001") -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": intent_id,
            "strategy_id": "strat_scenario_property",
            "market_id": "mkt_scenario_property",
            "contract_id": "ctr_scenario_property",
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": "10",
            "limit_price": "0.43",
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_scenario_property",
            "idempotency_key": f"idem-{intent_id}",
        }
    )


def _fill(*, price: Decimal, quantity: Decimal) -> Fill:
    return Fill.model_validate(
        {
            "fill_id": "fill_scenario_property",
            "exchange_fill_id": "exchange-fill-scenario-property",
            "order_id": "ord_scenario_property",
            "exchange_order_id": "exchange-order-scenario-property",
            "client_order_id": "client-order-scenario-property",
            "exchange": "kalshi",
            "account_id": "acct_paper_property",
            "market_id": "mkt_scenario_property",
            "contract_id": "ctr_scenario_property",
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "price": price,
            "quantity": quantity,
            "liquidity_role": LiquidityRole.TAKER,
            "fee": {"amount": "0", "currency": "USD"},
            "rebate": None,
            "exchange_occurred_at": NOW + timedelta(seconds=2),
            "received_at": NOW + timedelta(seconds=2),
            "trade_id": "trade_scenario_property",
        }
    )
