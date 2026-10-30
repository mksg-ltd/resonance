.PHONY: help up down clean run ui prod prod-down test lint install build

# Python settings and Docker Compose parse .env; Make must not reinterpret secrets.

# Color output
BLUE := \033[0;34m
GREEN := \033[0;32m
RESET := \033[0m

help: ## Show this help message
	@printf "$(GREEN)resonance Development Commands:$(RESET)\n"
	@grep -hE '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[0;34m%-15s\033[0m %s\n", $$1, $$2}'

up: ## Start dev dependencies (Qdrant + TEI)
	@printf "$(BLUE)Starting dev services...$(RESET)\n"
	docker compose up -d qdrant tei
	@printf "$(GREEN)Qdrant running at http://localhost:6333$(RESET)\n"

down: ## Stop dev dependencies without deleting state
	@printf "$(BLUE)Stopping dev services...$(RESET)\n"
	docker compose stop qdrant tei
	@printf "$(GREEN)Services stopped$(RESET)\n"

clean: ## Remove dev dependency containers, preserving stored data
	@printf "$(BLUE)Cleaning Docker state...$(RESET)\n"
	docker compose rm -sf qdrant tei
	@printf "$(GREEN)Clean state restored$(RESET)\n"

run: up ## Start Qdrant + dev server (Swagger UI at /docs)
	@printf "$(BLUE)Starting resonance at http://localhost:8000/docs$(RESET)\n"
	uv run resonance-dev

ui: ## Start the Vue/Vite development server at http://127.0.0.1:5173
	@test -x vue-ui/node_modules/.bin/vite || { printf "Install frontend dependencies first: pnpm --dir vue-ui install\n"; exit 1; }
	cd vue-ui && ./node_modules/.bin/vite --host 127.0.0.1

prod: ## Start full stack (UI at /, API at /api, Qdrant + resonance + TEI)
	@printf "$(BLUE)Starting production stack...$(RESET)\n"
	docker compose up -d --build
	@printf "$(GREEN)UI: http://localhost:8000/ · API: http://localhost:8000/api$(RESET)\n"

prod-down: ## Stop production stack
	@printf "$(BLUE)Stopping production stack...$(RESET)\n"
	docker compose down
	@printf "$(GREEN)Stack stopped$(RESET)\n"

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
