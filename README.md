# clawake

The sewer system beneath the bowls on which the agents are sitting. Effectively the sandbox for the agents, designed to contain all waste and prevent the cat from shitting in your house.

`clawake` is a Python-first operations toolkit for managing one or more OpenClaw deployments running in rootless Podman containers through Quadlet and systemd user services.

Operational defaults:
- Safe by default (`dry-run` first, explicit `--execute` for mutations).
- Staff-driven configuration (`-c/--config` YAML file).

## CLI Reference

### Portable staff paths

`examples/staff/product.yml` uses `${CLAWAKE_WORKSPACE_ROOT}` so paths stay portable across checkouts.

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
