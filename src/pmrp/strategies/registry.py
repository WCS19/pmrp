"""Strategy type registry and configuration validation."""

from __future__ import annotations

from dataclasses import dataclass
from typing import NoReturn

from pydantic import ValidationError

from pmrp.schemas.base import CanonicalModel
from pmrp.schemas.identifiers import StrategyId
from pmrp.schemas.immutability import thaw_canonical_mapping
from pmrp.schemas.strategy import StrategyConfigurationRecord, StrategyDefinition
from pmrp.strategies.errors import StrategyRegistryError
from pmrp.strategies.protocol import Strategy, StrategyFactory


class UnknownStrategyTypeError(KeyError):
    """Raised when a strategy type and version have no registration."""


type StrategyConfigurationModel = type[CanonicalModel]


@dataclass(frozen=True, slots=True)
class StrategyTypeRegistration:
    """Registered strategy implementation with its typed configuration schema."""

    definition: StrategyDefinition
    factory: StrategyFactory
    configuration_model: StrategyConfigurationModel

    def __post_init__(self) -> None:
        if not isinstance(self.definition, StrategyDefinition):
            msg = "definition must be a StrategyDefinition"
            raise TypeError(msg)
        if not callable(getattr(self.factory, "create", None)):
            msg = "factory must expose a callable create method"
            raise TypeError(msg)
        if not isinstance(self.configuration_model, type) or not issubclass(
            self.configuration_model, CanonicalModel
        ):
            msg = "configuration_model must be a CanonicalModel subclass"
            raise TypeError(msg)

    @property
    def strategy_type(self) -> str:
        """Return the registered strategy type key."""

        return self.definition.strategy_type

    @property
    def strategy_version(self) -> str:
        """Return the registered strategy implementation version."""

        return self.definition.version

    def validate_configuration(
        self,
        configuration_record: StrategyConfigurationRecord,
    ) -> CanonicalModel:
        """Validate a persisted configuration record with the registered schema."""

        _validate_configuration_version(self, configuration_record)
        try:
            return self.configuration_model.model_validate(
                thaw_canonical_mapping(configuration_record.configuration)
            )
        except ValidationError as exc:
            self._raise_configuration_validation_error(
                configuration_record,
                error_count=str(len(exc.errors(include_input=False))),
            )
        except Exception:
            self._raise_configuration_validation_error(
                configuration_record,
                error_count="unknown",
            )

    def _raise_configuration_validation_error(
        self,
        configuration_record: StrategyConfigurationRecord,
        *,
        error_count: str,
    ) -> NoReturn:
        raise StrategyRegistryError(
            "Strategy configuration validation failed",
            reason_code="strategy_registry_configuration_invalid",
            context={
                "strategy_type": self.strategy_type,
                "strategy_version": self.strategy_version,
                "strategy_id": str(configuration_record.strategy_id),
                "error_count": error_count,
            },
        ) from None


class StrategyRegistry:
    """In-memory registry for constructing validated strategy instances."""

    def __init__(self, registrations: tuple[StrategyTypeRegistration, ...] = ()) -> None:
        self._registrations: dict[tuple[str, str], StrategyTypeRegistration] = {}
        for registration in registrations:
            self.register(registration)

    def register(self, registration: StrategyTypeRegistration) -> None:
        """Register one strategy type and implementation version."""

        key = _registration_key(registration.strategy_type, registration.strategy_version)
        if key in self._registrations:
            msg = (
                "strategy type and version are already registered: "
                f"{registration.strategy_type} {registration.strategy_version}"
            )
            raise ValueError(msg)
        self._registrations[key] = registration

    def get(self, strategy_type: str, strategy_version: str) -> StrategyTypeRegistration:
        """Return a registered strategy type/version pair."""

        key = _registration_key(strategy_type, strategy_version)
        try:
            return self._registrations[key]
        except KeyError as exc:
            msg = f"strategy type is not registered: {strategy_type} {strategy_version}"
            raise UnknownStrategyTypeError(msg) from exc

    def create_strategy(
        self,
        *,
        strategy_type: str,
        strategy_version: str,
        configuration_record: StrategyConfigurationRecord,
    ) -> Strategy:
        """Instantiate a strategy from a typed and versioned configuration record."""

        registration = self.get(strategy_type, strategy_version)
        configuration = registration.validate_configuration(configuration_record)
        strategy = _create_strategy(registration, configuration_record.strategy_id, configuration)
        _validate_created_strategy(
            strategy,
            registration=registration,
            configuration_record=configuration_record,
        )
        return strategy

    def registrations(self) -> tuple[StrategyTypeRegistration, ...]:
        """Return registered strategy definitions in deterministic order."""

        return tuple(
            self._registrations[key]
            for key in sorted(self._registrations, key=lambda item: (item[0], item[1]))
        )


