"""Simulation settlement model tests."""

from __future__ import annotations

from decimal import Decimal, localcontext

import pytest

from pmrp.schemas.identifiers import OutcomeId
from pmrp.schemas.portfolio import SettlementStatus
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation import (
    BINARY_SETTLEMENT_MODEL_NAME,
    NO_SETTLEMENT_MODEL_NAME,
    BinarySettlementModel,
    NoSettlementModel,
    SettlementModel,
    SimulationConfigurationError,
    SimulationInputError,
)

pytestmark = pytest.mark.unit

_WINNER = OutcomeId("out_winner")
_LOSER = OutcomeId("out_loser")


def test_binary_settlement_model_pays_winning_outcome() -> None:
    model = BinarySettlementModel()

    estimate = model.estimate(
        outcome_id=_WINNER,
        quantity=Decimal("12.5"),
        winning_outcome_ids=(_WINNER,),
    )

    assert isinstance(model, SettlementModel)
    assert estimate.status is SettlementStatus.SETTLED
    assert estimate.outcome_id == _WINNER
    assert estimate.quantity == Decimal("12.5")
    assert estimate.winning_outcome_ids == (_WINNER,)
    assert estimate.payout_per_unit == Decimal("1")
    assert estimate.payout_amount == Decimal("12.5")
    assert estimate.is_winning_outcome is True


def test_binary_settlement_model_returns_zero_for_losing_outcome() -> None:
    estimate = BinarySettlementModel(payout_per_unit=Decimal("0.88")).estimate(
        outcome_id=_LOSER,
        quantity=Decimal("7"),
        winning_outcome_ids=(_WINNER,),
    )

    assert estimate.status is SettlementStatus.SETTLED
    assert estimate.payout_per_unit == Decimal("0.88")
    assert estimate.payout_amount == Decimal("0")
    assert estimate.is_winning_outcome is False


def test_no_settlement_model_returns_unresolved_zero_payout() -> None:
    model = NoSettlementModel()

    estimate = model.estimate(
        outcome_id=_WINNER,
        quantity=Decimal("3"),
    )

    assert isinstance(model, SettlementModel)
    assert estimate.status is SettlementStatus.UNRESOLVED
    assert estimate.winning_outcome_ids == ()
    assert estimate.payout_per_unit == Decimal("0")
    assert estimate.payout_amount == Decimal("0")
    assert estimate.is_winning_outcome is False


def test_settlement_models_load_from_simulation_configuration() -> None:
    binary_model = BinarySettlementModel.from_configuration(
        _configuration(
            settlement_model=BINARY_SETTLEMENT_MODEL_NAME,
            parameters={"settlement_payout_per_unit": "0.99"},
        )
    )
    default_binary_model = BinarySettlementModel.from_configuration(
        _configuration(settlement_model=BINARY_SETTLEMENT_MODEL_NAME)
    )
    no_model = NoSettlementModel.from_configuration(
        _configuration(settlement_model=NO_SETTLEMENT_MODEL_NAME)
    )

    assert binary_model.payout_per_unit == Decimal("0.99")
    assert default_binary_model.payout_per_unit == Decimal("1")
    assert isinstance(no_model, NoSettlementModel)


def test_settlement_models_reject_unsupported_configuration() -> None:
    with pytest.raises(SimulationConfigurationError) as binary_error:
        BinarySettlementModel.from_configuration(_configuration(settlement_model="oracle_v1"))

    assert binary_error.value.reason_code == "simulation_settlement_model_unsupported"
    assert binary_error.value.context["settlement_model"] == "oracle_v1"

    with pytest.raises(SimulationConfigurationError) as none_error:
        NoSettlementModel.from_configuration(
            _configuration(settlement_model=BINARY_SETTLEMENT_MODEL_NAME)
        )

    assert none_error.value.reason_code == "simulation_settlement_model_unsupported"


