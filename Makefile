.PHONY: help run test lint install build

# Color output
BLUE := \033[0;34m
GREEN := \033[0;32m
RESET := \033[0m

help: ## Show this help message
	@printf "$(GREEN)lrc-match Development Commands:$(RESET)\n"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[0;34m%-15s\033[0m %s\n", $$1, $$2}'

run: ## Start FastAPI dev server with auto-reload
	@printf "$(BLUE)Starting lrc-match server at http://localhost:8000$(RESET)\n"
	uv run uvicorn lrc_match.app:create_app --factory --host 0.0.0.0 --port 8000 --reload

test: ## Run pytest
	@printf "$(BLUE)Running tests...$(RESET)\n"
	uv run pytest -q || test $$? -eq 5

install: ## Install dependencies + pre-commit hooks
	@printf "$(BLUE)Installing dependencies...$(RESET)\n"
	uv sync
	@printf "$(BLUE)Installing pre-commit hooks...$(RESET)\n"
	uv run pre-commit install
	uv run pre-commit install --hook-type commit-msg
	@printf "$(GREEN)Done$(RESET)\n"

build: ## Build Docker image locally
	@printf "$(BLUE)Building Docker image...$(RESET)\n"
	docker build -t lrc-match:dev .
	@printf "$(GREEN)Done$(RESET)\n"