def _create_strategy(
    registration: StrategyTypeRegistration,
    strategy_id: StrategyId,
    configuration: CanonicalModel,
) -> Strategy:
    try:
        return registration.factory.create(
            strategy_id=strategy_id,
            configuration=configuration,
        )
    except Exception:
        raise StrategyRegistryError(
            "Strategy factory failed",
            reason_code="strategy_registry_factory_failed",
            context={
                "strategy_type": registration.strategy_type,
                "strategy_version": registration.strategy_version,
                "strategy_id": str(strategy_id),
            },
        ) from None


def _validate_created_strategy(
    strategy: object,
    *,
    registration: StrategyTypeRegistration,
    configuration_record: StrategyConfigurationRecord,
) -> None:
    if not isinstance(strategy, Strategy):
        raise StrategyRegistryError(
            "Strategy factory returned an invalid strategy instance",
            reason_code="strategy_registry_strategy_invalid",
            context={
                "strategy_type": registration.strategy_type,
                "strategy_version": registration.strategy_version,
                "strategy_id": str(configuration_record.strategy_id),
            },
        )

    mismatches: dict[str, str] = {}
    if strategy.strategy_id != configuration_record.strategy_id:
        mismatches["strategy_instance_id"] = str(strategy.strategy_id)
    if type(strategy.strategy_type) is not str:
        mismatches["strategy_instance_type"] = type(strategy.strategy_type).__name__
    elif strategy.strategy_type != registration.definition.strategy_type:
        mismatches["strategy_instance_type"] = strategy.strategy_type
    if type(strategy.strategy_version) is not str:
        mismatches["strategy_instance_version"] = type(strategy.strategy_version).__name__
    elif strategy.strategy_version != registration.definition.version:
        mismatches["strategy_instance_version"] = strategy.strategy_version

    configuration_schema_version = strategy.configuration_schema_version
    if type(configuration_schema_version) is not int:
        mismatches["strategy_instance_configuration_schema_version"] = type(
            configuration_schema_version
        ).__name__
    elif configuration_schema_version != registration.definition.configuration_schema_version:
        mismatches["strategy_instance_configuration_schema_version"] = str(
            configuration_schema_version
        )

    subscribed_event_types = strategy.subscribed_event_types
    if not isinstance(subscribed_event_types, tuple) or any(
        type(event_type) is not str for event_type in subscribed_event_types
    ):
        mismatches["strategy_instance_subscriptions"] = "invalid"
    elif subscribed_event_types != registration.definition.subscribed_event_types:
        mismatches["strategy_instance_subscriptions"] = ",".join(subscribed_event_types)

    if mismatches:
        mismatches.update(
            {
                "strategy_type": registration.strategy_type,
                "strategy_version": registration.strategy_version,
                "strategy_id": str(configuration_record.strategy_id),
            }
        )
        raise StrategyRegistryError(
            "Strategy factory returned an instance that does not match its registration",
            reason_code="strategy_registry_strategy_mismatch",
            context=mismatches,
        )


def _validate_configuration_version(
    registration: StrategyTypeRegistration,
    configuration_record: StrategyConfigurationRecord,
) -> None:
    if (
        configuration_record.configuration_version
        == registration.definition.configuration_schema_version
    ):
        return
    raise StrategyRegistryError(
        "Strategy configuration schema version does not match the registration",
        reason_code="strategy_registry_configuration_version_mismatch",
        context={
            "strategy_type": registration.strategy_type,
            "strategy_version": registration.strategy_version,
            "strategy_id": str(configuration_record.strategy_id),
            "expected_configuration_schema_version": str(
                registration.definition.configuration_schema_version
            ),
            "configuration_version": str(configuration_record.configuration_version),
        },
    )


def _registration_key(strategy_type: str, strategy_version: str) -> tuple[str, str]:
    _validate_required_text(strategy_type, field_name="strategy_type")
    _validate_required_text(strategy_version, field_name="strategy_version")
    return strategy_type, strategy_version


def _validate_required_text(value: str, *, field_name: str) -> None:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
