"""Property tests for simulation settlement models."""

from __future__ import annotations

from decimal import Decimal

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.schemas.identifiers import OutcomeId
from pmrp.schemas.portfolio import SettlementStatus
from pmrp.simulation import BinarySettlementModel, NoSettlementModel

pytestmark = pytest.mark.property

_WINNER = OutcomeId("out_winner")
_LOSER = OutcomeId("out_loser")
_QUANTITY = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("10000"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)
_PAYOUT = st.decimals(
    min_value=Decimal("0.0001"),
    max_value=Decimal("1"),
    allow_nan=False,
    allow_infinity=False,
    places=4,
)


@given(quantity=_QUANTITY, payout_per_unit=_PAYOUT)
def test_binary_settlement_model_pays_quantity_times_payout_for_winner(
    quantity: Decimal,
    payout_per_unit: Decimal,
) -> None:
    model = BinarySettlementModel(payout_per_unit=payout_per_unit)

    estimate = model.estimate(
        outcome_id=_WINNER,
        quantity=quantity,
        winning_outcome_ids=(_WINNER,),
    )

    assert estimate.status is SettlementStatus.SETTLED
    assert estimate.is_winning_outcome is True
    assert estimate.payout_amount == quantity * payout_per_unit


@given(quantity=_QUANTITY, payout_per_unit=_PAYOUT)
def test_binary_settlement_model_losing_outcome_payout_is_zero(
    quantity: Decimal,
    payout_per_unit: Decimal,
) -> None:
    model = BinarySettlementModel(payout_per_unit=payout_per_unit)

    estimate = model.estimate(
        outcome_id=_LOSER,
        quantity=quantity,
        winning_outcome_ids=(_WINNER,),
    )

    assert estimate.status is SettlementStatus.SETTLED
    assert estimate.is_winning_outcome is False
    assert estimate.payout_amount == Decimal("0")


@given(quantity=_QUANTITY, payout_per_unit=_PAYOUT)
def test_binary_settlement_model_is_deterministic(
    quantity: Decimal,
    payout_per_unit: Decimal,
) -> None:
    model = BinarySettlementModel(payout_per_unit=payout_per_unit)

    first = model.estimate(
        outcome_id=_WINNER,
        quantity=quantity,
        winning_outcome_ids=(_WINNER,),
    )
    second = model.estimate(
        outcome_id=_WINNER,
        quantity=quantity,
        winning_outcome_ids=(_WINNER,),
    )

    assert first == second


@given(quantity=_QUANTITY)
def test_no_settlement_model_is_deterministic_and_zero(quantity: Decimal) -> None:
    model = NoSettlementModel()

    first = model.estimate(outcome_id=_WINNER, quantity=quantity)
    second = model.estimate(outcome_id=_WINNER, quantity=quantity)

    assert first == second
    assert first.status is SettlementStatus.UNRESOLVED
    assert first.payout_amount == Decimal("0")
