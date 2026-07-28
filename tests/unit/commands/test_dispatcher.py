from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from pmrp.clock import AdvancingTestClock, FrozenClock
from pmrp.commands import (
    CommandContext,
    CommandDispatcher,
    CommandDispatchStatus,
    CommandFailure,
    CommandFailureKind,
    CommandHandlerError,
    CommandHandlerRegistration,
    CommandHandlerRegistry,
    CommandIdempotencyDecision,
    CommandRejectedError,
    InMemoryCommandIdempotencyHook,
)
from pmrp.schemas.commands import CommandEnvelope

pytestmark = pytest.mark.unit


def _instant() -> datetime:
    return datetime(2026, 7, 28, 21, 30, tzinfo=UTC)


def _command(
    *,
    command_type: str = "adapter.connect",
    schema_version: int = 1,
    idempotency_key: str = "idem-1",
    deadline_at: datetime | None = None,
) -> CommandEnvelope:
    return CommandEnvelope(
        command_id="cmd_01j00000000000000000000000",
        command_type=command_type,
        schema_version=schema_version,
        issued_at=_instant(),
        issuer="unit_test",
        correlation_id="corr_01j00000000000000000000000",
        idempotency_key=idempotency_key,
        deadline_at=deadline_at,
        attributes={"target": "fixture"},
    )


class RecordingHandler:
    def __init__(self, result: object | None = None) -> None:
        self.calls: list[CommandContext] = []
        self.result = result

    async def __call__(self, command: CommandEnvelope, context: CommandContext) -> object | None:
        del command
        self.calls.append(context)
        return self.result


def _registry(handler: RecordingHandler) -> CommandHandlerRegistry:
    return CommandHandlerRegistry(
        (
            CommandHandlerRegistration(
                command_type="adapter.connect",
                schema_name="command_envelope",
                schema_version=1,
                handler=handler,
            ),
        )
    )


async def test_command_dispatcher_passes_correlation_context_to_registered_handler() -> None:
    handler = RecordingHandler(result={"connected": True})
    dispatcher = CommandDispatcher(registry=_registry(handler), clock=FrozenClock(_instant()))

    result = await dispatcher.dispatch(_command())

    assert result.status is CommandDispatchStatus.COMPLETED
    assert result.result == {"connected": True}
    assert len(handler.calls) == 1
    assert handler.calls[0].correlation_id == "corr_01j00000000000000000000000"
    assert handler.calls[0].idempotency_key == "idem-1"


async def test_command_dispatcher_rejects_unknown_command_type() -> None:
    handler = RecordingHandler()
    dispatcher = CommandDispatcher(registry=_registry(handler), clock=FrozenClock(_instant()))

    result = await dispatcher.dispatch(_command(command_type="adapter.disconnect"))

    assert result.status is CommandDispatchStatus.REJECTED
    assert result.failure is not None
    assert result.failure.kind is CommandFailureKind.UNKNOWN_COMMAND_TYPE
    assert handler.calls == []


async def test_command_dispatcher_rejects_schema_version_mismatch() -> None:
    handler = RecordingHandler()
    dispatcher = CommandDispatcher(registry=_registry(handler), clock=FrozenClock(_instant()))

    result = await dispatcher.dispatch(_command(schema_version=2))

    assert result.status is CommandDispatchStatus.REJECTED
    assert result.failure is not None
    assert result.failure.kind is CommandFailureKind.SCHEMA_VERSION_MISMATCH
    assert handler.calls == []


async def test_command_dispatcher_rejects_expired_deadline_with_injected_clock() -> None:
    handler = RecordingHandler()
    dispatcher = CommandDispatcher(registry=_registry(handler), clock=FrozenClock(_instant()))

    result = await dispatcher.dispatch(_command(deadline_at=_instant() - timedelta(microseconds=1)))

    assert result.status is CommandDispatchStatus.REJECTED
    assert result.failure is not None
    assert result.failure.kind is CommandFailureKind.DEADLINE_EXCEEDED
    assert handler.calls == []


