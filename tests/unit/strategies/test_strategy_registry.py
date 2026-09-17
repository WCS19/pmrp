"""Strategy registry tests."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import model_validator

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.identifiers import StrategyId
from pmrp.schemas.numeric import Probability, Quantity
from pmrp.schemas.strategy import StrategyConfigurationRecord, StrategyDefinition
from pmrp.strategies import (
    MIDPOINT_OBSERVER_CONFIGURATION_SCHEMA_VERSION,
    MIDPOINT_OBSERVER_STRATEGY_TYPE,
    MIDPOINT_OBSERVER_STRATEGY_VERSION,
    THRESHOLD_SIGNAL_CONFIGURATION_SCHEMA_VERSION,
    THRESHOLD_SIGNAL_STRATEGY_TYPE,
    THRESHOLD_SIGNAL_STRATEGY_VERSION,
    MidpointObserverConfiguration,
    MidpointObserverStrategy,
    StrategyContext,
    StrategyRegistry,
    StrategyRegistryError,
    StrategyTypeRegistration,
    ThresholdSignalConfiguration,
    ThresholdSignalStrategy,
    UnknownStrategyTypeError,
    baseline_strategy_registrations,
    create_baseline_strategy_registry,
)

pytestmark = pytest.mark.unit


class ThresholdStrategyConfiguration(CanonicalModel):
    market_id: str
    minimum_probability: Probability
    max_quantity: Quantity


class RaisingStrategyConfiguration(CanonicalModel):
    market_id: str

    @model_validator(mode="before")
    @classmethod
    def reject_configuration(cls, value: object) -> object:
        del value
        raise TypeError("raw_sensitive_payload")


def test_strategy_registry_returns_registered_strategy_type_in_deterministic_order() -> None:
    first_registration = _registration(strategy_type="threshold_signal", version="1.0.0")
    second_registration = _registration(strategy_type="threshold_signal", version="1.1.0")
    registry = StrategyRegistry((second_registration, first_registration))

    assert registry.get("threshold_signal", "1.0.0") is first_registration
    assert registry.registrations() == (first_registration, second_registration)


def test_strategy_registry_rejects_duplicate_and_unknown_strategy_types() -> None:
    registration = _registration()
    registry = StrategyRegistry((registration,))

    with pytest.raises(ValueError, match="already registered"):
        registry.register(registration)

    with pytest.raises(UnknownStrategyTypeError, match="not registered"):
        registry.get("threshold_signal", "2.0.0")


def test_strategy_type_registration_requires_canonical_configuration_model() -> None:
    class MutableConfiguration:
        pass

    with pytest.raises(TypeError, match="CanonicalModel subclass"):
        StrategyTypeRegistration(
            definition=_definition(),
            factory=RecordingStrategyFactory(),
            configuration_model=MutableConfiguration,  # type: ignore[arg-type]
        )


def test_strategy_registry_validates_configuration_and_creates_strategy() -> None:
    factory = RecordingStrategyFactory()
    registry = StrategyRegistry((_registration(factory=factory),))
    configuration_record = _configuration_record(strategy_id=StrategyId("strat_registry_valid_v1"))

    strategy = registry.create_strategy(
        strategy_type="threshold_signal",
        strategy_version="1.0.0",
        configuration_record=configuration_record,
    )

    assert strategy.strategy_id == "strat_registry_valid_v1"
    assert strategy.strategy_type == "threshold_signal"
    assert strategy.strategy_version == "1.0.0"
    assert isinstance(factory.configuration, ThresholdStrategyConfiguration)
    assert factory.configuration.market_id == "mkt_registry_test"
    assert str(factory.configuration.minimum_probability.value) == "0.58"
    assert str(factory.configuration.max_quantity.value) == "10"


def test_strategy_registry_rejects_configuration_version_mismatch() -> None:
    registry = StrategyRegistry((_registration(),))

    with pytest.raises(StrategyRegistryError) as error:
        registry.create_strategy(
            strategy_type="threshold_signal",
            strategy_version="1.0.0",
            configuration_record=_configuration_record(configuration_version=2),
        )

    assert error.value.reason_code == "strategy_registry_configuration_version_mismatch"
    assert error.value.context["expected_configuration_schema_version"] == "1"
    assert error.value.context["configuration_version"] == "2"


def test_strategy_registry_rejects_invalid_configuration_without_leaking_values() -> None:
    registry = StrategyRegistry((_registration(),))

    with pytest.raises(StrategyRegistryError) as error:
        registry.create_strategy(
            strategy_type="threshold_signal",
            strategy_version="1.0.0",
            configuration_record=_configuration_record(
                configuration={
                    "market_id": "mkt_registry_test",
                    "minimum_probability": {"value": "0.58"},
                    "max_quantity": {"value": "10"},
                    "unexpected": "sensitive_payload_value",
                },
            ),
        )

    assert error.value.reason_code == "strategy_registry_configuration_invalid"
    assert error.value.context["error_count"] == "1"
    assert "sensitive_payload_value" not in str(error.value)
    assert "sensitive_payload_value" not in repr(error.value.context)


def test_strategy_registry_wraps_custom_configuration_validator_errors_safely() -> None:
    registry = StrategyRegistry((_registration(configuration_model=RaisingStrategyConfiguration),))

    with pytest.raises(StrategyRegistryError) as error:
        registry.create_strategy(
            strategy_type="threshold_signal",
            strategy_version="1.0.0",
            configuration_record=_configuration_record(),
        )

    assert error.value.reason_code == "strategy_registry_configuration_invalid"
    assert error.value.context["error_count"] == "unknown"
    assert "raw_sensitive_payload" not in str(error.value)
    assert error.value.__cause__ is None


def test_strategy_registry_wraps_factory_failure_safely() -> None:
    registry = StrategyRegistry((_registration(factory=RecordingStrategyFactory(fail=True)),))

    with pytest.raises(StrategyRegistryError) as error:
        registry.create_strategy(
            strategy_type="threshold_signal",
            strategy_version="1.0.0",
            configuration_record=_configuration_record(),
        )

    assert error.value.reason_code == "strategy_registry_factory_failed"
    assert "raw_sensitive_payload" not in str(error.value)
    assert error.value.__cause__ is None


def test_strategy_registry_rejects_invalid_or_mismatched_factory_results() -> None:
    invalid_registry = StrategyRegistry((_registration(factory=InvalidStrategyFactory()),))
    mismatch_registry = StrategyRegistry(
        (
            _registration(
                factory=RecordingStrategyFactory(strategy_type="other_strategy"),
            ),
        )
    )

    with pytest.raises(StrategyRegistryError) as invalid_error:
        invalid_registry.create_strategy(
            strategy_type="threshold_signal",
            strategy_version="1.0.0",
            configuration_record=_configuration_record(),
        )

    assert invalid_error.value.reason_code == "strategy_registry_strategy_invalid"

    with pytest.raises(StrategyRegistryError) as mismatch_error:
        mismatch_registry.create_strategy(
            strategy_type="threshold_signal",
            strategy_version="1.0.0",
            configuration_record=_configuration_record(),
        )

    assert mismatch_error.value.reason_code == "strategy_registry_strategy_mismatch"
    assert mismatch_error.value.context["strategy_instance_type"] == "other_strategy"

    schema_mismatch_registry = StrategyRegistry(
        (
            _registration(
                factory=RecordingStrategyFactory(configuration_schema_version=True),
            ),
        )
    )

    with pytest.raises(StrategyRegistryError) as schema_mismatch_error:
        schema_mismatch_registry.create_strategy(
            strategy_type="threshold_signal",
            strategy_version="1.0.0",
            configuration_record=_configuration_record(),
        )

    assert schema_mismatch_error.value.reason_code == "strategy_registry_strategy_mismatch"
    assert (
        schema_mismatch_error.value.context["strategy_instance_configuration_schema_version"]
        == "bool"
    )


def test_baseline_strategy_registrations_are_deterministic_and_schema_aligned() -> None:
    registrations = baseline_strategy_registrations()

    assert tuple(registration.strategy_type for registration in registrations) == (
        MIDPOINT_OBSERVER_STRATEGY_TYPE,
        THRESHOLD_SIGNAL_STRATEGY_TYPE,
    )
    midpoint_registration, threshold_registration = registrations
    assert midpoint_registration.strategy_version == MIDPOINT_OBSERVER_STRATEGY_VERSION
    assert (
        midpoint_registration.definition.configuration_schema_version
        == MIDPOINT_OBSERVER_CONFIGURATION_SCHEMA_VERSION
    )
    assert midpoint_registration.definition.implementation_path == (
        "pmrp.strategies.baseline:MidpointObserverStrategy"
    )
    assert midpoint_registration.definition.subscribed_event_types == (
        "market.order_book_snapshot",
    )
    assert midpoint_registration.configuration_model is MidpointObserverConfiguration
    assert not midpoint_registration.definition.supports_live

    assert threshold_registration.strategy_version == THRESHOLD_SIGNAL_STRATEGY_VERSION
    assert (
        threshold_registration.definition.configuration_schema_version
        == THRESHOLD_SIGNAL_CONFIGURATION_SCHEMA_VERSION
    )
    assert threshold_registration.definition.implementation_path == (
        "pmrp.strategies.baseline:ThresholdSignalStrategy"
    )
    assert threshold_registration.definition.subscribed_event_types == (
        "market.order_book_snapshot",
    )
    assert threshold_registration.configuration_model is ThresholdSignalConfiguration
    assert not threshold_registration.definition.supports_live


def test_create_baseline_strategy_registry_instantiates_midpoint_observer() -> None:
    registry = create_baseline_strategy_registry()

    strategy = registry.create_strategy(
        strategy_type=MIDPOINT_OBSERVER_STRATEGY_TYPE,
        strategy_version=MIDPOINT_OBSERVER_STRATEGY_VERSION,
        configuration_record=_configuration_record(
            strategy_id=StrategyId("strat_builtin_midpoint_registry"),
            configuration={"market_id": "mkt_registry_test", "metric_prefix": "custom.midpoint"},
        ),
    )

    assert isinstance(strategy, MidpointObserverStrategy)
    assert strategy.strategy_id == "strat_builtin_midpoint_registry"
    assert strategy.strategy_type == MIDPOINT_OBSERVER_STRATEGY_TYPE
    assert strategy.strategy_version == MIDPOINT_OBSERVER_STRATEGY_VERSION


def test_create_baseline_strategy_registry_instantiates_threshold_signal_strategy() -> None:
    registry = create_baseline_strategy_registry()

    strategy = registry.create_strategy(
        strategy_type=THRESHOLD_SIGNAL_STRATEGY_TYPE,
        strategy_version=THRESHOLD_SIGNAL_STRATEGY_VERSION,
        configuration_record=_configuration_record(
            strategy_id=StrategyId("strat_builtin_threshold_registry"),
            configuration={
                "market_id": "mkt_registry_test",
                "threshold_probability": "0.45",
                "confidence": "0.80",
                "signal_type": "custom_threshold",
            },
        ),
    )

    assert isinstance(strategy, ThresholdSignalStrategy)
    assert strategy.strategy_id == "strat_builtin_threshold_registry"
    assert strategy.strategy_type == THRESHOLD_SIGNAL_STRATEGY_TYPE
    assert strategy.strategy_version == THRESHOLD_SIGNAL_STRATEGY_VERSION


class RecordingStrategy:
    def __init__(
        self,
        *,
        strategy_id: StrategyId,
        strategy_type: str = "threshold_signal",
        strategy_version: str = "1.0.0",
        configuration_schema_version: object = 1,
        subscribed_event_types: tuple[str, ...] = ("market.snapshot",),
    ) -> None:
        self._strategy_id = strategy_id
        self._strategy_type = strategy_type
        self._strategy_version = strategy_version
        self._configuration_schema_version = configuration_schema_version
        self._subscribed_event_types = subscribed_event_types

    @property
    def strategy_id(self) -> StrategyId:
        return self._strategy_id

    @property
    def strategy_type(self) -> str:
        return self._strategy_type

    @property
    def strategy_version(self) -> str:
        return self._strategy_version

    @property
    def configuration_schema_version(self) -> object:
        return self._configuration_schema_version

    @property
    def subscribed_event_types(self) -> tuple[str, ...]:
        return self._subscribed_event_types

    async def initialize(self, context: StrategyContext) -> None:
        del context

    async def on_event(self, event: object) -> None:
        del event

    async def shutdown(self, reason: str) -> None:
        del reason


class RecordingStrategyFactory:
    def __init__(
        self,
        *,
        fail: bool = False,
        strategy_type: str = "threshold_signal",
        strategy_version: str = "1.0.0",
        configuration_schema_version: object = 1,
        subscribed_event_types: tuple[str, ...] = ("market.snapshot",),
    ) -> None:
        self._fail = fail
        self._strategy_type = strategy_type
        self._strategy_version = strategy_version
        self._configuration_schema_version = configuration_schema_version
        self._subscribed_event_types = subscribed_event_types
        self.configuration: object | None = None

    def create(
        self,
        *,
        strategy_id: StrategyId,
        configuration: object,
    ) -> RecordingStrategy:
        self.configuration = configuration
        if self._fail:
            raise RuntimeError("raw_sensitive_payload")
        return RecordingStrategy(
            strategy_id=strategy_id,
            strategy_type=self._strategy_type,
            strategy_version=self._strategy_version,
            configuration_schema_version=self._configuration_schema_version,
            subscribed_event_types=self._subscribed_event_types,
        )


class InvalidStrategyFactory:
    def create(self, *, strategy_id: StrategyId, configuration: object) -> object:
        del strategy_id, configuration
        return object()


def _registration(
    *,
    strategy_type: str = "threshold_signal",
    version: str = "1.0.0",
    factory: Any | None = None,
    configuration_model: type[CanonicalModel] = ThresholdStrategyConfiguration,
) -> StrategyTypeRegistration:
    return StrategyTypeRegistration(
        definition=_definition(strategy_type=strategy_type, version=version),
        factory=factory or RecordingStrategyFactory(),
        configuration_model=configuration_model,
    )


def _definition(
    *,
    strategy_type: str = "threshold_signal",
    version: str = "1.0.0",
) -> StrategyDefinition:
    return StrategyDefinition.model_validate(
        {
            "strategy_type": strategy_type,
            "version": version,
            "implementation_path": "pmrp.strategies.examples.threshold:ThresholdSignalStrategy",
            "description": "Transparent threshold strategy for registry validation.",
            "configuration_schema_version": 1,
            "subscribed_event_types": ("market.snapshot",),
            "supports_replay": True,
            "supports_simulation": True,
            "supports_paper": True,
            "supports_shadow": False,
            "supports_live": False,
        }
    )


def _configuration_record(**overrides: object) -> StrategyConfigurationRecord:
    payload: dict[str, object] = {
        "strategy_id": "strat_registry_valid_v1",
        "configuration_version": 1,
        "effective_at": "2026-07-27T15:00:00Z",
        "configuration": {
            "market_id": "mkt_registry_test",
            "minimum_probability": {"value": "0.58"},
            "max_quantity": {"value": "10"},
        },
        "configuration_hash": "sha256:strategy-registry-test",
        "created_by": "unit_test",
        "approved_by": None,
        "approval_required": False,
    }
    payload.update(overrides)
    return StrategyConfigurationRecord.model_validate(payload)
