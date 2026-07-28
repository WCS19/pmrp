"""Command dispatcher with idempotency and failure classification."""

from __future__ import annotations

import asyncio
from collections import OrderedDict
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol

from pmrp.clock import Clock
from pmrp.commands.registry import CommandContext, CommandHandlerRegistry, UnknownCommandTypeError
from pmrp.schemas.commands import CommandEnvelope
from pmrp.schemas.identifiers import CommandId, CorrelationId
from pmrp.schemas.serialization import canonical_sha256


class CommandDispatchStatus(StrEnum):
    """Top-level outcome for a command dispatch attempt."""

    COMPLETED = "completed"
    DUPLICATE = "duplicate"
    REJECTED = "rejected"
    FAILED = "failed"


class CommandFailureKind(StrEnum):
    """Stable classification for command dispatch failures."""

    UNKNOWN_COMMAND_TYPE = "unknown_command_type"
    SCHEMA_VERSION_MISMATCH = "schema_version_mismatch"
    DEADLINE_EXCEEDED = "deadline_exceeded"
    DUPLICATE_IN_PROGRESS = "duplicate_in_progress"
    IDEMPOTENCY_CONFLICT = "idempotency_conflict"
    IDEMPOTENCY_REJECTED = "idempotency_rejected"
    IDEMPOTENCY_HOOK_ERROR = "idempotency_hook_error"
    HANDLER_REJECTED = "handler_rejected"
    HANDLER_ERROR = "handler_error"


@dataclass(frozen=True, slots=True)
class CommandFailure:
    kind: CommandFailureKind
    message: str
    retryable: bool


@dataclass(frozen=True, slots=True)
class CommandDispatchResult:
    command_id: CommandId
    command_type: str
    correlation_id: CorrelationId
    status: CommandDispatchStatus
    result: object | None = None
    failure: CommandFailure | None = None


class CommandRejectedError(Exception):
    """Raised by handlers when a command is intentionally rejected."""

    def __init__(self, safe_message: str, *, retryable: bool = False) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message
        self.retryable = retryable


class CommandHandlerError(Exception):
    """Raised by handlers for classified execution failures."""

    def __init__(
        self,
        safe_message: str,
        *,
        kind: CommandFailureKind = CommandFailureKind.HANDLER_ERROR,
        retryable: bool = False,
    ) -> None:
        super().__init__(safe_message)
        self.safe_message = safe_message
        self.kind = kind
        self.retryable = retryable


class CommandIdempotencyStatus(StrEnum):
    """Decision returned by an idempotency hook before handler execution."""

    CLAIMED = "claimed"
    DUPLICATE_COMPLETED = "duplicate_completed"
    DUPLICATE_FAILED = "duplicate_failed"
    DUPLICATE_IN_PROGRESS = "duplicate_in_progress"
    CONFLICT = "conflict"
    REJECTED = "rejected"


@dataclass(frozen=True, slots=True)
class CommandIdempotencyDecision:
    status: CommandIdempotencyStatus
    result: object | None = None
    failure: CommandFailure | None = None
    reason: str | None = None

    @classmethod
    def claimed(cls) -> CommandIdempotencyDecision:
        return cls(status=CommandIdempotencyStatus.CLAIMED)

    @classmethod
    def duplicate_completed(cls, result: object | None) -> CommandIdempotencyDecision:
        return cls(status=CommandIdempotencyStatus.DUPLICATE_COMPLETED, result=result)

    @classmethod
    def duplicate_failed(cls, failure: CommandFailure) -> CommandIdempotencyDecision:
        return cls(status=CommandIdempotencyStatus.DUPLICATE_FAILED, failure=failure)

    @classmethod
    def duplicate_in_progress(cls, reason: str) -> CommandIdempotencyDecision:
        return cls(status=CommandIdempotencyStatus.DUPLICATE_IN_PROGRESS, reason=reason)

    @classmethod
    def conflict(cls, reason: str) -> CommandIdempotencyDecision:
        return cls(status=CommandIdempotencyStatus.CONFLICT, reason=reason)

    @classmethod
    def rejected(cls, reason: str) -> CommandIdempotencyDecision:
        return cls(status=CommandIdempotencyStatus.REJECTED, reason=reason)


class CommandIdempotencyHook(Protocol):
    """Hook used by the dispatcher to prevent duplicate business effects."""

    async def before_dispatch(self, command: CommandEnvelope) -> CommandIdempotencyDecision: ...

    async def record_success(self, command: CommandEnvelope, result: object | None) -> None: ...

    async def record_failure(self, command: CommandEnvelope, failure: CommandFailure) -> None: ...


class _InMemoryEntryStatus(StrEnum):
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(slots=True)
class _InMemoryIdempotencyEntry:
    fingerprint: str
    status: _InMemoryEntryStatus
    result: object | None = None
    failure: CommandFailure | None = None


