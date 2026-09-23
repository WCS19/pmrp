import json
from collections.abc import Mapping
from datetime import datetime

import pytest
from pydantic import ValidationError

from pmrp.schemas.enums import DataQualityFlag, OrderType, RiskDecisionStatus, Side, TimeInForce
from pmrp.schemas.events import (
    RISK_APPROVED_EVENT_TYPE,
    RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE,
    RISK_KILL_SWITCH_RELEASED_EVENT_TYPE,
    RISK_LIMIT_BREACHED_EVENT_TYPE,
    RISK_REJECTED_EVENT_TYPE,
    EventEnvelope,
    KillSwitchActivatedEvent,
    KillSwitchReleasedEvent,
    RiskApprovedEvent,
    RiskLimitBreachedEvent,
    RiskRejectedEvent,
)
from pmrp.schemas.identifiers import CausationId, CommandId, EventId
from pmrp.schemas.risk import KillSwitchScope, RiskLimitScope
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _event_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "event_id": "evt_01j00000000000000000000000",
        "event_type": "order.created",
        "schema_version": 1,
        "occurred_at": "2026-07-28T12:00:00Z",
        "received_at": "2026-07-28T12:00:00.100000Z",
        "published_at": "2026-07-28T12:00:00.200000Z",
        "producer": "execution",
        "exchange": "kalshi",
        "market_id": "mkt_01j00000000000000000000000",
        "account_id": "acct_shadow",
        "strategy_id": "strat_example",
        "order_id": "ord_01j00000000000000000000000",
        "correlation_id": "corr_01j00000000000000000000000",
        "causation_id": "evt_01j00000000000000000000001",
        "trace_id": "trace-abc123",
        "replay_session_id": None,
        "simulation_session_id": None,
        "quality_flags": (DataQualityFlag.REPLAYED,),
        "attributes": {"source": "unit_test"},
    }
    payload.update(overrides)
    return payload


def test_event_envelope_accepts_required_lineage_fields() -> None:
    event = EventEnvelope.model_validate(_event_payload())

    assert event.event_id == EventId("evt_01j00000000000000000000000")
    assert event.correlation_id == "corr_01j00000000000000000000000"
    assert event.causation_id == EventId("evt_01j00000000000000000000001")
    assert event.quality_flags == (DataQualityFlag.REPLAYED,)


def test_event_envelope_accepts_command_causation_reference() -> None:
    event = EventEnvelope.model_validate(
        _event_payload(causation_id="cmd_01j00000000000000000000000")
    )

    assert event.causation_id == CommandId("cmd_01j00000000000000000000000")


def test_event_envelope_accepts_explicit_causation_identifier() -> None:
    event = EventEnvelope.model_validate(
        _event_payload(causation_id="cause_01j00000000000000000000000")
    )

    assert event.causation_id == CausationId("cause_01j00000000000000000000000")


def test_event_envelope_rejects_unsupported_causation_prefix() -> None:
    with pytest.raises(ValidationError, match="must start"):
        EventEnvelope.model_validate(_event_payload(causation_id="risk_01j"))


def test_event_envelope_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        EventEnvelope.model_validate(_event_payload(unexpected=True))


def test_event_envelope_rejects_invalid_event_type() -> None:
    with pytest.raises(ValidationError, match="String should match pattern"):
        EventEnvelope.model_validate(_event_payload(event_type="OrderCreated"))


def test_event_envelope_rejects_naive_datetime() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        EventEnvelope.model_validate(
            _event_payload(occurred_at=datetime.fromisoformat("2026-07-28T12:00:00"))
        )


def test_event_envelope_serializes_datetimes_enums_and_ids() -> None:
    event = EventEnvelope.model_validate(_event_payload())

    serialized = json.loads(event.model_dump_json())

    assert serialized["occurred_at"] == "2026-07-28T12:00:00Z"
    assert serialized["quality_flags"] == ["replayed"]
    assert serialized["event_id"] == "evt_01j00000000000000000000000"


