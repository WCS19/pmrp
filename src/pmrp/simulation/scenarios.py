"""Deterministic simulation scenario definitions."""

from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from pmrp.schemas.enums import LiquidityRole, MarketStatus, Side
from pmrp.schemas.identifiers import OutcomeId
from pmrp.schemas.market_data import OrderBookDelta, OrderBookSnapshot, Trade
from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.orders import CancelOrderRequest, Fill, OrderIntent
from pmrp.schemas.serialization import canonical_sha256, to_canonical_data
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.schemas.time import parse_utc_datetime
from pmrp.simulation.errors import SimulationConfigurationError
from pmrp.simulation.exchange import (
    DeterministicSimulatedExchange,
    SimulatedExchange,
    SimulatedExchangeOrderAdmission,
)
from pmrp.simulation.fee_models import (
    FEE_TABLE_MODEL_NAME,
    FeeEstimate,
    FeeModel,
    FeeRule,
    FeeTableModel,
)
from pmrp.simulation.fill_models import (
    TOUCH_FILL_MODEL_NAME,
    TRADE_THROUGH_FILL_MODEL_NAME,
    FillEstimate,
    FillModel,
    SimulatedFillComponent,
    TouchFillModel,
    TradeThroughFillModel,
)
from pmrp.simulation.latency_models import (
    FIXED_LATENCY_MODEL_NAME,
    FixedLatencyModel,
)
from pmrp.simulation.order_book import apply_order_book_delta, best_ask, best_bid
from pmrp.simulation.rejection_models import (
    BOUNDED_REJECTION_MODEL_NAME,
    BoundedRejectionModel,
    RejectionDecision,
    RejectionReason,
)
from pmrp.simulation.results import (
    SimulationArtifact,
    SimulationMetric,
    SimulationResult,
    SimulationSourceType,
)
from pmrp.simulation.settlement import (
    BINARY_SETTLEMENT_MODEL_NAME,
    NO_SETTLEMENT_MODEL_NAME,
    BinarySettlementModel,
    NoSettlementModel,
    SettlementEstimate,
    SettlementModel,
)

SIMULATION_SCENARIO_HASH_VERSION = "simulation_scenario_hash_v1"
SIMULATION_SCENARIO_RUNNER_MODEL_NAME = "simulation_scenario_runner_v1"
SIMULATION_CANCEL_AFTER_ACTIVATION_NO_FILL = "simulation_cancel_after_activation_no_fill"
SIMULATION_CANCEL_BEFORE_ACTIVATION = "simulation_cancel_before_activation"
SIMULATION_CANCEL_FILL_RACE_LOST = "simulation_cancel_fill_race_lost"

_MAX_TEXT_LENGTH = 128
_ONE = Decimal("1")
_ZERO = Decimal("0")
_AVAILABLE_BALANCE_PARAMETER = "balance.available"
_DEFAULT_FEE_CURRENCY = "USD"
_FEE_CURRENCY_PARAMETER = "fee.currency"
_FEE_FIXED_PARAMETER = "fee.{role}.fixed"
_FEE_FIXED_REBATE_PARAMETER = "fee.{role}.fixed_rebate"
_FEE_RATE_BPS_PARAMETER = "fee.{role}.rate_bps"
_FEE_REBATE_RATE_BPS_PARAMETER = "fee.{role}.rebate_rate_bps"
_SETTLEMENT_WINNING_OUTCOME_IDS_PARAMETER = "settlement_winning_outcome_ids"
_ORDER_RESULT_ARTIFACT_BASE_SEQUENCE = 10
_ORDER_RESULT_ARTIFACT_STRIDE = 5
_CANCEL_OUTCOME_CODES = frozenset(
    {
        SIMULATION_CANCEL_AFTER_ACTIVATION_NO_FILL,
        SIMULATION_CANCEL_BEFORE_ACTIVATION,
        SIMULATION_CANCEL_FILL_RACE_LOST,
    }
)

type ScenarioMarketEventPayload = OrderBookSnapshot | OrderBookDelta | Trade
type ScenarioOrderActionPayload = OrderIntent | CancelOrderRequest


@runtime_checkable
class ScenarioRunner(Protocol):
    """Pure deterministic simulation scenario runner interface."""

    def run(self, scenario: SimulationScenario) -> SimulationScenarioRun:
        """Run a scenario without external exchange or persistence side effects."""
        ...


@dataclass(frozen=True, slots=True)
class ScheduledMarketEvent:
    """One canonical market-data event scheduled for a scenario."""

    sequence: int
    scheduled_at: datetime
    event: ScenarioMarketEventPayload
    source_type: SimulationSourceType = SimulationSourceType.OBSERVED_FACT

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _validate_sequence(self.sequence))
        object.__setattr__(
            self,
            "scheduled_at",
            parse_utc_datetime(self.scheduled_at),
        )
        if not isinstance(self.event, OrderBookSnapshot | OrderBookDelta | Trade):
            msg = "event must be an OrderBookSnapshot, OrderBookDelta, or Trade"
            raise TypeError(msg)
        _validate_source_type(self.source_type)

    @property
    def event_type(self) -> str:
        """Return a stable market event type label."""

        return _market_event_type(self.event)

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible scheduled event data."""

        return {
            "event": to_canonical_data(self.event),
            "event_type": self.event_type,
            "scheduled_at": self.scheduled_at,
            "sequence": self.sequence,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class ScheduledOrderAction:
    """One order intent or cancel request scheduled for a scenario."""

    sequence: int
    scheduled_at: datetime
    action: ScenarioOrderActionPayload
    source_type: SimulationSourceType = SimulationSourceType.INFERRED_BEHAVIOR

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _validate_sequence(self.sequence))
        object.__setattr__(
            self,
            "scheduled_at",
            parse_utc_datetime(self.scheduled_at),
        )
        if not isinstance(self.action, OrderIntent | CancelOrderRequest):
            msg = "action must be an OrderIntent or CancelOrderRequest"
            raise TypeError(msg)
        _validate_source_type(self.source_type)

    @property
    def action_type(self) -> str:
        """Return a stable order action type label."""

        return _order_action_type(self.action)

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible scheduled action data."""

        return {
            "action": to_canonical_data(self.action),
            "action_type": self.action_type,
            "scheduled_at": self.scheduled_at,
            "sequence": self.sequence,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class ExpectedSimulationFill:
    """One canonical fill expected from a scenario run."""

    sequence: int
    fill: Fill
    source_type: SimulationSourceType = SimulationSourceType.SIMULATED_OUTPUT

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _validate_sequence(self.sequence))
        if not isinstance(self.fill, Fill):
            msg = "fill must be a canonical Fill"
            raise TypeError(msg)
        if self.source_type is not SimulationSourceType.SIMULATED_OUTPUT:
            raise SimulationConfigurationError(
                "Expected simulation fills must be classified as simulated output",
                reason_code="simulation_scenario_expected_fill_source_invalid",
                context={"source_type": str(self.source_type)},
            )

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible expected fill data."""

        return {
            "fill": to_canonical_data(self.fill),
            "sequence": self.sequence,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class SimulationScenario:
    """Immutable deterministic definition for one simulation scenario."""

    scenario_id: str
    name: str
    configuration: SimulationConfiguration
    initial_book: OrderBookSnapshot
    market_events: tuple[ScheduledMarketEvent, ...] = ()
    order_actions: tuple[ScheduledOrderAction, ...] = ()
    expected_fills: tuple[ExpectedSimulationFill, ...] = ()
    expected_final_book: OrderBookSnapshot | None = None
    expected_final_book_source_type: SimulationSourceType | None = None
    tags: tuple[str, ...] = ()
    metadata: Mapping[str, str] = field(default_factory=dict)

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "scenario_id",
            _validate_text(self.scenario_id, field_name="scenario_id"),
        )
        object.__setattr__(self, "name", _validate_text(self.name, field_name="name"))
        if not isinstance(self.configuration, SimulationConfiguration):
            raise SimulationConfigurationError(
                "Simulation scenario requires a canonical SimulationConfiguration",
                reason_code="simulation_scenario_configuration_invalid",
            )
        _validate_initial_book(self.initial_book)

        market_events = _normalize_market_events(self.market_events)
        order_actions = _normalize_order_actions(self.order_actions)
        expected_fills = _normalize_expected_fills(self.expected_fills)
        expected_final_book = _validate_expected_final_book(
            self.expected_final_book,
            initial_book=self.initial_book,
        )
        expected_final_book_source_type = _validate_expected_final_book_source_type(
            self.expected_final_book_source_type,
            expected_final_book=expected_final_book,
        )

        _validate_market_event_lineage(market_events, initial_book=self.initial_book)
        _validate_order_action_lineage(order_actions, initial_book=self.initial_book)
        _validate_expected_fill_lineage(expected_fills, initial_book=self.initial_book)

        object.__setattr__(self, "market_events", market_events)
        object.__setattr__(self, "order_actions", order_actions)
        object.__setattr__(self, "expected_fills", expected_fills)
        object.__setattr__(self, "expected_final_book", expected_final_book)
        object.__setattr__(
            self,
            "expected_final_book_source_type",
            expected_final_book_source_type,
        )
        object.__setattr__(self, "tags", _normalize_tags(self.tags))
        object.__setattr__(self, "metadata", _freeze_metadata(self.metadata))

    @property
    def configuration_hash(self) -> str:
        """Return the stable hash of the scenario configuration."""

        return canonical_sha256(self.configuration)

    @property
    def scenario_hash(self) -> str:
        """Return the deterministic hash of the scenario definition."""

        return canonical_sha256(self.canonical_payload())

    @property
    def source_type_counts(self) -> Mapping[SimulationSourceType, int]:
        """Return immutable counts of scenario inputs and outputs by source type."""

        counts: Counter[SimulationSourceType] = Counter({SimulationSourceType.OBSERVED_FACT: 1})
        counts.update(event.source_type for event in self.market_events)
        counts.update(action.source_type for action in self.order_actions)
        counts.update(fill.source_type for fill in self.expected_fills)
        if (
            self.expected_final_book is not None
            and self.expected_final_book_source_type is not None
        ):
            counts.update((self.expected_final_book_source_type,))
        return MappingProxyType(dict(counts))

    def as_result_artifact(self, *, sequence: int) -> SimulationArtifact:
        """Return this scenario as a simulation result artifact."""

        return SimulationArtifact(
            sequence=_validate_sequence(sequence),
            artifact_type="simulation_scenario",
            artifact_id=self.scenario_id,
            artifact_hash=self.scenario_hash,
            source_type=SimulationSourceType.INFERRED_BEHAVIOR,
        )

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible scenario data."""

        payload: dict[str, object] = {
            "configuration": to_canonical_data(self.configuration),
            "configuration_hash": self.configuration_hash,
            "expected_fills": [fill.canonical_payload() for fill in self.expected_fills],
            "hash_version": SIMULATION_SCENARIO_HASH_VERSION,
            "initial_book": to_canonical_data(self.initial_book),
            "market_events": [event.canonical_payload() for event in self.market_events],
            "metadata": dict(self.metadata),
            "name": self.name,
            "order_actions": [action.canonical_payload() for action in self.order_actions],
            "scenario_id": self.scenario_id,
            "tags": list(self.tags),
        }
        if self.expected_final_book is not None:
            payload["expected_final_book"] = to_canonical_data(self.expected_final_book)
            payload["expected_final_book_source_type"] = self.expected_final_book_source_type
        return payload


