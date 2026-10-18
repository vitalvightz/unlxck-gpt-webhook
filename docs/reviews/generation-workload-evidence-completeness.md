# Generation workload evidence completeness

Audit baseline: Main `f0dc307a`, with merged #2921 (`005d069a`) and #2922 (`f0dc307a`).

## Confirmed defect (before implementation)

`annotate_payload_with_sparring_readiness.read` catches a prescribed-completion query failure, records `list_session_completions` in the contact context's `unavailable`, and returns `[]`. It passes that fallback as `training_history(..., prescribed=[])`. Because preloaded prescribed data bypasses retrieval, successful external history lets `training_history` return normally. The snapshot then claims `training_history.available=True`, despite the known prescribed-source failure. A Main reproduction with failed prescribed history and one Hard/90-minute Boxing log returns an available one-session workload alongside a top-level prescribed-source failure.

The opposite failure loses useful evidence: external history failure raises inside the combined-history assignment, so the snapshot retains its initial empty `sessions`, discarding successfully retrieved prescribed work from the workload context. Contact still retains the prescribed reports separately.

The top-level contact-unavailable flag already reaches the existing elevated hard-sparring cutoff for prescribed failures. The confirmed F3 defect is contradictory combined-history health and lost partial workload evidence, not a missing neurological/contact STOP rule.

Implementation and validation findings follow below.

## Focused change

Each generation source is retrieved independently through the existing snapshot boundary. Successful prescribed and external rows are passed to the existing `training_history` combiner using its preloaded-source arguments. That combiner retains its ordering, ownership, deduplication and provenance logic; it does not acquire a second availability system.

The existing top-level `unavailable` list still identifies contact/readiness failures. Combined `training_history.available` now derives from required-source health, with an additive internal `training_history.unavailable` list naming failed components. Successful rows and their known workload stay present even if another source fails. Workload numbers in an incomplete snapshot describe retrieved evidence, not a claim about total recent workload.

The four store SELECT methods used by this boundary now reject missing/non-list response data and non-object rows with a generic 503. A successful `data=[]` remains healthy. This prevents the lower store layer from erasing the distinction before the snapshot sees it. Query ownership predicates, limits, ordering, writes and schema are unchanged.

The snapshot checks occurrence identity/status, training dates and the existing external-session field contract before treating rows as usable evidence. Malformed rows mark their source unavailable; other valid records remain usable. It does not revalidate completion write-only timestamps/reasons or require optional RPE/pain actuals. Diagnostics contain athlete ID, failed source and exception type, without database messages, traceback details or workout/medical values.

| Source result | Before | After |
| --- | --- | --- |
| Both sources succeed, empty | Available, zero workload | Same; normal existing low-workload/contact scheduling rules |
| Both succeed, valid records | Available combined history | Same identities, workload window and thresholds |
| Prescribed fails; Boxing succeeds | Boxing retained but combined history incorrectly available | Boxing retained; prescribed source unavailable; combined history incomplete |
| External fails; Strength succeeds | Combined workload loses Strength; contact still retains it | Strength retained in both relevant contexts; external source unavailable; combined history incomplete |
| Both fail | Empty workload; contact-unavailable signal | Empty known evidence explicitly incomplete; both failures attributed; no fabricated heavy workload |
| Next attempt succeeds | No persistent failure cache | Complete current history; no duplicate occurrences or sticky failure state |
| Missing/malformed SELECT response data | Could silently become successful `[]` | Generic unavailable read; existing conservative mechanisms apply |

No readiness thresholds, phase rules, selection algorithms, dose, calendars, contact interpretation, rehab progression, completion writes, frozen evidence or athlete UX changed. There is no migration, dependency, background job or queue.

## Database to downstream decision map

