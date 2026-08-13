# Lower-Body Plyometric Selection Audit

**Date:** 2026-08-11
**Base commit:** `1a5386d` (origin/Main)
**Scope:** Why Box Jumps, Jump Squats, bounds, hops and reactive jumps rarely reach generated fight-camp plans.
**Method:** Static trace of the real runtime path plus instrumented executions of `generate_strength_block`, `build_stage2_payload`, `is_late_fight_metadata_safe` and `calculate_phase_weeks` against the live banks. No code was changed.

---

## A. Executive verdict

**Yes — Unlxck is materially under-prescribing lower-body plyometrics, and the dominant cause is a system gap, not a sports-science decision.**

**Confidence: 9/10.**

The verdict is split by countdown position, and the two halves have different answers:

| Countdown | Behaviour | Verdict |
|---|---|---|
| Late-selector inactive (D-22 and earlier) | Plyos score at the **top of the pool** and take 4 of 8 strength slots | Working as intended |
| Late selector active (D-21 → D-1) | **Zero** lower-body plyos survive to scoring — 100% removed by one metadata gate | System gap |

At D-21 through D-8 the strength block for a healthy, fresh, fully-equipped athlete whose goal *and* weakness are both `power` is:

```
Staggered-Stance Medicine-Ball Punch Throw
Band-Resisted Jab-Cross Primer
Seated Medicine-Ball Punch Throw
Band Row Speed Focus
Mobility Reset Flow
90/90 hip switches
Adductor rock-back
Boxer stance weight-shift hold
```

That is exactly the failure mode described in the brief: med-ball punch throw, band punch, upper-body primer, isometric, core/mobility support — with lower-body explosive qualities entirely absent. It is produced by the runtime, not hypothesised.

The single confounder holding this at 9 rather than 10: at D-22+ the system genuinely does prescribe plyometrics well, so the problem is a **window** problem, not a blanket absence. In camps of 6 weeks or longer the athlete does get real plyometric exposure before D-21.

---

## B. Root causes, ranked

### 🔴 BLOCKER 1 — `late_block_missing_late_windows` is an unconditional hard block

`fightcamp/bank_schema.py:712-713`

```python
if "missing_late_windows" in unsafe_metadata:
    _append_code(block_codes, "late_block_missing_late_windows")
```

Any strength-bank item without a `late_windows` array is hard-blocked in **every** active late window (D-21 → D-1), regardless of its cost metadata, phase, impact profile or the athlete's state. In `strength.py:2070` a blocked late-eval `continue`s before the candidate is ever appended to `weighted_exercises`.

**Only 68 of 336 exercise-bank entries (20.2%) carry `late_windows`.** Every genuine lower-body plyometric is in the other 80%. The 68 that do carry it are almost entirely med-ball punch throws, band punch primers, isometrics and shadowboxing — which is precisely why those are what the athlete sees.

This is a **fail-closed default applied to a field that was never backfilled**, not a considered judgement that jumps are unsafe at D-20.

### 🔴 BLOCKER 2 — The phase/window dead zone is total in camps of 4 weeks or less

Traced through `camp_phases.calculate_phase_weeks`, not assumed:

| Camp | GPP/SPP/TAPER days | SPP covers | Plyo-eligible days |
|---|---|---|---|
| 21-day short notice | 0 / 14 / 7 | **D-21 → D-8** | **0** |
| 4 weeks | 7 / 14 / 7 | **D-21 → D-8** | **0** |
| 6 weeks | 14 / 14 / 14 | D-28 → D-15 | D-28 → D-22 (7 days) |
| 8 weeks | 21 / 21 / 14 | D-35 → D-15 | D-35 → D-22 (14 days) |
| 12 weeks | 35 / 35 / 14 | D-49 → D-15 | D-49 → D-22 (28 days) |

Every meaningful lower-body plyometric is `SPP`-only. In a 4-week or short-notice camp SPP begins at exactly D-21 — the same day the late selector activates. The two gates abut perfectly:

> Too early → blocked, exercise is SPP-only
> SPP opens → late selector is already active
> Late selector → blocked, exercise has no `late_windows`

**A 4-week or 21-day camp can contain literally zero lower-body plyometric exposure, at any fatigue level, with any equipment, for any goal.** This is the hypothesised accidental dead zone, confirmed in production code.

### 🔴 BLOCKER 3 — `box` is recognised by the backend but cannot be declared at intake

`box` appears in `training_context.known_equipment:87` but **not** in `web/lib/intake-options.ts:78-97` (`EQUIPMENT_ACCESS_OPTIONS`).

`equipment_score_adjust` (`strength.py:1131-1133`) returns `-999` when an exercise needs *known* equipment the athlete has not declared. Unknown tokens (`hurdles`, `cones`, `open_space`) only take `-1`. So `box` being half-registered is worse than not registering it at all — it converts a soft preference into a terminal exclusion.

Verified against the real function with a maximally-equipped intake selection (all 18 options ticked):

```
box            -> -999      barbell,box -> -999
kettlebell     -> -999      trap_bar    ->    0
hurdles        ->   -1      cones       ->   -1
```

**No user of the current web intake can reach any box exercise.**

### 🟠 MAJOR 4 — `kettlebell` / `kettlebells` token mismatch (collateral, same root cause)

Intake offers `kettlebells` (plural). The bank uses `kettlebell` (singular). `EQUIP_ALIASES` maps neither to the other, and `known_equipment` contains both. An athlete who explicitly ticks "Kettlebells" still gets `-999` on all 11 kettlebell exercises, including **Kettlebell Swing** — one of the few `GPP`+`SPP` lower-body power options in the bank.

Full terminal-unreachable inventory (known equipment absent from intake): `box` (11), `kettlebell` (11), `trx` (3), `bench` (3), `towel` (3), `agility_ladder` (2), `atlas_stone` (2), `neck_harness` (2), `plate` (2), `sledgehammer` (2), `swiss_ball` (2), `tire` (2), `weight_vest` (2), `foam_roller` (2), `bosu_ball` (1), `bulgarian_bag` (1), `log` (1), `step_mill` (1), `treadmill` (1), `water_jug` (1).

### 🟠 MAJOR 5 — 12 TAPER-only reactive microdoses are permanently unreachable

`data/conditioning_bank.json` contains a deliberately-authored late-camp reactive library — `Pogo Jump Series (Mini Bounce)`, `Low Box Jump (Fast Reset)`, `Mini Box Depth Drop`, `Snapdown to Quick Hop`, `Quick Lateral Hop Tap`, `Wall Reactive Jump (Cue Start)`, `Tuck Jump (Submax)`, `Split Stance Hop Switch`, `Band-Resisted Vertical Jump`, `Med Ball Drop Catch to Jump`, `Single-Leg Med Ball Toss Jump`, `Mini Hurdle Quick Steps`.

