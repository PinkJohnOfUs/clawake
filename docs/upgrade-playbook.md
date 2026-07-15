# Upgrade Playbook (MVP)

This playbook follows the lifecycle-first operator model.

1. Diagnose dashboard access and token wiring:
   - `clawake diagnose-dashboard -c examples/staff/team.yml`
2. Apply or refresh Quadlet definitions:
   - `clawake setup-quadlets -c examples/staff/team.yml`
3. Restart impacted services:
   - `clawake restart-quadlets -c examples/staff/team.yml`
4. Verify runtime status:
   - `clawake status-quadlets -c examples/staff/team.yml`
5. If needed, remove and re-setup affected members:
   - `clawake teardown-quadlets -c examples/staff/team.yml --member <name>`
   - `clawake setup-quadlets -c examples/staff/team.yml --member <name>`

## Recovery concept

Recovery should be deterministic and explicit:

- Keep image provenance in the staff file (`tag` and optional `digest`).
- Reconcile by running `setup-quadlets` followed by `restart-quadlets`.
- Use `status-quadlets` as the canonical health checkpoint.
