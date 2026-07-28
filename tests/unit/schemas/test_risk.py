import json
from datetime import datetime
from decimal import Decimal

import pytest
from pydantic import ValidationError

from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.risk import (
    KillSwitchScope,
    KillSwitchState,
    RiskBreach,
    RiskDecision,
    RiskLimit,
    RiskLimitScope,
    RiskRuleResult,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256
from pmrp.schemas.versions import get_schema_model, get_schema_registration

pytestmark = pytest.mark.unit


def _risk_limit_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "risk_limit_id": "risk_limit_001",
        "rule_id": "RISK-005",
        "rule_version": "1.0",
        "scope": RiskLimitScope.STRATEGY,
        "scope_id": "strat_fed_value_v1",
        "limit_type": "market_data_age_ms",
        "limit_value": "5000",
        "unit": "milliseconds",
        "effective_at": "2026-07-27T15:00:00Z",
        "expires_at": "2026-08-27T15:00:00Z",
        "enabled": True,
        "created_by": "risk_admin",
        "approved_by": "risk_reviewer",
    }
    payload.update(overrides)
    return payload


def _risk_rule_result_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "rule_id": "RISK-005",
        "rule_version": "1.0",
        "passed": True,
        "reason_code": "MARKET_DATA_FRESH",
        "reason_text": None,
        "observed_value": "12",
        "limit_value": "5000",
        "unit": "milliseconds",
        "evaluated_at": "2026-07-27T15:00:00.145000Z",
    }
    payload.update(overrides)
    return payload


def _risk_decision_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "risk_decision_id": "risk_01j00000000000000000000000",
        "intent_id": "intent_01j00000000000000000000000",
        "status": RiskDecisionStatus.APPROVED,
        "evaluated_at": "2026-07-27T15:00:00.145000Z",
        "input_snapshot_id": "risk_input_01j0000000000000000000",
        "rule_results": (_risk_rule_result_payload(),),
        "approved_quantity": "10",
        "approved_limit_price": "0.43",
        "approval_expires_at": "2026-07-27T15:00:01.145000Z",
        "configuration_hash": "sha256:abc123",
        "correlation_id": "corr_01j00000000000000000000000",
    }
    payload.update(overrides)
    return payload


def _risk_breach_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "breach_id": "breach_001",
        "rule_id": "RISK-007",
        "rule_version": "1.0",
        "scope": RiskLimitScope.ACCOUNT,
        "scope_id": "acct_paper_001",
        "severity": "critical",
        "detected_at": "2026-07-27T15:10:00Z",
        "observed_value": "12000",
        "limit_value": "10000",
        "unit": "usd",
        "action_taken": "BLOCK_TRADING",
        "correlation_id": "corr_01j00000000000000000000000",
    }
    payload.update(overrides)
    return payload


def _kill_switch_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "kill_switch_id": "kill_switch_001",
        "scope": KillSwitchScope.STRATEGY,
        "scope_id": "strat_fed_value_v1",
        "active": True,
        "activated_at": "2026-07-27T15:10:00Z",
        "activated_by": "risk_operator",
        "activation_reason": "Unexpected fill behavior",
        "released_at": None,
        "released_by": None,
        "release_reason": None,
        "version": 1,
    }
    payload.update(overrides)
    return payload


def test_risk_limit_accepts_valid_payload_and_exact_decimal() -> None:
    limit = RiskLimit.model_validate(_risk_limit_payload())

    assert limit.scope is RiskLimitScope.STRATEGY
    assert limit.limit_value == Decimal("5000")


def test_risk_limit_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RiskLimit.model_validate(_risk_limit_payload(unexpected=True))


def test_risk_limit_rejects_float_limit_value() -> None:
    with pytest.raises(TypeError, match="float input"):
        RiskLimit.model_validate(_risk_limit_payload(limit_value=5000.0))