All are `phases: ["TAPER"]`, all carry proper dose (`6x3, 60s rest`, `3x10, 30s rest`), contact-time cues (`<150ms`) and stop rules — and **none has `late_windows`**. TAPER always falls inside the active late-window range, so these drills are **dead code**: verified blocked at `d21_to_d14`, `d13_to_d8` and `d7`.

Someone already built the microdose answer to this problem. The window gate makes it unreachable.

### 🟠 MAJOR 6 — No lower-body-power representation category exists

`strength_session_quality.missing_base_categories` balances exactly three categories:

```python
["lower_body_loaded", "upper_body_push_pull", "unilateral"]
```

There is no `lower_body_power`, no rotational-power and no upper-body-ballistic category. Nothing in the architecture notices that lower-body explosive work has vanished. Worse, `_loaded_pattern` matches on the substring `"squat"`, so **bodyweight Jump Squat is classified `lower_body_loaded`** — a jump can satisfy the loaded-strength representation requirement, and the reverse gap (no power representation) is never detected.

### 🟡 MODERATE 7 — `MOVEMENT_PATTERN_KEYWORDS` has no jump/hop/bound pattern

`strength.py:1430-1440` recognises squat, hinge, push, pull, lunge, rotation, carry, core, neck. **No jump, hop, bound, plyometric or triple-extension pattern exists.** 12 of 21 lower-body plyos resolve to `movement="unknown"`; others are actively miscategorised:

| Exercise | Detected movement | Correct |
|---|---|---|
| Ballistic Box Jump (Min Ground Contact) | `unknown` | jump |
| Single-Leg Box Jump | `unknown` | jump |
| Depth Jump (Stick Landing) | `unknown` | jump |
| Alternating Skater Hops | `unknown` | bound |
| Lateral Box Push-Off | **`push`** | lateral jump |
| Single-Leg 45° Bound | **`rotation`** | bound |
| Side Hop-to-Stabilize | **`core`** | hop |

Three consequences:

1. **Alternates are always empty.** `_build_strength_candidate_reservoir` buckets `unknown` under key `"strength_support"`, but `_build_strength_slots` sets `role = movement or "strength_support"` — and `"unknown"` is truthy, so the slot role is `"unknown"`. The lookup never matches. Confirmed in a real payload: `Ballistic Box Jump` and `Lateral Bound-to-Slip` both shipped with `alternates=[]` while every classified lift got two.
2. Reactive/ballistic work is pooled with support work under one `limit_per_role=4` cap.
3. `_apply_movement_caps` exempts `unknown` from the 2-per-movement cap, so unclassified plyos can stack while classified ones cannot — arbitrary, in both directions.

### 🟡 MODERATE 8 — Substring keyword `"ab"` misroutes 8 exercises to `core`

`MOVEMENT_PATTERN_KEYWORDS["core"] = ["core", "trunk", "ab"]`. Bare `"ab"` matches inside `Tabata`, `Stabilize`, `Cable`, `Alphabet` and `rehab_*` tags:

```
Burpee-to-Punch (Tabata)          -> core
Side Hop-to-Stabilize             -> core     (a lateral plyo)
Cable Fly (High to Low)           -> core
Four-way manual neck isometric    -> core     (should be neck)
```

### 🟡 MODERATE 9 — Hyphenated "Single-Leg" is invisible to unilateral detection

`_UNILATERAL_HINTS` contains `single_leg` and `single leg` but not `single-leg`, and `_collect_text` never includes `tags`. **32 exercises whose names begin "Single-Leg" fail to register the `unilateral` base category**, including every single-leg plyo (`Single-Leg Box Jump`, `Single-Leg Forward Hops`, `Single-Leg 45° Bound`, `Single-Leg Depth Drop`). Unilateral/lateral power is therefore invisible to the balancing mechanism.

### 🟡 MODERATE 10 — Plyometrics inherit strength-lift %1RM prescriptions

`_classify_prescription_type` routes on equipment first: anything with `barbell` or `trap_bar` gets the barbell template *before* any ballistic check.

| Exercise | Template | Prescription issued |
|---|---|---|
| Trap Bar Jump Squat | **barbell** | `3–5x3–5 @ 85–90% 1RM with contrast training` |
| Trap Bar Jump (Light) | **barbell** | `3–5x3–5 @ 85–90% 1RM` |
| Heavy RDL → Broad Jump | **barbell** | `3–5x3–5 @ 85–90% 1RM` |
| Back Squat → Box Jump | **barbell** | `3–5x3–5 @ 85–90% 1RM` |
| Single-Leg Box Jump | **general** | `2–3x6–10 @ RPE 6–7` |
| Box Jump / Jump Squat | ballistic | `4–6x2–5 reps at max speed; full rest 60–120s` ✅ |

A trap-bar jump squat prescribed at 85–90% 1RM is not a light prescription error — it is a different and unsafe exercise. `Single-Leg Box Jump` at 6–10 reps is well past the quality threshold for a high-impact unilateral jump. The `ballistic` template itself is reasonable but has no concept of total contacts, jump-height stop rule or landing fatigue — even though the bank's own `notes` carry exactly those cues (`"stop when jump height drops"`, `"Keep ground contact <150ms"`) and they are discarded.

### 🟢 MINOR 11 — Metadata inconsistencies in the bank

- `Depth Jump to Sprint` exists in **both** banks with contradictory equipment: `box` (strength) vs `[]` (conditioning). Same movement, two different gating outcomes.
- `Box Jump (Stick Landing)` in the conditioning bank needs no equipment; `Box Jump` in the strength bank requires `box`.
- `Chop Holds (Anti-Rotation)` and `Woodchopper (Cable)` carry `impact_cost: high, landing_cost: high` — implausible for a cable/KB anti-rotation hold, and enough to trip late-window impact penalties.
- `5-10-15 Ladder (Box Jumps/Push-Ups/KB Swings)` and `EMOM: 5 Squat Cleans + 5 Burpees` are classified `anchor_power` but are `category: finishers` — **conditioning masquerading as power work.**
- `Med-Ball Rotational Slam`, `Woodchopper (Cable)`, `Dynamic Plank-to-Punch` classify as `support_accessory` (−0.8 in SPP) because `_SUPPORT_HINTS` catches `core`/`trunk` before the power check. **Rotational power is systematically demoted to support.**
- `Reactive Band Taps (Partner)` classifies as `rehab_support` (−1.0 in SPP).
- `Trap Bar Jump Squat` and `Trap Bar Jump (Light)` are near-duplicates with identical cost metadata.
- `weighted_vest` (bank) vs `weight_vest` (`known_equipment`) — another silent token split.

