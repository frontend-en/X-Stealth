# Спецификация внедрения Agent Harness

Дата: 2026-06-30  
Статус: проектный контракт для реализации  
Область: `backend/` Python FastAPI/Playwright app, `frontend/` Vite React dashboard

## 1. Цель

Внедрить собственный Agent Harness - безопасный управляющий слой, через который агент сможет работать с приложением без прямого доступа к Playwright, session state, секретам и файловой системе.

Agent Harness должен позволять агенту:

- читать очередь публикаций;
- предлагать текстовые черновики;
- валидировать текст до постановки в очередь;
- сохранять черновики в управляемое хранилище;
- запускать dry-run;
- читать статусы запусков и runtime-артефакты;
- инициировать publish только через явный backend-gated approval flow.

Главный принцип: агент управляет намерениями и черновиками, backend остается единственным слоем исполнения, безопасности, аудита и публикации.

## 2. Текущий контекст

Backend уже содержит основные элементы runtime-контура:

- `src/api/app.py` - FastAPI API для dashboard;
- `src/services/queue_service.py` - read-only очередь из `data/tweets.txt`;
- `src/services/run_service.py` - dry-run/publish registry на `data/runs.jsonl`;
- `src/x_bot.py` - Playwright workflow публикации;
- `src/services/artifact_service.py` - allowlisted доступ к логам, screenshots и traces;
- `src/config.py` - Pydantic settings с безопасными default-значениями.

Ограничения текущей реализации:

- `POST /api/v1/queue` возвращает `501`, поэтому агенту некуда безопасно сохранять черновики;
- очередь построена вокруг plain text файла и не хранит состояние элементов;
- dry-run сейчас является валидационным событием, а не полноценным агентским rehearsal flow;
- `RunService` напрямую создает `XBot`, что усложняет тестирование agent harness без браузера;
- отсутствует отдельный audit trail действий агента.

## 3. Non-Goals

В рамках Agent Harness запрещено реализовывать или расширять:

- механики обхода антибот-защит, fingerprinting, stealth или detection evasion;
- multi-account orchestration;
- proxy rotation или управление прокси;
- автоматическое массовое создание контента без review;
- автоматическую публикацию без явного backend-side разрешения;
- доступ агента к `auth.json`, `.env`, cookies, raw browser storage, logs/traces как произвольным файлам.

## 4. Целевая архитектура

```text
Agent / UI / CLI
      |
      v
Agent Harness API
      |
      v
AgentHarness service
      |
      +--> AgentPolicy
      +--> QueueService
      +--> RunService
      +--> ArtifactService
      +--> Publisher interface
              |
              +--> FakePublisher
              +--> DryRunPublisher
              +--> XPublisher -> XBot
```

Agent Harness должен быть отдельным слоем поверх существующих сервисов. Он не должен импортировать Playwright напрямую и не должен вызывать методы `Page`, `Browser`, `Context` или helpers из `human_actions.py`.

## 5. Новая структура файлов

Рекомендуемая структура:

```text
agent/
  config/
    role.md           # кто агент и какова его зона ответственности
    rules.md          # рабочие правила, ограничения, safety policy
    examples.md       # хорошие примеры действий, ответов и черновиков
  memory/
    context.md        # важный долгоживущий контекст проекта
    history.md        # что уже происходило и какие решения приняты
    mistakes.md       # известные ошибки и что нужно исправлять

backend/src/agent/
  __init__.py
  harness.py          # сценарии агента и orchestration
  schemas.py          # DTO для agent API
  policy.py           # safety gates и разрешения действий
  events.py           # audit event model/write path

backend/src/publishers/
  __init__.py
  base.py             # Publisher protocol
  fake.py             # тестовый publisher
  dry_run.py          # dry-run publisher
  x_publisher.py      # adapter around XBot
```

Дополнить существующие модули:

```text
backend/src/services/queue_service.py
backend/src/services/run_service.py
backend/src/api/app.py
backend/src/api/schemas.py
```

`agent/` на уровне корня проекта является конфигурационным и memory-слоем для агента. `backend/src/agent/` является runtime-слоем, который читает этот контекст, применяет policy и вызывает backend services.

## 5.1 Agent Workspace Files

Agent Harness должен поддерживать контролируемый агентский workspace:

```text
agent/config/role.md
agent/config/rules.md
agent/config/examples.md
agent/memory/context.md
agent/memory/history.md
agent/memory/mistakes.md
```

Назначение файлов:

