UV ?= uv
CONFIG ?= examples/staff/product.yml
OUTPUT ?= .rendered
TARGET ?= $(HOME)/.config/containers/systemd
INSTANCE ?= excalibot-product-owner
CLAWAKE_WORKSPACE_ROOT ?= $(CURDIR)
CLAWAKE_RUNTIME_ROOT ?= $(CURDIR)/.clawake/instances

export CLAWAKE_WORKSPACE_ROOT
export CLAWAKE_RUNTIME_ROOT

CLAWAKE_RUN = $(UV) run clawake

.PHONY: uv-sync install-dev install-tool uninstall-tool doctor \
	validate render plan deploy deploy-exec apply apply-exec auto-onboard auto-onboard-exec \
	status-cluster teardown-example teardown-example-exec test lint fmt

uv-sync: ## Install project dependencies into .venv via uv
	$(UV) sync

install-dev: uv-sync ## Repo-local setup (preferred: use uv run for CLI)

install-tool: ## Install clawake as user-level CLI via uv tool
	$(UV) tool install --from . clawake --force

uninstall-tool: ## Remove user-level clawake CLI installed by uv tool
	$(UV) tool uninstall clawake

doctor: ## Show clawake --help through uv run
	$(CLAWAKE_RUN) --help

validate: ## Run clawake validate with CONFIG
	$(CLAWAKE_RUN) validate -c $(CONFIG)

render: ## Run clawake render with CONFIG/OUTPUT
	$(CLAWAKE_RUN) render -c $(CONFIG) -o $(OUTPUT)

plan: ## Run clawake plan with CONFIG/OUTPUT
	$(CLAWAKE_RUN) plan -c $(CONFIG) -o $(OUTPUT)

deploy: ## Dry-run deploy to TARGET
	$(CLAWAKE_RUN) deploy -c $(CONFIG) --target $(TARGET)

deploy-exec: ## Execute deploy to TARGET
	$(CLAWAKE_RUN) deploy -c $(CONFIG) --target $(TARGET) --execute

apply: ## Dry-run apply to TARGET
	$(CLAWAKE_RUN) apply -c $(CONFIG) --target $(TARGET) -o $(OUTPUT)

apply-exec: ## Execute apply to TARGET
	$(CLAWAKE_RUN) apply -c $(CONFIG) --target $(TARGET) -o $(OUTPUT) --execute

auto-onboard: ## Dry-run auto-onboard plan for INSTANCE
	$(CLAWAKE_RUN) auto-onboard -c $(CONFIG) -i $(INSTANCE)

auto-onboard-exec: ## Execute auto-onboard for INSTANCE
	$(CLAWAKE_RUN) auto-onboard -c $(CONFIG) -i $(INSTANCE) --execute

status-cluster: ## Check status-cluster in text format
	$(CLAWAKE_RUN) status-cluster -c $(CONFIG) --format text --execute

teardown-example: ## Dry-run teardown for examples/staff/product.yml
	$(CLAWAKE_RUN) teardown -c examples/staff/product.yml

teardown-example-exec: ## Execute teardown for examples/staff/product.yml (all instances)
	$(CLAWAKE_RUN) teardown -c examples/staff/product.yml --execute

test: ## Run pytest
	$(UV) run pytest

lint: ## Run ruff check
	$(UV) run ruff check src tests

fmt: ## Run ruff format
	$(UV) run ruff format src tests
