.PHONY: help up down clean run test lint install build

# Load .env if present
ifneq (,$(wildcard .env))
    include .env
    export
endif

# Color output
BLUE := \033[0;34m
GREEN := \033[0;32m
RESET := \033[0m

help: ## Show this help message
	@printf "$(GREEN)resonance Development Commands:$(RESET)\n"
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[0;34m%-15s\033[0m %s\n", $$1, $$2}'

up: ## Start dev dependencies (Qdrant)
	@printf "$(BLUE)Starting dev services...$(RESET)\n"
	docker compose -f docker-compose.dev.yml up -d
	@printf "$(GREEN)Qdrant running at http://localhost:6333$(RESET)\n"

down: ## Stop dev dependencies
	@printf "$(BLUE)Stopping dev services...$(RESET)\n"
	docker compose -f docker-compose.dev.yml down
	@printf "$(GREEN)Services stopped$(RESET)\n"

clean: ## Stop services and remove volumes (fresh start)
	@printf "$(BLUE)Cleaning Docker state...$(RESET)\n"
	docker compose -f docker-compose.dev.yml down -v
	@printf "$(GREEN)Clean state restored$(RESET)\n"

run: up ## Start Qdrant + dev server (Swagger UI at /docs)
	@printf "$(BLUE)Starting resonance at http://localhost:8000/docs$(RESET)\n"
	uv run resonance-dev

test: ## Run pytest
	@printf "$(BLUE)Running tests...$(RESET)\n"
	uv run pytest -q || test $$? -eq 5

lint: ## Run ruff linter + formatter check
	@printf "$(BLUE)Running linters...$(RESET)\n"
	uv run ruff check src/
	uv run ruff format --check src/
	@printf "$(GREEN)Done$(RESET)\n"

install: ## Install dependencies + pre-commit hooks
	@printf "$(BLUE)Installing dependencies...$(RESET)\n"
	uv sync
	@printf "$(BLUE)Installing pre-commit hooks...$(RESET)\n"
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg
	@printf "$(GREEN)Done$(RESET)\n"

build: ## Build Docker image locally
	@printf "$(BLUE)Building Docker image...$(RESET)\n"
	docker build -t resonance:dev .
	@printf "$(GREEN)Done$(RESET)\n"
