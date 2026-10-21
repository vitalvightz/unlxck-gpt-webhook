# Rehabilitation bank readiness

Based on Main `7f4ef5d8`, after #2982. This change reuses the completed
[64-profile inventory in #2983](https://github.com/vitalvightz/unlxck-gpt-webhook/pull/2983),
the [reachability report](rehab-bank-reachability.md),
[candidate review](rehab-advanced-candidate-review.md) and
[activation backlog](rehab-activation-backlog.md).

## Changes

- Today shows **Your rehab** near the top, with the prescribed exercise name
  and a link straight to its existing exercise row and player. Held, stale and
  completed work gets no start link. Completion keeps the existing controls.
- Generation now carries owned injury history, restrictions and reported props
  for every family. The old four-pilot condition dropped other injuries' context;
  its four-prop list also dropped items such as a dowel or soft ball. Today and
  generation now share the same exact reported-equipment reader.
- Complete, compatible bank prescriptions can join any existing live profile.
  The old five-profile rollout list no longer controls publication.
  Existing prescription validation and injury-specific restrictions still apply.
- Today uses the approved rehabilitation dose in every camp phase.
  GPP, SPP and TAPER still control normal training.
- Plan generation uses the same published decision as Today. Raw legacy bank
  content cannot bypass a missing policy or missing eligibility evidence.
  Surface injury care keeps its separate existing behaviour.
- Rename `wrist_sprain_wrist_stability_drill_with_dynamometer` to
  **Supported dynamometer grip loading**. Its reviewed instructions describe
  grip loading, not a test of ligament healing or clearance. Identity, mechanics,
  unknown loading, missing dose and unpublished status remain unchanged.
  The review ledger retains the old name and source hash.
- Probe equipment alternatives for every published profile in the existing
  reachability tool, rather than only the five original rollout profiles.

No stage, transition, clinical threshold, permission, completion event or
response workflow changes. Historical audit snapshots remain unchanged, using
exact-hash test fixtures to reconstruct their original inputs.

## Published coverage

Each cell shows profiles with published prescriptions, **before / after**.
This is content availability, not proof that an athlete is eligible today.

| Family | Profiles | CALM | RESTORE | LOAD | DYNAMIC | RETURN |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| Muscle strains | 8 | 8 / 8 | 8 / 8 | 0 / 0 | 0 / 0 | 0 / 0 |
| Sprains and instability | 10 | 10 / 10 | 10 / 10 | 1 / 1 | 0 / 0 | 0 / 0 |
| Tendons | 8 | 8 / 8 | 8 / 8 | 3 / 3 | 0 / 0 | 0 / 0 |
| Joint irritation and impingement | 5 | 5 / 5 | 4 / 4 | 0 / 0 | 0 / 0 | 0 / 0 |
| Hyperextension and joint trauma | 6 | 6 / 6 | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |
| Contusions | 11 | 11 / 11 | 5 / 5 | 0 / 0 | 0 / 0 | 0 / 0 |
| Nonspecific symptoms | 16 | 16 / 16 | 3 / 3 | 0 / 0 | 0 / 0 | 0 / 0 |
| Total | 64 | 64 / 64 | 38 / 38 | 4 / 4 | 0 / 0 | 0 / 0 |

There are still **111 distinct published exercise IDs**, used by 112
prescriptions. All 111 remain reachable with suitable equipment and evidence.
There are **no newly selectable IDs**. None of the remaining reviewed candidates
has all the information needed for safe publication. Removing the rollout list
lets future complete content use the existing pipeline across all seven families.

## What still blocks publication

The completed review covers 58 unpublished mechanics-reviewed candidates:
53 LOAD and five DYNAMIC. Their classification does not supply a prescription.
Do not bulk classify the other 1,433 entries.
The current [reachability JSON](rehab-bank-reachability.json) records each
dormant identity and its missing fields. Examples are listed below.

| Candidate | Information still needed |
| --- | --- |
| Elbow eccentric curl | Starting dose, resistance and suitable movement range. |
| Ankle band circles | Dose and a reproducible resistance prescription. |
| Ankle single-leg foam balance | Dose and suitability for the unstable surface. |
| Shoulder band scaption | Dose, selected resistance and permitted arm height. |
| Supported dynamometer grip loading | Dose, device and bounded load; a supported wrist LOAD transition. |
| Groin cable adduction | Bounded resistance and dose; a supported groin LOAD transition. |

The triceps incline push-up, neutral wrist hold and hands-and-knees wrist
rock-back names were already corrected on Main. Their remaining prescription
and transition gaps are recorded in the existing reviews, not solved by another
name change. Existing reviewed sources do not provide the missing values.

DYNAMIC and RETURN also need reviewed entry criteria, evidence sources and
pass/fail conditions alongside an executable prescription. That is separate
clinical pathway work. No extra forms or approval records are added here.

## Verification

New regression coverage exercises compatible publication in all seven families,
real Today API selection in all three camp phases, exact approved prescriptions,
unsupported stages and the unpublished-content boundary. Existing tests cover
permissions, equipment, multi-injury restrictions, setbacks, cadence, completion
and next-day responses. Episode allocation unit tests stub published decisions;
the Today API tests use the real policy resolver.
The old family-migration comparison explicitly composes policies with its dated
bank, so later publication metadata cannot leak into the historical replay.

The updated checks include 45 bank-readiness and selection tests, including
generation matching Today for all five bank options and owned context across
seven families. UI checks cover the direct link at 375px and 1280px, held work,
the existing player and single completion. Before/after screenshots are saved
outside the repo for review in the task response.

Production athlete testing was not performed. Authenticated API tests use the
existing authorised test fixtures, not a production account. Browser checks use
the existing test harness. Browser plugin not available; the repository's
Playwright workflow was used against the local production build.

Known failures reproduced on clean Main at `7f4ef5d8`:

- `tests/test_rehab_selection_pipeline.py::test_the_selector_actually_runs_during_plan_generation`
- `tests/test_rehab_selection_pipeline.py::test_live_stage_reaches_the_structured_rehab_block_with_a_canonical_id[restore]`
- `tests/test_rehab_selection_pipeline.py::test_selection_narrows_the_block_to_the_chosen_drill`

These remain separate from this publication change. See the PR for final test
counts and commands.