### ⚪ NOT A PROBLEM — Scoring

Scoring is healthy and needs no change. See section F.

---

## C. Equipment findings

**1. Can a normal user currently declare access to a plyometric box?**
**No.** `EQUIPMENT_ACCESS_OPTIONS` has 18 entries and `box` is not among them. `plan-intake-form.tsx:1485` runs `retainKnownOptionValues(current[key], EQUIPMENT_ACCESS_OPTIONS)`, so free-text is impossible through the UI. The API (`api/models.py:574`) accepts arbitrary strings with no enum, so the backend would honour `box` if it ever arrived — the restriction is UI-only.

**2. Which exercises become practically impossible?**
All 11 box exercises, of which 8 are lower-body power:

`Box Jump` · `Ballistic Box Jump (Min Ground Contact)` · `Single-Leg Box Jump` · `Depth Jump (Stick Landing)` · `Depth Jump to Sprint` · `Single-Leg Depth Drop (Stick Landing)` · `Lateral Box Push-Off` · `Back Squat → Box Jump` · `5-10-15 Ladder` · `Single-Leg Step-Up Hold` · `Step-Up (Bodyweight)`

**3. Is `box` used elsewhere in the bank?** Yes — `Step-Up (Bodyweight)` and `Single-Leg Step-Up Hold (Mid-Range)` are non-plyometric box users, both equally unreachable.

**4. Should Box / Plyo Box become an explicit intake option?** **Yes.** It is the cheapest, most common gym item in the unreachable list, it already exists in `known_equipment`, and the backend needs no change.

**5. Sensible aliases?** Yes, but narrowly:

| Alias | → canonical | Rationale |
|---|---|---|
| `plyo_box`, `plyo box`, `jump box`, `plyometric box` | `box` | Unambiguous synonyms |
| `kettlebells` | `kettlebell` | **Fixes a live bug** |
| `weighted_vest` | `weight_vest` | Fixes a silent split |
| `dumbbell` ↔ `dumbbells` | — | Verify parity while in there |

**Explicitly do NOT alias:** `step`, `bench`, `stair`, `chair` → `box`. A bench is not a safe landing surface and the brief is right to call this out. `Step-Up` and `Box Jump` have different surface requirements and must not share a token. If step-ups should be reachable without a plyo box, that is a separate `step`/`bench` intake option, not an alias.

**Sequencing note:** adding `box` to intake fixes nothing from D-21 onward — the late-window block removes those exercises before equipment is even consulted. Verified: the D-21→D-8 output is byte-identical with and without box. Equipment is a real bug, but it is the *second* gate.

---

## D. Exercise-by-exercise audit

All lower-body plyometric / ballistic / reactive entries in `data/exercise_bank.json`. **Every one has `late_windows: none`.** "Availability" is for a healthy, fresh, no-cut athlete with full declared equipment.

| Exercise | Phase | Equipment | Impact | Ecc | Landing | CNS | Soreness | `late_windows` | Current likely availability |
|---|---|---|---|---|---|---|---|---|---|
| **Box Jump** | SPP | `box` | mod | low | mod | high | low | — | ❌ Never (no box at intake) + blocked D-21→D-1 |
| **Jump Squat** | SPP | bodyweight | mod | low | mod | high | low | — | ✅ D-22+ only (**top scorer, 3.85**) |
| **Trap Bar Jump Squat** | SPP | trap_bar | mod | mod | mod | high | high | — | ✅ D-22+ only (3.85) — but bad dose |
| **Trap Bar Jump (Light)** | SPP | trap_bar | mod | mod | mod | high | high | — | ⚠️ D-22+, near-dup, loses on cap |
| **Ballistic Box Jump (Min Ground Contact)** | SPP | `box` | mod | low | mod | high | mod | — | ❌ Never (box) + `high_movement_cost` |
| **Single-Leg Box Jump** | SPP | `box` | high | mod | high | high | low | — | ❌ Never (box) |
| **Depth Jump (Stick Landing)** | SPP | `box` | mod | low | mod | high | low | — | ❌ Never (box) |
| **Depth Jump to Sprint** | SPP | `box` | mod | low | mod | high | low | — | ❌ Never (box); conditioning twin needs none |
| **Single-Leg Depth Drop (Stick Landing)** | SPP | `box` | high | mod | high | mod | low | — | ❌ Never (box) |
| **Staggered-Stance Reactive Jumps** | SPP | bodyweight | high | mod | high | high | low | — | ⚠️ D-22+ only; loses on score |
| **Jump Lunge (Alternating)** | SPP | bodyweight | high | mod | high | mod | low | — | ⚠️ D-22+ only |
| **Alternating Skater Hops** | SPP | bodyweight | high | mod | high | mod | low | — | ✅ D-22+ (selected under moderate fatigue) |
| **Drop-Step Lateral Bound** | SPP | bodyweight | high | mod | high | mod | low | — | ⚠️ D-22+ only |
| **Lateral Bound-to-Slip** | SPP | bodyweight | high | mod | high | mod | low | — | ✅ D-22+ (selected) |
| **Single-Leg 45° Bound** | SPP | bodyweight | high | mod | high | mod | low | — | ⚠️ D-22+ only |
| **Single-Leg Forward Hops** | GPP, SPP | bodyweight | high | mod | high | mod | low | — | ⚠️ Only GPP-reachable LB plyo — and it's high-impact unilateral |
| **Single-Leg Lateral Hops** | GPP, SPP | `agility_ladder` | high | mod | high | mod | low | — | ❌ Never (equipment) |
| **Single-Leg Zig-Zag Hops** | GPP, SPP | `cones` | high | mod | high | mod | low | — | ⚠️ −1 soft penalty only |
| **Heavy RDL → Broad Jump** | SPP | barbell | mod | **high** | mod | high | **high** | — | ✅ D-22+ (2.95) — but %1RM dose |
| **Back Squat → Box Jump** | SPP | barbell,`box` | mod | low | mod | high | low | — | ❌ Never (box) |
| **Jump-in-Place (Max Frequency)** | SPP | bodyweight | mod | low | mod | high | low | — | ⚠️ D-22+ only |
| **Lateral Lunge (Plyometric)** | SPP | bodyweight | high | mod | high | mod | low | — | ⚠️ D-22+ only |
| **Lateral Box Push-Off** | SPP | `box` | high | mod | high | high | low | — | ❌ Never (box); misclassed `push` |
| **Side Hop-to-Stabilize** | SPP | `line/tape` | high | mod | high | mod | low | — | ⚠️ −1 only; misclassed `core` |
| **Rapid Hurdle Hops (2-foot)** | SPP | `hurdles` | mod | **high** | mod | high | mod | — | ⚠️ −1 only |
| **Reactive Hurdle Hop (Single-Leg)** | SPP | `hurdles` | high | **high** | high | high | mod | — | ⚠️ −1 only |
| **Band-Resisted Reaction Hop** | SPP | bands | high | mod | high | high | low | — | ⚠️ D-22+ only |
| **Plyometric Shadow Boxing** | SPP | bodyweight | high | mod | high | high | low | — | ⚠️ D-22+ only |
| **Single-Leg Medicine Ball Chest Push Jump** | SPP | medicine_ball | high | mod | high | mod | low | — | ⚠️ D-22+ only |
| **Single-Leg Reactive Shuffle** | SPP | bodyweight | high | mod | high | mod | low | — | ⚠️ D-22+ only |
| **Single-Leg Rotational Hop to Balance** | SPP | bodyweight | high | mod | high | mod | low | — | ⚠️ D-22+ only |
| **Speed Box Squat** | SPP | barbell | low | mod | none | high | **high** | — | ⚠️ D-22+; loses on squat cap |
| **Kettlebell Swing** | GPP, SPP | `kettlebell` | low | mod | none | high | mod | — | ❌ Never (token mismatch bug) |
| **5-10-15 Ladder (Box Jumps/…)** | SPP | `box`/`kettlebell` | mod | low | mod | mod | mod | — | ❌ Never — **and is conditioning, not power** |