def test_risk_limit_rejects_invalid_scope_enum() -> None:
    with pytest.raises(ValidationError):
        RiskLimit.model_validate(_risk_limit_payload(scope="desk"))


def test_risk_limit_rejects_naive_effective_time() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        RiskLimit.model_validate(
            _risk_limit_payload(effective_at=datetime.fromisoformat("2026-07-27T15:00:00"))
        )


def test_risk_limit_rejects_invalid_effective_window() -> None:
    with pytest.raises(ValidationError, match="expires_at must be after"):
        RiskLimit.model_validate(_risk_limit_payload(expires_at="2026-07-27T15:00:00Z"))


def test_risk_rule_result_accepts_valid_payload() -> None:
    result = RiskRuleResult.model_validate(_risk_rule_result_payload())

    assert result.passed is True
    assert result.observed_value == Decimal("12")
    assert result.limit_value == Decimal("5000")


def test_risk_rule_result_rejects_float_observed_value() -> None:
    with pytest.raises(TypeError, match="float input"):
        RiskRuleResult.model_validate(_risk_rule_result_payload(observed_value=12.0))


def test_risk_rule_result_rejects_missing_reason_code() -> None:
    payload = _risk_rule_result_payload()
    del payload["reason_code"]

    with pytest.raises(ValidationError, match="Field required"):
        RiskRuleResult.model_validate(payload)


def test_risk_decision_accepts_valid_payload() -> None:
    decision = RiskDecision.model_validate(_risk_decision_payload())

    assert decision.risk_decision_id == "risk_01j00000000000000000000000"
    assert decision.status is RiskDecisionStatus.APPROVED
    assert decision.approved_quantity == Decimal("10")


def test_risk_decision_accepts_rejected_payload_with_failed_rule() -> None:
    decision = RiskDecision.model_validate(
        _risk_decision_payload(
            status=RiskDecisionStatus.REJECTED,
            rule_results=(
                _risk_rule_result_payload(
                    passed=False,
                    reason_code="ORDER_NOTIONAL_LIMIT",
                    reason_text="Requested notional exceeded limit.",
                ),
            ),
            approved_quantity=None,
            approved_limit_price=None,
            approval_expires_at=None,
        )
    )

    assert decision.status is RiskDecisionStatus.REJECTED
    assert decision.rule_results[0].passed is False


def test_risk_decision_rejects_empty_rule_results() -> None:
    with pytest.raises(ValidationError, match="requires at least one rule result"):
        RiskDecision.model_validate(_risk_decision_payload(rule_results=()))


def test_risk_decision_rejects_approved_with_failed_rule_result() -> None:
    with pytest.raises(ValidationError, match="approved risk decision cannot contain failed"):
        RiskDecision.model_validate(
            _risk_decision_payload(
                rule_results=(
                    _risk_rule_result_payload(
                        passed=False,
                        reason_code="ORDER_NOTIONAL_LIMIT",
                    ),
                )
            )
        )


def test_risk_decision_rejects_approved_without_approval_fields() -> None:
    with pytest.raises(ValidationError, match="requires approved quantity and limit price"):
        RiskDecision.model_validate(
            _risk_decision_payload(approved_quantity=None, approved_limit_price=None)
        )


def test_risk_decision_rejects_non_approved_with_approval_fields() -> None:
    with pytest.raises(ValidationError, match="non-approved risk decision cannot contain"):
        RiskDecision.model_validate(_risk_decision_payload(status=RiskDecisionStatus.REJECTED))


def test_risk_decision_rejects_non_approved_without_failed_rule_result() -> None:
    with pytest.raises(ValidationError, match="requires at least one failed rule result"):
        RiskDecision.model_validate(
            _risk_decision_payload(
                status=RiskDecisionStatus.ERROR,
                approved_quantity=None,
                approved_limit_price=None,
                approval_expires_at=None,
            )
        )