- `role.md` - описывает роль агента, допустимые задачи и границы ответственности;
- `rules.md` - содержит обязательные правила поведения, безопасности и стиля работы;
- `examples.md` - содержит эталонные примеры хороших черновиков, dry-run flows и отказов;
- `context.md` - хранит стабильный контекст проекта, который агент должен учитывать;
- `history.md` - фиксирует важные события, решения и изменения;
- `mistakes.md` - фиксирует повторяющиеся ошибки, запрещенные паттерны и corrective actions.

Эти файлы должны быть обычными Markdown-файлами, читаемыми человеком. Агент может читать их через Agent Harness, но запись в `memory/` должна проходить через backend-controlled append/update methods с audit event.

Sensitive data запрещено хранить в agent workspace:

- `.env`;
- `auth.json`;
- cookies;
- proxy credentials;
- access tokens;
- raw logs, screenshots или traces;
- персональные данные, не нужные для работы приложения.

## 5.2 Agent Context Assembly

Добавить сервис сборки контекста:

```text
backend/src/agent/context_loader.py
```

Responsibilities:

- читать allowlisted файлы из `agent/config/` и `agent/memory/`;
- ограничивать размер загружаемого контекста;
- возвращать structured context для agent route/service;
- игнорировать отсутствующие optional files без падения;
- логировать, какие context sections были использованы, без записи полного содержимого в runtime logs.

Пример DTO:

```python
class AgentContext(BaseModel):
    role: str = ""
    rules: str = ""
    examples: str = ""
    memoryContext: str = ""
    memoryHistory: str = ""
    memoryMistakes: str = ""
```

## 5.3 Agent Route Responsibility

Для frontend-oriented архитектуры route должен выполнять три действия:

```text
collect context -> call agent/model adapter -> persist result
```

В текущем FastAPI backend аналогом `/app/api/agent/route.ts` должен быть:

```text
backend/src/api/routes/agent.py
```

или, если проект остается с single-file API:

```text
backend/src/api/app.py
```

Но даже при single-file API бизнес-логика должна жить не в route handler, а в:

```text
backend/src/agent/harness.py
backend/src/agent/context_loader.py
backend/src/agent/events.py
```

## 6. Agent Harness Responsibilities

`AgentHarness` должен предоставлять высокоуровневые команды:

```python
class AgentHarness:
    def get_capabilities(self) -> AgentCapabilities: ...
    def list_queue(self, limit: int = 50, offset: int = 0) -> QueueListResponse: ...
    def propose_post(self, request: ProposePostRequest) -> DraftProposal: ...
    def validate_post(self, text: str) -> ValidationResult: ...
    def create_draft(self, request: CreateAgentDraftRequest) -> QueueItem: ...
    def start_dry_run(self, queue_item_id: str) -> RunRecord: ...
    def get_run(self, run_id: str) -> RunDetail | None: ...
    def list_artifacts(self, limit: int = 50) -> ArtifactListResponse: ...
    def request_publish(self, request: AgentPublishRequest) -> AgentPublishDecision: ...
```

В MVP `propose_post` может быть deterministic/no-LLM методом, который принимает готовый текст от внешнего агента и возвращает нормализованный draft proposal с validation result. Если LLM будет подключаться позже, подключение должно быть отдельным adapter-слоем и не должно смешиваться с runtime-публикацией.

## 7. Queue Storage

### 7.1 Проблема

Текущий `data/tweets.txt` удобен для ручного списка, но плохо подходит для агента:

- нет стабильного состояния элемента;
- нельзя хранить draft/reviewed/blocked/posting history;
- невозможно безопасно дописывать элементы без риска повредить формат;
- нет metadata: author, source, timestamps, validation, agent trace.

### 7.2 MVP-хранилище

Ввести `backend/data/queue.jsonl`.

Каждая строка - один `QueueRecord`:

```json
{
  "id": "queue-20260630-143000-000001",
  "text": "Example post",
  "status": "draft",
  "risk": "low",
  "source": "agent",
  "createdAt": "2026-06-30T14:30:00Z",
  "updatedAt": "2026-06-30T14:30:00Z",
  "scheduledFor": null,
  "validation": {
    "valid": true,
    "textLength": 12,
    "errors": [],
    "warnings": []
  },
  "metadata": {
    "createdBy": "agent",
    "promptId": null,
    "reviewRequired": true
  }
}
```

`tweets.txt` можно сохранить как legacy read-only source. `QueueService` должен уметь читать оба источника, но новые agent drafts должны писаться только в `queue.jsonl`.

### 7.3 Production-хранилище

После MVP рекомендуется перейти на SQLite:

- `queue_items`;
- `runs`;
- `agent_events`;
- `artifacts_index` опционально.

SQLite даст атомарные updates, индексы, миграции и более чистый audit trail.