### Flagged issues

**Duplicates / near-duplicates:** `Depth Jump to Sprint` (cross-bank, contradictory equipment) · `Trap Bar Jump Squat` ≈ `Trap Bar Jump (Light)` · `Box Jump` ≈ `Ballistic Box Jump` ≈ `Back Squat → Box Jump` (three box-jump variants, all unreachable) · `Lateral Bound-to-Slip` ≈ `Drop-Step Lateral Bound`.

**Misleading metadata:** `Jump Squat` (bodyweight, low soreness, low eccentric) carries `cns_load: high` — same CNS rating as `Hang Power Clean` and `EMOM: 5 Squat Cleans + 5 Burpees`. Since `cns_load: high` denies the `late_strength_boost_cns_freshness` bonus and triggers cut-pressure penalties, this over-severity would suppress the single best low-cost bilateral plyo even after the window block is fixed. `Chop Holds` / `Woodchopper` carry `impact_cost: high, landing_cost: high` with no impact or landing.

**Missing tags:** all 34 lack `late_windows`, `phase_role`, `stress_class`, `cost_class`, `support_only`, `meaningful_stress`, `sport_specific`. No plyo carries `ballistic_low_volume`, `neural_primer` or `low_impact` — the exact tags the late-window scorer rewards.

**Conditioning masquerading as power:** `5-10-15 Ladder`, `EMOM: 5 Squat Cleans + 5 Burpees`, `Burpee-to-Punch (Tabata)`, `Sprawl-to-Burpee` — all `category: finishers`/`combat`, all reaching the strength pool as `anchor_power`.

**Too aggressive to justify later-camp access:** `Depth Jump (Stick Landing)`, `Depth Jump to Sprint`, `Single-Leg Depth Drop`, `Reactive Hurdle Hop (Single-Leg)` (impact+eccentric+landing+CNS all high), `Heavy RDL → Broad Jump` (eccentric high, soreness high), `Back Squat → Box Jump`, `Trap Bar Jump Squat`.

---

## E. Phase / window recommendations

Deliberately conservative. Nothing is extended merely for being labelled plyometric. **Only 7 of 34 exercises are recommended for any late window, and none past D-8.**

### Group A — Reasonably suitable into D-13→D-8

| Exercise | Current | Recommended | Reason |
|---|---|---|---|
| Jump Squat | SPP, none | **+GPP; `[d21_to_d14, d13_to_d8]`** | Bodyweight, `eccentric_cost: low`, `soreness_risk: low`, bilateral, no learning curve, bank note already specifies `3-5x3, stop when height drops`. The single best low-cost bilateral option. Requires correcting `cns_load: high` → `moderate`. |
| Box Jump | SPP, none | **+GPP; `[d21_to_d14, d13_to_d8]`** | Concentric-dominant by design; `eccentric_cost: low`, `soreness_risk: low`, `landing_cost: moderate`. Lower landing cost than a bodyweight jump squat because the box absorbs the descent. Gated on box intake. |
| Jump-in-Place (Max Frequency) | SPP, none | **`[d21_to_d14, d13_to_d8]`** | Low amplitude, `eccentric_cost: low`, minimal complexity. |

### Group B — Should stop earlier (D-21→D-14 ceiling, or no late access)

| Exercise | Current | Recommended | Reason |
|---|---|---|---|
| Trap Bar Jump (Light) | SPP, none | **`[d21_to_d14]` only** | Loaded jump; `soreness_risk: high`. Already penalised by `late_strength_penalty_jump_landing`. |
| Alternating Skater Hops | SPP, none | **`[d21_to_d14]` only** | `impact/landing: high`, but low soreness and genuinely sport-relevant lateral power. |
| Lateral Bound-to-Slip | SPP, none | **`[d21_to_d14]` only** | Same, plus boxing-specific transfer. |
| Drop-Step Lateral Bound | SPP, none | **`[d21_to_d14]` only** | Same profile. |
| **Depth Jump (Stick Landing)** | SPP, none | **no late access — keep as-is** | Highest-eccentric plyometric class. Correctly excluded. |
| **Depth Jump to Sprint** | SPP, none | **no late access — keep as-is** | Depth jump + max sprint. Correctly excluded. |
| **Single-Leg Depth Drop** | SPP, none | **no late access — keep as-is** | Unilateral landing under gravity load. |
| **Reactive Hurdle Hop (Single-Leg)** | SPP, none | **no late access — keep as-is** | Impact/eccentric/landing/CNS all high. |
| **Heavy RDL → Broad Jump** | SPP, none | **no late access — keep as-is** | `eccentric_cost: high`, `soreness_risk: high`. Named in the brief as correctly conservative. |
| **Back Squat → Box Jump** | SPP, none | **no late access — keep as-is** | Heavy contrast pair. |
| **Trap Bar Jump Squat** | SPP, none | **no late access — keep as-is** | `soreness_risk: high`, loaded. |
| **Jump Lunge (Alternating)** | SPP, none | **no late access — keep as-is** | Named in the brief; high landing under cut/fatigue. |
| **Single-Leg Box Jump / 45° Bound / Forward Hops / Zig-Zag / Rotational Hop** | SPP, none | **no late access — keep as-is** | Repeated single-leg high-impact. Already balance-blocked under high cut. |
| **Staggered-Stance Reactive Jumps** | SPP, none | **no late access** | `impact/landing/CNS` all high — despite the "reactive" label. |

