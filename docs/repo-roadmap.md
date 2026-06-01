# Repository Roadmap

## Phase 1 (current)

- Declarative inventory and strict validation.
- Quadlet rendering and plan/deploy basics.
- Systemd-user status/log inspection wrappers.
- Backup primitive for mounted paths.

## Phase 2

- Controlled `upgrade` / `rollback` CLI commands.
- Host-specific override composition.
- Deployed-state snapshot tracking.

## Phase 3

- FastAPI + server-rendered dashboard for non-developers.
- Read-only views first (inventory, health, version drift, pending changes).
- Carefully gated mutating actions with confirmations and audit trail.

## Phase 4

- Optional remote execution (SSH or agent).
- Multi-host orchestration primitives.
