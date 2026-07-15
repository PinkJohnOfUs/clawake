PODMAN ?= podman

STAFF_DOCKERFILE ?= examples/staff/Dockerfile
STAFF_IMAGE_REPOSITORY ?= ghcr.io/openclaw/openclaw-staff
STAFF_IMAGE_TAG ?= 2026.6.11-tools

OPENCLAW_REPOSITORY ?= ghcr.io/openclaw/openclaw
OPENCLAW_VERSION ?= 2026.6.11

FFMPEG_STATIC_NPM_VERSION ?= 5.2.0

PO_CONTAINER ?= excalibot-product-owner
DEV_CONTAINER ?= excalibot-developer

.PHONY: staff-image-build staff-image-build-no-cache staff-image-team-snippet \
	staff-image-sbom staff-image-shell-po staff-image-shell-dev staff-image-shell

staff-image-build: ## Build staff image via Podman
	$(PODMAN) build \
		-f $(STAFF_DOCKERFILE) \
		-t $(STAFF_IMAGE_REPOSITORY):$(STAFF_IMAGE_TAG) \
		--build-arg OPENCLAW_REPOSITORY=$(OPENCLAW_REPOSITORY) \
		--build-arg OPENCLAW_VERSION=$(OPENCLAW_VERSION) \
		--build-arg FFMPEG_STATIC_NPM_VERSION=$(FFMPEG_STATIC_NPM_VERSION) \
		.

staff-image-build-no-cache: ## Build staff image via Podman without cache
	$(PODMAN) build --no-cache \
		-f $(STAFF_DOCKERFILE) \
		-t $(STAFF_IMAGE_REPOSITORY):$(STAFF_IMAGE_TAG) \
		--build-arg OPENCLAW_REPOSITORY=$(OPENCLAW_REPOSITORY) \
		--build-arg OPENCLAW_VERSION=$(OPENCLAW_VERSION) \
		--build-arg FFMPEG_STATIC_NPM_VERSION=$(FFMPEG_STATIC_NPM_VERSION) \
		.

staff-image-team-snippet: ## Print ready-to-copy image block for examples/staff/team.yml
	@printf 'image:\n'
	@printf '  repository: %s\n' '$(STAFF_IMAGE_REPOSITORY)'
	@printf '  tag: "%s"\n' '$(STAFF_IMAGE_TAG)'

staff-image-sbom: ## Display SBOM metadata from image labels
	@echo "=== Staff Image SBOM (OCI Labels) ==="
	@$(PODMAN) image inspect $(STAFF_IMAGE_REPOSITORY):$(STAFF_IMAGE_TAG) --format '{{range $$k, $$v := .Labels}}{{$$k}}: {{$$v}}{{"\n"}}{{end}}' | grep -E '^(org.opencontainers|com.openclaw)'
	@echo ""
	@echo "=== SBOM Manifest (Exact Versions) ==="
	@$(PODMAN) run --rm $(STAFF_IMAGE_REPOSITORY):$(STAFF_IMAGE_TAG) cat /etc/staff-image-sbom.env

staff-image-shell-po: ## Open bash in product-owner container
	$(PODMAN) exec -it $(PO_CONTAINER) bash

staff-image-shell-dev: ## Open bash in developer container
	$(PODMAN) exec -it $(DEV_CONTAINER) bash

staff-image-shell: ## Open bash in selected container (use CONTAINER=<name>)
	@if [ -z "$(CONTAINER)" ]; then \
		echo 'Set CONTAINER=<name>, e.g. make staff-image-shell CONTAINER=$(PO_CONTAINER)'; \
		exit 2; \
	fi
	$(PODMAN) exec -it $(CONTAINER) bash
