"""Deterministic strategy restart policy primitives."""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from typing import Protocol

from pmrp.clock.protocol import normalize_clock_datetime
from pmrp.schemas.identifiers import StrategyId
from pmrp.strategies.errors import StrategyRestartPolicyError


class StrategyRestartFailureKind(StrEnum):
    """Classified strategy failures eligible for configured restart decisions."""

    INITIALIZATION = "initialization"
    SUBSCRIPTION = "subscription"
    EVENT_PROCESSING = "event_processing"
    SHUTDOWN = "shutdown"


@dataclass(frozen=True, slots=True)
class StrategyRestartFailure:
    """Safe diagnostic input for evaluating one strategy restart decision."""

    strategy_id: StrategyId
    failure_kind: StrategyRestartFailureKind
    reason_code: str
    previous_restart_attempts: int
    first_failure_at: datetime
    latest_failure_at: datetime

    def __post_init__(self) -> None:
        if not isinstance(self.strategy_id, StrategyId):
            raise StrategyRestartPolicyError(
                "strategy_id must be a StrategyId",
                reason_code="strategy_restart_strategy_id_invalid",
            )
        failure_kind = _validate_failure_kind(self.failure_kind)
        reason_code = _validate_required_text(self.reason_code, field_name="reason_code")
        previous_restart_attempts = _validate_nonnegative_int(
            self.previous_restart_attempts,
            field_name="previous_restart_attempts",
        )
        first_failure_at = normalize_clock_datetime(self.first_failure_at)
        latest_failure_at = normalize_clock_datetime(self.latest_failure_at)
        if latest_failure_at < first_failure_at:
            raise StrategyRestartPolicyError(
                "latest_failure_at must not be before first_failure_at",
                reason_code="strategy_restart_failure_time_order_invalid",
                context={
                    "strategy_id": str(self.strategy_id),
                    "failure_kind": failure_kind.value,
                },
            )

        object.__setattr__(self, "failure_kind", failure_kind)
        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "previous_restart_attempts", previous_restart_attempts)
        object.__setattr__(self, "first_failure_at", first_failure_at)
        object.__setattr__(self, "latest_failure_at", latest_failure_at)


@dataclass(frozen=True, slots=True)
class StrategyRestartDecision:
    """Deterministic restart verdict returned by a configured policy."""

    should_restart: bool
    reason_code: str
    next_attempt: int | None = None
    restart_after: datetime | None = None
    backoff: timedelta = timedelta(0)
    jitter: timedelta = timedelta(0)

    def __post_init__(self) -> None:
        if type(self.should_restart) is not bool:
            raise StrategyRestartPolicyError(
                "should_restart must be a bool",
                reason_code="strategy_restart_decision_invalid",
            )
        reason_code = _validate_required_text(self.reason_code, field_name="reason_code")
        backoff = _validate_nonnegative_duration(self.backoff, field_name="backoff")
        jitter = _validate_nonnegative_duration(self.jitter, field_name="jitter")
        restart_after = (
            None if self.restart_after is None else normalize_clock_datetime(self.restart_after)
        )

        if self.should_restart:
            next_attempt = _validate_positive_int(self.next_attempt, field_name="next_attempt")
            if restart_after is None:
                raise StrategyRestartPolicyError(
                    "restart_after is required when restart is allowed",
                    reason_code="strategy_restart_decision_invalid",
                )
        else:
            _validate_absent(self.next_attempt, field_name="next_attempt")
            next_attempt = None
            if restart_after is not None:
                raise StrategyRestartPolicyError(
                    "restart_after must be absent when restart is denied",
                    reason_code="strategy_restart_decision_invalid",
                )

        object.__setattr__(self, "reason_code", reason_code)
        object.__setattr__(self, "next_attempt", next_attempt)
        object.__setattr__(self, "restart_after", restart_after)
        object.__setattr__(self, "backoff", backoff)
        object.__setattr__(self, "jitter", jitter)


class StrategyRestartPolicy(Protocol):
    """Visible, testable restart policy contract for strategy runtime failures."""

    def decide(self, failure: StrategyRestartFailure) -> StrategyRestartDecision:
        """Return the deterministic decision for a classified strategy failure."""
        ...


@dataclass(frozen=True, slots=True)
class NeverRestartPolicy:
    """Fail-closed strategy restart policy."""

    reason_code: str = "strategy_restart_policy_disabled"

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "reason_code",
            _validate_required_text(self.reason_code, field_name="reason_code"),
        )

    def decide(self, failure: StrategyRestartFailure) -> StrategyRestartDecision:
        """Always deny automatic strategy restart."""

        _validate_restart_failure(failure)
        return StrategyRestartDecision(
            should_restart=False,
            reason_code=self.reason_code,
        )


