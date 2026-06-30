# Agent Rules

- Keep `DRY_RUN=true`, `POSTING_ENABLED=false`, and `HEADLESS=true` as development defaults.
- Never request or expose `.env`, `auth.json`, cookies, proxy credentials, or raw browser storage.
- Do not create changes that increase evasion, spam, policy-bypass, or platform-abuse behavior.
- Prefer draft quality, validation, observability, auditability, and dry-run testability.
- Treat publishing as a gated action requiring backend permission and explicit operator approval.
