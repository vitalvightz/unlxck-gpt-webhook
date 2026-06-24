# Canonical State Machines

## Purpose
Status strings are shared by the API, Supabase rows, admin review actions, workers, and the frontend. This document is the human-readable contract for those states.

The executable contract lives in `api/state_machine.py`. Status checks and writes should use that module instead of open-coded sets.

## Status vocabularies (do not mix)

There are **three distinct status fields**. They share some words (notably
`review_required`) but live on different rows and mean different things. Code,
docs, and UI must use the exact string for the right field — never assume a plan
status is also a job status.

| Field | Lives on | Allowed values | Authority |
|---|---|---|---|
| **Generation job status** | `generation_jobs.status` | `queued`, `running`, `completed`, `review_required`, `failed` | `GENERATION_JOB_STATUSES` |
| **Plan status** | `plans.status` | `generated`, `ready`, `review_required`, `held_for_review`, `publishable_with_flags`, `triage_blocked`, `medical_hold`, `restricted_rehab_only`, `needs_review`, `archived` | `PLAN_STATUSES` |
| **`stage2_status`** | plan `admin_outputs.stage2_status` (audit only) | `stage2_pass`, `stage2_failed`, `admin_review_approved`, `admin_review_rejected`, `admin_archived`, `triage_resume_approved`, `""` (not run) | `api/stage2_automation.py`, admin services |

Key trap that prompted this section: **`review_required` exists as both a job
status and a plan status, and `held_for_review` exists only as a plan status.**
A failed Stage 2 validation sets the *plan* to `held_for_review`, and the worker
reports that plan's *job* as `review_required` (see
[Stage 2 outcomes](#stage-2-outcomes--statuses) and the
[plan→job mapping](#plan-status--generation-job-status)). `stage2_status` is a
separate audit trail and is never a job or plan status.

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

### Stage 2 outcomes → statuses

What the automated Stage 2 finalizer (`api/stage2_automation.py`) writes, by outcome:

| Stage 2 outcome | Plan status | `stage2_status` | Generation job status |
|---|---|---|---|
| Validator passes (clean) | `ready` | `stage2_pass` | `completed` |
| Validator passes (non-blocking flags) | `publishable_with_flags` | `stage2_pass` | `completed` |
| **Validator fails** | **`held_for_review`** | `stage2_failed` | `review_required` |
| Injury triage blocks Stage 2 | `triage_blocked` (or `medical_hold` / `restricted_rehab_only` / `needs_review`) | unchanged / `""` | `review_required` |

Naming caveat: the helper that builds the failed-validation result is named
`_review_required_result(...)`, but it sets the **plan** status to
`held_for_review` (constant `_APP_STATUS_HELD_FOR_REVIEW`). The "review required"
in the function name refers to the resulting *generation job* status, not the
plan status. Do not let the function name leak into plan-status strings.

### Plan status → generation job status

Terminal generation-job reporting is derived from the saved plan status by
`job_status_for_plan_status(...)` (`_PLAN_STATUS_TO_JOB_STATUS` in
`api/state_machine.py`). Unknown plan statuses fail closed to `review_required`.

| Plan status | Generation job status |
|---|---|
| `generated` | `completed` |
| `ready` | `completed` |
| `publishable_with_flags` | `completed` |
| `archived` | `completed` |
| `review_required` | `review_required` |
| `held_for_review` | `review_required` |
| `needs_review` | `review_required` |
| `medical_hold` | `review_required` |
| `restricted_rehab_only` | `review_required` |
| `triage_blocked` | `review_required` |
| *(unknown)* | `review_required` (fail closed) |

### Athlete-facing labels

The UI never shows raw status strings. `web/lib/plan-labels.ts` maps them to
human copy, and intentionally collapses both review states to the same label so
athletes are not exposed to the plan/job distinction:

| Status | Athlete-facing label |
|---|---|
| `ready` | Ready |
| `publishable_with_flags` | Ready — review notes included |
| `review_required` | Awaiting review |
| `held_for_review` | Awaiting review |
| `triage_blocked` | Paused for safety review |
| `generated` | Processing |
| `archived` | Archived |

Keep this table, `web/lib/plan-labels.ts`, and `api/state_machine.py` in sync
when a status is added or relabelled.

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
