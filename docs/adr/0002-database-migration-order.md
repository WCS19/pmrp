# ADR-0002: Initial Database Migration Order

- Status: Proposed
- Date: 2026-07-29
- Owners: PMRP maintainers
- Related issues: None

## Context

`docs/06_DATABASE.md` defines the initial migration order as:

- `0001 create logical schemas`
- `0002 create schema registry`

`docs/04_IMPLEMENTATION.md` later lists the M3 migration sequence starting with
`0001_create_schema_registry`. The documents therefore disagree on whether the
logical PostgreSQL schemas or the `pmrp_core.schema_registry` table should be the
first durable migration.

The implementation impact is concrete: the schema registry table must be created
inside `pmrp_core`, so creating the table before the logical schemas either
requires an implicit schema creation step in the table migration or fails on an
empty database.

## Decision

Follow the higher-authority database specification:

- `0001_create_logical_schemas`
- `0002_create_schema_registry`

Table migrations must assume their containing logical schema was created by an
earlier logical-schema migration unless a later ADR revises the migration order.

## Alternatives Considered

Create `pmrp_core` inside `0001_create_schema_registry`: couples one table
migration to global database layout and leaves the other logical schemas without
an authoritative creation point.

Renumber the logical-schema migration after the schema registry migration:
conflicts with `docs/06_DATABASE.md` and makes empty-database bootstrap order
less explicit.

## Consequences

Database bootstrap is deterministic on empty PostgreSQL databases. The Alembic
history starts with environment-wide logical schema setup, then creates durable
tables in dependency order.

`docs/04_IMPLEMENTATION.md` remains a work-decomposition guide, but its M3
migration numbering is superseded by this ADR and `docs/06_DATABASE.md`.

## Migration

No persisted production data exists. The committed Alembic history uses the
selected order from the first database migration.

## Validation

Database migration tests upgrade from `base` to `head`, verify the Alembic head,
check the logical schemas and schema registry table, downgrade to `base`, and
re-upgrade to `head`.
