# UNLXCK Fight Camp Builder

Athlete-first fight camp planning. Backend in Python (FastAPI), frontend in Next.js. Deployed on Render + Vercel.

---

## Stack

| Layer | Technology |
|---|---|
| Frontend | Next.js (TypeScript), deployed on Vercel |
| Backend | FastAPI (Python 3.10+), deployed on Render |
| Database | Supabase (PostgreSQL + Auth + Storage) |
| AI finalization | OpenAI (Stage 2 plan finalizer) |

---

## How the planner works

Plan generation runs in two stages:

**Stage 1 — Structured candidate generation**
The Python planner (`fightcamp/`) reads the athlete's intake profile and builds a full draft plan. It scores exercises and conditioning drills by weakness tags, goal tags, style tags, phase, and equipment availability. The injury guard removes anything that violates active restrictions and selects safe replacements. Output includes the draft plan text, candidate pools, coach review notes, and the Stage 2 handoff package.

**Stage 2 — AI finalization**
The handoff package is sent to OpenAI. Stage 2 applies the `STAGE2_FINALIZER_PROMPT` rules: hard-filtering any remaining restriction violations, improving sequencing, enforcing anchor session standards, and writing the final athlete-facing plan in coach voice. The validator reviews the output and can trigger a repair pass if quality thresholds are not met.

---

## Repository structure

```
api/                    FastAPI application
  app.py                Routes, lifespan, generation job handler
  auth.py               Supabase token verification
  store.py              Supabase persistence (profiles, intakes, plans)
  models.py             Pydantic request/response models
  stage2_automation.py  OpenAI Stage 2 call + retry logic
  nutrition_workspace.py Nutrition workspace endpoints

fightcamp/              Plan generation engine
  main.py               Entry point — orchestrates full generation pipeline
  stage2_payload.py     Assembles planning brief + candidate pools + handoff text
  stage2_planning_brief.py  Athlete model, phase briefs, limiter/sport-load profiles
  stage2_role_map.py    Week progression, session roles, sparring lock, compression
  stage2_payload_late_fight.py  Late-fight countdown modes and rendering rules
  stage2_validator.py   Plan quality validation and repair prompt builder
  strength.py           Strength exercise selection and scoring
  conditioning.py       Conditioning drill selection and scoring
  conditioning_boxing.py Boxing-specific aerobic routing and language sanitisation
  injury_guard.py       Exercise exclusion and safe replacement
  injury_filtering.py   Injury matching and exclusion mapping
  injury_synonyms.py    Free-text injury parsing and canonicalization
  injury_scoring.py     Injury severity scoring
  injury_formatting.py  Injury laterality and summary formatting
  injury_exclusion_rules.py  Region-to-pattern exclusion definitions
  rehab_protocols.py    Rehab drill selection and guardrail generation
  sparring_advisories.py  Sparring load advisory and injury risk bands
  sparring_dose_planner.py  Hard sparring day allocation
  late_fight_placement.py   Countdown session placement engine
  camp_phases.py        Phase week calculation with style adjustments
  training_context.py   Session allocation per phase and frequency
  coach_review.py       Post-selection coach review and substitution log
  mindset_module.py     Mental block classification and phase cues
  normalization.py      Shared string/collection utilities (single source of truth)
  config.py             Centralized constants and DATA_DIR
  input_parsing.py      Intake validation and field normalization
  plan_pipeline.py      Pipeline assembly
  plan_pipeline_blocks.py   Block generation
  plan_pipeline_rendering.py  Plan text rendering
  plan_pipeline_runtime.py    Bank priming and runtime context

data/                   JSON banks (loaded at runtime)
  exercise_bank.json
  conditioning_bank.json
  rehab_bank.json
  style_conditioning_bank.json
  coordination_bank.json
  injury_exclusion_map.json
  tag_vocabulary.json

web/                    Next.js frontend
  app/                  App Router pages (plans, onboarding, settings, nutrition, admin)
  components/           UI components
  lib/                  API client, types, utilities

tests/                  Pytest test suite
tools/                  Developer scripts (bank audits, validation, generation)
notes/                  Tag documentation and reference material
```

---

## Local development

### Backend

```bash
# Install dev environment (includes runtime + test/lint deps)
pip install -r requirements-dev.txt

# For production-only installs, use:
# pip install -r requirements.txt

# Set environment variables
cp .env.example .env  # then fill in values

# Run the API
uvicorn api.app:app --reload

# Run the plan generator directly (no API)
python -m fightcamp.main
```

