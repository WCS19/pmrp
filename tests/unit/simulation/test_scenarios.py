"""Simulation scenario harness tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.schemas.enums import LiquidityRole, MarketStatus, OrderType, Side, TimeInForce
from pmrp.schemas.market_data import OrderBookDelta, OrderBookDeltaAction, OrderBookSnapshot, Trade
from pmrp.schemas.orders import CancelOrderRequest, Fill, OrderIntent
from pmrp.schemas.portfolio import SettlementStatus
from pmrp.schemas.serialization import canonical_sha256
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation import (
    NO_SETTLEMENT_MODEL_NAME,
    SIMULATION_CANCEL_BEFORE_ACTIVATION,
    SIMULATION_CANCEL_FILL_RACE_LOST,
    SIMULATION_DISCONNECT_OPEN_ORDER,
    SIMULATION_SCENARIO_HASH_VERSION,
    SIMULATION_SCENARIO_RUNNER_MODEL_NAME,
    DeterministicScenarioRunner,
    ExpectedSimulationFill,
    RejectionReason,
    ScheduledMarketEvent,
    ScheduledOrderAction,
    SimulationArtifact,
    SimulationConfigurationError,
    SimulationInputError,
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
    assert len(order_result.slippage_estimates) == 1
    assert order_result.fee_estimates[0].net_fee_amount == Decimal("0")
    assert order_result.slippage_estimates[0].total_slippage == Decimal("0.0002580")
    assert run.final_book == order_result.activation_book
    assert metrics["accepted_order_count"] == Decimal("1")
    assert metrics["filled_order_count"] == Decimal("1")
    assert metrics["partial_fill_count"] == Decimal("1")
    assert metrics["filled_quantity"] == Decimal("4")
    assert metrics["total_fee_amount"] == Decimal("0")
    assert metrics["total_filled_notional"] == Decimal("1.72")
    assert metrics["total_net_fee_amount"] == Decimal("0")
    assert metrics["total_rebate_amount"] == Decimal("0")
    assert metrics["total_slippage_amount"] == Decimal("0.0002580")
    assert run.result.source_type_counts[SimulationSourceType.INFERRED_BEHAVIOR] == 1
    assert run.result.source_type_counts[SimulationSourceType.SIMULATED_OUTPUT] == 5


def test_deterministic_scenario_runner_records_decimal_fees_from_configuration() -> None:
    scenario = _scenario(
        scenario_id="SIM-012",
        name="taker fee calculation",
        configuration=_configuration(
            parameters={
                "fee.currency": "USD",
                "fee.taker.rate_bps": "10",
                "fee.taker.fixed": "0.01",
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
    assert fee_estimate.rebate_amount == Decimal("0")
    assert fee_estimate.net_fee_amount == Decimal("0.01430")
    assert "fee_estimates" in order_result.canonical_payload()
    assert metrics["total_filled_notional"] == Decimal("4.30")
    assert metrics["total_fee_amount"] == Decimal("0.01430")
    assert metrics["total_rebate_amount"] == Decimal("0")
    assert metrics["total_net_fee_amount"] == Decimal("0.01430")


def test_deterministic_scenario_runner_records_taker_slippage_from_configuration() -> None:
    scenario = _scenario(
        scenario_id="SIM-SLIPPAGE-TAKER",
        name="taker slippage calculation",
        configuration=_configuration(taker_slippage_bps="10"),
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
    slippage_estimate = order_result.slippage_estimates[0]
    metrics = {metric.name: metric.value for metric in run.result.metrics}
    artifact_types = {artifact.artifact_type for artifact in run.result.artifacts}

    assert order_result.fill_estimate is not None
    assert order_result.fill_estimate.filled_quantity == Decimal("10")
    assert slippage_estimate.side is Side.BUY
    assert slippage_estimate.liquidity_role is LiquidityRole.TAKER
    assert slippage_estimate.input_price == Decimal("0.43")
    assert slippage_estimate.adjusted_price == Decimal("0.43043")
    assert slippage_estimate.quantity == Decimal("10")
    assert slippage_estimate.slippage_bps == Decimal("10")
    assert slippage_estimate.slippage_amount_per_unit == Decimal("0.00043")
    assert slippage_estimate.total_slippage == Decimal("0.00430")
    assert "slippage_estimates" in order_result.canonical_payload()
    assert "simulation_slippage_estimates" in artifact_types
    assert metrics["slippage_estimate_count"] == Decimal("1")
    assert metrics["total_slippage_amount"] == Decimal("0.00430")


def test_deterministic_scenario_runner_records_rebates_from_configuration() -> None:
    scenario = _scenario(
        scenario_id="SIM-013",
        name="rebate calculation",
        configuration=_configuration(
            parameters={
                "fee.currency": "USD",
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
    assert fee_estimate.fee_amount == Decimal("0")
    assert fee_estimate.rebate_amount == Decimal("0.00243")
    assert fee_estimate.net_fee_amount == Decimal("-0.00243")
    assert "fee_estimates" in order_result.canonical_payload()
    assert metrics["total_filled_notional"] == Decimal("4.30")
    assert metrics["total_fee_amount"] == Decimal("0")
    assert metrics["total_rebate_amount"] == Decimal("0.00243")
    assert metrics["total_net_fee_amount"] == Decimal("-0.00243")


def test_deterministic_scenario_runner_records_settlement_payout() -> None:
    scenario = _scenario(
        scenario_id="SIM-014",
        name="settlement win",
        configuration=_configuration(
            parameters={
                "settlement_winning_outcome_ids": "out_yes",
                "settlement_payout_per_unit": "1.00",
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
    settlement_result = order_result.settlement_result
    metrics = {metric.name: metric.value for metric in run.result.metrics}
    artifacts = {artifact.artifact_type for artifact in run.result.artifacts}

    assert settlement_result is not None
    assert settlement_result.target_order_sequence == order_result.sequence
    assert settlement_result.estimate.status is SettlementStatus.SETTLED
    assert settlement_result.estimate.outcome_id == "out_yes"
    assert settlement_result.estimate.quantity == Decimal("10")
    assert settlement_result.estimate.winning_outcome_ids == ("out_yes",)
    assert settlement_result.estimate.payout_per_unit == Decimal("1.00")
    assert settlement_result.estimate.payout_amount == Decimal("10.00")
    assert settlement_result.estimate.is_winning_outcome is True
    assert "settlement_result" in order_result.canonical_payload()
    assert "simulation_settlement_result" in artifacts
    assert metrics["settlement_estimate_count"] == Decimal("1")
    assert metrics["settled_winning_quantity"] == Decimal("10")
    assert metrics["settled_payout_amount"] == Decimal("10.00")


def test_deterministic_scenario_runner_records_settlement_loss() -> None:
    scenario = _scenario(
        scenario_id="SIM-015",
        name="settlement loss",
        configuration=_configuration(
            parameters={
                "settlement_winning_outcome_ids": "out_no",
                "settlement_payout_per_unit": "1.00",
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
    settlement_result = run.order_results[0].settlement_result
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert settlement_result is not None
    assert settlement_result.estimate.status is SettlementStatus.SETTLED
    assert settlement_result.estimate.outcome_id == "out_yes"
    assert settlement_result.estimate.winning_outcome_ids == ("out_no",)
    assert settlement_result.estimate.payout_amount == Decimal("0")
    assert settlement_result.estimate.is_winning_outcome is False
    assert metrics["settlement_estimate_count"] == Decimal("1")
    assert metrics["settled_winning_quantity"] == Decimal("0")
    assert metrics["settled_payout_amount"] == Decimal("0")


def test_deterministic_scenario_runner_records_unresolved_no_settlement_estimate() -> None:
    scenario = _scenario(
        scenario_id="SIM-SETTLEMENT-NONE",
        name="unresolved settlement",
        configuration=_configuration(settlement_model=NO_SETTLEMENT_MODEL_NAME),
        order_actions=(
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW,
                action=_intent(quantity="3", limit_price="0.43"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    settlement_result = run.order_results[0].settlement_result
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert settlement_result is not None
    assert settlement_result.estimate.status is SettlementStatus.UNRESOLVED
    assert settlement_result.estimate.quantity == Decimal("3")
    assert settlement_result.estimate.winning_outcome_ids == ()
    assert settlement_result.estimate.payout_amount == Decimal("0")
    assert settlement_result.estimate.is_winning_outcome is False
    assert metrics["settlement_estimate_count"] == Decimal("1")
    assert metrics["settled_winning_quantity"] == Decimal("0")
    assert metrics["settled_payout_amount"] == Decimal("0")


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
    assert run.order_results[0].slippage_estimates == ()
    assert run.order_results[0].settlement_result is None
    assert metrics["accepted_order_count"] == Decimal("1")
    assert metrics["filled_order_count"] == Decimal("0")
    assert metrics["filled_quantity"] == Decimal("0")
    assert metrics["total_fee_amount"] == Decimal("0")


def test_deterministic_scenario_runner_records_passive_partial_fill() -> None:
    scenario = _scenario(
        scenario_id="SIM-003",
        name="passive order partial fill",
        market_events=(
            ScheduledMarketEvent(
                sequence=1,
                scheduled_at=NOW + timedelta(milliseconds=150),
                event=_trade(
                    price="0.42",
                    quantity="4",
                    aggressor_side=Side.SELL,
                ),
            ),
        ),
        order_actions=(
            ScheduledOrderAction(
                sequence=2,
                scheduled_at=NOW,
                action=_intent(quantity="10", limit_price="0.42"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    order_result = run.order_results[0]
    fill_estimate = order_result.fill_estimate
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert fill_estimate is not None
    assert fill_estimate.filled_quantity == Decimal("4")
    assert fill_estimate.remaining_quantity == Decimal("6")
    assert fill_estimate.average_fill_price == Decimal("0.42")
    assert fill_estimate.liquidity_role is LiquidityRole.MAKER
    assert fill_estimate.components[0].liquidity_role is LiquidityRole.MAKER
    assert fill_estimate.reason_code == "simulation_resting_trade_partial_fill"
    assert len(order_result.fee_estimates) == 1
    assert order_result.fee_estimates[0].liquidity_role is LiquidityRole.MAKER
    assert metrics["filled_order_count"] == Decimal("1")
    assert metrics["partial_fill_count"] == Decimal("1")
    assert metrics["filled_quantity"] == Decimal("4")
    assert metrics["total_filled_notional"] == Decimal("1.68")


def test_deterministic_scenario_runner_skips_duplicate_resting_trade_fills() -> None:
    duplicate_trade = _trade(
        price="0.42",
        quantity="4",
        aggressor_side=Side.SELL,
    )
    scenario = _scenario(
        scenario_id="SIM-017-RESTING-TRADE",
        name="duplicate resting trade event",
        market_events=(
            ScheduledMarketEvent(
                sequence=1,
                scheduled_at=NOW + timedelta(milliseconds=150),
                event=duplicate_trade,
            ),
            ScheduledMarketEvent(
                sequence=2,
                scheduled_at=NOW + timedelta(milliseconds=175),
                event=duplicate_trade,
            ),
        ),
        order_actions=(
            ScheduledOrderAction(
                sequence=3,
                scheduled_at=NOW,
                action=_intent(quantity="10", limit_price="0.42"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    fill_estimate = run.order_results[0].fill_estimate
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert fill_estimate is not None
    assert fill_estimate.filled_quantity == Decimal("4")
    assert fill_estimate.remaining_quantity == Decimal("6")
    assert metrics["duplicate_market_event_count"] == Decimal("1")
    assert metrics["projected_market_event_count"] == Decimal("1")


def test_deterministic_scenario_runner_records_passive_full_fill() -> None:
    scenario = _scenario(
        scenario_id="SIM-004",
        name="passive order full fill",
        market_events=(
            ScheduledMarketEvent(
                sequence=1,
                scheduled_at=NOW + timedelta(milliseconds=150),
                event=_trade(
                    price="0.42",
                    quantity="10",
                    aggressor_side=Side.SELL,
                ),
            ),
        ),
        order_actions=(
            ScheduledOrderAction(
                sequence=2,
                scheduled_at=NOW,
                action=_intent(quantity="10", limit_price="0.42"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    fill_estimate = run.order_results[0].fill_estimate
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert fill_estimate is not None
    assert fill_estimate.filled_quantity == Decimal("10")
    assert fill_estimate.remaining_quantity == Decimal("0")
    assert fill_estimate.is_full
    assert fill_estimate.liquidity_role is LiquidityRole.MAKER
    assert fill_estimate.reason_code == "simulation_resting_trade_full_fill"
    assert metrics["filled_order_count"] == Decimal("1")
    assert metrics["partial_fill_count"] == Decimal("0")
    assert metrics["filled_quantity"] == Decimal("10")


def test_deterministic_scenario_runner_records_maker_fees_from_configuration() -> None:
    scenario = _scenario(
        scenario_id="SIM-011",
        name="maker fee calculation",
        configuration=_configuration(
            parameters={
                "fee.currency": "USD",
                "fee.maker.rate_bps": "5",
                "fee.maker.fixed": "0.01",
            }
        ),
        market_events=(
            ScheduledMarketEvent(
                sequence=1,
                scheduled_at=NOW + timedelta(milliseconds=150),
                event=_trade(
                    price="0.42",
                    quantity="10",
                    aggressor_side=Side.SELL,
                ),
            ),
        ),
        order_actions=(
            ScheduledOrderAction(
                sequence=2,
                scheduled_at=NOW,
                action=_intent(quantity="10", limit_price="0.42"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    order_result = run.order_results[0]
    fee_estimate = order_result.fee_estimates[0]
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert order_result.fill_estimate is not None
    assert order_result.fill_estimate.liquidity_role is LiquidityRole.MAKER
    assert fee_estimate.liquidity_role is LiquidityRole.MAKER
    assert fee_estimate.notional == Decimal("4.20")
    assert fee_estimate.fee_amount == Decimal("0.01210")
    assert fee_estimate.rebate_amount == Decimal("0")
    assert fee_estimate.net_fee_amount == Decimal("0.01210")
    assert metrics["total_filled_notional"] == Decimal("4.20")
    assert metrics["total_fee_amount"] == Decimal("0.01210")
    assert metrics["total_net_fee_amount"] == Decimal("0.01210")


def test_deterministic_scenario_runner_records_disconnect_with_open_order() -> None:
    disconnected_at = NOW + timedelta(milliseconds=140)
    scenario = _scenario(
        scenario_id="SIM-016",
        name="disconnect with open order",
        configuration=_configuration(
            parameters={
                "connectivity.disconnected_at": disconnected_at.isoformat(),
            }
        ),
        market_events=(
            ScheduledMarketEvent(
                sequence=1,
                scheduled_at=NOW + timedelta(milliseconds=150),
                event=_trade(
                    price="0.42",
                    quantity="10",
                    aggressor_side=Side.SELL,
                ),
            ),
        ),
        order_actions=(
            ScheduledOrderAction(
                sequence=2,
                scheduled_at=NOW,
                action=_intent(quantity="10", limit_price="0.42"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    order_result = run.order_results[0]
    fill_estimate = order_result.fill_estimate
    disconnect_result = order_result.disconnect_result
    metrics = {metric.name: metric.value for metric in run.result.metrics}
    artifact_types = {artifact.artifact_type for artifact in run.result.artifacts}

    assert fill_estimate is not None
    assert not fill_estimate.has_fill
    assert fill_estimate.reason_code == "simulation_touch_no_fill"
    assert order_result.fee_estimates == ()
    assert disconnect_result is not None
    assert disconnect_result.target_order_sequence == order_result.sequence
    assert disconnect_result.disconnected_at == disconnected_at
    assert disconnect_result.reconnected_at is None
    assert disconnect_result.outcome_code == SIMULATION_DISCONNECT_OPEN_ORDER
    assert "disconnect_result" in order_result.canonical_payload()
    assert "simulation_disconnect_result" in artifact_types
    assert metrics["disconnect_window_count"] == Decimal("1")
    assert metrics["open_order_disconnect_count"] == Decimal("1")
    assert metrics["filled_order_count"] == Decimal("0")
    assert metrics["filled_quantity"] == Decimal("0")


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


def test_deterministic_scenario_runner_rejects_insufficient_simulated_balance() -> None:
    scenario = _scenario(
        scenario_id="SIM-009",
        name="insufficient simulated balance",
        configuration=_configuration(parameters={"balance.available": "4.29"}),
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
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert order_result.admission.rejected
    assert order_result.admission.rejection_decision.reason_code is (
        RejectionReason.INSUFFICIENT_BALANCE
    )
    assert order_result.admission.required_balance == Decimal("4.30")
    assert order_result.admission.available_balance == Decimal("4.29")
    assert order_result.activation_book is None
    assert order_result.fill_estimate is None
    assert order_result.fee_estimates == ()
    assert order_result.settlement_result is None
    assert metrics["accepted_order_count"] == Decimal("0")
    assert metrics["rejected_order_count"] == Decimal("1")
    assert metrics["filled_quantity"] == Decimal("0")


def test_deterministic_scenario_runner_accepts_sufficient_simulated_balance() -> None:
    scenario = _scenario(
        scenario_id="SIM-009-SUFFICIENT",
        name="sufficient simulated balance",
        configuration=_configuration(parameters={"balance.available": "4.30"}),
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

    assert order_result.admission.accepted
    assert order_result.admission.required_balance == Decimal("4.30")
    assert order_result.admission.available_balance == Decimal("4.30")
    assert order_result.fill_estimate is not None
    assert order_result.fill_estimate.filled_quantity == Decimal("10")


def test_deterministic_scenario_runner_balance_does_not_mask_invalid_price() -> None:
    scenario = _scenario(
        scenario_id="SIM-009-INVALID-PRICE",
        name="balance invalid price precedence",
        configuration=_configuration(parameters={"balance.available": "10.00"}),
        order_actions=(
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW,
                action=_intent(side=Side.SELL, quantity="10", limit_price="1.01"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    order_result = run.order_results[0]

    assert order_result.admission.rejected
    assert order_result.admission.rejection_decision.reason_code is RejectionReason.INVALID_PRICE
    assert order_result.admission.required_balance is None
    assert order_result.admission.available_balance == Decimal("10.00")


def test_deterministic_scenario_runner_rejects_post_only_order_that_would_cross() -> None:
    scenario = _scenario(
        scenario_id="SIM-010",
        name="post-only order would cross",
        market_events=(
            ScheduledMarketEvent(
                sequence=1,
                scheduled_at=NOW + timedelta(milliseconds=100),
                event=_delta(
                    sequence=2,
                    previous_sequence=1,
                    side=Side.SELL,
                    price="0.42",
                    quantity="4",
                ),
            ),
        ),
        order_actions=(
            ScheduledOrderAction(
                sequence=2,
                scheduled_at=NOW,
                action=_intent(
                    intent_id="intent_scenario_post_only_cross",
                    quantity="10",
                    limit_price="0.42",
                    post_only=True,
                ),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    order_result = run.order_results[0]
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.final_book.sequence == 2
    assert order_result.admission.rejected
    assert order_result.admission.rejection_decision.reason_code is (
        RejectionReason.POST_ONLY_WOULD_CROSS
    )
    assert order_result.activation_book is None
    assert order_result.fill_estimate is None
    assert order_result.fee_estimates == ()
    assert order_result.settlement_result is None
    assert metrics["accepted_order_count"] == Decimal("0")
    assert metrics["rejected_order_count"] == Decimal("1")
    assert metrics["filled_order_count"] == Decimal("0")


def test_deterministic_scenario_runner_allows_passive_post_only_order() -> None:
    scenario = _scenario(
        scenario_id="SIM-010-PASSIVE",
        name="post-only passive order",
        order_actions=(
            ScheduledOrderAction(
                sequence=1,
                scheduled_at=NOW,
                action=_intent(
                    intent_id="intent_scenario_post_only_passive",
                    limit_price="0.42",
                    post_only=True,
                ),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    order_result = run.order_results[0]

    assert order_result.admission.accepted
    assert order_result.activation_book is not None
    assert order_result.fill_estimate is not None
    assert not order_result.fill_estimate.has_fill


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


def test_deterministic_scenario_runner_ignores_duplicate_market_events() -> None:
    duplicate_delta = _delta(
        sequence=2,
        previous_sequence=1,
        side=Side.SELL,
        price="0.42",
        quantity="4",
    )
    scenario = _scenario(
        scenario_id="SIM-017",
        name="duplicate market event",
        market_events=(
            ScheduledMarketEvent(
                sequence=1,
                scheduled_at=NOW + timedelta(milliseconds=50),
                event=duplicate_delta,
            ),
            ScheduledMarketEvent(
                sequence=2,
                scheduled_at=NOW + timedelta(milliseconds=75),
                event=duplicate_delta,
            ),
        ),
        order_actions=(
            ScheduledOrderAction(
                sequence=3,
                scheduled_at=NOW,
                action=_intent(quantity="10", limit_price="0.42"),
            ),
        ),
    )

    run = DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)
    order_result = run.order_results[0]
    metrics = {metric.name: metric.value for metric in run.result.metrics}

    assert run.final_book.sequence == 2
    assert run.final_book.asks[0].price == Decimal("0.42")
    assert run.final_book.asks[0].quantity == Decimal("4")
    assert order_result.activation_book == run.final_book
    assert order_result.fill_estimate is not None
    assert order_result.fill_estimate.filled_quantity == Decimal("4")
    assert order_result.fill_estimate.remaining_quantity == Decimal("6")
    assert metrics["market_event_count"] == Decimal("2")
    assert metrics["duplicate_market_event_count"] == Decimal("1")
    assert metrics["projected_market_event_count"] == Decimal("1")


def test_deterministic_scenario_runner_rejects_conflicting_duplicate_market_sequence() -> None:
    scenario = _scenario(
        scenario_id="SIM-017-CONFLICT",
        name="conflicting duplicate market sequence",
        market_events=(
            ScheduledMarketEvent(
                sequence=1,
                scheduled_at=NOW + timedelta(milliseconds=50),
                event=_delta(
                    sequence=2,
                    previous_sequence=1,
                    side=Side.SELL,
                    price="0.42",
                    quantity="4",
                ),
            ),
            ScheduledMarketEvent(
                sequence=2,
                scheduled_at=NOW + timedelta(milliseconds=75),
                event=_delta(
                    sequence=2,
                    previous_sequence=1,
                    side=Side.SELL,
                    price="0.42",
                    quantity="5",
                ),
            ),
        ),
    )

    with pytest.raises(SimulationInputError) as error:
        DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)

    assert error.value.reason_code == "simulation_order_book_sequence_mismatch"


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

    settlement_scenario = _scenario(
        configuration=_configuration(settlement_model="unsupported_settlement_v1")
    )

    with pytest.raises(SimulationConfigurationError) as settlement_error:
        DeterministicScenarioRunner.from_configuration(settlement_scenario.configuration)

    assert (
        settlement_error.value.reason_code
        == "simulation_scenario_runner_settlement_model_unsupported"
    )

    slippage_scenario = _scenario(configuration=_configuration(slippage_model="sampled_v1"))

    with pytest.raises(SimulationConfigurationError) as slippage_error:
        DeterministicScenarioRunner.from_configuration(slippage_scenario.configuration)

    assert (
        slippage_error.value.reason_code == "simulation_scenario_runner_slippage_model_unsupported"
    )


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


def test_deterministic_scenario_runner_validates_balance_configuration_without_fills() -> None:
    scenario = _scenario(
        configuration=_configuration(parameters={"balance.available": "not-a-decimal"}),
        order_actions=(),
    )

    with pytest.raises(SimulationConfigurationError) as error:
        DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)

    assert error.value.reason_code == "simulation_scenario_runner_balance_configuration_invalid"
    assert "not-a-decimal" not in str(error.value)

    negative_scenario = _scenario(
        configuration=_configuration(parameters={"balance.available": "-0.01"}),
        order_actions=(),
    )

    with pytest.raises(SimulationConfigurationError) as negative_error:
        DeterministicScenarioRunner.from_configuration(negative_scenario.configuration).run(
            negative_scenario
        )

    assert (
        negative_error.value.reason_code
        == "simulation_scenario_runner_balance_configuration_invalid"
    )


def test_deterministic_scenario_runner_validates_disconnect_configuration_without_fills() -> None:
    reconnected_at = NOW + timedelta(milliseconds=200)
    reconnected_only = _scenario(
        configuration=_configuration(
            parameters={"connectivity.reconnected_at": reconnected_at.isoformat()}
        ),
        order_actions=(),
    )

    with pytest.raises(SimulationConfigurationError) as reconnected_only_error:
        DeterministicScenarioRunner.from_configuration(reconnected_only.configuration).run(
            reconnected_only
        )

    assert (
        reconnected_only_error.value.reason_code
        == "simulation_scenario_runner_disconnect_configuration_invalid"
    )

    invalid_datetime = _scenario(
        configuration=_configuration(parameters={"connectivity.disconnected_at": "not-a-datetime"}),
        order_actions=(),
    )

    with pytest.raises(SimulationConfigurationError) as invalid_datetime_error:
        DeterministicScenarioRunner.from_configuration(invalid_datetime.configuration).run(
            invalid_datetime
        )

    assert (
        invalid_datetime_error.value.reason_code
        == "simulation_scenario_runner_disconnect_configuration_invalid"
    )
    assert "not-a-datetime" not in str(invalid_datetime_error.value)

    reversed_window = _scenario(
        configuration=_configuration(
            parameters={
                "connectivity.disconnected_at": reconnected_at.isoformat(),
                "connectivity.reconnected_at": NOW.isoformat(),
            }
        ),
        order_actions=(),
    )

    with pytest.raises(SimulationConfigurationError) as reversed_window_error:
        DeterministicScenarioRunner.from_configuration(reversed_window.configuration).run(
            reversed_window
        )

    assert (
        reversed_window_error.value.reason_code
        == "simulation_scenario_runner_disconnect_configuration_invalid"
    )


def test_deterministic_scenario_runner_rejects_invalid_settlement_winners() -> None:
    scenario = _scenario(
        configuration=_configuration(
            parameters={"settlement_winning_outcome_ids": "out_yes, out_no"}
        ),
        order_actions=(),
    )

    with pytest.raises(SimulationConfigurationError) as error:
        DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)

    assert error.value.reason_code == "simulation_scenario_runner_settlement_winners_invalid"
    assert "out_yes" not in str(error.value)
    assert "out_no" not in str(error.value)

    duplicate_scenario = _scenario(
        configuration=_configuration(
            parameters={"settlement_winning_outcome_ids": "out_yes,out_yes"}
        ),
        order_actions=(),
    )

    with pytest.raises(SimulationConfigurationError) as duplicate_error:
        DeterministicScenarioRunner.from_configuration(duplicate_scenario.configuration).run(
            duplicate_scenario
        )

    assert (
        duplicate_error.value.reason_code == "simulation_scenario_runner_settlement_winners_invalid"
    )

    no_settlement_scenario = _scenario(
        configuration=_configuration(
            settlement_model=NO_SETTLEMENT_MODEL_NAME,
            parameters={"settlement_winning_outcome_ids": "out_yes"},
        ),
        order_actions=(),
    )

    with pytest.raises(SimulationConfigurationError) as no_settlement_error:
        DeterministicScenarioRunner.from_configuration(no_settlement_scenario.configuration).run(
            no_settlement_scenario
        )

    assert (
        no_settlement_error.value.reason_code
        == "simulation_scenario_runner_settlement_winners_invalid"
    )


def test_deterministic_scenario_runner_validates_settlement_configuration_without_fills() -> None:
    scenario = _scenario(
        configuration=_configuration(parameters={"settlement_payout_per_unit": "not-a-decimal"}),
        order_actions=(),
    )

    with pytest.raises(SimulationConfigurationError) as error:
        DeterministicScenarioRunner.from_configuration(scenario.configuration).run(scenario)

    assert error.value.reason_code == "simulation_scenario_runner_settlement_configuration_invalid"
    assert "not-a-decimal" not in str(error.value)


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
    trade_id: str = "trade_scenario_001",
    outcome_id: str = "out_yes",
    price: str = "0.42",
    quantity: str = "4",
    aggressor_side: Side | None = Side.BUY,
    liquidity_role: LiquidityRole = LiquidityRole.TAKER,
) -> Trade:
    return Trade.model_validate(
        {
            "trade_id": trade_id,
            "exchange": exchange,
            "exchange_trade_id": f"exchange-{trade_id}",
            "market_id": market_id,
            "contract_id": contract_id,
            "outcome_id": outcome_id,
            "price": price,
            "quantity": quantity,
            "aggressor_side": aggressor_side,
            "liquidity_role": liquidity_role,
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
    post_only: bool = False,
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
            "post_only": post_only,
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
