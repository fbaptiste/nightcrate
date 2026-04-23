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

.PHONY: help dev backend frontend install lint format test test-fast

## Start backend and frontend together (Ctrl+C stops both).
## Log level defaults to INFO; override with `make dev LOG=DEBUG`.
LOG ?= INFO
dev:
	@(cd backend && NIGHTCRATE_LOG_LEVEL=$(LOG) uv run uvicorn nightcrate.main:app --reload --port 8000) & \
	(cd frontend && npm run dev) & \
	trap '' INT TERM; \
	wait; \
	stty sane 2>/dev/null; true

## Start backend only (port 8000). Override log level with `make backend LOG=DEBUG`.
backend:
	cd backend && NIGHTCRATE_LOG_LEVEL=$(LOG) uv run uvicorn nightcrate.main:app --reload --port 8000

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
