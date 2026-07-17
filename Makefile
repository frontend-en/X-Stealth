.DEFAULT_GOAL := help

COMPOSE ?= docker compose

LOCAL_ENV ?= .env
PROD_ENV ?= .env.prod
LOCAL_PROJECT ?= x-stealth-autoposter
PROD_PROJECT ?= x-stealth-autoposter-prod

LOCAL_COMPOSE = $(COMPOSE) --env-file $(LOCAL_ENV) --project-name $(LOCAL_PROJECT) -f docker-compose.yml
PROD_COMPOSE = $(COMPOSE) --env-file $(PROD_ENV) --project-name $(PROD_PROJECT) -f docker-compose.yml -f docker-compose.prod.yml

LOCAL_HEALTH_URL ?= http://127.0.0.1:8000/api/v1/health
PROD_HEALTH_URL ?= http://127.0.0.1:8000/api/v1/health
LOG_TAIL ?= 200

.PHONY: help
help:
	@echo ""
	@echo "X Stealth AutoPoster operations"
	@echo ""
	@echo "Setup:"
	@echo "  make env-local          Create .env from .env.example when missing"
	@echo "  make env-prod           Create .env.prod from .env.prod.example when missing"
	@echo ""
	@echo "Local:"
	@echo "  make local-build        Build local Docker images"
	@echo "  make local-up           Start local API and dashboard"
	@echo "  make local-down         Stop local stack"
	@echo "  make local-restart      Restart local stack"
	@echo "  make local-logs         Tail local stack logs"
	@echo "  make local-ps           Show local containers"
	@echo "  make local-health       Check local API health"
	@echo "  make local-bot          Run one standalone bot pass with local env"
	@echo ""
	@echo "Production:"
	@echo "  make prod-config        Render production Compose config"
	@echo "  make prod-build         Build production-tagged Docker images"
	@echo "  make prod-up            Start production stack"
	@echo "  make prod-down          Stop production stack"
	@echo "  make prod-restart       Restart production stack"
	@echo "  make prod-logs          Tail production stack logs"
	@echo "  make prod-ps            Show production containers"
	@echo "  make prod-health        Check production API health"
	@echo "  make prod-pull          Pull production images"
	@echo "  make prod-push          Push production images"
	@echo ""
	@echo "Verification:"
	@echo "  make verify             Run backend compile, frontend build, compose config"
	@echo "  make backend-compile    Compile backend Python modules"
	@echo "  make frontend-build     Build frontend assets"
	@echo ""

.PHONY: env-local env-prod require-prod-env
env-local:
	@if [ ! -f "$(LOCAL_ENV)" ]; then cp .env.example "$(LOCAL_ENV)"; echo "Created $(LOCAL_ENV)"; else echo "$(LOCAL_ENV) already exists"; fi

env-prod:
	@if [ ! -f "$(PROD_ENV)" ]; then cp .env.prod.example "$(PROD_ENV)"; echo "Created $(PROD_ENV). Review it before prod-up."; else echo "$(PROD_ENV) already exists"; fi

require-prod-env:
	@test -f "$(PROD_ENV)" || { echo "Missing $(PROD_ENV). Run make env-prod and review it first." >&2; exit 1; }

.PHONY: backend-compile frontend-build local-config verify
backend-compile:
	cd backend && python -m compileall src

frontend-build:
	npm --prefix frontend run build

local-config: env-local
	$(LOCAL_COMPOSE) config

verify: backend-compile frontend-build local-config

.PHONY: local-build local-up local-down local-restart local-logs local-ps local-health local-bot
local-build: env-local
	$(LOCAL_COMPOSE) build

local-up: env-local
	$(LOCAL_COMPOSE) up -d

local-down: env-local
	$(LOCAL_COMPOSE) down

local-restart: local-down local-up

local-logs: env-local
	$(LOCAL_COMPOSE) logs --tail=$(LOG_TAIL) -f

local-ps: env-local
	$(LOCAL_COMPOSE) ps

local-health:
	$(LOCAL_COMPOSE) exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=10).read().decode())"

local-bot: env-local
	$(LOCAL_COMPOSE) --profile bot run --rm bot

.PHONY: prod-config prod-build prod-up prod-down prod-restart prod-logs prod-ps prod-health prod-bot prod-pull prod-push
prod-config: require-prod-env
	$(PROD_COMPOSE) config

prod-build: require-prod-env
	$(PROD_COMPOSE) build

prod-up: require-prod-env
	$(PROD_COMPOSE) up -d

prod-down: require-prod-env
	$(PROD_COMPOSE) down

prod-restart: prod-down prod-up

prod-logs: require-prod-env
	$(PROD_COMPOSE) logs --tail=$(LOG_TAIL) -f

prod-ps: require-prod-env
	$(PROD_COMPOSE) ps

prod-health: require-prod-env
	$(PROD_COMPOSE) exec -T api python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=10).read().decode())"

prod-bot: require-prod-env
	$(PROD_COMPOSE) --profile bot run --rm bot

prod-pull: require-prod-env
	$(PROD_COMPOSE) pull

prod-push: require-prod-env
	$(PROD_COMPOSE) push
