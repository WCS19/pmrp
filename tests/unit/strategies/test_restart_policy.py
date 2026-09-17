"""Strategy restart policy tests."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from typing import Any, cast

import pytest

from pmrp.schemas.identifiers import StrategyId
from pmrp.strategies import (
    BoundedRestartPolicy,
    NeverRestartPolicy,
    StrategyRestartDecision,
    StrategyRestartFailure,
    StrategyRestartFailureKind,
    StrategyRestartPolicyError,
)

pytestmark = pytest.mark.unit

NOW = datetime(2026, 7, 28, 15, 0, tzinfo=UTC)


def test_never_restart_policy_denies_fail_closed() -> None:
    policy = NeverRestartPolicy()

    decision = policy.decide(_failure())

    assert decision.should_restart is False
    assert decision.reason_code == "strategy_restart_policy_disabled"
    assert decision.next_attempt is None
    assert decision.restart_after is None
    assert decision.backoff == timedelta(0)
    assert decision.jitter == timedelta(0)


def test_bounded_restart_policy_allows_eligible_failure_with_backoff() -> None:
    policy = BoundedRestartPolicy(
        max_attempts=2,
        restartable_failure_kinds=frozenset({StrategyRestartFailureKind.EVENT_PROCESSING}),
        backoff=timedelta(seconds=5),
        jitter=timedelta(seconds=1),
        deadline=timedelta(minutes=1),
    )

    decision = policy.decide(
        _failure(
            previous_restart_attempts=1,
            latest_failure_at=datetime(
                2026,
                7,
                28,
                8,
                0,
                tzinfo=timezone(timedelta(hours=-7)),
            ),
        )
    )

    assert decision.should_restart is True
    assert decision.reason_code == "strategy_restart_allowed"
    assert decision.next_attempt == 2
    assert decision.restart_after == datetime(2026, 7, 28, 15, 0, 5, tzinfo=UTC)
    assert decision.backoff == timedelta(seconds=5)
    assert decision.jitter == timedelta(seconds=1)


def test_bounded_restart_policy_denies_unclassified_failure_kind() -> None:
    policy = _bounded_policy(restartable_failure_kinds={StrategyRestartFailureKind.INITIALIZATION})

    decision = policy.decide(_failure(failure_kind=StrategyRestartFailureKind.SHUTDOWN))

    assert decision == StrategyRestartDecision(
        should_restart=False,
        reason_code="strategy_restart_failure_kind_not_restartable",
    )


def test_bounded_restart_policy_denies_exhausted_attempts() -> None:
    policy = _bounded_policy(max_attempts=2)

    decision = policy.decide(_failure(previous_restart_attempts=2))

    assert decision.reason_code == "strategy_restart_attempts_exhausted"
    assert decision.should_restart is False


def test_bounded_restart_policy_denies_failures_after_deadline() -> None:
    policy = _bounded_policy(deadline=timedelta(seconds=30))

    decision = policy.decide(
        _failure(
            first_failure_at=NOW - timedelta(minutes=2),
            latest_failure_at=NOW,
        )
    )

    assert decision.reason_code == "strategy_restart_deadline_exceeded"
    assert decision.should_restart is False


def test_restart_failure_rejects_invalid_counts_and_time_order() -> None:
    with pytest.raises(StrategyRestartPolicyError) as count_error:
        _failure(previous_restart_attempts=cast(Any, True))

    assert count_error.value.reason_code == "strategy_restart_count_invalid"

    with pytest.raises(StrategyRestartPolicyError) as time_error:
        _failure(first_failure_at=NOW, latest_failure_at=NOW - timedelta(seconds=1))

    assert time_error.value.reason_code == "strategy_restart_failure_time_order_invalid"


def test_restart_policy_rejects_invalid_configuration() -> None:
    with pytest.raises(StrategyRestartPolicyError) as attempts_error:
        _bounded_policy(max_attempts=0)

    assert attempts_error.value.reason_code == "strategy_restart_count_invalid"

    with pytest.raises(StrategyRestartPolicyError) as kinds_error:
        BoundedRestartPolicy(
            max_attempts=1,
            restartable_failure_kinds=frozenset(),
            backoff=timedelta(0),
            deadline=timedelta(seconds=1),
        )

    assert kinds_error.value.reason_code == "strategy_restart_failure_kinds_invalid"

    with pytest.raises(StrategyRestartPolicyError) as deadline_error:
        _bounded_policy(deadline=timedelta(0))

    assert deadline_error.value.reason_code == "strategy_restart_duration_invalid"

    with pytest.raises(StrategyRestartPolicyError) as jitter_error:
        _bounded_policy(jitter=timedelta(seconds=-1))

    assert jitter_error.value.reason_code == "strategy_restart_duration_invalid"


def test_restart_decision_rejects_incoherent_restart_metadata() -> None:
    with pytest.raises(StrategyRestartPolicyError) as missing_attempt_error:
        StrategyRestartDecision(
            should_restart=True,
            reason_code="strategy_restart_allowed",
            restart_after=NOW,
        )

    assert missing_attempt_error.value.reason_code == "strategy_restart_count_invalid"

    with pytest.raises(StrategyRestartPolicyError) as extra_restart_after_error:
        StrategyRestartDecision(
            should_restart=False,
            reason_code="strategy_restart_denied",
            restart_after=NOW,
        )

    assert extra_restart_after_error.value.reason_code == "strategy_restart_decision_invalid"


def _bounded_policy(
    *,
    max_attempts: int = 2,
    restartable_failure_kinds: set[StrategyRestartFailureKind] | None = None,
    backoff: timedelta = timedelta(seconds=5),
    jitter: timedelta = timedelta(0),
    deadline: timedelta = timedelta(minutes=1),
) -> BoundedRestartPolicy:
    return BoundedRestartPolicy(
        max_attempts=max_attempts,
        restartable_failure_kinds=frozenset(
            restartable_failure_kinds or {StrategyRestartFailureKind.EVENT_PROCESSING}
        ),
        backoff=backoff,
        jitter=jitter,
        deadline=deadline,
    )


def _failure(
    *,
    failure_kind: StrategyRestartFailureKind = StrategyRestartFailureKind.EVENT_PROCESSING,
    previous_restart_attempts: int = 0,
    first_failure_at: datetime = NOW,
    latest_failure_at: datetime = NOW,
) -> StrategyRestartFailure:
    return StrategyRestartFailure(
        strategy_id=StrategyId("strat_restart_policy_test"),
        failure_kind=failure_kind,
        reason_code="strategy_event_processing_failed",
        previous_restart_attempts=previous_restart_attempts,
        first_failure_at=first_failure_at,
        latest_failure_at=latest_failure_at,
    )
