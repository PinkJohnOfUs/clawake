UV ?= uv
CONFIG ?= examples/staff/team.yml
MEMBER ?=
CLAWAKE_WORKSPACE_ROOT ?= $(CURDIR)
CLAWAKE_RUNTIME_ROOT ?= $(CURDIR)/.clawake/instances

export CLAWAKE_WORKSPACE_ROOT
export CLAWAKE_RUNTIME_ROOT

CLAWAKE_RUN = $(UV) run clawake

.PHONY: uv-sync install-dev install-tool uninstall-tool doctor \
	setup-quadlets setup-quadlets-exec restart-quadlets restart-quadlets-exec \
	teardown-quadlets teardown-quadlets-exec status-quadlets status-quadlets-json \
	test-lifecycle test lint fmt

uv-sync: ## Install project dependencies into .venv via uv
	$(UV) sync

install-dev: uv-sync ## Repo-local setup (preferred: use uv run for CLI)

install-tool: ## Install clawake as user-level CLI via uv tool
	$(UV) tool install --from . clawake --force

uninstall-tool: ## Remove user-level clawake CLI installed by uv tool
	$(UV) tool uninstall clawake

doctor: ## Show clawake --help through uv run
	$(CLAWAKE_RUN) --help

setup-quadlets: ## Dry-run setup-quadlets (use MEMBER=<name> to scope)
	$(CLAWAKE_RUN) setup-quadlets -c $(CONFIG) $(if $(MEMBER),--member $(MEMBER),)

setup-quadlets-exec: ## Execute setup-quadlets (use MEMBER=<name> to scope)
	$(CLAWAKE_RUN) setup-quadlets -c $(CONFIG) $(if $(MEMBER),--member $(MEMBER),) --execute

restart-quadlets: ## Dry-run restart-quadlets (use MEMBER=<name> to scope)
	$(CLAWAKE_RUN) restart-quadlets -c $(CONFIG) $(if $(MEMBER),--member $(MEMBER),)

restart-quadlets-exec: ## Execute restart-quadlets (use MEMBER=<name> to scope)
	$(CLAWAKE_RUN) restart-quadlets -c $(CONFIG) $(if $(MEMBER),--member $(MEMBER),) --execute

teardown-quadlets: ## Dry-run teardown-quadlets (use MEMBER=<name> to scope)
	$(CLAWAKE_RUN) teardown-quadlets -c $(CONFIG) $(if $(MEMBER),--member $(MEMBER),)

teardown-quadlets-exec: ## Execute teardown-quadlets (use MEMBER=<name> to scope)
	$(CLAWAKE_RUN) teardown-quadlets -c $(CONFIG) $(if $(MEMBER),--member $(MEMBER),) --execute

status-quadlets: ## Check status-quadlets in text format
	$(CLAWAKE_RUN) status-quadlets -c $(CONFIG) $(if $(MEMBER),--member $(MEMBER),) --format text

status-quadlets-json: ## Check status-quadlets in json format
	$(CLAWAKE_RUN) status-quadlets -c $(CONFIG) $(if $(MEMBER),--member $(MEMBER),) --format json

test-lifecycle: ## Run architecture lifecycle flow (setup/restart/status/teardown); status is best-effort
	$(MAKE) setup-quadlets CONFIG=$(CONFIG) MEMBER=$(MEMBER)
	$(MAKE) restart-quadlets CONFIG=$(CONFIG) MEMBER=$(MEMBER)
	-$(MAKE) status-quadlets CONFIG=$(CONFIG) MEMBER=$(MEMBER)
	$(MAKE) teardown-quadlets CONFIG=$(CONFIG) MEMBER=$(MEMBER)

test: ## Run pytest
	$(UV) run pytest

lint: ## Run ruff check
	$(UV) run ruff check src tests

fmt: ## Run ruff format
	$(UV) run ruff format src tests
