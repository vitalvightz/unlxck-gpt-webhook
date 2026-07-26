# UNLXCK Fight Camp Builder

UNLXCK is an athlete-first fight-camp planning and daily training application. Athletes complete onboarding, generate a structured camp, review it by week/day/phase, submit daily readiness and injury check-ins, receive a server-authoritative Today recommendation, record session completion, and send beta feedback without leaving the app.

New plans are stored and displayed in the application. PDF export is retained only for legacy compatibility and is not part of the current generation flow.

## Production architecture

| Layer | Current service |
|---|---|
| Web application | Next.js 16 / React 19 on Vercel |
| API | FastAPI on Hetzner Docker Compose |
| Generation | Persistent Python worker on Hetzner |
| Edge / TLS | Caddy on Hetzner |
| Data and identity | Supabase PostgreSQL, Auth, and private Storage |
| AI finalization | OpenAI Stage 2 markdown and structured-card generation |
| Monitoring | Health checks, structured logs, and Sentry |

The browser uses same-origin `/api/*` requests. Vercel rewrites those requests to the Hetzner HTTPS endpoint. The API writes durable generation jobs to Supabase, and the persistent worker claims and processes them. The API does not run heavy plan generation in-process in production.

Render web and worker services are suspended emergency rollback targets only. Never run the Render and Hetzner workers against the production queue at the same time.

Operational references:

- [Hetzner deployment runbook](docs/hetzner-deployment.md)
- [Deployment health checks](docs/deployment-health-checks.md)
- [Supabase runtime schema check](docs/supabase-runtime-schema-check.md)
- [Generation reliability checklist](docs/generation-reliability-checklist.md)

## How plan generation works

1. The API validates the athlete and creates a durable generation job.
2. The worker claims the job and runs the Python planner in `fightcamp/`.
3. Stage 1 builds a structured candidate plan from intake, goals, style, equipment, schedule, phase, and injury restrictions.
4. Stage 2 finalizes the plan with OpenAI and, by default, converts it into the `StructuredTrainingPlan` schema.
5. Validation either publishes the plan or marks it `held_for_review`; the corresponding job status is `review_required`.
6. The app displays structured plan cards with raw-markdown fallback, so structured conversion failure does not leave the athlete with a blank plan.

Plan and job statuses are deliberately separate. See [the state-machine contract](docs/state_machine.md) and [`STAGE2_PAYLOAD_SPEC.md`](STAGE2_PAYLOAD_SPEC.md).

## Daily athlete flow

The saved plan remains the training source of truth. Daily check-ins, session logs, injury flags, recommendations, and adaptations are stored separately:

- The server calculates the athlete's training day using their timezone and a 04:00 local rollover.
- The recommendation engine evaluates readiness and injury signals; the client does not choose the recommendation.
- Daily activity never rewrites the saved plan. Rule decisions are appended as adaptation notes.
- Today supports readiness check-in, injury reconciliation, session completion, and feedback.
- Admin routes expose athlete status, injury/check-in review queues, job triage, and plan review.

See [the live athlete flow](docs/live-athlete-flow.md) and [Block 4 UX hierarchy](docs/block-4-ux-hierarchy-addendum.md).

## Repository map

```text
api/                    FastAPI app, routes, services, contracts, and worker runtime
fightcamp/              Deterministic plan-generation and injury-safety engine
web/                    Next.js application and Playwright tests
supabase/migrations/    Versioned production schema and security changes
docs/                   Operational and domain contracts
tests/                  Python unit, integration, and API tests
compose.yaml            Hetzner API, worker, and Caddy services
render.yaml             Suspended emergency fallback definition
```

Important backend modules:

- `api/app.py` — application assembly, middleware, router mounting, and readiness.
- `api/worker.py` — persistent generation worker.
- `api/generation/` — job orchestration, timeouts, milestones, and persistence.
- `api/routes/today.py` and `api/routes/daily.py` — daily athlete experience.
- `api/routes/feedback.py` — authenticated beta feedback and private screenshots.
- `api/state_machine.py` — canonical plan/job states and transitions.
- `api/structured_plan_models.py` — machine-readable plan schema.

