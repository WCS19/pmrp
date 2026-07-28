## Summary

What does this change do?

## Motivation

Why is it needed?

## Architecture

Which components and interfaces are affected?

## Risk and Safety

Does this affect execution, risk, accounting, secrets, or live trading?

## Data and Migration

Are schemas, migrations, fixtures, or backfills involved?

## Replay and Determinism

Does expected replay output change?

## Testing

What tests were added or run?

## Operations

Are metrics, logs, alerts, runbooks, or deployment steps required?

## Checklist

- [ ] Scope is clear and focused.
- [ ] Architecture boundaries are respected.
- [ ] Financial values use Decimal where required.
- [ ] Time uses approved clock or schema validation paths.
- [ ] External input is validated.
- [ ] Tests cover normal and failure paths.
- [ ] Replay determinism impact is reviewed.
- [ ] Database migration impact is reviewed.
- [ ] Security and secret handling are reviewed.
- [ ] Documentation is updated.
- [ ] CI passes.
- [ ] Live-trading safety is unchanged or explicitly reviewed.
