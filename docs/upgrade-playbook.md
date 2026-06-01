# Upgrade Playbook (MVP)

1. Validate inventory:
   - `clawake validate -c examples/inventory/prod.yaml`
2. Render and inspect changes:
   - `clawake plan -c examples/inventory/prod.yaml -o .rendered/prod`
3. Create backup for target instance:
   - `clawake backup -c examples/inventory/prod.yaml -i openclaw-prod -o .backups --execute`
4. Deploy rendered Quadlet:
   - `clawake deploy -c examples/inventory/prod.yaml --target ~/.config/containers/systemd --execute`
5. Reload and restart service:
   - `clawake restart openclaw-prod --execute`
6. Verify health/logs:
   - `clawake status openclaw-prod --execute`
   - `clawake logs openclaw-prod --execute --lines 200`
7. If unhealthy, rollback to known-good digest and redeploy.

## Rollback concept

Store known-good digest in inventory (`image.known_good_digest`) and revert to it during rollback workflows.
