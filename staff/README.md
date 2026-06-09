# Staff

Use this directory for real host/instance staff files used by operations.

- Keep environment examples in `examples/staff/`.
- Example env files live in `examples/staff/env/`.
- Keep deployable source-of-truth files here (for example `staff/product-owner.yml`).
- Run `clawake validate -c <file>` before render/deploy.
- Use a single-host cluster root (`cluster.mode: single_host`) for the current MVP.
