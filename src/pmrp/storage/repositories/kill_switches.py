"""Typed repository for durable risk kill-switch gates."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Select, Update, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.risk import KillSwitchScope, KillSwitchState
from pmrp.schemas.time import parse_utc_datetime
from pmrp.storage.errors import classify_storage_error
from pmrp.storage.models import KillSwitchRow

_KILL_SWITCH_ID_MAX_LENGTH = 128
_AUDIT_ACTOR_MAX_LENGTH = 128
_AUDIT_REASON_MAX_LENGTH = 1024
_SCOPE_ID_MAX_LENGTH = 256
_DEFAULT_ACTIVE_LIMIT = 100
_MAX_ACTIVE_LIMIT = 1_000


class KillSwitchRepository:
    """Persist, query, and release scoped risk kill switches."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, kill_switch: KillSwitchState) -> None:
        """Insert a kill switch state and flush without committing."""

        row = kill_switch_to_row(kill_switch)
        try:
            self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get(self, kill_switch_id: str) -> KillSwitchState | None:
        """Return a kill switch by its durable ID."""

        _validate_kill_switch_id(kill_switch_id)
        statement = select(KillSwitchRow).where(KillSwitchRow.kill_switch_id == kill_switch_id)
        return await self._one_or_none(statement)

    async def list_active(
        self,
        *,
        scope: KillSwitchScope | None = None,
        scope_id: str | None = None,
        limit: int = _DEFAULT_ACTIVE_LIMIT,
    ) -> tuple[KillSwitchState, ...]:
        """Return active kill switches for optional scope filters."""

        _validate_limit(limit)
        statement = (
            select(KillSwitchRow)
            .where(KillSwitchRow.active.is_(True))
            .order_by(KillSwitchRow.scope, KillSwitchRow.scope_id, KillSwitchRow.kill_switch_id)
            .limit(limit)
        )
        if scope is not None:
            statement = statement.where(KillSwitchRow.scope == KillSwitchScope(scope).value)
        if scope_id is not None:
            scope_id = _validate_scope_id(scope_id)
            statement = statement.where(KillSwitchRow.scope_id == scope_id)
        return await self._many(statement)

    async def release(
        self,
        kill_switch_id: str,
        *,
        released_at: datetime,
        released_by: str,
        release_reason: str,
    ) -> int:
        """Release one active kill switch and return the updated row count."""

        _validate_kill_switch_id(kill_switch_id)
        released_at = parse_utc_datetime(released_at)
        released_by = _validate_audit_actor(released_by, field_name="released_by")
        release_reason = _validate_audit_reason(release_reason, field_name="release_reason")
        statement = (
            update(KillSwitchRow)
            .where(
                KillSwitchRow.kill_switch_id == kill_switch_id,
                KillSwitchRow.active.is_(True),
                KillSwitchRow.released_at.is_(None),
            )
            .values(
                active=False,
                released_at=released_at,
                released_by=released_by,
                release_reason=release_reason,
                updated_at=released_at,
                aggregate_version=KillSwitchRow.aggregate_version + 1,
            )
        )
        return await self._execute_update(statement)

    async def _one_or_none(
        self,
        statement: Select[tuple[KillSwitchRow]],
    ) -> KillSwitchState | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        row = result.scalar_one_or_none()
        if row is None:
            return None
        return kill_switch_from_row(row)

    async def _many(
        self,
        statement: Select[tuple[KillSwitchRow]],
    ) -> tuple[KillSwitchState, ...]:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return tuple(kill_switch_from_row(row) for row in result.scalars().all())

    async def _execute_update(self, statement: Update) -> int:
        try:
            result = await self._session.execute(statement)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        return int(getattr(result, "rowcount", 0) or 0)


def kill_switch_to_row(kill_switch: KillSwitchState) -> KillSwitchRow:
    """Map a canonical kill switch state into its storage row."""

    return KillSwitchRow(
        kill_switch_id=kill_switch.kill_switch_id,
        scope=kill_switch.scope.value,
        scope_id=kill_switch.scope_id,
        active=kill_switch.active,
        activated_at=kill_switch.activated_at,
        activated_by=kill_switch.activated_by,
        activation_reason=kill_switch.activation_reason,
        released_at=kill_switch.released_at,
        released_by=kill_switch.released_by,
        release_reason=kill_switch.release_reason,
        aggregate_version=kill_switch.version,
    )


def kill_switch_from_row(row: KillSwitchRow) -> KillSwitchState:
    """Map a storage row into a validated canonical kill switch state."""

    return KillSwitchState(
        kill_switch_id=row.kill_switch_id,
        scope=KillSwitchScope(row.scope),
        scope_id=row.scope_id,
        active=row.active,
        activated_at=row.activated_at,
        activated_by=row.activated_by,
        activation_reason=row.activation_reason,
        released_at=row.released_at,
        released_by=row.released_by,
        release_reason=row.release_reason,
        version=row.aggregate_version,
    )


def _validate_kill_switch_id(kill_switch_id: str) -> None:
    if type(kill_switch_id) is not str:
        msg = "kill switch ID must be a string"
        raise TypeError(msg)
    if kill_switch_id == "":
        raise ValueError("kill switch ID must not be empty")
    if len(kill_switch_id) > _KILL_SWITCH_ID_MAX_LENGTH:
        raise ValueError("kill switch ID must be at most 128 characters")


def _validate_scope_id(scope_id: str) -> str:
    if type(scope_id) is not str:
        msg = "kill switch scope_id must be a string"
        raise TypeError(msg)
    if scope_id == "":
        raise ValueError("kill switch scope_id must not be empty")
    if len(scope_id) > _SCOPE_ID_MAX_LENGTH:
        raise ValueError("kill switch scope_id must be at most 256 characters")
    return scope_id


def _validate_audit_actor(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        msg = f"kill switch {field_name} must be a string"
        raise TypeError(msg)
    if value == "":
        raise ValueError(f"kill switch {field_name} must not be empty")
    if len(value) > _AUDIT_ACTOR_MAX_LENGTH:
        raise ValueError(f"kill switch {field_name} must be at most 128 characters")
    return value


def _validate_audit_reason(value: str, *, field_name: str) -> str:
    if type(value) is not str:
        msg = f"kill switch {field_name} must be a string"
        raise TypeError(msg)
    if value == "":
        raise ValueError(f"kill switch {field_name} must not be empty")
    if len(value) > _AUDIT_REASON_MAX_LENGTH:
        raise ValueError(f"kill switch {field_name} must be at most 1024 characters")
    return value


def _validate_limit(limit: int) -> None:
    if type(limit) is not int:
        msg = "kill switch list limit must be an integer"
        raise TypeError(msg)
    if limit <= 0:
        raise ValueError("kill switch list limit must be positive")
    if limit > _MAX_ACTIVE_LIMIT:
        raise ValueError("kill switch list limit must be at most 1000")