1. Athlete-scoped `session_completions`, `external_training_sessions`, `today_checkins`, and active `injury_flags` are read by `annotate_payload_with_sparring_readiness`.
2. Prescribed/external records flow through `training_history` into `training_history.sessions`; `completed_workload` computes the unchanged five-day, three-session evidence summary. Unknown legacy provenance marks the workload unavailable within that same five-day window.
3. Only independently reported prescribed completions flow into contact evidence. The snapshot resolves their actual session in their owned plan. Missing, unreadable, foreign or unmatched plan/session data becomes unknown contact with a component failure. The existing contact-history window remains seven days. Manual Hard Boxing or Sparring never becomes head-contact evidence.
4. `_sparring_readiness` passes through `PlanInput.from_payload` and `build_runtime_context` into `training_context.sparring_readiness`. `_build_athlete_model` retains the derived readiness flags, not raw history.
5. `sparring_readiness_flags` translates the existing top-level failure contract into `sparring_history_unavailable`. `hard_sparring_risk_state` applies the existing elevated scheduling cutoff; medical/neurological contact blocks continue to take precedence. Tests verify actual D-16 hard-to-technical output for incomplete evidence, normal hard output for genuine complete low workload, and no contact at any tested countdown under STOP restrictions. This is the existing scheduling policy, not a new clearance rule.
6. `_generate_conditioning_blocks` requires available combined history, a current check-in and external work before its existing workload-based adjustment can run. Incomplete evidence skips that adjustment. Baseline fatigue remains the declared intake value, not an inference of recovery from missing workouts. No new heavy-workload or arbitrary fatigue penalty is invented.

## Retrieval-health and empty-fallback audit

| Location | Empty fallback / distinction | Handling in this PR |
| --- | --- | --- |
| Store `list_session_completions`, `list_external_training_sessions`, `list_today_checkins`, `list_injury_flags` | Raised database errors propagate, but missing `response.data` previously became `[]` | Required response list shape is checked; healthy `[]` is retained |
| Snapshot `read` | Catches failures, returns `[]`, records top-level source health | Source health now reaches combined history too; malformed row/date/identity cannot silently count as healthy empty history |
| `training_history` | Default reads raise on failure; explicit preloaded `[]` carries no intrinsic health | Snapshot owns source health and passes each successfully collected subset; other callers retain their existing raising contract. The manual-only History API intentionally preloads prescribed `[]` as a filter, not as an availability claim |
| `recent_rows` | Bad `as_of` returns `[]`; bad/missing row date is skipped | Worker supplies trusted `resolve_training_day`; snapshot validates source dates before this filter. Valid stale/future dates remain normal exclusions |
| `completed_workload` | Excludes unknown provenance, progress-only/non-completed/deleted rows and out-of-window dates; absent actuals contribute no demanding classification | Unchanged pure aggregation; it does not claim retrieval health. The surrounding snapshot marks unknown legacy provenance unavailable in the existing window |
| Contact-plan resolution | Missing/foreign/raised plan read or unmatched session becomes unknown, with top-level `completion_plan` / `completed_session` attribution | Retained; source/type logging is sanitized. Known physical workload is not erased by unavailable contact classification |
| Today checked-read helpers / tracking boundary | Failure may return `[]`, but completeness is tracked separately and floors readiness | Unchanged #2922 authoritative path. It does not consume the generation snapshot or its new field; store shape failures now reach its existing safe fallback |
| `PlanInput.from_payload` | Missing/non-object `_sparring_readiness` becomes `{}` | Generation worker always replaces caller history with its server snapshot before fresh health-enabled Stage 1. Direct standalone/CLI planner calls without this boundary remain outside this database-evidence contract |
| Conditioning consumer | Missing/false `available` skips history-dependent adjustment | Existing behavior retained; the formerly false `available=True` case is fixed |

## Generation, regeneration and partial evidence

Athlete generation (`/api/plans/generate`), admin generation from latest intake, and triage-resume regeneration share `run_generation_job` in `api/generation/orchestrator.py`. Every fresh health-enabled Stage 1 pass annotates current evidence immediately before invoking the deterministic planner. Three service-level tests run the real orchestrator for these sources, evaluate the real runtime/athlete model/sparring dose plan inside the planner boundary, and complete safely with the expected incomplete evidence. The resume test verifies the linked plan is retained. Ephemeral history is not written into intake.

A worker retry that already has a saved `stage1_result` is a continuation of that artifact, not a new readiness evaluation: it skips Stage 1 and does not reread this snapshot. Stage 2 finalization/card repair likewise operates on its existing artifact. New generation/regeneration without a saved Stage 1 result gets fresh source health. Non-health mode deliberately skips health evidence under its separate consent contract. These lifecycle semantics are unchanged.

Consumers that need complete evidence:

- The first-active-phase conditioning adjustment needs complete combined workload/check-in evidence before drawing its repeated-hard-work conclusion.
- Sparring eligibility needs its existing contact/check-in/injury/availability evidence. Source failures now consistently reach the existing unknown-history scheduling gate, including manual-source failure.

Consumers that can use partial evidence:

