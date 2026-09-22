"""Property tests for the RISK-016 duplicate-order guard rule."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.risk import (
    RISK_DUPLICATE_IDEMPOTENCY_KEY_REASON,
    RISK_DUPLICATE_INTENT_ID_REASON,
    RISK_DUPLICATE_ORDER_STATE_FUTURE_REASON,
    RISK_DUPLICATE_ORDER_STATE_STALE_REASON,
    RISK_DUPLICATE_ORDER_VALID_REASON,
    DuplicateOrderGuardRule,
    RiskContext,
    RiskDuplicateOrderGuardState,
)
from pmrp.schemas.enums import OrderType, Side, TimeInForce
from pmrp.schemas.identifiers import ContractId, IntentId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent

pytestmark = pytest.mark.property

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_duplicate_order_guard_property")
CONTRACT_ID = ContractId("ctr_risk_duplicate_order_guard_property")
STRATEGY_ID = StrategyId("strat_risk_duplicate_order_guard_property")
INTENT_ID = IntentId("intent_risk_duplicate_order_guard_property")
IDEMPOTENCY_KEY = "idem-risk-duplicate-order-guard-property"


@given(
    seen_intent_suffixes=st.sets(st.integers(min_value=0, max_value=1000), max_size=20),
    seen_key_suffixes=st.sets(st.integers(min_value=0, max_value=1000), max_size=20),
    age_ms=st.integers(min_value=0, max_value=5000),
)
async def test_duplicate_order_guard_rule_is_deterministic_without_duplicates(
    seen_intent_suffixes: set[int],
    seen_key_suffixes: set[int],
    age_ms: int,
) -> None:
    rule = DuplicateOrderGuardRule(max_state_age=timedelta(milliseconds=5000))
    context = _context(
        observed_at=NOW - timedelta(milliseconds=age_ms),
        known_intent_ids={IntentId(f"intent_seen_{suffix}") for suffix in seen_intent_suffixes},
        known_idempotency_keys={f"idem-seen-{suffix}" for suffix in seen_key_suffixes},
    )

    first = await rule.evaluate(_intent(), context)
    second = await rule.evaluate(_intent(), context)

    assert first == second
    assert first.passed is True
    assert first.reason_code == RISK_DUPLICATE_ORDER_VALID_REASON
    assert first.observed_value == Decimal("0")
    assert first.limit_value == Decimal("0")


@given(
    seen_intent_suffixes=st.sets(st.integers(min_value=0, max_value=1000), max_size=20),
    seen_key_suffixes=st.sets(st.integers(min_value=0, max_value=1000), max_size=20),
)
async def test_duplicate_order_guard_rule_rejects_any_duplicate_intent_id(
    seen_intent_suffixes: set[int],
    seen_key_suffixes: set[int],
) -> None:
    result = await DuplicateOrderGuardRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            observed_at=NOW,
            known_intent_ids={IntentId(f"intent_seen_{suffix}") for suffix in seen_intent_suffixes}
            | {INTENT_ID},
            known_idempotency_keys={f"idem-seen-{suffix}" for suffix in seen_key_suffixes},
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DUPLICATE_INTENT_ID_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")


@given(
    seen_intent_suffixes=st.sets(st.integers(min_value=0, max_value=1000), max_size=20),
    seen_key_suffixes=st.sets(st.integers(min_value=0, max_value=1000), max_size=20),
)
async def test_duplicate_order_guard_rule_rejects_any_duplicate_idempotency_key(
    seen_intent_suffixes: set[int],
    seen_key_suffixes: set[int],
) -> None:
    result = await DuplicateOrderGuardRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(
            observed_at=NOW,
            known_intent_ids={IntentId(f"intent_seen_{suffix}") for suffix in seen_intent_suffixes},
            known_idempotency_keys={f"idem-seen-{suffix}" for suffix in seen_key_suffixes}
            | {IDEMPOTENCY_KEY},
        ),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DUPLICATE_IDEMPOTENCY_KEY_REASON
    assert result.observed_value == Decimal("1")
    assert result.limit_value == Decimal("0")


@given(age_ms=st.integers(min_value=5001, max_value=600000))
async def test_duplicate_order_guard_rule_rejects_any_stale_guard_state(age_ms: int) -> None:
    result = await DuplicateOrderGuardRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(observed_at=NOW - timedelta(milliseconds=age_ms)),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DUPLICATE_ORDER_STATE_STALE_REASON
    assert result.observed_value == Decimal(age_ms)
    assert result.limit_value == Decimal("5000")


@given(future_ms=st.integers(min_value=1, max_value=600000))
async def test_duplicate_order_guard_rule_rejects_any_future_guard_state(
    future_ms: int,
) -> None:
    result = await DuplicateOrderGuardRule(max_state_age=timedelta(milliseconds=5000)).evaluate(
        _intent(),
        _context(observed_at=NOW + timedelta(milliseconds=future_ms)),
    )

    assert result.passed is False
    assert result.reason_code == RISK_DUPLICATE_ORDER_STATE_FUTURE_REASON
    assert result.observed_value == Decimal(future_ms)
    assert result.limit_value == Decimal("0")


def _context(
    *,
    observed_at: datetime,
    known_intent_ids: set[IntentId] | None = None,
    known_idempotency_keys: set[str] | None = None,
) -> RiskContext:
    return RiskContext(
        evaluated_at=NOW,
        duplicate_order_guard=RiskDuplicateOrderGuardState(
            observed_at=observed_at,
            known_intent_ids=known_intent_ids or frozenset(),
            known_idempotency_keys=known_idempotency_keys or frozenset(),
        ),
    )


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": INTENT_ID,
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
            "correlation_id": "corr_risk_duplicate_order_guard_property",
            "idempotency_key": IDEMPOTENCY_KEY,
        }
    )
