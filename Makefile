.PHONY: install install-dev test lint type-check format check bot pipeline clean help

VENV      := .venv
PYTHON    := $(VENV)/bin/python
PIP       := $(VENV)/bin/pip

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-15s\033[0m %s\n", $$1, $$2}'

$(VENV)/bin/activate:
	python3 -m venv $(VENV)

install: $(VENV)/bin/activate ## Install project dependencies
	$(PIP) install -e .

install-dev: $(VENV)/bin/activate ## Install project with dev dependencies
	$(PIP) install -e ".[dev]"

test: ## Run all tests
	$(PYTHON) -m pytest tests/ -v

test-cov: ## Run tests with coverage report
	$(PYTHON) -m pytest tests/ --cov=content_farm --cov-report=term-missing -v

lint: ## Run ruff linter
	$(PYTHON) -m ruff check src/ tests/

format: ## Auto-format code with ruff
	$(PYTHON) -m ruff format src/ tests/
	$(PYTHON) -m ruff check --fix src/ tests/

type-check: ## Run mypy type checking
	$(PYTHON) -m mypy src/

check: lint type-check test ## Run lint + type-check + tests

bot: ## Start Telegram bot
	$(PYTHON) scripts/run_bot.py

pipeline: ## Run pipeline (usage: make pipeline TOPIC="your topic")
	$(PYTHON) scripts/run_pipeline.py $(TOPIC)

clean: ## Remove build artifacts and caches
	rm -rf build/ dist/ *.egg-info src/*.egg-info .pytest_cache .mypy_cache .ruff_cache
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true

clean-all: clean ## Remove venv and all build artifacts
	rm -rf $(VENV)