## 8. Publisher Interface

`RunService` не должен напрямую зависеть от `XBot`. Вместо этого нужен protocol:

```python
class Publisher(Protocol):
    async def publish_once(self, text: str) -> PublishResult: ...
```

Реализации:

- `FakePublisher` - всегда возвращает controlled result для тестов;
- `DryRunPublisher` - валидирует и пишет rehearsal result без браузера;
- `XPublisher` - адаптер вокруг `XBot(settings).run_once(text)`.

Это позволит тестировать Agent Harness без Playwright и без реального аккаунта.

## 9. Agent Policy

Создать `AgentPolicy`, который централизует разрешения:

```python
class AgentPolicy:
    def can_create_draft(self, text: str) -> PolicyDecision: ...
    def can_start_dry_run(self, queue_item: QueueItem) -> PolicyDecision: ...
    def can_request_publish(self, queue_item: QueueItem) -> PolicyDecision: ...
```

Минимальные правила:

- пустой текст блокируется;
- текст длиннее 280 символов блокируется;
- control characters блокируются;
- publish запрещен при `DRY_RUN=true`;
- publish запрещен при `POSTING_ENABLED=false`;
- publish запрещен без `auth.json`;
- publish запрещен без explicit confirm;
- publish запрещен, если уже есть активный publish run;
- publish запрещен для элемента без успешного dry-run после последнего изменения текста.

## 10. API Contract

Добавить endpoints под `/api/v1/agent`.

### 10.1 Capabilities

`GET /api/v1/agent/capabilities`

Response:

```json
{
  "canCreateDraft": true,
  "canDryRun": true,
  "canPublish": false,
  "publishBlockedReason": "Publishing is disabled by backend configuration.",
  "queueStorage": "jsonl",
  "requiresHumanApprovalForPublish": true
}
```

### 10.2 Propose Post

`POST /api/v1/agent/proposals`

Request:

```json
{
  "text": "Draft text from agent",
  "sourcePrompt": "Optional short source description"
}
```

Response:

```json
{
  "proposalId": "proposal-20260630-143000-000001",
  "text": "Draft text from agent",
  "validation": {
    "valid": true,
    "textLength": 21,
    "errors": [],
    "warnings": []
  },
  "recommendedAction": "create_draft"
}
```

### 10.3 Create Draft

`POST /api/v1/agent/drafts`

Request:

```json
{
  "text": "Draft text from agent",
  "sourcePrompt": "Optional short source description",
  "reviewRequired": true
}
```

Response:

```json
{
  "id": "queue-20260630-143000-000001",
  "status": "draft",
  "validation": {
    "valid": true,
    "textLength": 21,
    "errors": [],
    "warnings": []
  }
}
```

### 10.4 Start Agent Dry Run

`POST /api/v1/agent/runs/dry-run`

Request:

```json
{
  "queueItemId": "queue-20260630-143000-000001"
}
```

Response:

```json
{
  "runId": "run-20260630-143500-000001",
  "status": "completed"
}
```

### 10.5 Request Publish

`POST /api/v1/agent/runs/publish-request`

Request:

```json
{
  "queueItemId": "queue-20260630-143000-000001",
  "confirm": true,
  "approvalNote": "Approved by local operator"
}
```

Response when blocked:

```json
{
  "allowed": false,
  "reason": "Publishing is disabled by backend configuration.",
  "requiredActions": ["set POSTING_ENABLED=true", "set DRY_RUN=false"]
}
```

Response when accepted:

```json
{
  "allowed": true,
  "runId": "run-20260630-144000-000001",
  "status": "queued"
}
```

## 11. Audit Events

Создать append-only файл `backend/data/agent_events.jsonl`.

События:

- `proposal_created`;
- `draft_created`;
- `validation_failed`;
- `dry_run_requested`;
- `dry_run_completed`;
- `publish_requested`;
- `publish_blocked`;
- `publish_started`;
- `publish_completed`;
- `publish_failed`.

Пример:

```json
{
  "id": "event-20260630-143000-000001",
  "type": "draft_created",
  "time": "2026-06-30T14:30:00Z",
  "actor": "agent",
  "queueItemId": "queue-20260630-143000-000001",
  "runId": null,
  "message": "Agent draft created.",
  "details": {
    "textLength": 21,
    "reviewRequired": true
  }
}
```

События не должны содержать секреты, cookies, proxy URL, raw `.env` или содержимое `auth.json`.

## 12. Frontend Integration

Добавить в dashboard отдельную область Agent Harness:

- список capabilities;
- форма/панель agent draft proposal;
- validation result до сохранения;
- кнопка create draft;
- кнопка dry-run для draft items;
- publish request button только если backend capabilities позволяют;
- отображение agent events.

Frontend не должен самостоятельно решать, разрешен ли publish. Он только отображает backend decision.

## 13. Configuration

Добавить settings:

```python
agent_enabled: bool = True
agent_queue_path: Path = Path("data/queue.jsonl")
agent_events_path: Path = Path("data/agent_events.jsonl")
agent_publish_requires_approval: bool = True
agent_require_successful_dry_run_before_publish: bool = True
```

Default-значения должны оставаться безопасными:

```dotenv
DRY_RUN=true
POSTING_ENABLED=false
AGENT_ENABLED=true
AGENT_PUBLISH_REQUIRES_APPROVAL=true
AGENT_REQUIRE_SUCCESSFUL_DRY_RUN_BEFORE_PUBLISH=true
```

## 14. Error Model

Все agent endpoints должны использовать существующий error envelope:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Post text exceeds 280 characters.",
    "details": {
      "field": "text",
      "maxLength": 280
    }
  }
}
```

Новые коды:

- `AGENT_DISABLED`;
- `POLICY_BLOCKED`;
- `DRAFT_NOT_FOUND`;
- `DRY_RUN_REQUIRED`;
- `APPROVAL_REQUIRED`;
- `PUBLISH_NOT_ALLOWED`.

## 15. Implementation Plan

### Phase 1 - Storage and Queue Write Path

- Добавить `QueueRecord` schema.
- Реализовать `queue.jsonl` append/update path.
- Реализовать `POST /api/v1/queue`.
- Сохранить чтение legacy `tweets.txt`.
- Добавить unit tests для create/list/get/update.

### Phase 2 - Publisher Abstraction

- Добавить `Publisher` protocol.
- Добавить `FakePublisher`, `DryRunPublisher`, `XPublisher`.
- Обновить `RunService`, чтобы dependency-инжектить publisher.
- Сохранить текущее поведение publish через `XBot`.

### Phase 3 - Agent Harness Service

- Добавить `backend/src/agent`.
- Реализовать `AgentPolicy`.
- Реализовать `AgentHarness`.
- Добавить audit events.
- Покрыть тестами policy decisions и happy-path draft -> dry-run.

### Phase 4 - Agent API

- Добавить `/api/v1/agent/capabilities`.
- Добавить `/api/v1/agent/proposals`.
- Добавить `/api/v1/agent/drafts`.
- Добавить `/api/v1/agent/runs/dry-run`.
- Добавить `/api/v1/agent/runs/publish-request`.

### Phase 5 - Frontend

- Добавить API client methods.
- Добавить Agent Harness panel.
- Отобразить capabilities, validation, draft creation, dry-run result.
- Publish UI оставить disabled/hidden, пока backend не разрешает.

### Phase 6 - Hardening

- Добавить auth requirement, если API доступен не только на localhost.
- Добавить request size limits.
- Добавить file locking или SQLite migration.
- Добавить structured logs с `runId`, `queueItemId`, `eventId`.

## 16. Verification

Backend:

```powershell
cd backend
python -m compileall src
```

Frontend:

```powershell
cd frontend
npm run build
```

API smoke test:

```powershell
cd backend
uvicorn src.api.app:app --host 127.0.0.1 --port 8000
```

Проверить:

- `GET /api/v1/health`;
- `GET /api/v1/agent/capabilities`;
- `POST /api/v1/agent/proposals`;
- `POST /api/v1/agent/drafts`;
- `POST /api/v1/agent/runs/dry-run`;
- publish request возвращает blocked при `DRY_RUN=true` или `POSTING_ENABLED=false`.

## 17. Acceptance Criteria

Реализация считается завершенной, когда:

- агент может создать draft без прямого изменения файлов;
- каждый draft проходит backend validation;
- dry-run создает auditable run record;
- все действия агента пишутся в `agent_events.jsonl`;
- publish невозможен при безопасных default-настройках;
- publish невозможен без explicit confirm;
- publish невозможен без успешного dry-run после последнего изменения текста;
- `auth.json`, `.env`, logs, screenshots и traces не доступны агенту как произвольные файлы;
- frontend показывает capabilities и не включает publish UI без backend permission;
- `python -m compileall src` проходит;
- `npm run build` проходит.

## 18. Recommended MVP

Минимальный полезный инкремент:

```text
Agent text -> validate -> create draft in queue.jsonl -> dry-run -> run record -> audit event -> dashboard display
```

Publish flow следует реализовывать только после стабилизации MVP и только как backend-gated действие с явным подтверждением локального оператора.
