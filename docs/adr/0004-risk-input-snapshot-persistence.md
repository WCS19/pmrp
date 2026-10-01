# ADR-0004: Risk Input Snapshot Persistence

- Status: Proposed
- Date: 2026-10-01
- Owners: PMRP maintainers
- Related issues: None

## Context

`docs/03_SCHEMAS.md` defines `RiskInputSnapshot` as a canonical schema used by
risk evaluation. `docs/06_DATABASE.md` section 64 says the recommended order
creation transaction inserts a risk input snapshot before inserting the risk
decision.

The same database specification defines `pmrp_risk.risk_decisions` with an
`input_snapshot_id` column, but it does not define a physical
`pmrp_risk.risk_input_snapshots` table, indexes, constraints, retention policy,
or migration order. The current Alembic history and SQLAlchemy row models
therefore have nowhere to store risk input snapshots independently of canonical
event payloads.

The implementation impact is concrete: adding a repository or service method
that claims durable risk input snapshot persistence would either invent a table
outside the governing database spec or store snapshots only inside event payloads
while the transaction contract implies a first-class durable record.

## Decision

Treat risk input snapshots as first-class durable risk records. A future
database migration must add a `pmrp_risk.risk_input_snapshots` table before
application services claim to persist the full order creation transaction from
`docs/06_DATABASE.md` section 64.

The table should preserve the canonical `RiskInputSnapshot` fields with Decimal
values stored as `numeric(38,18)`, timezone-aware timestamps, strict boolean
state, and a deterministic payload hash. The risk decision repository should
continue to store `input_snapshot_id`, and a follow-up migration may add an
explicit foreign key once the partitioning and migration constraints are
defined.

Until that table and repository exist, risk workflows may embed
`RiskInputSnapshot` inside canonical risk events and outbox messages, but they
must not present that as the independent durable snapshot insert required by the
order creation transaction.

## Alternatives Considered

Store snapshots only in canonical event payloads: preserves replay payloads, but
does not satisfy the database transaction step that inserts a risk input
snapshot before the risk decision.

Store snapshots in `risk_decisions.rule_results` or another existing JSONB
column: avoids a migration, but mixes input state with evaluation results and
makes snapshot lookup, hashing, and retention ambiguous.

Add a repository without an explicit table specification: unblocks code quickly,
but violates the database specification authority and risks an incompatible
schema that must be migrated later.

## Consequences

Risk decision persistence remains valid for the implemented subset, but complete
order creation transaction support remains incomplete until the snapshot table,
row model, repository, unit-of-work exposure, and migration tests are added.

Future M11 work that wires order creation persistence must include snapshot
persistence before the risk decision and before canonical event/outbox inserts.

The existing transactional risk event workflow remains acceptable because its
event payload contains the snapshot for replay and audit, while this ADR
clarifies that payload embedding is not a substitute for the first-class
snapshot record.

## Migration

No production snapshot data exists. A future migration should add the
`pmrp_risk.risk_input_snapshots` table after the current risk storage tables and
before any application service depends on full order creation transaction
semantics.

## Validation

Future validation should include:

- SQLAlchemy row-model metadata tests for the snapshot table
- Alembic migration tests for columns, numeric precision, indexes, and rollback
- repository round-trip tests for Decimal and UTC timestamp preservation
- risk unit-of-work tests proving snapshots are inserted before decisions
- service/workflow tests proving rollback when snapshot persistence fails
