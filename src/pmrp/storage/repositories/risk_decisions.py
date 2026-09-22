"""Typed repository for immutable risk decision persistence."""

from __future__ import annotations

from datetime import datetime
from typing import cast

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from pmrp.schemas.enums import RiskDecisionStatus
from pmrp.schemas.identifiers import IntentId, RiskDecisionId
from pmrp.schemas.risk import RiskDecision
from pmrp.schemas.serialization import canonical_sha256, to_canonical_data
from pmrp.schemas.time import parse_utc_datetime
from pmrp.storage.errors import InvariantViolationError, classify_storage_error
from pmrp.storage.models import RiskDecisionRow


class RiskDecisionRepository:
    """Persist and query immutable canonical risk decisions."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, decision: RiskDecision) -> None:
        """Insert a canonical risk decision and flush without committing."""

        row = risk_decision_to_row(decision)
        try:
            self._session.add(row)
            await self._session.flush()
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

    async def get_by_key(
        self,
        *,
        evaluated_at: datetime,
        risk_decision_id: RiskDecisionId,
    ) -> RiskDecision | None:
        """Return a decision by its partition key and decision ID."""

        risk_decision_id = RiskDecisionId(risk_decision_id)
        evaluated_at = parse_utc_datetime(evaluated_at)
        statement = select(RiskDecisionRow).where(
            RiskDecisionRow.evaluated_at == evaluated_at,
            RiskDecisionRow.risk_decision_id == str(risk_decision_id),
        )
        return await self._one_or_none(statement)

    async def get_latest_for_intent(self, intent_id: IntentId) -> RiskDecision | None:
        """Return the latest decision recorded for an order intent."""

        intent_id = IntentId(intent_id)
        statement = (
            select(RiskDecisionRow)
            .where(RiskDecisionRow.intent_id == str(intent_id))
            .order_by(RiskDecisionRow.evaluated_at.desc())
            .limit(1)
        )
        return await self._one_or_none(statement)

    async def _one_or_none(self, statement: Select[tuple[RiskDecisionRow]]) -> RiskDecision | None:
        try:
            result = await self._session.execute(statement)
        except SQLAlchemyError as exc:
            raise classify_storage_error(exc) from exc

        row = result.scalar_one_or_none()
        if row is None:
            return None
        return risk_decision_from_row(row)


def risk_decision_to_row(decision: RiskDecision) -> RiskDecisionRow:
    """Map a canonical risk decision into its immutable storage row."""

    rule_results = _risk_rule_results_json(decision)
    return RiskDecisionRow(
        evaluated_at=decision.evaluated_at,
        risk_decision_id=str(decision.risk_decision_id),
        intent_id=str(decision.intent_id),
        status=decision.status.value,
        input_snapshot_id=decision.input_snapshot_id,
        approved_quantity=decision.approved_quantity,
        approved_limit_price=decision.approved_limit_price,
        approval_expires_at=decision.approval_expires_at,
        configuration_hash=decision.configuration_hash,
        correlation_id=str(decision.correlation_id),
        rule_results=rule_results,
        payload_hash=canonical_sha256(decision),
    )


def risk_decision_from_row(row: RiskDecisionRow) -> RiskDecision:
    """Map a storage row back into a validated canonical risk decision."""

    decision = RiskDecision.model_validate(
        {
            "risk_decision_id": row.risk_decision_id,
            "intent_id": row.intent_id,
            "status": RiskDecisionStatus(row.status),
            "evaluated_at": row.evaluated_at,
            "input_snapshot_id": row.input_snapshot_id,
            "rule_results": tuple(row.rule_results),
            "approved_quantity": row.approved_quantity,
            "approved_limit_price": row.approved_limit_price,
            "approval_expires_at": row.approval_expires_at,
            "configuration_hash": row.configuration_hash,
            "correlation_id": row.correlation_id,
        }
    )
    expected_hash = canonical_sha256(decision)
    if row.payload_hash != expected_hash:
        raise InvariantViolationError(
            "risk decision payload hash mismatch",
            context={"risk_decision_id": row.risk_decision_id},
        )
    return decision


def _risk_rule_results_json(decision: RiskDecision) -> list[dict[str, object]]:
    rule_results = to_canonical_data(decision.rule_results)
    if not isinstance(rule_results, list) or not all(
        isinstance(result, dict) for result in rule_results
    ):
        raise InvariantViolationError("risk decision rule results must serialize as a JSON list")
    return cast("list[dict[str, object]]", rule_results)