@dataclass(frozen=True, slots=True)
class BoundedRestartPolicy:
    """Bounded restart policy with explicit eligibility, backoff, jitter, and deadline."""

    max_attempts: int
    restartable_failure_kinds: Collection[StrategyRestartFailureKind]
    backoff: timedelta
    deadline: timedelta
    jitter: timedelta = timedelta(0)

    def __post_init__(self) -> None:
        max_attempts = _validate_positive_int(self.max_attempts, field_name="max_attempts")
        restartable_failure_kinds = _validate_failure_kinds(self.restartable_failure_kinds)
        backoff = _validate_nonnegative_duration(self.backoff, field_name="backoff")
        deadline = _validate_positive_duration(self.deadline, field_name="deadline")
        jitter = _validate_nonnegative_duration(self.jitter, field_name="jitter")

        object.__setattr__(self, "max_attempts", max_attempts)
        object.__setattr__(self, "restartable_failure_kinds", restartable_failure_kinds)
        object.__setattr__(self, "backoff", backoff)
        object.__setattr__(self, "deadline", deadline)
        object.__setattr__(self, "jitter", jitter)

    def decide(self, failure: StrategyRestartFailure) -> StrategyRestartDecision:
        """Evaluate whether a classified strategy failure may restart."""

        _validate_restart_failure(failure)
        if failure.failure_kind not in self.restartable_failure_kinds:
            return _deny("strategy_restart_failure_kind_not_restartable")
        if failure.previous_restart_attempts >= self.max_attempts:
            return _deny("strategy_restart_attempts_exhausted")
        if failure.latest_failure_at - failure.first_failure_at > self.deadline:
            return _deny("strategy_restart_deadline_exceeded")

        return StrategyRestartDecision(
            should_restart=True,
            reason_code="strategy_restart_allowed",
            next_attempt=failure.previous_restart_attempts + 1,
            restart_after=failure.latest_failure_at + self.backoff,
            backoff=self.backoff,
            jitter=self.jitter,
        )


def _deny(reason_code: str) -> StrategyRestartDecision:
    return StrategyRestartDecision(should_restart=False, reason_code=reason_code)


def _validate_restart_failure(failure: StrategyRestartFailure) -> None:
    if not isinstance(failure, StrategyRestartFailure):
        raise StrategyRestartPolicyError(
            "failure must be a StrategyRestartFailure",
            reason_code="strategy_restart_failure_invalid",
        )


def _validate_failure_kind(value: StrategyRestartFailureKind) -> StrategyRestartFailureKind:
    if not isinstance(value, StrategyRestartFailureKind):
        raise StrategyRestartPolicyError(
            "failure_kind must be a StrategyRestartFailureKind",
            reason_code="strategy_restart_failure_kind_invalid",
            context={"failure_kind": type(value).__name__},
        )
    return value


def _validate_failure_kinds(
    values: Collection[StrategyRestartFailureKind],
) -> frozenset[StrategyRestartFailureKind]:
    if isinstance(values, str) or not isinstance(values, Collection):
        raise StrategyRestartPolicyError(
            "restartable_failure_kinds must be a nonempty collection",
            reason_code="strategy_restart_failure_kinds_invalid",
        )
    failure_kinds = frozenset(_validate_failure_kind(value) for value in values)
    if not failure_kinds:
        raise StrategyRestartPolicyError(
            "restartable_failure_kinds must be nonempty",
            reason_code="strategy_restart_failure_kinds_invalid",
        )
    return failure_kinds


def _validate_required_text(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        raise StrategyRestartPolicyError(
            f"{field_name} must be a string",
            reason_code="strategy_restart_text_invalid",
        )
    if value == "" or value.strip() != value:
        raise StrategyRestartPolicyError(
            f"{field_name} must be nonempty without surrounding whitespace",
            reason_code="strategy_restart_text_invalid",
        )
    return value


def _validate_nonnegative_int(value: int, *, field_name: str) -> int:
    if type(value) is not int:
        raise StrategyRestartPolicyError(
            f"{field_name} must be an int",
            reason_code="strategy_restart_count_invalid",
        )
    if value < 0:
        raise StrategyRestartPolicyError(
            f"{field_name} must not be negative",
            reason_code="strategy_restart_count_invalid",
            context={field_name: str(value)},
        )
    return value


def _validate_positive_int(value: int | None, *, field_name: str) -> int:
    if type(value) is not int:
        raise StrategyRestartPolicyError(
            f"{field_name} must be an int",
            reason_code="strategy_restart_count_invalid",
        )
    if value < 1:
        raise StrategyRestartPolicyError(
            f"{field_name} must be positive",
            reason_code="strategy_restart_count_invalid",
            context={field_name: str(value)},
        )
    return value


def _validate_absent(value: int | None, *, field_name: str) -> None:
    if value is not None:
        raise StrategyRestartPolicyError(
            f"{field_name} must be absent",
            reason_code="strategy_restart_decision_invalid",
        )
    return None


def _validate_nonnegative_duration(value: timedelta, *, field_name: str) -> timedelta:
    if not isinstance(value, timedelta):
        raise StrategyRestartPolicyError(
            f"{field_name} must be a timedelta",
            reason_code="strategy_restart_duration_invalid",
        )
    if value < timedelta(0):
        raise StrategyRestartPolicyError(
            f"{field_name} must not be negative",
            reason_code="strategy_restart_duration_invalid",
        )
    return value


def _validate_positive_duration(value: timedelta, *, field_name: str) -> timedelta:
    if not isinstance(value, timedelta):
        raise StrategyRestartPolicyError(
            f"{field_name} must be a timedelta",
            reason_code="strategy_restart_duration_invalid",
        )
    if value <= timedelta(0):
        raise StrategyRestartPolicyError(
            f"{field_name} must be positive",
            reason_code="strategy_restart_duration_invalid",
        )
    return value
