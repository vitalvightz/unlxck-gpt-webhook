# Programme fidelity follow-up to #2875

## Scope and evidence

This change repairs normal dated programmes using the existing calendar,
selected exercise membership and resolved prescriptions. It does not introduce
another scheduling authority. Core reconciliation, goal evidence, phase mapping,
prescriptions and session budgeting are shared across sports. Striking conditioning
selection remains subject to the existing sport, equipment, injury and load filters.
Free-text frequency parsing and failed-plan visibility/release policy are unchanged.
No production records, schema, environment variables or exercise-bank snapshots were changed.

The affected plan is `9eb137f7-571a-43fa-8e5d-47d2b5032755`. Its generation job
started on 2026-10-14 at 03:39:58 UTC. Successful deployment run
[38505129608](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/38505129608)
deployed commit `792a1670085db73d1b83d77e3744f1d8f571fe3e`, completed at
03:16:42 UTC, and verified API/worker revision and health. This is the latest
successful deployment before the job. The job has no immutable backend SHA
receipt, so this is deployment correlation, not a per-job cryptographic proof.

The regressions use anonymised actual intakes and recorded model responses for
all three plans. A separate trimmed recorded authority proves the original
affected output's omissions and wrong dates without regenerating Stage 1.
Source regeneration pins the original intake date and seed 1: production did not
save its seed. No live provider request or production generation was performed.

## Root causes and corrections

1. Stage 2 text could omit coach appointments and change dates even though the
   handoff contained the correct calendar. Text finalization now reconciles the
   training section deterministically, before review and persistence. Validation
   independently compares every appointment, order, phase heading and complete
   prescription. Closed sessions with missing effective doses are failures.
2. The weekly renderer used pool-level examples instead of closed membership;
   strength effective doses lived separately from selected assignments. It now
   reads the shared rendering authority and joins selected members to their
   effective doses. Repeated weekdays in eight-date progression weeks are resolved
   by exact date in both rendering and validation.
3. Primary goal/weakness did not reach exercise-selection context. Style quota
   exhaustion then excluded higher-scoring bag intervals from remaining conditioning
   slots. Context now reaches selectors; appropriate alactic/glycolytic style work
   can compete on its score. Aerobic selection keeps its existing preference.
4. Power evidence ignored legitimate explosive, full-rest conditioning bursts,
   while landing-only Depth Drop could count as speed. Evidence now uses actual
   mechanics, work/rest, effective rounds and effort. Landing-only work is excluded;
   easy bag practice does not earn power or speed-development credit.
5. Landmine push presses fell into generic core tempo prescriptions, holds could
   receive movement tempos, and speed sled work received heavy-carry doses. Their
   source templates now match explosive propulsion, static holds and light
   acceleration respectively. Working prescriptions choose minimum approved work
   and full recovery within authorised ranges; tempos and dose ceilings are retained.
6. Overlapping progression-week and calendar frequency caps removed valid sessions.
   Budgeting now uses the existing whole-calendar cadence, counts separate same-day
   appointments individually and considers real goal coverage before dropping a
   surplus role. It never adds workload to clear a warning.
7. Late goal repair reran global placement/recomposition and could move an earlier
   speed appointment. Repair retains athlete context, recomposes changed roles and
   does not restart unrelated bounded placement searches. Realised-load checks run
   around the repair; forbidden-load checks and residual reporting remain global.
8. Normal dated-calendar D-0 phase mapping was off by one. Both the phase owner and independent
   authority check now use its inclusive calendar length. Direct short-camp
   timelines and legacy phase-only records retain their countdown-interval
   convention, so D-13 primers remain available. The affected 52-day camp
   has 15 GPP, 22 SPP and 15 taper dates.

## Before and after

