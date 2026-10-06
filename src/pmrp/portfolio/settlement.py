"""Settlement accounting helpers for portfolio positions."""

from __future__ import annotations

from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Final

from pmrp.portfolio.balances import CashBalanceProjectionResult, apply_journal_to_cash_balance
from pmrp.portfolio.errors import PortfolioProjectionError
from pmrp.portfolio.journal import (
    ACCOUNT_CASH,
    ACCOUNT_POSITION_COST,
    ACCOUNT_SETTLEMENT_PNL,
)
from pmrp.schemas.identifiers import EventId
from pmrp.schemas.numeric import Money, validate_currency
from pmrp.schemas.portfolio import (
    AccountingJournalEntry,
    CashBalance,
    JournalLine,
    Position,
    Settlement,
    SettlementStatus,
)
from pmrp.schemas.serialization import canonical_sha256

SETTLEMENT_REFERENCE_TYPE: Final = "settlement"

_ZERO = Decimal("0")


@dataclass(frozen=True, slots=True)
class SettlementAccountingResult:
    """Settlement accounting amounts for one canonical position."""

    cash_delta: Money
    position_cost_basis: Money
    settlement_pnl: Money
    settled_quantity: Decimal
    winning_position: bool


@dataclass(frozen=True, slots=True)
class SettlementPositionProjectionResult:
    """Result of closing one canonical position through settlement."""

    position: Position
    settlement_accounting: SettlementAccountingResult


@dataclass(frozen=True, slots=True)
class SettlementApplicationResult:
    """Result of idempotently applying a settlement to position and cash projections."""

    position: Position
    cash_balance: CashBalance
    position_projection: SettlementPositionProjectionResult | None
    cash_projection: CashBalanceProjectionResult | None
    journal_entry: AccountingJournalEntry | None
    applied_journal_entry_ids: frozenset[str]
    applied: bool
    duplicate_settlement: bool


@dataclass(frozen=True, slots=True)
class SettlementCorrectionAccountingResult:
    """Delta accounting required to replace one applied settlement with a correction."""

    previous_accounting: SettlementAccountingResult
    corrected_accounting: SettlementAccountingResult
    cash_delta: Money
    position_cost_basis_delta: Money
    settlement_pnl_delta: Money


@dataclass(frozen=True, slots=True)
class SettlementCorrectionApplicationResult:
    """Result of idempotently applying a settlement correction."""

    position: Position
    cash_balance: CashBalance
    correction_accounting: SettlementCorrectionAccountingResult | None
    cash_projection: CashBalanceProjectionResult | None
    journal_entry: AccountingJournalEntry | None
    applied_journal_entry_ids: frozenset[str]
    applied: bool
    duplicate_correction: bool


def build_settlement_accounting_result(
    *,
    position: Position,
    settlement: Settlement,
    currency: str,
) -> SettlementAccountingResult:
    """Calculate deterministic settlement amounts for one position."""

    validated_currency = validate_currency(currency)
    return _build_settlement_accounting_result(
        position=position,
        settlement=settlement,
        currency=validated_currency,
        allowed_statuses=frozenset({SettlementStatus.SETTLED}),
    )


def build_settlement_correction_accounting_result(
    *,
    original_position: Position,
    previous_settlement: Settlement,
    corrected_settlement: Settlement,
    currency: str,
) -> SettlementCorrectionAccountingResult:
    """Calculate the delta required to correct a previously applied settlement."""

    validated_currency = validate_currency(currency)
    _validate_corrected_settlement(
        original_position=original_position,
        previous_settlement=previous_settlement,
        corrected_settlement=corrected_settlement,
        currency=validated_currency,
    )
    previous_accounting = _build_settlement_accounting_result(
        position=original_position,
        settlement=previous_settlement,
        currency=validated_currency,
        allowed_statuses=frozenset({SettlementStatus.SETTLED}),
    )
    corrected_accounting = _build_settlement_accounting_result(
        position=original_position,
        settlement=corrected_settlement,
        currency=validated_currency,
        allowed_statuses=frozenset({SettlementStatus.CORRECTED}),
    )
    cash_delta = corrected_accounting.cash_delta.amount - previous_accounting.cash_delta.amount
    position_cost_basis_delta = (
        corrected_accounting.position_cost_basis.amount
        - previous_accounting.position_cost_basis.amount
    )
    settlement_pnl_delta = (
        corrected_accounting.settlement_pnl.amount - previous_accounting.settlement_pnl.amount
    )

    return SettlementCorrectionAccountingResult(
        previous_accounting=previous_accounting,
        corrected_accounting=corrected_accounting,
        cash_delta=Money(amount=cash_delta, currency=validated_currency),
        position_cost_basis_delta=Money(
            amount=position_cost_basis_delta,
            currency=validated_currency,
        ),
        settlement_pnl_delta=Money(amount=settlement_pnl_delta, currency=validated_currency),
    )