- The snapshot retains individually verified workouts and known workload, without presenting their totals as complete.
- Known prescribed contact can still trigger high-contact/fatigue flags even when another source failed. Unknown contact is kept distinct from confirmed no-contact Strength.
- Known neurological symptoms, injury restrictions and medical contact blocks remain authoritative regardless of missing other records.
- Generation may proceed under the existing conservative scheduling rules; the whole programme is not cancelled solely for an incomplete history.

#2921 rules remain intact: only `reported` proves actual prescribed workload; `day_credit` never creates independent work or contact; unknown origin remains conservative; independently reported same-day workouts remain separate. #2922's live Today refresh, cache/snapshot behavior, persistence and UX are untouched.

## Remaining availability gaps outside F3

`rehab_stage_snapshot.resolve_open_injury_rehab_context` separately discards the success booleans from checked check-in/completion reads. Its `_open_flags` and `_flag_exposures` helpers return empty collections on failures, and stage/exposure annotation is documented as best-effort. This is not a truthful component-health contract for all rehab evidence; it remains a separate follow-up. This PR does not change rehab-stage or clearance policy. The generation snapshot still independently records the same workload/check-in/injury source failures for its own consumers. A regression checks that a current CALM injury stays CALM with failed workload history and that the real selector rejects higher-stage drills.

Other store history methods (for example legacy `list_session_logs`, plan-specific completion/history reads and injury-episode reads) still have `response.data or []` patterns. They are not read by this generation workload snapshot. No broader history/store rewrite is included. Bounded query limits (200 completions/manual records, 100 check-ins, 500 injury flags) are unchanged; this PR describes retrieval health within those existing contracts and does not introduce pagination policy.

## Validation

The repository's fast-lane dependencies are used in an external virtual environment; spaCy/model packages and live database integration are not installed or exercised. No dependency files changed.

- Original five-module provenance/external-training/sparring/rehab-generation baseline: **162 passed** on Main and the implementation branch.
- New source-completeness suite: **52 deterministic cases**, covering every failure direction, healthy empty evidence, recovery, malformed responses, source diagnostics, provenance, contact uncertainty, neurological/injury/rehab precedence, conditioning contract and three real worker entry sources.
- Matched broader generation/regeneration, clinical-safety, provenance and Today refresh suite: **943 passed on Main; 943 passed on this branch**. No PR-related failures in this selection.
- Store suite: **178 passed**. The final 52-case source-completeness suite passed after all edits.
- Changed Python Ruff and import compilation: **passed**.

Exact commands follow. The full repository suite, live Supabase/Postgres integration, and frontend/browser checks are outside this backend-only change; no frontend files changed.

```sh
python -m pytest -q tests/test_generation_workload_completeness.py
python -m pytest -q -n 3 tests/test_store*.py
python -m pytest -q -n 3 \
  tests/test_api_generation_flows.py tests/test_generation_runtime.py \
  tests/test_rehab_generation_boundary.py tests/test_sparring_readiness_boundary.py \
  tests/test_sparring_dose_planner.py tests/test_dynamic_sparring_cutoff.py \
  tests/test_generation_safety_bypasses.py tests/test_clinician_clearance_today.py \
  tests/test_rehab_pathway_safety_invariants.py tests/test_source_neutral_readiness_refresh.py \
  tests/test_prescribed_workload_provenance.py tests/test_external_training.py \
  tests/test_store_external_training.py tests/test_store_completion_origin.py
python -m ruff check api/store.py api/services/training_history.py \
  api/services/sparring_readiness_snapshot.py tests/test_generation_workload_completeness.py
python -m compileall -q api/store.py api/services/training_history.py \
  api/services/sparring_readiness_snapshot.py
```

The 943-case command was run independently in the isolated Main checkout and the implementation checkout with the same dependencies. Existing Starlette/Sentry deprecation warnings remain. No targeted failures were attributed to this PR.

Latest Main already has unrelated published failures:

- [Backend Checks](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39145896113): custom-plan publication expects `Strength / Rounds` but receives `Strength` (1 failed, 65 passed in that job).
- [Web Build](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39145896066): exercise-coaching release gate failures, predating this change.

Those failures were confirmed from the Main job logs, not inferred from this branch. No claim is made that all Main CI or the full repository suite is green. The service tests exercise real worker orchestration and deterministic readiness/sparring decisions with FakeStore and fake Stage 2 finalization; they do not execute a full live database-to-published-program deployment.
