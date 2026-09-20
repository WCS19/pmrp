"""Simulation scenario harness tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.schemas.enums import LiquidityRole, MarketStatus, OrderType, Side, TimeInForce
from pmrp.schemas.market_data import OrderBookDelta, OrderBookDeltaAction, OrderBookSnapshot, Trade
from pmrp.schemas.orders import CancelOrderRequest, Fill, OrderIntent
from pmrp.schemas.serialization import canonical_sha256
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation import (
    SIMULATION_CANCEL_BEFORE_ACTIVATION,
    SIMULATION_CANCEL_FILL_RACE_LOST,
    SIMULATION_SCENARIO_HASH_VERSION,
    SIMULATION_SCENARIO_RUNNER_MODEL_NAME,
    DeterministicScenarioRunner,
    ExpectedSimulationFill,
    ScheduledMarketEvent,
    ScheduledOrderAction,
    SimulationArtifact,
    SimulationConfigurationError,
    SimulationScenario,
    SimulationSourceType,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 8, 1, 15, 0, tzinfo=UTC)


def test_simulation_scenario_builds_deterministic_contract() -> None:
    scenario = _scenario(
        market_events=(
            ScheduledMarketEvent(
                sequence=1,
                scheduled_at=NOW + timedelta(seconds=1),
                event=_delta(sequence=2, previous_sequence=1),
            ),
        ),
        order_actions=(
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW + timedelta(milliseconds=100),
                action=_intent(),
            ),
            ScheduledOrderAction(
                sequence=2,
                scheduled_at=NOW + timedelta(milliseconds=300),
                action=_cancel_request(),
            ),
        ),
        expected_fills=(ExpectedSimulationFill(sequence=0, fill=_fill()),),
        expected_final_book=_snapshot(sequence=2, snapshot_reason="expected_final"),
        tags=("partial_fill", "cancel_race"),
        metadata={"scenario": "SIM-006"},
    )

    assert SIMULATION_SCENARIO_HASH_VERSION == "simulation_scenario_hash_v1"
    assert scenario.configuration_hash == canonical_sha256(scenario.configuration)
    assert scenario.scenario_hash == canonical_sha256(scenario.canonical_payload())
    assert scenario.market_events[0].event_type == "order_book_delta"
    assert scenario.order_actions[0].action_type == "order_intent"
    assert scenario.order_actions[1].action_type == "cancel_order_request"
    assert scenario.source_type_counts[SimulationSourceType.OBSERVED_FACT] == 2
    assert scenario.source_type_counts[SimulationSourceType.INFERRED_BEHAVIOR] == 2
    assert scenario.source_type_counts[SimulationSourceType.SIMULATED_OUTPUT] == 2
    assert scenario.canonical_payload()["hash_version"] == SIMULATION_SCENARIO_HASH_VERSION
    assert (
        scenario.canonical_payload()["expected_final_book_source_type"]
        == SimulationSourceType.SIMULATED_OUTPUT
    )

    artifact = scenario.as_result_artifact(sequence=3)

    assert isinstance(artifact, SimulationArtifact)
    assert artifact.sequence == 3
    assert artifact.artifact_type == "simulation_scenario"
    assert artifact.artifact_id == "SIM-006"
    assert artifact.artifact_hash == scenario.scenario_hash


def test_simulation_scenario_normalizes_ordering_for_stable_hashes() -> None:
    first = _scenario(
        market_events=(
            ScheduledMarketEvent(
                sequence=2,
                scheduled_at=NOW + timedelta(seconds=2),
                event=_trade(sequence=3),
            ),
            ScheduledMarketEvent(
                sequence=1,
                scheduled_at=NOW + timedelta(seconds=1),
                event=_delta(sequence=2, previous_sequence=1),
            ),
        ),
        order_actions=(
            ScheduledOrderAction(
                sequence=2,
                scheduled_at=NOW + timedelta(milliseconds=200),
                action=_cancel_request(),
            ),
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW + timedelta(milliseconds=100),
                action=_intent(),
            ),
        ),
        expected_fills=(
            ExpectedSimulationFill(sequence=1, fill=_fill(fill_id="fill_scenario_002")),
            ExpectedSimulationFill(sequence=0, fill=_fill(fill_id="fill_scenario_001")),
        ),
        tags=("zeta", "alpha"),
    )
    second = _scenario(
        market_events=tuple(reversed(first.market_events)),
        order_actions=tuple(reversed(first.order_actions)),
        expected_fills=tuple(reversed(first.expected_fills)),
        tags=tuple(reversed(first.tags)),
    )

    assert [event.sequence for event in first.market_events] == [1, 2]
    assert [action.sequence for action in first.order_actions] == [1, 2]
    assert [fill.sequence for fill in first.expected_fills] == [0, 1]
    assert first.tags == ("alpha", "zeta")
    assert first.scenario_hash == second.scenario_hash


def test_simulation_scenario_rejects_invalid_configuration_inputs() -> None:
    with pytest.raises(SimulationConfigurationError) as configuration_error:
        SimulationScenario(
            scenario_id="SIM-001",
            name="invalid configuration",
            configuration="config",  # type: ignore[arg-type]
            initial_book=_snapshot(),
        )

    assert configuration_error.value.reason_code == "simulation_scenario_configuration_invalid"

    with pytest.raises(SimulationConfigurationError) as book_error:
        _scenario(initial_book=_snapshot(is_valid=False))

    assert book_error.value.reason_code == "simulation_scenario_initial_book_invalid"

    with pytest.raises(TypeError, match="market_events"):
        _scenario(market_events=[])  # type: ignore[arg-type]

    with pytest.raises(SimulationConfigurationError) as duplicate_error:
        _scenario(
            market_events=(
                ScheduledMarketEvent(sequence=0, scheduled_at=NOW, event=_delta()),
                ScheduledMarketEvent(sequence=0, scheduled_at=NOW, event=_trade()),
            )
        )

    assert duplicate_error.value.reason_code == "simulation_scenario_sequence_duplicate"

    with pytest.raises(SimulationConfigurationError) as tag_error:
        _scenario(tags=("dup", "dup"))

    assert tag_error.value.reason_code == "simulation_scenario_tag_duplicate"

    with pytest.raises(SimulationConfigurationError) as source_error:
        _scenario(
            expected_final_book=_snapshot(),
            expected_final_book_source_type=SimulationSourceType.OBSERVED_FACT,
        )

    assert (
        source_error.value.reason_code == "simulation_scenario_expected_final_book_source_invalid"
    )

    with pytest.raises(SimulationConfigurationError) as orphan_source_error:
        _scenario(expected_final_book_source_type=SimulationSourceType.SIMULATED_OUTPUT)

    assert (
        orphan_source_error.value.reason_code
        == "simulation_scenario_expected_final_book_source_invalid"
    )


def test_scheduled_items_reject_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="timezone-aware"):
        ScheduledMarketEvent(
            sequence=0,
            scheduled_at=datetime.fromisoformat("2026-08-01T15:00:00"),
            event=_delta(),
        )

    with pytest.raises(TypeError, match="OrderBookSnapshot"):
        ScheduledMarketEvent(sequence=0, scheduled_at=NOW, event="event")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="OrderIntent"):
        ScheduledOrderAction(sequence=0, scheduled_at=NOW, action="intent")  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="SimulationSourceType"):
        ScheduledOrderAction(
            sequence=0,
            scheduled_at=NOW,
            action=_intent(),
            source_type="observed",  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="sequence"):
        ExpectedSimulationFill(sequence=-1, fill=_fill())

    with pytest.raises(SimulationConfigurationError) as source_error:
        ExpectedSimulationFill(
            sequence=0,
            fill=_fill(),
            source_type=SimulationSourceType.OBSERVED_FACT,
        )

    assert source_error.value.reason_code == "simulation_scenario_expected_fill_source_invalid"


def test_simulation_scenario_rejects_lineage_mismatches() -> None:
    with pytest.raises(SimulationConfigurationError) as market_event_error:
        _scenario(
            market_events=(
                ScheduledMarketEvent(
                    sequence=0,
                    scheduled_at=NOW,
                    event=_delta(market_id="mkt_other"),
                ),
            )
        )

    assert market_event_error.value.reason_code == "simulation_scenario_market_event_mismatch"

    with pytest.raises(SimulationConfigurationError) as order_action_error:
        _scenario(
            order_actions=(
                ScheduledOrderAction(
                    sequence=0,
                    scheduled_at=NOW,
                    action=_intent(contract_id="ctr_other"),
                ),
            )
        )

    assert order_action_error.value.reason_code == "simulation_scenario_order_action_mismatch"

    with pytest.raises(SimulationConfigurationError) as cancel_error:
        _scenario(
            order_actions=(
                ScheduledOrderAction(
                    sequence=0,
                    scheduled_at=NOW,
                    action=_cancel_request(exchange="polymarket"),
                ),
            )
        )

    assert cancel_error.value.reason_code == "simulation_scenario_order_action_mismatch"

    with pytest.raises(SimulationConfigurationError) as fill_error:
        _scenario(
            expected_fills=(
                ExpectedSimulationFill(
                    sequence=0,
                    fill=_fill(exchange="polymarket"),
                ),
            )
        )

    assert fill_error.value.reason_code == "simulation_scenario_expected_fill_mismatch"

    with pytest.raises(SimulationConfigurationError) as final_book_error:
        _scenario(expected_final_book=_snapshot(exchange="polymarket"))

    assert final_book_error.value.reason_code == "simulation_scenario_expected_final_book_mismatch"


def test_simulation_scenario_metadata_is_immutable() -> None:
    scenario = _scenario(metadata={"scenario": "SIM-001"})
    original_hash = scenario.scenario_hash

    with pytest.raises(TypeError, match="does not support item assignment"):
        scenario.metadata["late"] = "mutation"

    assert scenario.scenario_hash == original_hash


def test_deterministic_scenario_runner_applies_latency_before_fill() -> None:
    scenario = _scenario(
        scenario_id="SIM-007",
        name="stale quote after latency",
        market_events=(
            ScheduledMarketEvent(
                sequence=1,
                scheduled_at=NOW + timedelta(milliseconds=100),
                event=_delta(
                    sequence=2,
                    previous_sequence=1,
                    side=Side.SELL,
                    price="0.43",
                    quantity="4",
                ),
            ),
        ),
        order_actions=(
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW,
                action=_intent(quantity="10", limit_price="0.43"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    repeated = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    order_result = run.order_results[0]
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert SIMULATION_SCENARIO_RUNNER_MODEL_NAME == "simulation_scenario_runner_v1"
    assert run.result_checksum == repeated.result_checksum
    assert run.run_hash == repeated.run_hash
    assert order_result.admission.accepted
    assert order_result.admission.activates_at == NOW + timedelta(milliseconds=125)
    assert order_result.activation_book is not None
    assert order_result.activation_book.sequence == 2
    assert order_result.fill_estimate is not None
    assert order_result.fill_estimate.filled_quantity == Decimal("4")
    assert order_result.fill_estimate.remaining_quantity == Decimal("6")
    assert order_result.fill_estimate.is_partial
    assert len(order_result.fee_estimates) == 1
    assert order_result.fee_estimates[0].net_fee_amount == Decimal("0")
    assert run.final_book == order_result.activation_book
    assert metrics["accepted_order_count"] == Decimal("1")
    assert metrics["filled_order_count"] == Decimal("1")
    assert metrics["partial_fill_count"] == Decimal("1")
    assert metrics["filled_quantity"] == Decimal("4")
    assert metrics["total_fee_amount"] == Decimal("0")
    assert metrics["total_filled_notional"] == Decimal("1.72")
    assert metrics["total_net_fee_amount"] == Decimal("0")
    assert metrics["total_rebate_amount"] == Decimal("0")
    assert run.result.source_type_counts[SimulationSourceType.INFERRED_BEHAVIOR] == 1
    assert run.result.source_type_counts[SimulationSourceType.SIMULATED_OUTPUT] == 4


def test_deterministic_scenario_runner_records_decimal_fees_from_configuration() -> None:
    scenario = _scenario(
        scenario_id="SIM-011",
        name="fee calculation",
        configuration=_configuration(
            parameters={
                "fee.currency": "USD",
                "fee.taker.rate_bps": "10",
                "fee.taker.fixed": "0.01",
                "fee.taker.rebate_rate_bps": "1",
                "fee.taker.fixed_rebate": "0.002",
            }
        ),
        order_actions=(
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW,
                action=_intent(quantity="10", limit_price="0.43"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    order_result = run.order_results[0]
    fee_estimate = order_result.fee_estimates[0]
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert order_result.fill_estimate is not None
    assert order_result.fill_estimate.filled_quantity == Decimal("10")
    assert fee_estimate.notional == Decimal("4.30")
    assert fee_estimate.fee_amount == Decimal("0.01430")
    assert fee_estimate.rebate_amount == Decimal("0.00243")
    assert fee_estimate.net_fee_amount == Decimal("0.01187")
    assert "fee_estimates" in order_result.canonical_payload()
    assert metrics["total_filled_notional"] == Decimal("4.30")
    assert metrics["total_fee_amount"] == Decimal("0.01430")
    assert metrics["total_rebate_amount"] == Decimal("0.00243")
    assert metrics["total_net_fee_amount"] == Decimal("0.01187")


def test_deterministic_scenario_runner_records_passive_no_fill() -> None:
    scenario = _scenario(
        scenario_id="SIM-002",
        name="passive order no fill",
        order_actions=(
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW,
                action=_intent(limit_price="0.42"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    fill_estimate = run.order_results[0].fill_estimate
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert fill_estimate is not None
    assert not fill_estimate.has_fill
    assert fill_estimate.average_fill_price is None
    assert fill_estimate.reason_code == "simulation_touch_no_fill"
    assert run.order_results[0].fee_estimates == ()
    assert metrics["accepted_order_count"] == Decimal("1")
    assert metrics["filled_order_count"] == Decimal("0")
    assert metrics["filled_quantity"] == Decimal("0")
    assert metrics["total_fee_amount"] == Decimal("0")


def test_deterministic_scenario_runner_records_rejections_without_fill_outputs() -> None:
    scenario = _scenario(
        scenario_id="SIM-008",
        name="market closes before activation",
        order_actions=(
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW,
                action=_intent(),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(
        scenario.configuration,
        market_status=MarketStatus.CLOSED,
    ).run(scenario)
    order_result = run.order_results[0]
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert order_result.admission.rejected
    assert order_result.activation_book is None
    assert order_result.fill_estimate is None
    assert metrics["accepted_order_count"] == Decimal("0")
    assert metrics["rejected_order_count"] == Decimal("1")
    assert run.result.source_type_counts[SimulationSourceType.SIMULATED_OUTPUT] == 2


def test_deterministic_scenario_runner_cancels_before_activation() -> None:
    scenario = _scenario(
        scenario_id="SIM-005",
        name="cancel before activation",
        order_actions=(
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW,
                action=_intent(quantity="10", limit_price="0.43"),
            ),
            ScheduledOrderAction(
                sequence=2,
                scheduled_at=NOW + timedelta(milliseconds=50),
                action=_cancel_request(),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    order_result = run.order_results[0]
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert order_result.admission.accepted
    assert order_result.cancel_result is not None
    assert order_result.cancel_result.outcome_code == SIMULATION_CANCEL_BEFORE_ACTIVATION
    assert order_result.activation_book is None
    assert order_result.fill_estimate is None
    assert order_result.fee_estimates == ()
    assert "cancel_result" in order_result.canonical_payload()
    assert metrics["cancel_action_count"] == Decimal("1")
    assert metrics["canceled_before_activation_count"] == Decimal("1")
    assert metrics["cancel_fill_race_count"] == Decimal("0")
    assert metrics["filled_order_count"] == Decimal("0")
    assert metrics["filled_quantity"] == Decimal("0")


def test_deterministic_scenario_runner_records_fill_during_cancel_race() -> None:
    scenario = _scenario(
        scenario_id="SIM-006",
        name="fill during cancel race",
        order_actions=(
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW,
                action=_intent(quantity="10", limit_price="0.43"),
            ),
            ScheduledOrderAction(
                sequence=2,
                scheduled_at=NOW + timedelta(milliseconds=200),
                action=_cancel_request(),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    order_result = run.order_results[0]
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert order_result.cancel_result is not None
    assert order_result.cancel_result.outcome_code == SIMULATION_CANCEL_FILL_RACE_LOST
    assert order_result.activation_book is not None
    assert order_result.fill_estimate is not None
    assert order_result.fill_estimate.filled_quantity == Decimal("10")
    assert len(order_result.fee_estimates) == 1
    assert metrics["cancel_action_count"] == Decimal("1")
    assert metrics["cancel_fill_race_count"] == Decimal("1")
    assert metrics["canceled_before_activation_count"] == Decimal("0")
    assert metrics["filled_order_count"] == Decimal("1")


def test_deterministic_scenario_runner_uses_noncolliding_artifact_sequences() -> None:
    order_actions = tuple(
        ScheduledOrderAction(
            sequence=index + 1,
            scheduled_at=NOW,
            action=_intent(
                intent_id=f"intent_scenario_bulk_{index:03d}",
                correlation_id=f"corr_scenario_bulk_{index:03d}",
                quantity="1",
            ),
        )
        for index in range(331)
    )
    scenario = _scenario(
        scenario_id="SIM-BULK-CANCEL",
        name="bulk cancel artifact sequence regression",
        order_actions=(
            *order_actions,
            ScheduledOrderAction(
                sequence=332,
                scheduled_at=NOW + timedelta(milliseconds=200),
                action=_cancel_request(correlation_id="corr_scenario_bulk_330"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    artifact_sequences = [artifact.sequence for artifact in run.result.artifacts]

    assert run.order_results[330].cancel_result is not None
    assert len(set(artifact_sequences)) == len(artifact_sequences)


def test_deterministic_scenario_runner_rejects_unmatched_cancel_actions() -> None:
    scenario = _scenario(
        order_actions=(
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW,
                action=_cancel_request(),
            ),
        ),
    )

    with pytest.raises(SimulationConfigurationError) as error:
        DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)

    assert error.value.reason_code == "simulation_scenario_cancel_unmatched"


def test_deterministic_scenario_runner_rejects_unsupported_configuration() -> None:
    scenario = _scenario(configuration=_configuration(fill_model="unsupported_fill_v1"))

    with pytest.raises(SimulationConfigurationError) as error:
        DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)

    assert error.value.reason_code == "simulation_scenario_runner_fill_model_unsupported"

    fee_scenario = _scenario(configuration=_configuration(fee_model="unsupported_fee_v1"))

    with pytest.raises(SimulationConfigurationError) as fee_error:
        DeterministicScenarioRunner.from_configuration(fee_scenario.configuration)

    assert fee_error.value.reason_code == "simulation_scenario_runner_fee_model_unsupported"


def test_deterministic_scenario_runner_validates_fee_configuration_without_fills() -> None:
    scenario = _scenario(
        configuration=_configuration(
            parameters={
                "fee.currency": "usd",
                "fee.taker.rate_bps": "not-a-decimal",
            }
        ),
        order_actions=(),
    )

    with pytest.raises(SimulationConfigurationError) as error:
        DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)

    assert error.value.reason_code == "simulation_scenario_runner_fee_configuration_invalid"
    assert "not-a-decimal" not in str(error.value)
    assert "usd" not in str(error.value)


def _scenario(
    *,
    scenario_id: str = "SIM-006",
    name: str = "fill during cancel race",
    configuration: SimulationConfiguration | None = None,
    initial_book: OrderBookSnapshot | None = None,
    market_events: tuple[ScheduledMarketEvent, ...] = (),
    order_actions: tuple[ScheduledOrderAction, ...] = (),
    expected_fills: tuple[ExpectedSimulationFill, ...] = (),
    expected_final_book: OrderBookSnapshot | None = None,
    expected_final_book_source_type: SimulationSourceType | None = None,
    tags: tuple[str, ...] = (),
    metadata: dict[str, str] | None = None,
) -> SimulationScenario:
    return SimulationScenario(
        scenario_id=scenario_id,
        name=name,
        configuration=configuration or _configuration(),
        initial_book=initial_book or _snapshot(),
        market_events=market_events,
        order_actions=order_actions,
        expected_fills=expected_fills,
        expected_final_book=expected_final_book,
        expected_final_book_source_type=expected_final_book_source_type,
        tags=tags,
        metadata=metadata or {},
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


def _snapshot(
    *,
    market_id: str = "mkt_scenario_market",
    contract_id: str = "ctr_scenario_contract",
    exchange: str = "kalshi",
    sequence: int | None = 1,
    is_valid: bool = True,
    snapshot_reason: str = "initial",
) -> OrderBookSnapshot:
    return OrderBookSnapshot.model_validate(
        {
            "market_id": market_id,
            "contract_id": contract_id,
            "exchange": exchange,
            "sequence": sequence,
            "exchange_occurred_at": NOW,
            "received_at": NOW,
            "bids": (
                {"price": "0.41", "quantity": "10", "order_count": 1},
                {"price": "0.40", "quantity": "20", "order_count": 2},
            ),
            "asks": (
                {"price": "0.43", "quantity": "12", "order_count": 1},
                {"price": "0.44", "quantity": "18", "order_count": 2},
            ),
            "is_valid": is_valid,
            "snapshot_reason": snapshot_reason,
        }
    )


def _delta(
    *,
    market_id: str = "mkt_scenario_market",
    contract_id: str = "ctr_scenario_contract",
    exchange: str = "kalshi",
    sequence: int | None = 2,
    previous_sequence: int | None = 1,
    side: Side = Side.BUY,
    price: str = "0.41",
    quantity: str = "8",
    action: OrderBookDeltaAction = OrderBookDeltaAction.UPSERT,
) -> OrderBookDelta:
    return OrderBookDelta.model_validate(
        {
            "market_id": market_id,
            "contract_id": contract_id,
            "exchange": exchange,
            "sequence": sequence,
            "previous_sequence": previous_sequence,
            "exchange_occurred_at": NOW + timedelta(seconds=1),
            "received_at": NOW + timedelta(seconds=1),
            "changes": (
                {
                    "side": side,
                    "price": price,
                    "quantity": quantity,
                    "action": action,
                },
            ),
        }
    )


def _trade(
    *,
    market_id: str = "mkt_scenario_market",
    contract_id: str = "ctr_scenario_contract",
    exchange: str = "kalshi",
    sequence: int | None = 3,
) -> Trade:
    return Trade.model_validate(
        {
            "trade_id": "trade_scenario_001",
            "exchange": exchange,
            "exchange_trade_id": "exchange-trade-scenario-001",
            "market_id": market_id,
            "contract_id": contract_id,
            "outcome_id": "out_yes",
            "price": "0.42",
            "quantity": "4",
            "aggressor_side": Side.BUY,
            "liquidity_role": LiquidityRole.TAKER,
            "exchange_occurred_at": NOW + timedelta(seconds=2),
            "received_at": NOW + timedelta(seconds=2),
            "sequence": sequence,
        }
    )


def _intent(
    *,
    intent_id: str = "intent_scenario_001",
    market_id: str = "mkt_scenario_market",
    contract_id: str = "ctr_scenario_contract",
    side: Side = Side.BUY,
    quantity: str | Decimal = "10",
    limit_price: str | Decimal | None = "0.43",
    correlation_id: str = "corr_scenario_001",
) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": intent_id,
            "strategy_id": "strat_scenario_v1",
            "market_id": market_id,
            "contract_id": contract_id,
            "outcome_id": "out_yes",
            "side": side,
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
            "correlation_id": correlation_id,
            "idempotency_key": f"idem-{intent_id}",
        }
    )


def _cancel_request(
    *,
    exchange: str = "kalshi",
    correlation_id: str = "corr_scenario_001",
) -> CancelOrderRequest:
    return CancelOrderRequest.model_validate(
        {
            "cancel_request_id": "cancel_scenario_001",
            "order_id": "ord_scenario_001",
            "exchange": exchange,
            "account_id": "acct_paper_001",
            "client_order_id": "client-order-scenario-001",
            "exchange_order_id": "exchange-order-scenario-001",
            "requested_at": NOW + timedelta(milliseconds=300),
            "idempotency_key": "idem-scenario-cancel-001",
            "correlation_id": correlation_id,
        }
    )


def _fill(
    *,
    fill_id: str = "fill_scenario_001",
    exchange: str = "kalshi",
    market_id: str = "mkt_scenario_market",
    contract_id: str = "ctr_scenario_contract",
) -> Fill:
    return Fill.model_validate(
        {
            "fill_id": fill_id,
            "exchange_fill_id": f"exchange-{fill_id}",
            "order_id": "ord_scenario_001",
            "exchange_order_id": "exchange-order-scenario-001",
            "client_order_id": "client-order-scenario-001",
            "exchange": exchange,
            "account_id": "acct_paper_001",
            "market_id": market_id,
            "contract_id": contract_id,
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "price": Decimal("0.42"),
            "quantity": Decimal("4"),
            "liquidity_role": LiquidityRole.TAKER,
            "fee": {"amount": "0.01", "currency": "USD"},
            "rebate": None,
            "exchange_occurred_at": NOW + timedelta(seconds=2),
            "received_at": NOW + timedelta(seconds=2),
            "trade_id": "trade_scenario_001",
        }
    )
