# Conditioning Bank — Dose Metadata Audit (Second Pass)

> **Status: pre-cleanup snapshot.** This records the bank as audited at 259
> entries. The follow-up cleanup PR acted on most of it (deduplication, name
> standardisation, `rest_sec`/`total_minutes`/equipment/cost corrections, notes
> cleanup). Items deliberately left alone — chiefly the rep/distance `work_sec`
> ambiguity and the `Treadmill Hill Sprints` "1:40 rest" reading — are called
> out in that PR as remaining ambiguity.

This report is **diagnostic only**. It does not rewrite, delete, rename, redose, or
otherwise change any bank entry or selector logic. It catalogues every malformed or
contradictory dose field found in `data/conditioning_bank.json` and ranks
dead/near-dead and duplicate drills.

- Entries audited: **259**
- Source of truth for field semantics: `fightcamp/conditioning.py`
  (`_conditioning_structured_profile` and the constants below).

## Why these fields are load-bearing

The selector reads the numeric dose fields directly to classify a drill's energy
system and freshness. The thresholds that flip a classification:

| Classification | Rule (from `conditioning.py`) |
|---|---|
| Alactic structure | `work_sec ≤ 12` **and** `rest_sec ≥ 60` |
| Glycolytic — dense interval | `work_sec ≥ 45` **and** `rest_sec ≤ 90` **and** `rounds ≥ 3` |
| Glycolytic — sustained | `total_minutes ≥ 12` **and** `rpe ≥ 7` |
| Freshness-safe | `lactate_load ∈ {none,low}` **and** `impact_cost` low **and** `movement_cost` low **and** `rpe ≤ 6` |

Both `alactic_structure` and `dense_interval` require a **numeric** `rest_sec` and
`work_sec`; a rest value that lives only in the `duration` prose does not count.

---

## 1. `work_sec` has no single canonical meaning (76 entries)

`work_sec` is supposed to be *per-round work duration in seconds*. Across the bank it
is currently used in **four** incompatible ways. Of 259 entries, 76 store something
other than per-round seconds in `work_sec`.

### 1a. `work_sec` = rep count (34 entries)

Stored value is the number of reps, not seconds of work. Because these are almost all
alactic plyo/throw drills, the rep count (3–10) *accidentally* satisfies
`work_sec ≤ 12`, so the field is not obviously wrong — but it is not a duration, and
any future tightening of the alactic test would silently break.

`Band-Resisted Broad Jump`, `Depth Jump to Sprint`, `Plyo Push-Up to Sprint`,
`Box Jump (Stick Landing)`, `KB Swing (Heavy)`, `Med Ball Chest Pass (Reactive)`,
`Hurdle Hop (Stick Landing)`, `Depth Drop to Vertical`, `Wall Ball Shot (Max Height)`,
`Broad Jump (Stick Landing)`, `Box Jump-Over (Continuous)`, `Plyo Push-Up Burpee`,
`Band-Resisted Broad Jumps (ATP-PCr)`, `Depth Drops (ATP-PCr)`,
`Clap Push-Up Sprints (ATP-PCr)`, `Box Jump Repeats (ATP-PCr)`,
`Sandbag Clean & Press (ATP-PCr)`, `Broad Jump Repeats (ATP-PCr)`,
`Low Box Jump (Fast Reset)`, `Pogo Jump Series (Mini Bounce)`,
`Band-Resisted Vertical Jump`, `Snapdown to Quick Hop`,
`Med Ball Drop Catch to Jump`, `Mini Box Depth Drop`, `Band-Assisted Jump Reset`,
`Wall Reactive Jump (Cue Start)`, `Tuck Jump (Submax)`, `Split Stance Hop Switch`,
`Reactive Med Ball Chest Pass`, `Plyo Push-Up on Knees`,
`Overhead Med Ball Slam (Snappy)`, `Seated Med Ball Chest Pop`,
`Sandbag Shoulder Clean Flow`, `Turkish Get-Up Skill Flow`.

### 1b. `work_sec` = distance in metres/yards (16 entries)

Stored value is the prescribed distance, not seconds. Several of these break the
alactic test outright because the "seconds" exceed 12 (e.g. `Sled Sprint (Empty)`
`work_sec=15`, `Sled Push (Light)` `work_sec=20`, `Mixed Stroke Tempo Set`
`work_sec=200`).

