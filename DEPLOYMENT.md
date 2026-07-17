# Production deployment

This project is designed for a Linux host with Docker Engine and the Docker
Compose plugin. The dashboard is exposed on `FRONTEND_PORT`; Nginx proxies
`/api/*` to the API container. The API port is bound only to the server's
loopback interface by default.

## First deployment

From the computer that has the private SSH key authorised on the VPS, you can
upload the source and start both the frontend and API in one command:

```sh
make prod-first-deploy VPS_HOST=YOUR_SERVER_IP VPS_USER=root
```

For a non-standard SSH port or key file, add `VPS_PORT=2222` and/or
`VPS_SSH_KEY=/path/to/private_key`. The command transfers source over SSH,
creates `/opt/x-stealth-autoposter` by default, and runs the production build
there. It deliberately never uploads or overwrites `.env.prod` or
`backend/auth.json`; the first run creates safe defaults and an empty
restricted `auth.json` on the VPS.

Before enabling any owned-account bot run, connect to the VPS yourself and
place its session state in `backend/auth.json`. Do not copy it through Git.

Alternatively, deploy manually:

1. Clone the repository on the server and change into its directory.
2. Create the production environment file:

   ```sh
   make env-prod
   ```

3. Edit `.env.prod`. Keep `DRY_RUN=true`, `POSTING_ENABLED=false`, and
   `HEADLESS=true` until an owned-account dry run has been verified. Leave
   `VITE_API_BASE_URL` empty when using this Compose stack.
4. Place the owned-account Playwright session state at `backend/auth.json`.
   This file is not committed and must be readable by Docker. Do not copy it
   through source control.
5. Build, validate, and start the stack:

   ```sh
   make prod-config
   make prod-build
   make prod-up
   make prod-ps
   make prod-health
   ```

The dashboard will be available at `http://SERVER_IP:${FRONTEND_PORT}`.
For a public deployment, terminate TLS in a reverse proxy in front of the
dashboard and expose only ports 80/443. Do not expose `API_PORT` publicly.

## Updating

```sh
git pull
make prod-build
make prod-up
make prod-health
```

Use `make prod-logs` to inspect logs. The production Compose file rotates
container logs; runtime artifacts remain under `backend/` and are ignored by
Git.
