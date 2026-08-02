"""Tests for shared adapter rate-limit contracts."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pmrp.adapters import (
    AdapterEndpointCategory,
    AdapterRateLimitDecision,
    AdapterRateLimitRule,
    evaluate_rate_limit,
)
from pmrp.schemas.serialization import canonical_json, canonical_sha256


def _rule_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "exchange": "kalshi",
        "endpoint_category": AdapterEndpointCategory.MARKET_DATA,
        "operation": "list_markets",
        "window_name": "minute",
        "limit": 120,
        "window_seconds": 60,
        "cost": 2,
    }
    payload.update(overrides)
    return payload


def _decision_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "exchange": "kalshi",
        "endpoint_category": AdapterEndpointCategory.MARKET_DATA,
        "operation": "list_markets",
        "window_name": "minute",
        "allowed": True,
        "cost": 2,
        "limit": 120,
        "remaining_before": 10,
        "remaining_after": 8,
        "decided_at": "2026-08-02T18:15:00Z",
        "resets_at": "2026-08-02T18:16:00Z",
        "retry_after_seconds": None,
    }
    payload.update(overrides)
    return payload


@pytest.mark.unit
def test_adapter_rate_limit_rule_accepts_valid_payload() -> None:
    rule = AdapterRateLimitRule.model_validate(_rule_payload())

    assert rule.exchange == "kalshi"
    assert rule.endpoint_category is AdapterEndpointCategory.MARKET_DATA
    assert rule.cost == 2


@pytest.mark.unit
def test_adapter_rate_limit_rule_rejects_unknown_fields() -> None:
    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        AdapterRateLimitRule.model_validate(_rule_payload(unexpected=True))


@pytest.mark.unit
def test_adapter_rate_limit_rule_rejects_raw_endpoint_category_string() -> None:
    with pytest.raises(
        ValidationError, match="Input should be an instance of AdapterEndpointCategory"
    ):
        AdapterRateLimitRule.model_validate(_rule_payload(endpoint_category="market_data"))


@pytest.mark.unit
def test_adapter_rate_limit_rule_rejects_blank_text() -> None:
    with pytest.raises(ValidationError, match="without surrounding whitespace"):
        AdapterRateLimitRule.model_validate(_rule_payload(operation=" list_markets "))


@pytest.mark.unit
def test_adapter_rate_limit_rule_rejects_nonpositive_values() -> None:
    with pytest.raises(ValidationError, match="greater than 0"):
        AdapterRateLimitRule.model_validate(_rule_payload(limit=0))
    with pytest.raises(ValidationError, match="greater than 0"):
        AdapterRateLimitRule.model_validate(_rule_payload(window_seconds=0))
    with pytest.raises(ValidationError, match="greater than 0"):
        AdapterRateLimitRule.model_validate(_rule_payload(cost=0))


@pytest.mark.unit
def test_adapter_rate_limit_rule_rejects_cost_above_limit() -> None:
    with pytest.raises(ValidationError, match="cost must not exceed limit"):
        AdapterRateLimitRule.model_validate(_rule_payload(limit=1, cost=2))


@pytest.mark.unit
def test_evaluate_rate_limit_allows_request_and_consumes_capacity() -> None:
    rule = AdapterRateLimitRule.model_validate(_rule_payload())

    decision = evaluate_rate_limit(
        rule,
        remaining=10,
        decided_at=datetime(2026, 8, 2, 18, 15, tzinfo=UTC),
        resets_at=datetime(2026, 8, 2, 18, 16, tzinfo=UTC),
    )

    assert decision.allowed is True
    assert decision.remaining_before == 10
    assert decision.remaining_after == 8
    assert decision.retry_after_seconds is None


@pytest.mark.unit
def test_evaluate_rate_limit_blocks_request_and_preserves_capacity() -> None:
    rule = AdapterRateLimitRule.model_validate(_rule_payload(cost=3))

    decision = evaluate_rate_limit(
        rule,
        remaining=2,
        decided_at=datetime(2026, 8, 2, 18, 15, 0, 1, tzinfo=UTC),
        resets_at=datetime(2026, 8, 2, 18, 15, 2, tzinfo=UTC),
    )

    assert decision.allowed is False
    assert decision.remaining_before == 2
    assert decision.remaining_after == 2
    assert decision.retry_after_seconds == 2


@pytest.mark.unit
def test_evaluate_rate_limit_accepts_per_request_cost_override() -> None:
    rule = AdapterRateLimitRule.model_validate(_rule_payload(cost=1))

    decision = evaluate_rate_limit(
        rule,
        remaining=10,
        cost=4,
        decided_at=datetime(2026, 8, 2, 18, 15, tzinfo=UTC),
    )

    assert decision.cost == 4
    assert decision.remaining_after == 6


@pytest.mark.unit
def test_evaluate_rate_limit_rejects_invalid_inputs_via_decision_model() -> None:
    rule = AdapterRateLimitRule.model_validate(_rule_payload())

    with pytest.raises(ValidationError, match="greater than or equal to 0"):
        evaluate_rate_limit(
            rule,
            remaining=-1,
            decided_at=datetime(2026, 8, 2, 18, 15, tzinfo=UTC),
        )
    with pytest.raises(ValidationError, match="must not exceed limit"):
        evaluate_rate_limit(
            rule,
            remaining=121,
            decided_at=datetime(2026, 8, 2, 18, 15, tzinfo=UTC),
        )
    with pytest.raises(ValidationError, match="cost must not exceed limit"):
        evaluate_rate_limit(
            rule,
            remaining=10,
            cost=121,
            decided_at=datetime(2026, 8, 2, 18, 15, tzinfo=UTC),
        )


@pytest.mark.unit
def test_evaluate_rate_limit_rejects_naive_decision_time() -> None:
    rule = AdapterRateLimitRule.model_validate(_rule_payload())
    naive_decided_at = datetime(2026, 8, 2, 18, 15, tzinfo=UTC).replace(tzinfo=None)

    with pytest.raises(ValueError, match="timezone-aware"):
        evaluate_rate_limit(rule, remaining=10, decided_at=naive_decided_at)


@pytest.mark.unit
def test_adapter_rate_limit_decision_rejects_invalid_allowed_remaining() -> None:
    with pytest.raises(ValidationError, match="must consume cost"):
        AdapterRateLimitDecision.model_validate(_decision_payload(remaining_after=9))


@pytest.mark.unit
def test_adapter_rate_limit_decision_rejects_stale_reset_time() -> None:
    with pytest.raises(ValidationError, match="must not precede"):
        AdapterRateLimitDecision.model_validate(_decision_payload(resets_at="2026-08-02T18:14:59Z"))


@pytest.mark.unit
def test_adapter_rate_limit_decision_rejects_blocked_capacity_consumption() -> None:
    with pytest.raises(ValidationError, match="must preserve remaining capacity"):
        AdapterRateLimitDecision.model_validate(
            _decision_payload(
                allowed=False,
                remaining_before=1,
                remaining_after=0,
                retry_after_seconds=30,
            )
        )


@pytest.mark.unit
def test_adapter_rate_limit_decision_rejects_allowed_retry_after() -> None:
    with pytest.raises(ValidationError, match="must not include retry_after_seconds"):
        AdapterRateLimitDecision.model_validate(_decision_payload(retry_after_seconds=30))


@pytest.mark.unit
def test_adapter_rate_limit_models_are_immutable_after_validation() -> None:
    decision = AdapterRateLimitDecision.model_validate(_decision_payload())
    original_hash = canonical_sha256(decision)

    with pytest.raises(ValidationError, match="Instance is frozen"):
        decision.remaining_after = 7

    assert canonical_sha256(decision) == original_hash


@pytest.mark.unit
def test_adapter_rate_limit_models_json_round_trip_and_stable_hash() -> None:
    decision = AdapterRateLimitDecision.model_validate(_decision_payload())
    canonical = canonical_json(decision)

    assert '"endpoint_category":"market_data"' in canonical
    assert AdapterRateLimitDecision.model_validate_json(canonical) == decision
    assert canonical_sha256(decision) == canonical_sha256(
        AdapterRateLimitDecision.model_validate_json(canonical)
    )


@pytest.mark.unit
def test_adapter_rate_limit_models_json_schema_generation() -> None:
    assert AdapterRateLimitRule.model_json_schema()["title"] == "AdapterRateLimitRule"
    assert AdapterRateLimitDecision.model_json_schema()["title"] == "AdapterRateLimitDecision"
