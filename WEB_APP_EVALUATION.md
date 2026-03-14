# Web App Evaluation (Codebase + Latest Updates)

_Date:_ 2026-03-14  
_Scope:_ repository architecture, recently shipped web shell update, runtime quality checks.

## Executive summary

The latest web shell launch is a strong structural upgrade: the app now has authenticated athlete/admin routes, onboarding persistence, plan generation UX, and API scaffolding with role-aware responses. Core backend + frontend boundaries are clear and test coverage for API scaffold behavior is present.

The main regression found during this evaluation was build fragility in restricted environments caused by `next/font/google` fetches at build-time. This has been addressed by switching to resilient CSS fallback font stacks.

## What was reviewed

- **Backend API scaffold:** auth, profile, plan listing/detail mapping, and role-aware response shaping.
- **Frontend app shell:** global layout/nav, auth gate flow, onboarding/generation surfaces, and dashboard composition.
- **Repo quality signals:** test inventory, docs/readability, and build/test pass behavior.
- **Latest updates:** commit series culminating in `Launch athlete web app shell` and associated UI/API additions.

## Findings

### Strengths

1. **Clear service boundaries**
   - `api/` cleanly wraps planner runtime with typed models and auth/store interfaces.
   - `fightcamp/` remains separated as domain planning engine.
   - `web/` focuses on user journeys and typed client interactions.

2. **Good product workflow coverage in v1 shell**
   - End-to-end athlete path now exists: signup/login → onboarding → generate plan → view history/details.
   - Admin-facing views are scaffolded and role-gated.

3. **Testing baseline established for new API layer**
   - `tests/test_api_scaffold.py` validates key scaffold expectations and currently passes.

### Risks / Gaps

1. **Build reliability risk from remote font fetches**
   - Prior implementation relied on `next/font/google`, which fails when Google Fonts is unreachable.
   - This risk is now mitigated in this branch via local CSS fallbacks.

2. **No dedicated web lint/typecheck script in `package.json`**
   - Current scripts include `dev`, `build`, and `start`, but no explicit `lint`/`typecheck` gates.
   - Recommend adding CI checks for TS and linting to catch regressions pre-merge.

3. **Limited frontend test coverage**
   - Python/backend test surface is strong, but frontend currently appears to rely mostly on build-time validation.
   - Recommend adding focused unit/integration tests for intake validation and auth-guarded routing behavior.

## Changes made during this evaluation

1. **Hardened frontend build path for offline/restricted environments**
   - Removed build-time Google font imports from `web/app/layout.tsx`.
   - Added robust local fallback font variables in `web/app/globals.css`.

## Quality checks executed

- `pytest -q tests/test_api_scaffold.py` → pass.
- `npm run build` (web) initially failed due to Google Fonts fetch errors.
- `npm run build` (web) after font fallback change → pass.

## Recommended next updates

1. Add `lint` and `typecheck` npm scripts and wire into CI.
2. Add frontend tests for:
   - onboarding validation edge cases,
   - role-based route protection,
   - plan detail rendering fallbacks.
3. Consider local self-hosted font files if strict typography parity is required across platforms.

