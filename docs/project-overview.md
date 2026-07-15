# Project Overview

This document contains general project documentation that was previously in the repository root README.

## Concise architectural recommendation

- Keep staff files in git as source of truth (`staff/` + `examples/staff/`).
- Keep operational logic in `src/clawake/services/`; keep CLI thin and user-intent driven.
- Focus on team lifecycle operations over infrastructure verbs.
- Keep default workflows safe and predictable, with explicit mutation steps.
- Use simple local state first (filesystem, deterministic rendered artifacts), no DB in MVP.
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
├── examples/staff/
│   ├── team.yml
│   ├── env/
│   └── workspaces/
├── staff/
│   └── README.md
├── templates/quadlet/
│   └── openclaw.container.j2
├── src/clawake/
│   ├── __init__.py
│   ├── cli.py
│   ├── config.py
│   └── services/
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
- `examples/staff/`: declarative examples.
- `templates/`: Quadlet templates rendered from staff files.
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

Staff model highlights:
- Cluster root for single-host mode (`cluster.name`, `cluster.mode=single_host`, `cluster.primary_host`).
- Instance identity (`name`, `host`, `role`, `container_name`, `quadlet_path`).
- Two-path mount model (`workspace_path` + `team_definition_path`).
- Image source controls (`repository`, `tag`, `digest`, `known_good_digest`).
- Runtime details (`ports`, bind address, mounts, env files, labels).
- Operational policies (health expectations, update policy, guardrails).
- Dashboard metadata/friendly labels.

Examples:
- `examples/staff/team.yml`

Path convention:
- Use `${CLAWAKE_WORKSPACE_ROOT}` in staff files for repository-relative absolute paths.
- Set `CLAWAKE_WORKSPACE_ROOT` to checkout root (VS Code: `${workspaceFolder}`, CI: `${{ github.workspace }}`).

## Dashboard readiness notes

- Core behavior is in services and should stay UI-agnostic.
- CLI is orchestration over the service layer.
- Future dashboard routes should call the same services.
- `status-quadlets --format json` is the machine-readable status contract.

## Primary lifecycle interface

The preferred operator interface is a small, intent-first command set:

- `setup-quadlets`
- `restart-quadlets`
- `teardown-quadlets`
- `status-quadlets`

Other commands should align with the same mental model and avoid exposing runtime internals.

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

- [ ] Harden `setup-quadlets` reconciliation diagnostics for partial-failure reporting.
- [ ] Add policy checks for unsafe host path selections in staff inventory.
- [ ] Add preview diff summary for Quadlet changes before `--execute`.
- [ ] Add stricter guardrails for team-wide mutating operations.
- [ ] Add host-specific override merge behavior.
- [ ] Add preflight networking collision detection against live host state.
- [ ] Add explicit digest pinning policy checks.
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

Preferred lifecycle smoke flow:

```bash
make setup-quadlets
make setup-quadlets-exec
make status-quadlets
make teardown-quadlets
```