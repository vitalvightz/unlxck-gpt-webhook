# Mechanical metadata corrections — PR #2826

Base: Main `acafae19` (merged #2825), pulled before editing. Seven source rows
address portions of four original findings. This does not close the broad audit
findings or certify the rest of the catalogue. No selection engine, clinical
policy, goals, doses or normalization code is changed.

| Audit finding | Exercise / permanent source ID | Original → correction | Source evidence | Runtime effect / test |
| --- | --- | --- | --- | --- |
| MI-d857b5615775; MI-f6ac4b3a763c | Battle Ropes Tempo Burner / `conditioning_bank.json:1f94dcf3-dc9c-4e90-bc4b-d81a364eb954` | Remove landing/rebound tags in both copies; impact high → low | “Upper body glycolytic work; lower body unloaded”; 4×40s hard, 20s rest, RPE 9 | Remove false ankle-impact exclusion and cost signal; retain ballistic, systemic fatigue and high lactate/movement costs |
| Same | Battle Rope Gauntlet / `conditioning_bank.json:2cc04be9-cf99-4825-99cb-901b89493154` | Same | 30s waves / 30s slams; upper-body shoulder-turnover instruction; no jumping | Same; overhead/grip and existing equipment gates remain |
| Same | Battle Rope Waves / `conditioning_bank.json:616d349d-7c5a-4546-ad04-d8d6762ce566` | Same | “Double waves only (RPE 8)”; 8×30s, 90s rest | Same; high systemic/density cost remains |
| MI-f6ac4b3a763c | Defensive Rhythm Flow / `conditioning_bank.json:7224b3b4-3355-45d4-811a-1040f0d0dca4` | Remove mech_reactive from tags and mechanical_risk_tags | “Conversational pace only. No sharp cutting or high-output defensive bursts.” | Remove unsupported rebound mechanism; explicit aerobic, footwork and low-CNS support classifications remain |
| MI-c53ebeb0917a (bounded accuracy follow-up) | Trap-Bar Pin Pull Isometric / `exercise_bank.json:179a855e-c1b6-4cbb-a74f-273e4d5f308c` | Remove mech_ballistic from both copies | Isometric against pins; 2–3×4–6s, full setup/rest | Remove false ballistic categories and 0.25 crisp-ballistic bonus; retain force-maintenance goal, moderate CNS cost, grip/hinge/bracing risks and D-7 cutoff |
| Same | Isometric Mid-Thigh Pull / `exercise_bank.json:60a85468-781a-47c0-857f-36ed7544654a` | Same | “fixed mid-thigh position”; 2–3×3–5s at maximal intent | Same; hand injury remains excluded by independent finger/pinch-load evidence |
| MI-b30c402ba17a | Slow-Lowered Pull-Up / `exercise_bank.json:57cbe600-bab4-4511-92f6-4e63ec1b350d` | low_eccentric true → false; eccentric_cost low → empty/unknown | Explicit eccentric movement/tag and slow-lowered execution; no quantified eccentric dose/cost evidence | Remove false low-eccentric bonus; existing missing-cost late-window policy fails conservatively. No guessed moderate/high cost or soreness/CNS backfill |

Both `tags` and `mechanical_risk_tags` remain compatible; only the disproven
mechanisms above are removed. No grip quality or power goal is deleted merely
because it overlaps a loading mechanism. Genuine plyometric step-up landing
and rebound risks remain intact. Ballistic rope slams remain ballistic; upper
body landing in plyometric push-ups is not relabelled as harmless.

## Actual consumers and authority

- `fightcamp/strength.py`: `generate_strength_block` reads source tags/costs;
  `_strength_contextual_risk_patterns` and `_evaluate_strength_late_window`
  classify ballistic/eccentric loading and score/deny late work;
  `_strength_metadata_score_adjustment` handles fatigue/cut costs. Existing
  classification categories and prescription authority are retained.
- `fightcamp/conditioning.py`: `generate_conditioning_block` reads the corrected
  sources; `_conditioning_mechanical_cost_is_high` and
  `_promote_lower_cost_conditioning_head` use actual impact/landing evidence for
  equal-dose conditioning ordering. `_evaluate_conditioning_late_window` still
  enforces phase, density, lactate, movement cost and countdown restrictions.
- `fightcamp/injury_filtering.py`: `injury_match_details` reads normalized mixed
  tags plus existing name-inferred mechanisms and injury aliases. Removing one
  false hit does not erase other exclusions. `mechanical_risk_tags` is not a
  substitute for those legacy mixed tags, so both copies stay synchronized.
- `fightcamp/bank_schema.py`: `validate_training_item` and
  `is_late_fight_metadata_safe` preserve the existing unknown-cost and late-window
  fail-safe. Real-generator tests include runtime schema validation.
- `fightcamp/training_context.py`, clinical/rehab policies and contact clearance
  remain unchanged. Discovery stays `prescription_allowed: false`.

## Explicitly deferred

Four individually examined source assignments remain REVIEW: Farmer Carry +
Battle Rope Combo (loaded carry/setup uncertain), Swimming Interval Pyramid
(wall/push-off and energy-system evidence insufficient), Reaction Ball Drills
(execution and high-CNS declaration insufficient), Hand-Fight to Snapdown
Reaction (grip quality versus supporting load). Their original metadata remains.
Numeric eccentric/soreness cost for Slow-Lowered Pull-Up also needs dose review.

Overlapping restrictions `avoid_if`, `contraindications` and
`block_if_fight_within_days` are retained as original source declarations: no
named generator consumer was found. Existing athlete restrictions, injury
rules and late-window policy are enforced independently. Free-text blood-pressure
or pain cautions are not converted into new clinical permission/exclusion rules.
The `Speed` versus `speed` goal mapping is also deferred: the existing distinct
Speed / Reaction input contract needs a separate reviewed migration.

## Preservation and verification

Seven manifest hashes and three existing equipment-review hashes are rebound
without changing permanent IDs, exercise/media keys or historical references.
Only five source fields change: `tags`, `mechanical_risk_tags`, `impact_cost`,
`low_eccentric` and `eccentric_cost`. All other rows/fields
are compared exactly. Original reports and baseline files remain unchanged.

A 6.4 KB, seven-record field-delta receipt supports exact historical replay;
it is tooling only, not a runtime taxonomy or an extra clinical registry. Replay
checks both row hashes and original whole-file hashes, rejecting unrelated edits.
PR #2825's original assertions replay its original equipment stage; new tests
separately compare actual Main before/after this stage.

Run `python -X utf8 -m pytest tests/test_mechanical_metadata_corrections.py` for
real-generator phase/fatigue/capacity/injury comparisons, exact dose/scoring
changes, all 2,855 identity/media checks and complete fixed-clock plans. Complete
plan outputs remain temporary and are not committed. Hosted full CI must pass
before merge; no deployment or merge is authorized by this report.

Local results: 168 new regressions passed (126 real-generator matrix cases,
28 injury comparisons, seven clinical restrictions and seven identity/semantic/
plan checks). All three full Main control plan texts and Stage 2 payloads match
exactly at UTC 2026-10-11 09:00, seed 7, Python hash seed 0. No full-plan
selection, prescription, rehab, scheduling or workload drift occurs in these
controls. Real-bank isometric candidates lose exactly 0.25 score and false
ballistic categories; their selected work and prescribed doses remain exact.
Existing schema gates still exclude rope work lacking late-window declarations;
removing false impact does not make those drills late-safe.

Ruff over api/fightcamp/tests/tools, bank validation, tag audit/migration and
authority checks passed. The bank validator reports existing metadata debt;
clearing the unsupported eccentric cost adds an intentional unknown-cost warning.
Broader regressions and hosted full CI are pending; no results are assumed.
