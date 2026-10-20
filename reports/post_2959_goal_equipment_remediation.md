# Post-#2959 remediation: goal, weak-area and equipment targeting

Branch from Main `f27edef` (includes #2959). Independent of PR #2958: no injury
metadata, contraindication, `avoid_if`, fight-proximity, mechanical-risk or
upper-back alias is touched, and injury-text matching is byte-for-byte the same.

Two defects are corrected. Both change what real athletes are prescribed, and
both are reproduced on live bank rows and complete Stage 1/Stage 2 programmes.
No source bank row, catalogue identity, dose, threshold, baseline or saved
programme field changes.

## 1. Ranked assessment

| Rank | Finding | Area | Verdict | Action |
| --- | --- | --- | --- | --- |
| 1 | *new*: goals and weak areas read as symptom text | goal/weakness → conditioning | **confirmed defect, live web option** | fixed |
| 2 | `MI-e85f5cef1705` Speed → reactive vs speed → speed | goal normalization | **confirmed programme divergence**, root cause is #1 | fixed at root; normalizer kept |
| 3 | *new*: `open_space` treated as declarable apparatus | equipment → strength | **confirmed defect**: 9 rows unreachable for every athlete | 3 rows fixed, 6 held back with reasons |
| 4 | *new*: legacy primary goal lost after normalization | goal priority | confirmed, legacy labels only | deferred (see §7) |
| 5 | `MI-a22b542d2011`, `MI-19c8f76c5408` partner/dummy | equipment | 2 rows unreachable (`dummy` cannot be declared) | preserved, deferred |
| 6 | `MI-2a5bb39b6422` Towel Hang `towel/bar` | equipment | unreachable (`bar` cannot be declared) | deferred: needs a row/identity edit |
| 7 | `MI-1277d8b6d1a1` Tabata Sprints `treadmill/rower` | equipment | ALL is the safe reading | preserved |
| 8 | `MI-85d8031a7c6b` line/tape | equipment | generator rejects, editor accepts | deferred |
| 9 | `MI-770609066613` mat/mats | equipment | 45 rows unreachable; suitability is unresolved | preserved |
| 10 | `MI-b4fe8a71fda0` Adductor Squeeze `pad` | equipment | unreachable (`pad` cannot be declared) | deferred |
| 11 | 10 "missing explicit goals" findings | goals | no defect: no consumer depends on row `goals` | preserved |
| 12 | `MI-cc45611f69c2`, `MI-2c0f544f8bdb` system | conditioning | no defect shown | preserved |

## 2. Confirmed defects and what athletes experienced

### 2a. Footwork and the legacy Speed goal were treated as injuries (boxing)

`_boxing_aerobic_context_flags` built one string from injuries, weak areas and
goals, then matched symptom hints as substrings:

- `footwork` (a current intake weak area) contains `foot`. The athlete was
  flagged `lower_limb_unload_desirable`: every run was ranked −0.75 instead
  of +0.75, light shadowboxing 0.4 instead of 0.9, and pool treading counted
  as "justified".
- The legacy `Speed` and `Speed / Reaction` goals normalize to `reactive`,
  which is one of the impact keywords. The athlete was flagged
  `impact_tolerance_reduced`, with the same ranking penalties.
- Legacy regional goals (`Shoulders`, `Hip Mobility`, `Knees` → `quad_dominant`)
  set swim sensitivity or lower-limb unloading for uninjured athletes.

**Correction** (`fightcamp/conditioning_boxing.py`): the context flags read
only injury text (unchanged substring matching) and restrictions. A
performance weakness is something to improve, a functional limitation is
something currently restricting training, and a medical restriction is an
independent safety decision: only the last two may change aerobic
preferences. A healthy boxer working on knee stability, hip mobility or
shoulders keeps normal running and shadowboxing. The old
`knee stability → unload` test is inverted accordingly.

This is the root cause of `MI-e85f5cef1705`'s programme divergence. Selection
tag maps already treat the two spellings the same (`GOAL_TAG_MAP["reactive"]
== GOAL_TAG_MAP["speed"]`, and both map to the `speed` adaptation). After the
fix, all four spellings select identical programmes in 24 runs (6 cases × 4
spellings). The normalizer and its three pinning tests are unchanged.

### 2b. Open-space strength rows could never be prescribed

Intake has no `open_space` option. Stage 1 required every normalized token,
so Sprint Acceleration (10–20 m), Carioca Sprint, Lateral Shuffle Sprint,
Backpedal-to-Sprint and Single-Leg Bounding (plus three style rows) were
unreachable for every athlete. Meanwhile:

- the conditioning bank prescribes Hill Sprint Repeats, Short Hill Sprints and
  the 80-60-40 m Descending Sprint Ladder with no equipment;
- the editor's `_AMBIENT_EQUIPMENT` and `bank_schema.NON_EQUIPMENT_TOKENS`
  (already used by strength's own D-1 gate) both say `open_space` is not
  equipment;
- `shared/training-metadata.json` already reviews Sprint Acceleration as the
  speed row with an SPP ballistic dose.

A speed-primary athlete therefore never received the bank's dedicated
acceleration exercise.

**Correction** (`fightcamp/strength.py`, `fightcamp/stage2_payload.py`): the
strength gate no longer requires `open_space`. The Stage 2 option's
`universally_available` flag agrees, so the validator does not report the
selection as `equipment_incongruent_selection`. The raw `required_equipment`
value is still serialized, so the payload still says the row needs space.

Before enabling a row, its injury decisions were compared with the
conditioning sprints athletes already receive: 14 regions × 3 severities.

| Row | Laxer than existing sprints at | Decision |
| --- | --- | --- |
| Sprint Acceleration (10–20m) | none | **reachable** |
| Carioca Sprint | none | **reachable** |
| Lateral Shuffle Sprint | none | **reachable** |
| Backpedal-to-Sprint Transition | moderate/high ankle, moderate/high knee (derives no deceleration tag) | held back |
| Single-Leg Bounding | 14 combinations, including high Achilles and high hip flexor | held back |

The three style rows stay unreachable because the conditioning path is
unchanged. Blast Double Sprints ("sprint into explosive takedown finish") and
Guillotine Shot Sprints ("drop to guillotine grip") declare no partner or mat,
so open space is not their only missing requirement. Mats, lines and tape are
deliberately out of scope.

## 3. Targeted corrections

- `fightcamp/conditioning_boxing.py`: the context flags read injuries
  (substring, as before) and restrictions only.
- `fightcamp/strength.py`: `_SPACE_ONLY_EQUIPMENT`, `_SPACE_ONLY_HELD_BACK` and
  `_required_strength_equipment`, used by both strength eligibility gates.
- `fightcamp/stage2_payload.py`: the strength option's `universally_available`
  uses the same exemption.
- `tests/test_goal_weakness_equipment_remediation.py`: 39 tests.

## 4. Before/after evidence

Complete programmes use the planner probe with a pinned clock (2026-10-11),
`PYTHONHASHSEED=0` and seed 7. Main = `f27edef`.

**Regression fixture** (the six #2959 programmes): five are byte-identical
(plan text and full Stage 2 payload). `boxing_gpp_power_conditioning` changes
only in its SPP strength list: Sprint Acceleration enters and Back Squat → Box
Jump leaves. Its conditioning sessions are identical.

**Legacy speed labels** (boxing GPP, goals `X, power, conditioning`):

| Goal spelling | Main GPP aerobic | Main SPP aerobic | After |
| --- | --- | --- | --- |
| `speed` (web) | 5K Steady Run | 5K Steady Run | unchanged |
| `Speed`, `Speed / Reaction`, `reactive` | Heavy Bag Aerobic Pace | Light Heavy Bag (Pacing Drill) | 5K Steady Run / 5K Steady Run (same as web) |

**Footwork weak area** (boxing GPP): on Main the footwork athlete got no runs
(Heavy Bag Aerobic Pace in GPP, Lateral Shuffle + Strike Drills in SPP). The
balance athlete got 5K Steady Run in both. After the fix, both athletes get
5K Steady Run twice. The footwork weakness still earns weakness-tag matches
elsewhere (Ring Cut-Off Walkdown, Entry-and-Score Burst, Pressure Combination
Rounds). MMA, kickboxing and taper cases are byte-identical. In the
shoulder-injured taper case, only Stage 2 score evidence changes (0.4 → 0.9);
the selection is unchanged.

**Targeted scenarios** (SPP strength list, Main → after):

| Scenario | Change |
| --- | --- |
| Boxer, speed primary, D35, gym | + Sprint Acceleration, − Band-Resisted Reaction Hop |
| + moderate ankle sprain | + Sprint Acceleration (injury guard: *modify*, same as hill sprints), − Lateral Bound-to-Slip |
| + foot pain on landing | no sprint selected (guard excludes); Lateral Bound-to-Slip → Push Press |
| + high fatigue | + Sprint Acceleration, − Depth Jump to Sprint |
| fight at D21 | byte-identical (late-window gates unchanged) |
| MMA grappler GPP with partner | plan text identical |
| Boxer footwork SPP / footwork + mild ankle sprain | + Sprint Acceleration; footwork-only case also gets 5K Steady Run (2a) |
| Legacy `Speed / Reaction` kickboxer | + Sprint Acceleration, − Depth Jump to Sprint |

Held-back rows appear in no scenario. Phase (GPP), moderate hamstring and high
foot injuries still exclude every sprint (tested).

## 5. Regression results

See the PR description for the full-suite comparison against an untouched Main
worktree. New file: 39/39 pass on the branch; 19 fail on Main (the defects plus
the new helpers), while the 20 guard tests pass on both. Existing boxing,
running and sport-safety conditioning tests pass unchanged. Ruff and
`git diff --check` are clean.

## 6. Intentionally preserved

- `GOAL_NORMALIZER` (`Speed → reactive`): selection already treats it as
  speed, and three tests pin it. Changing it would also remove the conditioning
  `primary_goal == "speed"` alactic bonus that legacy `Speed` athletes keep
  today.
- Tabata Sprints (Treadmill/Row) keeps ALL. Its `impact_cost: low`,
  `landing_cost: none` and rowing mechanics tags (`mech_upper_pull`,
  `mech_grip_support`) describe only the rower variant. ANY would give a
  treadmill-only athlete a sprint whose impact metadata is wrong.
- Partner/dummy rows keep ALL. A partner-only reading would enable live
  takedown work with no contact-load metadata.
- Mat/mats, pad, pins, bag isometrics, Death by Carry and Towel/Gi Row: the
  conservative gates and UNKNOWN reviews from #2824/#2959 stand.
- The 10 "missing explicit goals" findings: Stage 1 never reads row `goals`.
  The editor folds them into tag relevance, where the same tags already match.
  No behaviour depends on filling them.

## 7. Deferred, with a proposed sequence

1. **Injury metadata for Backpedal-to-Sprint and Single-Leg Bounding** (owner:
   #2958's mechanical-risk work). Once each passes
   `test_newly_reachable_rows_are_gated_at_least_as_strictly_as_existing_sprints`,
   remove it from `_SPACE_ONLY_HELD_BACK`. The editor already offers both
   (ambient `open_space`); its injury policy should be checked against the
   same table. Lateral Bound-to-Slip, which is already reachable, shows the
   same Achilles laxity.
2. **Primary-goal loss for normalized labels.** Repro: goals
   `Power & Explosiveness, Speed / Reaction`, primary `Speed / Reaction` →
   profile primary `explosive`. Web values are unaffected. Fix by normalizing
   `primary_goal` with the same map, together with a decision on one
   canonical speed token, so the `primary_goal == "speed"` alactic bonus is
   preserved.
3. **Identity-aware apparatus edits**: Towel Hang `bar → pullup_bar`, Adductor
   Squeeze `pad`. Each needs a catalogue identity/alias update and an
   equipment review entry, following the #2825 `source_history` pattern.
4. **Line/tape parity** between generation and editor, with athletic tape
   (`Tape-Assisted Plyo Taps`) kept separate from floor tape.
5. **Style rows with undeclared apparatus** (Blast Double Sprints, Guillotine
   Shot Sprints): declare partner/mat before any space rule reaches the
   conditioning path.
6. **Rehab `dumbbell` vs intake `dumbbells`**: four clinical rows are
   unreachable for anyone who owns dumbbells. This needs clinical review.
7. Observed, not investigated: Light Heavy Bag (Pacing Drill) is authored
   `system: aerobic` but rendered under a Glycolytic heading in one SPP
   session (Main, legacy-speed run). It belongs with `MI-cc45611f69c2`.

## Addendum: merged follow-ups

This PR also carries the two follow-ups (formerly #2961 and #2962).

**Primary goal and legacy labels.** `GOAL_NORMALIZER` maps legacy labels to
the intake form's values (`Speed`, `Speed / Reaction` → `speed`;
`Power & Explosiveness` → `power`), and `primary_goal` is normalized with the
same map. On Main, a "Speed / Reaction" primary was scored as `explosive`,
and a "Maximal Strength" primary as conditioning, because the raw primary was
not found among the normalized goals. Five legacy-label programmes now have
Stage 2 payloads byte-identical to their intake-value equivalents.
Intake-value programmes are unchanged.

**Equipment (owner decision).** Mat/mats, line/tape, Towel Hang's `bar` and
Adductor Squeeze's `pad` never gate eligibility (`NOT_REQUIRED_EQUIPMENT` in
the shared normalizer), and ticking `dumbbells` satisfies the single-dumbbell
rehab rows. The four UNKNOWN equipment reviews record the decision so the
editor agrees. This supersedes deferred items 3, 4 and 6 above, and the mat
preservation in §6.
