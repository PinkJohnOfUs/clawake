# Inventory

Use this directory for real host/instance inventories used by operations.

- Keep environment examples in `examples/inventory/`.
- Keep deployable source-of-truth files here (for example `inventory/prod.yaml`).
- Run `clawake validate -c <file>` before render/deploy.
- Use a single-host cluster root (`cluster.mode: single_host`) for the current MVP.