def _build_settlement_accounting_result(
    *,
    position: Position,
    settlement: Settlement,
    currency: str,
    allowed_statuses: frozenset[SettlementStatus],
) -> SettlementAccountingResult:
    _validate_settlement_position(
        position,
        settlement,
        currency=currency,
        allowed_statuses=allowed_statuses,
    )

    assert settlement.payout_per_unit is not None
    assert position.average_entry_price is not None
    position_cost_basis = position.quantity * position.average_entry_price
    winning_position = position.outcome_id in settlement.winning_outcome_ids
    payout_per_unit = settlement.payout_per_unit if winning_position else _ZERO
    cash_delta = position.quantity * payout_per_unit
    settlement_pnl = cash_delta - position_cost_basis

    return SettlementAccountingResult(
        cash_delta=Money(amount=cash_delta, currency=currency),
        position_cost_basis=Money(amount=position_cost_basis, currency=currency),
        settlement_pnl=Money(amount=settlement_pnl, currency=currency),
        settled_quantity=abs(position.quantity),
        winning_position=winning_position,
    )


def apply_settlement_to_position(
    *,
    position: Position,
    settlement: Settlement,
    currency: str,
) -> SettlementPositionProjectionResult:
    """Close one position through a settled market outcome."""

    validated_currency = validate_currency(currency)
    _validate_settlement_position(
        position,
        settlement,
        currency=validated_currency,
        allowed_statuses=frozenset({SettlementStatus.SETTLED}),
    )
    assert settlement.settled_at is not None
    if settlement.settled_at < position.last_updated_at:
        msg = "settlement settled_at is older than the position update horizon"
        raise PortfolioProjectionError(msg)

    accounting = build_settlement_accounting_result(
        position=position,
        settlement=settlement,
        currency=validated_currency,
    )
    projected_position = Position(
        position_id=position.position_id,
        exchange=position.exchange,
        account_id=position.account_id,
        market_id=position.market_id,
        contract_id=position.contract_id,
        outcome_id=position.outcome_id,
        quantity=_ZERO,
        average_entry_price=None,
        realized_pnl=Money(
            amount=position.realized_pnl.amount + accounting.settlement_pnl.amount,
            currency=validated_currency,
        ),
        unrealized_pnl=Money(amount=_ZERO, currency=validated_currency),
        fees_paid=position.fees_paid,
        rebates_received=position.rebates_received,
        opened_at=None,
        last_updated_at=settlement.settled_at,
        aggregate_version=position.aggregate_version + 1,
    )
    return SettlementPositionProjectionResult(
        position=projected_position,
        settlement_accounting=accounting,
    )


def apply_settlement_once(
    *,
    position: Position,
    cash_balance: CashBalance,
    settlement: Settlement,
    applied_journal_entry_ids: AbstractSet[str],
    currency: str,
    source_event_id: EventId,
    created_at: datetime,
) -> SettlementApplicationResult:
    """Apply a settlement once and return a no-op result for duplicates."""

    validated_currency = validate_currency(currency)
    _validate_cash_balance_for_position(
        cash_balance,
        position,
        currency=validated_currency,
    )
    existing_journal_ids = frozenset(applied_journal_entry_ids)
    journal_entry_id = derive_settlement_journal_entry_id(position, settlement)
    if journal_entry_id in existing_journal_ids:
        return SettlementApplicationResult(
            position=position,
            cash_balance=cash_balance,
            position_projection=None,
            cash_projection=None,
            journal_entry=None,
            applied_journal_entry_ids=existing_journal_ids,
            applied=False,
            duplicate_settlement=True,
        )

    position_projection = apply_settlement_to_position(
        position=position,
        settlement=settlement,
        currency=validated_currency,
    )
    journal_entry = build_settlement_journal_entry(
        position=position,
        settlement=settlement,
        currency=validated_currency,
        source_event_id=source_event_id,
        created_at=created_at,
    )
    cash_projection = apply_journal_to_cash_balance(cash_balance, journal_entry)

    return SettlementApplicationResult(
        position=position_projection.position,
        cash_balance=cash_projection.balance,
        position_projection=position_projection,
        cash_projection=cash_projection,
        journal_entry=journal_entry,
        applied_journal_entry_ids=existing_journal_ids | {journal_entry_id},
        applied=True,
        duplicate_settlement=False,
    )