### Group C — Genuinely justified microdoses (conditioning bank)

These are the only items justifying access inside D-7, and only because they were authored for exactly that purpose with contact-count dose already specified.

| Exercise | Current | Recommended | Reason |
|---|---|---|---|
| Pogo Jump Series (Mini Bounce) | TAPER, none → **unreachable** | **`[d13_to_d8, d7]`** | `3x10, 30s rest`, `<150ms` contact, ankle-stiffness only. Needs `impact_cost: high` → `low`/`moderate` review — the current value is amplitude-blind. |
| Low Box Jump (Fast Reset) | TAPER, none → **unreachable** | **`[d13_to_d8, d7]`** | `6x3, 60s rest`, 12–18″ box, snap-down focus. |
| Quick Lateral Hop Tap | TAPER, none → **unreachable** | **`[d13_to_d8, d7]`** | Minimal amplitude. |
| Snapdown to Quick Hop | TAPER, none → **unreachable** | **`[d13_to_d8]`** | Slightly higher demand. |
| Mini Box Depth Drop / Tuck Jump (Submax) / Wall Reactive Jump | TAPER, none → unreachable | **`[d13_to_d8]` only** | Real landing load; not D-7 material. |

**D-6 → D-1: no lower-body plyometric of any kind.** Current behaviour is correct and should not change.

### GPP correction

Today the **only** GPP-reachable lower-body plyo is `Single-Leg Forward Hops` — high impact, high landing, unilateral. The safest bilateral entry-level options (Box Jump, Jump Squat, Broad Jump) are locked out of GPP entirely. This is backwards: GPP is where an athlete should build landing competence on bilateral, low-complexity jumps before progressing to unilateral hops in SPP. Recommend adding `GPP` to `Jump Squat` and `Box Jump`, and considering removing `GPP` from `Single-Leg Lateral Hops` / `Single-Leg Zig-Zag Hops`.

---

## F. Selector scoring findings

**Scoring is not the problem. Do not change it.**

Full ranked pool, Athlete A (healthy, low fatigue, no cut, goal=power, weakness=power, full equipment incl. box, SPP, D-28):

```
  1.  3.850  Jump Squat                              anchor_power  [LB-PLYO]  <== SELECTED
  2.  3.850  Trap Bar Jump Squat                     anchor_power  [LB-PLYO]  <== SELECTED
  3.  3.150  Box Jump                                anchor_power  [LB-PLYO]
  4.  3.150  Speed Box Squat                         anchor_power
  5.  2.950  Heavy RDL → Broad Jump                  anchor_power  [LB-PLYO]  <== SELECTED
  6.  2.550  Banded Row (Speed Focus)                anchor_power             <== SELECTED
  7.  2.450  Back Squat → Box Jump                   anchor_power  [LB-PLYO]
  8.  2.550  High Pull                               anchor_power             <== SELECTED
  9.  2.050  Alternating Skater Hops                 anchor_power  [LB-PLYO]
 10.  2.050  Ballistic Box Jump (Min Ground Contact) anchor_power  [LB-PLYO]  <== SELECTED
```

Lower-body plyos occupy **5 of the top 10** and take **4 of 8** selected slots. `strength_quality_adjustment` gives `anchor_power` +0.9 in SPP; `must_have_by_phase["SPP"]` includes `explosive` and `rate_of_force`; `GOAL_TAG_MAP["power"]` matches cleanly.

**Box Jump specifically: eligible, competitive, and loses fairly — but not on score.** At 3.15 it ranks 3rd overall. It is displaced by `_apply_movement_caps`, which allows max 2 per movement: `Jump Squat` and `Trap Bar Jump Squat` (both `movement="squat"`) take both squat slots first. `Speed Box Squat`, tied at 3.15, is displaced identically. This is legitimate diversity behaviour and needs no change — though note it is a **cap** loss, not a scoring loss.

**Per-athlete results:**

| Athlete | Config | Lower-body plyos selected |
|---|---|---|
| **A** | healthy, low fatigue, no cut, power/power, full equip, SPP D-28 | **4** — Jump Squat 3.85, Trap Bar Jump Squat 3.85, Heavy RDL→Broad Jump 2.95, Ballistic Box Jump 2.05 |
| **B** | same, goal=strength | **4** — Heavy RDL→Broad Jump 2.95, Jump Squat 2.55, Back Squat→Box Jump 2.45, Ballistic Box Jump 2.05 |
| **C** | same as A, moderate fatigue | **4** — uniform −0.35; ordering shifts (Alternating Skater Hops enters, Ballistic Box Jump exits) |
| **D** | same as A, 8% weight cut | **3** — uniform decay to 1.75/0.85; med-ball work rises appropriately |
| **E** | same as A, **D-12** | **0** — all 22 removed pre-scoring by `late_block_missing_late_windows` |

Athletes A–D behave sensibly and prove the scoring architecture works. **Athlete E is the failure.** The gap between B (goal=strength still yields 4 plyos) and E (goal=power yields 0) shows the outcome is driven entirely by countdown position, not by athlete intent.

**Answer to the brief's framing:** *both* — and the distinction is temporal.
- **D-22 and earlier: Box Jump is eligible and loses fairly** (movement cap, near-tie).
- **D-21 and later: Box Jump never gets to compete.** Not one lower-body plyo reaches `score_exercise`.

Countdown sweep (healthy boxing athlete, goal=power, weakness=power):

| Day | Phase | Window | LB plyos reaching scoring | LB plyos selected | Blocking reason |
|---|---|---|---|---|---|
| D-28 | SPP | `control_d28` | **22** | **4** | — |
| D-21 | SPP | `d21_to_d14` | **0** | 0 | `late_block_missing_late_windows` ×22 |
| D-18 | SPP | `d21_to_d14` | **0** | 0 | same ×22 |
| D-14 | SPP | `d21_to_d14` | **0** | 0 | same ×22 |
| D-13 | SPP | `d13_to_d8` | **0** | 0 | same ×21 (+`high_movement_cost` ×1) |
| D-10 | SPP | `d13_to_d8` | **0** | 0 | same |
| D-8 | SPP | `d13_to_d8` | **0** | 0 | same |
| D-7 | TAPER | `d7` | **0** | 0 | no TAPER-phase plyo exists in the strength bank |

Without box declared the D-21→D-7 rows are **identical** — the window block already removed everything. Only D-28 changes (22 → 15 candidates reaching scoring; `Ballistic Box Jump` drops out of the selection).

---

## G. Stage 2 findings

