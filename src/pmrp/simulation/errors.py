"""Simulation package error types."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType


class SimulationError(Exception):
    """Base class for simulation errors safe to expose to operators."""

    def __init__(
        self,
        safe_message: str,
        *,
        reason_code: str,
        context: Mapping[str, str] | None = None,
    ) -> None:
        self.safe_message = _validate_required_text(safe_message, field_name="safe_message")
        self.reason_code = _validate_required_text(reason_code, field_name="reason_code")
        safe_context = dict(context or {})
        safe_context["reason_code"] = self.reason_code
        self.context: Mapping[str, str] = MappingProxyType(
            {
                _validate_required_text(key, field_name="context key"): _validate_required_text(
                    value,
                    field_name=f"context value for {key}",
                )
                for key, value in safe_context.items()
            }
        )
        super().__init__(self.safe_message)


class SimulationConfigurationError(SimulationError):
    """Raised when simulation model configuration is invalid."""


class SimulationInputError(SimulationError):
    """Raised when simulation model inputs are invalid."""


def _validate_required_text(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value
