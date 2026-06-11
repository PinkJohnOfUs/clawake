# clawake

The sewer system beneath the bowls on which the agents are sitting. Effectively the sandbox for the agents, designed to contain all waste and prevent the cat from shitting in your house.

`clawake` is a Python-first operations toolkit for managing one or more OpenClaw deployments running in rootless Podman containers through Quadlet and systemd user services.

Operational defaults:
- Safe by default (`dry-run` first, explicit `--execute` for mutations).
- Staff-driven configuration (`-c/--config` YAML file).

## CLI Setup (uv + make)

`pyproject.toml` already defines the console entry point `clawake = "clawake.cli:app"`.
That means the project knows how to expose a `clawake` command, but the command is only directly available after you run it through `uv` or install it into your user environment.

Preferred for contributors (repo-local and reproducible):

```bash
make install-dev
make validate
make render
make plan
```

This uses `uv run clawake ...` against the project environment and avoids global drift.

Optional user-level installation (global command on your machine):

```bash
make install-tool
clawake --help
```

Remove user-level installation:

```bash
make uninstall-tool
```

Useful overrides:

```bash
make validate CONFIG=examples/staff/product.yml
make render CONFIG=examples/staff/product.yml OUTPUT=.rendered
make plan CONFIG=examples/staff/product.yml OUTPUT=.rendered
```

## CLI Reference

### Portable staff paths

`examples/staff/product.yml` uses `${CLAWAKE_WORKSPACE_ROOT}` so paths stay portable across checkouts.

### Migration note: host runtime storage defaults

`clawake` treats `workspace_path` as mounted project input, while runtime config/state defaults live outside the workspace.

- `config_path` and `state_path` are optional.
- If omitted, they are derived automatically as:
	- `~/.local/share/clawake/instances/<instance-name>/config`
	- `~/.local/share/clawake/instances/<instance-name>/state`
- Override the root with `CLAWAKE_RUNTIME_ROOT` when needed.
- `make` targets in this repository set `CLAWAKE_RUNTIME_ROOT=$PWD/.clawake/instances` by default, so local runs keep runtime state in the project scope.
- Existing staff files that still define explicit `config_path`/`state_path` continue to work.

For local CLI usage, set it once per shell:

```bash
export CLAWAKE_WORKSPACE_ROOT="$PWD"
```

In VS Code launch configurations, set `CLAWAKE_WORKSPACE_ROOT` to `${workspaceFolder}`.
In CI, set `CLAWAKE_WORKSPACE_ROOT` to the repository workspace path.

### Validate and render

- `clawake validate --config|-c <staff.yaml>`
- `clawake render --config|-c <staff.yaml> [--output|-o <render-dir>]`
- `clawake plan --config|-c <staff.yaml> [--output|-o <render-dir>]`

### Deploy and reconcile

- `clawake deploy --config|-c <staff.yaml> --target <quadlet-dir> [--execute]`
- `clawake apply --config|-c <staff.yaml> --target <quadlet-dir> [--output|-o <render-dir>] [--execute]`

### Service operations

- `clawake restart <instance> [--execute]`
- `clawake status <instance> [--execute]`
- `clawake status-cluster --config|-c <staff.yaml> [--format text|json] [--execute]`
- `clawake logs <instance> [--lines <N>] [--execute]`
- `clawake auto-onboard --config|-c <staff.yaml> --instance|-i <name> [--execute]`
- `clawake teardown --config|-c <staff.yaml> [--instance|-i <name>] [--force-image] [--execute]`
- `clawake remove --config|-c <staff.yaml> [--instance|-i <name>] [--force-image] [--execute]` (alias for `teardown`)

### Backup and image lifecycle

- `clawake backup --config|-c <staff.yaml> --instance|-i <name> [--output|-o <backup-dir>] [--execute]`
- `clawake upgrade --config|-c <staff.yaml> --instance|-i <name> [--tag <tag>] [--digest <sha256:...>] [--execute]`
- `clawake rollback --config|-c <staff.yaml> --instance|-i <name> [--execute]`

### Parameter behavior

- `--execute`: required for commands that mutate host state/config.
- `--output/-o`: render or backup output directory (command-dependent).
- `--target`: target Quadlet directory for deployment/apply.
- `--format`: output format for `status-cluster` (`text` or `json`).
- `--lines`: journal line count for `logs` (default: `100`).

## Documentation

Please find general architecture, roadmap, and operational notes in `docs/`.

- Architecture: `docs/architecture.md`
- Roadmap: `docs/repo-roadmap.md`
- Upgrade runbook: `docs/upgrade-playbook.md`
- Project overview: `docs/project-overview.md`
