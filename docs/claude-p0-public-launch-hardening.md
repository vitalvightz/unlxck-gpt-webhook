# Claude implementation prompt: P0 public launch hardening

This PR is a Claude-facing implementation brief. The goal is to convert the current private-beta app into a safer public-beta candidate by implementing the P0 hardening items below.

## Context

The app is a full-stack UNLXCK fight-camp planner:

- Backend: Python/FastAPI.
- Frontend: Next.js/TypeScript in `web/`.
- Database/auth/storage: Supabase.
- AI generation: deterministic planner first, OpenAI Stage 2 finalisation second, validation before release.
- Existing backend test/lint tooling:
  - `pyproject.toml` has pytest config and ruff lint config.
  - `requirements-dev-fast.txt` supports fast tests without spaCy.
  - `requirements-dev.txt` supports fuller development tests.
- Existing frontend scripts in `web/package.json`:
  - `build`
  - `typecheck`
  - `lint`
  - `test:e2e`
  - `audit:high`

Do not rewrite the app. Harden what exists.

## P0 objective

Implement the minimum launch-hardening layer required before moving from private beta toward public beta.

A successful implementation should improve:

1. CI enforcement.
2. Route authorization proof.
3. Secrets/dependency scanning.
4. AI spend/token guardrails.
5. Medical/injury safety UX and auditability.

## Required deliverables

### 1. Enforced GitHub Actions CI

Create or update GitHub Actions workflows so every PR into `Main` runs meaningful gates.

Required checks:

- Backend:
  - Install Python using the repo-supported version.
  - Install fast dev dependencies from `requirements-dev-fast.txt`.
  - Run `ruff check .`.
  - Run `pytest -m "not spacy"`.
- Frontend:
  - Use Node 20.x.
  - Run from `web/`.
  - `npm ci`.
  - `npm run typecheck`.
  - `npm run lint`.
  - `npm run build`.
  - `npm run audit:high`.
- E2E smoke:
  - Run Playwright where feasible.
  - If the full app requires unavailable secrets, add a documented smoke subset or make the workflow skip only with an explicit reason.

Acceptance criteria:

- A PR cannot look “green” if backend lint/tests or frontend type/build/lint checks fail.
- The workflow does not require production secrets for normal PR validation.
- The workflow is understandable for a solo founder to maintain.

### 2. Authorization matrix tests

Add tests proving the most important access-control rules.

Minimum scenarios:

- A normal athlete cannot access another athlete’s plan.
- A normal athlete cannot access admin routes.
- Archived plans are not exposed to normal athlete flows unless intentionally allowed.
- Service-role write paths verify ownership before writing.
- Admin-only actions require both the database admin role and the configured admin email allowlist.

Implementation guidance:

- Prefer small, direct tests around dependencies/services rather than huge brittle end-to-end tests.
- Mock Supabase responses where needed.
- Do not require real Supabase credentials in CI.
- Add fixtures/fakes if the current test setup does not already provide them.

Acceptance criteria:

- Tests fail if ownership checks are removed.
- Tests fail if admin allowlisting is bypassed.
- Tests run in CI without external secrets.

### 3. Secrets and dependency scanning

Add lightweight security checks suitable for the current repo.

Required:

- Add a secret-scanning workflow or documented local/CI step using a standard tool such as `gitleaks`.
- Ensure dependency audit exists in CI:
  - frontend: `npm run audit:high`.
  - backend: add a Python dependency vulnerability check if practical, such as `pip-audit`, without making the workflow unreasonably slow.
- Add or update docs explaining required repository settings:
  - GitHub secret scanning.
  - Dependabot alerts/updates.
  - branch protection requiring CI.

Acceptance criteria:

- No secret scanning depends on production secrets.
- The docs tell the owner exactly which GitHub repository settings to enable.
- The workflow fails on high/critical findings unless explicitly documented otherwise.

### 4. AI cost and token guardrails

Harden OpenAI/Stage 2 usage so public users cannot accidentally create runaway cost.

Required:

- Add explicit per-request output token cap defaults.
- Add per-user daily AI usage limit or daily generation budget.
- Add global daily AI usage/spend guardrail where possible.
- Record enough telemetry to support admin review:
  - model
  - prompt tokens if available
  - completion tokens if available
  - total tokens if available
  - estimated/requested cost if available
  - generation job id
  - user id
  - failure reason
- Add clear behaviour when budget is exceeded:
  - no crash
  - no silent failure
  - user-safe message
  - admin-observable event/log

Implementation guidance:

- Do not remove the deterministic planner fallback.
- Do not blindly truncate plans in a way that creates invalid plans.
- If token limits risk truncation, hold for review rather than publish a bad plan.

Acceptance criteria:

- A user cannot spam generation indefinitely in one day.
- A misconfigured model cannot generate uncapped output by default.
- Admins can see or log why AI generation was blocked, failed, or held.

### 5. Medical/injury safety UX and auditability

The app gives training guidance around injuries, so public beta needs clearer safety boundaries.

Required:

- Add visible “not medical advice” language in relevant injury/training flows.
- Add severe injury red-flag escalation copy.
- Add clinician-clearance wording where the app returns from medical hold / rehab-only / restricted states.
- Ensure admin overrides or safety-state changes are auditable.
- Make sure high-risk injury flows do not produce normal training plans as if nothing happened.

Acceptance criteria:

- Users see plain-English safety guidance before relying on injury-modified programming.
- Severe injury paths clearly tell the user to seek professional medical help.
- Returning from an injury restriction requires a clear state transition and leaves an audit trail.
- Existing injury logic is not weakened.

## Non-goals

Do not do these in this PR unless required for the P0 work:

- Full redesign.
- Major schema rewrite.
- Replacing Supabase.
- Replacing FastAPI.
- Replacing the planner engine.
- Large AI prompt rewrite unrelated to cost/safety.
- Adding paid analytics vendors unless already configured.

## Suggested implementation order

1. Add CI first so the rest of the PR is measurable.
2. Add/repair authorization tests.
3. Add secret/dependency scan docs and workflow.
4. Add AI guardrails and telemetry.
5. Add medical safety UX/audit changes.
6. Update README or docs with launch-readiness checklist.

## Final PR checklist

Before marking ready for review:

- [ ] Backend CI passes.
- [ ] Frontend CI passes.
- [ ] Authorization matrix tests pass locally and in CI.
- [ ] Secret/dependency scan documented and wired into CI where practical.
- [ ] AI token/cost guardrails are implemented and tested.
- [ ] Injury/medical safety wording is visible in the relevant UX.
- [ ] Admin/safety overrides leave an audit trail.
- [ ] No production secrets were added.
- [ ] No real Supabase/OpenAI credentials are required for PR tests.

## Output expected from Claude

Implement the P0 fixes in code, tests, workflows, and docs. Keep changes focused and explain any skipped item clearly in the PR body with the reason and the safest next step.