def test_event_envelope_attributes_are_deeply_immutable_after_validation() -> None:
    event = EventEnvelope.model_validate(
        _event_payload(attributes={"source": "unit_test", "nested": {"levels": ["one"]}})
    )
    original_hash = canonical_sha256(event)
    nested_attributes = event.attributes["nested"]

    with pytest.raises(TypeError, match="does not support item assignment"):
        event.attributes["source"] = "changed"
    assert isinstance(nested_attributes, Mapping)
    with pytest.raises(TypeError, match="does not support item assignment"):
        nested_attributes["levels"] = ["changed"]

    assert canonical_sha256(event) == original_hash


def test_event_envelope_rejects_invalid_attribute_key() -> None:
    with pytest.raises(ValidationError, match="keys must be nonempty"):
        EventEnvelope.model_validate(_event_payload(attributes={" source": "unit_test"}))


def test_event_envelope_rejects_noncanonical_attribute_leaf_value() -> None:
    with pytest.raises(TypeError, match="must not contain floats"):
        EventEnvelope.model_validate(_event_payload(attributes={"probability": 0.5}))


def test_event_envelope_json_round_trip_accepts_quality_flag_array() -> None:
    event = EventEnvelope.model_validate_json(json.dumps(_event_payload()))

    assert event.quality_flags == (DataQualityFlag.REPLAYED,)


def test_event_envelope_canonical_hash_is_stable() -> None:
    event = EventEnvelope.model_validate(_event_payload())

    assert canonical_json(event) == canonical_json(EventEnvelope.model_validate(_event_payload()))
    assert canonical_sha256(event) == canonical_sha256(
        EventEnvelope.model_validate(_event_payload())
    )


def test_event_envelope_registry_entry_exists() -> None:
    registration = get_schema_registration("event_envelope", 1)

    assert registration.model_path == "pmrp.schemas.events.EventEnvelope"
    assert get_schema_model("event_envelope", 1) is EventEnvelope


def test_risk_approved_event_accepts_valid_lineage() -> None:
    event = RiskApprovedEvent.model_validate(
        {
            "envelope": _risk_envelope_payload(RISK_APPROVED_EVENT_TYPE),
            "decision": _risk_decision_payload(),
            "approved_order": _approved_order_payload(),
        }
    )

    assert event.envelope.event_type == RISK_APPROVED_EVENT_TYPE
    assert event.decision.risk_decision_id == event.approved_order.risk_decision_id


def test_risk_approved_event_rejects_wrong_event_type() -> None:
    with pytest.raises(ValidationError, match=RISK_APPROVED_EVENT_TYPE):
        RiskApprovedEvent.model_validate(
            {
                "envelope": _risk_envelope_payload(RISK_REJECTED_EVENT_TYPE),
                "decision": _risk_decision_payload(),
                "approved_order": _approved_order_payload(),
            }
        )


def test_risk_approved_event_rejects_mismatched_approval_lineage() -> None:
    with pytest.raises(ValidationError, match="risk_decision_id"):
        RiskApprovedEvent.model_validate(
            {
                "envelope": _risk_envelope_payload(RISK_APPROVED_EVENT_TYPE),
                "decision": _risk_decision_payload(),
                "approved_order": _approved_order_payload(risk_decision_id="risk_mismatched_event"),
            }
        )


def test_risk_approved_event_rejects_rejected_decision() -> None:
    with pytest.raises(ValidationError, match="approved"):
        RiskApprovedEvent.model_validate(
            {
                "envelope": _risk_envelope_payload(RISK_APPROVED_EVENT_TYPE),
                "decision": _risk_decision_payload(
                    status=RiskDecisionStatus.REJECTED,
                    rule_results=(_risk_rule_result_payload(passed=False),),
                    approved_quantity=None,
                    approved_limit_price=None,
                    approval_expires_at=None,
                ),
                "approved_order": _approved_order_payload(),
            }
        )


