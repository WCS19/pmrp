"""Unit tests for the RISK-016 duplicate-order guard rule."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from pmrp.risk import (
    RISK_DUPLICATE_IDEMPOTENCY_KEY_REASON,
    RISK_DUPLICATE_INTENT_ID_REASON,
    RISK_DUPLICATE_ORDER_GUARD_RULE_ID,
    RISK_DUPLICATE_ORDER_GUARD_RULE_VERSION,
    RISK_DUPLICATE_ORDER_STATE_FUTURE_REASON,
    RISK_DUPLICATE_ORDER_STATE_MISSING_REASON,
    RISK_DUPLICATE_ORDER_STATE_STALE_REASON,
    RISK_DUPLICATE_ORDER_VALID_REASON,
    DuplicateOrderGuardRule,
    RiskConfigurationError,
    RiskContext,
    RiskDuplicateOrderGuardState,
    RiskInputError,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, IntentId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_duplicate_order_guard")
CONTRACT_ID = ContractId("ctr_risk_duplicate_order_guard")
STRATEGY_ID = StrategyId("strat_risk_duplicate_order_guard")
INTENT_ID = IntentId("intent_risk_duplicate_order_guard")
IDEMPOTENCY_KEY = "idem-risk-duplicate-order-guard"


async def test_duplicate_order_guard_rule_passes_without_seen_identifiers() -> None:
    rule = DuplicateOrderGuardRule(max_state_age=timedelta(seconds=5))
    result = await rule.evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            duplicate_order_guard=RiskDuplicateOrderGuardState(
                observed_at=NOW - timedelta(seconds=1),
                known_intent_ids={IntentId("intent_seen_other")},
                known_idempotency_keys={"idem-seen-other"},
            ),
        ),
    )

    assert rule.rule_id == RISK_DUPLICATE_ORDER_GUARD_RULE_ID
    assert rule.version == RISK_DUPLICATE_ORDER_GUARD_RULE_VERSION
    assert result.passed is True
    assert result.rule_id == "RISK-016"
    assert result.rule_version == "1.0"
    assert result.reason_code == RISK_DUPLICATE_ORDER_VALID_REASON
    assert result.observed_value == Decimal("0")
    assert result.limit_value == Decimal("0")
    assert result.unit == "duplicate_count"
    assert result.evaluated_at == NOW


async def test_duplicate_order_guard_rule_rejects_duplicate_intent_id() -> None:
    result = await DuplicateOrderGuardRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            duplicate_order_guard=RiskDuplicateOrderGuardState(
                observed_at=NOW,
                known_intent_ids={INTENT_ID},
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DUPLICATE_INTENT_ID_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "duplicate_count"


async def test_duplicate_order_guard_rule_rejects_duplicate_idempotency_key() -> None:
    result = await DuplicateOrderGuardRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            duplicate_order_guard=RiskDuplicateOrderGuardState(
                observed_at=NOW,
                known_idempotency_keys={IDEMPOTENCY_KEY},
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DUPLICATE_IDEMPOTENCY_KEY_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")


async def test_duplicate_order_guard_rule_prefers_intent_id_duplicate_reason() -> None:
    result = await DuplicateOrderGuardRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            duplicate_order_guard=RiskDuplicateOrderGuardState(
                observed_at=NOW,
                known_intent_ids={INTENT_ID},
                known_idempotency_keys={IDEMPOTENCY_KEY},
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DUPLICATE_INTENT_ID_REASON


async def test_duplicate_order_guard_rule_rejects_missing_guard_state() -> None:
    result = await DuplicateOrderGuardRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(evaluated_at=NOW),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DUPLICATE_ORDER_STATE_MISSING_REASON
    assert result.observed_value is None
    assert result.limit_value == Decimal("0")
    assert result.unit == "duplicate_count"


async def test_duplicate_order_guard_rule_rejects_stale_guard_state() -> None:
    result = await DuplicateOrderGuardRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            duplicate_order_guard=RiskDuplicateOrderGuardState(
                observed_at=NOW - timedelta(seconds=5, milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DUPLICATE_ORDER_STATE_STALE_REASON
    assert result.observed_value == Decimal("5001")
    assert result.limit_value == Decimal("5000")
    assert result.unit == "milliseconds"


async def test_duplicate_order_guard_rule_rejects_future_guard_state() -> None:
    result = await DuplicateOrderGuardRule(max_state_age=timedelta(seconds=5)).evaluate(
        _intent(),
        RiskContext(
            evaluated_at=NOW,
            duplicate_order_guard=RiskDuplicateOrderGuardState(
                observed_at=NOW + timedelta(milliseconds=1),
            ),
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DUPLICATE_ORDER_STATE_FUTURE_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")
    assert result.unit == "milliseconds"


def test_risk_context_duplicate_order_guard_validates_inputs() -> None:
    context = RiskContext(
        evaluated_at=NOW,
        duplicate_order_guard=RiskDuplicateOrderGuardState(
            observed_at=NOW,
            known_intent_ids=(IntentId("intent_seen_tuple"),),
            known_idempotency_keys=("idem-seen-tuple",),
        ),
    )
    state = context.duplicate_order_guard_state()

    assert state is not None
    assert state == context.duplicate_order_guard
    assert state.known_intent_ids == frozenset({IntentId("intent_seen_tuple")})
    assert state.known_idempotency_keys == frozenset({"idem-seen-tuple"})
    with pytest.raises(FrozenInstanceError):
        context.duplicate_order_guard = RiskDuplicateOrderGuardState(observed_at=NOW)
    with pytest.raises(RiskConfigurationError, match="RiskDuplicateOrderGuardState"):
        RiskContext(evaluated_at=NOW, duplicate_order_guard=True)  # type: ignore[arg-type]
    with pytest.raises(TypeError, match="known_intent_ids"):
        RiskDuplicateOrderGuardState(
            observed_at=NOW,
            known_intent_ids="intent_seen_wrong",  # type: ignore[arg-type]
        )
    with pytest.raises(RiskConfigurationError, match="IntentId"):
        RiskDuplicateOrderGuardState(
            observed_at=NOW,
            known_intent_ids={"intent_seen_wrong"},  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="known_idempotency_keys"):
        RiskDuplicateOrderGuardState(
            observed_at=NOW,
            known_idempotency_keys="idem-wrong",  # type: ignore[arg-type]
        )
    with pytest.raises(TypeError, match="strings"):
        RiskDuplicateOrderGuardState(
            observed_at=NOW,
            known_idempotency_keys={1},  # type: ignore[arg-type]
        )
    with pytest.raises(RiskConfigurationError, match="must not be empty"):
        RiskDuplicateOrderGuardState(observed_at=NOW, known_idempotency_keys={""})
    with pytest.raises(RiskConfigurationError, match="at most 256"):
        RiskDuplicateOrderGuardState(observed_at=NOW, known_idempotency_keys={"x" * 257})


async def test_duplicate_order_guard_rule_rejects_invalid_configuration_and_inputs() -> None:
    rule = DuplicateOrderGuardRule(max_state_age=timedelta(seconds=5))

    with pytest.raises(RiskConfigurationError, match="max_state_age"):
        DuplicateOrderGuardRule(max_state_age=timedelta(0))
    with pytest.raises(TypeError, match="max_state_age"):
        DuplicateOrderGuardRule(max_state_age=5)  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="OrderIntent"):
        await rule.evaluate(object(), RiskContext(evaluated_at=NOW))  # type: ignore[arg-type]
    with pytest.raises(RiskInputError, match="RiskContext"):
        await rule.evaluate(_intent(), object())  # type: ignore[arg-type]


def _intent(
    *,
    intent_id: IntentId = INTENT_ID,
    idempotency_key: str = IDEMPOTENCY_KEY,
) -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": intent_id,
            "strategy_id": STRATEGY_ID,
            "market_id": MARKET_ID,
            "contract_id": CONTRACT_ID,
            "outcome_id": "out_yes",
            "side": Side.BUY,
            "quantity": "10",
            "limit_price": "0.50",
            "order_type": OrderType.LIMIT,
            "time_in_force": TimeInForce.GTC,
            "post_only": False,
            "reduce_only": False,
            "urgency": "0.75",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_duplicate_order_guard",
            "idempotency_key": idempotency_key,
        }
    )
