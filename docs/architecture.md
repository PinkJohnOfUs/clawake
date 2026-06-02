# Architecture

## Goals

- Safe, predictable OpenClaw operations.
- Declarative configuration and deterministic rendering.
- Shared backend logic for both CLI and future dashboard.

## Layers

1. **Domain/config (`clawake.config`)**
   - Pydantic models for cluster/hosts/instances/policies.
   - Single-host-first cluster mode (`single_host`) for MVP.
   - Explicit instance role (`product_owner|developer`) vs profile (`public|internal`).
   - Validation of host references, port collisions, and storage boundary collisions.
2. **Services (`clawake.services`)**
   - Render Quadlet files.
   - Deploy/plan workflow support.
   - Backup and systemd interaction wrappers.
3. **Interfaces**
   - CLI today (`clawake.cli`).
   - Dashboard API later (FastAPI) reusing same services.

## Operational safety principles

- Preview before mutation.
- Backup before risky operations.
- Every instance has dedicated workspace/config/state paths and backup scope.
- Explicit tag vs digest handling.
- Rootless/systemd-user assumptions are first-class.
- Human-readable errors for non-specialists.

## Current MVP workflows

- `clawake apply` provides validate → render → deploy with dry-run by default.
- `clawake apply --execute` mutates state, performs pre-mutation backups, then systemd daemon-reload + restarts changed services.
- `clawake status-cluster` aggregates per-instance status; `--format json` returns a dashboard-ready machine-readable snapshot.
