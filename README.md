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
make doctor
make setup-quadlets
make status-quadlets
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
make setup-quadlets CONFIG=examples/staff/team.yml
make setup-quadlets MEMBER=product-owner
make status-quadlets-json CONFIG=examples/staff/team.yml
```

## New Workflow (Phase 1 MVP)

The current lifecycle is team/member oriented and built around Quadlet reconciliation.

1. Prepare environment and dependencies:

	```bash
	export CLAWAKE_WORKSPACE_ROOT="$PWD"
	make install-dev
	```

2. Preview changes (safe dry-run):

	```bash
	make setup-quadlets CONFIG=examples/staff/team.yml
	```

3. Apply changes (mutating):

	```bash
	make setup-quadlets-exec CONFIG=examples/staff/team.yml
	```

4. Check runtime health:

	```bash
	make status-quadlets CONFIG=examples/staff/team.yml
	```

5. Restart after config/image updates (optional):

	```bash
	make restart-quadlets-exec CONFIG=examples/staff/team.yml
	```

6. Teardown when needed:

	```bash
	make teardown-quadlets-exec CONFIG=examples/staff/team.yml
	```

## CLI Reference

### Portable staff paths

`examples/staff/team.yml` uses `${CLAWAKE_WORKSPACE_ROOT}` so paths stay portable across checkouts.

### Simplified mount model

`clawake` uses exactly two host paths per instance:

- `workspace_path`: mounted at `/workspace` for runtime work.
- `team_definition_path`: mounted read-only at `/team-definition`.

For local CLI usage, set it once per shell:

```bash
export CLAWAKE_WORKSPACE_ROOT="$PWD"
```

In VS Code launch configurations, set `CLAWAKE_WORKSPACE_ROOT` to `${workspaceFolder}`.
In CI, set `CLAWAKE_WORKSPACE_ROOT` to the repository workspace path.

### Lifecycle commands

- `clawake setup-quadlets --config|-c <staff.yaml> [--member|-m <name>] [--execute]`
- `clawake restart-quadlets --config|-c <staff.yaml> [--member|-m <name>] [--execute]`
- `clawake status-quadlets --config|-c <staff.yaml> [--member|-m <name>] [--format text|json]`
- `clawake teardown-quadlets --config|-c <staff.yaml> [--member|-m <name>] [--execute]`

### Makefile shortcuts

- `make setup-quadlets`
- `make setup-quadlets-exec`
- `make restart-quadlets`
- `make restart-quadlets-exec`
- `make status-quadlets`
- `make status-quadlets-json`
- `make teardown-quadlets`
- `make teardown-quadlets-exec`
- `make test-lifecycle`

### Parameter behavior

- `--execute`: required for commands that mutate host state/config.
- `--config/-c`: team inventory file (for example `examples/staff/team.yml`).
- `--member/-m`: scope operation to one member instead of the whole team.
- `--format`: output format for `status-quadlets` (`text` or `json`).

## Documentation

Please find general architecture, roadmap, and operational notes in `docs/`.

- Architecture: `docs/architecture.md`
- Roadmap: `docs/repo-roadmap.md`
- Upgrade runbook: `docs/upgrade-playbook.md`
- Project overview: `docs/project-overview.md`