| Recorded affected programme | Reconciled programme |
| --- | --- |
| Hard sparring on D-42, D-35, D-28 and D-21 omitted | All four Saturday appointments retained at their authoritative dates |
| `D-40 (Wednesday)` with misplaced S&C | `D-40 (Monday) — Fight Visualisation`; authoritative Wednesday S&C remains D-38 |
| `D-26 (Thursday)` with misplaced strength | `D-26 (Monday) — Fight Visualisation`; strength stays on its calendar date |
| No heavy-bag conditioning | `Max-Power Bag Burst — 5s work, 60s rest x 8 rounds; RPE 8` at D-15 |
| Speed intent credited to landing/braking | Real speed sled work: `6 x 5s acceleration with a light sled; full rest 90s; stop if speed drops` |
| Slow movement tempo on explosive press; tempo on holds | Explosive press and hold-specific source prescriptions, independently tested |

Suitable aerobic/recovery work remains. Unknown weight information is stated as
incomplete rather than inventing a weight-cut target. Coaching appointments are
not expanded into invented drills.

## Replay results

Each intake requests six total standalone sessions per week. Counts below are
the existing calendar's consecutive cadence windows, including the partial final
window; support inserts are counted only when their existing ownership marks them
as physical standalone appointments. Optional mental rehearsal is not a session.

| Scenario | Actually scheduled cadence counts | Required coach appointments | Selected goals with qualifying doses | Bag conditioning |
| --- | --- | --- | --- | --- |
| Affected `9eb137f7…` | 6, 6, 6, 5, 6, 6, 6, 3 | 30 retained | Speed build; power and conditioning maintain | D-15: 8 × 5s, 60s recovery |
| Earlier `40d25b71…` | 6, 6, 6, 6, 6, 6, 6, 4 | 30 retained | Recovery build; speed and power maintain | D-30 and D-16: 8 × 5s, 60s recovery |
| Earlier `0e1f9aaf…` | 6, 6, 6, 6, 6, 6, 6, 4 | 30 retained | Speed build; power and conditioning maintain | D-31/D-23 bursts; D-30/D-17 five sustained 180s power rounds with 60s recovery |

All three recorded-response finalizer replays have zero validator errors, exact
appointment/date/prescription fidelity and satisfied selected-goal contracts.
Their full-camp standalone totals are 44, 46 and 46; S&C totals are 13, 14 and
15 respectively. Each retains 30 coach appointments. Advisory warning counts
are 1, 1 and 2, with zero blocking warnings. The remaining warnings compare
phase-pool examples with rendered selections (taper primary strength in all
three, plus GPP aerobic in the last comparison); they do not establish missing
authoritative appointments. No extra work was added to satisfy these warnings.
The existing release decision is `publish_with_flags`; advisory requirements
remain visible. Persistence regression verifies the corrected text is saved
unchanged. Visibility and release overrides are deliberately unchanged at the
user's request. No original production plan has been overwritten.

## Verification and limitations

The production regression file exercises intake → Stage 1 → recorded-response
Stage 2 → reconciliation → validator → persistence, plus negative mutations for
missing/invented appointments, weekdays, selected exercise, rest, phase and order.
It also checks total frequency across progression boundaries, inclusive phases,
source exercise intent, unpriced membership and late repair retaining earlier speed.

Existing range expectations are changed only where working-dose resolution now
produces a concrete value inside the original permitted range. No snapshots were
refreshed. The existing timed-power assertion now checks actual short efforts,
rounds and full rest rather than requiring a conditioning burst to have lifting reps.
Legacy synthetic phase fixtures retain their original interval convention. The
new production regression checks the inclusive normal-calendar count separately.

