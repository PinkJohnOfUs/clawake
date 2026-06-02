# Project Overview

This document contains general project documentation that was previously in the repository root README.

## Concise architectural recommendation

- Keep inventory files in git as source of truth (`inventory/` + `examples/inventory/`).
- Keep operational logic in `src/clawake/services/`; keep CLI thin.
- Default workflows to safe preview/dry-run.
- Require explicit `--execute` for mutation (`deploy`/`apply`/`restart`/`upgrade`/`rollback`).
- Use simple local state first (files + tar backups), no DB in MVP.
- Reuse services for a future FastAPI dashboard layer.

## Proposed repository tree

```text
.
├── .github/workflows/ci.yml
├── docs/
│   ├── architecture.md
│   ├── project-overview.md
│   ├── repo-roadmap.md
│   └── upgrade-playbook.md
├── examples/inventory/
│   ├── dev.yaml
│   └── prod.yaml
├── inventory/
│   └── README.md
├── templates/quadlet/
│   └── openclaw.container.j2
├── src/clawake/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   └── services/
│       ├── backup.py
│       ├── render.py
│       ├── systemd.py
│       └── upgrade.py
├── tests/
│   ├── test_cli.py
│   ├── test_config.py
│   ├── test_render.py
│   ├── test_systemd.py
│   ├── test_upgrade.py
│   └── test_uv_setup.py
├── pyproject.toml
├── LICENSE
└── README.md
```

Why these top-level parts exist:
- `docs/`: operator-facing architecture and runbooks.
- `src/`: installable application code.
- `tests/`: focused unit/CLI tests.
- `examples/inventory/`: declarative examples.
- `templates/`: Quadlet templates rendered from inventory.
- `.github/workflows/`: CI checks for lint/test/render validation.

## Recommended Python stack

- CLI: Typer.
- Config/schema validation: Pydantic v2 + YAML loading.
- Templating: Jinja2 for Quadlet generation.
- Testing: pytest.
- Lint/format: ruff.
- Logging: stdlib logging.
- Packaging/deps: `pyproject.toml` + setuptools.
- Dashboard path: FastAPI + server-rendered templates.

## Initial config/domain model

Inventory model highlights:
- Cluster root for single-host mode (`cluster.name`, `cluster.mode=single_host`, `cluster.primary_host`).
- Instance identity (`name`, `host`, `role`, `profile`, `container_name`, `quadlet_path`).
- Explicit per-instance storage paths (`workspace_path`, `config_path`, `state_path`).
- Image source controls (`repository`, `tag`, `digest`, `known_good_digest`).
- Runtime details (`ports`, bind address, mounts, env files, labels).
- Operational policies (health expectations, update policy, backup policy).
- Dashboard metadata/friendly labels.

Examples:
- `examples/inventory/dev.yaml`
- `examples/inventory/prod.yaml`

## Dashboard readiness notes

- Core behavior is in services and should stay UI-agnostic.
- CLI is orchestration over the service layer.
- Future dashboard routes should call the same services.
- `status-cluster --format json` is the machine-readable status contract.

Suggested MVP dashboard capabilities:
- List instances and friendly labels.
- Health/status summary.
- Current vs target image details.
- Pending rendered changes.
- Confirmed, safe workflow triggers.
- Human-readable warnings/errors.

## Open questions

- Single inventory file vs split per-host/per-instance sources?
- Local-only execution first vs early remote-over-SSH path?
- Secrets model (`.env`, sops, external secret manager)?
- How should known-good/deployed state be tracked over time?
- Should dashboard actions run locally, remotely over SSH, or via on-host agent?
- At what scale does introducing a database become justified?

## Next milestone tasks

- [ ] Harden `upgrade` and `rollback` command flows.
- [ ] Add host-specific override merge behavior.
- [ ] Add preflight networking collision detection against live host state.
- [ ] Add explicit digest pinning policy checks.
- [ ] Add backup retention cleanup workflow.
- [ ] Add deployment state snapshot file format.
- [ ] Add structured JSON output mode for CLI.
- [ ] Add FastAPI read-only dashboard prototype.
- [ ] Add role-based controls for mutating actions.
- [ ] Add remote SSH execution adapter.

## Development

This repository uses `uv` for dependency management and local tooling.

```bash
uv sync --dev
uv run ruff check .
uv run ruff format --check .
uv run pytest -q
```