"""Canonical strategy event schema tests."""

from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from pmrp.schemas.enums import Environment, HealthStatus, StrategyState
from pmrp.schemas.events import (
    STRATEGY_HEALTH_CHANGED_EVENT_TYPE,
    STRATEGY_SIGNAL_GENERATED_EVENT_TYPE,
    STRATEGY_STARTED_EVENT_TYPE,
    STRATEGY_STOPPED_EVENT_TYPE,
    SignalGeneratedEvent,
    StrategyHealthChangedEvent,
    StrategyStartedEvent,
    StrategyStoppedEvent,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.strategy import SignalDirection
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _envelope_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": "evt_strategy_event_test",
        "event_type": STRATEGY_STARTED_EVENT_TYPE,
        "schema_version": 1,
        "occurred_at": "2026-07-27T15:00:00Z",
        "received_at": "2026-07-27T15:00:00Z",
        "published_at": "2026-07-27T15:00:00Z",
        "producer": "strategy_runtime",
        "strategy_id": "strat_strategy_event_test_v1",
        "correlation_id": "corr_strategy_event_test",
    }
    payload.update(overrides)
    return payload


def _strategy_instance_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "strategy_id": "strat_strategy_event_test_v1",
        "strategy_type": "threshold_signal",
        "strategy_version": "1.0.0",
        "name": "Threshold signal research instance",
        "environment": Environment.TEST,
        "state": StrategyState.RUNNING,
        "configuration_version": 1,
        "configuration_hash": "sha256:strategy-configuration",
        "capital_allocation": None,
        "created_at": "2026-07-27T14:59:00Z",
        "started_at": "2026-07-27T15:00:00Z",
        "stopped_at": None,
        "health_status": HealthStatus.HEALTHY,
        "health_message": None,
    }
    payload.update(overrides)
    return payload


def _signal_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "signal_id": "sig_strategy_event_test",
        "strategy_id": "strat_strategy_event_test_v1",
        "market_id": "mkt_strategy_event_test",
        "signal_type": "threshold",
        "direction": SignalDirection.BUY,
        "strength": "0.75",
        "fair_probability": "0.58",
        "confidence": "0.80",
        "valid_from": "2026-07-27T15:00:00Z",
        "reason_code": "THRESHOLD_CROSSED",
        "correlation_id": "corr_strategy_event_test",
    }
    payload.update(overrides)
    return payload


def test_strategy_started_event_accepts_matching_envelope_and_instance() -> None:
    event = StrategyStartedEvent.model_validate(
        {
            "envelope": _envelope_payload(event_type=STRATEGY_STARTED_EVENT_TYPE),
            "strategy": _strategy_instance_payload(),
        }
    )

    assert event.envelope.event_type == "strategy.started"
    assert event.strategy.strategy_id == event.envelope.strategy_id


def test_strategy_stopped_event_accepts_matching_envelope_and_reason() -> None:
    event = StrategyStoppedEvent.model_validate(
        {
            "envelope": _envelope_payload(event_type=STRATEGY_STOPPED_EVENT_TYPE),
            "strategy_id": "strat_strategy_event_test_v1",
            "reason": "operator_stop",
        }
    )

    assert event.envelope.event_type == "strategy.stopped"
    assert event.strategy_id == event.envelope.strategy_id


def test_strategy_health_changed_event_requires_status_change() -> None:
    event = StrategyHealthChangedEvent.model_validate(
        {
            "envelope": _envelope_payload(event_type=STRATEGY_HEALTH_CHANGED_EVENT_TYPE),
            "strategy_id": "strat_strategy_event_test_v1",
            "previous_status": HealthStatus.HEALTHY,
            "current_status": HealthStatus.DEGRADED,
            "message": "event processing failed",
        }
    )

    assert event.previous_status is HealthStatus.HEALTHY
    assert event.current_status is HealthStatus.DEGRADED

    with pytest.raises(ValidationError, match="distinct statuses"):
        StrategyHealthChangedEvent.model_validate(
            {
                "envelope": _envelope_payload(event_type=STRATEGY_HEALTH_CHANGED_EVENT_TYPE),
                "strategy_id": "strat_strategy_event_test_v1",
                "previous_status": HealthStatus.HEALTHY,
                "current_status": HealthStatus.HEALTHY,
            }
        )


