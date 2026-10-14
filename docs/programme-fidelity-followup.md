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
8. Inclusive D-0 phase mapping was off by one. Both the phase owner and independent
   authority check now use inclusive calendar length. The affected 52-day camp
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
Synthetic phase fixtures now explicitly count D-0: D-5 through D-0 is six dates,
and D-7 through D-0 is eight. Their exercise-selection assertions are retained.

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
validators. Structured-card provider generation and a fresh live model run have
not been replayed here. CI results must be checked before recommending merge.