def test_risk_approved_event_requires_order_lineage() -> None:
    with pytest.raises(ValidationError, match="order_id"):
        RiskApprovedEvent.model_validate(
            {
                "envelope": _risk_envelope_payload(RISK_APPROVED_EVENT_TYPE, order_id=None),
                "decision": _risk_decision_payload(),
                "approved_order": _approved_order_payload(),
            }
        )


def test_risk_rejected_event_accepts_rejected_decision() -> None:
    event = RiskRejectedEvent.model_validate(
        {
            "envelope": _risk_envelope_payload(RISK_REJECTED_EVENT_TYPE),
            "decision": _risk_decision_payload(
                status=RiskDecisionStatus.REJECTED,
                rule_results=(_risk_rule_result_payload(passed=False),),
                approved_quantity=None,
                approved_limit_price=None,
                approval_expires_at=None,
            ),
        }
    )

    assert event.envelope.event_type == RISK_REJECTED_EVENT_TYPE
    assert event.decision.status is RiskDecisionStatus.REJECTED


def test_risk_rejected_event_rejects_approved_decision() -> None:
    with pytest.raises(ValidationError, match="rejected"):
        RiskRejectedEvent.model_validate(
            {
                "envelope": _risk_envelope_payload(RISK_REJECTED_EVENT_TYPE),
                "decision": _risk_decision_payload(),
            }
        )


def test_risk_rejected_event_rejects_correlation_mismatch() -> None:
    with pytest.raises(ValidationError, match="correlation_id"):
        RiskRejectedEvent.model_validate(
            {
                "envelope": _risk_envelope_payload(
                    RISK_REJECTED_EVENT_TYPE,
                    correlation_id="corr_other_event",
                ),
                "decision": _risk_decision_payload(
                    status=RiskDecisionStatus.REJECTED,
                    rule_results=(_risk_rule_result_payload(passed=False),),
                    approved_quantity=None,
                    approved_limit_price=None,
                    approval_expires_at=None,
                ),
            }
        )


def test_risk_limit_breached_event_accepts_breach() -> None:
    event = RiskLimitBreachedEvent.model_validate(
        {
            "envelope": _risk_envelope_payload(RISK_LIMIT_BREACHED_EVENT_TYPE),
            "breach": _risk_breach_payload(),
        }
    )

    assert event.envelope.event_type == RISK_LIMIT_BREACHED_EVENT_TYPE
    assert event.breach.breach_id == "breach_event"


def test_kill_switch_events_validate_active_state() -> None:
    activated = KillSwitchActivatedEvent.model_validate(
        {
            "envelope": _risk_envelope_payload(RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE),
            "state": _kill_switch_payload(active=True),
        }
    )
    released = KillSwitchReleasedEvent.model_validate(
        {
            "envelope": _risk_envelope_payload(RISK_KILL_SWITCH_RELEASED_EVENT_TYPE),
            "state": _kill_switch_payload(active=False),
        }
    )

    assert activated.state.active is True
    assert released.state.active is False

    with pytest.raises(ValidationError, match="active"):
        KillSwitchActivatedEvent.model_validate(
            {
                "envelope": _risk_envelope_payload(RISK_KILL_SWITCH_ACTIVATED_EVENT_TYPE),
                "state": _kill_switch_payload(active=False),
            }
        )
    with pytest.raises(ValidationError, match="inactive"):
        KillSwitchReleasedEvent.model_validate(
            {
                "envelope": _risk_envelope_payload(RISK_KILL_SWITCH_RELEASED_EVENT_TYPE),
                "state": _kill_switch_payload(active=True),
            }
        )


def test_risk_event_registry_entries_exist() -> None:
    expected = {
        "risk_approved_event": RiskApprovedEvent,
        "risk_rejected_event": RiskRejectedEvent,
        "risk_limit_breached_event": RiskLimitBreachedEvent,
        "kill_switch_activated_event": KillSwitchActivatedEvent,
        "kill_switch_released_event": KillSwitchReleasedEvent,
    }

    for schema_name, model in expected.items():
        registration = get_schema_registration(schema_name, 1)

        assert registration.model_path == f"pmrp.schemas.events.{model.__name__}"
        assert get_schema_model(schema_name, 1) is model