Required environment variables:

```
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=
UNLXCK_ADMIN_EMAILS=you@example.com
APP_CORS_ORIGINS=http://localhost:3000
OPENAI_API_KEY=
```

### Frontend

```bash
cd web
npm ci
npm run dev
```

Copy `web/.env.local.example` to `web/.env.local`:

```
NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
```

---


### Dependency versioning policy

- `requirements.txt` contains **runtime-only** Python dependencies and every package is pinned to an exact version.
- `requirements-dev.txt` contains development/test tooling and references `requirements.txt` so dev environments stay aligned with production.
- `web/package.json` uses exact dependency versions (no caret ranges) and `web/package-lock.json` is committed to lock transitive installs.
- Runtime versions are pinned with `runtime.txt` / `.python-version` for Python and `web/.nvmrc` + `web/package.json#engines` for Node.js.

## Deployment

**Backend (Render)**

- Start command: `uvicorn api.app:app --host 0.0.0.0 --port $PORT --workers 2`
- The bank JSON files are loaded into memory on first request and cached for each worker process lifetime (with `--workers 2`, both workers will warm independently).
- Keep the instance warm with a cron job hitting `/health` every 14 minutes or use Render Standard tier

**Frontend (Vercel)**

- All browser API calls use same-origin `/api/...` URLs
- `next.config.ts` rewrites `/api/*` to the Render backend server-to-server
- Set `NEXT_PUBLIC_API_BASE_URL` to your Render URL in Vercel environment variables

---

## API surface

| Method | Route | Description |
|---|---|---|
| GET | `/health` | Health check |
| GET | `/api/me` | Current athlete profile |
| PUT | `/api/me` | Update profile |
| POST | `/api/plans/generate` | Start plan generation (returns job ID) |
| GET | `/api/generation-jobs/{id}` | Poll generation status |
| GET | `/api/plans` | List saved plans |
| GET | `/api/plans/{id}` | Get plan detail |
| DELETE | `/api/plans/{id}` | Delete plan |
| PATCH | `/api/plans/{id}/name` | Rename plan |
| GET | `/api/nutrition/current` | Get nutrition workspace |
| PUT | `/api/nutrition/current` | Update nutrition workspace |
| GET | `/api/admin/athletes` | Admin: list athletes |
| GET | `/api/admin/plans` | Admin: list all plans |

---

## Testing

```bash
# Run full test suite
pytest

# Run specific file
pytest tests/test_injury_guard.py

# Run with verbose output
pytest -v

# Run only fast unit tests (skip API integration tests)
pytest --ignore=tests/test_api_admin_flows.py \
       --ignore=tests/test_api_generation_flows.py
```

Tests covering: injury guard, sparring advisories, stage 2 payload modes, planning brief, conditioning diagnostics, surgical rehab integration, input parsing, restriction parsing, and more.

---

## Injury pipeline

Free-text injury notes (e.g. `"worsening left knee strain"`) flow through:

1. **Parsing** (`injury_synonyms.py`) — splits into phrases, extracts laterality, canonicalises injury type and body location
2. **Scoring** (`injury_scoring.py`) — detects severity (mild/moderate/severe), medical urgency flags
3. **Guard** (`injury_guard.py`) — scores each exercise against active injuries using region multipliers and tag-based risk; returns EXCLUDE / MODIFY / ALLOW
4. **Replacement** — picks a safer alternative from fallback tag hierarchies
5. **Rehab** (`rehab_protocols.py`) — matches injuries to `rehab_bank.json` and generates phase-specific rehab prescriptions with `Purpose` and `Why today` framing
6. **Advisory** (`sparring_advisories.py`) — classifies injury risk bands (green/amber/red/black) for the sparring advisory output

Enable detailed exclusion logging:

```bash
INJURY_DEBUG=1 python -m fightcamp.main
```

---

## Stage 2 late-fight modes

When `days_until_fight` ≤ 13, the payload switches to a countdown mode instead of a normal camp week. Modes:

| Days out | Mode |
|---|---|
| 13–8 | Compressed pre-fight week |
| 7 | Sharpness week |
| 6–5 | Sharpness & freshness window |
| 4–2 | Sharpness-first sessions |
| 1 | Primer day |
| 0 | Fight day protocol |

Each mode has its own rendering rules, session caps, forbidden terms, and handoff instructions. Session roles are placed by the three-layer placement engine: permission → budget → countdown placement.
