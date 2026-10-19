# Plan-free daily readiness

Every athlete gets the same daily check-in on Today, with or without an active
UNLXCK programme. There is one readiness system: the same inputs, the same
deterministic engine (`build_readiness_adjustment`), the same context fail-safe,
and the same Today presentation. Only what depends on a programme is absent,
and nothing is invented to stand in for it.

## How a check-in is routed

`POST /api/today/checkin` with `plan_id` and `phase` is the existing planned
check-in, unchanged. Without either it is plan-free:

- The server first confirms there is no active plan. If there is one, the
  request gets a 409 and nothing is written, so a stale client can never
  record a plan-free check-in over a programme. A failed plan read is a 503,
  never "no plan".
- The engine runs with no prescribed session, no camp phase and no intake.
  "No plan" is a known fact, not a failed read, so it does not trip the
  fail-safe. With no session to grade, exposure is treated as unresolved, never
  as a safe rest day, and the decision records `session_unresolved` (and
  `sparse_history` for a new athlete) so its confidence band reports the thin
  evidence.
- It still reads everything that exists without a plan: open injuries and
  their clinician clearance, recent check-ins, recent training (manual and
  prescribed, via shared training history) and sparring reports.
- A phase is sent with a `plan_id`, and only then (422 otherwise). A plan-free
  row is stored with `plan_id` and `phase` both NULL.

## What the athlete is told

Every restrictive decision keeps the engine's own copy ("No training today.",
"Rehab only today.", "No contact today.", fail-safe holds). Only the clean-day
wording written for a prescribed session ("Full session." / "Run the planned
work…") is replaced:

- Title: "No warning signs today."
- Action: "Train as your coach plans and stop anything that hurts."
- Always: "This check-in is not medical clearance for sparring or contact."

On Today, `getPlanFreeGuidanceBanner` keeps the tier, chip and tone exactly as
`resolveTodayDecision` set them, and shows the stored plan-free copy instead of
the session-based tier titles. A safety notice or STOP keeps its own copy.

## Safety

- Missing or failed safety-critical reads floor the decision exactly as they
  do for planned athletes. A failed injury read holds at pull-back, and other
  failed reads degrade to modify, on submission and again whenever Today is
  read.
- **Every Today read re-evaluates the check-in**, exactly as on the planned
  path. The stored recommendation is a check-in-time snapshot. Each read runs
  the stored answers through the same evaluator (`plan_row=None`) against the
  latest injuries, medical holds, workload, sparring and safety reads, so a
  hard session logged later, a deleted session, a head-impact report or a
  failed read changes what Today shows. The read is read-only and never
  rewrites the check-in. It reuses reads already made in the same build; the
  planned path has always paid this cost.
- A new injury report, or a worsening one, also re-evaluates and stores the
  plan-free check-in, so the persisted recommendation keeps up too.
- **Head impact (all athletes):** a rocked/dropped sparring report on the
  current or previous training day pulls readiness back with "No contact
  today." This is a floor, never a clearance. A failed sparring read degrades
  readiness (`sparring_unavailable`) instead of ignoring head impact. This is
  the one deliberate change for planned athletes, as an explicit safety fix.
- Without health-data consent no plan-free check-in is offered (the server
  also rejects it), and the status tile reads "Not assessed".

## Database

Migration `20261019150000_allow_plan_free_today_checkins.sql`:

- `today_checkins.plan_id` and `phase` become nullable together:
  `today_checkins_phase_matches_plan` requires `(plan_id is null) = (phase is null)`.
- `today_checkins_athlete_plan_free_day_key`: a partial unique index for one
  plan-free row per athlete-day. The plan-scoped unique constraint treats NULL
  plan_ids as distinct, so it cannot deduplicate them.
- `upsert_plan_free_today_checkin(uuid, jsonb)`: backend-only upsert on that
  partial key. PostgREST cannot target a partial index. `api/store.py` routes
  plan-free rows to it automatically.

Existing rows all have a plan and a phase and are untouched. Plan-scoped
triggers and XP checks match on `plan_id`, which a plan-free row never
satisfies. XP for checking in is per athlete-day and works unchanged. Apply
**before deploying the backend**: the runtime schema gate requires the new
index and function.

## Moving to a programme

Creating a plan does not reset anything. The plan-free check-in stays in
history, injury and training history carry over, and Today asks for the
plan's own check-in. That check-in is evaluated against the prescribed session
and phase, and the existing same-day warning notes that one was already done.

## Verification

- `python -m pytest tests/test_plan_free_readiness.py -q`
- Schema: `PGLITE_ROOT=<isolated pglite> node tests/sql/plan_free_today_checkins.test.mjs`
- Races: `REHAB_TEST_DATABASE_URL=<local disposable cluster> python -m pytest tests/test_plan_free_checkin_postgres.py -q`
  (also in the `rehab-lock-concurrency` CI job)
- Web: `npm run test:unit`, then `npx playwright test e2e/starting-path.spec.ts`