def test_risk_decision_rejects_invalid_risk_identifier() -> None:
    with pytest.raises(ValidationError, match="RiskDecisionId must start"):
        RiskDecision.model_validate(_risk_decision_payload(risk_decision_id="decision_001"))


def test_risk_decision_rejects_invalid_intent_identifier() -> None:
    with pytest.raises(ValidationError, match="IntentId must start"):
        RiskDecision.model_validate(_risk_decision_payload(intent_id="order_intent_001"))


def test_risk_decision_rejects_invalid_status_enum() -> None:
    with pytest.raises(ValidationError):
        RiskDecision.model_validate(_risk_decision_payload(status="pending"))


def test_risk_decision_rejects_float_approved_quantity() -> None:
    with pytest.raises(TypeError, match="float input"):
        RiskDecision.model_validate(_risk_decision_payload(approved_quantity=10.0))


def test_risk_decision_rejects_non_positive_approved_quantity() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        RiskDecision.model_validate(_risk_decision_payload(approved_quantity="0"))


def test_risk_decision_rejects_naive_evaluated_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        RiskDecision.model_validate(
            _risk_decision_payload(
                evaluated_at=datetime.fromisoformat("2026-07-27T15:00:00.145000")
            )
        )


def test_risk_decision_rejects_expired_approval_window() -> None:
    with pytest.raises(ValidationError, match="approval_expires_at must be after"):
        RiskDecision.model_validate(
            _risk_decision_payload(approval_expires_at="2026-07-27T15:00:00.145000Z")
        )


def test_risk_decision_rejects_invalid_correlation_id() -> None:
    with pytest.raises(ValidationError, match="CorrelationId must start"):
        RiskDecision.model_validate(_risk_decision_payload(correlation_id="corr-001"))


def test_risk_decision_json_round_trip_and_stable_hash() -> None:
    decision = RiskDecision.model_validate_json(
        json.dumps(
            {
                **_risk_decision_payload(),
                "status": "approved",
                "rule_results": [_risk_rule_result_payload()],
            }
        )
    )
    canonical = canonical_json(decision)

    assert RiskDecision.model_validate_json(canonical) == decision
    assert canonical_sha256(decision) == canonical_sha256(
        RiskDecision.model_validate_json(canonical)
    )


def test_risk_decision_json_schema_generation() -> None:
    json_schema = RiskDecision.model_json_schema()

    assert json_schema["title"] == "RiskDecision"
    assert "rule_results" in json_schema["properties"]


def test_risk_decision_schema_registry_entries_exist() -> None:
    assert get_schema_model("risk_limit", 1) is RiskLimit
    assert get_schema_model("risk_rule_result", 1) is RiskRuleResult
    assert get_schema_model("risk_decision", 1) is RiskDecision
    registration = get_schema_registration("risk_decision", 1)

    assert registration.model_path == "pmrp.schemas.risk.RiskDecision"


def test_risk_breach_accepts_valid_payload() -> None:
    breach = RiskBreach.model_validate(_risk_breach_payload())

    assert breach.scope is RiskLimitScope.ACCOUNT
    assert breach.observed_value == Decimal("12000")
    assert breach.limit_value == Decimal("10000")


def test_risk_breach_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        RiskBreach.model_validate(_risk_breach_payload(unexpected=True))


def test_risk_breach_rejects_float_limit_value() -> None:
    with pytest.raises(TypeError, match="float input"):
        RiskBreach.model_validate(_risk_breach_payload(limit_value=10000.0))


def test_risk_breach_rejects_invalid_scope_enum() -> None:
    with pytest.raises(ValidationError):
        RiskBreach.model_validate(_risk_breach_payload(scope="portfolio"))


def test_risk_breach_rejects_naive_detected_at() -> None:
    with pytest.raises(ValidationError, match="timezone-aware"):
        RiskBreach.model_validate(
            _risk_breach_payload(detected_at=datetime.fromisoformat("2026-07-27T15:10:00"))
        )


