# Known case: 21-day amateur boxer, trunk-strength weakness

Anonymised scenario, reproduced deterministically with `repro/harness.py`
(`python repro/harness.py boxer '{}'` and `'{"foot": true}'`).

| Input | Value |
| --- | --- |
| Sport / status / record | Boxing, amateur, 0-0 |
| Fight | 21 days out (clock frozen 2026-01-04 12:00 UTC, fight 2026-01-25), 3 x 3 min |
| Weight / target | 68 kg → 65 kg (4.4 %, cut severity bucket `moderate`) |
| Goals | primary speed, secondary conditioning |
| Weakness | primary `trunk_strength` |
| Fatigue / frequency | low / 4 physical sessions per week (Mon–Sat available) |
| Hard sparring | Thursday |
| Injury variants | none; right foot pain, low severity, stable |
| Seed | 7 (seed 99 is identical) |

## 1. What the athlete gets (no injury)

| Week | D-day | Role | Closed membership |
| --- | --- | --- | --- |
| 1 SPP | D-20 Mon | transfer_strength_day | Box Jump · Band-Resisted Jab-Cross Primer · *Reactive Start Burst* (microdose) |
| | D-19 Tue | neural_plus_strength_day | Overcoming Split-Squat Isometric · Mobility Reset Flow |
| | D-17 Thu | hard_sparring_day | **hard as planned** |
| | D-15 Sat | fight_pace_repeatability_day | **— empty —** |
| 2 SPP (tail) | D-13 Tue | strength_touch_day | Pocket Frame-Burst Touch (style-taper primer) |
| | D-11 Thu | hard_sparring_day | technical (`d14_hard_sparring_ban`) |
| | D-10 Fri | light_fight_pace_touch_day | Tempo Shadowboxing |
| | D-7 Mon | neural_primer_day | Pull-Counter-Reset |
| 3 TAPER (tail) | D-5 / D-4 / D-2 / D-0 | alactic sharpness · technical contact · freshness · fight-day protocol | Pocket Frame-Burst Touch · — · Light Heavy-Bag Technical Tempo · protocol |

Plus support inserts (tactical watch, visualisation, breathing reset, aerobic
shadow flow, walk flush).

**No dedicated low-load trunk work appears anywhere.** The brief nevertheless
says "Primary limiter is trunk strength" and "Build speed while managing
trunk_strength", and records
`primary_weakness_disposition = {resolution: delegated, subsystem:
session_composition.trunk_support}`. Goal preservation lists only speed
(build, satisfied by the microdose) and conditioning (maintain, satisfied by
an 8-minute shadow-flow insert). No finding is raised anywhere — validator,
planner-authority gate and goal preservation are all clean.

The deliberate D-17 behaviour is intact: D-17 is hard, later Thursdays are
technical. Nothing in the trace below touches it.

## 2. Where the trunk work is lost — seven hops

Each hop alone would be survivable; together they guarantee zero trunk work.

1. **Intake → athlete model (OK).** `trunk_strength` survives parsing and the
   athlete model (`weaknesses: ["trunk_strength"]`). (Unlike a `strength`
   weakness, which F12 erases at ≤ 20 days.)
2. **Goal contract (gap).** `goal_preservation.primary_weakness_disposition`
   delegates it and, by design, creates no obligation and no verifier
   (F03). From here on no layer is accountable for trunk delivery.
3. **Stage 1 strength scoring (defect, F01).** `generate_strength_block` gets
   `weaknesses=["trunk_strength"]`, unexpanded. No bank entry has that tag, so
   no exercise earns a weakness hit.
4. **Stage 1 core-balance bonus (coverage gap, F02).** The bonus is active, but
   in the D-21…D-14 window only 2 of 67 core-balance entries are SPP- and
   window-eligible and neither is usable; 60 lack `late_windows` and are
   hard-blocked. SPP pool: 16 items, none core (`Dead-bug breathing` is
   `rehab_support`, which the classifier never counts as core). The TAPER pool
   does get *Kettlebell Suitcase Carry Hold*.
