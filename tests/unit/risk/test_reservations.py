"""Unit tests for capital reservation value objects."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal

import pytest

from pmrp.risk import CapitalReservation, CapitalReservationStatus, RiskConfigurationError
from pmrp.schemas.enums import ExchangeName
from pmrp.schemas.identifiers import AccountId, IntentId, MarketId, StrategyId

pytestmark = pytest.mark.unit

NOW = datetime(2026, 9, 22, 12, 0, tzinfo=UTC)


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
