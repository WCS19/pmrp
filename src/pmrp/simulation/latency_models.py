"""Deterministic latency models for simulated order activation."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol, runtime_checkable

from pmrp.schemas.simulation import SimulationConfiguration
from pmrp.simulation.errors import SimulationConfigurationError

FIXED_LATENCY_MODEL_NAME = "fixed_latency_v1"


@runtime_checkable
class LatencyModel(Protocol):
    """Pure latency model used by simulated exchange order activation."""

    def activation_time(self, *, accepted_at: datetime) -> datetime:
        """Return the UTC time when a simulated accepted order becomes active."""
        ...


@dataclass(frozen=True, slots=True)
class FixedLatencyModel:
    """Apply a fixed nonnegative latency to simulated order activation."""

    latency: timedelta

    def __post_init__(self) -> None:
        if not isinstance(self.latency, timedelta):
            msg = "latency must be a timedelta"
            raise TypeError(msg)
        if self.latency < timedelta(0):
            msg = "latency must be nonnegative"
            raise ValueError(msg)

    @classmethod
    def from_milliseconds(cls, milliseconds: int) -> FixedLatencyModel:
        """Create a fixed latency model from exact integer milliseconds."""

        _validate_milliseconds(milliseconds)
        return cls(latency=timedelta(milliseconds=milliseconds))

    @classmethod
    def from_configuration(cls, configuration: SimulationConfiguration) -> FixedLatencyModel:
        """Create a fixed latency model from canonical simulation configuration."""

        if configuration.latency_model != FIXED_LATENCY_MODEL_NAME:
            raise SimulationConfigurationError(
                "Simulation latency_model must select the fixed latency model",
                reason_code="simulation_latency_model_unsupported",
                context={"latency_model": configuration.latency_model},
            )
        if configuration.fixed_latency_ms is None:
            raise SimulationConfigurationError(
                "Fixed latency simulation requires fixed_latency_ms",
                reason_code="simulation_fixed_latency_missing",
                context={"latency_model": configuration.latency_model},
            )
        return cls.from_milliseconds(configuration.fixed_latency_ms)

    def activation_time(self, *, accepted_at: datetime) -> datetime:
        """Return accepted_at plus the configured latency in UTC."""

        _validate_aware_datetime(accepted_at, field_name="accepted_at")
        try:
            return accepted_at.astimezone(UTC) + self.latency
        except OverflowError as exc:
            raise SimulationConfigurationError(
                "Fixed latency activation time is outside supported datetime range",
                reason_code="simulation_fixed_latency_datetime_overflow",
            ) from exc


def _validate_milliseconds(milliseconds: int) -> None:
    if type(milliseconds) is not int:
        msg = "latency milliseconds must be an int"
        raise TypeError(msg)
    if milliseconds < 0:
        msg = "latency milliseconds must be nonnegative"
        raise ValueError(msg)


def _validate_aware_datetime(value: datetime, *, field_name: str) -> None:
    if not isinstance(value, datetime):
        msg = f"{field_name} must be a datetime"
        raise TypeError(msg)
    if value.tzinfo is None or value.utcoffset() is None:
        msg = f"{field_name} must be timezone-aware"
        raise ValueError(msg)
