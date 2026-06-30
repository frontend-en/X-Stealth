# X Stealth AutoPoster — Финальная Спецификация v1.1 (Production-Ready)

**Дата:** 2026-06-26  
**Статус:** Финальная версия с лучшими практиками  
**Цель:** Стабильный, низко-детектируемый автопостинг в X.com через Playwright

---

## 1. Миссия и Принципы

### Главная цель
Создать **надёжную, трудно детектируемую систему автопостинга** в X.com полностью через браузерную автоматизацию.

### Основные принципы (не нарушать)
- **Stealth-first** — всё подчинено снижению риска бана.
- **Human-like behavior** — приоритет №1 (Bézier mouse, fatigue typing, микро-паузы, overshoot).
- **Low volume + High variance** — мало постов, максимальная вариативность.
- **Observable** — отличные логи, скриншоты, traces.
- **Spec-driven** — сначала спецификация, потом код.
- **Clean Architecture** + separation of concerns.
- **Security & Reliability** в Docker (non-root, resource limits, healthchecks).

**Золотое правило:** Если поведение выглядит неестественно даже для внимательного человека — оно будет детектироваться X.

---

## 2. Архитектура (4 слоя защиты)

| Слой | Модуль                  | Что делает |
|------|-------------------------|----------|
| 1    | `playwright-stealth`    | Базовые fingerprint патчи |
| 2    | `src/stealth.py`        | Дополнительные патчи (WebGL, Canvas noise, AudioContext, hardware) |
| 3    | `src/human_actions.py`  | Продвинутое человеческое поведение (Bézier mouse + fatigue typing) |
| 4    | `src/x_bot.py`          | Warm-up сессии + правильный flow постинга + error handling |

---

## 3. Финальная Структура Проекта

```
x-stealth-autoposter/
├── src/
│   ├── logging_config.py     # loguru: console + bot.log + error.log
│   ├── stealth.py            # Доп. fingerprint патчи + create_stealth_context
│   ├── human_actions.py      # Bézier mouse, fatigue typing, natural scroll
│   ├── x_bot.py              # Главный класс бота (warm_up, post_tweet, error handling)
│   ├── config.py             # Pydantic-settings
│   ├── tweet_source.py       # Абстракция источника твитов
│   └── main.py               # Entry point
├── data/
│   └── tweets.txt
├── logs/                     # bot.log + error.log (ротация)
├── screenshots/
├── traces/
├── auth.json                 # (в .gitignore)
├── Dockerfile                # Production-ready (non-root, healthcheck)
├── docker-compose.yml        # С resource limits и логированием
├── requirements.txt
├── DEVELOPMENT.md
├── SPECIFICATION.md          # Этот файл
└── .env.example
```

---

## 4. Ключевые Модули (Спецификация)

### 4.1 `src/logging_config.py`
- loguru с тремя хендлерами: stdout, `bot.log`, `error.log`
- Ротация + сжатие
- Поддержка `logger.bind()` для контекста

### 4.2 `src/stealth.py`
- `apply_extra_stealth(context)`
- `create_stealth_context(...)`
- WebGL spoofing, Canvas noise, AudioContext, hardware properties

### 4.3 `src/human_actions.py`
- `human_mouse_move()` — **обязательно** через Bézier curves + overshoot
- `human_type()` — fatigue + случайные ошибки + микро-паузы
- `human_scroll()`, `random_micro_actions()`, `random_delay()`

### 4.4 `src/x_bot.py` (самый важный)
Обязательные методы:
- `warm_up_session()` — перед каждым постом (скролл + просмотр твитов)
- `post_tweet(text)` — с полным человеческим flow + проверкой результата
- `handle_x_errors()` — распознавание rate limit, "something went wrong" и т.д.
- Использование `tenacity` для retry

### 4.5 Конфигурация
- `pydantic-settings`
- Все задержки, вероятности, viewport — через конфиг

---

## 5. Среда Разработки и Deployment (Best Practices)

### 5.1 Рекомендуемый Workflow

| Этап                    | Среда             | Инструмент          |
|-------------------------|-------------------|---------------------|
| Разработка + отладка    | Локально          | `.venv` + headed    |
| Проверка                | Локально          | `docker compose`    |
| Продакшен               | VPS / сервер      | Docker              |

### 5.2 Локальная разработка
```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
```

### 5.3 Production Deployment (Docker)

**Dockerfile** — non-root user, healthcheck, минимальный образ.

**docker-compose.yml**:
- `restart: unless-stopped`
- Resource limits (CPU/Memory)
- JSON logging driver с ротацией
- Монтирование `auth.json`, `logs/`, `screenshots/`, `data/`

**Запуск в проде:**
```bash
docker compose up -d
docker compose logs -f
```

**Healthcheck** встроен в Dockerfile.

### 5.4 Логирование в проде
- `logs/bot.log` + `logs/error.log` внутри контейнера (монтируются)
- Также вывод в stdout (json-file driver)

---

## 6. Лучшие Практики (Обязательны)

### Stealth & Behavior
- Всегда использовать `human_mouse_move()` и `human_type()`
- Обязательный `warm_up_session()` перед постом
- Высокая вариативность задержек и поведения
- Никогда не использовать фиксированные `time.sleep()`

### Код
- Type hints + docstrings
- Structured logging через loguru
- При любой ошибке — скриншот + подробный лог
- Separation of concerns (stealth / behavior / bot logic)

### Docker & Security
- Non-root user
- Resource limits
- Healthcheck
- Не коммитить `auth.json` и `.env`

### Операции
- Низкая частота постинга на старте (1 пост в несколько часов)
- Мониторинг `error.log`
- При первых признаках проблем — останавливать бота

---

## 7. Риски и Правила Безопасности

- Даже лучший stealth не даёт 100% защиты.
- Начинай с минимальной частоты.
- Aged аккаунт + residential proxy = значительно выше выживаемость.
- Веди историю запусков и результатов.

---

## 8. Дорожная Карта (Спринты)

**Спринт 1 (текущий):** Финальный E2E на тестовом аккаунте
- Интеграция всех модулей
- `x_bot.py` с warm-up и error handling
- Логирование + скриншоты
- Docker production-ready

**Спринт 2:** Стабильность и конфигурация
- `config.py` + pydantic
- Умный retry + обработка X-ошибок
- `tweet_source.py` как абстракция

**Спринт 3:** Операции
- Планировщик с случайными интервалами
- Защита от дубликатов
- Улучшенный мониторинг

**Спринт 4+:** Масштабирование
- Residential proxies
- Multi-account (осторожно)
- Интеграция с AI-генерацией

---

**Это финальная спецификация.**  
Всё остальное (код, Docker, логирование) должно соответствовать ей.

Готов приступать к реализации `x_bot.py` и финальной сборке проекта.