`Swim Intervals (Freestyle)` (50), `Sled Drag Walk` (100), `Farmers Walk (Light)`
(100), `Sandbag Carry (Light)` (60), `Sled Sprint (Empty)` (15),
`Band-Resisted Sprint Start` (10), `Sled Push (Light)` (20),
`Sandbag Bearhug Carry` (60), `Water Jug Carries (No Sled)` (60),
`Tire Flip Drag (No Sled)` (40), `Sled Push Sprints (ATP-PCr)` (15),
`Band-Resisted Sprint Starts (ATP-PCr)` (10), `Sled Harness Backward Drag` (50),
`Kickboard Tempo Sets` (100), `Mixed Stroke Tempo Set` (200),
`Fins Sprint Repeats` (50).

### 1c. `work_sec` = full continuous-session length (26 entries)

Stored value is the entire session duration in seconds (e.g. `Step Mill (No Hands)`
`work_sec=2100` for a 35-min tempo session). Internally consistent for a continuous
drill, but it is a *different meaning* of the field from the interval entries above,
which is the core inconsistency.

`Reaction Ball Drills` (600), `Step Mill (No Hands)` (2100),
`Shadowboxing (Light Pace)` (600 — see §2), `Hiking (Weighted Vest)` (3600),
`Recumbent Bike` (2700), `Arm Ergometer` (2100), `Yoga Flow (Dynamic)` (2700),
`Elliptical (Nasal Only)` (1800), `Breath Control Drills` (900),
`Kettlebell Snatch Test` (600), `Incline Walk (Posture Focus)` (1200),
`EMOM Jab-Cross (Aerobic)` (600), `Dynamic Yoga for Fighters` (1800),
`Breathwork + Slow Shadowboxing` (900), `Kettlebell Swings (EMOM Aerobic)` (600),
`Meditative Jump Rope (Eyes Closed)` (600), `Muay Thai Skip Rope (Rhythm Focus)` (900),
`Cooldown Flow (Striking + Mobility)` (900), `Assault Bike Capacity Builder` (1200),
`Sled Push EMOM Capacity` (1200), `Incline Treadmill Walk Intervals` (1200),
`Versa Climber EMOM Capacity` (900), `Nasal Breathing Walk Tempo` (2400),
`Foam Rolling Mobility Circuit` (1200), `PVC Pipe Mobility Prep` (900),
`Mobility Reset: Breathing + T-Spine + Ankle Flow` (600).

**Recommendation:** pick one canonical meaning for `work_sec` (per-round work
seconds), and represent distance/reps in their own fields, and continuous sessions via
`total_minutes` only.

---

## 2. Contradictory duration metadata (`total_minutes` bugs)

These stored `total_minutes` disagree with the prescription. The dominant pattern is
`total_minutes` storing the *per-round* minutes instead of `rounds × round-length`.
This is high-impact because the glycolytic-sustained test fires on
`total_minutes ≥ 12`.

| Drill | Prescription | Stored `total_minutes` | Should be ≈ |
|---|---|---|---|
| **Pad EMOM (5x5 format)** | 5×5min, 30s rest | **5** | ~25 work / ~27.5 full |
| **Grapple Circuits (High Pace)** | 5×4min w/30s rest | **4** | ~20 work / ~22.5 full |
| **Shadowboxing (Light Pace)** | 3×10min rounds | **10** | 30 |
| **Grappler Escape Chains** | 6×4min, 90s rest | **4** | ~24 work / ~33 full |
| **Heat Acclimation Rounds** | 3×5min | **5** | 15 |
| **Light Heavy Bag (Pacing Drill)** | 5×5min, 30s rest | **5** | ~25 |
| **Wall Drill Sparring (Light Tap)** | 3×5min | **5** | 15 |
| **Lateral Shuffle + Strike Drills** | 3×5min | **5** | 15 |
| **Band-Resisted Jab/Cross (Slow Tempo)** | 3×5min | **5** | 15 |
| **Stationary Bike Lactate Threshold** | 2×8min, 3min rest | **8** | ~16 work / ~22 full |
| **Concept2 Rower Zone 3 Block** | 3×4min, 2min easy | **4** | ~12 work / ~18 full |
| **Pull Buoy Aerobic Threshold** | 3×5min, 1min rest | **5** | ~15 work / ~18 full |
| **Elliptical Lactate Threshold** | 2×8min, 3min rest | **8** | ~16 work / ~22 full |
| **MMA Gauntlet (Strike-Grapple-Strike)** | 5×3min stations | **19** | ~15 work / ~20 full |
| **Treadmill Hill Sprints (Glycolytic)** | 6×20s, 1:40 rest | **68.67** | ~12 (grossly inflated) |

Note for §1c/§2: `Shadowboxing (Light Pace)` stores a *correct* per-round
`work_sec=600` (10-min rounds); its defect is `total_minutes=10` instead of 30.

`Treadmill Hill Sprints (Glycolytic)` is the standout outlier — `total_minutes=68.67`
for six 20-second sprints. It trivially passes the sustained-glycolytic test on a
nonsense number.

