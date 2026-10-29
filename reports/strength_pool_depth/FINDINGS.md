# Strength pool depth: findings, changes and remaining review list

Generated detail: `strength_pool_depth.md` / `.json` in this folder, from
`python tools/audit_strength_pool_depth.py --selection --step 5`. That run
covers 504 representative camps (GPP then SPP), every one with no injuries
and no seed. The tables below compare the bank before and after this branch.

## Why the same strength exercises kept appearing

The selector takes the top of a scored pool. For many athletes that pool was
barely larger than the slots a phase must fill. Tweaking the tie-break alone
(two variants were measured) either moved the bias to other exercises or
reduced category coverage. The levers that worked were the pool itself and a
seed that actually reaches the tie-break.

## What changed

**New rows** (bodyweight or bands): Tempo Push-Up (3-1-1), Feet-Elevated
Push-Up, Pike Push-Up, Band Bent-Over Row, Half-Kneeling Single-Arm Band Row,
Split Squat (Bodyweight Tempo 3-1-1). Their scoring tags are no richer than
the loaded lifts they stand in for, so gym athletes keep their loaded work.

**Phase change:** Bulgarian Split Squat gains GPP, so gym and home athletes
have a loaded single-leg squat in general prep.

**Seeded variation:** each self-serve request now carries a seed, derived from
athlete id and client request id, and that seed decides between equally rated
candidates. Previously the name sort decided for everyone.

| Phase / equipment | Eligible anchors | Picked in ≥80% of camps | Blocks missing a required category |
|---|---|---|---|
| GPP / full gym | 38 → 45 | 7 → 5 | unilateral 1 → **0** |
| GPP / home | 14 → 21 | 6 → 8 | 0 → 0 |
| GPP / minimal | **4 → 10** | 4 → 8 | upper-body push/pull **168 → 0** |
| SPP / full gym | 90 → 95 | 6 → 6 | unilateral 109 → 109 |
| SPP / home | 42 → 47 | 5 → 5 | lower-body loaded 36 → 36 |
| SPP / minimal | 35 → 40 | 3 → 3 | lower-body loaded 52 → 52 |

Full-gym blocks keep their loaded lifts: on average 13.9 → 14.4 loaded
exercises per GPP block. The new rows show up mainly where the pool was
thin. In full-gym GPP only Pike Push-Up appears often (43%); it fills the
vertical-push slot next to Z Press.

"Picked in ≥80%" rises for GPP minimal and home because the new push-ups and
band rows are now the expected choice for those athletes. That is suitability,
not repetition. Across seeds, the same athlete gets a different GPP block 5.5
times out of 6 (SPP 4.1 of 6), keeping about 88% of exercises between any two
seeds. Mean block score and size are unchanged. 2 of 1,008 seeded GPP blocks
missed a category, against 0 unseeded.

**Measured and dropped:**
- GPP for Single-Leg Rotational Hop to Balance: GPP then took it, and the
  GPP→SPP novelty rule removed SPP's main single-leg option (SPP blocks
  missing unilateral rose from 7 to 124 of 240).
- SPP for Wall Sit: it crowded out SPP single-leg work.
- SPP for Cossack Squat: no measurable effect.

## Still open for a coach

1. **SPP lower-body loaded for home and minimal athletes** (36 and 52 of 168
   blocks). Candidate: an equipment-free loaded or tempo single-leg squat that
   suits SPP.
2. **What counts as "lower-body loaded".** Ten bodyweight rows satisfy that
   requirement, including Wall Sit, Squat Hold (Parallel) and Wrestler Shot
   Drill (Repetitive). If a coach does not accept those as loaded, the real gap
   is larger.
3. **Duplicate rows**: "Band-Resisted Clinch Knee Strike" and "Clinch Knee
   Strike (Band-Resisted)" are the same exercise and can take two slots.

## Engineering notes

- **Bank movement normalization (fixed).** `normalize_exercise_movement` writes
  the canonical movement back onto the row. The production pipeline primes the
  bank first, so production was already consistent. Callers that skipped
  priming (tests, tools, direct `generate_strength_block` calls) could still
  get blocks that depended on earlier generations. The loader now normalizes
  as it reads. 23 rows classify differently under the authored and normalized
  movement, and some of those labels look wrong (Couch Stretch as lower-body
  loaded, Chin tuck nod as upper-body push/pull); see the generated report.
- **Classifier hint matching is substring-based.** For example, "switching"
  matches the pull hint "chin". New row notes were worded around it. Existing
  rows may be misclassified the same way.
- **SPP full-gym blocks miss a unilateral exercise in 65% of camps** even
  though 10 unilateral anchors are eligible. That points at base-category
  promotion, not pool depth.
- **Identical intakes still return the existing plan.** The same-payload
  duplicate guard ignores the seed, so resubmitting an unchanged intake while
  its plan is visible returns that plan, as before.
