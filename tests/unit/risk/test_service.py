"""Unit tests for the risk evaluation application service."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from types import TracebackType
from typing import Literal

import pytest

from pmrp.risk import (
    ApprovedOrderFactory,
    CapitalReservation,
    CapitalReservationStatus,
    RiskApprovedOrderRequest,
    RiskCapitalReservationRequest,
    RiskConfigurationError,
    RiskContext,
    RiskEvaluationResult,
    RiskEvaluationService,
    build_approved_order,
)
from pmrp.risk.breaches import RiskBreachFactory, RiskBreachPolicy
from pmrp.schemas.enums import ExchangeName, OrderType, RiskDecisionStatus, Side, TimeInForce
from pmrp.schemas.identifiers import AccountId, ContractId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskBreach, RiskDecision, RiskLimitScope, RiskRuleResult

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
MARKET_ID = MarketId("mkt_risk_service")
CONTRACT_ID = ContractId("ctr_risk_service")
STRATEGY_ID = StrategyId("strat_risk_service")
ACCOUNT_ID = AccountId("acct_01k00000000000000000000000")
INPUT_SNAPSHOT_ID = "risk_input_01k0000000000000000"


async def test_risk_evaluation_service_persists_and_commits_decision() -> None:
    decision = _decision()
    engine = _FakeEvaluator(decision=decision)
    unit_of_work = _FakeUnitOfWork()
    service = RiskEvaluationService(engine=engine, unit_of_work_factory=lambda: unit_of_work)
    intent = _intent()
    context = RiskContext(evaluated_at=NOW)

    result = await service.evaluate_and_persist(
        intent,
        context,
        input_snapshot_id=INPUT_SNAPSHOT_ID,
    )

    assert result == decision
    assert engine.calls == [(intent, context, INPUT_SNAPSHOT_ID)]
    assert unit_of_work.entered == 1
    assert unit_of_work.store.added == [decision]
    assert unit_of_work.committed == 1
    assert unit_of_work.rolled_back == 0
    assert unit_of_work.exited == 1


async def test_risk_evaluation_service_persists_rejections() -> None:
    decision = _decision(
        status=RiskDecisionStatus.REJECTED,
        rule_results=(_result(passed=False, reason_code="RISK_TEST_REJECTED"),),
        approved_quantity=None,
        approved_limit_price=None,
        approval_expires_at=None,
    )
    unit_of_work = _FakeUnitOfWork()
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=decision),
        unit_of_work_factory=lambda: unit_of_work,
    )

    result = await service.evaluate_and_persist(
        _intent(),
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
    )

    assert result.status is RiskDecisionStatus.REJECTED
    assert unit_of_work.store.added == [decision]
    assert unit_of_work.committed == 1


async def test_risk_evaluation_service_persists_configured_breaches() -> None:
    decision = _decision(
        status=RiskDecisionStatus.REJECTED,
        rule_results=(_result(passed=False, reason_code="RISK_STRATEGY_CAPITAL_ABOVE_MAX"),),
        approved_quantity=None,
        approved_limit_price=None,
        approval_expires_at=None,
    )
    unit_of_work = _FakeUnitOfWork()
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=decision),
        unit_of_work_factory=lambda: unit_of_work,
        breach_factory=RiskBreachFactory(
            policies=(
                RiskBreachPolicy(
                    rule_id="RISK-TEST",
                    reason_code="RISK_STRATEGY_CAPITAL_ABOVE_MAX",
                    scope=RiskLimitScope.STRATEGY,
                    scope_id="strat_risk_service",
                    severity="critical",
                    action_taken="reject_order",
                ),
            )
        ),
    )

    result = await service.evaluate_and_persist(
        _intent(),
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
    )

    assert result == decision
    assert unit_of_work.store.added == [decision]
    assert len(unit_of_work.breach_store.added) == 1
    breach = unit_of_work.breach_store.added[0]
    assert breach.rule_id == "RISK-TEST"
    assert breach.scope is RiskLimitScope.STRATEGY
    assert breach.scope_id == "strat_risk_service"
    assert breach.severity == "critical"
    assert breach.action_taken == "reject_order"
    assert breach.correlation_id == decision.correlation_id
    assert unit_of_work.committed == 1


async def test_risk_evaluation_service_persists_reservation_for_approved_decision() -> None:
    decision = _decision()
    unit_of_work = _FakeUnitOfWork()
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=decision),
        unit_of_work_factory=lambda: unit_of_work,
    )
    intent = _intent()

    result = await service.evaluate_and_persist(
        intent,
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
        reservation_request=_reservation_request(),
    )

    assert result == decision
    assert unit_of_work.store.added == [decision]
    assert len(unit_of_work.reservation_store.added) == 1
    reservation = unit_of_work.reservation_store.added[0]
    assert reservation.intent_id == intent.intent_id
    assert reservation.strategy_id == intent.strategy_id
    assert reservation.exchange is ExchangeName.KALSHI
    assert reservation.account_id == ACCOUNT_ID
    assert reservation.market_id == intent.market_id
    assert reservation.quantity == Decimal("10")
    assert reservation.notional == Decimal("5.00")
    assert reservation.currency == "USD"
    assert reservation.status is CapitalReservationStatus.ACTIVE
    assert reservation.created_at == decision.evaluated_at
    assert reservation.expires_at == decision.approval_expires_at
    assert unit_of_work.committed == 1


async def test_risk_evaluation_service_result_derives_approved_order() -> None:
    decision = _decision()
    unit_of_work = _FakeUnitOfWork()
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=decision),
        unit_of_work_factory=lambda: unit_of_work,
    )
    intent = _intent()

    result = await service.evaluate_and_persist_result(
        intent,
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
        approved_order_request=_approved_order_request(),
    )

    assert result.decision == decision
    assert result.capital_reservation is None
    assert result.approved_order is not None
    approved_order = result.approved_order
    assert approved_order.intent_id == intent.intent_id
    assert approved_order.strategy_id == intent.strategy_id
    assert approved_order.risk_decision_id == decision.risk_decision_id
    assert approved_order.exchange == ExchangeName.KALSHI.value
    assert approved_order.account_id == ACCOUNT_ID
    assert approved_order.quantity == decision.approved_quantity
    assert approved_order.limit_price == decision.approved_limit_price
    assert approved_order.approved_at == decision.evaluated_at
    assert approved_order.approval_expires_at == decision.approval_expires_at
    assert approved_order.correlation_id == intent.correlation_id
    assert unit_of_work.store.added == [decision]
    assert unit_of_work.reservation_store.added == []
    assert unit_of_work.committed == 1


async def test_risk_evaluation_service_result_returns_requested_reservation() -> None:
    decision = _decision()
    unit_of_work = _FakeUnitOfWork()
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=decision),
        unit_of_work_factory=lambda: unit_of_work,
    )

    result = await service.evaluate_and_persist_result(
        _intent(),
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
        approved_order_request=_approved_order_request(),
        reservation_request=_reservation_request(),
    )

    assert result.decision == decision
    assert result.approved_order is not None
    assert result.capital_reservation is not None
    assert result.capital_reservation == unit_of_work.reservation_store.added[0]
    assert unit_of_work.committed == 1


async def test_risk_evaluation_service_skips_reservation_for_rejected_decision() -> None:
    decision = _decision(
        status=RiskDecisionStatus.REJECTED,
        rule_results=(_result(passed=False, reason_code="RISK_TEST_REJECTED"),),
        approved_quantity=None,
        approved_limit_price=None,
        approval_expires_at=None,
    )
    unit_of_work = _FakeUnitOfWork()
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=decision),
        unit_of_work_factory=lambda: unit_of_work,
    )

    result = await service.evaluate_and_persist(
        _intent(),
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
        reservation_request=_reservation_request(),
    )

    assert result == decision
    assert unit_of_work.store.added == [decision]
    assert unit_of_work.reservation_store.added == []
    assert unit_of_work.committed == 1


async def test_risk_evaluation_service_result_skips_approved_order_for_rejection() -> None:
    decision = _decision(
        status=RiskDecisionStatus.REJECTED,
        rule_results=(_result(passed=False, reason_code="RISK_TEST_REJECTED"),),
        approved_quantity=None,
        approved_limit_price=None,
        approval_expires_at=None,
    )
    unit_of_work = _FakeUnitOfWork()
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=decision),
        unit_of_work_factory=lambda: unit_of_work,
    )

    result = await service.evaluate_and_persist_result(
        _intent(),
        RiskContext(evaluated_at=NOW),
        input_snapshot_id=INPUT_SNAPSHOT_ID,
        approved_order_request=_approved_order_request(),
    )

    assert result.decision == decision
    assert result.approved_order is None
    assert result.capital_reservation is None
    assert unit_of_work.committed == 1


async def test_risk_evaluation_service_rolls_back_when_reservation_persist_fails() -> None:
    unit_of_work = _FakeUnitOfWork(
        reservation_store_error=RuntimeError("reservation persist failed")
    )
    decision = _decision()
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=decision),
        unit_of_work_factory=lambda: unit_of_work,
    )

    with pytest.raises(RuntimeError, match="reservation persist failed"):
        await service.evaluate_and_persist(
            _intent(),
            RiskContext(evaluated_at=NOW),
            input_snapshot_id=INPUT_SNAPSHOT_ID,
            reservation_request=_reservation_request(),
        )

    assert unit_of_work.store.added == [decision]
    assert unit_of_work.reservation_store.added == []
    assert unit_of_work.committed == 0
    assert unit_of_work.rolled_back == 1
    assert unit_of_work.exit_error_type is RuntimeError


async def test_risk_evaluation_service_rolls_back_when_approved_order_build_fails() -> None:
    unit_of_work = _FakeUnitOfWork()
    decision = _decision()
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=decision),
        unit_of_work_factory=lambda: unit_of_work,
        approved_order_factory=ApprovedOrderFactory(
            reference_generator=_InvalidApprovedOrderReferences()
        ),
    )

    with pytest.raises(RiskConfigurationError, match="ApprovedOrderReferences"):
        await service.evaluate_and_persist_result(
            _intent(),
            RiskContext(evaluated_at=NOW),
            input_snapshot_id=INPUT_SNAPSHOT_ID,
            approved_order_request=_approved_order_request(),
        )

    assert unit_of_work.store.added == [decision]
    assert unit_of_work.reservation_store.added == []
    assert unit_of_work.committed == 0
    assert unit_of_work.rolled_back == 1
    assert unit_of_work.exit_error_type is RiskConfigurationError


def test_risk_approved_order_request_validates_metadata() -> None:
    request = RiskApprovedOrderRequest(
        exchange=ExchangeName.KALSHI,
        account_id=ACCOUNT_ID,
    )

    assert request.exchange is ExchangeName.KALSHI
    assert request.account_id == ACCOUNT_ID

    with pytest.raises(ValueError, match="valid"):
        RiskApprovedOrderRequest(
            exchange="unknown",  # type: ignore[arg-type]
            account_id=ACCOUNT_ID,
        )


def test_risk_evaluation_result_rejects_non_approved_artifacts() -> None:
    approved_order = build_approved_order(
        _intent(),
        _decision(),
        exchange=ExchangeName.KALSHI.value,
        account_id=ACCOUNT_ID,
    )
    rejected_decision = _decision(
        status=RiskDecisionStatus.REJECTED,
        rule_results=(_result(passed=False, reason_code="RISK_TEST_REJECTED"),),
        approved_quantity=None,
        approved_limit_price=None,
        approval_expires_at=None,
    )

    with pytest.raises(ValueError, match="non-approved"):
        RiskEvaluationResult(decision=rejected_decision, approved_order=approved_order)


def test_risk_capital_reservation_request_validates_metadata() -> None:
    request = RiskCapitalReservationRequest(
        exchange=ExchangeName.KALSHI,
        account_id=ACCOUNT_ID,
        currency="USD",
    )

    assert request.exchange is ExchangeName.KALSHI
    assert request.account_id == ACCOUNT_ID
    assert request.currency == "USD"

    with pytest.raises(ValueError, match="currency"):
        RiskCapitalReservationRequest(
            exchange=ExchangeName.KALSHI,
            account_id=ACCOUNT_ID,
            currency="usd",
        )


async def test_risk_evaluation_service_rolls_back_when_breach_persist_fails() -> None:
    decision = _decision(
        status=RiskDecisionStatus.REJECTED,
        rule_results=(_result(passed=False, reason_code="RISK_BREACH_TEST"),),
        approved_quantity=None,
        approved_limit_price=None,
        approval_expires_at=None,
    )
    unit_of_work = _FakeUnitOfWork(breach_store_error=RuntimeError("breach persist failed"))
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=decision),
        unit_of_work_factory=lambda: unit_of_work,
        breach_factory=RiskBreachFactory(
            policies=(
                RiskBreachPolicy(
                    rule_id="RISK-TEST",
                    reason_code="RISK_BREACH_TEST",
                    scope=RiskLimitScope.GLOBAL,
                    severity="critical",
                    action_taken="reject_order",
                ),
            )
        ),
    )

    with pytest.raises(RuntimeError, match="breach persist failed"):
        await service.evaluate_and_persist(
            _intent(),
            RiskContext(evaluated_at=NOW),
            input_snapshot_id=INPUT_SNAPSHOT_ID,
        )

    assert unit_of_work.store.added == [decision]
    assert unit_of_work.breach_store.added == []
    assert unit_of_work.committed == 0
    assert unit_of_work.rolled_back == 1
    assert unit_of_work.exit_error_type is RuntimeError


async def test_risk_evaluation_service_rolls_back_when_evaluation_fails() -> None:
    unit_of_work = _FakeUnitOfWork()
    service = RiskEvaluationService(
        engine=_FakeEvaluator(error=RuntimeError("evaluation failed")),
        unit_of_work_factory=lambda: unit_of_work,
    )

    with pytest.raises(RuntimeError, match="evaluation failed"):
        await service.evaluate_and_persist(
            _intent(),
            RiskContext(evaluated_at=NOW),
            input_snapshot_id=INPUT_SNAPSHOT_ID,
        )

    assert unit_of_work.store.added == []
    assert unit_of_work.committed == 0
    assert unit_of_work.rolled_back == 1
    assert unit_of_work.exited == 1
    assert unit_of_work.exit_error_type is RuntimeError


async def test_risk_evaluation_service_rolls_back_when_persist_fails() -> None:
    unit_of_work = _FakeUnitOfWork(store_error=RuntimeError("persist failed"))
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=_decision()),
        unit_of_work_factory=lambda: unit_of_work,
    )

    with pytest.raises(RuntimeError, match="persist failed"):
        await service.evaluate_and_persist(
            _intent(),
            RiskContext(evaluated_at=NOW),
            input_snapshot_id=INPUT_SNAPSHOT_ID,
        )

    assert unit_of_work.committed == 0
    assert unit_of_work.rolled_back == 1
    assert unit_of_work.exit_error_type is RuntimeError


async def test_risk_evaluation_service_rolls_back_when_commit_fails() -> None:
    unit_of_work = _FakeUnitOfWork(commit_error=RuntimeError("commit failed"))
    decision = _decision()
    service = RiskEvaluationService(
        engine=_FakeEvaluator(decision=decision),
        unit_of_work_factory=lambda: unit_of_work,
    )

    with pytest.raises(RuntimeError, match="commit failed"):
        await service.evaluate_and_persist(
            _intent(),
            RiskContext(evaluated_at=NOW),
            input_snapshot_id=INPUT_SNAPSHOT_ID,
        )

    assert unit_of_work.store.added == [decision]
    assert unit_of_work.committed == 0
    assert unit_of_work.rolled_back == 1
    assert unit_of_work.exit_error_type is RuntimeError


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_service",
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
            "urgency": "0.50",
            "created_at": NOW,
            "expires_at": NOW + timedelta(seconds=5),
            "signal_ids": (),
            "correlation_id": "corr_risk_service",
            "idempotency_key": "idem-risk-service",
        }
    )


def _reservation_request() -> RiskCapitalReservationRequest:
    return RiskCapitalReservationRequest(
        exchange=ExchangeName.KALSHI,
        account_id=ACCOUNT_ID,
        currency="USD",
    )


def _approved_order_request() -> RiskApprovedOrderRequest:
    return RiskApprovedOrderRequest(
        exchange=ExchangeName.KALSHI,
        account_id=ACCOUNT_ID,
    )


def _decision(
    *,
    status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
    rule_results: tuple[RiskRuleResult, ...] | None = None,
    approved_quantity: Decimal | None = Decimal("10"),
    approved_limit_price: Decimal | None = Decimal("0.50"),
    approval_expires_at: datetime | None = NOW + timedelta(seconds=2),
) -> RiskDecision:
    return RiskDecision(
        risk_decision_id="risk_01k00000000000000000000000",
        intent_id="intent_risk_service",
        status=status,
        evaluated_at=NOW,
        input_snapshot_id=INPUT_SNAPSHOT_ID,
        rule_results=rule_results or (_result(),),
        approved_quantity=approved_quantity,
        approved_limit_price=approved_limit_price,
        approval_expires_at=approval_expires_at,
        configuration_hash="sha256:config",
        correlation_id="corr_risk_service",
    )


def _result(*, passed: bool = True, reason_code: str = "RISK_TEST_VALID") -> RiskRuleResult:
    return RiskRuleResult(
        rule_id="RISK-TEST",
        rule_version="1.0",
        passed=passed,
        reason_code=reason_code,
        reason_text=None,
        observed_value=Decimal("1"),
        limit_value=Decimal("2"),
        unit="test",
        evaluated_at=NOW,
    )


class _FakeEvaluator:
    def __init__(
        self,
        *,
        decision: RiskDecision | None = None,
        error: Exception | None = None,
    ) -> None:
        self._decision = decision
        self._error = error
        self.calls: list[tuple[OrderIntent, RiskContext, str]] = []

    async def evaluate(
        self,
        intent: OrderIntent,
        context: RiskContext,
        *,
        input_snapshot_id: str,
    ) -> RiskDecision:
        self.calls.append((intent, context, input_snapshot_id))
        if self._error is not None:
            raise self._error
        if self._decision is None:
            raise AssertionError("test evaluator decision is not configured")
        return self._decision


class _FakeDecisionStore:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.added: list[RiskDecision] = []

    async def add(self, decision: RiskDecision) -> None:
        if self._error is not None:
            raise self._error
        self.added.append(decision)


class _FakeBreachStore:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.added: list[RiskBreach] = []

    async def add(self, breach: RiskBreach) -> None:
        if self._error is not None:
            raise self._error
        self.added.append(breach)


class _FakeReservationStore:
    def __init__(self, *, error: Exception | None = None) -> None:
        self._error = error
        self.added: list[CapitalReservation] = []

    async def add(self, reservation: CapitalReservation) -> None:
        if self._error is not None:
            raise self._error
        self.added.append(reservation)


class _InvalidApprovedOrderReferences:
    def references(
        self,
        *,
        intent: OrderIntent,
        decision: RiskDecision,
        exchange: str,
        account_id: AccountId,
    ) -> object:
        del intent, decision, exchange, account_id
        return object()


class _FakeUnitOfWork:
    def __init__(
        self,
        *,
        store_error: Exception | None = None,
        breach_store_error: Exception | None = None,
        reservation_store_error: Exception | None = None,
        commit_error: Exception | None = None,
    ) -> None:
        self.store = _FakeDecisionStore(error=store_error)
        self.breach_store = _FakeBreachStore(error=breach_store_error)
        self.reservation_store = _FakeReservationStore(error=reservation_store_error)
        self._commit_error = commit_error
        self.entered = 0
        self.exited = 0
        self.committed = 0
        self.rolled_back = 0
        self.exit_error_type: type[BaseException] | None = None

    async def __aenter__(self) -> _FakeUnitOfWork:
        self.entered += 1
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> Literal[False]:
        del exc, traceback
        self.exited += 1
        self.exit_error_type = exc_type
        if self.committed == 0:
            self.rolled_back += 1
        return False

    @property
    def risk_decisions(self) -> _FakeDecisionStore:
        return self.store

    @property
    def risk_breaches(self) -> _FakeBreachStore:
        return self.breach_store

    @property
    def capital_reservations(self) -> _FakeReservationStore:
        return self.reservation_store

    async def commit(self) -> None:
        if self._commit_error is not None:
            raise self._commit_error
        self.committed += 1