### `total_minutes` excludes rest inconsistently (power entries)

Some power drills store work-only totals, others store work+rest, so the field's
meaning is not uniform:

- Work-only: `Depth Jump to Sprint` (0.25), `Box Jump (Stick Landing)` (0.3),
  `Med Ball Chest Pass (Reactive)` (0.5), `Explosive Boxing Burst Intervals` (0.4),
  `Reactive Shuffle Repeats` (0.3).
- Includes substantial rest: `Sled Sprint (Empty)` (12.5), `Band-Resisted Sprint
  Start` (10.67), `Sled Push (Light)` (12), `Band-Resisted Broad Jump` (2.3).

**Recommendation:** either split into `work_minutes` + `session_minutes`, or make
`total_minutes` consistently mean full elapsed session time.

---

## 3. Equipment metadata missing (16 genuine gaps)

`equipment: []` on drills that require kit now available through intake (`box`,
`weight_vest`, etc.). These list silently as free-access.

- **Needs `box`:** `Depth Jump to Sprint`, `Box Jump (Stick Landing)`,
  `Depth Drop to Vertical`, `Box Jump-Over (Continuous)`, `Plyo Step-Up Jumps`,
  `Depth Drops (ATP-PCr)`, `Box Jump Repeats (ATP-PCr)`,
  `Plyo Step-Up Intervals (Glycolytic)`, `Low Box Jump (Fast Reset)`,
  `Mini Box Depth Drop`.
- **Needs `hurdles`:** `Hurdle Hop (Stick Landing)`, `Mini Hurdle Quick Steps`.
- **Needs `weight_belt`:** `Pool Running (Weight Belt)`.
- **Needs `weight_vest`:** `Hiking (Weighted Vest)`.
- **Needs `jump_rope`:** `Jump Rope Conditioning`, `Jump Rope (Recovery Pace)`.

**Not defects (correctly equipment-free):** `Water Jug Carries (No Sled)`,
`Tire Flip Drag (No Sled)`, `Backpack Step-Ups (No Weight Vest)` are deliberate
no-equipment substitutes. Shadowboxing/boxing drills also correctly need no `box`
(the word "box" is a substring of "boxing", not a kit requirement).

---

## 4. Impact / lactate ratings that contradict tags or system (15)

### `low_impact`/`zero_impact` tag vs `impact_cost: high` (11)

`Sled Sprint Repeats`, `Sled Sprint (Empty)`, `Sled Drag Intervals`,
`Sled Drag Sprint Complex`, `Assault Bike :10s Sprints (ATP-PCr)`,
`Sled Push Sprints (ATP-PCr)`, `Prowler Sprint Intervals (ATP-PCr)`,
`Sled Drag Sprints (ATP-PCr)`, `Sled Sprint Finisher`,
`Swimming Interval Pyramid` (zero_impact), `Fins Sprint Repeats` (zero_impact).

(Sled/pool work is genuinely low- or zero-impact by nature — the `impact_cost: high`
rating is the value most likely wrong, and it evicts these drills from freshness/late
windows.)

### Alactic system but `lactate_load: high` (3)

`Hurdle Hop (Stick Landing)` (5×5 reactive jumps, 2-min rest — far more alactic than
glycolytic), `Split Jump (Alternating)`, `Single-Arm KB Snatch (ATP-PCr)`.

### Low-barrier/rhythm drill rated high impact **and** high movement

`Jump Rope Conditioning` — described as low-barrier rhythm work, but
`impact_cost: high` + `movement_cost: high`. `Jump Rope (Recovery Pace)` is also
`impact_cost: high`.

---

## 5. Dead / near-dead ranking

### 5a. Alactic structural pathway is effectively dead (55 of 68 alactic drills)

Only **14 of 68** ATP-PCr/alactic drills carry a numeric `rest_sec`. The other 55
have their rest value only in prose, so `alactic_structure` (which needs numeric
`work_sec` **and** `rest_sec`) is **always False** for them — they can only ever be
classified alactic via tags, never via dose.

`rest_sec` numeric coverage by system:

| System | Numeric `rest_sec` |
|---|---|
| aerobic | 14 / 93 |
| atp-pcr | 14 / 68 |
| glycolytic | 17 / 88 |
| recovery | 4 / 6 |
| anaerobic_alactic | 0 / 1 |
| cognitive | 0 / 2 |
| hypertrophy | 0 / 1 |

