# Athlete starting paths

New athletes choose `/get-started` after age and Terms acceptance. The choice is
stored in `profiles.starting_path` through the existing authenticated `/api/me`
endpoint. It selects a landing experience, never feature access:

- `tracking_first`: Today, with the existing manual logger, repeat shortcut,
  recent shared history, round timer, and a secondary link to Quick Build.
- `plan_first`: the existing Quick Build.
- `null`: show the choice only if there are no plans, intake or onboarding draft.

Existing plan destinations take priority over the preference. Home also exposes
the tracking workspace for tracking-first athletes with no active programme.
Loading errors never create a new-account or empty-history state.

## Rollout

Apply `20261018160000_add_starting_path.sql` **before deploying the backend**.
The temporary column default assigns `plan_first` to existing profiles, then
is dropped so new profiles start with NULL. The migration is repeatable and
preserves existing profile ownership policies and later saved choices. The
runtime schema gate requires the new column. No environment changes are needed.

This release does not change Quick Build, plan generation, readiness, workload,
rehab or clearance calculations. The timer does not create training records.
Detailed standalone sparring and plan-free readiness remain separate work.

## Verification

- Python regression: `python -m pytest tests/test_starting_path.py tests/test_training_habit_preferences.py tests/test_api_types_generated.py -q`.
- Schema: with `PGLITE_ROOT` pointing to an isolated install containing
  `@electric-sql/pglite`, run `node tests/sql/starting_path.test.mjs`.
- Frontend: `npm run typecheck`, `npm run lint`, `npm run test:unit`, and
  `npm run build` from `web`, using the existing CI-safe public environment values.
- Browser: `npx playwright test e2e/starting-path.spec.ts e2e/log-training.spec.ts e2e/signup-code.spec.ts`.
  New journeys cover 320px, 390px and 1280px, keyboard focus, accessibility,
  save retry, reload, plan-first, consent, existing plans, and failed reads.

Browser fixtures contain no real athlete data. Production migration application
and live cross-device persistence must be verified during rollout.

## Review follow-up — 18 October 2026

Applied the exact starting-path migration to the previously confirmed connected
Main project `unlxckpdf` (`leienvqynijrgghhzczt`). Supabase recorded version
`20261018212315`, name `add_starting_path` (the repository filename remains
`20261018160000_add_starting_path.sql`; reconcile that version difference before
future CLI migration pushes). Metadata checks confirm nullable text, no default,
a validated two-value check, preserved RLS, and all 20 existing profiles keeping
`plan_first`. The GitHub Actions live runtime schema-check job was rerun and
passed. No backend was deployed.

Athletes may still choose tracking without health-data consent. Opening the
logger explains why consent is required before collecting session inputs and
offers a single explicit consent action through the existing compliance API,
using the same consent statement as signup. It continues directly into the
logger, with no Settings detour or medical questionnaire. "Not now" dismisses
the prompt without granting consent. The same explanation handles a server
rejection after consent is withdrawn on another device. Consent is never
silently granted, and the standalone round timer remains available.

Shared history is fetched for display only. Habit learning and repeat shortcuts
retain the separate manual-only, 200-record history source; a failure in one
history source does not falsely empty or authorize the other.

The broader backend run found an existing failure in
`TestCommandView.test_malformed_structured_session_degrades_without_crashing`:
`fightcamp/exercise_instructions.py:54` calls `.get()` on a malformed string
session. The same failure was reproduced in an isolated checkout of Main
`828d03f5`; it is outside this starting-path change.
