"""Deterministic settlement payout models for simulation."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Context, Decimal, localcontext
from typing import Protocol, runtime_checkable

from pmrp.schemas.identifiers import OutcomeId
from pmrp.schemas.numeric import parse_decimal
from pmrp.schemas.portfolio import SettlementStatus
from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation.errors import SimulationConfigurationError, SimulationInputError

BINARY_SETTLEMENT_MODEL_NAME = "binary_settlement_v1"
NO_SETTLEMENT_MODEL_NAME = "none_v1"

_MAX_DECIMAL_ADJUSTED_EXPONENT = 36
_MAX_DECIMAL_DIGITS = 28
_MAX_DECIMAL_SCALE = 18
_PAYOUT_PER_UNIT_PARAMETER = "settlement_payout_per_unit"
_SETTLEMENT_ARITHMETIC_CONTEXT = Context(prec=128)
_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class SettlementEstimate:
    """Estimated simulated settlement payout for one outcome position."""

    outcome_id: OutcomeId
    quantity: Decimal
    status: SettlementStatus
    winning_outcome_ids: tuple[OutcomeId, ...]
    payout_per_unit: Decimal
    payout_amount: Decimal
    is_winning_outcome: bool


@runtime_checkable
class SettlementModel(Protocol):
    """Pure model for simulated settlement payout estimates."""

    def estimate(
        self,
        *,
        outcome_id: OutcomeId,
        quantity: Decimal,
        winning_outcome_ids: tuple[OutcomeId, ...] = (),
    ) -> SettlementEstimate:
        """Estimate simulated settlement payout for one outcome position."""
        ...


class NoSettlementModel:
    """Leave simulated settlement unresolved with zero payout."""

    @classmethod
    def from_configuration(cls, configuration: SimulationConfiguration) -> NoSettlementModel:
        """Create a no-settlement model from canonical simulation configuration."""

        if configuration.settlement_model != NO_SETTLEMENT_MODEL_NAME:
            raise SimulationConfigurationError(
                "Simulation settlement_model must select the no-settlement model",
                reason_code="simulation_settlement_model_unsupported",
                context={"settlement_model": configuration.settlement_model},
            )
        return cls()

    def estimate(
        self,
        *,
        outcome_id: OutcomeId,
        quantity: Decimal,
        winning_outcome_ids: tuple[OutcomeId, ...] = (),
    ) -> SettlementEstimate:
        """Return an unresolved zero-payout estimate."""

        outcome_id = _validate_outcome_id(outcome_id, field_name="outcome_id")
        quantity = _parse_positive_decimal(quantity, field_name="settlement quantity")
        winning_outcome_ids = _validate_winning_outcome_ids(
            winning_outcome_ids,
            allow_empty=True,
        )
        if winning_outcome_ids:
            raise SimulationInputError(
                "No-settlement model cannot contain winning outcomes",
                reason_code="simulation_no_settlement_winning_outcomes_invalid",
            )
        return SettlementEstimate(
            outcome_id=outcome_id,
            quantity=quantity,
            status=SettlementStatus.UNRESOLVED,
            winning_outcome_ids=winning_outcome_ids,
            payout_per_unit=_ZERO,
            payout_amount=_ZERO,
            is_winning_outcome=False,
        )


@dataclass(frozen=True, slots=True)
class BinarySettlementModel:
    """Apply deterministic binary-outcome payout assumptions."""

    payout_per_unit: Decimal = Decimal("1")

    def __post_init__(self) -> None:
        object.__setattr__(
            self,
            "payout_per_unit",
            _parse_positive_decimal(self.payout_per_unit, field_name="payout_per_unit"),
        )

    @classmethod
    def from_configuration(cls, configuration: SimulationConfiguration) -> BinarySettlementModel:
        """Create a binary settlement model from canonical simulation configuration."""

        if configuration.settlement_model != BINARY_SETTLEMENT_MODEL_NAME:
            raise SimulationConfigurationError(
                "Simulation settlement_model must select the binary settlement model",
                reason_code="simulation_settlement_model_unsupported",
                context={"settlement_model": configuration.settlement_model},
            )
        configured_payout = configuration.parameters.get(_PAYOUT_PER_UNIT_PARAMETER)
        if configured_payout is None:
            return cls()
        return cls(payout_per_unit=parse_decimal(configured_payout, field_name="payout_per_unit"))

    def estimate(
        self,
        *,
        outcome_id: OutcomeId,
        quantity: Decimal,
        winning_outcome_ids: tuple[OutcomeId, ...] = (),
    ) -> SettlementEstimate:
        """Return settlement payout for a binary outcome position."""

        outcome_id = _validate_outcome_id(outcome_id, field_name="outcome_id")
        quantity = _parse_positive_decimal(quantity, field_name="settlement quantity")
        winning_outcome_ids = _validate_winning_outcome_ids(
            winning_outcome_ids,
            allow_empty=False,
        )
        if len(winning_outcome_ids) != 1:
            raise SimulationInputError(
                "Binary settlement requires exactly one winning outcome",
                reason_code="simulation_binary_settlement_winner_count_invalid",
                context={"winning_outcome_count": str(len(winning_outcome_ids))},
            )

        is_winning_outcome = outcome_id == winning_outcome_ids[0]
        with localcontext(_SETTLEMENT_ARITHMETIC_CONTEXT):
            payout_amount = self.payout_per_unit * quantity if is_winning_outcome else _ZERO

        return SettlementEstimate(
            outcome_id=outcome_id,
            quantity=quantity,
            status=SettlementStatus.SETTLED,
            winning_outcome_ids=winning_outcome_ids,
            payout_per_unit=self.payout_per_unit,
            payout_amount=payout_amount,
            is_winning_outcome=is_winning_outcome,
        )


def _validate_outcome_id(value: OutcomeId, *, field_name: str) -> OutcomeId:
    if isinstance(value, OutcomeId):
        return value
    try:
        return OutcomeId(value)
    except (TypeError, ValueError) as exc:
        raise SimulationInputError(
            f"Settlement model {field_name} must be a canonical OutcomeId",
            reason_code="simulation_settlement_outcome_id_invalid",
        ) from exc


def _validate_winning_outcome_ids(
    values: tuple[OutcomeId, ...],
    *,
    allow_empty: bool,
) -> tuple[OutcomeId, ...]:
    if not isinstance(values, tuple):
        msg = "winning_outcome_ids must be a tuple"
        raise TypeError(msg)
    if not values and not allow_empty:
        raise SimulationInputError(
            "Settlement model requires at least one winning outcome",
            reason_code="simulation_settlement_winning_outcomes_missing",
        )

    validated = tuple(
        _validate_outcome_id(value, field_name="winning_outcome_ids") for value in values
    )
    if len(set(validated)) != len(validated):
        raise SimulationInputError(
            "Settlement model winning outcomes must be unique",
            reason_code="simulation_settlement_winning_outcomes_duplicate",
        )
    return validated


def _parse_positive_decimal(value: Decimal, *, field_name: str) -> Decimal:
    parsed = _parse_bounded_decimal(value, field_name=field_name)
    if parsed <= _ZERO:
        msg = f"{field_name} must be positive"
        raise ValueError(msg)
    return parsed


def _parse_bounded_decimal(value: Decimal, *, field_name: str) -> Decimal:
    parsed = parse_decimal(value, field_name=field_name)
    _validate_decimal_bounds(parsed, field_name=field_name)
    return parsed


def _validate_decimal_bounds(value: Decimal, *, field_name: str) -> None:
    decimal_tuple = value.as_tuple()
    if not isinstance(decimal_tuple.exponent, int):
        msg = f"{field_name} must be finite"
        raise ValueError(msg)
    digits = len(decimal_tuple.digits)
    scale = max(-decimal_tuple.exponent, 0)
    if digits > _MAX_DECIMAL_DIGITS:
        msg = f"{field_name} must have at most {_MAX_DECIMAL_DIGITS} significant digits"
        raise ValueError(msg)
    if scale > _MAX_DECIMAL_SCALE:
        msg = f"{field_name} must have at most {_MAX_DECIMAL_SCALE} fractional digits"
        raise ValueError(msg)
    if value.adjusted() > _MAX_DECIMAL_ADJUSTED_EXPONENT:
        msg = f"{field_name} adjusted exponent must be at most {_MAX_DECIMAL_ADJUSTED_EXPONENT}"
        raise ValueError(msg)
