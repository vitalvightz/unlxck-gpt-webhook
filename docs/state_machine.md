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

What the automated Stage 2 finalizer (`api/stage2_automation.py`) writes, by outcome:

**Stage 2 validator findings never hold a plan.** They decide which release
status is written, not whether the athlete gets the plan. Flagged plans land in
`publishable_with_flags`, which is athlete-displayable *and* in
`ADMIN_REVIEW_PLAN_STATUSES` — so the plan reaches the athlete immediately and
still shows up in the admin review surface with every finding attached.

| Stage 2 outcome | Plan status | `stage2_status` | Generation job status |
|---|---|---|---|
| Validator passes (clean) | `ready` | `stage2_pass` | `completed` |
| Validator has only allowlisted low-risk quality flags | `publishable_with_flags` | `stage2_pass` | `completed` |
| Validator has an admin-review blocking context/programme finding | `publishable_with_flags` | `stage2_failed` | `completed` |
| Validator fails on a hard blocker (safety / output integrity) | `publishable_with_flags` | `stage2_failed` | `completed` |
| No clean structured card | unchanged (card status logged; plan_text is the fallback) | unchanged | `completed` |
| **Technical failure with no usable Stage 2 text** — timeout, provider error, unavailable finalizer, empty output | no plan row | — | `failed` |
| Injury triage blocks Stage 2 | `triage_blocked` (or `medical_hold` / `restricted_rehab_only` / `needs_review`) | unchanged / `""` | `review_required` |

The shared Stage 2 policy still has three explicit classes:

- `hard_stage2_blocker_codes`: safety and output-integrity failures;
- `athlete_release_with_flags_codes`: a narrow allowlist of low-risk clarity findings;
- `admin_review_blocking_codes`: athlete-context and programme-quality failures.

What changed is the consequence, not the classification. Validator errors, hard
blockers, admin-review blockers, mixed reports, and unknown `blocking_warnings`
are all still detected and recorded verbatim on the plan; they now release with
flags rather than holding. `stage2_status` stays `stage2_failed` on those plans,
so the audit trail still shows the validator failed. The persisted report's
`release_decision` / `is_athlete_releasable` / `is_publishable` are set to the
released-with-flags values so the report agrees with the saved plan status.

`publishable_with_flags` remains in the admin review surface for asynchronous
audit. This policy removes athlete release delay; it does not remove flagged
plans from the admin queue or reduce review volume.

Planner decisions are authoritative. Validators are observational after a usable
plan exists. Validator findings may flag a plan for review but cannot veto athlete
release or convert a usable plan into a failed generation. Safety must be enforced
by the canonical planner before output, not retroactively by relying on a validator
kill switch.

Goal-preservation and rendered-witness findings use this same release policy.
They remain in `stage2_validator_report.errors`, with unsatisfied states and
missing coverage unchanged. Automatic finalization makes no dose/goal repair
call and never requests planner regeneration to satisfy a validator.
Post-generation contract checks flag usable content even for unknown error codes.
Manual Stage 2 submissions use the same released-with-flags report policy.
The offline `build_stage2_retry` helper remains available for explicit diagnostic
repair tooling, but neither automatic nor manual release calls it. Structured
conversion failures retain their debug report and fall back to existing plan text;
card-format repair does not regenerate the canonical plan.
Explicit admin holds and pre-planner triage remain separate decisions.

#### Technical Stage 2 failures

The rows above describe a Stage 2 plan that *exists*. If Stage 2 fails before
producing usable athlete-facing text — for example a timeout, provider error,
unavailable finalizer, empty response, or unexpected finalizer crash — the
generation attempt fails and no plan row is created. Stage 1 remains internal
planner input only; it is never promoted to the athlete-facing final plan.

An `incomplete` provider response is handled by content, not by status alone. If
it still contains usable Stage 2 text, that Stage 2 text continues through the
validator and releases as `publishable_with_flags` with an admin-visible
`stage2_incomplete_response` warning. If it contains no usable Stage 2 text, the
generation attempt fails.

The historical `stage2_failed_stage1_fallback` audit value may still appear on
old plan rows created before this contract changed. New generations do not write
that outcome.

#### What can still block a release

Two Stage 1 gates remain. Both are deliberately narrow.

1. **Injury triage** — `triage_blocked` / `medical_hold` /
   `restricted_rehab_only` / `needs_review`.
2. **The post-generation plan-contract gate**
   (`_apply_plan_contract_validation` in `api/generation/persistence.py`), but
   only for an unrecoverable finding.

The contract gate runs after Stage 2 and validates the finalized result: the
calendar rendered from `planning_brief`, the `stage2_payload` late-fight
sequence, and the athlete-facing plan text. Its error-severity findings are split
by consequence, not by which stage produced them:

| Finding | Outcome |
|---|---|
| `weekly_schedule_blank` | `publishable_with_flags` |
| `calendar_unrenderable` | `publishable_with_flags` |
| `fight_day_missing` | `publishable_with_flags` |
| `late_fight_session_sequence_empty` | `publishable_with_flags` |
| `plan_text_empty` | `review_required` |
| `validator_error`, or any unknown code | `publishable_with_flags` if usable content exists; otherwise `review_required` |

Findings flag readable plan text or a usable structured card for admin audit.
A `plan_text_empty` finding still releases with flags if a usable card exists;
without either form of content, the plan remains withheld. Unknown validator
codes cannot veto existing content. The separate card-rescue classification can
keep a clean card at `ready` for known render-only discrepancies.

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
