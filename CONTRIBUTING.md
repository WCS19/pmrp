# Contributing

PMRP is built in small, reviewable, validated changes. Read the governing
documents in `docs/` before changing architecture, schemas, database design,
API contracts, testing policy, or milestone scope.

## Development Setup

```bash
uv sync --locked --all-groups
uv run pre-commit install
```

## Local Validation

Run the smallest relevant checks before committing:

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -m "unit or property"
```

Before opening a pull request, run:

```bash
uv sync --locked --all-groups
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest --cov=src/pmrp --cov-branch --cov-report=term-missing
uv build
```

## Commit Discipline

Use focused commits with descriptive messages:

```text
<type>(<scope>): <imperative summary>
```

Examples:

```text
feat(schemas): add strict canonical base model
test(schemas): add numeric invariant property tests
```

Each commit should stage only related files, include relevant tests when
behavior changes, and leave the repository in a valid state.

## Branch Protection

The `main` branch should require pull requests and passing CI before merge.
Direct pushes to `main` should be reserved for explicitly approved repository
administration.

Recommended required checks:

- formatting
- linting
- type checking
- unit/property tests
- branch coverage
- package build

## Scope Control

Do not include live exchange credentials, production account data, raw
production payloads, local database files, generated build artifacts, or editor
caches in commits.

Strategies must not import concrete exchange adapters. Domain logic must not
depend on SQLAlchemy or wall-clock calls.
