# Спецификация интеграции frontend и backend

Дата: 2026-06-30  
Статус: проектный контракт для реализации  
Область: `frontend/` Vite React dashboard + `backend/` Python Playwright app

## 1. Цель

Соединить текущий React dashboard с Python backend так, чтобы frontend показывал реальное состояние очереди, настроек, запусков и артефактов, а backend оставался единственным слоем, который читает runtime-файлы и выполняет действия.

Интеграция должна начинаться с безопасного режима разработки:

- по умолчанию `DRY_RUN=true`;
- по умолчанию `POSTING_ENABLED=false`;
- frontend не может напрямую включать публикацию без backend-side проверок;
- `auth.json`, `.env`, логи, screenshots и traces не отдаются как произвольные файлы.

## 2. Текущие компоненты

### Backend

Текущий backend запускается как CLI:

```powershell
cd backend
python -m src.main
```

Основные модули:

- `src/config.py` - Pydantic settings из `.env`;
- `src/main.py` - entrypoint для одного запуска;
- `src/tweet_source.py` - чтение постов из `data/tweets.txt`;
- `src/x_bot.py` - workflow публикации через Playwright;
- `logs/`, `screenshots/`, `traces/` - runtime-артефакты.

### Frontend

Текущий frontend - Vite React dashboard:

```powershell
cd frontend
npm run dev
```

Сейчас данные находятся в `frontend/src/main.jsx` как моковые массивы `posts`, `weeklyPerformance`, `queueMix`, `personaData`.

## 3. Целевая архитектура

Добавить backend API слой, который будет жить рядом с CLI-логикой и использовать существующие модули.

Рекомендуемая структура:

```text
backend/
  src/
    api/
      __init__.py
      app.py              # ASGI app
      schemas.py          # Pydantic response/request DTO
      routes/
        health.py
        settings.py
        queue.py
        runs.py
        artifacts.py
    services/
      queue_service.py    # работа с data/tweets.txt
      run_service.py      # запуск dry-run/job и статус
      artifact_service.py # безопасный список logs/screenshots/traces
```

Frontend получает данные только через HTTP:

```text
React UI -> API client -> Backend API -> services -> existing backend modules/files
```

Backend CLI `python -m src.main` остается рабочим. API слой не должен ломать текущий one-shot запуск.

## 4. Технологический выбор

Рекомендуемый backend API framework: FastAPI.

Причины:

- уже используется Pydantic;
- удобная OpenAPI-схема для frontend-контракта;
- простая ASGI-разработка через `uvicorn`;
- удобно типизировать request/response DTO.

Новые backend зависимости:

```text
fastapi
uvicorn[standard]
```

Команда разработки:

```powershell
cd backend
uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

Frontend env:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

## 5. API контракт v1

Все endpoint'ы имеют префикс `/api/v1`.

### 5.1 Health

`GET /api/v1/health`

Назначение: проверка доступности backend.

Response:

```json
{
  "status": "ok",
  "version": "0.1.0",
  "time": "2026-06-30T09:00:00Z"
}
```

### 5.2 Runtime settings

`GET /api/v1/settings`

Назначение: отдать только безопасные runtime-настройки для UI.

Response:

```json
{
  "dryRun": true,
  "postingEnabled": false,
  "headless": true,
  "xBaseUrl": "https://x.com",
  "dataPath": "data/tweets.txt",
  "logsDir": "logs",
  "screenshotsDir": "screenshots",
  "tracesDir": "traces",
  "minPostIntervalMinutes": 180,
  "warmupScrollRange": {
    "min": 2,
    "max": 5
  },
  "hasAuthState": true,
  "hasProxyConfigured": false
}
```

Запрещено отдавать:

- `proxy_url`;
- содержимое `.env`;
- содержимое `auth.json`;
- абсолютные пути за пределами проекта.

### 5.3 Queue summary

`GET /api/v1/queue`

Назначение: прочитать `data/tweets.txt` и вернуть очередь постов.

Query params:

- `limit`: integer, default `50`, max `200`;
- `offset`: integer, default `0`.

Response:

```json
{
  "items": [
    {
      "id": "tweet-0001",
      "text": "Example post text",
      "textLength": 17,
      "status": "queued",
      "risk": "low",
      "source": "data/tweets.txt",
      "createdAt": null,
      "scheduledFor": null
    }
  ],
  "total": 1
}
```

Status values:

- `queued`;
- `draft`;
- `blocked`;
- `posted`;
- `failed`;
- `dry_run_completed`.

Risk values:

- `low` - valid text, length `1..280`;
- `medium` - empty text, too long, suspicious spacing, duplicate candidate;
- `high` - backend-side validation blocks action.

### 5.4 Queue item detail

`GET /api/v1/queue/{itemId}`

Назначение: показать один пост, validation details и связанную историю запусков.

Response:

```json
{
  "id": "tweet-0001",
  "text": "Example post text",
  "textLength": 17,
  "status": "queued",
  "risk": "low",
  "validation": {
    "valid": true,
    "errors": []
  },
  "runs": []
}
```

### 5.5 Validate post text

`POST /api/v1/queue/validate`

Назначение: frontend может проверять текст до сохранения или запуска.

Request:

```json
{
  "text": "Example post text"
}
```

Response:

```json
{
  "valid": true,
  "textLength": 17,
  "errors": [],
  "warnings": []
}
```

Backend validation:

- text must not be empty;
- text length must be `<= 280`;
- normalize line endings;
- reject control characters except newline and tab.

### 5.6 Create draft queue item

`POST /api/v1/queue`

Назначение: добавить draft в управляемое хранилище очереди.

MVP-вариант: backend может возвращать `501 Not Implemented`, если очередь пока остается read-only из `data/tweets.txt`.

Request:

```json
{
  "text": "New post",
  "scheduledFor": null
}
```

Response:

```json
{
  "id": "tweet-0002",
  "status": "draft"
}
```

### 5.7 Runs

`GET /api/v1/runs`

Назначение: список последних запусков.

Response:

```json
{
  "items": [
    {
      "id": "run-20260630-090000",
      "queueItemId": "tweet-0001",
      "mode": "dry_run",
      "status": "completed",
      "startedAt": "2026-06-30T09:00:00Z",
      "finishedAt": "2026-06-30T09:00:02Z",
      "message": "Dry run: posting skipped",
      "artifacts": []
    }
  ],
  "total": 1
}
```

Run modes:

- `dry_run`;
- `publish`.

Run statuses:

- `queued`;
- `running`;
- `completed`;
- `failed`;
- `cancelled`;
- `blocked`.

### 5.8 Start dry-run

`POST /api/v1/runs/dry-run`

Назначение: безопасно проверить выбранный пост без публикации.

Request:

```json
{
  "queueItemId": "tweet-0001"
}
```

Response:

```json
{
  "runId": "run-20260630-090000",
  "status": "queued"
}
```

MVP-поведение:

- backend вызывает тот же validation path, что и реальный запуск;
- backend не открывает X и не публикует;
- результат фиксируется в run history.

### 5.9 Start publish run

`POST /api/v1/runs/publish`

Назначение: запустить реальную публикацию только если backend разрешает это по конфигурации.

Request:

```json
{
  "queueItemId": "tweet-0001",
  "confirm": true
}
```

Response when disabled:

```json
{
  "error": {
    "code": "POSTING_DISABLED",
    "message": "Publishing is disabled by backend configuration."
  }
}
```

Required backend gates:

- `POSTING_ENABLED=true`;
- `DRY_RUN=false`;
- `auth.json` exists;
- text validates;
- no active publish run is currently running;
- optional local auth/admin protection is satisfied.

Frontend must never decide that publishing is allowed by itself. It only shows backend state.

### 5.10 Run detail

`GET /api/v1/runs/{runId}`

Response:

```json
{
  "id": "run-20260630-090000",
  "queueItemId": "tweet-0001",
  "mode": "dry_run",
  "status": "completed",
  "startedAt": "2026-06-30T09:00:00Z",
  "finishedAt": "2026-06-30T09:00:02Z",
  "message": "Dry run: posting skipped",
  "logs": [
    {
      "level": "INFO",
      "time": "2026-06-30T09:00:01Z",
      "message": "Dry run: posting skipped"
    }
  ],
  "artifacts": []
}
```

### 5.11 Artifacts

`GET /api/v1/artifacts`

Назначение: безопасный индекс runtime-артефактов.

Query params:

- `type`: `log`, `screenshot`, `trace`;
- `limit`: default `50`.

Response:

```json
{
  "items": [
    {
      "id": "log-error",
      "type": "log",
      "name": "error.log",
      "sizeBytes": 1024,
      "createdAt": "2026-06-30T09:00:00Z",
      "downloadUrl": "/api/v1/artifacts/log-error/download"
    }
  ]
}
```

`GET /api/v1/artifacts/{artifactId}/download`

Rules:

- artifact ID must map to a backend-owned allowlisted directory;
- no path traversal;
- no arbitrary file path parameter;
- `auth.json`, `.env`, source files, and lockfiles are never downloadable through this endpoint.

## 6. Data model

### QueueItem

```ts
type QueueItemStatus =
  | "queued"
  | "draft"
  | "blocked"
  | "posted"
  | "failed"
  | "dry_run_completed";

type QueueItemRisk = "low" | "medium" | "high";

interface QueueItem {
  id: string;
  text: string;
  textLength: number;
  status: QueueItemStatus;
  risk: QueueItemRisk;
  source: string;
  createdAt: string | null;
  scheduledFor: string | null;
}
```

### Run

```ts
type RunMode = "dry_run" | "publish";
type RunStatus = "queued" | "running" | "completed" | "failed" | "cancelled" | "blocked";

interface Run {
  id: string;
  queueItemId: string;
  mode: RunMode;
  status: RunStatus;
  startedAt: string | null;
  finishedAt: string | null;
  message: string | null;
  artifacts: Artifact[];
}
```

### Artifact

```ts
type ArtifactType = "log" | "screenshot" | "trace";

