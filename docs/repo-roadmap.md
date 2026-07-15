# Repository Roadmap

## Validated Baseline (from tests)

- CLI baseline coverage currently centers on `validate`, `apply` (dry-run/execute), and `status-cluster` (json) while lifecycle command migration is underway.
- Config: inventory loading plus port/path collision checks are covered.
- Rendering: Quadlet output includes expected image/labels/volumes.
- Systemd wrapper: unsafe instance names are rejected.
- Upgrade primitives: plan/apply/rollback behavior is covered.

All current tests pass (`14 passed`).

## Phase 1 (current)

- Declarative inventory and strict validation.
- Quadlet rendering and deployment basics.
- Systemd-user status/log inspection wrappers.
- Team-centric lifecycle command model (`setup-quadlets`, `restart-quadlets`, `teardown-quadlets`, `status-quadlets`).

## Phase 2

- Harden controlled `upgrade` / `rollback` flows.
- Add host-specific override composition.
- Add deployed-state snapshot tracking.

### Next Steps (Phase 2 Execution Plan)

1. Lifecycle command hardening
- Implement stable command contracts for `setup-quadlets`, `restart-quadlets`, `teardown-quadlets`, `status-quadlets`.
- Keep preview-first behavior where mutation is possible.
- Add role and selector targeting semantics (single member vs full team).
- DoD: happy-path + failure-path tests for each lifecycle command.

2. Host override composition
- Add optional host overlay files and deterministic merge order.
- Validate merged inventory with existing collision checks.
- Add `plan` output that shows which values came from host overrides.
- DoD: fixture-based tests for merge precedence and conflict errors.

3. Deployed-state snapshot tracking
- Persist a local state snapshot after successful mutation.
- Track rendered digest/checksum per instance plus applied timestamp.
- Add drift command/report comparing inventory intent vs deployed snapshot.
- DoD: tests for snapshot write/read, missing snapshot, and drift detection.

### Testing Focus For Upcoming Work

- Add negative tests for malformed YAML and missing required fields.
- Add systemd failure-path tests (`daemon-reload`/`restart` non-zero rc).
- Add multi-host prep tests where parsing is allowed but execution is gated.

## Phase 3

- FastAPI + server-rendered dashboard for non-developers.
- Read-only views first (inventory, health, version drift, pending changes).
- Carefully gated mutating actions with confirmations and audit trail.

## Phase 4

- Optional remote execution (SSH or agent).
- Multi-host orchestration primitives.