def build_settlement_journal_entry(
    *,
    position: Position,
    settlement: Settlement,
    currency: str,
    source_event_id: EventId,
    created_at: datetime,
) -> AccountingJournalEntry:
    """Build a balanced accounting journal entry for one settled position."""

    result = build_settlement_accounting_result(
        position=position,
        settlement=settlement,
        currency=currency,
    )
    assert settlement.settled_at is not None

    return AccountingJournalEntry(
        journal_entry_id=derive_settlement_journal_entry_id(position, settlement),
        occurred_at=settlement.settled_at,
        source_event_id=source_event_id,
        reference_type=SETTLEMENT_REFERENCE_TYPE,
        reference_id=settlement.settlement_id,
        lines=(
            JournalLine(
                account_code=ACCOUNT_CASH,
                amount=result.cash_delta.amount,
                currency=result.cash_delta.currency,
                description="Settlement cash movement.",
            ),
            JournalLine(
                account_code=ACCOUNT_POSITION_COST,
                amount=-result.position_cost_basis.amount,
                currency=result.position_cost_basis.currency,
                description="Settlement clears position cost basis.",
            ),
            JournalLine(
                account_code=ACCOUNT_SETTLEMENT_PNL,
                amount=-result.settlement_pnl.amount,
                currency=result.settlement_pnl.currency,
                description="Settlement PnL offset.",
            ),
        ),
        description=f"Settlement accounting for {position.position_id}.",
        created_at=created_at,
    )


def apply_settlement_correction_once(
    *,
    original_position: Position,
    settled_position: Position,
    cash_balance: CashBalance,
    previous_settlement: Settlement,
    corrected_settlement: Settlement,
    applied_journal_entry_ids: AbstractSet[str],
    currency: str,
    source_event_id: EventId,
    created_at: datetime,
) -> SettlementCorrectionApplicationResult:
    """Apply a corrected settlement once as a delta to existing projections."""

    validated_currency = validate_currency(currency)
    _validate_settlement_correction_identity(
        original_position=original_position,
        settled_position=settled_position,
        cash_balance=cash_balance,
        previous_settlement=previous_settlement,
        corrected_settlement=corrected_settlement,
        currency=validated_currency,
    )
    existing_journal_ids = frozenset(applied_journal_entry_ids)
    journal_entry_id = derive_settlement_correction_journal_entry_id(
        original_position=original_position,
        previous_settlement=previous_settlement,
        corrected_settlement=corrected_settlement,
    )
    if journal_entry_id in existing_journal_ids:
        return SettlementCorrectionApplicationResult(
            position=settled_position,
            cash_balance=cash_balance,
            correction_accounting=None,
            cash_projection=None,
            journal_entry=None,
            applied_journal_entry_ids=existing_journal_ids,
            applied=False,
            duplicate_correction=True,
        )

    _validate_settlement_correction_application(
        settled_position=settled_position,
        corrected_settlement=corrected_settlement,
    )
    accounting = build_settlement_correction_accounting_result(
        original_position=original_position,
        previous_settlement=previous_settlement,
        corrected_settlement=corrected_settlement,
        currency=validated_currency,
    )
    journal_entry = build_settlement_correction_journal_entry(
        original_position=original_position,
        previous_settlement=previous_settlement,
        corrected_settlement=corrected_settlement,
        currency=validated_currency,
        source_event_id=source_event_id,
        created_at=created_at,
    )
    cash_projection = apply_journal_to_cash_balance(cash_balance, journal_entry)

    assert corrected_settlement.settled_at is not None
    corrected_position = Position(
        position_id=settled_position.position_id,
        exchange=settled_position.exchange,
        account_id=settled_position.account_id,
        market_id=settled_position.market_id,
        contract_id=settled_position.contract_id,
        outcome_id=settled_position.outcome_id,
        quantity=_ZERO,
        average_entry_price=None,
        realized_pnl=Money(
            amount=settled_position.realized_pnl.amount + accounting.settlement_pnl_delta.amount,
            currency=validated_currency,
        ),
        unrealized_pnl=Money(amount=_ZERO, currency=validated_currency),
        fees_paid=settled_position.fees_paid,
        rebates_received=settled_position.rebates_received,
        opened_at=None,
        last_updated_at=corrected_settlement.settled_at,
        aggregate_version=settled_position.aggregate_version + 1,
    )

    return SettlementCorrectionApplicationResult(
        position=corrected_position,
        cash_balance=cash_projection.balance,
        correction_accounting=accounting,
        cash_projection=cash_projection,
        journal_entry=journal_entry,
        applied_journal_entry_ids=existing_journal_ids | {journal_entry_id},
        applied=True,
        duplicate_correction=False,
    )