interface Artifact {
  id: string;
  type: ArtifactType;
  name: string;
  sizeBytes: number;
  createdAt: string | null;
  downloadUrl: string;
}
```

## 7. Frontend integration plan

### Phase 1: API client and read-only dashboard

Create:

```text
frontend/src/api/client.js
frontend/src/api/types.js
```

Responsibilities:

- read `import.meta.env.VITE_API_BASE_URL`;
- wrap `fetch`;
- normalize API errors;
- expose functions:
  - `getHealth()`;
  - `getSettings()`;
  - `getQueue()`;
  - `getRuns()`;
  - `getArtifacts()`.

UI changes:

- replace hardcoded `posts` with `GET /queue`;
- replace dashboard counters with derived values from API data;
- show loading, empty, and error states.

### Phase 2: Validation and dry-run actions

Add UI actions:

- validate text through `POST /queue/validate`;
- trigger dry-run through `POST /runs/dry-run`;
- poll `GET /runs/{runId}` until terminal status.

Polling interval:

- `1000ms` while run is `queued` or `running`;
- stop on `completed`, `failed`, `blocked`, or `cancelled`.

### Phase 3: Artifact browsing

Add UI sections:

- latest logs;
- latest screenshots;
- latest traces;
- download links through allowlisted artifact endpoint.

### Phase 4: Publish action

Only after Phases 1-3 are stable.

Frontend behavior:

- show publish button only when `settings.postingEnabled === true` and `settings.dryRun === false`;
- require explicit user confirmation modal;
- call `POST /runs/publish`;
- treat backend rejection as final.

Backend behavior:

- enforce all gates;
- allow only one active publish job at a time;
- write auditable run record.

## 8. Backend implementation plan

### Phase 1: API skeleton

Add dependencies:

```text
fastapi
uvicorn[standard]
```

Add `src/api/app.py`:

- create `FastAPI(title="X Stealth AutoPoster API")`;
- configure CORS for local Vite origin `http://127.0.0.1:5173`;
- include routers under `/api/v1`.

Development command:

```powershell
uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

### Phase 2: Read-only services

Implement:

- `queue_service.list_items()` using `FileTweetSource` parsing rules;
- `settings_service.get_public_settings()`;
- `artifact_service.list_artifacts()` with path allowlist.

### Phase 3: Run registry

MVP storage:

```text
backend/data/runs.jsonl
```

Each line is a JSON object with run metadata.

Rules:

- append-only for auditability;
- write one line on start;
- write one line on completion/update or store current state in a separate `runs_state.json`;
- never store secrets or full environment.

### Phase 4: Job execution

For MVP, run jobs in-process with an `asyncio.Task` registry.

Constraints:

- one active publish job maximum;
- dry-run jobs may be short and synchronous;
- errors are mapped to stable API error codes.

Future production option:

- external worker process;
- SQLite/Postgres run store;
- queue system.

## 9. Error format

All API errors should use one envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Tweet text exceeds 280 characters.",
    "details": {
      "field": "text",
      "maxLength": 280
    }
  }
}
```

Common codes:

- `VALIDATION_ERROR`;
- `NOT_FOUND`;
- `POSTING_DISABLED`;
- `AUTH_STATE_MISSING`;
- `RUN_ALREADY_ACTIVE`;
- `ARTIFACT_NOT_ALLOWED`;
- `INTERNAL_ERROR`.

## 10. CORS and deployment

Development:

- frontend: `http://127.0.0.1:5173`;
- backend API: `http://127.0.0.1:8000`;
- backend CORS allowlist includes only the Vite dev origin.

Production option A:

- backend serves built frontend static files from `frontend/dist`;
- same origin, no CORS needed.

Production option B:

- frontend and backend are separate services;
- configure explicit allowed origin;
- do not use wildcard CORS with credentials.

## 11. Security requirements

- Never return `.env`, `auth.json`, proxy credentials, cookies, or raw browser storage.
- Never allow arbitrary file reads through artifact endpoints.
- Publish action must be backend-gated by config, not frontend-gated only.
- API must default to read-only/dry-run behavior.
- Add request size limits for post text endpoints.
- Log actions with run IDs, but do not log secrets.
- If exposed beyond localhost, add authentication before enabling write endpoints.

## 12. Acceptance criteria

Integration is complete when:

- `GET /api/v1/health` returns `ok`;
- dashboard loads queue data from backend, not hardcoded arrays;
- dashboard shows public settings and whether publishing is enabled;
- dashboard can trigger dry-run and display run result;
- artifacts list is visible without exposing sensitive files;
- `npm run build` succeeds;
- `python -m compileall src` succeeds;
- publish endpoint refuses requests while `DRY_RUN=true` or `POSTING_ENABLED=false`;
- all API errors use the agreed error envelope.

## 13. Open decisions

- Whether queue storage remains `data/tweets.txt` or moves to SQLite.
- Whether frontend should support editing/scheduling in MVP or only read-only queue plus dry-run.
- Whether production should serve frontend through backend or as a separate static service.
- Whether auth is needed immediately or only before exposing beyond localhost.