async def test_command_dispatcher_returns_cached_duplicate_result_without_handler_call() -> None:
    handler = RecordingHandler(result={"accepted": True})
    dispatcher = CommandDispatcher(registry=_registry(handler), clock=FrozenClock(_instant()))
    command = _command()

    first = await dispatcher.dispatch(command)
    second = await dispatcher.dispatch(command)

    assert first.status is CommandDispatchStatus.COMPLETED
    assert second.status is CommandDispatchStatus.DUPLICATE
    assert second.result == {"accepted": True}
    assert len(handler.calls) == 1


async def test_command_dispatcher_retains_terminal_duplicates_below_hook_capacity() -> None:
    calls = 0

    async def handler(command: CommandEnvelope, context: CommandContext) -> object | None:
        nonlocal calls
        del context
        calls += 1
        return {"call": calls, "key": command.idempotency_key}

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
        clock=FrozenClock(_instant()),
    )

    first = await dispatcher.dispatch(_command(idempotency_key="idem-1"))
    second = await dispatcher.dispatch(_command(idempotency_key="idem-2"))
    third = await dispatcher.dispatch(_command(idempotency_key="idem-1"))

    assert first.status is CommandDispatchStatus.COMPLETED
    assert second.status is CommandDispatchStatus.COMPLETED
    assert third.status is CommandDispatchStatus.DUPLICATE
    assert third.result == {"call": 1, "key": "idem-1"}
    assert calls == 2


async def test_command_dispatcher_rejects_same_idempotency_key_for_different_command() -> None:
    connect_handler = RecordingHandler(result={"connected": True})
    disconnect_handler = RecordingHandler(result={"disconnected": True})
    dispatcher = CommandDispatcher(
        registry=CommandHandlerRegistry(
            (
                CommandHandlerRegistration(
                    command_type="adapter.connect",
                    schema_name="command_envelope",
                    schema_version=1,
                    handler=connect_handler,
                ),
                CommandHandlerRegistration(
                    command_type="adapter.disconnect",
                    schema_name="command_envelope",
                    schema_version=1,
                    handler=disconnect_handler,
                ),
            )
        ),
        clock=FrozenClock(_instant()),
    )

    first = await dispatcher.dispatch(_command(command_type="adapter.connect"))
    second = await dispatcher.dispatch(_command(command_type="adapter.disconnect"))

    assert first.status is CommandDispatchStatus.COMPLETED
    assert second.status is CommandDispatchStatus.REJECTED
    assert second.failure is not None
    assert second.failure.kind is CommandFailureKind.IDEMPOTENCY_CONFLICT
    assert connect_handler.calls
    assert disconnect_handler.calls == []


async def test_command_dispatcher_replays_completed_duplicate_after_deadline_expires() -> None:
    clock = AdvancingTestClock(_instant())
    handler = RecordingHandler(result={"accepted": True})
    dispatcher = CommandDispatcher(registry=_registry(handler), clock=clock)
    command = _command(deadline_at=_instant() + timedelta(seconds=1))

    first = await dispatcher.dispatch(command)
    clock.advance(timedelta(seconds=2))
    second = await dispatcher.dispatch(command)

    assert first.status is CommandDispatchStatus.COMPLETED
    assert second.status is CommandDispatchStatus.DUPLICATE
    assert second.result == {"accepted": True}
    assert second.failure is None
    assert len(handler.calls) == 1


async def test_command_dispatcher_returns_cached_duplicate_failure_without_handler_call() -> None:
    class RejectingHandler:
        def __init__(self) -> None:
            self.calls = 0

        async def __call__(
            self,
            command: CommandEnvelope,
            context: CommandContext,
        ) -> object | None:
            del command, context
            self.calls += 1
            raise CommandRejectedError("risk rejected command")

    handler = RejectingHandler()
    registry = CommandHandlerRegistry(
        (
            CommandHandlerRegistration(
                command_type="adapter.connect",
                schema_name="command_envelope",
                schema_version=1,
                handler=handler,
            ),
        )
    )
    dispatcher = CommandDispatcher(registry=registry, clock=FrozenClock(_instant()))
    command = _command()

    first = await dispatcher.dispatch(command)
    second = await dispatcher.dispatch(command)

    assert first.status is CommandDispatchStatus.REJECTED
    assert second.status is CommandDispatchStatus.DUPLICATE
    assert second.failure is not None
    assert second.failure.kind is CommandFailureKind.HANDLER_REJECTED
    assert handler.calls == 1


