# clawake

The sewer system beneath the bowls on which the agents are sitting.

`clawake` is a Python-first operations toolkit for managing one or more OpenClaw deployments running in rootless Podman containers through Quadlet and systemd user services.

## 1) Concise architectural recommendation

- Keep **inventory files** in git as the source of truth (`inventory/` + `examples/inventory/`).
- Put all operational logic in `src/clawake/services/`; keep CLI thin.
- Default every workflow to **safe preview/dry-run**.
- Require explicit `--execute` for mutation (deploy/restart/upgrade/rollback).
- Keep a simple local-state approach first (files + tar backups), no DB yet.
- Prepare dashboard by reusing the same services behind a future FastAPI web layer.

## 2) Proposed repository tree

```text
.
├── .github/workflows/ci.yml
├── docs/
│   ├── architecture.md
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
│       └── systemd.py
├── tests/
│   ├── test_cli.py
│   ├── test_config.py
│   └── test_render.py
├── pyproject.toml
├── LICENSE
└── README.md
```

Why these top-level parts exist:
- `docs/`: operator-facing architecture and runbooks.
- `src/`: installable application code.
- `tests/`: focused unit/CLI tests.
- `examples/inventory/`: practical declarative examples.
- `templates/`: Quadlet templates rendered from inventory.
- `.github/workflows/`: CI checks for lint/test/render validation.

## 3) Recommended Python stack

- CLI: **Typer** (clear subcommands, good UX).
- Config/schema validation: **Pydantic v2** + YAML loading.
- Templating: **Jinja2** for Quadlet generation.
- Testing: **pytest**.
- Lint/format: **ruff**.
- Logging: stdlib **logging**.
- Packaging/deps: **pyproject.toml** with setuptools.
- Dashboard-later path: **FastAPI + server-rendered Jinja templates** (not SPA-first).

## 4) MVP CLI/workflow design

Implemented CLI commands (safe by default):

- `clawake validate -c <inventory.yaml>`
- `clawake render -c <inventory.yaml> -o <render-dir>`
- `clawake plan -c <inventory.yaml> -o <render-dir>` (preview/diff)
- `clawake apply -c <inventory.yaml> --target <quadlet-dir> [--output <render-dir>] [--execute]`
- `clawake deploy -c <inventory.yaml> --target <quadlet-dir> [--execute]`
- `clawake restart <instance> [--execute]`
- `clawake status <instance> [--execute]`
- `clawake status-cluster -c <inventory.yaml> [--format text|json] [--execute]`
- `clawake logs <instance> [--lines N] [--execute]`
- `clawake backup -c <inventory.yaml> -i <instance> -o <backup-dir> [--execute]`
- `clawake upgrade -c <inventory.yaml> -i <instance> [--tag X] [--digest Y] [--execute]`
- `clawake rollback -c <inventory.yaml> -i <instance> [--execute]`

Commands that mutate host state are dry-run unless `--execute` is set.

## 5) Initial config/domain model

Inventory models include:
- cluster root for single-host mode (`cluster.name`, `cluster.mode=single_host`, `cluster.primary_host`)
- instance name, host name, role, profile, service scope, quadlet path, container name
- explicit per-instance `workspace_path`, `config_path`, `state_path`
- image repository/tag/digest and known-good digest
- ports/bind address, mounts, env files, labels
- public URL, health expectations
- update policy, backup policy
- dashboard metadata/friendly labels

See examples:
- `examples/inventory/dev.yaml`
- `examples/inventory/prod.yaml`

## 6) Dashboard-readiness design

- Core behavior lives in `services/*` and is UI-agnostic.
- CLI orchestrates service calls only.
- Future dashboard can call same services from FastAPI routes.
- `status-cluster --format json` provides a machine-readable status snapshot contract.
- Suggested MVP dashboard features for non-developers:
  - list instances and friendly labels
  - health + status summary
  - current vs target image info
  - pending rendered changes
  - safe workflow triggers with confirmation prompts
  - human-readable warnings/errors

## 7) Key bootstrap files included

This scaffold includes:
- README + docs runbooks
- installable Python package + starter CLI
- domain/config models + rendering/systemd/backup/upgrade services
- example inventory + Quadlet template
- tests and CI workflow

License recommendation: **MIT** (already included in `LICENSE`) because this is an operations tool likely to benefit from broad reuse with low legal friction.

## 8) Open questions

- Should source-of-truth remain a single YAML inventory or split per-host/per-instance files?
- Local-only execution first, or early remote-over-SSH support?
- Secrets model (`.env` files, sops, external secret manager)?
- How should deployed state/known-good snapshots be tracked over time?
- Should dashboard actions run locally, remotely over SSH, or through an on-host agent?
- At what scale does adding a database become justified?

## Next 10 tasks

- [ ] Add `upgrade` and `rollback` command implementations.
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
