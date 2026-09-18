# Architecture

## Responsibility

Clawake is the local operations layer around an OpenClaw team. A YAML inventory
expresses desired deployment state; Podman executes containers and systemd user
services supervise them. OpenClaw remains responsible for agent behavior and its
runtime state. Clawake has no background controller or independent scheduler.

## Implemented boundaries

| Module | Responsibility | Effects |
| --- | --- | --- |
| `config.py` | Inventory schema, expansion and structural validation | Reads inventory |
| `services/render.py` | Deterministic Quadlet generation | Rendering is in memory; explicit export helper writes files |
| `services/deployment.py` | Typed artifact changes, desired/installed comparison, explicit apply | Planning reads installed files; applying writes changed files |
| `services/systemd.py` | systemd, journal and container command adapter | Commands execute only when requested |
| `services/gateway_config.py` | Managed workspace and local dashboard configuration | Updates OpenClaw configuration |
| `services/backup.py`, `upgrade.py`, `runtime_upgrade.py`, `image_check.py` | Upgrade planning, backups, migration and verification | Filesystem, registry and runtime operations |
| `cli.py` | Input/output, selection and lifecycle sequencing | Coordinates explicit operations |

The deployment service has no Typer dependency and returns immutable artifact
change records. Both setup and upgrade use it. Planning renders all selected
artifacts before applying any, and setup previews do not create a `.rendered`
directory. Applying writes directly to configured Quadlet destinations.

## Lifecycle contracts

1. Load and validate the inventory; resolve the selected members.
2. Render desired artifacts and compare them with installed text.
3. Present changes and the operational consequences.
4. Only with `--execute`, prepare runtime configuration and write artifacts.
5. Reload systemd; stop the setup workflow if reload fails.
6. Restart selected services and propagate failures to the caller.

Setup converges artifact contents but deliberately restarts even unchanged members
to reconcile stopped services. It is not a continuous reconciliation loop. File
application is not transactional: a filesystem failure can leave partial changes.
A subsequent setup can recompute the remaining differences.

Upgrade verifies the target image before stopping the service, backs up according
to policy, runs migrations, updates inventory and deploys the new artifacts. It
checks health and runtime identity after restart. Failure handling restarts the
previous image only before configuration changes; after changes it stops the
failed service and reports recovery information. Data rollback remains manual.

## Ownership and isolation

- The host workspace is mounted at `/workspace`.
- Team definitions are mounted read-only at `/team-definition`.
- Persistent OpenClaw state lives under the workspace's `.openclaw` directory.
- Additional configured mounts, environment files and port bindings extend the
  runtime's access and must be understood as part of the deployment definition.
- Optional per-member `dns_servers` entries are rendered as Quadlet `DNS=` settings
  and passed to the one-shot upgrade migration container. They must contain literal
  IPv4 or IPv6 addresses. This is useful when Podman's DNS forwarder cannot use a
  host-local resolver stub, but it couples the inventory to that network environment.
- Rootless Podman and systemd operate as the invoking user. Host records in an
  inventory do not imply an SSH transport or remote deployment capability.

Validation catches structural errors, host references and configured collisions.
It is not a proof of runtime readiness or a sandbox for hostile host configuration.
Status represents systemd service state, while upgrade has additional application
health checks. Mutable image tags remain accepted for setup; changing an image tag
through upgrade requires a digest.

## Direction

Keep future interfaces above the same inventory and application-service boundaries.
The next architectural step is extracting the remaining upgrade and lifecycle
sequencing from the CLI into workflows with injectable runtime adapters and typed
results. A web interface should reuse those workflows. Remote execution needs an
explicit transport and host-selection model before it can safely be supported.

These are extension points, not promises of already implemented functionality.

## Security decision and operator experience

The [security assessment](security.md) evaluates native OpenClaw, manually managed
Quadlets and Clawake, with a threat model and code-level gaps. Quadlet expresses
container settings; it is not an independent isolation boundary. Clawake's long-term
value depends on verifiable compatibility, deployment policy and recovery.

The [operator manual](manual.md) documents today's workflows. The
[user journey](user_journey.md) specifies the intended capability-oriented experience
without presenting planned commands as implemented features.