**Stage 2 is not the problem. It faithfully carries whatever Stage 1 gives it.**

Verified by building a real payload from the D-28 Athlete A block. All 8 Stage 1 selections became `strength_slots` with correct `quality_class: anchor_power` and `anchor_capable: true`:

```
role=squat    anchor_power  Jump Squat              req_equip=['bodyweight'] alts=['Box Jump','Speed Box Squat']
role=squat    anchor_power  Trap Bar Jump Squat     req_equip=['trap_bar']   alts=['Box Jump','Speed Box Squat']
role=hinge    anchor_power  Heavy RDL → Broad Jump  req_equip=['barbell']    alts=[...]
role=unknown  anchor_power  Lateral Bound-to-Slip   req_equip=['bodyweight'] alts=[]      <-- empty
role=unknown  anchor_power  Ballistic Box Jump      req_equip=['box']        alts=[]      <-- empty
```

**No LLM bias toward med-ball or band work exists in the instructions.** The med-ball/band monoculture at D-21→D-8 is inherited from Stage 1, not introduced by Stage 2. Every `jumps` reference in Stage 2 is a *prohibition* (`_CROWDED_ANCHOR_FORBIDDEN_TOKENS`, D-1 forbid list) — appropriate, and there is no corresponding positive representation.

Three genuine Stage 2 weaknesses:

1. **Empty alternates for unclassified plyos** (root cause §B-7): `_build_strength_candidate_reservoir` keys `unknown` movements as `"strength_support"` while `_build_strength_slots` keys them as `"unknown"`. If the LLM rejects the selected option there is no in-role substitute, so the slot is likelier to be dropped.
2. **No `must_keep` requirement covers lower-body power.** The vocabulary is `rehab`, `aerobic`, `glycolytic`, `alactic`, `primary_strength`. `primary_strength` maps to `strength_slots[:1]` only — so a plyo is protected only if it happens to be the first slot, and even then the enforcement is `severity: "warning"`, not a hard repair.
3. `Ballistic Box Jump` ships with `required_equipment: ['box']` and `universally_available: false` while the athlete could never have declared box — an unreachable state that only arises because of §B-3.

---

## H. Recommended fixes

### MUST FIX — correctness and system gaps

**H1. Stop `missing_late_windows` from being an unconditional hard block.**
The fail-closed default is right for unaudited items but wrong as a permanent state for 80% of the bank. Two options; H1a is preferred as the smaller change:

- **H1a (preferred):** backfill `late_windows` on the exercises in §E. Explicit `late_windows: []` should mean "audited, never late" and remain a block; *absent* should downgrade to a penalty for items that carry complete cost metadata (`impact_cost`, `eccentric_cost`, `landing_cost`, `cns_load`, `soreness_risk` all present), which all 34 plyos do.
- **H1b:** keep the block but treat complete cost metadata as sufficient evidence, deriving eligibility from cost levels rather than requiring the field.

Either way the D-6→D-1 lockdown must survive untouched.

**H2. Close the phase/window dead zone.** Add `GPP` to `Jump Squat` and `Box Jump` (§E). Independently of H1 this restores plyometric exposure to 6-week+ camps' GPP block; combined with H1 it removes the ≤4-week blackout.

**H3. Add "Plyo Box" to `EQUIPMENT_ACCESS_OPTIONS`.** One line in `web/lib/intake-options.ts`. No backend change needed. Unblocks 11 exercises, 8 of them lower-body power.

**H4. Fix the `kettlebells` → `kettlebell` alias.** Live bug: athletes who declare kettlebells get `-999` on all 11 kettlebell exercises. Also add `weighted_vest` → `weight_vest`. One-line additions to `EQUIP_ALIASES`.

**H5. Fix the reservoir/slot role-key mismatch.** `_build_strength_slots` should map `movement == "unknown"` → `"strength_support"`, matching `_build_strength_candidate_reservoir`. Currently guarantees zero alternates for the exercises least able to afford it.

**H6. Stop routing plyometrics through the barbell %1RM template.** In `_classify_prescription_type`, check ballistic/plyometric signals (`method == "plyometric"`, `mech_lower_jump`, `mech_ballistic`, `explosive`) **before** the equipment check. `Trap Bar Jump Squat @ 85–90% 1RM` is a safety defect, not a formatting one.

**H7. Decide `Depth Jump to Sprint`'s equipment.** Contradictory across banks (`box` vs `[]`). Same for `Box Jump` vs `Box Jump (Stick Landing)`.

### SHOULD FIX — better representation

**H8. Add jump/hop/bound to `MOVEMENT_PATTERN_KEYWORDS`.** A `jump` pattern (`jump`, `hop`, `bound`, `plyometric`, `depth`, `pogo`, `skater`) removes 12 `unknown` classifications and un-breaks the movement cap in both directions. Fixes `Lateral Box Push-Off → push` and `Single-Leg 45° Bound → rotation`.

**H9. Remove the bare `"ab"` keyword** from the `core` pattern; use `abs`, `ab wheel`, `ab rollout`. Currently miscategorises 8 exercises including a lateral plyo and three neck-rehab drills.

**H10. Add `single-leg` (hyphenated) to `_UNILATERAL_HINTS`,** and include `tags` in `_collect_text`. Restores the `unilateral` base category to 32 exercises.

**H11. Add a `lower_body_power` base category** to `missing_base_categories`. **Not a quota** — the same soft representation mechanism already used for `lower_body_loaded`, satisfied by any anchor_power lower-body item, and only when one is eligible and competitive. Also tighten `_loaded_pattern` so a bodyweight Jump Squat stops satisfying `lower_body_loaded`.

**H12. Reclassify conditioning-as-power.** `5-10-15 Ladder`, `EMOM: 5 Squat Cleans + 5 Burpees`, `Burpee-to-Punch (Tabata)`, `Sprawl-to-Burpee` should not enter the strength pool as `anchor_power`.

**H13. Let power beat support for rotational work.** Check power tags before `_SUPPORT_HINTS` so `Med-Ball Rotational Slam` and `Woodchopper` stop taking the −0.8 SPP support penalty.

**H14. Re-review over-severe cost metadata.** `Jump Squat cns_load: high` (equal to Hang Power Clean); `Chop Holds` / `Woodchopper` `impact_cost: high, landing_cost: high` with no impact or landing; `Pogo Jump Series impact_cost: high` for a mini bounce. **Do not treat low eccentric cost as zero fatigue** — Jump Squat should move `high → moderate`, not to `low`.