@dataclass(frozen=True, slots=True)
class SimulatedScenarioOrderResult:
    """One deterministic order-intent result produced by a scenario run."""

    sequence: int
    action: ScheduledOrderAction
    admission: SimulatedExchangeOrderAdmission
    activation_book: OrderBookSnapshot | None
    fill_estimate: FillEstimate | None
    fee_estimates: tuple[FeeEstimate, ...] = ()
    cancel_result: SimulatedScenarioCancelResult | None = None
    settlement_result: SimulatedScenarioSettlementResult | None = None
    source_type: SimulationSourceType = SimulationSourceType.SIMULATED_OUTPUT

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _validate_sequence(self.sequence))
        if not isinstance(self.action, ScheduledOrderAction):
            msg = "action must be a ScheduledOrderAction"
            raise TypeError(msg)
        if not isinstance(self.action.action, OrderIntent):
            raise SimulationConfigurationError(
                "Scenario order results require an order intent action",
                reason_code="simulation_scenario_order_result_action_invalid",
                context={"action_type": self.action.action_type},
            )
        if not isinstance(self.admission, SimulatedExchangeOrderAdmission):
            msg = "admission must be a SimulatedExchangeOrderAdmission"
            raise TypeError(msg)
        if self.activation_book is not None:
            _validate_initial_book(self.activation_book)
        if self.fill_estimate is not None and not isinstance(self.fill_estimate, FillEstimate):
            msg = "fill_estimate must be a FillEstimate"
            raise TypeError(msg)
        fee_estimates = _normalize_fee_estimates(self.fee_estimates)
        cancel_result = _validate_cancel_result(self.cancel_result)
        settlement_result = _validate_settlement_result(
            self.settlement_result,
            fill_estimate=self.fill_estimate,
            order_sequence=self.sequence,
        )
        if self.admission.rejected:
            if (
                self.activation_book is not None
                or self.fill_estimate is not None
                or fee_estimates
                or settlement_result is not None
            ):
                raise SimulationConfigurationError(
                    "Rejected scenario orders must not include simulated order outputs",
                    reason_code="simulation_scenario_rejected_order_output_invalid",
                )
            if cancel_result is not None:
                raise SimulationConfigurationError(
                    "Rejected scenario orders must not include cancellation outputs",
                    reason_code="simulation_scenario_rejected_order_cancel_invalid",
                )
        elif cancel_result is not None and cancel_result.before_activation:
            if (
                self.activation_book is not None
                or self.fill_estimate is not None
                or fee_estimates
                or settlement_result is not None
            ):
                raise SimulationConfigurationError(
                    "Pre-activation cancelled scenario orders must not include fill outputs",
                    reason_code="simulation_scenario_cancelled_order_output_invalid",
                )
        elif self.activation_book is None or self.fill_estimate is None:
            raise SimulationConfigurationError(
                "Accepted scenario orders require activation book and fill estimate outputs",
                reason_code="simulation_scenario_accepted_order_output_missing",
            )
        elif len(fee_estimates) != len(self.fill_estimate.components):
            raise SimulationConfigurationError(
                "Scenario order fee estimates must match fill components",
                reason_code="simulation_scenario_fee_component_count_mismatch",
                context={
                    "fee_estimate_count": str(len(fee_estimates)),
                    "fill_component_count": str(len(self.fill_estimate.components)),
                },
            )
        if self.source_type is not SimulationSourceType.SIMULATED_OUTPUT:
            raise SimulationConfigurationError(
                "Scenario order results must be classified as simulated output",
                reason_code="simulation_scenario_order_result_source_invalid",
                context={"source_type": str(self.source_type)},
            )
        object.__setattr__(self, "fee_estimates", fee_estimates)
        object.__setattr__(self, "cancel_result", cancel_result)
        object.__setattr__(self, "settlement_result", settlement_result)

    @property
    def order_result_hash(self) -> str:
        """Return the deterministic hash of this order result."""

        return canonical_sha256(self.canonical_payload())

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible simulated order-result data."""

        payload: dict[str, object] = {
            "action": self.action.canonical_payload(),
            "admission": self.admission.canonical_payload(),
            "runner_model": SIMULATION_SCENARIO_RUNNER_MODEL_NAME,
            "sequence": self.sequence,
            "source_type": self.source_type,
        }
        if self.activation_book is not None:
            payload["activation_book_hash"] = canonical_sha256(self.activation_book)
            payload["activation_book_sequence"] = self.activation_book.sequence
        if self.fill_estimate is not None:
            payload["fill_estimate"] = _fill_estimate_payload(self.fill_estimate)
        if self.fee_estimates:
            payload["fee_estimates"] = [
                _fee_estimate_payload(estimate) for estimate in self.fee_estimates
            ]
        if self.cancel_result is not None:
            payload["cancel_result"] = self.cancel_result.canonical_payload()
        if self.settlement_result is not None:
            payload["settlement_result"] = self.settlement_result.canonical_payload()
        return payload


@dataclass(frozen=True, slots=True)
class SimulatedScenarioCancelResult:
    """One deterministic cancellation result produced by a scenario run."""

    sequence: int
    action: ScheduledOrderAction
    target_order_sequence: int
    requested_at: datetime
    effective_at: datetime
    outcome_code: str
    source_type: SimulationSourceType = SimulationSourceType.SIMULATED_OUTPUT

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _validate_sequence(self.sequence))
        if not isinstance(self.action, ScheduledOrderAction):
            msg = "action must be a ScheduledOrderAction"
            raise TypeError(msg)
        if not isinstance(self.action.action, CancelOrderRequest):
            raise SimulationConfigurationError(
                "Scenario cancel results require a cancel request action",
                reason_code="simulation_scenario_cancel_result_action_invalid",
                context={"action_type": self.action.action_type},
            )
        object.__setattr__(
            self,
            "target_order_sequence",
            _validate_sequence(self.target_order_sequence),
        )
        object.__setattr__(self, "requested_at", parse_utc_datetime(self.requested_at))
        object.__setattr__(self, "effective_at", parse_utc_datetime(self.effective_at))
        if self.effective_at < self.requested_at:
            raise SimulationConfigurationError(
                "Scenario cancel effective_at must be at or after requested_at",
                reason_code="simulation_scenario_cancel_time_invalid",
            )
        object.__setattr__(self, "outcome_code", _validate_cancel_outcome(self.outcome_code))
        if self.source_type is not SimulationSourceType.SIMULATED_OUTPUT:
            raise SimulationConfigurationError(
                "Scenario cancel results must be classified as simulated output",
                reason_code="simulation_scenario_cancel_result_source_invalid",
                context={"source_type": str(self.source_type)},
            )

    @property
    def before_activation(self) -> bool:
        """Return whether this cancel prevented order activation."""

        return self.outcome_code == SIMULATION_CANCEL_BEFORE_ACTIVATION

    @property
    def cancel_result_hash(self) -> str:
        """Return the deterministic hash of this cancel result."""

        return canonical_sha256(self.canonical_payload())

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible simulated cancel-result data."""

        return {
            "action": self.action.canonical_payload(),
            "effective_at": self.effective_at,
            "outcome_code": self.outcome_code,
            "requested_at": self.requested_at,
            "runner_model": SIMULATION_SCENARIO_RUNNER_MODEL_NAME,
            "sequence": self.sequence,
            "source_type": self.source_type,
            "target_order_sequence": self.target_order_sequence,
        }