def test_risk_breach_rejects_invalid_correlation_id() -> None:
    with pytest.raises(ValidationError, match="CorrelationId must start"):
        RiskBreach.model_validate(_risk_breach_payload(correlation_id="corr-001"))


def test_kill_switch_state_accepts_active_payload() -> None:
    state = KillSwitchState.model_validate(_kill_switch_payload())

    assert state.scope is KillSwitchScope.STRATEGY
    assert state.active is True
    assert state.version == 1


def test_kill_switch_state_accepts_released_payload() -> None:
    state = KillSwitchState.model_validate(
        _kill_switch_payload(
            active=False,
            released_at="2026-07-27T15:30:00Z",
            released_by="risk_operator",
            release_reason="Incident reviewed.",
            version=2,
        )
    )

    assert state.active is False
    assert state.released_by == "risk_operator"


def test_kill_switch_state_accepts_inactive_never_activated_payload() -> None:
    state = KillSwitchState.model_validate(
        _kill_switch_payload(
            active=False,
            activated_at=None,
            activated_by=None,
            activation_reason=None,
            version=0,
        )
    )

    assert state.active is False
    assert state.activated_at is None


def test_kill_switch_state_rejects_active_without_activation_time() -> None:
    with pytest.raises(ValidationError, match="active kill switch requires activation audit"):
        KillSwitchState.model_validate(_kill_switch_payload(activated_at=None))


def test_kill_switch_state_rejects_active_with_release_fields() -> None:
    with pytest.raises(ValidationError, match="active kill switch cannot contain release fields"):
        KillSwitchState.model_validate(
            _kill_switch_payload(
                released_at="2026-07-27T15:30:00Z",
                released_by="risk_operator",
                release_reason="Incident reviewed.",
            )
        )


def test_kill_switch_state_rejects_release_without_activation_time() -> None:
    with pytest.raises(ValidationError, match="released kill switch requires activation audit"):
        KillSwitchState.model_validate(
            _kill_switch_payload(
                active=False,
                activated_at=None,
                activated_by=None,
                activation_reason=None,
                released_at="2026-07-27T15:30:00Z",
                released_by="risk_operator",
                release_reason="Incident reviewed.",
            )
        )


def test_kill_switch_state_rejects_release_without_operator_evidence() -> None:
    with pytest.raises(ValidationError, match="released kill switch requires release audit"):
        KillSwitchState.model_validate(
            _kill_switch_payload(
                active=False,
                released_at="2026-07-27T15:30:00Z",
                released_by=None,
                release_reason=None,
            )
        )


def test_kill_switch_state_rejects_inactive_activated_without_release() -> None:
    with pytest.raises(ValidationError, match="inactive activated kill switch requires release"):
        KillSwitchState.model_validate(_kill_switch_payload(active=False))


def test_kill_switch_state_rejects_release_before_activation() -> None:
    with pytest.raises(ValidationError, match="released_at must be after"):
        KillSwitchState.model_validate(
            _kill_switch_payload(
                active=False,
                released_at="2026-07-27T15:09:59Z",
                released_by="risk_operator",
                release_reason="Incident reviewed.",
            )
        )


def test_kill_switch_state_rejects_negative_version() -> None:
    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        KillSwitchState.model_validate(_kill_switch_payload(version=-1))


def test_kill_switch_state_json_round_trip_preserves_scope() -> None:
    state = KillSwitchState.model_validate_json(
        json.dumps({**_kill_switch_payload(), "scope": "strategy"})
    )

    assert KillSwitchState.model_validate_json(canonical_json(state)) == state


def test_operational_risk_schema_registry_entries_exist() -> None:
    assert get_schema_model("risk_breach", 1) is RiskBreach
    assert get_schema_model("kill_switch_state", 1) is KillSwitchState
    registration = get_schema_registration("kill_switch_state", 1)

    assert registration.model_path == "pmrp.schemas.risk.KillSwitchState"
