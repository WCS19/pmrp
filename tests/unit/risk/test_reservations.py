"""Unit tests for capital reservation value objects."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from pmrp.risk import (
    CapitalReservation,
    CapitalReservationFactory,
    CapitalReservationStatus,
    RiskConfigurationError,
    RiskInputError,
    build_capital_reservation,
)
from pmrp.schemas.enums import ExchangeName, OrderType, RiskDecisionStatus, Side, TimeInForce
from pmrp.schemas.identifiers import AccountId, IntentId, MarketId, StrategyId
from pmrp.schemas.orders import OrderIntent
from pmrp.schemas.risk import RiskDecision, RiskRuleResult

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)
ACCOUNT_ID = AccountId("acct_01k00000000000000000000000")


def test_capital_reservation_accepts_valid_active_payload() -> None:
    reservation = _reservation()

    assert reservation.reservation_id == "reserve_01k00000000000000000000000"
    assert reservation.intent_id == IntentId("intent_01k00000000000000000000000")
    assert reservation.strategy_id == StrategyId("strat_risk_reservation")
    assert reservation.exchange is ExchangeName.KALSHI
    assert reservation.account_id == AccountId("acct_01k00000000000000000000000")
    assert reservation.market_id == MarketId("mkt_risk_reservation")
    assert reservation.quantity == Decimal("10")
    assert reservation.notional == Decimal("4.20")
    assert reservation.currency == "USD"
    assert reservation.status is CapitalReservationStatus.ACTIVE
    assert reservation.released_at is None


def test_capital_reservation_normalizes_utc_datetimes() -> None:
    reservation = _reservation(
        created_at=datetime(2026, 9, 22, 6, 0, tzinfo=timezone(timedelta(hours=-6))),
        expires_at=datetime(2026, 9, 22, 6, 5, tzinfo=timezone(timedelta(hours=-6))),
    )

    assert reservation.created_at == NOW
    assert reservation.expires_at == NOW + timedelta(minutes=5)


def test_capital_reservation_accepts_released_payload_with_release_time() -> None:
    reservation = _reservation(
        status=CapitalReservationStatus.RELEASED,
        released_at=NOW + timedelta(minutes=1),
    )

    assert reservation.status is CapitalReservationStatus.RELEASED
    assert reservation.released_at == NOW + timedelta(minutes=1)


@pytest.mark.parametrize(
    ("field_name", "override", "match"),
    [
        ("reservation_id", {"reservation_id": ""}, "must not be empty"),
        ("reservation_id_length", {"reservation_id": f"reserve_{'x' * 122}"}, "at most 128"),
        ("quantity", {"quantity": "0"}, "quantity must be positive"),
        ("notional", {"notional": "0"}, "notional must be positive"),
        ("currency", {"currency": "usd"}, "currency must be"),
        ("expires_at", {"expires_at": NOW}, "expires_at must be after"),
        (
            "released_at",
            {"released_at": NOW + timedelta(seconds=1)},
            "active capital reservation cannot have released_at",
        ),
        (
            "released_status",
            {"status": CapitalReservationStatus.RELEASED},
            "requires released_at",
        ),
        (
            "released_before_created",
            {
                "status": CapitalReservationStatus.RELEASED,
                "released_at": NOW - timedelta(seconds=1),
            },
            "cannot precede created_at",
        ),
    ],
)
def test_capital_reservation_rejects_invalid_payloads(
    field_name: str,
    override: dict[str, object],
    match: str,
) -> None:
    del field_name
    with pytest.raises((RiskConfigurationError, ValueError), match=match):
        _reservation(**override)


def test_capital_reservation_rejects_float_decimal_inputs() -> None:
    with pytest.raises(TypeError, match="float input"):
        _reservation(quantity=10.0)


def test_capital_reservation_factory_builds_active_reservation_from_approval() -> None:
    intent = _intent()
    decision = _decision()
    factory = CapitalReservationFactory(id_generator=_FixedReservationIdGenerator())

    reservation = factory.build(
        intent,
        decision,
        exchange=ExchangeName.KALSHI,
        account_id=ACCOUNT_ID,
        currency="USD",
    )

    assert reservation.reservation_id == "reserve_fixed_approved"
    assert reservation.intent_id == intent.intent_id
    assert reservation.strategy_id == intent.strategy_id
    assert reservation.exchange is ExchangeName.KALSHI
    assert reservation.account_id == ACCOUNT_ID
    assert reservation.market_id == intent.market_id
    assert reservation.quantity == decision.approved_quantity
    assert reservation.notional == Decimal("5.00")
    assert reservation.currency == "USD"
    assert reservation.status is CapitalReservationStatus.ACTIVE
    assert reservation.created_at == decision.evaluated_at
    assert reservation.expires_at == decision.approval_expires_at
    assert reservation.released_at is None


def test_default_capital_reservation_id_is_deterministic() -> None:
    intent = _intent()
    decision = _decision()

    first = build_capital_reservation(
        intent,
        decision,
        exchange=ExchangeName.KALSHI,
        account_id=ACCOUNT_ID,
        currency="USD",
    )
    second = build_capital_reservation(
        intent,
        decision,
        exchange=ExchangeName.KALSHI,
        account_id=ACCOUNT_ID,
        currency="USD",
    )

    assert first == second
    assert first.reservation_id.startswith("reserve_")


def test_default_capital_reservation_id_changes_with_decision() -> None:
    intent = _intent()

    first = build_capital_reservation(
        intent,
        _decision(risk_decision_id="risk_reservation_a"),
        exchange=ExchangeName.KALSHI,
        account_id=ACCOUNT_ID,
        currency="USD",
    )
    second = build_capital_reservation(
        intent,
        _decision(risk_decision_id="risk_reservation_b"),
        exchange=ExchangeName.KALSHI,
        account_id=ACCOUNT_ID,
        currency="USD",
    )

    assert first.reservation_id != second.reservation_id


@pytest.mark.parametrize(
    "status",
    [RiskDecisionStatus.REJECTED, RiskDecisionStatus.ERROR],
)
def test_capital_reservation_factory_rejects_non_approved_decisions(
    status: RiskDecisionStatus,
) -> None:
    decision = _decision(
        status=status,
        rule_results=(_result(passed=False, reason_code=f"RISK_TEST_{status.value}"),),
        approved_quantity=None,
        approved_limit_price=None,
        approval_expires_at=None,
    )

    with pytest.raises(RiskInputError, match="approved risk decision"):
        build_capital_reservation(
            _intent(),
            decision,
            exchange=ExchangeName.KALSHI,
            account_id=ACCOUNT_ID,
            currency="USD",
        )


def test_capital_reservation_factory_validates_approval_pair() -> None:
    with pytest.raises(RiskInputError, match="intent_id"):
        build_capital_reservation(
            _intent(),
            _decision(intent_id="intent_other_reservation"),
            exchange=ExchangeName.KALSHI,
            account_id=ACCOUNT_ID,
            currency="USD",
        )
    with pytest.raises(RiskInputError, match="correlation_id"):
        build_capital_reservation(
            _intent(),
            _decision(correlation_id="corr_other_reservation"),
            exchange=ExchangeName.KALSHI,
            account_id=ACCOUNT_ID,
            currency="USD",
        )
    with pytest.raises(RiskInputError, match="approved quantity"):
        build_capital_reservation(
            _intent(),
            _decision(approved_quantity=Decimal("11")),
            exchange=ExchangeName.KALSHI,
            account_id=ACCOUNT_ID,
            currency="USD",
        )
    with pytest.raises(RiskInputError, match="approval_expires_at"):
        build_capital_reservation(
            _intent(),
            _decision(approval_expires_at=None),
            exchange=ExchangeName.KALSHI,
            account_id=ACCOUNT_ID,
            currency="USD",
        )


def test_capital_reservation_factory_validates_inputs_and_generated_id() -> None:
    with pytest.raises(RiskConfigurationError, match="ID generator"):
        CapitalReservationFactory(id_generator=object())  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="currency"):
        build_capital_reservation(
            _intent(),
            _decision(),
            exchange=ExchangeName.KALSHI,
            account_id=ACCOUNT_ID,
            currency="usd",
        )
    with pytest.raises(RiskConfigurationError, match="notional"):
        build_capital_reservation(
            _intent(),
            _decision(approved_limit_price=Decimal("0")),
            exchange=ExchangeName.KALSHI,
            account_id=ACCOUNT_ID,
            currency="USD",
        )
    with pytest.raises(RiskConfigurationError, match="must not be empty"):
        CapitalReservationFactory(id_generator=_InvalidReservationIdGenerator()).build(
            _intent(),
            _decision(),
            exchange=ExchangeName.KALSHI,
            account_id=ACCOUNT_ID,
            currency="USD",
        )


def _reservation(**overrides: object) -> CapitalReservation:
    payload: dict[str, object] = {
        "reservation_id": "reserve_01k00000000000000000000000",
        "intent_id": "intent_01k00000000000000000000000",
        "strategy_id": "strat_risk_reservation",
        "exchange": ExchangeName.KALSHI,
        "account_id": "acct_01k00000000000000000000000",
        "market_id": "mkt_risk_reservation",
        "quantity": "10",
        "notional": "4.20",
        "currency": "USD",
        "status": CapitalReservationStatus.ACTIVE,
        "created_at": NOW,
        "expires_at": NOW + timedelta(minutes=5),
        "released_at": None,
    }
    payload.update(overrides)
    return CapitalReservation(**payload)  # type: ignore[arg-type]


def _intent() -> OrderIntent:
    return OrderIntent.model_validate(
        {
            "intent_id": "intent_risk_reservation",
            "strategy_id": "strat_risk_reservation",
            "market_id": "mkt_risk_reservation",
            "contract_id": "ctr_risk_reservation",
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
            "correlation_id": "corr_risk_reservation",
            "idempotency_key": "idem-risk-reservation-intent",
        }
    )


def _decision(
    *,
    risk_decision_id: str = "risk_reservation",
    intent_id: str = "intent_risk_reservation",
    status: RiskDecisionStatus = RiskDecisionStatus.APPROVED,
    rule_results: tuple[RiskRuleResult, ...] | None = None,
    approved_quantity: Decimal | None = Decimal("10"),
    approved_limit_price: Decimal | None = Decimal("0.50"),
    approval_expires_at: datetime | None = NOW + timedelta(seconds=2),
    correlation_id: str = "corr_risk_reservation",
) -> RiskDecision:
    return RiskDecision(
        risk_decision_id=risk_decision_id,
        intent_id=intent_id,
        status=status,
        evaluated_at=NOW,
        input_snapshot_id="risk_input_reservation",
        rule_results=rule_results or (_result(),),
        approved_quantity=approved_quantity,
        approved_limit_price=approved_limit_price,
        approval_expires_at=approval_expires_at,
        configuration_hash="sha256:config",
        correlation_id=correlation_id,
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


class _FixedReservationIdGenerator:
    def reservation_id(
        self,
        *,
        intent: OrderIntent,
        decision: RiskDecision,
        exchange: ExchangeName,
        account_id: AccountId,
        currency: str,
    ) -> str:
        del intent, decision, exchange, account_id, currency
        return "reserve_fixed_approved"


class _InvalidReservationIdGenerator:
    def reservation_id(
        self,
        *,
        intent: OrderIntent,
        decision: RiskDecision,
        exchange: ExchangeName,
        account_id: AccountId,
        currency: str,
    ) -> str:
        del intent, decision, exchange, account_id, currency
        return ""