@dataclass(frozen=True, slots=True)
class SimulatedScenarioSettlementResult:
    """One deterministic settlement estimate produced by a scenario run."""

    sequence: int
    target_order_sequence: int
    estimate: SettlementEstimate
    source_type: SimulationSourceType = SimulationSourceType.SIMULATED_OUTPUT

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", _validate_sequence(self.sequence))
        object.__setattr__(
            self,
            "target_order_sequence",
            _validate_sequence(self.target_order_sequence),
        )
        if not isinstance(self.estimate, SettlementEstimate):
            msg = "estimate must be a SettlementEstimate"
            raise TypeError(msg)
        if self.source_type is not SimulationSourceType.SIMULATED_OUTPUT:
            raise SimulationConfigurationError(
                "Scenario settlement results must be classified as simulated output",
                reason_code="simulation_scenario_settlement_result_source_invalid",
                context={"source_type": str(self.source_type)},
            )

    @property
    def settlement_result_hash(self) -> str:
        """Return the deterministic hash of this settlement result."""

        return canonical_sha256(self.canonical_payload())

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible simulated settlement-result data."""

        return {
            "estimate": _settlement_estimate_payload(self.estimate),
            "runner_model": SIMULATION_SCENARIO_RUNNER_MODEL_NAME,
            "sequence": self.sequence,
            "source_type": self.source_type,
            "target_order_sequence": self.target_order_sequence,
        }


@dataclass(frozen=True, slots=True)
class SimulationScenarioRun:
    """Deterministic output of a complete simulation scenario run."""

    scenario: SimulationScenario
    final_book: OrderBookSnapshot
    order_results: tuple[SimulatedScenarioOrderResult, ...]
    result: SimulationResult
    source_type: SimulationSourceType = SimulationSourceType.SIMULATED_OUTPUT

    def __post_init__(self) -> None:
        if not isinstance(self.scenario, SimulationScenario):
            msg = "scenario must be a SimulationScenario"
            raise TypeError(msg)
        _validate_expected_final_book(self.final_book, initial_book=self.scenario.initial_book)
        order_results = _normalize_order_results(self.order_results)
        expected_result = _build_scenario_run_result(
            scenario=self.scenario,
            final_book=self.final_book,
            order_results=order_results,
        )
        if self.result != expected_result:
            raise SimulationConfigurationError(
                "Scenario run result must match deterministic runner output",
                reason_code="simulation_scenario_run_result_mismatch",
                context={
                    "expected_checksum": expected_result.result_checksum,
                    "actual_checksum": self.result.result_checksum,
                },
            )
        if self.source_type is not SimulationSourceType.SIMULATED_OUTPUT:
            raise SimulationConfigurationError(
                "Scenario runs must be classified as simulated output",
                reason_code="simulation_scenario_run_source_invalid",
                context={"source_type": str(self.source_type)},
            )
        object.__setattr__(self, "order_results", order_results)

    @property
    def run_hash(self) -> str:
        """Return the deterministic hash of this scenario run."""

        return canonical_sha256(self.canonical_payload())

    @property
    def result_checksum(self) -> str:
        """Return the deterministic simulation result checksum."""

        return self.result.result_checksum

    def canonical_payload(self) -> Mapping[str, object]:
        """Return stable JSON-compatible scenario-run data."""

        return {
            "final_book": to_canonical_data(self.final_book),
            "order_results": [result.canonical_payload() for result in self.order_results],
            "result": self.result.canonical_payload(),
            "runner_model": SIMULATION_SCENARIO_RUNNER_MODEL_NAME,
            "scenario_hash": self.scenario.scenario_hash,
            "scenario_id": self.scenario.scenario_id,
            "source_type": self.source_type,
        }


@dataclass(frozen=True, slots=True)
class DeterministicScenarioRunner:
    """Pure deterministic scenario runner composed from simulation models."""

    exchange: SimulatedExchange
    fill_model: FillModel
    fee_model: FeeModel | None = None
    settlement_model: SettlementModel | None = None
    market_status: MarketStatus = MarketStatus.OPEN

    def __post_init__(self) -> None:
        if not isinstance(self.exchange, SimulatedExchange):
            msg = "exchange must implement SimulatedExchange"
            raise TypeError(msg)
        if not isinstance(self.fill_model, FillModel):
            msg = "fill_model must implement FillModel"
            raise TypeError(msg)
        if self.fee_model is not None and not isinstance(self.fee_model, FeeModel):
            msg = "fee_model must implement FeeModel"
            raise TypeError(msg)
        if self.settlement_model is not None and not isinstance(
            self.settlement_model,
            SettlementModel,
        ):
            msg = "settlement_model must implement SettlementModel"
            raise TypeError(msg)
        if not isinstance(self.market_status, MarketStatus):
            raise SimulationConfigurationError(
                "Scenario runner market_status must be a canonical MarketStatus",
                reason_code="simulation_scenario_runner_market_status_invalid",
            )

    @classmethod
    def from_configuration(
        cls,
        configuration: SimulationConfiguration,
        *,
        market_status: MarketStatus = MarketStatus.OPEN,
    ) -> DeterministicScenarioRunner:
        """Build the deterministic default runner supported by M10 foundations."""

        _validate_runner_configuration(configuration)
        fill_model: FillModel
        if configuration.fill_model == TOUCH_FILL_MODEL_NAME:
            fill_model = TouchFillModel()
        else:
            fill_model = TradeThroughFillModel()
        return cls(
            exchange=DeterministicSimulatedExchange(
                rejection_model=BoundedRejectionModel(),
                latency_model=FixedLatencyModel.from_configuration(configuration),
            ),
            fill_model=fill_model,
            fee_model=None,
            settlement_model=None,
            market_status=market_status,
        )

    def run(self, scenario: SimulationScenario) -> SimulationScenarioRun:
        """Execute one scenario without live exchange, storage, or clock side effects."""

        scenario = _validate_scenario(scenario)
        _validate_runner_configuration(scenario.configuration)
        fee_model = _fee_model_for_scenario(scenario, fee_model=self.fee_model)
        settlement_model = _settlement_model_for_scenario(
            scenario,
            settlement_model=self.settlement_model,
        )
        winning_outcome_ids = _settlement_winning_outcome_ids_from_configuration(
            scenario.configuration
        )
        available_balance = _available_balance_from_configuration(scenario.configuration)
        final_book = _project_book_until(scenario=scenario, through=None)
        used_cancel_sequences: set[int] = set()
        order_results_list: list[SimulatedScenarioOrderResult] = []
        for index, action in enumerate(_order_intent_actions(scenario.order_actions)):
            cancel_action = _matching_cancel_action(
                scenario=scenario,
                action=action,
                used_cancel_sequences=used_cancel_sequences,
            )
            order_result = self._run_order_action(
                scenario=scenario,
                action=action,
                sequence=index,
                fee_model=fee_model,
                settlement_model=settlement_model,
                winning_outcome_ids=winning_outcome_ids,
                available_balance=available_balance,
                cancel_action=cancel_action,
            )
            if order_result.cancel_result is not None:
                used_cancel_sequences.add(order_result.cancel_result.sequence)
            order_results_list.append(order_result)
        _validate_no_unmatched_cancel_actions(
            scenario.order_actions,
            used_cancel_sequences=used_cancel_sequences,
        )
        order_results = tuple(order_results_list)
        result = _build_scenario_run_result(
            scenario=scenario,
            final_book=final_book,
            order_results=order_results,
        )
        return SimulationScenarioRun(
            scenario=scenario,
            final_book=final_book,
            order_results=order_results,
            result=result,
        )

    def _run_order_action(
        self,
        *,
        scenario: SimulationScenario,
        action: ScheduledOrderAction,
        sequence: int,
        fee_model: FeeModel,
        settlement_model: SettlementModel,
        winning_outcome_ids: tuple[OutcomeId, ...],
        available_balance: Decimal | None,
        cancel_action: ScheduledOrderAction | None,
    ) -> SimulatedScenarioOrderResult:
        if not isinstance(action.action, OrderIntent):
            raise SimulationConfigurationError(
                "Scenario runner order execution requires an order intent action",
                reason_code="simulation_scenario_order_action_invalid",
                context={"action_type": action.action_type},
            )
        intent = action.action
        admission = self.exchange.admit_order(
            intent=intent,
            market_status=self.market_status,
            submitted_at=action.scheduled_at,
            required_balance=_required_balance_for_intent(intent)
            if available_balance is not None
            else None,
            available_balance=available_balance,
        )
        if admission.rejected:
            return SimulatedScenarioOrderResult(
                sequence=sequence,
                action=action,
                admission=admission,
                activation_book=None,
                fill_estimate=None,
            )
        if admission.activates_at is None:
            raise SimulationConfigurationError(
                "Accepted scenario order is missing activation time",
                reason_code="simulation_scenario_activation_missing",
            )
        if cancel_action is not None and cancel_action.scheduled_at < admission.activates_at:
            return SimulatedScenarioOrderResult(
                sequence=sequence,
                action=action,
                admission=admission,
                activation_book=None,
                fill_estimate=None,
                cancel_result=_cancel_result(
                    action=cancel_action,
                    target_order_sequence=sequence,
                    outcome_code=SIMULATION_CANCEL_BEFORE_ACTIVATION,
                ),
            )
        if intent.limit_price is None:
            raise SimulationConfigurationError(
                "Accepted scenario order requires limit_price for deterministic fill",
                reason_code="simulation_scenario_fill_price_missing",
            )
        activation_book = _project_book_until(
            scenario=scenario,
            through=admission.activates_at,
        )
        if _post_only_would_cross(intent=intent, snapshot=activation_book):
            return SimulatedScenarioOrderResult(
                sequence=sequence,
                action=action,
                admission=_post_only_rejection_admission(admission),
                activation_book=None,
                fill_estimate=None,
            )
        fill_estimate = self.fill_model.evaluate(
            snapshot=activation_book,
            side=intent.side,
            limit_price=intent.limit_price,
            quantity=intent.quantity,
        )
        fee_estimates = _estimate_fees(
            fee_model=fee_model,
            exchange=scenario.initial_book.exchange,
            fill_estimate=fill_estimate,
        )
        cancel_result = (
            _cancel_result(
                action=cancel_action,
                target_order_sequence=sequence,
                outcome_code=(
                    SIMULATION_CANCEL_FILL_RACE_LOST
                    if fill_estimate.has_fill
                    else SIMULATION_CANCEL_AFTER_ACTIVATION_NO_FILL
                ),
            )
            if cancel_action is not None
            else None
        )
        settlement_result = _estimate_settlement(
            settlement_model=settlement_model,
            fill_estimate=fill_estimate,
            intent=intent,
            sequence=sequence,
            winning_outcome_ids=winning_outcome_ids,
        )
        return SimulatedScenarioOrderResult(
            sequence=sequence,
            action=action,
            admission=admission,
            activation_book=activation_book,
            fill_estimate=fill_estimate,
            fee_estimates=fee_estimates,
            cancel_result=cancel_result,
            settlement_result=settlement_result,
        )


def _market_event_type(event: ScenarioMarketEventPayload) -> str:
    if isinstance(event, OrderBookSnapshot):
        return "order_book_snapshot"
    if isinstance(event, OrderBookDelta):
        return "order_book_delta"
    return "trade"


def _order_action_type(action: ScenarioOrderActionPayload) -> str:
    if isinstance(action, OrderIntent):
        return "order_intent"
    return "cancel_order_request"


def _validate_sequence(sequence: int) -> int:
    if type(sequence) is not int:
        msg = "sequence must be an integer"
        raise TypeError(msg)
    if sequence < 0:
        msg = "sequence must be nonnegative"
        raise ValueError(msg)
    return sequence


def _validate_source_type(source_type: SimulationSourceType) -> None:
    if not isinstance(source_type, SimulationSourceType):
        msg = "source_type must be a SimulationSourceType"
        raise TypeError(msg)


def _validate_cancel_outcome(outcome_code: str) -> str:
    if type(outcome_code) is not str:
        msg = "outcome_code must be a string"
        raise TypeError(msg)
    if outcome_code not in _CANCEL_OUTCOME_CODES:
        raise SimulationConfigurationError(
            "Scenario cancel result outcome_code is unsupported",
            reason_code="simulation_scenario_cancel_result_outcome_invalid",
            context={"outcome_code": outcome_code},
        )
    return outcome_code


def _validate_cancel_result(
    cancel_result: SimulatedScenarioCancelResult | None,
) -> SimulatedScenarioCancelResult | None:
    if cancel_result is None:
        return None
    if not isinstance(cancel_result, SimulatedScenarioCancelResult):
        msg = "cancel_result must be a SimulatedScenarioCancelResult"
        raise TypeError(msg)
    return cancel_result


def _validate_settlement_result(
    settlement_result: SimulatedScenarioSettlementResult | None,
    *,
    fill_estimate: FillEstimate | None,
    order_sequence: int,
) -> SimulatedScenarioSettlementResult | None:
    if settlement_result is None:
        return None
    if not isinstance(settlement_result, SimulatedScenarioSettlementResult):
        msg = "settlement_result must be a SimulatedScenarioSettlementResult"
        raise TypeError(msg)
    if fill_estimate is None or not fill_estimate.has_fill:
        raise SimulationConfigurationError(
            "Scenario settlement results require a filled order",
            reason_code="simulation_scenario_settlement_without_fill_invalid",
        )
    if settlement_result.target_order_sequence != order_sequence:
        raise SimulationConfigurationError(
            "Scenario settlement result must reference its order result sequence",
            reason_code="simulation_scenario_settlement_order_sequence_mismatch",
            context={
                "settlement_order_sequence": str(settlement_result.target_order_sequence),
                "order_sequence": str(order_sequence),
            },
        )
    if settlement_result.estimate.quantity != fill_estimate.filled_quantity:
        raise SimulationConfigurationError(
            "Scenario settlement quantity must match filled quantity",
            reason_code="simulation_scenario_settlement_quantity_mismatch",
            context={
                "settlement_quantity": str(settlement_result.estimate.quantity),
                "filled_quantity": str(fill_estimate.filled_quantity),
            },
        )
    return settlement_result


def _validate_text(value: str, *, field_name: str, max_length: int = _MAX_TEXT_LENGTH) -> str:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    if len(value) > max_length:
        msg = f"{field_name} must be at most {max_length} characters"
        raise ValueError(msg)
    return value


def _validate_initial_book(initial_book: OrderBookSnapshot) -> None:
    if not isinstance(initial_book, OrderBookSnapshot):
        raise SimulationConfigurationError(
            "Simulation scenario initial_book must be an OrderBookSnapshot",
            reason_code="simulation_scenario_initial_book_invalid",
        )
    if not initial_book.is_valid:
        raise SimulationConfigurationError(
            "Simulation scenario initial_book must be valid",
            reason_code="simulation_scenario_initial_book_invalid",
            context={"market_id": str(initial_book.market_id)},
        )


def _validate_expected_final_book(
    expected_final_book: OrderBookSnapshot | None,
    *,
    initial_book: OrderBookSnapshot,
) -> OrderBookSnapshot | None:
    if expected_final_book is None:
        return None
    if not isinstance(expected_final_book, OrderBookSnapshot):
        raise SimulationConfigurationError(
            "Simulation scenario expected_final_book must be an OrderBookSnapshot",
            reason_code="simulation_scenario_expected_final_book_invalid",
        )
    if not expected_final_book.is_valid:
        raise SimulationConfigurationError(
            "Simulation scenario expected_final_book must be valid",
            reason_code="simulation_scenario_expected_final_book_invalid",
            context={"market_id": str(expected_final_book.market_id)},
        )
    _validate_book_lineage(
        expected_final_book,
        initial_book=initial_book,
        reason_code="simulation_scenario_expected_final_book_mismatch",
    )
    return expected_final_book


def _validate_expected_final_book_source_type(
    source_type: SimulationSourceType | None,
    *,
    expected_final_book: OrderBookSnapshot | None,
) -> SimulationSourceType | None:
    if expected_final_book is None:
        if source_type is not None:
            raise SimulationConfigurationError(
                "Expected final book source type requires expected_final_book",
                reason_code="simulation_scenario_expected_final_book_source_invalid",
                context={"source_type": str(source_type)},
            )
        return None
    if source_type is None:
        return SimulationSourceType.SIMULATED_OUTPUT
    if source_type is not SimulationSourceType.SIMULATED_OUTPUT:
        raise SimulationConfigurationError(
            "Expected final book must be classified as simulated output",
            reason_code="simulation_scenario_expected_final_book_source_invalid",
            context={"source_type": str(source_type)},
        )
    return source_type


def _normalize_market_events(
    events: tuple[ScheduledMarketEvent, ...],
) -> tuple[ScheduledMarketEvent, ...]:
    if not isinstance(events, tuple):
        msg = "market_events must be a tuple"
        raise TypeError(msg)
    if any(not isinstance(event, ScheduledMarketEvent) for event in events):
        msg = "market_events must contain only ScheduledMarketEvent values"
        raise TypeError(msg)
    return _sort_and_validate_unique_sequences(events, field_name="market_events")


def _normalize_order_actions(
    actions: tuple[ScheduledOrderAction, ...],
) -> tuple[ScheduledOrderAction, ...]:
    if not isinstance(actions, tuple):
        msg = "order_actions must be a tuple"
        raise TypeError(msg)
    if any(not isinstance(action, ScheduledOrderAction) for action in actions):
        msg = "order_actions must contain only ScheduledOrderAction values"
        raise TypeError(msg)
    return _sort_and_validate_unique_sequences(actions, field_name="order_actions")


def _normalize_expected_fills(
    fills: tuple[ExpectedSimulationFill, ...],
) -> tuple[ExpectedSimulationFill, ...]:
    if not isinstance(fills, tuple):
        msg = "expected_fills must be a tuple"
        raise TypeError(msg)
    if any(not isinstance(fill, ExpectedSimulationFill) for fill in fills):
        msg = "expected_fills must contain only ExpectedSimulationFill values"
        raise TypeError(msg)
    return _sort_and_validate_unique_sequences(fills, field_name="expected_fills")


def _sort_and_validate_unique_sequences[
    T: ScheduledMarketEvent | ScheduledOrderAction | ExpectedSimulationFill,
](items: tuple[T, ...], *, field_name: str) -> tuple[T, ...]:
    sorted_items = tuple(sorted(items, key=lambda item: item.sequence))
    sequences = [item.sequence for item in sorted_items]
    if len(set(sequences)) != len(sequences):
        raise SimulationConfigurationError(
            f"{field_name} must have unique sequences",
            reason_code="simulation_scenario_sequence_duplicate",
            context={"field_name": field_name},
        )
    return sorted_items


def _normalize_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    if not isinstance(tags, tuple):
        msg = "tags must be a tuple"
        raise TypeError(msg)
    normalized = tuple(
        sorted(_validate_text(tag, field_name="tag", max_length=_MAX_TEXT_LENGTH) for tag in tags)
    )
    if len(set(normalized)) != len(normalized):
        raise SimulationConfigurationError(
            "Simulation scenario tags must be unique",
            reason_code="simulation_scenario_tag_duplicate",
        )
    return normalized


def _freeze_metadata(metadata: Mapping[str, str]) -> Mapping[str, str]:
    if not isinstance(metadata, Mapping):
        msg = "metadata must be a mapping"
        raise TypeError(msg)
    frozen: dict[str, str] = {}
    for key, value in metadata.items():
        frozen[_validate_text(key, field_name="metadata key")] = _validate_text(
            value,
            field_name=f"metadata value for {key}",
        )
    return MappingProxyType(frozen)


def _validate_market_event_lineage(
    events: tuple[ScheduledMarketEvent, ...],
    *,
    initial_book: OrderBookSnapshot,
) -> None:
    for event in events:
        if isinstance(event.event, OrderBookSnapshot | OrderBookDelta):
            _validate_book_lineage(
                event.event,
                initial_book=initial_book,
                reason_code="simulation_scenario_market_event_mismatch",
            )
            continue
        _validate_trade_lineage(event.event, initial_book=initial_book)


def _validate_order_action_lineage(
    actions: tuple[ScheduledOrderAction, ...],
    *,
    initial_book: OrderBookSnapshot,
) -> None:
    for action in actions:
        if isinstance(action.action, OrderIntent):
            if (
                action.action.market_id != initial_book.market_id
                or action.action.contract_id != initial_book.contract_id
            ):
                raise SimulationConfigurationError(
                    "Simulation scenario order intent does not match initial book",
                    reason_code="simulation_scenario_order_action_mismatch",
                    context={"action_type": action.action_type},
                )
            continue
        if action.action.exchange != initial_book.exchange:
            raise SimulationConfigurationError(
                "Simulation scenario cancel request exchange does not match initial book",
                reason_code="simulation_scenario_order_action_mismatch",
                context={"action_type": action.action_type},
            )


def _validate_expected_fill_lineage(
    expected_fills: tuple[ExpectedSimulationFill, ...],
    *,
    initial_book: OrderBookSnapshot,
) -> None:
    for expected_fill in expected_fills:
        fill = expected_fill.fill
        if (
            fill.market_id != initial_book.market_id
            or fill.contract_id != initial_book.contract_id
            or fill.exchange != initial_book.exchange
        ):
            raise SimulationConfigurationError(
                "Simulation scenario expected fill does not match initial book",
                reason_code="simulation_scenario_expected_fill_mismatch",
                context={"fill_id": str(fill.fill_id)},
            )


def _validate_book_lineage(
    book: OrderBookSnapshot | OrderBookDelta,
    *,
    initial_book: OrderBookSnapshot,
    reason_code: str,
) -> None:
    if (
        book.market_id != initial_book.market_id
        or book.contract_id != initial_book.contract_id
        or book.exchange != initial_book.exchange
    ):
        raise SimulationConfigurationError(
            "Simulation scenario order-book lineage does not match initial book",
            reason_code=reason_code,
            context={"market_id": str(book.market_id), "contract_id": str(book.contract_id)},
        )


def _validate_trade_lineage(trade: Trade, *, initial_book: OrderBookSnapshot) -> None:
    if (
        trade.market_id != initial_book.market_id
        or trade.contract_id != initial_book.contract_id
        or trade.exchange != initial_book.exchange
    ):
        raise SimulationConfigurationError(
            "Simulation scenario trade lineage does not match initial book",
            reason_code="simulation_scenario_market_event_mismatch",
            context={"trade_id": trade.trade_id},
        )


def _validate_scenario(scenario: SimulationScenario) -> SimulationScenario:
    if not isinstance(scenario, SimulationScenario):
        raise SimulationConfigurationError(
            "Scenario runner requires a SimulationScenario",
            reason_code="simulation_scenario_runner_scenario_invalid",
        )
    return scenario


def _validate_runner_configuration(configuration: SimulationConfiguration) -> None:
    if not isinstance(configuration, SimulationConfiguration):
        raise SimulationConfigurationError(
            "Scenario runner requires a canonical SimulationConfiguration",
            reason_code="simulation_scenario_runner_configuration_invalid",
        )
    if configuration.fill_model not in {
        TOUCH_FILL_MODEL_NAME,
        TRADE_THROUGH_FILL_MODEL_NAME,
    }:
        raise SimulationConfigurationError(
            "Scenario runner does not support the configured fill model",
            reason_code="simulation_scenario_runner_fill_model_unsupported",
            context={"fill_model": configuration.fill_model},
        )
    if configuration.latency_model != FIXED_LATENCY_MODEL_NAME:
        raise SimulationConfigurationError(
            "Scenario runner currently supports fixed latency only",
            reason_code="simulation_scenario_runner_latency_model_unsupported",
            context={"latency_model": configuration.latency_model},
        )
    if configuration.rejection_model != BOUNDED_REJECTION_MODEL_NAME:
        raise SimulationConfigurationError(
            "Scenario runner currently supports bounded rejection only",
            reason_code="simulation_scenario_runner_rejection_model_unsupported",
            context={"rejection_model": configuration.rejection_model},
        )
    if configuration.fee_model != FEE_TABLE_MODEL_NAME:
        raise SimulationConfigurationError(
            "Scenario runner currently supports fee table fees only",
            reason_code="simulation_scenario_runner_fee_model_unsupported",
            context={"fee_model": configuration.fee_model},
        )
    if configuration.settlement_model not in {
        BINARY_SETTLEMENT_MODEL_NAME,
        NO_SETTLEMENT_MODEL_NAME,
    }:
        raise SimulationConfigurationError(
            "Scenario runner currently supports binary or no settlement only",
            reason_code="simulation_scenario_runner_settlement_model_unsupported",
            context={"settlement_model": configuration.settlement_model},
        )


def _project_book_until(
    *,
    scenario: SimulationScenario,
    through: datetime | None,
) -> OrderBookSnapshot:
    projected = scenario.initial_book
    through = parse_utc_datetime(through) if through is not None else None
    seen_event_hashes: set[str] = set()
    for event in scenario.market_events:
        if through is not None and event.scheduled_at > through:
            continue
        event_hash = _market_event_payload_hash(event)
        if event_hash in seen_event_hashes:
            continue
        seen_event_hashes.add(event_hash)
        projected = _apply_scheduled_market_event(projected, event)
    return projected


def _apply_scheduled_market_event(
    snapshot: OrderBookSnapshot,
    event: ScheduledMarketEvent,
) -> OrderBookSnapshot:
    if isinstance(event.event, OrderBookSnapshot):
        return event.event
    if isinstance(event.event, OrderBookDelta):
        return apply_order_book_delta(snapshot, event.event)
    return snapshot


def _normalize_order_results(
    order_results: tuple[SimulatedScenarioOrderResult, ...],
) -> tuple[SimulatedScenarioOrderResult, ...]:
    if not isinstance(order_results, tuple):
        msg = "order_results must be a tuple"
        raise TypeError(msg)
    if any(not isinstance(result, SimulatedScenarioOrderResult) for result in order_results):
        msg = "order_results must contain only SimulatedScenarioOrderResult values"
        raise TypeError(msg)
    sorted_results = tuple(sorted(order_results, key=lambda result: result.sequence))
    sequences = [result.sequence for result in sorted_results]
    if len(set(sequences)) != len(sequences):
        raise SimulationConfigurationError(
            "Scenario order results must have unique sequences",
            reason_code="simulation_scenario_order_result_sequence_duplicate",
        )
    return sorted_results


def _order_intent_actions(
    actions: tuple[ScheduledOrderAction, ...],
) -> tuple[ScheduledOrderAction, ...]:
    return tuple(action for action in actions if isinstance(action.action, OrderIntent))


def _cancel_request_actions(
    actions: tuple[ScheduledOrderAction, ...],
) -> tuple[ScheduledOrderAction, ...]:
    return tuple(action for action in actions if isinstance(action.action, CancelOrderRequest))


def _matching_cancel_action(
    *,
    scenario: SimulationScenario,
    action: ScheduledOrderAction,
    used_cancel_sequences: set[int],
) -> ScheduledOrderAction | None:
    if not isinstance(action.action, OrderIntent):
        return None
    candidates = [
        cancel_action
        for cancel_action in _cancel_request_actions(scenario.order_actions)
        if _cancel_matches_order_intent(
            cancel_action=cancel_action,
            action=action,
            exchange=scenario.initial_book.exchange,
            used_cancel_sequences=used_cancel_sequences,
        )
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: (candidate.scheduled_at, candidate.sequence))


def _cancel_matches_order_intent(
    *,
    cancel_action: ScheduledOrderAction,
    action: ScheduledOrderAction,
    exchange: str,
    used_cancel_sequences: set[int],
) -> bool:
    if cancel_action.sequence in used_cancel_sequences:
        return False
    if not isinstance(cancel_action.action, CancelOrderRequest):
        return False
    if not isinstance(action.action, OrderIntent):
        return False
    return (
        cancel_action.scheduled_at >= action.scheduled_at
        and cancel_action.action.exchange == exchange
        and cancel_action.action.correlation_id == action.action.correlation_id
    )


def _validate_no_unmatched_cancel_actions(
    actions: tuple[ScheduledOrderAction, ...],
    *,
    used_cancel_sequences: set[int],
) -> None:
    unmatched = [
        action
        for action in _cancel_request_actions(actions)
        if action.sequence not in used_cancel_sequences
    ]
    if not unmatched:
        return
    raise SimulationConfigurationError(
        "Scenario cancel action did not match an order intent",
        reason_code="simulation_scenario_cancel_unmatched",
        context={"cancel_sequence": str(unmatched[0].sequence)},
    )


def _normalize_fee_estimates(
    fee_estimates: tuple[FeeEstimate, ...],
) -> tuple[FeeEstimate, ...]:
    if not isinstance(fee_estimates, tuple):
        msg = "fee_estimates must be a tuple"
        raise TypeError(msg)
    if any(not isinstance(estimate, FeeEstimate) for estimate in fee_estimates):
        msg = "fee_estimates must contain only FeeEstimate values"
        raise TypeError(msg)
    return fee_estimates


def _cancel_result(
    *,
    action: ScheduledOrderAction,
    target_order_sequence: int,
    outcome_code: str,
) -> SimulatedScenarioCancelResult:
    return SimulatedScenarioCancelResult(
        sequence=action.sequence,
        action=action,
        target_order_sequence=target_order_sequence,
        requested_at=action.scheduled_at,
        effective_at=action.scheduled_at,
        outcome_code=outcome_code,
    )


def _build_scenario_run_result(
    *,
    scenario: SimulationScenario,
    final_book: OrderBookSnapshot,
    order_results: tuple[SimulatedScenarioOrderResult, ...],
) -> SimulationResult:
    order_results = _normalize_order_results(order_results)
    return SimulationResult.build(
        configuration=scenario.configuration,
        artifacts=_scenario_run_artifacts(
            scenario=scenario,
            final_book=final_book,
            order_results=order_results,
        ),
        metrics=_scenario_run_metrics(
            scenario=scenario,
            order_results=order_results,
        ),
    )


def _scenario_run_artifacts(
    *,
    scenario: SimulationScenario,
    final_book: OrderBookSnapshot,
    order_results: tuple[SimulatedScenarioOrderResult, ...],
) -> tuple[SimulationArtifact, ...]:
    artifacts: list[SimulationArtifact] = [
        scenario.as_result_artifact(sequence=0),
        SimulationArtifact(
            sequence=1,
            artifact_type="simulation_final_book",
            artifact_id=f"{scenario.scenario_id}:final_book",
            artifact_hash=canonical_sha256(final_book),
            source_type=SimulationSourceType.SIMULATED_OUTPUT,
        ),
    ]
    for index, order_result in enumerate(order_results):
        sequence_base = _ORDER_RESULT_ARTIFACT_BASE_SEQUENCE + index * _ORDER_RESULT_ARTIFACT_STRIDE
        artifacts.append(
            SimulationArtifact(
                sequence=sequence_base,
                artifact_type="simulation_order_result",
                artifact_id=f"{scenario.scenario_id}:order:{order_result.sequence}",
                artifact_hash=order_result.order_result_hash,
                source_type=SimulationSourceType.SIMULATED_OUTPUT,
            )
        )
        if order_result.fill_estimate is not None:
            artifacts.append(
                SimulationArtifact(
                    sequence=sequence_base + 1,
                    artifact_type="simulation_fill_estimate",
                    artifact_id=f"{scenario.scenario_id}:fill:{order_result.sequence}",
                    artifact_hash=canonical_sha256(
                        _fill_estimate_payload(order_result.fill_estimate)
                    ),
                    source_type=SimulationSourceType.SIMULATED_OUTPUT,
                )
            )
        if order_result.fee_estimates:
            artifacts.append(
                SimulationArtifact(
                    sequence=sequence_base + 2,
                    artifact_type="simulation_fee_estimates",
                    artifact_id=f"{scenario.scenario_id}:fees:{order_result.sequence}",
                    artifact_hash=canonical_sha256(
                        [_fee_estimate_payload(estimate) for estimate in order_result.fee_estimates]
                    ),
                    source_type=SimulationSourceType.SIMULATED_OUTPUT,
                )
            )
        if order_result.cancel_result is not None:
            artifacts.append(
                SimulationArtifact(
                    sequence=sequence_base + 3,
                    artifact_type="simulation_cancel_result",
                    artifact_id=f"{scenario.scenario_id}:cancel:{order_result.sequence}",
                    artifact_hash=order_result.cancel_result.cancel_result_hash,
                    source_type=SimulationSourceType.SIMULATED_OUTPUT,
                )
            )
        if order_result.settlement_result is not None:
            artifacts.append(
                SimulationArtifact(
                    sequence=sequence_base + 4,
                    artifact_type="simulation_settlement_result",
                    artifact_id=f"{scenario.scenario_id}:settlement:{order_result.sequence}",
                    artifact_hash=order_result.settlement_result.settlement_result_hash,
                    source_type=SimulationSourceType.SIMULATED_OUTPUT,
                )
            )
    return tuple(artifacts)


def _scenario_run_metrics(
    *,
    scenario: SimulationScenario,
    order_results: tuple[SimulatedScenarioOrderResult, ...],
) -> tuple[SimulationMetric, ...]:
    accepted_count = sum(1 for result in order_results if result.admission.accepted)
    rejected_count = sum(1 for result in order_results if result.admission.rejected)
    filled_order_count = sum(
        1
        for result in order_results
        if result.fill_estimate is not None and result.fill_estimate.has_fill
    )
    partial_fill_count = sum(
        1
        for result in order_results
        if result.fill_estimate is not None and result.fill_estimate.is_partial
    )
    cancel_action_count = sum(1 for result in order_results if result.cancel_result is not None)
    canceled_before_activation_count = sum(
        1
        for result in order_results
        if result.cancel_result is not None
        and result.cancel_result.outcome_code == SIMULATION_CANCEL_BEFORE_ACTIVATION
    )
    cancel_fill_race_count = sum(
        1
        for result in order_results
        if result.cancel_result is not None
        and result.cancel_result.outcome_code == SIMULATION_CANCEL_FILL_RACE_LOST
    )
    duplicate_market_event_count = _duplicate_market_event_count(scenario.market_events)
    projected_market_event_count = len(scenario.market_events) - duplicate_market_event_count
    settlement_estimate_count = sum(
        1 for result in order_results if result.settlement_result is not None
    )
    settled_winning_quantity = sum(
        (
            result.settlement_result.estimate.quantity
            for result in order_results
            if result.settlement_result is not None
            and result.settlement_result.estimate.is_winning_outcome
        ),
        _ZERO,
    )
    settled_payout_amount = sum(
        (
            result.settlement_result.estimate.payout_amount
            for result in order_results
            if result.settlement_result is not None
        ),
        _ZERO,
    )
    filled_quantity = sum(
        (
            result.fill_estimate.filled_quantity
            for result in order_results
            if result.fill_estimate is not None
        ),
        _ZERO,
    )
    fee_currency = _fee_metric_currency(scenario=scenario, order_results=order_results)
    total_fee_amount = _sum_fee_estimate_field(
        order_results,
        field_name="fee_amount",
    )
    total_filled_notional = _sum_fee_estimate_field(
        order_results,
        field_name="notional",
    )
    total_net_fee_amount = _sum_fee_estimate_field(
        order_results,
        field_name="net_fee_amount",
    )
    total_rebate_amount = _sum_fee_estimate_field(
        order_results,
        field_name="rebate_amount",
    )
    return (
        SimulationMetric(
            name="accepted_order_count",
            value=Decimal(accepted_count),
            unit="count",
        ),
        SimulationMetric(
            name="filled_order_count",
            value=Decimal(filled_order_count),
            unit="count",
        ),
        SimulationMetric(
            name="cancel_action_count",
            value=Decimal(cancel_action_count),
            unit="count",
        ),
        SimulationMetric(
            name="cancel_fill_race_count",
            value=Decimal(cancel_fill_race_count),
            unit="count",
        ),
        SimulationMetric(
            name="canceled_before_activation_count",
            value=Decimal(canceled_before_activation_count),
            unit="count",
        ),
        SimulationMetric(
            name="filled_quantity",
            value=parse_decimal(filled_quantity, field_name="filled_quantity metric"),
            unit="contracts",
        ),
        SimulationMetric(
            name="duplicate_market_event_count",
            value=Decimal(duplicate_market_event_count),
            unit="count",
        ),
        SimulationMetric(
            name="projected_market_event_count",
            value=Decimal(projected_market_event_count),
            unit="count",
        ),
        SimulationMetric(
            name="settled_payout_amount",
            value=parse_decimal(
                settled_payout_amount,
                field_name="settled_payout_amount metric",
            ),
            unit="payout_units",
        ),
        SimulationMetric(
            name="settled_winning_quantity",
            value=parse_decimal(
                settled_winning_quantity,
                field_name="settled_winning_quantity metric",
            ),
            unit="contracts",
        ),
        SimulationMetric(
            name="settlement_estimate_count",
            value=Decimal(settlement_estimate_count),
            unit="count",
        ),
        SimulationMetric(
            name="total_fee_amount",
            value=parse_decimal(total_fee_amount, field_name="total_fee_amount metric"),
            unit=fee_currency,
        ),
        SimulationMetric(
            name="total_filled_notional",
            value=parse_decimal(total_filled_notional, field_name="total_filled_notional metric"),
            unit=fee_currency,
        ),
        SimulationMetric(
            name="total_net_fee_amount",
            value=parse_decimal(total_net_fee_amount, field_name="total_net_fee_amount metric"),
            unit=fee_currency,
        ),
        SimulationMetric(
            name="total_rebate_amount",
            value=parse_decimal(total_rebate_amount, field_name="total_rebate_amount metric"),
            unit=fee_currency,
        ),
        SimulationMetric(
            name="market_event_count",
            value=Decimal(len(scenario.market_events)),
            unit="count",
        ),
        SimulationMetric(
            name="order_action_count",
            value=Decimal(len(scenario.order_actions)),
            unit="count",
        ),
        SimulationMetric(
            name="partial_fill_count",
            value=Decimal(partial_fill_count),
            unit="count",
        ),
        SimulationMetric(
            name="rejected_order_count",
            value=Decimal(rejected_count),
            unit="count",
        ),
    )


def _fill_estimate_payload(fill_estimate: FillEstimate) -> Mapping[str, object]:
    return {
        "average_fill_price": fill_estimate.average_fill_price,
        "components": [
            _fill_component_payload(component) for component in fill_estimate.components
        ],
        "filled_quantity": fill_estimate.filled_quantity,
        "limit_price": fill_estimate.limit_price,
        "liquidity_role": fill_estimate.liquidity_role,
        "order_quantity": fill_estimate.order_quantity,
        "reason_code": fill_estimate.reason_code,
        "remaining_quantity": fill_estimate.remaining_quantity,
        "side": fill_estimate.side,
    }


def _fill_component_payload(component: SimulatedFillComponent) -> Mapping[str, object]:
    return {
        "liquidity_role": component.liquidity_role,
        "price": component.price,
        "quantity": component.quantity,
    }


def _market_event_payload_hash(event: ScheduledMarketEvent) -> str:
    return canonical_sha256(event.event)


def _duplicate_market_event_count(events: tuple[ScheduledMarketEvent, ...]) -> int:
    seen: set[str] = set()
    duplicate_count = 0
    for event in events:
        event_hash = _market_event_payload_hash(event)
        if event_hash in seen:
            duplicate_count += 1
            continue
        seen.add(event_hash)
    return duplicate_count


def _fee_model_for_scenario(
    scenario: SimulationScenario,
    *,
    fee_model: FeeModel | None,
) -> FeeModel:
    if fee_model is not None:
        return fee_model
    return _fee_table_model_from_configuration(
        scenario.configuration,
        exchange=scenario.initial_book.exchange,
    )


def _settlement_model_for_scenario(
    scenario: SimulationScenario,
    *,
    settlement_model: SettlementModel | None,
) -> SettlementModel:
    if settlement_model is not None:
        return settlement_model
    try:
        if scenario.configuration.settlement_model == NO_SETTLEMENT_MODEL_NAME:
            return NoSettlementModel.from_configuration(scenario.configuration)
        return BinarySettlementModel.from_configuration(scenario.configuration)
    except (TypeError, ValueError) as exc:
        raise SimulationConfigurationError(
            "Scenario runner settlement configuration is invalid",
            reason_code="simulation_scenario_runner_settlement_configuration_invalid",
            context={"settlement_model": scenario.configuration.settlement_model},
        ) from exc


def _settlement_winning_outcome_ids_from_configuration(
    configuration: SimulationConfiguration,
) -> tuple[OutcomeId, ...]:
    raw_winners = configuration.parameters.get(_SETTLEMENT_WINNING_OUTCOME_IDS_PARAMETER)
    if raw_winners is None:
        return ()
    try:
        winner_tokens = tuple(raw_winners.split(","))
        if any(token == "" or token.strip() != token for token in winner_tokens):
            msg = "settlement winning outcome ids must be comma-separated canonical ids"
            raise ValueError(msg)
        winners = tuple(OutcomeId(token) for token in winner_tokens)
        if len(set(winners)) != len(winners):
            msg = "settlement winning outcome ids must be unique"
            raise ValueError(msg)
        if configuration.settlement_model == NO_SETTLEMENT_MODEL_NAME:
            msg = "no-settlement scenarios cannot configure winning outcomes"
            raise ValueError(msg)
        return winners
    except (TypeError, ValueError) as exc:
        raise SimulationConfigurationError(
            "Scenario runner settlement winning outcomes are invalid",
            reason_code="simulation_scenario_runner_settlement_winners_invalid",
            context={"settlement_model": configuration.settlement_model},
        ) from exc


def _estimate_settlement(
    *,
    settlement_model: SettlementModel,
    fill_estimate: FillEstimate,
    intent: OrderIntent,
    sequence: int,
    winning_outcome_ids: tuple[OutcomeId, ...],
) -> SimulatedScenarioSettlementResult | None:
    if not fill_estimate.has_fill:
        return None
    if not winning_outcome_ids and not isinstance(settlement_model, NoSettlementModel):
        return None
    estimate = settlement_model.estimate(
        outcome_id=intent.outcome_id,
        quantity=fill_estimate.filled_quantity,
        winning_outcome_ids=winning_outcome_ids,
    )
    return SimulatedScenarioSettlementResult(
        sequence=sequence,
        target_order_sequence=sequence,
        estimate=estimate,
    )


def _available_balance_from_configuration(
    configuration: SimulationConfiguration,
) -> Decimal | None:
    configured_balance = configuration.parameters.get(_AVAILABLE_BALANCE_PARAMETER)
    if configured_balance is None:
        return None
    try:
        available_balance = parse_decimal(
            configured_balance,
            field_name="simulation available balance",
        )
    except (TypeError, ValueError) as exc:
        raise SimulationConfigurationError(
            "Scenario runner balance configuration is invalid",
            reason_code="simulation_scenario_runner_balance_configuration_invalid",
        ) from exc
    if available_balance < _ZERO:
        raise SimulationConfigurationError(
            "Scenario runner balance configuration is invalid",
            reason_code="simulation_scenario_runner_balance_configuration_invalid",
        )
    return available_balance


def _required_balance_for_intent(intent: OrderIntent) -> Decimal | None:
    if intent.limit_price is None:
        return None
    if intent.limit_price < _ZERO or intent.limit_price > _ONE:
        return None
    exposure_price = intent.limit_price if intent.side is Side.BUY else _ONE - intent.limit_price
    return parse_decimal(
        exposure_price * intent.quantity,
        field_name="simulation required balance",
    )


def _post_only_would_cross(
    *,
    intent: OrderIntent,
    snapshot: OrderBookSnapshot,
) -> bool:
    if not intent.post_only or intent.limit_price is None:
        return False
    if intent.side is Side.BUY:
        ask = best_ask(snapshot)
        return ask is not None and ask.price <= intent.limit_price
    bid = best_bid(snapshot)
    return bid is not None and bid.price >= intent.limit_price


def _post_only_rejection_admission(
    admission: SimulatedExchangeOrderAdmission,
) -> SimulatedExchangeOrderAdmission:
    return SimulatedExchangeOrderAdmission(
        intent=admission.intent,
        market_status=admission.market_status,
        rejection_decision=RejectionDecision(
            accepted=False,
            reason_code=RejectionReason.POST_ONLY_WOULD_CROSS,
            reason_text="post-only order would cross at activation",
        ),
        submitted_at=admission.submitted_at,
        accepted_at=None,
        activates_at=None,
        required_balance=admission.required_balance,
        available_balance=admission.available_balance,
    )


def _fee_table_model_from_configuration(
    configuration: SimulationConfiguration,
    *,
    exchange: str,
) -> FeeTableModel:
    parameters = configuration.parameters
    currency = parameters.get(_FEE_CURRENCY_PARAMETER, _DEFAULT_FEE_CURRENCY)
    try:
        return FeeTableModel.from_rules(
            _fee_rule_from_parameters(
                exchange=exchange,
                liquidity_role=LiquidityRole.TAKER,
                currency=currency,
                parameters=parameters,
            ),
            _fee_rule_from_parameters(
                exchange=exchange,
                liquidity_role=LiquidityRole.MAKER,
                currency=currency,
                parameters=parameters,
            ),
            _fee_rule_from_parameters(
                exchange=exchange,
                liquidity_role=LiquidityRole.UNKNOWN,
                currency=currency,
                parameters=parameters,
            ),
        )
    except (TypeError, ValueError) as exc:
        raise SimulationConfigurationError(
            "Scenario runner fee configuration is invalid",
            reason_code="simulation_scenario_runner_fee_configuration_invalid",
            context={"fee_model": configuration.fee_model},
        ) from exc


def _fee_rule_from_parameters(
    *,
    exchange: str,
    liquidity_role: LiquidityRole,
    currency: str,
    parameters: Mapping[str, str],
) -> FeeRule:
    role = liquidity_role.value
    return FeeRule(
        exchange=exchange,
        liquidity_role=liquidity_role,
        currency=currency,
        fee_rate_bps=_fee_parameter_decimal(
            parameters,
            _FEE_RATE_BPS_PARAMETER.format(role=role),
        ),
        fixed_fee=_fee_parameter_decimal(
            parameters,
            _FEE_FIXED_PARAMETER.format(role=role),
        ),
        rebate_rate_bps=_fee_parameter_decimal(
            parameters,
            _FEE_REBATE_RATE_BPS_PARAMETER.format(role=role),
        ),
        fixed_rebate=_fee_parameter_decimal(
            parameters,
            _FEE_FIXED_REBATE_PARAMETER.format(role=role),
        ),
    )


def _fee_parameter_decimal(parameters: Mapping[str, str], key: str) -> Decimal:
    return parse_decimal(
        parameters.get(key, "0"),
        field_name=f"simulation fee parameter {key}",
    )


def _estimate_fees(
    *,
    fee_model: FeeModel,
    exchange: str,
    fill_estimate: FillEstimate,
) -> tuple[FeeEstimate, ...]:
    return tuple(
        fee_model.estimate(
            exchange=exchange,
            price=component.price,
            quantity=component.quantity,
            liquidity_role=component.liquidity_role,
        )
        for component in fill_estimate.components
    )


def _fee_metric_currency(
    *,
    scenario: SimulationScenario,
    order_results: tuple[SimulatedScenarioOrderResult, ...],
) -> str:
    for result in order_results:
        for estimate in result.fee_estimates:
            return estimate.currency
    fee_model = _fee_table_model_from_configuration(
        scenario.configuration,
        exchange=scenario.initial_book.exchange,
    )
    return fee_model.rules[0].currency


def _sum_fee_estimate_field(
    order_results: tuple[SimulatedScenarioOrderResult, ...],
    *,
    field_name: str,
) -> Decimal:
    if field_name == "fee_amount":
        return sum(
            (estimate.fee_amount for result in order_results for estimate in result.fee_estimates),
            _ZERO,
        )
    if field_name == "net_fee_amount":
        return sum(
            (
                estimate.net_fee_amount
                for result in order_results
                for estimate in result.fee_estimates
            ),
            _ZERO,
        )
    if field_name == "notional":
        return sum(
            (estimate.notional for result in order_results for estimate in result.fee_estimates),
            _ZERO,
        )
    if field_name == "rebate_amount":
        return sum(
            (
                estimate.rebate_amount
                for result in order_results
                for estimate in result.fee_estimates
            ),
            _ZERO,
        )
    msg = f"unsupported fee estimate field: {field_name}"
    raise ValueError(msg)


def _fee_estimate_payload(estimate: FeeEstimate) -> Mapping[str, object]:
    return {
        "currency": estimate.currency,
        "exchange": estimate.exchange,
        "fee_amount": estimate.fee_amount,
        "liquidity_role": estimate.liquidity_role,
        "net_fee_amount": estimate.net_fee_amount,
        "notional": estimate.notional,
        "rebate_amount": estimate.rebate_amount,
    }


def _settlement_estimate_payload(estimate: SettlementEstimate) -> Mapping[str, object]:
    return {
        "is_winning_outcome": estimate.is_winning_outcome,
        "outcome_id": estimate.outcome_id,
        "payout_amount": estimate.payout_amount,
        "payout_per_unit": estimate.payout_per_unit,
        "quantity": estimate.quantity,
        "status": estimate.status,
        "winning_outcome_ids": list(estimate.winning_outcome_ids),
    }
