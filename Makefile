.DEFAULT_GOAL := help

# COLORS
GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
WHITE  := $(shell tput -Txterm setaf 7)
RESET  := $(shell tput -Txterm sgr0)

TARGET_MAX_CHAR_NUM=30

# Log level defaults to INFO; override with `make dev LOG=DEBUG`.
LOG ?= INFO

# On macOS, BROWSER defaults to Brave; override with `make dev BROWSER=...`
# or BROWSER=none to suppress auto-opening. Vite's macOS heuristic picks the
# first running Chromium-family browser from its own list (Chrome before Brave),
# so setting BROWSER explicitly is needed when multiple are running. "Brave
# Browser" is a macOS app name, so elsewhere BROWSER stays unset and Vite opens
# the system default browser.
UNAME_S := $(shell uname -s 2>/dev/null)
ifeq ($(UNAME_S),Darwin)
BROWSER ?= Brave Browser
endif

# `make help` lists each target with the `## ` summary on its own line.
help: ## Show help
	@awk 'match($$0, /^[a-zA-Z0-9_.-]+:.*## /) { \
		helpCommand = substr($$0, 1, index($$0, ":")); \
		helpMessage = substr($$0, RSTART + RLENGTH); \
		printf "  ${YELLOW}%-$(TARGET_MAX_CHAR_NUM)s${RESET} ${GREEN}%s${RESET}\n", helpCommand, helpMessage; \
	}' $(MAKEFILE_LIST)

.PHONY: help dev dev-lan backend backend-lan frontend install lint format test test-fast

dev: ## Start backend and frontend together (Ctrl+C stops both). Options: LOG=DEBUG, BROWSER=... or BROWSER=none.
	@(cd backend && NIGHTCRATE_LOG_LEVEL=$(LOG) uv run uvicorn nightcrate.main:app --reload --port 8000) & \
	(cd frontend && $(if $(BROWSER),BROWSER="$(BROWSER)" )npm run dev) & \
	trap '' INT TERM; \
	wait; \
	stty sane 2>/dev/null; true

dev-lan: ## Start backend + frontend on LAN (accessible from other machines on local network)
	@(cd backend && NIGHTCRATE_LAN=1 NIGHTCRATE_LOG_LEVEL=$(LOG) uv run uvicorn nightcrate.main:app --reload --host 0.0.0.0 --port 8000) & \
	(cd frontend && NIGHTCRATE_LAN=1 npm run dev) & \
	trap '' INT TERM; \
	wait; \
	stty sane 2>/dev/null; true

backend: ## Start backend only (port 8000). Override log level with `make backend LOG=DEBUG`.
	cd backend && NIGHTCRATE_LOG_LEVEL=$(LOG) uv run uvicorn nightcrate.main:app --reload --port 8000

backend-lan: ## Start backend only, accessible on LAN
	cd backend && NIGHTCRATE_LAN=1 NIGHTCRATE_LOG_LEVEL=$(LOG) uv run uvicorn nightcrate.main:app --reload --host 0.0.0.0 --port 8000

frontend: ## Start frontend only (port 5173)
	cd frontend && npm run dev

# `npm ci` installs exactly what package-lock.json lists and never rewrites it.
# Add or upgrade a frontend package with `npm install <package>` in frontend/.
install: ## Install all dependencies (backend + frontend) from the lockfiles
	cd backend && uv sync
	cd frontend && npm ci

lint: ## Run ruff lint on backend
	cd backend && uv run ruff check src/

format: ## Run ruff format on backend
	cd backend && uv run ruff format src/

test: ## Run backend tests (serial — full output, consistent ordering)
	cd backend && uv run pytest

test-fast: ## Run backend tests in parallel via pytest-xdist (fast — uses all CPU cores)
	cd backend && uv run pytest -n auto
