.DEFAULT_GOAL := help

# COLORS
GREEN  := $(shell tput -Txterm setaf 2)
YELLOW := $(shell tput -Txterm setaf 3)
WHITE  := $(shell tput -Txterm setaf 7)
RESET  := $(shell tput -Txterm sgr0)

## Show help
TARGET_MAX_CHAR_NUM=30
help:
	@awk '/^[a-zA-Z\-\_0-9\.]+:/ { \
		helpMessage = match(lastLine, /^## (.*)/); \
		if (helpMessage) { \
			helpCommand = substr($$1, 0, index($$1, ":")); \
			helpMessage = substr(lastLine, RSTART + 3, RLENGTH); \
			printf "  ${YELLOW}%-$(TARGET_MAX_CHAR_NUM)s${RESET} ${GREEN}%s${RESET}\n", helpCommand, helpMessage; \
		} \
	} \
	{ lastLine = $$0 }' $(MAKEFILE_LIST)

.PHONY: help dev dev-lan backend backend-lan frontend install lint format test test-fast

## Start backend and frontend together (Ctrl+C stops both).
## Log level defaults to INFO; override with `make dev LOG=DEBUG`.
## BROWSER defaults to Brave (Fred's default); override with `make dev BROWSER=...`
## or BROWSER=none to suppress auto-opening. Vite's macOS heuristic picks the
## first running Chromium-family browser from its own list (Chrome before Brave),
## so setting BROWSER explicitly is needed when multiple are running.
LOG ?= INFO
BROWSER ?= Brave Browser
dev:
	@(cd backend && NIGHTCRATE_LOG_LEVEL=$(LOG) uv run uvicorn nightcrate.main:app --reload --port 8000) & \
	(cd frontend && BROWSER="$(BROWSER)" npm run dev) & \
	trap '' INT TERM; \
	wait; \
	stty sane 2>/dev/null; true

## Start backend + frontend on LAN (accessible from other machines on local network)
dev-lan:
	@(cd backend && NIGHTCRATE_LAN=1 NIGHTCRATE_LOG_LEVEL=$(LOG) uv run uvicorn nightcrate.main:app --reload --host 0.0.0.0 --port 8000) & \
	(cd frontend && NIGHTCRATE_LAN=1 npm run dev) & \
	trap '' INT TERM; \
	wait; \
	stty sane 2>/dev/null; true

## Start backend only (port 8000). Override log level with `make backend LOG=DEBUG`.
backend:
	cd backend && NIGHTCRATE_LOG_LEVEL=$(LOG) uv run uvicorn nightcrate.main:app --reload --port 8000

## Start backend only, accessible on LAN
backend-lan:
	cd backend && NIGHTCRATE_LAN=1 NIGHTCRATE_LOG_LEVEL=$(LOG) uv run uvicorn nightcrate.main:app --reload --host 0.0.0.0 --port 8000

## Start frontend only (port 5173)
frontend:
	cd frontend && npm run dev

## Install all dependencies (backend + frontend)
install:
	cd backend && uv sync
	cd frontend && npm install

## Run ruff lint on backend
lint:
	cd backend && uv run ruff check src/

## Run ruff format on backend
format:
	cd backend && uv run ruff format src/

## Run backend tests (serial — full output, consistent ordering)
test:
	cd backend && uv run pytest

## Run backend tests in parallel via pytest-xdist (fast — uses all CPU cores)
test-fast:
	cd backend && uv run pytest -n auto
