# Upgrade Playbook

Use the transactional member upgrade command for image changes:

```bash
# Preview only; does not contact the registry or mutate state.
clawake upgrade -c personal-team/team.yml -m fokus-partner \
  --to 2026.8.2 \
  --digest sha256:5d25165995041caa6a7175bec82b25ad98c44eb269bb42435da8e27ec06e6be4

# Verify the pinned image, back up state, migrate, deploy, restart, and verify health.
clawake upgrade -c personal-team/team.yml -m fokus-partner \
  --to 2026.8.2 \
  --digest sha256:5d25165995041caa6a7175bec82b25ad98c44eb269bb42435da8e27ec06e6be4 \
  --execute
```

An immutable digest is required when changing tags. The command scopes every operation to
the selected member and uses its `backup_policy` and `health` settings. It stops on failed
image validation, backup, migration, systemd activation, HTTP health, image identity, or
runtime-version verification.

## Recovery concept

Recovery should be deterministic and explicit:

- Successful upgrades retain the previous tag and digest as `known_good_tag` and
  `known_good_digest`.
- Runtime and configuration backups are written to `.backups/` before migrations.
- A failed migration restarts the unchanged previous service. A failure after deployment
  stops the upgraded service to prevent a restart loop and prints the recovery paths.
- Do not run `restart-quadlets` after `setup-quadlets --execute`; setup already reconciles
  and restarts the selected service.
