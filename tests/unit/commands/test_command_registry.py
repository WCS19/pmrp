from __future__ import annotations

import pytest

from pmrp.commands import (
    CommandContext,
    CommandHandlerRegistration,
    CommandHandlerRegistry,
    UnknownCommandTypeError,
)
from pmrp.schemas.commands import CommandEnvelope

pytestmark = pytest.mark.unit


async def _handler(command: CommandEnvelope, context: CommandContext) -> object | None:
    del command, context
    return None


def test_command_handler_registry_returns_registered_handler() -> None:
    registration = CommandHandlerRegistration(
        command_type="adapter.connect",
        schema_name="command_envelope",
        schema_version=3,
        handler=_handler,
    )
    registry = CommandHandlerRegistry((registration,))

    assert registry.get("adapter.connect") is registration
    assert registry.registrations() == (registration,)


def test_command_handler_registry_rejects_duplicate_command_type() -> None:
    registry = CommandHandlerRegistry(
        (
            CommandHandlerRegistration(
                command_type="adapter.connect",
                schema_name="command_envelope",
                schema_version=1,
                handler=_handler,
            ),
        )
    )

    with pytest.raises(ValueError, match="already registered"):
        registry.register(
            CommandHandlerRegistration(
                command_type="adapter.connect",
                schema_name="command_envelope",
                schema_version=1,
                handler=_handler,
            )
        )


def test_command_handler_registry_rejects_unknown_command_type() -> None:
    registry = CommandHandlerRegistry()

    with pytest.raises(UnknownCommandTypeError, match="not registered"):
        registry.get("adapter.connect")


def test_command_handler_registration_rejects_invalid_command_type() -> None:
    with pytest.raises(ValueError, match="dotted lowercase"):
        CommandHandlerRegistration(
            command_type="AdapterConnect",
            schema_name="command_envelope",
            schema_version=1,
            handler=_handler,
        )


def test_command_handler_registration_rejects_invalid_schema_name() -> None:
    with pytest.raises(ValueError, match="lowercase snake_case"):
        CommandHandlerRegistration(
            command_type="adapter.connect",
            schema_name="CommandEnvelope",
            schema_version=1,
            handler=_handler,
        )


def test_command_handler_registration_rejects_nonpositive_schema_version() -> None:
    with pytest.raises(ValueError, match="positive"):
        CommandHandlerRegistration(
            command_type="adapter.connect",
            schema_name="command_envelope",
            schema_version=0,
            handler=_handler,
        )