**H15. Give plyometric prescriptions a contacts concept.** A `plyometric` template with total contacts, reps/set, sets, rest, and a quality stop-rule, tapering `D-21→D-14` normal → `D-13→D-8` reduced → `D-7` microdose only → `D-1` none. The bank's own notes already carry the cues (`"stop when jump height drops"`, `"Keep ground contact <150ms"`, `"Disable if vertical jump drops >10%"`) — surface them rather than building a second taper system.

**H16. Unlock the TAPER-only reactive microdose library** (§E group C) once H1 lands — 12 authored, well-dosed drills currently dead.

### LEAVE ALONE — justified conservatism

- **D-6 → D-1 total plyometric lockout.** Correct.
- **`late_strength_penalty_jump_landing` / `late_strength_block_trap_bar_jump`** across all late windows. Correct for loaded jumps.
- **`late_strength_block_high_cut_balance_risk`** hard-blocking single-leg/balance work under high cut. Correct — do not weaken.
- **`late_strength_block_eccentric_lower`** and the depth-jump/high-eccentric exclusions. Correct.
- **Heavy contrast pairs** (`Heavy RDL → Broad Jump`, `Back Squat → Box Jump`) with no late access. Correct; explicitly endorsed by the brief.
- **`late_strength_block_familiarity_required_late`** from D-13. Correct.
- **`_apply_movement_caps` 2-per-movement.** Correct — Box Jump losing the 3rd squat slot is good behaviour.
- **Cut-pressure penalty stack** (`cut_pressure_landing_impact`, `cut_pressure_dense_ballistic`). Correct.
- **D-1 `d1_ok` tag + zero-equipment requirement.** Correct.
- **Stage 2 `jumps` prohibitions** on crowded-anchor days and D-1. Correct.
- **Scoring architecture and `NEAR_EQUAL_SCORE_BAND` restraint.** Working; preserve.

**Inconsistencies (neither clearly over- nor under-conservative):**
- `Single-Leg Forward Hops` (high impact, high landing, unilateral) is GPP-legal while bodyweight `Jump Squat` (moderate/moderate, bilateral) is not.
- `Rapid Hurdle Hops` and `Side Hop-to-Stabilize` take only a `-1` equipment penalty because `hurdles`/`line`/`tape` are unknown tokens, while the safer `Box Jump` is terminally excluded. Severity is inverted relative to risk.
- `Ballistic Box Jump` takes an extra `late_block_high_movement_cost` from `movement_cost: high` while the more demanding `Depth Jump` is rated `moderate`.

---

## I. Proposed tests

To add **before** implementation, so each fix is pinned by a failing test first.

### Equipment

```
test_plyo_box_is_declarable_at_intake
  EQUIPMENT_ACCESS_OPTIONS contains a box option; its value is in known_equipment.

test_every_known_equipment_token_is_reachable_from_intake
  Parity guard: for each token in known_equipment used by >=1 bank exercise,
  either it is selectable at intake or it is on an explicit
  DELIBERATELY_UNREACHABLE allowlist. Prevents new -999 tokens.

test_kettlebells_intake_token_normalizes_to_kettlebell
  equipment_score_adjust("kettlebell", ["kettlebells"], known_equipment) == 0.   [fails today]

test_box_jump_selectable_with_box_access
  Healthy SPP power athlete, D-28, box declared -> Box Jump reaches scoring
  with score > 0.

test_box_jump_absent_without_box_access
  Same athlete without box -> Box Jump never appears in selections,
  reservoir or Stage 2 slots.

test_bench_does_not_satisfy_box_requirement
  Declaring bench must NOT make box exercises eligible.
```

### Phase and window

```
test_four_week_camp_has_a_plyo_eligible_window
  21- and 28-day camps: at least one countdown day where a lower-body plyo
  reaches scoring.                                                  [fails today]

test_bilateral_plyo_available_in_gpp
  Jump Squat and Box Jump are GPP-eligible.                         [fails today]

test_taper_only_items_are_reachable_in_some_window
  No bank item may be phases:[TAPER] with no late_windows — that combination
  is unreachable by construction.                                   [fails today,
                                                                     12 items]

test_low_cost_bilateral_plyo_survives_d13_to_d8
  Healthy, no-cut, low-fatigue athlete at D-10 -> at least one low-cost
  bilateral plyo reaches scoring.                                   [fails today]
```

### Late-window safety (must stay green — regression guards)

```
test_depth_jumps_never_available_inside_d21
  Depth Jump (Stick Landing), Depth Jump to Sprint, Single-Leg Depth Drop
  blocked in every active late window.

test_high_impact_unilateral_plyos_blocked_from_d13
  Single-Leg Box Jump / 45° Bound / Reactive Hurdle Hop blocked D-13 onward.

test_no_lower_body_plyo_from_d6_to_d1
  Sweep D-6..D-1: zero lower-body plyometrics under any athlete config.

test_loaded_jump_variants_blocked_late
  Trap Bar Jump Squat / Trap Bar Jump (Light) keep late_strength_block_trap_bar_jump.

test_contrast_pairs_have_no_late_access
  Heavy RDL → Broad Jump, Back Squat → Box Jump blocked in all late windows.

test_high_cut_blocks_single_leg_plyos
  8% cut at D-12 -> all single-leg plyos blocked on balance risk.

test_plyos_suppressed_under_high_fatigue
  fatigue="high" -> high-impact plyos do not out-rank low-cost options.
```

### Competition, not forcing

```
test_bilateral_plyo_competes_without_being_forced
  Healthy SPP power athlete -> >=1 lower-body plyo selected on merit; assert
  it won on score/cap ordering, NOT via a promotion or quota path.

test_no_mandatory_plyo_quota
  Athlete with no box, high fatigue, heavy cut, knee injury -> zero plyos,
  and generation still succeeds.

test_box_jump_loses_to_higher_scoring_peer
  Pins the movement-cap behaviour: Box Jump at 3.15 correctly yields the
  third squat slot.
```

### Classification

```
test_jumps_hops_bounds_classify_as_anchor_power
  Every plyo-named lower-body exercise -> quality_class == "anchor_power".

test_jump_movement_pattern_detected
  Box Jump/Ballistic Box Jump/Skater Hops/Depth Jump -> movement == "jump",
  not "unknown"/"push"/"rotation"/"core".                            [fails today]

test_core_keyword_does_not_match_ab_substring
  Tabata / Stabilize / Cable / neck isometrics do not classify as core. [fails today]

test_hyphenated_single_leg_counts_as_unilateral
  All 32 "Single-Leg *" exercises carry the unilateral base category.  [fails today]

test_finishers_do_not_enter_strength_pool_as_anchor_power
  5-10-15 Ladder, EMOM Squat Cleans + Burpees.                        [fails today]
```

### Stage 2

