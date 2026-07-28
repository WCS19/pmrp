import json
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.risk import RiskDecision, RiskRuleResult
from pmrp.schemas.serialization import canonical_json, canonical_sha256

pytestmark = pytest.mark.property

_EXACT_DECIMALS = st.decimals(
    min_value=Decimal("-1000000"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)

_POSITIVE_DECIMALS = st.decimals(
    min_value=Decimal("0.000001"),
    max_value=Decimal("1000000"),
    allow_nan=False,
    allow_infinity=False,
    places=6,
)


def _rule_result_payload(**overrides: object) -> dict[str, object]:
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


def _decision_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "risk_decision_id": "risk_01j00000000000000000000000",
        "intent_id": "intent_01j00000000000000000000000",
        "status": RiskDecisionStatus.APPROVED,
        "evaluated_at": "2026-07-27T15:00:00.145000Z",
        "input_snapshot_id": "risk_input_01j0000000000000000000",
        "rule_results": (_rule_result_payload(),),
        "approved_quantity": "10",
        "approved_limit_price": "0.43",
        "approval_expires_at": "2026-07-27T15:00:01.145000Z",
        "configuration_hash": "sha256:abc123",
        "correlation_id": "corr_01j00000000000000000000000",
    }
    payload.update(overrides)
    return payload


@given(observed_value=_EXACT_DECIMALS, limit_value=_EXACT_DECIMALS)
def test_risk_rule_result_decimal_values_round_trip_exactly(
    observed_value: Decimal,
    limit_value: Decimal,
) -> None:
    result = RiskRuleResult.model_validate_json(
        json.dumps(
            _rule_result_payload(
                observed_value=str(observed_value),
                limit_value=str(limit_value),
            )
        )
    )

    assert result.observed_value == observed_value
    assert result.limit_value == limit_value
    assert RiskRuleResult.model_validate_json(canonical_json(result)) == result


@given(approved_quantity=_POSITIVE_DECIMALS, approved_limit_price=_POSITIVE_DECIMALS)
def test_risk_decision_hash_is_stable_for_generated_approvals(
    approved_quantity: Decimal,
    approved_limit_price: Decimal,
) -> None:
    decision = RiskDecision.model_validate(
        _decision_payload(
            approved_quantity=str(approved_quantity),
            approved_limit_price=str(approved_limit_price),
        )
    )

    assert canonical_sha256(decision) == canonical_sha256(
        RiskDecision.model_validate_json(canonical_json(decision))
    )