class InMemoryCommandIdempotencyHook:
    """Bounded in-memory idempotency hook for tests, replay, and local runtimes."""

    def __init__(self, *, max_entries: int = 1024) -> None:
        if max_entries < 1:
            msg = "max_entries must be positive"
            raise ValueError(msg)
        self._max_entries = max_entries
        self._entries: OrderedDict[str, _InMemoryIdempotencyEntry] = OrderedDict()
        self._lock = asyncio.Lock()

    async def before_dispatch(self, command: CommandEnvelope) -> CommandIdempotencyDecision:
        fingerprint = _command_idempotency_fingerprint(command)
        async with self._lock:
            existing = self._entries.get(command.idempotency_key)
            if existing is not None:
                self._entries.move_to_end(command.idempotency_key)
                if existing.fingerprint != fingerprint:
                    return CommandIdempotencyDecision.conflict(
                        "command idempotency key conflicts with a different command request"
                    )
                if existing.status is _InMemoryEntryStatus.IN_PROGRESS:
                    return CommandIdempotencyDecision.duplicate_in_progress(
                        "command idempotency key is already in progress"
                    )
                if existing.status is _InMemoryEntryStatus.COMPLETED:
                    return CommandIdempotencyDecision.duplicate_completed(existing.result)
                if existing.failure is None:
                    return CommandIdempotencyDecision.rejected(
                        "command idempotency key has a failed record without failure metadata"
                    )
                return CommandIdempotencyDecision.duplicate_failed(existing.failure)

            if len(self._entries) >= self._max_entries:
                self._evict_oldest_terminal_entry()
            if len(self._entries) >= self._max_entries:
                return CommandIdempotencyDecision.rejected(
                    "command idempotency hook capacity is exhausted"
                )

            self._entries[command.idempotency_key] = _InMemoryIdempotencyEntry(
                fingerprint=fingerprint, status=_InMemoryEntryStatus.IN_PROGRESS
            )
            return CommandIdempotencyDecision.claimed()

    async def record_success(self, command: CommandEnvelope, result: object | None) -> None:
        async with self._lock:
            self._entries[command.idempotency_key] = _InMemoryIdempotencyEntry(
                fingerprint=_command_idempotency_fingerprint(command),
                status=_InMemoryEntryStatus.COMPLETED,
                result=result,
            )
            self._entries.move_to_end(command.idempotency_key)
            self._trim_to_capacity(command.idempotency_key)

    async def record_failure(self, command: CommandEnvelope, failure: CommandFailure) -> None:
        async with self._lock:
            self._entries[command.idempotency_key] = _InMemoryIdempotencyEntry(
                fingerprint=_command_idempotency_fingerprint(command),
                status=_InMemoryEntryStatus.FAILED,
                failure=failure,
            )
            self._entries.move_to_end(command.idempotency_key)
            self._trim_to_capacity(command.idempotency_key)

    def _trim_to_capacity(self, protected_key: str) -> None:
        while len(self._entries) > self._max_entries:
            removed = self._evict_oldest_terminal_entry(protected_key=protected_key)
            if not removed:
                break

    def _evict_oldest_terminal_entry(self, *, protected_key: str | None = None) -> bool:
        for key, entry in self._entries.items():
            if key == protected_key or entry.status is _InMemoryEntryStatus.IN_PROGRESS:
                continue
            del self._entries[key]
            return True
        return False


