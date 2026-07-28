.PHONY: sync format format-check lint typecheck test test-unit coverage build check

sync:
	uv sync --locked --all-groups

format:
	uv run ruff format .

format-check:
	uv run ruff format --check .

lint:
	uv run ruff check .

typecheck:
	uv run mypy src

test:
	uv run pytest

test-unit:
	uv run pytest -m "unit or property"

coverage:
	uv run pytest --cov=src/pmrp --cov-branch --cov-report=term-missing

build:
	uv build

check: format-check lint typecheck test build