```
test_stage1_plyo_survives_into_stage2_payload
  Box Jump selected at Stage 1 -> present in strength_slots with
  quality_class "anchor_power".

test_unknown_movement_slots_receive_alternates
  Slot role and reservoir key agree; anchor_power slots never ship
  alternates=[] when candidates exist.                               [fails today]

test_stage2_cannot_invent_plyos_outside_candidate_pool
  A jump not in candidate_pools is rejected by the validator.
```

### Dose

```
test_plyometric_prescription_is_not_percent_1rm
  No exercise with method "plyometric" or mech_lower_jump receives a
  prescription containing "1RM".                                     [fails today,
                                                                      Trap Bar Jump Squat]

test_plyometric_dose_reduces_across_late_windows
  Contacts at D-21..D-14 > D-13..D-8 > D-7; zero at D-1.

test_single_leg_plyo_reps_capped
  Single-Leg Box Jump does not receive a 6-10 rep prescription.      [fails today]
```

---

## Reproduction

All findings were produced by instrumenting the real runtime path:

- `generate_strength_block` run across D-28/21/18/14/13/10/8/7, with and without box, for five athlete profiles; `_apply_late_strength_diversity_dampener` wrapped to capture the full scored pool and `_evaluate_strength_late_window` wrapped to capture block codes.
- `build_stage2_payload` run end-to-end on the D-28 block to confirm slot construction and alternates.
- `is_late_fight_metadata_safe` called directly per window for the conditioning microdose family.
- `calculate_phase_weeks` traced for 21/28/42/56/84-day camps.
- `equipment_score_adjust` called with a maximally-equipped intake selection.

No code was modified *for the audit pass above*. The section below records what was implemented afterwards.

---

## J. Implementation status (this branch)

The **seven must-fixes** are implemented. Should-fixes (H8–H16) and leave-alone items are untouched. Product decision from the owner: **box is assumed universally available**, so H3 was implemented by making box behave like bodyweight rather than by adding a "Plyo Box" intake option.

### What changed

| Fix | Change | Files |
|---|---|---|
| **H3 (box)** | Removed `box` from equipment on all 11 box records — box-only → `bodyweight`, `barbell,box` → `barbell`, `box/kettlebell` → `kettlebell`. Box now gates like bodyweight everywhere (selection, fallback, Stage 2 `universally_available`). | `data/exercise_bank.json` |
| **H7** | Resolved as a side-effect of H3: `Depth Jump to Sprint` no longer carries a `box` token, so it matches its conditioning-bank twin (`[]`). | `data/exercise_bank.json` |
| **H1 (dead zone)** | Backfilled `late_windows: [d21_to_d14, d13_to_d8]` on the three **safe bilateral** plyos: `Jump Squat`, `Box Jump`, `Jump-in-Place (Max Frequency)`. | `data/exercise_bank.json` |
| **H2 (GPP)** | Added `GPP` to `Jump Squat` and `Box Jump` phases. | `data/exercise_bank.json` |
| **H4 (alias)** | `kettlebells` → `kettlebell` in `EQUIP_ALIASES`. | `fightcamp/training_context.py` |
| **H5 (slot key)** | `_build_strength_slots` maps `movement == "unknown"` → role `"strength_support"`, matching the reservoir key, so unclassified jumps/bounds get in-role alternates instead of `[]`. | `fightcamp/stage2_payload.py` |
| **H6 (dose)** | `_classify_prescription_type` routes jumps/hops/bounds (`method=="plyometric"`, `mech_lower_jump`, or a word-boundary jump/hop/bound/pogo name match) to the `ballistic` template **before** the barbell check. Contrast/complex pairs (`→` / `contrast_pairing`) are excepted and keep the loaded contrast prescription. | `fightcamp/strength.py` |

### Scope decision on H1 — why only three exercises

§E group A (bilateral, low-eccentric, moderate-impact) is backfilled. Group B was **deliberately left blocked**:

- `Alternating Skater Hops`, `Lateral Bound-to-Slip` — `type: unilateral` + high landing + ballistic. The existing `late_strength_block_landing_unilateral_power` rule already governs these; surfacing high-impact unilateral bounds into the late window conflicts with "do not weaken landing-impact safety."
- `Trap Bar Jump (Light)` — caught by `late_strength_block_trap_bar_jump` in all late windows (a loaded jump). Correctly stays blocked regardless of metadata.
- Depth jumps, single-leg high-impact, heavy contrast pairs — remain `late_windows`-absent → hard-blocked late, exactly as §E group B recommends.

This keeps the change conservative: the block that was wiping out *legitimate* bilateral power is lifted for the three safe exercises, while every safety-motivated block is preserved. The conditioning-bank microdose unlock (§E group C / H16) is a should-fix and was **not** done here.

### Verified behaviour (real runtime, healthy boxing power athlete)

| Countdown | Before | After |
|---|---|---|
| D-21 → D-8 (SPP) | 0 lower-body plyos | `Jump Squat`, `Box Jump`, `Jump-in-Place` selected; block still balanced with med-ball/band/mobility work |
| D-12 (audit Athlete E) | 0 plyos (all 22 late-blocked) | Box Jump + Jump Squat + Jump-in-Place |
| D-6 → D-1 | 0 plyos | **0 plyos** (unchanged — final-week lockout preserved) |
| Depth jumps / loaded trap-bar jumps, any late window | blocked | **still blocked** |
| `Trap Bar Jump Squat` prescription | `3–5×3–5 @ 85–90% 1RM` | `ballistic` template (no 1RM) |

### Tests

- New: `tests/test_lower_body_plyo_selection.py` (15 tests — box universality, kettlebells alias, GPP eligibility, D-21/D-10 plyo selection, prescription routing, slot alternates, plus safety regressions for depth jumps, final-week lockout, and loaded trap-bar jumps). Written red-first, now green.
- Regenerated golden snapshot `tests/golden_snapshots/late_camp_selector_audit/{after,diff}.json` (frozen `before.json` kept). The regeneration adds the three bilateral plyos as winners at `d21_to_d14`/`d13_to_d8` only; no jump appears in any final-week window.
- Full relevant fightcamp suite run: every failure present is identical on clean `Main` (pre-existing environment gaps — `pydantic`/`fastapi`/`httpx2` and degraded spaCy parsing); this branch introduces **zero** new failures.

### Not done (should-fix, deferred)

H8 (jump/hop/bound movement pattern), H9 (`ab` substring), H10 (hyphenated single-leg unilateral), H11 (`lower_body_power` category), H12 (finishers-as-power reclass), H13 (rotational power vs support), H14 (over-severe cost metadata, incl. `Jump Squat cns_load`), H15 (plyometric contacts dose), H16 (conditioning microdose unlock). These remain as recommended follow-ups.
