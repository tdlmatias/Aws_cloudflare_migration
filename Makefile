.DEFAULT_GOAL := help
SHELL := /bin/bash

TERRAFORM_DIR := terraform

.PHONY: help install format lint typecheck test security validate terraform-test export-fixture ci

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-16s\033[0m %s\n", $$1, $$2}'

install: ## Install the package with dev dependencies
	python -m pip install --upgrade pip
	pip install -e ".[dev]"

format: ## Auto-format Python and Terraform
	ruff format .
	ruff check --fix .
	terraform -chdir=$(TERRAFORM_DIR) fmt -recursive

lint: ## Lint Python, shell and Terraform formatting
	ruff check .
	ruff format --check .
	@if command -v shellcheck >/dev/null 2>&1; then \
		shellcheck scripts/*.sh; \
	else \
		echo "shellcheck not installed; skipping shell lint"; \
	fi
	@if command -v terraform >/dev/null 2>&1; then \
		terraform -chdir=$(TERRAFORM_DIR) fmt -check -recursive; \
	else \
		echo "terraform not installed; skipping terraform fmt check"; \
	fi

typecheck: ## Run mypy
	mypy migration

test: ## Run Python tests with coverage
	pytest --cov=migration --cov-report=term-missing --cov-fail-under=85

security: ## Run security scanners (best effort; tools must be installed)
	@command -v gitleaks >/dev/null 2>&1 && gitleaks detect --no-banner || echo "gitleaks not installed; skipping"
	@command -v checkov  >/dev/null 2>&1 && checkov -d $(TERRAFORM_DIR) --quiet --compact || echo "checkov not installed; skipping"

validate: ## Validate generated zones.json against the schema
	python -m migration validate $(TERRAFORM_DIR)/data/zones.json --schema zones

terraform-test: ## Terraform fmt, validate and native tests (needs provider registry)
	@if command -v terraform >/dev/null 2>&1; then \
		terraform -chdir=$(TERRAFORM_DIR) fmt -check -recursive; \
		terraform -chdir=$(TERRAFORM_DIR) init -backend=false -input=false; \
		terraform -chdir=$(TERRAFORM_DIR) validate; \
		terraform -chdir=$(TERRAFORM_DIR) test; \
	else \
		echo "terraform not installed; skipping terraform validation and tests"; \
	fi

export-fixture: ## Convert the bundled test fixture into zones.json (no AWS needed)
	python -m migration convert \
		--zones tests/fixtures/hosted-zones.json \
		--records-dir tests/fixtures \
		--output /tmp/zones.json \
		--review-output /tmp/manual-review.json
	@echo "Wrote /tmp/zones.json and /tmp/manual-review.json"

diagram: ## Render Mermaid diagrams to SVG (needs @mermaid-js/mermaid-cli)
	@command -v mmdc >/dev/null 2>&1 || { echo "mmdc not installed: npm i -g @mermaid-js/mermaid-cli"; exit 1; }
	mmdc -i docs/diagrams/system-architecture.mmd -o docs/diagrams/system-architecture.svg
	mmdc -i docs/diagrams/migration-sequence.mmd -o docs/diagrams/migration-sequence.svg

ci: lint typecheck test validate ## Run the full local quality gate
