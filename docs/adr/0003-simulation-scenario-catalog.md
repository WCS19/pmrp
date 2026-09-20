# ADR-0003: Simulation Scenario Catalog Numbering

- Status: Proposed
- Date: 2026-09-20
- Owners: PMRP maintainers
- Related issues: None

## Context

`docs/04_IMPLEMENTATION.md` defines the M10 scenario catalog as `SIM-001` through
`SIM-015`, with fee and settlement cases grouped into single entries:

- `SIM-011 fee calculation`
- `SIM-012 settlement payout`
- `SIM-013 disconnect while order open`
- `SIM-014 duplicate market event`
- `SIM-015 multi-leg imbalance`

`docs/07_TESTING.md` defines a more granular catalog as `SIM-001` through
`SIM-018`, splitting fees and settlement into distinct required cases:

- `SIM-011 maker fee`
- `SIM-012 taker fee`
- `SIM-013 rebate`
- `SIM-014 settlement win`
- `SIM-015 settlement loss`
- `SIM-016 disconnect with open order`
- `SIM-017 duplicate market event`
- `SIM-018 multi-leg imbalance`

The implementation impact is concrete: deterministic scenario fixtures, test
names, expected artifacts, and future scenario catalogs need stable IDs. If both
numbering schemes are used, the same scenario ID can refer to different behavior.

## Decision

Use the `docs/07_TESTING.md` catalog as the canonical scenario ID assignment for
deterministic simulation tests and future scenario catalog fixtures.

Treat the M10 list in `docs/04_IMPLEMENTATION.md` as milestone work
decomposition. Its grouped fee and settlement entries map to the more granular
testing catalog:

- `fee calculation` maps to `SIM-011`, `SIM-012`, and `SIM-013`
- `settlement payout` maps to `SIM-014` and `SIM-015`
- `disconnect while order open` maps to `SIM-016`
- `duplicate market event` maps to `SIM-017`
- `multi-leg imbalance` maps to `SIM-018`

## Alternatives Considered

Use the `docs/04_IMPLEMENTATION.md` numbering: keeps the implementation milestone
list compact, but conflicts with the higher-authority testing requirements and
collapses materially different fee and settlement behaviors into ambiguous IDs.

Maintain both numbering schemes: preserves both documents verbatim, but makes
scenario IDs unreliable for regression tests, result artifacts, and operator
debugging.

Renumber `docs/07_TESTING.md` to match `docs/04_IMPLEMENTATION.md`: removes the
extra scenarios that the testing standard explicitly requires and weakens the
coverage matrix for fees and settlement.

## Consequences

Scenario IDs are stable across deterministic simulation tests and future scenario
fixtures. Tests that already exercise taker fees and settlement wins should use
the corresponding `docs/07_TESTING.md` IDs.

Future M10 work should add missing catalog coverage under the canonical IDs
rather than reusing the grouped M10 implementation IDs.

## Migration

No persisted simulation catalog exists yet. Existing unit tests can be relabeled
without data migration.

## Validation

Simulation scenario tests verify deterministic behavior under the canonical
catalog IDs for the covered cases.
