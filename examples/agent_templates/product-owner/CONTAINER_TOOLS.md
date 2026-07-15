# CONTAINER_TOOLS.md

This workspace runs inside a container. Runtime installs are ephemeral unless they are documented here and later moved into the image build.

Fixed rule: whenever a tool is installed or changed during a session, update this file with reproducible installation details before considering the setup complete. Do not store secrets or tokens here.

## Installed Tools

### Bootstrap tool checker (`scripts/bootstrap-tools.sh`)

- **Installed at runtime:** 2026-06-18
- **Current install location:** `/home/node/.openclaw/workspace/scripts/bootstrap-tools.sh`
- **Purpose:** Idempotently verifies and installs the workspace container tools listed here.
- **Startup hook:** `~/.profile` and `~/.bashrc` call the script when readable.
- **Install target:** `/home/node/.local/bin`
- **Auth behavior:** Uses `GH_TOKEN` from the runtime environment for `gh auth login --with-token`. Do not store the token in files.
- **Verification command:** `/home/node/.openclaw/workspace/scripts/bootstrap-tools.sh`

Dockerfile-ready install sketch:

```dockerfile
COPY scripts/bootstrap-tools.sh /home/node/.openclaw/workspace/scripts/bootstrap-tools.sh
RUN chmod +x /home/node/.openclaw/workspace/scripts/bootstrap-tools.sh
ENV PATH="/home/node/.local/bin:${PATH}"
RUN /home/node/.openclaw/workspace/scripts/bootstrap-tools.sh
```

### GitHub CLI (`gh`)

- **Version:** 2.94.0
- **Installed at runtime:** 2026-06-17
- **Current install location:** `/home/node/.local/bin/gh`
- **Source:** `https://github.com/cli/cli/releases/download/v2.94.0/gh_2.94.0_linux_amd64.tar.gz`
- **Checksum file:** `https://github.com/cli/cli/releases/download/v2.94.0/gh_2.94.0_checksums.txt`
- **Verification command:** `/home/node/.local/bin/gh --version`
- **Auth status:** Authenticated at startup when `GH_TOKEN` is present and valid.
- **Purpose:** Coordinate GitHub organization project `edge-robot/projects/3` for Excalibot.

Dockerfile-ready install sketch:

```dockerfile
ARG GH_VERSION=2.94.0
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl tar; \
    rm -rf /var/lib/apt/lists/*; \
    curl -fsSLO "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_amd64.tar.gz"; \
    curl -fsSLO "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_checksums.txt"; \
    grep "gh_${GH_VERSION}_linux_amd64.tar.gz$" "gh_${GH_VERSION}_checksums.txt" | sha256sum -c -; \
    tar -xzf "gh_${GH_VERSION}_linux_amd64.tar.gz"; \
    install -m 0755 "gh_${GH_VERSION}_linux_amd64/bin/gh" /usr/local/bin/gh; \
    rm -rf "gh_${GH_VERSION}_linux_amd64" "gh_${GH_VERSION}_linux_amd64.tar.gz" "gh_${GH_VERSION}_checksums.txt"; \
    gh --version
```

Runtime auth setup after the container starts:

```bash
gh auth login --hostname github.com --git-protocol https --web --scopes "repo,read:org,project"
```

Alternative noninteractive setup when a token is supplied securely by the runtime:

```bash
printf '%s\n' "$GH_TOKEN" | gh auth login --with-token
gh auth status
```

### ripgrep (`rg`)

- **Version:** 14.1.1
- **Installed at runtime:** 2026-06-18
- **Current install location:** `/home/node/.local/bin/rg`
- **Source:** `https://github.com/BurntSushi/ripgrep/releases/download/14.1.1/ripgrep-14.1.1-x86_64-unknown-linux-musl.tar.gz`
- **Verification command:** `/home/node/.local/bin/rg --version`
- **Purpose:** Fast workspace search; preferred over slower recursive grep/find patterns.

Dockerfile-ready install sketch:

```dockerfile
ARG RG_VERSION=14.1.1
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl tar; \
    rm -rf /var/lib/apt/lists/*; \
    curl -fsSLO "https://github.com/BurntSushi/ripgrep/releases/download/${RG_VERSION}/ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl.tar.gz"; \
    tar -xzf "ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl.tar.gz"; \
    install -m 0755 "ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl/rg" /usr/local/bin/rg; \
    rm -rf "ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl" "ripgrep-${RG_VERSION}-x86_64-unknown-linux-musl.tar.gz"; \
    rg --version
```

### ffmpeg-static

- **Package:** `ffmpeg-static@5.2.0`
- **FFmpeg version:** 6.0-static
- **Installed at runtime:** 2026-06-29
- **Current install location:** `/home/node/.openclaw/tools/ffmpeg-static`
- **Install method:** `npm install --prefix /home/node/.openclaw/tools/ffmpeg-static ffmpeg-static@5.2.0`
- **Verification command:** `/home/node/.openclaw/tools/ffmpeg-static/node_modules/ffmpeg-static/ffmpeg -version`
- **Purpose:** Decode local MP4/video files and extract frames for inspection when browser/media tools are unavailable.

Dockerfile-ready install sketch:

```dockerfile
RUN mkdir -p /home/node/.openclaw/tools/ffmpeg-static && \
    npm install --prefix /home/node/.openclaw/tools/ffmpeg-static ffmpeg-static@5.2.0 && \
    /home/node/.openclaw/tools/ffmpeg-static/node_modules/ffmpeg-static/ffmpeg -version
```