5. **Late tail (deliberate policy, hop closes).** D-13 and D-7 strength roles
   belong to the late tail; its builder prefers a style-taper sport primer over
   any strength slot, so the TAPER pool's suitcase carry is never used.
6. **Normal-camp strength composition (defect, F03).** Weight-cut pressure 1 →
   `effective_exercise_cap = 2` for both SPP roles; each role has two required
   family groups (power + strength), which consume both slots before the
   `preserve_trunk_support` branch is evaluated (`len(selected) < cap` is
   false). Trace (`repro/trace_trunk.py`): every candidate has
   `core_balance_support=False` anyway.
7. **Conditioning embedded trunk support (defect, F08 → F03).** The only
   normal-camp conditioning role (D-15 glycolytic) is empty, because the role
   map scheduled a glycolytic role that the Stage 1 pool could not fill (bridge
   rule: `glycolytic_touch_max = 0` at D-15 and with a declared hard day).
   The embedded add-on requires `workload_met`, so it records
   `embedded_trunk_support_skip_reason: conditioning_workload_unmet`.

Earliest originating stage: **Stage 1 candidate selection** (hop 3), enabled by
the **goal-contract delegation without a verifier** (hop 2). The first visible
symptom is in session composition.

## 3. Low, stable foot pain

Differences from the no-injury case:

- `transfer_strength_day` and `tissue_recovery_day` are suppressed
  (`active_weight_cut`, `injury_management`); week 1 has one strength session.
- That session is Punch-Specific Max Isometric Hold · **Jump Squat** ·
  **Reactive Start Burst** — a landing plyometric and a sprint start on a
  painful foot (F05, F06). The foot rule bans neither; the microdose is never
  injury-checked.
- Rehab inserts (`joint_prep`, `mobility_rehab`) appear; triage stays
  `full_plan`; sparring risk is `normal`, so D-17 stays hard — consistent with
  `docs/hard_sparring_cutoff.md` (low/stable injury does not elevate risk).
- Trunk work: still none.

## 4. Things in the known case that are working as intended

- D-17 hard, D-10/D-3 technical (resolver `hard_sparring_plan`).
- Late-tail ownership from D-13; fight-day protocol on D-0.
- Speed build covered in week 1 (by the microdose — but see F06/F07 for why
  that witness is not trustworthy).
- Determinism across seeds and repeated runs.

## 5. What a correct plan would minimally contain

Without changing any safety or taper rule: at least one low-load trunk drill
(e.g. Bird Dog Hold, Dead Bug (Isometric), Pallof Press Iso) embedded in a
week-1 SPP session and one more in week 2 at the embedded-support dose, and
either a real week-1 conditioning member or an explicit suppression of the
D-15 glycolytic role. The foot variant additionally must not contain landing
or sprint-start work.

## 6. Low-load trunk classifier probe (supports F04)

Running `_low_load_trunk_support_records` over every bank entry the strength
classifier marks `core_balance_support` accepts 39 items. Among them (with
the embedded prescription they would receive):

| Exercise | Equipment | Mechanical tags | Embedded prescription |
| --- | --- | --- | --- |
| Sled Push (Heavy) | sled | trunk_stability | 1-2 controlled sets x 3-5 slow reps |
| Sled Push (Incline) — **reproduced in S11** | sled | trunk_stability | 1-2 controlled sets x 3-5 slow reps |
| Yoke Walk | yoke | systemic_fatigue, trunk_stability | 1-2 controlled sets x 3-5 slow reps |
| Sledgehammer Strikes | sledgehammer | hip_hinge, systemic_fatigue, trunk_rotation | 1-2 controlled sets x 3-5 slow reps |
| Boxing Shuffle Drill (Ladder) | agility_ladder | systemic_fatigue | 1-2 controlled sets x 3-5 slow reps |
| Lateral Raise (Machine) | machine | shoulder_overhead | 1-2 controlled sets x 3-5 slow reps |
| Split-Stance Wall-Drive Isometric | wall | ballistic, cns_high, hinge_isometric | 1-2 controlled sets x 15-20 sec hold |
