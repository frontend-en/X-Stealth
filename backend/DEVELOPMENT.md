# Development

## Local setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium
cp ../.env.example ../.env
```

On Windows PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium
Copy-Item ..\.env.example ..\.env
```

## Running

The default mode is safe dry-run mode:

```bash
python -m src.main
```

## API server

The React dashboard talks to the backend through the local API:

```bash
python -m uvicorn src.api.app:app --host 127.0.0.1 --port 8000 --reload
```

The frontend expects:

```dotenv
VITE_API_BASE_URL=http://127.0.0.1:8000
```

The API exposes only public runtime state. It does not expose `.env`,
`auth.json`, proxy credentials, or arbitrary files.

To publish for an account you own, create `auth.json` from a logged-in Playwright
session and set both:

```dotenv
DRY_RUN=false
POSTING_ENABLED=true
```

## Docker

Run Docker commands from the project root:

```bash
make local-build
make local-up
```

The compose file starts the API and dashboard, reads the root `.env` when it
exists, and mounts `backend/data/`, `backend/logs/`, `backend/screenshots/`,
`backend/traces/`, and `backend/auth.json`. Logs are written to stdout,
`backend/logs/bot.log`, and `backend/logs/error.log`.

To run the standalone bot entry point instead of using the dashboard API:

```bash
make local-bot
```

Production commands use `.env.prod` and a separate Compose project name:

```bash
make env-prod
make prod-config
make prod-build
make prod-up
```

## Safety notes

This implementation intentionally avoids fingerprint spoofing and stealth
patches. Keep posting frequency low, respect platform rules, and monitor
`logs/error.log`.
