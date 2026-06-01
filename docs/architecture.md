# Architecture

## Goals

- Safe, predictable OpenClaw operations.
- Declarative configuration and deterministic rendering.
- Shared backend logic for both CLI and future dashboard.

## Layers

1. **Domain/config (`clawake.config`)**
   - Pydantic models for hosts/instances/policies.
   - Validation of references and port collisions.
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
- Explicit tag vs digest handling.
- Rootless/systemd-user assumptions are first-class.
- Human-readable errors for non-specialists.
