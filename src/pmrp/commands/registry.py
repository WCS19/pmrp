"""Command handler registry for runtime dispatch."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from pmrp.schemas.commands import CommandEnvelope
from pmrp.schemas.identifiers import CausationRef, CommandId, CorrelationId
from pmrp.schemas.time import UTCDateTime
from pmrp.schemas.versions import parse_schema_version

_DOTTED_COMMAND_TYPE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$")


class UnknownCommandTypeError(KeyError):
    """Raised when a command type has no registered handler."""


@dataclass(frozen=True, slots=True)
class CommandContext:
    """Correlation and idempotency context passed to command handlers."""

    command_id: CommandId
    command_type: str
    issued_at: UTCDateTime
    issuer: str
    correlation_id: CorrelationId
    causation_id: CausationRef | None
    trace_id: str | None
    idempotency_key: str
    deadline_at: UTCDateTime | None
    priority: int

    @classmethod
    def from_command(cls, command: CommandEnvelope) -> CommandContext:
        return cls(
            command_id=command.command_id,
            command_type=command.command_type,
            issued_at=command.issued_at,
            issuer=command.issuer,
            correlation_id=command.correlation_id,
            causation_id=command.causation_id,
            trace_id=command.trace_id,
            idempotency_key=command.idempotency_key,
            deadline_at=command.deadline_at,
            priority=command.priority,
        )


type CommandHandler = Callable[[CommandEnvelope, CommandContext], Awaitable[object | None]]


@dataclass(frozen=True, slots=True)
class CommandHandlerRegistration:
    command_type: str
    schema_name: str
    schema_version: int
    handler: CommandHandler

    def __post_init__(self) -> None:
        _validate_command_type(self.command_type)
        _validate_schema_name(self.schema_name)
        object.__setattr__(self, "schema_version", parse_schema_version(self.schema_version))


class CommandHandlerRegistry:
    """Runtime registry mapping command types to async handlers."""

    def __init__(self, registrations: tuple[CommandHandlerRegistration, ...] = ()) -> None:
        self._registrations: dict[str, CommandHandlerRegistration] = {}
        for registration in registrations:
            self.register(registration)

    def register(self, registration: CommandHandlerRegistration) -> None:
        if registration.command_type in self._registrations:
            msg = f"command type is already registered: {registration.command_type}"
            raise ValueError(msg)
        self._registrations[registration.command_type] = registration

    def get(self, command_type: str) -> CommandHandlerRegistration:
        _validate_command_type(command_type)
        try:
            return self._registrations[command_type]
        except KeyError as exc:
            msg = f"command type is not registered: {command_type}"
            raise UnknownCommandTypeError(msg) from exc

    def registrations(self) -> tuple[CommandHandlerRegistration, ...]:
        return tuple(self._registrations.values())


def _validate_command_type(command_type: str) -> None:
    if _DOTTED_COMMAND_TYPE_PATTERN.fullmatch(command_type) is None:
        msg = "command_type must use dotted lowercase segments"
        raise ValueError(msg)


def _validate_schema_name(schema_name: str) -> None:
    if re.fullmatch(r"^[a-z][a-z0-9_]*$", schema_name) is None:
        msg = "schema_name must use lowercase snake_case"
        raise ValueError(msg)