def test_signal_generated_event_accepts_matching_signal_lineage() -> None:
    event = SignalGeneratedEvent.model_validate(
        {
            "envelope": _envelope_payload(
                event_type=STRATEGY_SIGNAL_GENERATED_EVENT_TYPE,
                market_id="mkt_strategy_event_test",
            ),
            "signal": _signal_payload(),
        }
    )

    assert event.signal.strategy_id == event.envelope.strategy_id
    assert event.envelope.market_id == event.signal.market_id


def test_strategy_events_reject_unknown_fields_wrong_type_and_missing_lineage() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        StrategyStoppedEvent.model_validate(
            {
                "envelope": _envelope_payload(event_type=STRATEGY_STOPPED_EVENT_TYPE),
                "strategy_id": "strat_strategy_event_test_v1",
                "reason": "operator_stop",
                "unexpected": True,
            }
        )

    with pytest.raises(ValidationError, match="event envelope event_type must be"):
        StrategyStartedEvent.model_validate(
            {
                "envelope": _envelope_payload(event_type=STRATEGY_STOPPED_EVENT_TYPE),
                "strategy": _strategy_instance_payload(),
            }
        )

    with pytest.raises(ValidationError, match="event envelope strategy_id is required"):
        StrategyStartedEvent.model_validate(
            {
                "envelope": _envelope_payload(
                    event_type=STRATEGY_STARTED_EVENT_TYPE,
                    strategy_id=None,
                ),
                "strategy": _strategy_instance_payload(),
            }
        )

    with pytest.raises(ValidationError, match="event envelope strategy_id must match"):
        StrategyStoppedEvent.model_validate(
            {
                "envelope": _envelope_payload(event_type=STRATEGY_STOPPED_EVENT_TYPE),
                "strategy_id": "strat_other_strategy_event_test_v1",
                "reason": "operator_stop",
            }
        )


def test_signal_generated_event_rejects_market_lineage_mismatch() -> None:
    with pytest.raises(ValidationError, match="market_id must match"):
        SignalGeneratedEvent.model_validate(
            {
                "envelope": _envelope_payload(
                    event_type=STRATEGY_SIGNAL_GENERATED_EVENT_TYPE,
                    market_id="mkt_other_strategy_event_test",
                ),
                "signal": _signal_payload(),
            }
        )


def test_strategy_event_json_round_trip_hash_and_registry_entries() -> None:
    event = StrategyStartedEvent.model_validate(
        {
            "envelope": _envelope_payload(event_type=STRATEGY_STARTED_EVENT_TYPE),
            "strategy": _strategy_instance_payload(),
        }
    )
    canonical = canonical_json(event)

    assert StrategyStartedEvent.model_validate_json(canonical) == event
    assert canonical_sha256(event) == canonical_sha256(
        StrategyStartedEvent.model_validate_json(canonical)
    )
    assert json.loads(canonical)["envelope"]["event_type"] == STRATEGY_STARTED_EVENT_TYPE
    assert get_schema_model("strategy_started_event", 1) is StrategyStartedEvent
    assert get_schema_model("strategy_stopped_event", 1) is StrategyStoppedEvent
    assert get_schema_model("strategy_health_changed_event", 1) is StrategyHealthChangedEvent
    assert get_schema_model("signal_generated_event", 1) is SignalGeneratedEvent
    assert (
        get_schema_registration("strategy_started_event", 1).model_path
        == "pmrp.schemas.events.StrategyStartedEvent"
    )
