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

## Staff Image Workflow (Podman)

Use the Make targets from `make/staff-image.mk` (included by the root `Makefile`) to build the custom staff image and prepare the image block for `examples/staff/team.yml`.

The `/examples/staff/Dockerfile` is designed as an **SBOM-ready standalone base image** with:
- **No workspace dependencies** - pure base image with tools
- **SBOM manifest** at `/etc/staff-image-sbom.env` with exact versions captured at build time
- **OCI image labels** for component tracking via `podman inspect`
- **Simplified apt-based installation** (GitHub CLI, ripgrep from stable repos)
- **npm-based ffmpeg-static** installed to `/home/node/.local/ffmpeg-static`
- **Clean structure** - tools available system-wide, no bootstrap scripts

### 1) Build custom staff image

Build with defaults:

```bash
make staff-image-build
```

Build without cache:

```bash
make staff-image-build-no-cache
```

Override versions and repository:

```bash
make staff-image-build \
  OPENCLAW_REPOSITORY=ghcr.io/openclaw/openclaw \
  OPENCLAW_VERSION=2026.6.11 \
  FFMPEG_STATIC_NPM_VERSION=5.2.0 \
  STAFF_IMAGE_REPOSITORY=ghcr.io/openclaw/openclaw-staff \
  STAFF_IMAGE_TAG=2026.6.11-tools
```

**Note:** GitHub CLI and ripgrep versions come from apt stable repositories and are determined at build time. See the SBOM manifest for exact versions.

### 2) Print copy/paste image block for team.yml

```bash
make staff-image-team-snippet
```

Example output:

```yaml
image:
  repository: ghcr.io/openclaw/openclaw-staff
  tag: "2026.6.11-tools"
```

Paste this block into the instance image section in `examples/staff/team.yml`.

### 3) Inspect SBOM metadata

View embedded OCI labels:

```bash
make staff-image-sbom
```

View exact installed versions from SBOM manifest:

```bash
podman run --rm ghcr.io/openclaw/openclaw-staff:2026.6.11-tools cat /etc/staff-image-sbom.env
```

Example output:

```
GH_VERSION=2.96.0
RG_VERSION=13.0.0
FFMPEG_VERSION=6.0-static
FFMPEG_STATIC_NPM_VERSION=5.2.0
```

These versions are captured at build time from the stable apt repositories and npm.

### 4) Open bash in running containers

Product Owner container:

```bash
make staff-image-shell-po
```

Developer container:

```bash
make staff-image-shell-dev
```

Generic shell target (explicit container):

```bash
make staff-image-shell CONTAINER=excalibot-product-owner
```

### 5) GitHub CLI Authentication (Optional)

To authenticate GitHub CLI at runtime, set the `GH_TOKEN` environment variable when starting the container:

```bash
podman run --rm -e GH_TOKEN="your-token-here" \
  ghcr.io/openclaw/openclaw-staff:2026.6.11-tools \
  gh auth status
```

Or in team.yml via env_files.

### 6) Apply updated team config to Quadlets

After changing `examples/staff/team.yml`, render/apply and restart:

```bash
make setup-quadlets-exec CONFIG=examples/staff/team.yml
make restart-quadlets-exec CONFIG=examples/staff/team.yml
```
