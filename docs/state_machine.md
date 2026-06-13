# Canonical State Machines

## Purpose
Status strings are shared by the API, Supabase rows, admin review actions, workers, and the frontend. This document is the human-readable contract for those states.

The executable contract lives in `api/state_machine.py`. Status checks and writes should use that module instead of open-coded sets.

## Generation Job States
Generation jobs describe worker execution. They do not describe whether a saved plan is clinically safe or publishable.

- `queued`: persisted and waiting for a worker.
- `running`: claimed by a worker.
- `completed`: worker finished and saved a terminal plan result.
- `review_required`: worker finished, but the Stage 2 output needs admin review.
- `failed`: worker could not finish successfully.

Allowed transitions:

- `queued` -> `running`, `failed`
- `running` -> `queued`, `completed`, `review_required`, `failed`
- `failed` -> `queued`
- `completed` -> `queued`
- `review_required` -> `queued`, `completed`, `failed`

Self-transitions are allowed for idempotent updates.
Workers must claim a job and move it through `running` before writing
`completed` or `review_required`; direct `queued` -> terminal success/review
transitions are not part of the contract.

## Plan States
Plans describe the saved planning result and review/safety state.

- `generated`: legacy/default pre-finalization state.
- `ready`: plan is available to the athlete.
- `review_required`: Stage 2 or admin review must resolve the plan before release.
- `held_for_review`: explicit admin hold.
- `publishable_with_flags`: admin has marked the plan publishable with known warnings.
- `triage_blocked`: injury triage blocked Stage 2.
- `medical_hold`: injury triage requires medical clearance before planning proceeds.
- `restricted_rehab_only`: injury triage allows restricted rehab-only planning.
- `needs_review`: injury triage requires review before normal planning proceeds.
- `archived`: hidden from athlete-facing active plan lists.

Allowed transitions are defined in `api/state_machine.py`. In plain terms:

- New/legacy generated plans may move into any terminal review, safety, ready, or archived state.
- Review states may resolve to `ready`, stay under review, or be archived.
- Triage-blocked/restricted review states may resolve to `ready`, remain constrained, move to another triage safety state, or be archived.
- `archived` is terminal except for idempotent archive writes.

### Explicit plan transition matrix

| From \ To | generated | ready | review_required | held_for_review | publishable_with_flags | triage_blocked | medical_hold | restricted_rehab_only | needs_review | archived |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| generated | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| ready | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| review_required | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| held_for_review | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |
| publishable_with_flags | ❌ | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| triage_blocked | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| medical_hold | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| restricted_rehab_only | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| needs_review | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| archived | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

### Protected-state resume contract

- `approve-and-resume-generation` is only allowed for triage modes `needs_review` and `restricted_rehab_only`.
- `medical_hold` is intentionally non-resumable via approve-and-resume.
- Resumed jobs may end as:
  - plan `ready` (job `completed`)
  - plan `review_required` / `held_for_review` (job `review_required` according to `job_status_for_plan_status`)
  - job `failed` if worker/runtime cannot safely persist a valid linked plan

### Triage resume UI lifecycle

The backend currently uses `stage2_status = triage_resume_approved` as an audit marker that approval happened. It is **not** proof that resumed generation completed successfully. UI should treat it as "approved previously" and keep retry/resume controls available when the linked `admin_triage_resume` job is stale, failed, or still blocked.

### Backend invariant for terminal jobs

For generation jobs ending in `completed` or `review_required`:

- `plan_id` must point to an existing `plans` row.

Otherwise the job is downgraded to `failed` to avoid exposing orphaned terminal job links.

Unknown plan statuses map to `review_required` for generation-job reporting so
new safety/review states fail closed to human review instead of worker failure.

### Athlete-displayable / publishable plan statuses

`ATHLETE_DISPLAYABLE_PLAN_STATUSES` (and `is_athlete_displayable_plan_status`) in
`api/state_machine.py` name the states where a plan is shown to the athlete:

- `ready`
- `publishable_with_flags`

Downstream, display-oriented work — e.g. building the `structured_plan` rendering
payload — runs only in these states, regardless of how the plan got there
(automated Stage 2 pass or admin approval). Blocked, held, medical-gated,
review-required, and archived plans are excluded so nothing is published merely to
derive structured output.

`restricted_rehab_only` is intentionally excluded: it is a safety-gated "planning
paused, clinician clearance required" state, not a normal athlete-facing training
plan. Add it only if the product decides to render rehab-only plans to athletes.

Use `is_athlete_displayable_plan_status(...)` instead of open-coded
`status == "ready"` checks.

## Implementation Rule
Use:

```python
can_transition("generation_job", "running", "review_required")
can_transition("plan", "review_required", "ready")
can_transition("generation_job", "running", "failed")
```

Do not introduce scattered status sets in route handlers, workers, or frontend helpers. Add new states to this document and `api/state_machine.py` in the same change.
