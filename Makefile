.DEFAULT_GOAL := help

include make/clawake.mk
include make/staff-image.mk

help: ## Show help for main targets
	@# Modified from https://gist.github.com/prwhite/8168133?permalink_comment_id=4260260#gistcomment-4260260
	@grep -hE '^[A-Za-z0-9_ \%-]*?:[^#]*?##[^#].*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'

help-all: ## Show help for all targets
	@# Modified from https://gist.github.com/prwhite/8168133?permalink_comment_id=4260260#gistcomment-4260260
	@grep -hE '^[A-Za-z0-9_ \%-]*?:.*##.*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-30s\033[0m %s\n", $$1, $$2}'