def _risk_envelope_payload(event_type: str, **overrides: object) -> dict[str, object]:
    payload = _event_payload(
        event_type=event_type,
        producer="risk",
        market_id="mkt_event",
        account_id="acct_event",
        strategy_id="strat_event",
        order_id="ord_event",
        correlation_id="corr_event",
        causation_id="cmd_event",
    )
    payload.update(overrides)
    return payload


def _risk_rule_result_payload(*, passed: bool = True) -> dict[str, object]:
    return {
        "rule_id": "RISK-TEST",
        "rule_version": "1.0",
        "passed": passed,
        "reason_code": "RISK_TEST_VALID" if passed else "RISK_TEST_REJECTED",
        "reason_text": None,
        "observed_value": "1",
        "limit_value": "2",
        "unit": "test",
        "evaluated_at": "2026-07-28T12:00:00Z",
    }


def _risk_decision_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "risk_decision_id": "risk_event",
        "intent_id": "intent_event",
        "status": RiskDecisionStatus.APPROVED,
        "evaluated_at": "2026-07-28T12:00:00Z",
        "input_snapshot_id": "risk_input_event",
        "rule_results": (_risk_rule_result_payload(),),
        "approved_quantity": "10",
        "approved_limit_price": "0.50",
        "approval_expires_at": "2026-07-28T12:00:05Z",
        "configuration_hash": "sha256:config",
        "correlation_id": "corr_event",
    }
    payload.update(overrides)
    return payload


def _approved_order_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "order_id": "ord_event",
        "intent_id": "intent_event",
        "strategy_id": "strat_event",
        "risk_decision_id": "risk_event",
        "exchange": "kalshi",
        "account_id": "acct_event",
        "market_id": "mkt_event",
        "contract_id": "ctr_event",
        "outcome_id": "out_event",
        "side": Side.BUY,
        "quantity": "10",
        "limit_price": "0.50",
        "order_type": OrderType.LIMIT,
        "time_in_force": TimeInForce.GTC,
        "post_only": False,
        "reduce_only": False,
        "approved_at": "2026-07-28T12:00:00Z",
        "approval_expires_at": "2026-07-28T12:00:05Z",
        "client_order_id": "client-event",
        "idempotency_key": "idem-event",
        "correlation_id": "corr_event",
    }
    payload.update(overrides)
    return payload


def _risk_breach_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "breach_id": "breach_event",
        "rule_id": "RISK-TEST",
        "rule_version": "1.0",
        "scope": RiskLimitScope.STRATEGY,
        "scope_id": "strat_event",
        "severity": "critical",
        "detected_at": "2026-07-28T12:00:00Z",
        "observed_value": "3",
        "limit_value": "2",
        "unit": "test",
        "action_taken": "reject_order",
        "correlation_id": "corr_event",
    }
    payload.update(overrides)
    return payload


def _kill_switch_payload(*, active: bool) -> dict[str, object]:
    if active:
        return {
            "kill_switch_id": "kill_switch_event",
            "scope": KillSwitchScope.STRATEGY,
            "scope_id": "strat_event",
            "active": True,
            "activated_at": "2026-07-28T12:00:00Z",
            "activated_by": "operator",
            "activation_reason": "risk limit breach",
            "released_at": None,
            "released_by": None,
            "release_reason": None,
            "version": 1,
        }
    return {
        "kill_switch_id": "kill_switch_event",
        "scope": KillSwitchScope.STRATEGY,
        "scope_id": "strat_event",
        "active": False,
        "activated_at": "2026-07-28T12:00:00Z",
        "activated_by": "operator",
        "activation_reason": "risk limit breach",
        "released_at": "2026-07-28T12:05:00Z",
        "released_by": "operator",
        "release_reason": "risk state cleared",
        "version": 2,
    }