Highest-priority alactic drills that cannot pass the structural test:
`Depth Jump to Sprint`, `Box Jump (Stick Landing)`, `Alternating Bound`,
`Med Ball Chest Pass (Reactive)`, `Hurdle Hop (Stick Landing)`,
`Depth Drop to Vertical`, `Single-Leg Hop (Stabilize)`, `Wall Ball Shot (Max Height)`,
`Broad Jump (Stick Landing)`, `Split Jump (Alternating)`, `Med Ball Slam (Rotational)`,
`Box Jump-Over (Continuous)`, `Band-Resisted Lateral Bound` (+42 more).

A handful are doubly broken — even the numeric `rest_sec` they *do* have is below the
60s floor, so the dose actively reads as **not** alactic:
`Band-Resisted Broad Jump` (rest 24), `Medicine Ball Rotational Throw` (rest 30),
`Plyo Push-Up to Sprint` (rest 30), `KB Swing (Heavy)` (rest 40),
`Prowler Sprint Intervals (ATP-PCr)` (rest 50), `Single-Arm KB Snatch (ATP-PCr)`
(rest 25), `Sled Drag Sprints (ATP-PCr)` (rest 50).

### 5b. No glycolytic drills fail every density test

All `glycolytic`-system drills currently pass at least one density gate (usually via
`lactate_load: high`). None are dead on that axis — but note several rely *only* on the
`lactate_load` flag because their `total_minutes` is under-counted (§2), so correcting
`total_minutes` without keeping `lactate_load` would make some fall through.

---

## 6. Duplicate / near-duplicate drills

### 6a. Base ↔ suffixed clones (same movement, split across systems/phases)

| Base | Suffixed twin | Divergence |
|---|---|---|
| `Band-Resisted Broad Jump` | `Band-Resisted Broad Jumps (ATP-PCr)` | same system/phase — near-exact dup |
| `Band-Resisted Sprint Start` | `Band-Resisted Sprint Starts (ATP-PCr)` | dose-identical dup |
| `Tire Flip Sprints` | `Tire Flip Sprints (ATP-PCr)` | glycolytic/SPP vs ATP-PCr/GPP |
| `Rope Climb Sprints` | `Rope Climb Sprints (ATP-PCr)` | glycolytic/SPP vs ATP-PCr/GPP |
| `Sledgehammer Strikes` | `Sledgehammer Strikes (Glycolytic)` | both glycolytic; SPP vs GPP |
| `Defensive Movement Drill` | `Defensive Movement Drills` | glycolytic vs aerobic (singular/plural) |

### 6b. Dose+system identical pairs

- `Box Jump (Stick Landing)` ≡ `Box Jump Repeats (ATP-PCr)`
- `Band-Resisted Sprint Start` ≡ `Band-Resisted Sprint Starts (ATP-PCr)`
- `Depth Drop to Vertical` ≡ `Depth Drops (ATP-PCr)`
- `Tuck Jump (Submax)` ≡ `Single-Leg Med Ball Toss Jump`

### 6c. High-similarity near-twins worth a manual look

`Box Jump (Stick Landing)` ↔ `Broad Jump (Stick Landing)` (0.92),
`Box Jump Repeats (ATP-PCr)` ↔ `Broad Jump Repeats (ATP-PCr)` (0.93),
`Sled Push Sprints (ATP-PCr)` ↔ `Sled Drag Sprints (ATP-PCr)` (0.85), and the large
`… Intervals (Glycolytic)` family (`KB Swing`, `Sandbag Shoulder`, `Wall Ball Shot`,
`Jump Squat`, `Lateral Bound`, `Heavy Bag Power`, `Plyo Step-Up`,
`Defensive Sprawl`) which share a common template and should be checked for redundant
overlap.

---

## 7. Notes containing unenforced logic

The following notes imply protections the selector has no structural field for, so
they are prose only:

- "Only program after upper body days" / "After lower body strength days only"
- "Disable if tightness >3/10" / "Disable if vertical jump drops >10%"
- "No same week as max deadlifts" / "Not same week as heavy cleans"
- "Requires 48h recovery" / "CNS LOAD: Max 2x/week"
- "Ideal 48h post heavy bench" / "Safe 48h post pulls"

**Recommendation:** either encode the load-bearing ones structurally (recovery-hour
and same-week-lift fields) or trim the notes so they don't imply enforcement that
doesn't exist.

---

## Priority summary

| Priority | Issue | Count |
|---|---|---|
| P0 | `total_minutes` contradicts prescription (incl. 68.67-min outlier) | ~15 |
| P0 | `work_sec` non-canonical (reps / distance / full session) | 76 |
| P0 | Alactic drills that can never pass the structural dose test | 55 |
| P1 | Missing equipment metadata (now intake-available) | 16 |
| P1 | Impact/lactate ratings contradicting tag or system | 15 |
| P1 | Duplicate / clone drills | 6 pairs + clusters |
| P2 | Notes implying unenforced protections | many |
