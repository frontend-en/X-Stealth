.DEFAULT_GOAL := help

COMPOSE ?= docker compose
POWERSHELL ?= powershell -NoProfile -ExecutionPolicy Bypass -Command

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
	@$(POWERSHELL) "Write-Host ''; Write-Host 'X Stealth AutoPoster operations'; Write-Host ''; Write-Host 'Setup:'; Write-Host '  make env-local          Create .env from .env.example when missing'; Write-Host '  make env-prod           Create .env.prod from .env.prod.example when missing'; Write-Host ''; Write-Host 'Local:'; Write-Host '  make local-build        Build local Docker images'; Write-Host '  make local-up           Start local API and dashboard'; Write-Host '  make local-down         Stop local stack'; Write-Host '  make local-restart      Restart local stack'; Write-Host '  make local-logs         Tail local stack logs'; Write-Host '  make local-ps           Show local containers'; Write-Host '  make local-health       Check local API health'; Write-Host '  make local-bot          Run one standalone bot pass with local env'; Write-Host ''; Write-Host 'Production:'; Write-Host '  make prod-config        Render production Compose config'; Write-Host '  make prod-build         Build production-tagged Docker images'; Write-Host '  make prod-up            Start production stack'; Write-Host '  make prod-down          Stop production stack'; Write-Host '  make prod-restart       Restart production stack'; Write-Host '  make prod-logs          Tail production stack logs'; Write-Host '  make prod-ps            Show production containers'; Write-Host '  make prod-health        Check production API health'; Write-Host '  make prod-pull          Pull production images'; Write-Host '  make prod-push          Push production images'; Write-Host ''; Write-Host 'Verification:'; Write-Host '  make verify             Run backend compile, frontend build, compose config'; Write-Host '  make backend-compile    Compile backend Python modules'; Write-Host '  make frontend-build     Build frontend assets'; Write-Host ''"

.PHONY: env-local env-prod require-prod-env
env-local:
	@$(POWERSHELL) "if (!(Test-Path -LiteralPath '$(LOCAL_ENV)')) { Copy-Item -LiteralPath '.env.example' -Destination '$(LOCAL_ENV)'; Write-Host 'Created $(LOCAL_ENV)' } else { Write-Host '$(LOCAL_ENV) already exists' }"

env-prod:
	@$(POWERSHELL) "if (!(Test-Path -LiteralPath '$(PROD_ENV)')) { Copy-Item -LiteralPath '.env.prod.example' -Destination '$(PROD_ENV)'; Write-Host 'Created $(PROD_ENV). Review it before prod-up.' } else { Write-Host '$(PROD_ENV) already exists' }"

require-prod-env:
	@$(POWERSHELL) "if (!(Test-Path -LiteralPath '$(PROD_ENV)')) { Write-Error 'Missing $(PROD_ENV). Run make env-prod and review it first.'; exit 1 }"

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
	@$(POWERSHELL) "Invoke-RestMethod -Uri '$(LOCAL_HEALTH_URL)' -TimeoutSec 10 | ConvertTo-Json -Compress"

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

prod-health:
	@$(POWERSHELL) "Invoke-RestMethod -Uri '$(PROD_HEALTH_URL)' -TimeoutSec 10 | ConvertTo-Json -Compress"

prod-bot: require-prod-env
	$(PROD_COMPOSE) --profile bot run --rm bot

prod-pull: require-prod-env
	$(PROD_COMPOSE) pull

prod-push: require-prod-env
	$(PROD_COMPOSE) push
