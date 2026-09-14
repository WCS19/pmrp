"""Strategy metadata schema tests."""

from __future__ import annotations

import json
from datetime import datetime
from decimal import Decimal
from typing import Any, cast

import pytest
from pydantic import ValidationError

from pmrp.schemas.enums import Environment, HealthStatus, StrategyState
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.strategy import (
    StrategyConfigurationRecord,
    StrategyDefinition,
    StrategyInstance,
)
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _strategy_definition_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "strategy_type": "threshold_signal",
        "version": "1.0.0",
        "implementation_path": "pmrp.strategies.examples.threshold:ThresholdSignalStrategy",
        "description": "Transparent threshold strategy for runtime validation.",
        "configuration_schema_version": 1,
        "subscribed_event_types": ("market.order_book_snapshot", "market.trade_observed"),
        "supports_replay": True,
        "supports_simulation": True,
        "supports_paper": True,
        "supports_shadow": False,
        "supports_live": False,
    }
    payload.update(overrides)
    return payload


def _strategy_instance_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "strategy_id": "strat_threshold_signal_v1",
        "strategy_type": "threshold_signal",
        "strategy_version": "1.0.0",
        "name": "Threshold signal research instance",
        "environment": Environment.TEST,
        "state": StrategyState.RUNNING,
        "configuration_version": 1,
        "configuration_hash": "sha256:strategy-configuration",
        "capital_allocation": {"amount": "1000.00", "currency": "USD"},
        "created_at": "2026-07-27T14:59:00Z",
        "started_at": "2026-07-27T15:00:00Z",
        "stopped_at": None,
        "health_status": HealthStatus.HEALTHY,
        "health_message": None,
    }
    payload.update(overrides)
    return payload


def _configuration_record_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "strategy_id": "strat_threshold_signal_v1",
        "configuration_version": 1,
        "effective_at": "2026-07-27T15:00:00Z",
        "configuration": {
            "market_id": "mkt_threshold_test",
            "min_confidence": "0.75",
            "window_seconds": 30,
            "enabled": True,
        },
        "configuration_hash": "sha256:strategy-configuration",
        "created_by": "unit_test",
        "approved_by": None,
        "approval_required": False,
    }
    payload.update(overrides)
    return payload


def test_strategy_definition_accepts_valid_payload() -> None:
    definition = StrategyDefinition.model_validate(_strategy_definition_payload())

    assert definition.strategy_type == "threshold_signal"
    assert definition.configuration_schema_version == 1
    assert definition.subscribed_event_types == (
        "market.order_book_snapshot",
        "market.trade_observed",
    )
    assert definition.supports_replay is True
    assert definition.supports_live is False


def test_strategy_definition_rejects_unknown_fields_and_invalid_values() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StrategyDefinition.model_validate(_strategy_definition_payload(unexpected=True))

    with pytest.raises(ValidationError, match="String should match pattern"):
        StrategyDefinition.model_validate(_strategy_definition_payload(implementation_path="bad"))

    with pytest.raises(ValidationError, match="subscribed_event_types must not be empty"):
        StrategyDefinition.model_validate(_strategy_definition_payload(subscribed_event_types=()))

    with pytest.raises(ValidationError, match="unique event types"):
        StrategyDefinition.model_validate(
            _strategy_definition_payload(
                subscribed_event_types=("market.snapshot", "market.snapshot")
            )
        )

    with pytest.raises(ValidationError, match="Input should be a valid boolean"):
        StrategyDefinition.model_validate(_strategy_definition_payload(supports_live=cast(Any, 1)))


def test_strategy_instance_accepts_running_payload_and_exact_money() -> None:
    instance = StrategyInstance.model_validate(_strategy_instance_payload())

    assert instance.strategy_id == "strat_threshold_signal_v1"
    assert instance.environment is Environment.TEST
    assert instance.state is StrategyState.RUNNING
    assert instance.capital_allocation is not None
    assert instance.capital_allocation.amount == Decimal("1000.00")
    assert instance.health_status is HealthStatus.HEALTHY


def test_strategy_instance_accepts_created_and_stopped_lifecycle_shapes() -> None:
    created = StrategyInstance.model_validate(
        _strategy_instance_payload(
            state=StrategyState.CREATED,
            started_at=None,
            stopped_at=None,
            health_status=HealthStatus.UNKNOWN,
            capital_allocation=None,
        )
    )
    stopped = StrategyInstance.model_validate(
        _strategy_instance_payload(
            state=StrategyState.STOPPED,
            stopped_at="2026-07-27T16:00:00Z",
            health_status=HealthStatus.UNKNOWN,
        )
    )

    assert created.started_at is None
    assert stopped.stopped_at is not None


def test_strategy_instance_rejects_invalid_lifecycle_timestamps() -> None:
    with pytest.raises(ValidationError, match="active strategy instance requires started_at"):
        StrategyInstance.model_validate(_strategy_instance_payload(started_at=None))

    with pytest.raises(ValidationError, match="active strategy instance cannot contain stopped_at"):
        StrategyInstance.model_validate(
            _strategy_instance_payload(stopped_at="2026-07-27T16:00:00Z")
        )

    with pytest.raises(ValidationError, match="terminal strategy instance requires stopped_at"):
        StrategyInstance.model_validate(
            _strategy_instance_payload(state=StrategyState.STOPPED, stopped_at=None)
        )

    with pytest.raises(ValidationError, match="started_at must not be before created_at"):
        StrategyInstance.model_validate(
            _strategy_instance_payload(started_at="2026-07-27T14:00:00Z")
        )

    with pytest.raises(ValidationError, match="timezone-aware"):
        StrategyInstance.model_validate(
            _strategy_instance_payload(created_at=datetime.fromisoformat("2026-07-27T14:59:00"))
        )


def test_strategy_configuration_record_freezes_configuration_and_rejects_floats() -> None:
    record = StrategyConfigurationRecord.model_validate(_configuration_record_payload())
    original_hash = canonical_sha256(record)
    nested_configuration = record.configuration

    with pytest.raises(TypeError, match="does not support item assignment"):
        cast(Any, nested_configuration)["window_seconds"] = 60
    with pytest.raises(TypeError, match="must not contain floats"):
        StrategyConfigurationRecord.model_validate(
            _configuration_record_payload(configuration={"min_confidence": 0.75})
        )

    assert canonical_sha256(record) == original_hash


def test_strategy_configuration_record_json_round_trip_and_registry_entries() -> None:
    record = StrategyConfigurationRecord.model_validate(_configuration_record_payload())
    canonical = canonical_json(record)

    assert StrategyConfigurationRecord.model_validate_json(canonical) == record
    assert json.loads(canonical)["configuration"]["min_confidence"] == "0.75"
    assert get_schema_model("strategy_definition", 1) is StrategyDefinition
    assert get_schema_model("strategy_instance", 1) is StrategyInstance
    assert get_schema_model("strategy_configuration_record", 1) is StrategyConfigurationRecord
    assert (
        get_schema_registration("strategy_instance", 1).model_path
        == "pmrp.schemas.strategy.StrategyInstance"
    )
