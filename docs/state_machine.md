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
| **`stage2_status`** | plan `admin_outputs.stage2_status` (audit only) | `stage2_pass`, `stage2_failed`, `stage2_failed_stage1_fallback`, `admin_review_approved`, `admin_review_rejected`, `admin_archived`, `triage_resume_approved`, `manual_stage2_pass`, `manual_stage2_retry_pass`, `manual_stage2_retry_required`, `""` (not run) | `api/stage2_automation.py`, admin services |

Key trap that prompted this section: **`review_required` exists as both a job
status and a plan status, and `held_for_review` exists only as a plan status.**
`held_for_review` is written by admin action only — a failed Stage 2 validation
no longer produces it (see [Stage 2 outcomes](#stage-2-outcomes--statuses) and the
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
- `publishable_with_flags`: the plan is athlete-releasable with known low-risk quality warnings and remains visible for asynchronous admin audit.
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
| review_required | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| held_for_review | ❌ | ✅ | ✅ | ✅ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| publishable_with_flags | ❌ | ✅ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ |
| triage_blocked | ❌ | ✅ | ✅ | ✅ | ❌ | ✅ | ✅ | ✅ | ✅ | ✅ |
| medical_hold | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| restricted_rehab_only | ❌ | ✅ | ❌ | ✅ | ❌ | ❌ | ❌ | ✅ | ✅ | ✅ |
| needs_review | ❌ | ✅ | ✅ | ✅ | ❌ | ❌ | ✅ | ✅ | ✅ | ✅ |
| archived | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ❌ | ✅ |

### Stage 2 outcomes → statuses

`fightcamp/stage2_policy.py` is the Stage 2 release authority. Automatic and
manual submission paths consume its decision without upgrading `hold` to
publication. They use the same audit statuses: `stage2_pass` for a policy-approved
release and `stage2_failed` for a hold. Held renderer output is retained in
`final_plan_text` for admins; athlete-facing `plan_text` is empty.

| Central decision | Plan status | Audit status | Job status |
|---|---|---|---|
| `publish` | `ready` | `stage2_pass` | `completed` |
| `publish_with_flags` | `publishable_with_flags` | `stage2_pass` | `completed` |
| `hold` | `review_required` | `stage2_failed` | `review_required` |
| Runtime/provider failure with no usable response, empty output, persistence failure | no released plan | failure telemetry | `failed` |

Only `goal_preservation_failed` is allowlisted as an observational error in the
shared policy. It describes planner/evidence disagreement and is preserved in
`errors` and `quality_review_flags`, including unsatisfied states and missing
coverage. It cannot trigger planner regeneration or a renderer retry by itself.
Existing allowlisted presentation warnings can also publish with flags.

Renderer divergence is different: injury restrictions, illegal sparring, forbidden
exercises, effective-dose overages, witness render mismatches, fight-day protocol
violations, and truncated output remain blocking. Unknown errors, unknown
blocking warnings, malformed reports, and admin-review blockers fail closed.
Observations mixed with blockers never override a hold.

Effective-dose and witness render mismatches get at most one conforming renderer
repair. Both the corrected output and a still-invalid repair are revalidated by
the central policy. The first report is retained as `repair_source_report`; token
telemetry includes both calls. A failed repair stays held. A provider-incomplete
final response is recorded as `stage2_output_truncated` and held.

Planner safety rules must determine the canonical plan before rendering.
Validators must not second-guess legitimate planner choices, but must prevent
the renderer from violating those choices. A readable body alone does not prove
that the renderer followed the canonical plan.

Structured conversion runs only for policy-approved release. Invalid cards fall
back to that approved text; a card cannot rescue a Stage 2 safety hold.
The separate persistence contract gate retains its existing narrow calendar
allowlist and clean-card checks. Unknown contract errors and unusable content
remain held; it never promotes an existing Stage 2 hold. Medical triage and
explicit admin review actions retain their separate authority.

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
