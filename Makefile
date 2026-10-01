# Common tasks. Variables from a local .env (see .env.example) are exported to every command.
-include .env
export

PYTHON ?= python3
VENV   ?= .venv
BIN     = $(VENV)/bin

.PHONY: help install test lint check site serve status clean

help:  ## List targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-10s %s\n", $$1, $$2}'

install:  ## Create .venv and install the package with dev + figures extras
	$(PYTHON) -m venv $(VENV)
	$(BIN)/pip install -q --upgrade pip
	$(BIN)/pip install -q -e ".[dev,figures]"

test:  ## Run the test suite (offline, ~30 s)
	$(BIN)/pytest

lint:  ## Lint with ruff
	$(BIN)/ruff check .

check: lint test  ## Lint + tests (what CI runs)

site:  ## Regenerate site/data.js from the committed results
	$(BIN)/ofi site

serve: site  ## Serve the results explorer on http://localhost:8000
	$(BIN)/python -m http.server 8000 --directory site

status:  ## Show configuration and pipeline progress
	$(BIN)/ofi status

clean:  ## Remove caches and build artifacts (keeps data/)
	rm -rf .pytest_cache .ruff_cache build *.egg-info src/*.egg-info
	find . -name __pycache__ -type d -prune -not -path './$(VENV)/*' -exec rm -rf {} +
