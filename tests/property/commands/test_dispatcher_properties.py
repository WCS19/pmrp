from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest
from hypothesis import given
from hypothesis import strategies as st

from pmrp.clock import FrozenClock
from pmrp.commands import (
    CommandContext,
    CommandDispatcher,
    CommandDispatchStatus,
    CommandHandlerRegistration,
    CommandHandlerRegistry,
)
from pmrp.schemas.commands import CommandEnvelope

pytestmark = pytest.mark.property


def _command() -> CommandEnvelope:
    return CommandEnvelope(
        command_id="cmd_01j00000000000000000000000",
        command_type="adapter.connect",
        schema_version=1,
        issued_at=datetime(2026, 7, 28, 21, 30, tzinfo=UTC),
        issuer="property_test",
        correlation_id="corr_01j00000000000000000000000",
        idempotency_key="idem-property",
    )


async def _dispatch_duplicates(count: int) -> tuple[int, tuple[CommandDispatchStatus, ...]]:
    calls = 0

    async def handler(command: CommandEnvelope, context: CommandContext) -> object | None:
        nonlocal calls
        del command, context
        calls += 1
        return {"sequence": calls}

    dispatcher = CommandDispatcher(
        registry=CommandHandlerRegistry(
            (
                CommandHandlerRegistration(
                    command_type="adapter.connect",
                    schema_name="command_envelope",
                    schema_version=1,
                    handler=handler,
                ),
            )
        ),
        clock=FrozenClock(datetime(2026, 7, 28, 21, 30, tzinfo=UTC)),
    )

    results = []
    for _ in range(count):
        results.append(await dispatcher.dispatch(_command()))
    return calls, tuple(result.status for result in results)


@given(count=st.integers(min_value=1, max_value=50))
def test_duplicate_dispatch_attempts_execute_handler_at_most_once(count: int) -> None:
    calls, statuses = asyncio.run(_dispatch_duplicates(count))

    assert calls == 1
    assert statuses[0] is CommandDispatchStatus.COMPLETED
    assert all(status is CommandDispatchStatus.DUPLICATE for status in statuses[1:])