## Local development

### Backend

Python 3.11 is required.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
uvicorn api.app:app --reload
```

Run the planner without the API:

```bash
python -m fightcamp.main
```

Core local environment values:

```env
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=
OPENAI_API_KEY=
UNLXCK_ADMIN_EMAILS=you@example.com
APP_CORS_ORIGINS=http://localhost:3000
APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER=5
FEEDBACK_REPORT_LIMIT_PER_HOUR=5
FEEDBACK_SCREENSHOT_LIMIT_PER_HOUR=2
FEEDBACK_SCREENSHOT_RETENTION_DAYS=90
```

Admin authorization is a dual gate: the stored `profiles.role` must be `admin` and the user's email must be in `UNLXCK_ADMIN_EMAILS`. See [admin role management](docs/admin-role-management.md).

### Frontend

Node 24 is required.

```bash
cd web
npm ci
cp .env.local.example .env.local
npm run dev
```

Minimum frontend values:

```env
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_SITE_URL=http://localhost:3000
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

On Windows, `tools/start-local-preview.ps1` starts the API and web application with local-safe overrides.

## Production deployment

The live backend runs from `/opt/unlxck` on the `Main` branch. Production secrets are stored in `/opt/unlxck/.env.production` and are never committed.

```bash
cd /opt/unlxck
git fetch origin
git reset --hard origin/Main
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl -fsS https://$API_DOMAIN/health
```

The Compose services are:

- `api`: one Uvicorn worker, in-process generation disabled, spaCy disabled.
- `worker`: one persistent job consumer with full spaCy injury parsing.
- `caddy`: TLS termination and reverse proxy with persistent certificate volumes.

In Vercel, `NEXT_PUBLIC_API_BASE_URL` points to the Hetzner HTTPS API endpoint and `NEXT_PUBLIC_SITE_URL` points to the production frontend. Follow the runbook for first deployment, verification, rollback, and the emergency Render fallback.

Beta screenshot retention is scheduled on the Hetzner host and runs inside the API container. See [beta feedback operations](docs/beta-feedback-operations.md).

## API groups

| Area | Representative routes |
|---|---|
| Health | `GET /health` |
| Profile and onboarding | `/api/me`, `/api/me/username`, `/api/onboarding/draft` |
| Generation | `/api/plans/generate`, `/api/generation-jobs/*` |
| Plans | `/api/plans`, `/api/plans/{id}`, weekly schedule and active-plan routes |
| Daily flow | `/api/today`, `/api/today/landing`, `/api/injury-flags` |
| Nutrition | `/api/nutrition/current` |
| Feedback | `/api/plans/{id}/feedback`, `/api/today/feedback`, `/api/feedback/global` |
| Admin | `/api/admin/athletes/*`, `/api/admin/plans/*`, `/api/admin/generation-jobs/*`, `/api/admin/feedback` |

The FastAPI OpenAPI schema is the authoritative route inventory.

## Validation

Backend:

```bash
pytest -n auto
pytest -n auto -m "not spacy"   # fast lane
pytest -m spacy                 # injury-parser coverage
```

Frontend, from `web/`:

```bash
npm run typecheck
npm run lint
npm run test:unit
npm run build
npm run test:e2e
npm run audit:high
```

Dependencies and runtimes are pinned through the Python requirement files, `runtime.txt`, `.python-version`, `web/package-lock.json`, `web/.nvmrc`, and `web/package.json#engines`.

## Canonical documentation

- [State machine](docs/state_machine.md)
- [Stage 2 payload specification](STAGE2_PAYLOAD_SPEC.md)
- [Injury pipeline contract](docs/injury_pipeline_contract.md)
- [Live athlete flow](docs/live-athlete-flow.md)
- [Beta feedback operations](docs/beta-feedback-operations.md)
- [Service-role authorization checklist](docs/service-role-authorization-checklist.md)
- [System regression checklist](docs/qa/system-regression-checklist.md)

Historical planning material should be treated as context, not production truth. When documentation conflicts, the current code, migrations, deployment runbooks, and state-machine contract take precedence.