def test_binary_settlement_model_uses_explicit_decimal_arithmetic_context() -> None:
    model = BinarySettlementModel(payout_per_unit=Decimal("0.123456789012"))
    quantity = Decimal("0.987654321098")

    with localcontext() as context:
        context.prec = 12
        low_precision_estimate = model.estimate(
            outcome_id=_WINNER,
            quantity=quantity,
            winning_outcome_ids=(_WINNER,),
        )
        context_sensitive_payout = model.payout_per_unit * quantity

    with localcontext() as context:
        context.prec = 28
        default_precision_estimate = model.estimate(
            outcome_id=_WINNER,
            quantity=quantity,
            winning_outcome_ids=(_WINNER,),
        )

    assert low_precision_estimate == default_precision_estimate
    assert low_precision_estimate.payout_amount != context_sensitive_payout


def test_settlement_models_reject_invalid_inputs() -> None:
    model = BinarySettlementModel()

    with pytest.raises(SimulationInputError) as missing_error:
        model.estimate(outcome_id=_WINNER, quantity=Decimal("1"), winning_outcome_ids=())

    assert missing_error.value.reason_code == "simulation_settlement_winning_outcomes_missing"

    with pytest.raises(SimulationInputError) as count_error:
        model.estimate(
            outcome_id=_WINNER,
            quantity=Decimal("1"),
            winning_outcome_ids=(_WINNER, _LOSER),
        )

    assert count_error.value.reason_code == "simulation_binary_settlement_winner_count_invalid"

    with pytest.raises(SimulationInputError) as duplicate_error:
        model.estimate(
            outcome_id=_WINNER,
            quantity=Decimal("1"),
            winning_outcome_ids=(_WINNER, _WINNER),
        )

    assert duplicate_error.value.reason_code == "simulation_settlement_winning_outcomes_duplicate"

    with pytest.raises(SimulationInputError) as outcome_error:
        model.estimate(
            outcome_id="winner",  # type: ignore[arg-type]
            quantity=Decimal("1"),
            winning_outcome_ids=(_WINNER,),
        )

    assert outcome_error.value.reason_code == "simulation_settlement_outcome_id_invalid"

    with pytest.raises(TypeError, match="tuple"):
        model.estimate(
            outcome_id=_WINNER,
            quantity=Decimal("1"),
            winning_outcome_ids=[_WINNER],  # type: ignore[arg-type]
        )

    with pytest.raises(TypeError, match="float input"):
        BinarySettlementModel(payout_per_unit=1.0)  # type: ignore[arg-type]

    with pytest.raises(TypeError, match="float input"):
        model.estimate(
            outcome_id=_WINNER,
            quantity=1.0,  # type: ignore[arg-type]
            winning_outcome_ids=(_WINNER,),
        )

    with pytest.raises(ValueError, match="positive"):
        BinarySettlementModel(payout_per_unit=Decimal("0"))

    with pytest.raises(ValueError, match="positive"):
        model.estimate(
            outcome_id=_WINNER,
            quantity=Decimal("0"),
            winning_outcome_ids=(_WINNER,),
        )

    with pytest.raises(ValueError, match="significant digits"):
        BinarySettlementModel(
            payout_per_unit=Decimal("0.12345678901234567890123456789"),
        )


def _configuration(
    *,
    settlement_model: str = BINARY_SETTLEMENT_MODEL_NAME,
    parameters: dict[str, str] | None = None,
) -> SimulationConfiguration:
    return SimulationConfiguration.model_validate(
        {
            "simulation_version": "sim-v1",
            "fill_model": "touch_fill_v1",
            "queue_model": "immediate_touch_v1",
            "latency_model": "fixed_latency_v1",
            "fee_model": "fee_table_v1",
            "rejection_model": "bounded_rejection_v1",
            "slippage_model": "bps_slippage_v1",
            "settlement_model": settlement_model,
            "random_seed": 42,
            "fixed_latency_ms": 125,
            "taker_slippage_bps": "1.50",
            "parameters": parameters or {},
        }
    )