def build_settlement_correction_journal_entry(
    *,
    original_position: Position,
    previous_settlement: Settlement,
    corrected_settlement: Settlement,
    currency: str,
    source_event_id: EventId,
    created_at: datetime,
) -> AccountingJournalEntry:
    """Build a balanced journal entry for replacing one settlement with a correction."""

    result = build_settlement_correction_accounting_result(
        original_position=original_position,
        previous_settlement=previous_settlement,
        corrected_settlement=corrected_settlement,
        currency=currency,
    )
    assert corrected_settlement.settled_at is not None

    return AccountingJournalEntry(
        journal_entry_id=derive_settlement_correction_journal_entry_id(
            original_position=original_position,
            previous_settlement=previous_settlement,
            corrected_settlement=corrected_settlement,
        ),
        occurred_at=corrected_settlement.settled_at,
        source_event_id=source_event_id,
        reference_type=SETTLEMENT_REFERENCE_TYPE,
        reference_id=corrected_settlement.settlement_id,
        lines=(
            JournalLine(
                account_code=ACCOUNT_CASH,
                amount=result.cash_delta.amount,
                currency=result.cash_delta.currency,
                description="Settlement correction cash delta.",
            ),
            JournalLine(
                account_code=ACCOUNT_POSITION_COST,
                amount=-result.position_cost_basis_delta.amount,
                currency=result.position_cost_basis_delta.currency,
                description="Settlement correction position cost delta.",
            ),
            JournalLine(
                account_code=ACCOUNT_SETTLEMENT_PNL,
                amount=-result.settlement_pnl_delta.amount,
                currency=result.settlement_pnl_delta.currency,
                description="Settlement correction PnL delta.",
            ),
        ),
        description=(
            "Settlement correction accounting for "
            f"{original_position.position_id} replacing {previous_settlement.settlement_id}."
        ),
        created_at=created_at,
    )


def derive_settlement_journal_entry_id(position: Position, settlement: Settlement) -> str:
    """Derive a stable journal entry identifier for one position settlement."""

    digest = canonical_sha256(
        {
            "position_id": position.position_id,
            "schema": "pmrp.settlement_journal_entry.v1",
            "settlement_id": settlement.settlement_id,
        }
    ).removeprefix("sha256:")
    return f"journal_settlement_{digest[:32]}"


def derive_settlement_correction_journal_entry_id(
    *,
    original_position: Position,
    previous_settlement: Settlement,
    corrected_settlement: Settlement,
) -> str:
    """Derive a stable journal entry identifier for one settlement correction."""

    digest = canonical_sha256(
        {
            "corrected_settlement_id": corrected_settlement.settlement_id,
            "original_position_id": original_position.position_id,
            "previous_settlement_id": previous_settlement.settlement_id,
            "schema": "pmrp.settlement_correction_journal_entry.v1",
        }
    ).removeprefix("sha256:")
    return f"journal_settlement_correction_{digest[:32]}"


def _validate_settlement_position(
    position: Position,
    settlement: Settlement,
    *,
    currency: str,
    allowed_statuses: frozenset[SettlementStatus],
) -> None:
    if settlement.status not in allowed_statuses:
        expected = ", ".join(sorted(status.value for status in allowed_statuses))
        msg = f"settlement accounting requires settlement status in {{{expected}}}"
        raise PortfolioProjectionError(msg)
    if settlement.settled_at is None:
        msg = "settlement accounting requires settled_at"
        raise PortfolioProjectionError(msg)
    if settlement.payout_per_unit is None:
        msg = "settlement accounting requires payout_per_unit"
        raise PortfolioProjectionError(msg)
    if position.exchange != settlement.exchange:
        msg = "position exchange does not match settlement exchange"
        raise PortfolioProjectionError(msg)
    if position.market_id != settlement.market_id:
        msg = "position market_id does not match settlement market_id"
        raise PortfolioProjectionError(msg)
    if position.quantity == _ZERO:
        msg = "settlement accounting requires nonzero position quantity"
        raise PortfolioProjectionError(msg)
    if position.average_entry_price is None:
        msg = "settlement accounting requires position average_entry_price"
        raise PortfolioProjectionError(msg)
    _validate_money(position.realized_pnl, currency=currency, field_name="realized_pnl")
    _validate_money(position.unrealized_pnl, currency=currency, field_name="unrealized_pnl")
    _validate_money(position.fees_paid, currency=currency, field_name="fees_paid")
    _validate_money(position.rebates_received, currency=currency, field_name="rebates_received")


