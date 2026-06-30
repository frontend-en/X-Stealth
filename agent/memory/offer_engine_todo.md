# Offer Engine Architecture TODO

Goal: evolve the existing X AutoPoster into a controlled offer-posting engine:
draft posts enter a rich queue, dry-run and quality checks happen first, the
operator approves 1-2 best posts per day, publishing stays backend-gated, and
funnel logs make clicks, leads, and sales measurable later.

## MVP Order

1. Extend the queue model.
2. Add pillars and CTA config.
3. Add validator plus quality gate.
4. Make dry-run produce `dry_run_passed`.
5. Add approve, skip, and reject flow.
6. Block publish unless the post is approved.
7. Add UTM builder and `posts.jsonl`.
8. Update the dashboard.

## Detailed Tasks

1. Decide on storage: prefer extending existing `backend/data/queue.jsonl`
   instead of creating a separate `tweets.json`, because QueueService already
   uses JSONL.
2. Extend queue item fields: `pillar`, `content`, `ctaType`, `targetUrl`,
   `utmCampaign`, `utmContent`, `qualityScore`, `approvedAt`, `postedAt`,
   `dryRunId`, and `notes`.
3. Add config files:
   - `backend/config/pillars.json`
   - `backend/config/cta_templates.json`
4. Hard-code the five default pillars in config:
   - `cases`
   - `errors`
   - `breakdowns`
   - `mini_guides`
   - `personal_experience`
5. Update `backend/src/api/schemas.py` with expanded queue fields, pillar/CTA
   types, UTM fields, and statuses such as `dry_run_passed`, `approved`,
   `skipped`, and `rejected`.
6. Update `backend/src/services/queue_service.py` to read and write expanded
   JSONL queue records while preserving legacy `tweets.txt` reading.
7. Add queue mutation methods: `approve_item`, `skip_item`, `reject_item`,
   `update_item`, and `mark_posted`.
8. Add `backend/src/services/quality_service.py` for Quality Gate checks:
   non-empty text, <= 280 chars, valid pillar, CTA present, target URL present,
   UTM data present or derivable, rough duplicate detection, and basic
   "value before sale" heuristics.
9. Add `backend/src/services/funnel_service.py` for UTM URL construction:
   `utm_source=x`, `utm_medium=social`, `utm_campaign`, and `utm_content`.
10. Update dry-run in `backend/src/services/run_service.py` so it runs Quality
    Gate, stores `qualityScore`, marks successful queue items as
    `dry_run_passed`, and writes `dryRunId`.
11. Add queue endpoints in `backend/src/api/app.py`:
    - `POST /api/v1/queue/{item_id}/approve`
    - `POST /api/v1/queue/{item_id}/skip`
    - `POST /api/v1/queue/{item_id}/reject`
    - `PATCH /api/v1/queue/{item_id}`
12. Enforce approve flow: approval is allowed only after successful dry-run.
13. Strengthen publish guards: item must exist, status must be `approved`,
    there must be a successful dry-run after the latest edit, `DRY_RUN=false`,
    `POSTING_ENABLED=true`, `auth.json` must exist, and no publish run can be
    active.
14. Add `backend/data/posts.jsonl` funnel log events for dry-run and publish:
    post id, pillar, CTA type, target URL, UTM URL, status, run id,
    quality score, posted time, and notes.
15. Add `GET /api/v1/funnel/export.csv` with post id, pillar, CTA type,
    campaign, UTM URL, status, dry-run time, posted time, and quality score.
16. Update `backend/src/agent/harness.py`: proposals and drafts should accept
    pillar, CTA type, and target URL; publish request should require approved
    queue item; audit events should include approve, reject, and skip.
17. Update `frontend/src/main.jsx`: pillar filter, quality score, CTA type, UTM
    preview, Dry Run / Approve / Skip / Reject actions, Approved Today block,
    and disabled/hidden publish controls when backend denies publishing.
18. Add `backend/scripts/seed_examples.py` to create 5-10 example posts across
    the five pillars.
19. Add tests for validation, Quality Gate, UTM builder, queue state changes,
    publish guard without approve, publish guard without dry-run, and CSV
    export.
20. Verify backend changes with:
    `cd backend && python -m compileall src`
21. Verify frontend changes with:
    `cd frontend && npm run build`

## Product Principle

The money-making loop is:
pillar -> strong post -> CTA -> UTM -> lead -> sale -> learn which post themes
produce revenue.

Keep Playwright as a controlled publisher only. Do not expand stealth,
fingerprint spoofing, evasion, proxy rotation, multi-account orchestration, or
spam behavior.
