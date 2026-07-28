"""Command runtime primitives."""

from pmrp.commands.dispatcher import (
    CommandDispatcher,
    CommandDispatchResult,
    CommandDispatchStatus,
    CommandFailure,
    CommandFailureKind,
    CommandHandlerError,
    CommandIdempotencyDecision,
    CommandIdempotencyHook,
    CommandIdempotencyStatus,
    CommandRejectedError,
    InMemoryCommandIdempotencyHook,
)
from pmrp.commands.registry import (
    CommandContext,
    CommandHandler,
    CommandHandlerRegistration,
    CommandHandlerRegistry,
    UnknownCommandTypeError,
)

__all__ = [
    "CommandContext",
    "CommandDispatchResult",
    "CommandDispatchStatus",
    "CommandDispatcher",
    "CommandFailure",
    "CommandFailureKind",
    "CommandHandler",
    "CommandHandlerError",
    "CommandHandlerRegistration",
    "CommandHandlerRegistry",
    "CommandIdempotencyDecision",
    "CommandIdempotencyHook",
    "CommandIdempotencyStatus",
    "CommandRejectedError",
    "InMemoryCommandIdempotencyHook",
    "UnknownCommandTypeError",
]
