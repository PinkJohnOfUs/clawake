# Architecture

## Goals

### User Experience

- Enable users to create and manage complete OpenClaw teams within minutes.
- Provide an intuitive CLI focused on user intent rather than infrastructure details.
- Hide the complexity of Quadlet deployment and lifecycle management.
- Offer sensible defaults while allowing customization where it matters.
- Reduce the learning curve for new OpenClaw users.

### Team-Centric Management

- Treat teams as the primary abstraction instead of individual OpenClaw instances.
- Define an entire team in a single staff inventory file (for example `examples/staff/team.yml`).
- Allow team members to be onboarded, modified, or removed through simple commands.
- Support common team operations such as:
  - onboarding team members
  - conducting job interviews
  - firing team members
  - evolving team structures over time

### Declarative Configuration

- Manage the complete desired state through a single declarative configuration file.
- Ensure deterministic rendering and reconciliation from configuration to runtime.
- Make team definitions portable and version controllable.
- Enable configuration review through standard Git workflows.

### Infrastructure Abstraction

- Manage OpenClaw instances as systemd Quadlets.
- Automatically generate and maintain Quadlet definitions.
- Shield users from container runtime and systemd implementation details.
- Keep OpenClaw runtime configuration ownership inside OpenClaw itself.

### Instance Lifecycle Management

Provide simple lifecycle commands for OpenClaw deployments:

- `setup-quadlets`
- `restart-quadlets`
- `teardown-quadlets`
- `status-quadlets`

Additional lifecycle operations should remain consistent with the same user-focused approach.

### Safety and Predictability

- Ensure safe and predictable OpenClaw operations.
- Make deployments reproducible and deterministic.
- Minimize manual configuration errors.
- Provide clear feedback about the current system state.

### Extensibility

- Keep business logic independent from the CLI implementation.
- Allow future integration with a web dashboard.
- Enable additional deployment targets without changing the user-facing workflow.
- Support future OpenClaw features without requiring users to understand internal implementation details.

## Vision

The tool should be the easiest way to build, deploy, and manage OpenClaw teams.

Users describe their desired team in a single staff inventory file and interact with it through a small set of intuitive commands. The tool handles systemd Quadlets, container lifecycle management, and operational complexity behind the scenes.


## Layers

1. **Domain/config (`clawake.config`)**
   - Pydantic models for cluster/hosts/instances/policies.
   - Single-host-first cluster mode (`single_host`) for MVP.
   - Explicit instance role (`product_owner|developer`).
   - Validation of host references, port collisions, and storage boundary collisions.
2. **Services (`clawake.services`)**
   - Render Quadlet files.
   - Lifecycle workflow support (`setup`, `restart`, `teardown`, `status`).
   - Systemd interaction wrappers.
3. **Interfaces**
   - CLI today (`clawake.cli`).
   - Dashboard API later (FastAPI) reusing same services.

## Operational safety principles

- Preview before mutation.
- Every instance has dedicated workspace/config/state paths and clear ownership boundaries.
- Explicit tag vs digest handling.
- Rootless/systemd-user assumptions are first-class.
- Human-readable errors for non-specialists.

## Workspace and state boundaries

- `workspace_path` is host-owned runtime workspace mounted at `/workspace`.
- `team_definition_path` is mounted read-only at `/team-definition` for role/team inputs.
- Runtime-mutated OpenClaw data remains owned by OpenClaw itself.
- This keeps Clawake focused on deployment orchestration while preserving a dedicated read-only team definition mount.

## Security guardrails (Phase 1)

- Path traversal via config values.
   - Risk: user-provided paths could escape expected workspace boundaries.
   - Impact: unintended host file exposure or mutation.
   - Mitigation: validate paths structurally, resolve to absolute paths, and fail on missing/invalid mount targets before mutation.
- Over-broad workspace write access.
   - Risk: container can write to too much host data.
   - Impact: accidental data loss or privilege expansion via host-mounted files.
   - Mitigation: keep write access limited to `workspace_path`, mount `team_definition_path` read-only, and keep runtime state under `workspace_path/.openclaw`.
- Untrusted image source.
   - Risk: mutable tags can pull unexpected image content.
   - Impact: drift, supply-chain compromise, and hard-to-reproduce runtime behavior.
   - Mitigation: prefer digest-aware image refs, keep explicit tag vs digest handling, and surface image decisions in preview output.
- Pasta network exposure.
   - Risk: incorrect port bindings can expose services wider than intended.
   - Impact: unintended access from non-local peers.
   - Mitigation: use explicit bind addresses and minimal published ports; document exposure rules in staff config review.

## Current MVP workflows

- `setup-quadlets` previews by default and applies with `--execute`; it renders and deploys member Quadlet artifacts.
- `restart-quadlets` restarts selected or all managed services after config/image changes.
- `teardown-quadlets` removes managed runtime services for selected members or whole teams.
- `status-quadlets` aggregates per-member runtime status with optional machine-readable output.
