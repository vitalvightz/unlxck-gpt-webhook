# Strength pool depth: findings and coach review list

Generated detail: `strength_pool_depth.md` / `.json` in this folder, from
`python tools/audit_strength_pool_depth.py --selection --step 5`. That run
covers 504 representative camps (GPP then SPP), every one with no injuries.
Nothing in the bank or selector was changed.

## Why the same strength exercises keep appearing

The selector is deterministic and takes the top of a scored pool. Earlier
attempts to change tie-breaking, in two forms, either moved the bias to
other exercises or reduced movement-category coverage, so neither shipped. The
lever is the pool itself: for many athletes it is barely larger than the slots
a phase must fill.

| Phase / equipment | Eligible anchors | Distinct exercises across 168 camps | Picked in ≥80% of camps |
|---|---|---|---|
| GPP / full gym | 38 | 46 | 7 |
| GPP / home (DB, KB, bands, bar) | 14 | 27 | 6 |
| GPP / minimal (bodyweight, bands) | **4** | 18 | 4 |
| SPP / full gym | 90 | 40 | 6 |
| SPP / home | 42 | 30 | 5 |
| SPP / minimal | 35 | 23 | 3 |

With 4 GPP anchors, a minimal-equipment athlete gets Cossack Squat, Cossack
Squat (Dynamic) and Single-Leg Forward Hops in 100% of camps. Mobility drills
fill the remaining GPP strength slots: Brettzel Stretch in 83%, Psoas March
(Banded) in 79%.

## Coverage gaps the planner currently ships

| Cell | Blocks missing a required category |
|---|---|
| GPP / minimal | upper-body push/pull: **168 of 168** |
| SPP / minimal | lower-body loaded: 52; unilateral: 5 |
| SPP / home | lower-body loaded: 36 |
| SPP / full gym | unilateral: **109 of 168** (selector issue, see below) |

## Decisions for a coach

1. **Add equipment-free upper-body strength work (GPP, and probably SPP).**
   Nothing in the bank counts as upper-body push/pull for a bodyweight-plus-bands
   athlete in GPP. Across all phases only three band power drills in SPP
   qualify. There is no plain push-up progression or band row strength row:
   Push-Up (Weighted) needs a vest, TRX Row needs a TRX, and pull-ups need a
   bar. Suggested new rows to author: a push-up progression (tempo,
   feet-elevated or deficit), a band row and a band press.
2. **Decide whether these existing SPP rows also belong in GPP.** Each would
   fill an empty or one-deep GPP/minimal cell:
   - Upper push/pull: Banded Row (Speed Focus), Band-Resisted Push Press,
     Judo Throw Simulation (Band-Resisted).
   - Unilateral: Single-Leg 45° Bound, Single-Leg Reactive Shuffle,
     Single-Leg Rotational Hop to Balance (moderate cost); Single-Leg Box Jump,
     Single-Leg Depth Drop (Stick Landing) (high cost, likely SPP-only on
     purpose).
3. **Decide whether Cossack Squat and Wall Sit (Knee-Friendly) also belong in
   SPP.** That would give SPP/minimal more than two lower-body-loaded options.
4. **Confirm what should count as "lower-body loaded".** Ten bodyweight rows
   satisfy that requirement today, including Wall Sit, Squat Hold (Parallel)
   and Wrestler Shot Drill (Repetitive). If a coach does not accept those as
   loaded work, the real gap for home and minimal athletes is larger than the
   table above shows.
5. **Merge the duplicate rows** "Band-Resisted Clinch Knee Strike" and "Clinch
   Knee Strike (Band-Resisted)". They are the same exercise twice and can fill
   two slots in one block.

## Engineering issues found (separate from metadata)

- **The selector mutates the shared bank cache.** `normalize_exercise_movement`
  writes the canonical movement back onto the cached row (`strength.py`), so a
  row's classification changes once any generation in the process has touched
  it. Plans can then depend on which plans were generated earlier in the same
  process. 23 rows flip; some flips are wrong for coverage. Couch Stretch and
  Single-Leg Wall Sit start counting as lower-body loaded, Chin tuck nod as
  upper-body push/pull, and Lateral Resisted Band Walk as a lower-body
  explosive anchor. The full table is in the generated report. This audit
  classifies in the normalized steady state, which is what a warm process
  converges to.
- **SPP full-gym blocks miss a unilateral exercise in 65% of camps** even though
  9 unilateral anchors are eligible. That points at base-category promotion,
  not pool depth.
- **The seeded tie-break shuffle in `generate_strength_block` has no effect.**
  The name sort in `sort_weighted_candidates` overrides it, and no client sends
  `random_seed`.