class CommandDispatcher:
    """Dispatch canonical command envelopes to registered async handlers."""

    def __init__(
        self,
        *,
        registry: CommandHandlerRegistry,
        clock: Clock,
        idempotency_hook: CommandIdempotencyHook | None = None,
    ) -> None:
        self._registry = registry
        self._clock = clock
        self._idempotency_hook = idempotency_hook or InMemoryCommandIdempotencyHook()

    async def dispatch(self, command: CommandEnvelope) -> CommandDispatchResult:
        try:
            registration = self._registry.get(command.command_type)
        except (UnknownCommandTypeError, ValueError):
            return _result_for_failure(
                command,
                CommandFailure(
                    kind=CommandFailureKind.UNKNOWN_COMMAND_TYPE,
                    message="command type is not registered",
                    retryable=False,
                ),
                status=CommandDispatchStatus.REJECTED,
            )

        if registration.schema_version != command.schema_version:
            return _result_for_failure(
                command,
                CommandFailure(
                    kind=CommandFailureKind.SCHEMA_VERSION_MISMATCH,
                    message="command schema version does not match registered handler",
                    retryable=False,
                ),
                status=CommandDispatchStatus.REJECTED,
            )

        try:
            decision = await self._idempotency_hook.before_dispatch(command)
        except Exception:
            return _idempotency_hook_error(command)

        duplicate_result = _result_for_idempotency_decision(command, decision)
        if duplicate_result is not None:
            return duplicate_result

        if command.deadline_at is not None and self._clock.now() > command.deadline_at:
            return await self._record_failure(
                command,
                CommandFailure(
                    kind=CommandFailureKind.DEADLINE_EXCEEDED,
                    message="command deadline has expired",
                    retryable=False,
                ),
                status=CommandDispatchStatus.REJECTED,
            )

        context = CommandContext.from_command(command)
        try:
            result = await registration.handler(command, context)
        except CommandRejectedError as exc:
            failure = CommandFailure(
                kind=CommandFailureKind.HANDLER_REJECTED,
                message=exc.safe_message,
                retryable=exc.retryable,
            )
            return await self._record_failure(
                command, failure, status=CommandDispatchStatus.REJECTED
            )
        except CommandHandlerError as exc:
            failure = CommandFailure(
                kind=exc.kind,
                message=exc.safe_message,
                retryable=exc.retryable,
            )
            return await self._record_failure(command, failure, status=CommandDispatchStatus.FAILED)
        except Exception as exc:
            failure = CommandFailure(
                kind=CommandFailureKind.HANDLER_ERROR,
                message=f"{type(exc).__name__} raised by command handler",
                retryable=False,
            )
            return await self._record_failure(command, failure, status=CommandDispatchStatus.FAILED)

        try:
            await self._idempotency_hook.record_success(command, result)
        except Exception:
            return _idempotency_hook_error(command)

        return CommandDispatchResult(
            command_id=command.command_id,
            command_type=command.command_type,
            correlation_id=command.correlation_id,
            status=CommandDispatchStatus.COMPLETED,
            result=result,
        )

    async def _record_failure(
        self,
        command: CommandEnvelope,
        failure: CommandFailure,
        *,
        status: CommandDispatchStatus,
    ) -> CommandDispatchResult:
        try:
            await self._idempotency_hook.record_failure(command, failure)
        except Exception:
            return _idempotency_hook_error(command)
        return _result_for_failure(command, failure, status=status)


def _result_for_idempotency_decision(
    command: CommandEnvelope,
    decision: CommandIdempotencyDecision,
) -> CommandDispatchResult | None:
    if decision.status is CommandIdempotencyStatus.CLAIMED:
        return None
    if decision.status is CommandIdempotencyStatus.DUPLICATE_COMPLETED:
        return CommandDispatchResult(
            command_id=command.command_id,
            command_type=command.command_type,
            correlation_id=command.correlation_id,
            status=CommandDispatchStatus.DUPLICATE,
            result=decision.result,
        )
    if decision.status is CommandIdempotencyStatus.DUPLICATE_FAILED:
        if decision.failure is None:
            failure = CommandFailure(
                kind=CommandFailureKind.IDEMPOTENCY_REJECTED,
                message="duplicate command has no failure metadata",
                retryable=False,
            )
        else:
            failure = decision.failure
        return _result_for_failure(command, failure, status=CommandDispatchStatus.DUPLICATE)
    if decision.status is CommandIdempotencyStatus.DUPLICATE_IN_PROGRESS:
        return _result_for_failure(
            command,
            CommandFailure(
                kind=CommandFailureKind.DUPLICATE_IN_PROGRESS,
                message=decision.reason or "command idempotency key is already in progress",
                retryable=True,
            ),
            status=CommandDispatchStatus.REJECTED,
        )
    if decision.status is CommandIdempotencyStatus.CONFLICT:
        return _result_for_failure(
            command,
            CommandFailure(
                kind=CommandFailureKind.IDEMPOTENCY_CONFLICT,
                message=decision.reason or "command idempotency key conflicts with another request",
                retryable=False,
            ),
            status=CommandDispatchStatus.REJECTED,
        )
    return _result_for_failure(
        command,
        CommandFailure(
            kind=CommandFailureKind.IDEMPOTENCY_REJECTED,
            message=decision.reason or "command idempotency hook rejected command",
            retryable=True,
        ),
        status=CommandDispatchStatus.REJECTED,
    )


def _command_idempotency_fingerprint(command: CommandEnvelope) -> str:
    return canonical_sha256(
        {
            "attributes": command.attributes,
            "command_type": command.command_type,
            "deadline_at": command.deadline_at,
            "issuer": command.issuer,
            "priority": command.priority,
            "schema_version": command.schema_version,
        }
    )


def _idempotency_hook_error(command: CommandEnvelope) -> CommandDispatchResult:
    return _result_for_failure(
        command,
        CommandFailure(
            kind=CommandFailureKind.IDEMPOTENCY_HOOK_ERROR,
            message="command idempotency hook raised an exception",
            retryable=True,
        ),
        status=CommandDispatchStatus.FAILED,
    )


def _result_for_failure(
    command: CommandEnvelope,
    failure: CommandFailure,
    *,
    status: CommandDispatchStatus,
) -> CommandDispatchResult:
    return CommandDispatchResult(
        command_id=command.command_id,
        command_type=command.command_type,
        correlation_id=command.correlation_id,
        status=status,
        failure=failure,
    )