async def test_command_dispatcher_sanitizes_unexpected_handler_exception_message() -> None:
    class FailingHandler:
        async def __call__(
            self,
            command: CommandEnvelope,
            context: CommandContext,
        ) -> object | None:
            del command, context
            raise RuntimeError("secret-token-value")

    registry = CommandHandlerRegistry(
        (
            CommandHandlerRegistration(
                command_type="adapter.connect",
                schema_name="command_envelope",
                schema_version=1,
                handler=FailingHandler(),
            ),
        )
    )
    dispatcher = CommandDispatcher(registry=registry, clock=FrozenClock(_instant()))

    result = await dispatcher.dispatch(_command())

    assert result.status is CommandDispatchStatus.FAILED
    assert result.failure is not None
    assert result.failure.kind is CommandFailureKind.HANDLER_ERROR
    assert result.failure.message == "RuntimeError raised by command handler"
    assert "secret-token-value" not in result.failure.message


async def test_command_dispatcher_preserves_classified_handler_error() -> None:
    class FailingHandler:
        async def __call__(
            self,
            command: CommandEnvelope,
            context: CommandContext,
        ) -> object | None:
            del command, context
            raise CommandHandlerError("transient dependency failure", retryable=True)

    registry = CommandHandlerRegistry(
        (
            CommandHandlerRegistration(
                command_type="adapter.connect",
                schema_name="command_envelope",
                schema_version=1,
                handler=FailingHandler(),
            ),
        )
    )
    dispatcher = CommandDispatcher(registry=registry, clock=FrozenClock(_instant()))

    result = await dispatcher.dispatch(_command())

    assert result.status is CommandDispatchStatus.FAILED
    assert result.failure is not None
    assert result.failure.kind is CommandFailureKind.HANDLER_ERROR
    assert result.failure.message == "transient dependency failure"
    assert result.failure.retryable is True


class FailingBeforeDispatchHook:
    async def before_dispatch(self, command: CommandEnvelope) -> CommandIdempotencyDecision:
        del command
        raise RuntimeError("store unavailable")

    async def record_success(self, command: CommandEnvelope, result: object | None) -> None:
        del command, result

    async def record_failure(self, command: CommandEnvelope, failure: CommandFailure) -> None:
        del command, failure


async def test_command_dispatcher_fails_closed_when_idempotency_hook_raises() -> None:
    handler = RecordingHandler()
    dispatcher = CommandDispatcher(
        registry=_registry(handler),
        clock=FrozenClock(_instant()),
        idempotency_hook=FailingBeforeDispatchHook(),
    )

    result = await dispatcher.dispatch(_command())

    assert result.status is CommandDispatchStatus.FAILED
    assert result.failure is not None
    assert result.failure.kind is CommandFailureKind.IDEMPOTENCY_HOOK_ERROR
    assert handler.calls == []


class InProgressHook:
    async def before_dispatch(self, command: CommandEnvelope) -> CommandIdempotencyDecision:
        del command
        return CommandIdempotencyDecision.duplicate_in_progress("already running")

    async def record_success(self, command: CommandEnvelope, result: object | None) -> None:
        del command, result

    async def record_failure(self, command: CommandEnvelope, failure: CommandFailure) -> None:
        del command, failure


async def test_command_dispatcher_rejects_duplicate_in_progress_without_handler_call() -> None:
    handler = RecordingHandler()
    dispatcher = CommandDispatcher(
        registry=_registry(handler),
        clock=FrozenClock(_instant()),
        idempotency_hook=InProgressHook(),
    )

    result = await dispatcher.dispatch(_command())

    assert result.status is CommandDispatchStatus.REJECTED
    assert result.failure is not None
    assert result.failure.kind is CommandFailureKind.DUPLICATE_IN_PROGRESS
    assert result.failure.retryable is True
    assert handler.calls == []


async def test_in_memory_idempotency_hook_is_bounded() -> None:
    hook = InMemoryCommandIdempotencyHook(max_entries=1)

    first = await hook.before_dispatch(_command(idempotency_key="idem-1"))
    second = await hook.before_dispatch(_command(idempotency_key="idem-2"))

    assert first == CommandIdempotencyDecision.claimed()
    assert second.status.name == "REJECTED"
