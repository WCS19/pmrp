"""Strategy runtime error taxonomy with safe structured context."""

from __future__ import annotations

from collections.abc import Mapping
from types import MappingProxyType


class StrategyError(Exception):
    """Base class for strategy interface and runtime failures."""

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


class StrategyContextError(StrategyError):
    """A strategy context dependency or operation is invalid."""


class StrategyEmissionError(StrategyContextError):
    """A strategy attempted an invalid or failed signal/intent emission."""


class StrategyProtocolError(StrategyError):
    """A strategy object does not satisfy the required protocol."""


def _validate_required_text(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        msg = f"{field_name} must be a string"
        raise TypeError(msg)
    if value == "" or value.strip() != value:
        msg = f"{field_name} must be nonempty without surrounding whitespace"
        raise ValueError(msg)
    return value
