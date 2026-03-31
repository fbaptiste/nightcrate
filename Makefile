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

.PHONY: help dev backend frontend install lint format test

## Start backend and frontend together (Ctrl+C stops both)
dev:
	@trap 'kill 0' EXIT; \
	(cd backend && uv run uvicorn nightcrate.main:app --reload --port 8000) & \
	(cd frontend && npm run dev) & \
	wait || true

## Start backend only (port 8000)
backend:
	cd backend && uv run uvicorn nightcrate.main:app --reload --port 8000

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

## Run backend tests
test:
	cd backend && uv run pytest