def _validate_corrected_settlement(
    *,
    original_position: Position,
    previous_settlement: Settlement,
    corrected_settlement: Settlement,
    currency: str,
) -> None:
    if corrected_settlement.status is not SettlementStatus.CORRECTED:
        msg = "settlement correction requires corrected settlement status"
        raise PortfolioProjectionError(msg)
    if corrected_settlement.correction_of_settlement_id != previous_settlement.settlement_id:
        msg = "corrected settlement must reference previous settlement"
        raise PortfolioProjectionError(msg)
    _validate_settlement_position(
        original_position,
        previous_settlement,
        currency=currency,
        allowed_statuses=frozenset({SettlementStatus.SETTLED}),
    )
    _validate_settlement_position(
        original_position,
        corrected_settlement,
        currency=currency,
        allowed_statuses=frozenset({SettlementStatus.CORRECTED}),
    )


def _validate_settlement_correction_identity(
    *,
    original_position: Position,
    settled_position: Position,
    cash_balance: CashBalance,
    previous_settlement: Settlement,
    corrected_settlement: Settlement,
    currency: str,
) -> None:
    _validate_cash_balance_for_position(
        cash_balance,
        settled_position,
        currency=currency,
    )
    _validate_corrected_settlement(
        original_position=original_position,
        previous_settlement=previous_settlement,
        corrected_settlement=corrected_settlement,
        currency=currency,
    )
    _validate_position_identity(original_position, settled_position)
    if settled_position.quantity != _ZERO:
        msg = "settlement correction requires flat settled position"
        raise PortfolioProjectionError(msg)
    if settled_position.average_entry_price is not None:
        msg = "flat settled position must not have average_entry_price"
        raise PortfolioProjectionError(msg)
    _validate_money(
        settled_position.realized_pnl,
        currency=currency,
        field_name="settled_position.realized_pnl",
    )
    _validate_money(
        settled_position.unrealized_pnl,
        currency=currency,
        field_name="settled_position.unrealized_pnl",
    )
    _validate_money(
        settled_position.fees_paid,
        currency=currency,
        field_name="settled_position.fees_paid",
    )
    _validate_money(
        settled_position.rebates_received,
        currency=currency,
        field_name="settled_position.rebates_received",
    )


def _validate_settlement_correction_application(
    *,
    settled_position: Position,
    corrected_settlement: Settlement,
) -> None:
    assert corrected_settlement.settled_at is not None
    if corrected_settlement.settled_at < settled_position.last_updated_at:
        msg = "corrected settlement settled_at is older than the position update horizon"
        raise PortfolioProjectionError(msg)


def _validate_position_identity(original_position: Position, settled_position: Position) -> None:
    identity_fields = (
        "position_id",
        "exchange",
        "account_id",
        "market_id",
        "contract_id",
        "outcome_id",
    )
    for field_name in identity_fields:
        if getattr(original_position, field_name) != getattr(settled_position, field_name):
            msg = f"settled position {field_name} must match original position"
            raise PortfolioProjectionError(msg)


def _validate_money(money: Money, *, currency: str, field_name: str) -> None:
    if money.currency != currency:
        msg = f"{field_name} currency must match settlement currency"
        raise PortfolioProjectionError(msg)


def _validate_cash_balance_for_position(
    cash_balance: CashBalance,
    position: Position,
    *,
    currency: str,
) -> None:
    if cash_balance.exchange != position.exchange:
        msg = "cash balance exchange does not match position exchange"
        raise PortfolioProjectionError(msg)
    if cash_balance.account_id != position.account_id:
        msg = "cash balance account_id does not match position account_id"
        raise PortfolioProjectionError(msg)
    if cash_balance.currency != currency:
        msg = "cash balance currency must match settlement currency"
        raise PortfolioProjectionError(msg)
