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

# Remote VPS deployment settings. Override these on the make command line.
VPS_HOST ?=31.76.42.159
VPS_USER ?= root
VPS_PORT ?= 22
VPS_PATH ?= /root/X-Stealth
VPS_SSH_KEY ?=
VPS_TARGET = $(VPS_USER)@$(VPS_HOST)
VPS_SSH_KEY_ARG = $(if $(VPS_SSH_KEY),-i "$(VPS_SSH_KEY)",)
VPS_SSH = ssh -p $(VPS_PORT) -o BatchMode=yes -o StrictHostKeyChecking=accept-new $(VPS_SSH_KEY_ARG)
DEPLOY_TAR_EXCLUDES = --exclude-vcs --exclude=.env --exclude=.env.local --exclude=.env.prod --exclude=backend/auth.json --exclude=backend/.venv --exclude=backend/__pycache__ --exclude=backend/**/__pycache__ --exclude=backend/logs --exclude=backend/screenshots --exclude=backend/traces --exclude=frontend/node_modules --exclude=frontend/dist

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
	@echo "  make local-bot          Start the local scheduler worker"
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
	@echo "  make prod-first-deploy  Upload source to VPS and start the complete stack"
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
	$(LOCAL_COMPOSE) up -d bot

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
	$(PROD_COMPOSE) up -d bot

prod-pull: require-prod-env
	$(PROD_COMPOSE) pull

prod-push: require-prod-env
	$(PROD_COMPOSE) push

.PHONY: require-vps prod-first-deploy
require-vps:
	@test -n "$(VPS_HOST)" || { echo "Missing VPS_HOST. Example: make prod-first-deploy VPS_HOST=203.0.113.10" >&2; exit 1; }

# Run this from the machine that owns the SSH private key. The archive omits
# secrets and runtime artifacts; existing remote .env.prod and auth.json stay
# untouched. On first run, safe defaults and an empty protected auth.json are
# created on the VPS.
prod-first-deploy: require-vps
	@echo "Uploading application source to $(VPS_TARGET):$(VPS_PATH)"
	tar -czf - $(DEPLOY_TAR_EXCLUDES) . | $(VPS_SSH) "$(VPS_TARGET)" "mkdir -p '$(VPS_PATH)' && tar -xzf - -C '$(VPS_PATH)'"
	@echo "Building and starting the production stack on $(VPS_TARGET)"
	$(VPS_SSH) "$(VPS_TARGET)" "set -eu; cd '$(VPS_PATH)'; test -f .env.prod || cp .env.prod.example .env.prod; mkdir -p backend/data backend/logs backend/screenshots backend/traces; chown -R 999:999 backend/data backend/logs backend/screenshots backend/traces; test -f backend/auth.json || { umask 077; : > backend/auth.json; }; chown 999:999 backend/auth.json; chmod 600 backend/auth.json; make prod-config >/dev/null; make prod-build; make prod-up; make prod-ps; make prod-health"
