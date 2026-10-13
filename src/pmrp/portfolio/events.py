"""Factories for canonical portfolio event contracts."""

from __future__ import annotations

from dataclasses import dataclass

from pmrp.events import EventFactory
from pmrp.schemas.events import (
    PORTFOLIO_CASH_BALANCE_CHANGED_EVENT_TYPE,
    PORTFOLIO_MISMATCH_DETECTED_EVENT_TYPE,
    PORTFOLIO_PNL_UPDATED_EVENT_TYPE,
    PORTFOLIO_POSITION_CHANGED_EVENT_TYPE,
    PORTFOLIO_RECONCILED_EVENT_TYPE,
    CashBalanceChangedEvent,
    PnlUpdatedEvent,
    PortfolioMismatchDetectedEvent,
    PortfolioReconciledEvent,
    PositionChangedEvent,
)
from pmrp.schemas.identifiers import CausationRef, CorrelationId, FillId
from pmrp.schemas.portfolio import (
    CashBalance,
    PnlAttribution,
    Position,
    ReconciliationResult,
    ReconciliationStatus,
)

type PortfolioCanonicalEvent = (
    CashBalanceChangedEvent
    | PnlUpdatedEvent
    | PortfolioMismatchDetectedEvent
    | PortfolioReconciledEvent
    | PositionChangedEvent
)
type PortfolioReconciliationEvent = PortfolioMismatchDetectedEvent | PortfolioReconciledEvent


@dataclass(frozen=True, slots=True)
class PortfolioEventFactory:
    """Build canonical portfolio events with validated envelope lineage."""

    event_factory: EventFactory
    producer: str = "portfolio"

    def build_position_changed_event(
        self,
        *,
        current_position: Position,
        previous_position: Position | None = None,
        source_fill_id: FillId | None = None,
        correlation_id: CorrelationId | None = None,
        causation_id: CausationRef | None = None,
    ) -> PositionChangedEvent:
        """Build the event that records a position projection update."""

        return PositionChangedEvent(
            envelope=self.event_factory.create_envelope(
                event_type=PORTFOLIO_POSITION_CHANGED_EVENT_TYPE,
                producer=self.producer,
                occurred_at=current_position.last_updated_at,
                exchange=current_position.exchange,
                market_id=current_position.market_id,
                account_id=current_position.account_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
            ),
            previous_position=previous_position,
            current_position=current_position,
            source_fill_id=source_fill_id,
        )

    def build_cash_balance_changed_event(
        self,
        *,
        current_balance: CashBalance,
        reason: str,
        previous_balance: CashBalance | None = None,
        correlation_id: CorrelationId | None = None,
        causation_id: CausationRef | None = None,
    ) -> CashBalanceChangedEvent:
        """Build the event that records a cash balance projection update."""

        return CashBalanceChangedEvent(
            envelope=self.event_factory.create_envelope(
                event_type=PORTFOLIO_CASH_BALANCE_CHANGED_EVENT_TYPE,
                producer=self.producer,
                occurred_at=current_balance.captured_at,
                exchange=current_balance.exchange,
                account_id=current_balance.account_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
            ),
            previous_balance=previous_balance,
            current_balance=current_balance,
            reason=reason,
        )

    def build_pnl_updated_event(
        self,
        attribution: PnlAttribution,
        *,
        correlation_id: CorrelationId | None = None,
        causation_id: CausationRef | None = None,
    ) -> PnlUpdatedEvent:
        """Build the event that records a PnL attribution update."""

        return PnlUpdatedEvent(
            envelope=self.event_factory.create_envelope(
                event_type=PORTFOLIO_PNL_UPDATED_EVENT_TYPE,
                producer=self.producer,
                occurred_at=attribution.ends_at,
                exchange=attribution.exchange,
                market_id=attribution.market_id,
                strategy_id=attribution.strategy_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
            ),
            attribution=attribution,
        )

    def build_reconciliation_event(
        self,
        result: ReconciliationResult,
        *,
        correlation_id: CorrelationId | None = None,
        causation_id: CausationRef | None = None,
    ) -> PortfolioReconciliationEvent:
        """Build the portfolio event implied by a completed reconciliation result."""

        if result.status is ReconciliationStatus.HEALTHY:
            return self.build_reconciled_event(
                result,
                correlation_id=correlation_id,
                causation_id=causation_id,
            )
        return self.build_mismatch_detected_event(
            result,
            correlation_id=correlation_id,
            causation_id=causation_id,
        )

    def build_reconciled_event(
        self,
        result: ReconciliationResult,
        *,
        correlation_id: CorrelationId | None = None,
        causation_id: CausationRef | None = None,
    ) -> PortfolioReconciledEvent:
        """Build the event that records a healthy reconciliation result."""

        return PortfolioReconciledEvent(
            envelope=self.event_factory.create_envelope(
                event_type=PORTFOLIO_RECONCILED_EVENT_TYPE,
                producer=self.producer,
                occurred_at=result.completed_at,
                exchange=result.exchange,
                account_id=result.account_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
            ),
            result=result,
        )

    def build_mismatch_detected_event(
        self,
        result: ReconciliationResult,
        *,
        correlation_id: CorrelationId | None = None,
        causation_id: CausationRef | None = None,
    ) -> PortfolioMismatchDetectedEvent:
        """Build the event that records a non-healthy reconciliation result."""

        if not result.mismatches:
            msg = "portfolio mismatch event requires at least one reconciliation mismatch"
            raise ValueError(msg)
        return PortfolioMismatchDetectedEvent(
            envelope=self.event_factory.create_envelope(
                event_type=PORTFOLIO_MISMATCH_DETECTED_EVENT_TYPE,
                producer=self.producer,
                occurred_at=result.completed_at,
                exchange=result.exchange,
                account_id=result.account_id,
                correlation_id=correlation_id,
                causation_id=causation_id,
            ),
            result=result,
        )