Local verification: 19 production regressions pass; 311 tests across finalizer,
validator, workload and safety suites pass (including production regressions); 140 additional goal, frequency,
conditioning and coach-ownership tests pass. The combined goal/production
recheck passes 73 tests. Ruff and `compileall` pass. CI backend pytest,
rehab concurrency, lint, dependency audit and schema checks have passed;
full-suite shards and remaining builds are still being reviewed on
[PR #2876](https://github.com/vitalvightz/unlxck-gpt-webhook/pull/2876).

Direct late-fight and open/ongoing programmes keep their separate existing owners;
this strict reconciliation applies to normal dated calendars. Supporting nutrition,
recovery and mindset text still comes from the provider and is subject to existing
validators. No fresh live provider run has been made. CI results must be checked
before recommending merge.

## Full-suite follow-up and interactive verification

PR #2875 remains merged; #2876 remains open and must not be merged yet. The
completed CI run on `c8de1e67` passed web build, backend checks, runtime surfaces,
lint, dependency audit and schema checks, but failed all six full-suite shards.
There were 96 failing test cases. Running those exact cases on merged #2875
(`792a1670`) reproduced 32 failures and passed the other 64. The baseline failures
include historical metadata/source drift, generated API type checks, incomplete
injury mocks and several existing late-camp/goal fixtures. They are not attributed
to this patch. No frozen snapshots have been refreshed.

The follow-up repairs actual regressions:

- Selected bank coaching cues and purposes now accompany the authoritative doses.
  Phase objectives remain in readable text and interactive week goals. Banked
  tactical/visualisation instructions and their progressions retain their existing owners.
- Stage 1 draft parity explicitly excludes the finished-programme contract;
  finalization still applies strict reconciliation and validation by default.
- Closed, fully priced membership is stable at its approved date and phase.
  Explicit changed-role callbacks and stale-date/phase checks still recompose.
- Goal evidence cannot use an old preferred support name to credit a different
  selected conditioning exercise. Instruction-only support is checked against its
  own rendered name and prescribed duration, rather than a nonexistent bank slot.
- Interactive conversion now extracts compact sets/reps, timed holds, carries,
  rounds, work/rest and RPE into numeric fields while retaining the original
  execution wording. Attaching actual S&C clears an empty calendar's rest marker.
  The fallback reads the actual athlete snapshot and preserves sport, equipment
  and timezone, instead of defaulting real boxing plans to generic metadata.

The production regression now checks the same programme through reconstructed
cards, stored-card resolution and the provider conversion/finalizer path. It
verifies every selected assignment is represented, all dates/weekdays/phases,
the four required hard-sparring appointments, numeric bag/strength/sled/hold/carry
doses, phase goals and execution cues. These are recorded-response tests without
paid model calls. Existing dose and safety gates remain active.

Negative provider/card replays found and now cover two additional defects: a
converter could replace the bag's 60-second rest with 20 seconds, and role-level
coverage could pass a strength card after its sled exercise disappeared.
Structured faithfulness now rejects changed numeric doses, and existing planner
coverage checks require every selected source exercise. The persistence/API
resolver regression proves that either a faithful stored card or the existing
deterministic fallback reaches the athlete with the original 60-second recovery
and all three sled exposures. Failure visibility and publication policy remain
unchanged. Omission-only advisory handling is retained; changed values are
distinct from an absent field that the source-backed renderer can recover.

Follow-up local results: the three-module parity/goal/membership recheck passes
196 tests with two failures also present on merged #2875. Structured conversion,
faithfulness and salvage checks pass 225 tests; focused render/dose/recovery
checks pass 174; phase/late-primer checks pass 211; card/closure checks pass 95.
These groups overlap and are not a claimed unique-test total. The three negative
and positive provider-card persistence cases pass. Ruff and import compilation
pass. Full CI must be rerun on the follow-up commit.

Test expectation changes have concrete evidence: range doses resolve inside the
original bounds, static holds and push presses retain their actual intent, and
unplaced guidance is not rendered as an appointment. Instruction-only inserts
retain their original coaching copy plus the already prescribed duration. The
three-session novice scenario now has no calendar collision after surplus roles
are removed; it checks all surviving doses against the shared legality policy,
frequency and goal coverage rather than forcing an unnecessary relocation.

Remaining historical checks need separate review: seven reviewed-goal fixtures
pin the entire `strength.py` hash, and five frozen calendar fixtures expect the
old overlapping budget/placement outcomes. The seven reviewed exercise archetypes
and their recorded phase doses were independently checked and remain identical;
only the whole-module hash changed. Calendar fixture contacts are unchanged; the
observed changes retain allowed goal/recovery appointments within the requested
budget. These snapshots are preserved for review, not silently rewritten to make
CI green. Updated CI and regression results will be recorded before merge advice.
