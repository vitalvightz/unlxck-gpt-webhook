# Groin closed-stage pilot verification

Baseline: Main `1315869a9baef178bec86c409852182ca62ba6df`, 20 October 2026.
The final branch CI comparison is maintained in the PR description; the links
below identify the exact completed Main runs, rather than treating a red badge
as a new regression. No inherited failing test or fixture is edited.

## Focused checks

- `pytest -q tests/test_groin_load_hold.py`: **65 passed** locally (Python 3.12.14).
- Main's four existing LOAD pilots: **310 passed**, using
  `tests/test_achilles_load_activation.py`,
  `tests/test_lateral_elbow_load_activation.py`,
  `tests/test_ankle_load_activation.py` and
  `tests/test_shoulder_load_activation.py`.
- Branch regression command includes those same four files plus
  `tests/test_clinical_review_engine_and_freeze.py`,
  `tests/test_rehab_generation_boundary.py`, `tests/test_rehab_schedule.py`,
  `tests/test_rehab_transition_engine.py` and
  `tests/test_rehab_selection_pipeline.py`. Results are reported in the PR.
- `ruff check api fightcamp tests tools`: passed.
- `python -m compileall -q fightcamp/input_parsing.py tests/test_groin_load_hold.py`:
  passed.
- All nine commands from Validate JSON Banks completed with exit code zero,
  including both migration `--check` commands and the clinical validator.
  The general validator runs in audit mode and still reports inherited inventory
  issues; zero exit is not a claim of a clean whole-bank audit. The rehab
  validator reports **64 active profiles and four promotable transitions**.
- The manifest test verifies all 64 profile hashes, complete pathway/bank/ledger
  bytes, all bank and review identity hashes, dated audits/reports, prior pilot
  manifests and athlete-interaction files against Main. No new question exists.

The generation integration assertion failed on unchanged Main and passed after
adding `groin/strain` to the existing exact-type preservation set. It verifies
GPP, SPP and TAPER: guided groin strain now selects the reviewed side-lying
RESTORE instead of legacy Copenhagen content. No exercise or dose is invented.

## What is and is not verified

| Area | Result |
| --- | --- |
| Apparently eligible acute-adductor report, completed RESTORE, both reassuring responses | Safety baseline may pass; clinical criterion and LOAD prescription remain absent. |
| Unknown/conflicting/non-adductor presentation, avulsion/significant tear, severe/neurological or unexplained symptoms | Never gains LOAD; no new diagnostic or baseline-indication claim. |
| Permission missing, contact-only, loading or sport-specific | None can activate a nonexistent groin LOAD option. |
| Wrong athlete, injury, side/episode; absent/modified/unreviewed work; unknown demand or response; worse response; incomplete history | Cannot open LOAD. Existing setback handling retains CALM. |
| Relevant hip/groin/pelvic/lower-limb injury and unrelated mild wrist bruise | No LOAD available; baseline decision remains appropriate. No new blanket multi-injury veto. |
| Cable equipment present/absent, missing/modified reviewed content | Cannot schedule dormant cable LOAD. |
| Normal RESTORE complete/modified/skipped, response attribution and next-day observation | Tested through existing completion and episode-observation services. Completion records RESTORE provenance; no strength or ROM inferred. |
| Daily allocation | A completed baseline session cannot schedule duplicate same-day RESTORE. |
| Saved but unstarted baseline after worsening | Held; saved snapshot unchanged. |
| Started/completed baseline after worsening | History unchanged; future policy decision remains conservative. |
| Frozen LOAD revalidation and LOAD completion | Not applicable: no executable groin LOAD. Shared frozen-review and four existing LOAD pilot regressions are included separately. |
| DYNAMIC / RETURN | Both unavailable, including with sport-specific permission. |

## Exact Main CI baseline

| Workflow/job | Completed Main result |
| --- | --- |
| [Backend Checks](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39434337192) | Passed, including PostgreSQL jobs. |
| [Validate JSON Banks](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39434337331) | Passed. |
| [Python Quality](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39434337215), Ruff, dependency audit, runtime surfaces | Passed. |
| Python full suite shard 0 | 26 failed, 2,838 passed. |
| Python full suite shard 1 | 10 failed, 11 errors, 2,413 passed, 13 skipped. |
| Python full suite shard 2 | 17 failed, 3,786 passed, 43 skipped. |
| Python full suite shard 3 | 43 failed, 2,602 passed, 24 skipped. |
| Python full suite shard 4 | 26 failed, 2 errors, 2,386 passed, 11 skipped. |
| Python full suite shard 5 | 18 failed, 3,590 passed, 37 skipped. |
| [Web Build](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39434337188), coaching release | 47 failed, 73 passed. |
| Web typecheck, lint, unit tests, dependency audit, Next build | Passed. |
| Web smoke/accessibility | 5 failed, 3 flaky, 10 skipped, 197 passed. |

Full failing node IDs and job IDs are retained in
[the baseline record](../reports/groin-load-ci-baseline.json). Python failures
include existing coaching, calendar/planner, metadata fingerprints, catalogue
counts and injury-pipeline regressions. Main already fails the ankle bundle
`worse-calm` case. Web failures are mental-task layout at two widths, round-timer
audio and two Tracking-start paths; the three flaky cases are recorded separately.
The original Main findings remain visible. They are not repaired inside this PR.

GitHub CI uses Python 3.11.15 and PostgreSQL 17.11; local checks use 3.12.14 and
no live database credentials. PostgreSQL results are obtained from CI. There is
no live Supabase or deployment claim. No merge or deployment is performed.
