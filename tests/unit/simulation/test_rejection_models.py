"""Simulation rejection model tests."""

from __future__ import annotations

from decimal import Decimal

import pytest

from pmrp.schemas.enums import MarketStatus
from pmrp.simulation import (
    BOUNDED_REJECTION_MODEL_NAME,
    BoundedRejectionModel,
    RejectionModel,
    RejectionReason,
    SimulationInputError,
)

pytestmark = pytest.mark.unit


def test_bounded_rejection_model_accepts_valid_order() -> None:
    model = BoundedRejectionModel()

    decision = model.evaluate(
        market_status=MarketStatus.OPEN,
        price=Decimal("0.42"),
        quantity=Decimal("10"),
        required_balance=Decimal("4.20"),
        available_balance=Decimal("10.00"),
    )

    assert BOUNDED_REJECTION_MODEL_NAME == "bounded_rejection_v1"
    assert isinstance(model, RejectionModel)
    assert decision.accepted
    assert not decision.rejected
    assert decision.reason_code is RejectionReason.ACCEPTED
    assert decision.reason_text == "order accepted by simulation rejection model"


def test_bounded_rejection_model_rejects_invalid_price() -> None:
    model = BoundedRejectionModel(min_price=Decimal("0.01"), max_price=Decimal("0.99"))

    assert (
        model.evaluate(
            market_status=MarketStatus.OPEN,
            price=None,
            quantity=Decimal("10"),
        ).reason_code
        is RejectionReason.INVALID_PRICE
    )
    assert (
        model.evaluate(
            market_status=MarketStatus.OPEN,
            price=Decimal("-0.01"),
            quantity=Decimal("10"),
        ).reason_code
        is RejectionReason.INVALID_PRICE
    )
    assert (
        model.evaluate(
            market_status=MarketStatus.OPEN,
            price=Decimal("0"),
            quantity=Decimal("10"),
        ).reason_code
        is RejectionReason.INVALID_PRICE
    )
    assert (
        model.evaluate(
            market_status=MarketStatus.OPEN,
            price=Decimal("1.00"),
            quantity=Decimal("10"),
        ).reason_code
        is RejectionReason.INVALID_PRICE
    )


def test_bounded_rejection_model_rejects_invalid_quantity() -> None:
    model = BoundedRejectionModel(min_quantity=Decimal("1"), max_quantity=Decimal("100"))

    assert (
        model.evaluate(
            market_status=MarketStatus.OPEN,
            price=Decimal("0.42"),
            quantity=Decimal("0"),
        ).reason_code
        is RejectionReason.INVALID_QUANTITY
    )
    assert (
        model.evaluate(
            market_status=MarketStatus.OPEN,
            price=Decimal("0.42"),
            quantity=Decimal("0.5"),
        ).reason_code
        is RejectionReason.INVALID_QUANTITY
    )
    assert (
        model.evaluate(
            market_status=MarketStatus.OPEN,
            price=Decimal("0.42"),
            quantity=Decimal("101"),
        ).reason_code
        is RejectionReason.INVALID_QUANTITY
    )


def test_bounded_rejection_model_rejects_closed_markets() -> None:
    model = BoundedRejectionModel(open_statuses=(MarketStatus.OPEN, MarketStatus.HALTED))

    halted_decision = model.evaluate(
        market_status=MarketStatus.HALTED,
        price=Decimal("0.42"),
        quantity=Decimal("10"),
    )
    closed_decision = model.evaluate(
        market_status=MarketStatus.CLOSED,
        price=Decimal("0.42"),
        quantity=Decimal("10"),
    )

    assert halted_decision.accepted
    assert closed_decision.rejected
    assert closed_decision.reason_code is RejectionReason.MARKET_CLOSED


def test_bounded_rejection_model_rejects_insufficient_balance() -> None:
    model = BoundedRejectionModel()

    insufficient_decision = model.evaluate(
        market_status=MarketStatus.OPEN,
        price=Decimal("0.42"),
        quantity=Decimal("10"),
        required_balance=Decimal("4.20"),
        available_balance=Decimal("4.19"),
    )
    unavailable_decision = model.evaluate(
        market_status=MarketStatus.OPEN,
        price=Decimal("0.42"),
        quantity=Decimal("10"),
        required_balance=Decimal("4.20"),
        available_balance=None,
    )

    assert insufficient_decision.rejected
    assert insufficient_decision.reason_code is RejectionReason.INSUFFICIENT_BALANCE
    assert unavailable_decision.rejected
    assert unavailable_decision.reason_code is RejectionReason.INSUFFICIENT_BALANCE


def test_bounded_rejection_model_uses_deterministic_reason_precedence() -> None:
    decision = BoundedRejectionModel().evaluate(
        market_status=MarketStatus.CLOSED,
        price=Decimal("-0.01"),
        quantity=Decimal("0"),
        required_balance=Decimal("100"),
        available_balance=Decimal("0"),
    )

    assert decision.reason_code is RejectionReason.INVALID_PRICE


def test_bounded_rejection_model_rejects_invalid_inputs() -> None:
    model = BoundedRejectionModel()

    with pytest.raises(SimulationInputError) as status_error:
        model.evaluate(
            market_status="open",  # type: ignore[arg-type]
            price=Decimal("0.42"),
            quantity=Decimal("10"),
        )

    assert status_error.value.reason_code == "simulation_rejection_market_status_invalid"

    with pytest.raises(TypeError, match="float input"):
        model.evaluate(
            market_status=MarketStatus.OPEN,
            price=0.42,  # type: ignore[arg-type]
            quantity=Decimal("10"),
        )

    with pytest.raises(TypeError, match="float input"):
        model.evaluate(
            market_status=MarketStatus.OPEN,
            price=Decimal("0.42"),
            quantity=10.0,  # type: ignore[arg-type]
        )

    with pytest.raises(ValueError, match="nonnegative"):
        model.evaluate(
            market_status=MarketStatus.OPEN,
            price=Decimal("0.42"),
            quantity=Decimal("10"),
            required_balance=Decimal("-1"),
        )


def test_bounded_rejection_model_rejects_invalid_configuration() -> None:
    with pytest.raises(ValueError, match="max_price"):
        BoundedRejectionModel(min_price=Decimal("0.50"), max_price=Decimal("0.49"))

    with pytest.raises(ValueError, match="max_quantity"):
        BoundedRejectionModel(min_quantity=Decimal("10"), max_quantity=Decimal("9"))

    with pytest.raises(ValueError, match="open_statuses"):
        BoundedRejectionModel(open_statuses=())

    with pytest.raises(TypeError, match="MarketStatus"):
        BoundedRejectionModel(open_statuses=("open",))  # type: ignore[arg-type]
