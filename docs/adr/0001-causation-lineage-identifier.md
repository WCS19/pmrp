# ADR-0001: Causation Lineage Identifier Semantics

- Status: Proposed
- Date: 2026-07-28
- Owners: PMRP maintainers
- Related issues: None

## Context

`docs/03_SCHEMAS.md` defines a typed `CausationId` with the `cause_` prefix in
the identifier catalog. The same document's event-envelope example uses an
`evt_...` value in the `causation_id` field, implying that causation may point
directly to the event that caused the current event.

The implementation impact is that envelope schemas need a precise type for
`causation_id`. Choosing only `cause_` rejects the example payload. Choosing
only `evt_` makes the explicit `CausationId` identifier unused and prevents
commands from recording command-to-command causation.

## Decision

Model causation as a typed lineage reference that accepts:

- `EventId`
- `CommandId`
- `CausationId`

The field remains optional because root events and commands can begin a new
causal chain.

## Alternatives Considered

Use only `CausationId`: rejects documented event examples and obscures direct
event references.

Use only `EventId`: prevents command lineage and ignores the documented
`CausationId` prefix.

Leave `causation_id` as plain `str`: loses validation and makes correlation
lineage weaker than the rest of the canonical identifier model.

## Consequences

Envelope validation remains strict while preserving compatibility with both
documented interpretations.

Consumers must treat `causation_id` as an opaque lineage reference and inspect
its prefix only when resolving the referenced record.

## Migration

No migration is required before persisted data exists.

## Validation

Envelope tests verify acceptance of event, command, and explicit causation
references and rejection of unsupported prefixes.
