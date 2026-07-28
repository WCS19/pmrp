# Prediction Market Research Platform

PMRP is a Python 3.13 modular monolith for prediction-market research,
simulation, paper trading, shadow trading, and carefully gated live execution.

The project is governed by the documents in `docs/`. Architecture decisions are
recorded in `docs/adr/`.

## Local Setup

```bash
uv sync --locked --all-groups
uv run pytest
```

## Validation

```bash
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -m "unit or property"
uv run pytest --cov=src/pmrp --cov-branch --cov-report=term-missing
uv build
```
