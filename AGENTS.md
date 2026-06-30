# AGENTS.md

## Project Map

- `backend/` contains the Python Playwright app.
- `backend/src/` contains runtime code: configuration, logging, tweet source, human-action helpers, and bot orchestration.
- `backend/data/`, `backend/logs/`, `backend/screenshots/`, and `backend/traces/` are runtime state and artifacts.
- `frontend/` contains the Vite React dashboard.

## Development Commands

Run backend commands from `backend/`:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item ..\.env.example ..\.env
python -m src.main
```

Run frontend commands from `frontend/`:

```powershell
npm install
npm run dev
npm run build
```

Docker verification, when Docker is available:

```powershell
make verify
make local-build
```

## Safety And Scope

- Keep development defaults safe: `DRY_RUN=true`, `POSTING_ENABLED=false`, and `HEADLESS=true` unless the user explicitly asks for a local owned-account run.
- Do not commit or expose `backend/auth.json`, `.env` files, logs, screenshots, traces, virtual environments, or `node_modules`.
- Treat `backend/auth.json` as sensitive session state.
- Avoid changes that increase evasion, spam, policy-bypass, or platform-abuse behavior. Prefer observability, reliability, configuration hygiene, and dry-run testability.
- Do not edit generated caches such as `__pycache__/`, `frontend/dist/`, logs, traces, or screenshots unless the user is explicitly asking to inspect or clean artifacts.

## Coding Conventions

- Preserve the existing small-module Python structure and keep side effects inside entry points or explicit runtime methods.
- Use typed Python and Pydantic settings for new backend configuration.
- Use structured Loguru logging for backend behavior that may fail in production.
- Keep frontend changes consistent with the existing Vite React setup and `lucide-react` icon usage.
- Prefer focused changes over broad rewrites.

## Verification

- For backend-only changes, at minimum run `python -m compileall src` from `backend/`.
- For frontend changes, run `npm run build` from `frontend/`.
- For behavior that touches Docker packaging, run `make verify` and `make local-build` from the project root when Docker is available.
- Report any verification command that could not be run and why.
