# Staff

Use this directory for real host/instance staff files used by operations.

- Keep environment examples in `examples/staff/`.
- Example env files live in `examples/staff/env/`.
- Keep team source-of-truth files here (for example `staff/team.yml`).
- Use `clawake setup-quadlets -c <file>` as the default preview (dry-run).
- Use `clawake setup-quadlets -c <file> --execute` to apply rendered Quadlets.
- Use `clawake status-quadlets -c <file> --format text|json` to check member health.
- Use `clawake restart-quadlets -c <file> [--member <name>] --execute` after config/image changes.
- Use `clawake teardown-quadlets -c <file> [--member <name>] --execute` for controlled cleanup.
- Use a single-host cluster root (`cluster.mode: single_host`) for the current MVP.
