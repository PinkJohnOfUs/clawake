# syntax=docker/dockerfile:1.7

# =============================================================================
# OpenClaw Staff Image - SBOM Template
# =============================================================================
# Base: OpenClaw runtime container with extended development tooling
# Purpose: Standalone staff base image with gh, ripgrep, ffmpeg-static
# SBOM: Component versions captured at build time in /etc/staff-image-sbom.env
# Auth: Set GH_TOKEN env var at runtime for GitHub CLI authentication
# Maintenance: Rebuild image to get latest stable versions from apt repos
# =============================================================================

# -----------------------------------------------------------------------------
# Build Arguments - Version Control
# -----------------------------------------------------------------------------
ARG OPENCLAW_REPOSITORY=ghcr.io/openclaw/openclaw
ARG OPENCLAW_VERSION=2026.6.11
ARG FFMPEG_STATIC_NPM_VERSION=5.2.0

# -----------------------------------------------------------------------------
# Base Stage
# -----------------------------------------------------------------------------
FROM ${OPENCLAW_REPOSITORY}:${OPENCLAW_VERSION}

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

ARG FFMPEG_STATIC_NPM_VERSION

ENV HOME=/home/node
ENV PATH=/home/node/.local/bin:${PATH}

# -----------------------------------------------------------------------------
# System Dependencies & Directory Setup
# -----------------------------------------------------------------------------
USER root

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        gpg \
        gpg-agent \
        npm \
    ; \
    rm -rf /var/lib/apt/lists/*; \
    mkdir -p /home/node/.local/bin; \
    chown -R node:node /home/node/.local

# -----------------------------------------------------------------------------
# GitHub CLI (via official apt repository - latest stable)
# -----------------------------------------------------------------------------
RUN set -eux; \
    curl -fsSL https://cli.github.com/packages/githubcli-archive-keyring.gpg \
        | gpg --dearmor -o /usr/share/keyrings/githubcli-archive-keyring.gpg; \
    chmod go+r /usr/share/keyrings/githubcli-archive-keyring.gpg; \
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/usr/share/keyrings/githubcli-archive-keyring.gpg] https://cli.github.com/packages stable main" \
        > /etc/apt/sources.list.d/github-cli.list; \
    apt-get update; \
    apt-get install -y --no-install-recommends gh; \
    rm -rf /var/lib/apt/lists/*; \
    gh --version

# -----------------------------------------------------------------------------
# ripgrep (via apt - latest stable)
# -----------------------------------------------------------------------------
RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ripgrep; \
    rm -rf /var/lib/apt/lists/*; \
    rg --version

# -----------------------------------------------------------------------------
# ffmpeg-static (via npm - no system package available)
# -----------------------------------------------------------------------------
USER node

RUN set -eux; \
    npm install --prefix /home/node/.local/ffmpeg-static \
        "ffmpeg-static@${FFMPEG_STATIC_NPM_VERSION}"; \
    /home/node/.local/ffmpeg-static/node_modules/ffmpeg-static/ffmpeg -version

# -----------------------------------------------------------------------------
# Verification & SBOM Label Generation
# -----------------------------------------------------------------------------
USER root

RUN set -eux; \
    GH_VERSION=$(gh --version | head -n1 | awk '{print $3}'); \
    RG_VERSION=$(rg --version | head -n1 | awk '{print $2}'); \
    FFMPEG_VERSION=$(su - node -c '/home/node/.local/ffmpeg-static/node_modules/ffmpeg-static/ffmpeg -version 2>&1' | head -n1 | awk '{print $3}'); \
    printf 'GH_VERSION=%s\nRG_VERSION=%s\nFFMPEG_VERSION=%s\nFFMPEG_STATIC_NPM_VERSION=%s\n' \
        "$GH_VERSION" "$RG_VERSION" "$FFMPEG_VERSION" "${FFMPEG_STATIC_NPM_VERSION}" \
        > /etc/staff-image-sbom.env

# SBOM Metadata Labels
LABEL org.opencontainers.image.title="OpenClaw Staff Image"
LABEL org.opencontainers.image.description="OpenClaw base with gh, ripgrep, ffmpeg-static"
LABEL org.opencontainers.image.base.name="${OPENCLAW_REPOSITORY}:${OPENCLAW_VERSION}"
LABEL org.opencontainers.image.vendor="OpenClaw Project"
LABEL com.openclaw.component.gh-cli.source="apt"
LABEL com.openclaw.component.ripgrep.source="apt"
LABEL com.openclaw.component.ffmpeg-static.version="${FFMPEG_STATIC_NPM_VERSION}"
LABEL com.openclaw.component.ffmpeg-static.source="npm"
LABEL com.openclaw.sbom.manifest="/etc/staff-image-sbom.env"

USER node
