# Findings register

Every confirmed finding below was reproduced through the real Stage 1 entry
point (`fightcamp.main.generate_plan_sync`) with a frozen clock
(2026-01-04 12:00 UTC) and a fixed seed, using `repro/harness.py`. Scenario
IDs (`S01`…`S32`) refer to `scenario_matrix.md`. No model call, database or
real athlete record was used. Line numbers are against `Main` at `0926f2e`.

Severity: **P0** safety · **P1** programming correctness · **P2** quality ·
**P3** maintainability.

Root-cause groups (used by `roadmap.md`):

| RC | Shared root cause |
| --- | --- |
| RC-A | A selected weakness is "delegated" to a subsystem that has no input that understands it, no guaranteed capacity, and no verifier |
| RC-B | Role existence is decided without asking whether a legal, eligible member exists for that role on that day |
| RC-C | `goal_preservation`'s microdose tier is a second content author that bypasses selection, injury, equipment and load authorities |
| RC-D | Calendar movers run after (or inside) membership composition and use a destination doctrine that differs from the documented one |
| RC-E | Two definitions of the same fact ("loaded", "low-load trunk support", the coverage window) live in different owners |
| RC-F | Bank/library coverage gaps that crash or silently empty the plan |

---

## Confirmed defects

### F01 · P1 · RC-A — Strength selection never sees the athlete's weakness unless the raw intake token is a bank tag

- **Reproduction:** S01 (known case), S09, S22, S32 and every trunk-strength
  scenario. `repro/trace_trunk.py` / `repro/trace_bonus.py`.
- **Expected:** a `trunk_strength` primary weakness raises the score of
  core / anti-rotation / stability work in the Stage 1 strength pool, exactly
  as the documented tag map (`fightcamp/tag_maps.py:237`,
  `"trunk_strength": ["core", "anti_rotation", "stability"]`) says.
- **Actual:** `plan_pipeline_blocks._generate_strength_blocks`
  (`fightcamp/plan_pipeline_blocks.py:125-128`) passes the raw normalised
  weakness list to `strength.generate_strength_block`, and
  `strength.score_exercise` (`fightcamp/strength.py:1208`, `:1230`) intersects
  it with exercise tags. **No exercise-bank entry carries the tag
  `trunk_strength` (0 / 339)**, so every exercise scores
  `weakness_hits = 0`. Conditioning *does* expand weaknesses through
  `WEAKNESS_TAG_MAP` (`fightcamp/conditioning.py:3156`); strength does not.
  Result: GPP and SPP strength pools contain no core/anti-rotation work in any
  trunk-strength scenario (S09 GPP pool: Kettlebell Swing, DB presses, RDL,
  pull-up, Cossack squats, hops, carries; SPP: 16 power/plyometric items).
- **Diagnostic (not a fix):** `repro/experiment_expand.py` wraps the call and
  expands the weakness through the existing map. In the 56-day boxer case the
  pools then gain Chop Holds (Anti-Rotation), Side Plank, Cross-Body Carry,
  Anti-Rotation Med Ball Slam, and the final plan carries four trunk members
  instead of none. In the 21-day case it changes nothing (see F02).
- **Earliest stage:** Stage 1 candidate selection.
- **Silent override:** no override; the information is simply never consumed.
- **Scope beyond trunk:** the same literal match applies to every weakness.
  `strength` (0 bank tags) and `gas_tank` (0) never score; `power` matches only
  8 entries. `test_tagging_consistency.py:58` locks the map contents but no test
  asserts that strength scoring consumes it.
- **Relevant PRs:** #719 aligned the trunk weakness with the core map (tag map
  only); #2265 added the low-cost core/balance bonus.
- **Minimal correction:** expand weaknesses through `WEAKNESS_TAG_MAP` once, in
  the strength selector's input (the same helper conditioning uses), keeping
  `priority_profile` weights.
- **Regression tests:** unit — `score_exercise` gives a weakness hit to a
  `core`-tagged item for `trunk_strength`; e2e — the 56-day S09 fixture has at
  least one `core_balance_support` slot in GPP or SPP; golden — the existing
  strength-selection snapshots are re-baselined deliberately.
- **Interaction:** large. Weakness hits now reorder pools for strength/power/
  speed weaknesses too (the experiment also surfaced "Glute Bridge Hold (Heavy
  Load)"). Gate behind the scenario matrix and re-run
  `test_strength_*`, `test_goal_preservation_e2e.py`,
  `test_stage1_parity.py`.

### F02 · P1 · RC-A / RC-F — No low-load trunk exercise is eligible for an SPP session inside D-21…D-14

- **Reproduction:** S01; `repro/trace_core.py` and the
  bank count below.
- **Expected:** a 21-day camp whose Stage 1 strength selector *does* run the
  core/balance bonus (`strength.py:2982`, it fires because
  `_has_core_balance_priority` is true) can find at least one bodyweight/band
  trunk drill.
- **Actual:** the bonus returned `None` for SPP and added *Kettlebell Suitcase
  Carry Hold* only to the TAPER pool. Of the 67 bank entries the strength
  classifier marks `core_balance_support`, 60 have no `late_windows`, so inside
  any active late window they are hard-blocked by
  `bank_schema.py:820-821` (`late_block_missing_late_windows`); only 26 list
  SPP and only **2** list both SPP and `d21_to_d14` (Sandbag Shouldering —
  sandbag, loaded compound; Adductor Squeeze Isometric — pad). The usable ones
  (Controlled Bird-Dog, Bird Dog Hold, Pallof Press Iso, Suitcase Carry Holds,
  Kettlebell Suitcase Carry Hold) are tagged GPP/TAPER only.
- **Second hop:** the TAPER pool's suitcase carry is never used. D-13 inward
  strength roles belong to the late tail, whose assignment builder prefers a
  style-taper sport primer over any strength slot
  (`fightcamp/stage2_payload.py:1057-1084`, deliberate), so the D-13 "strength
  touch" is *Pocket Frame-Burst Touch* (2 x 5 s) and D-7 is *Pull-Counter-Reset*.
- **Earliest stage:** bank metadata (phases / late_windows), surfaced at Stage 1
  late-window gating.
- **Relationship to the metadata audit:** this is the *programming* consequence
  of the `late_windows` incompleteness the metadata audit already inventories;
  do not re-taxonomise, fix coverage for the trunk family.
- **Minimal correction:** author `late_windows` (and SPP phase where
  appropriate) for the low-load trunk drills that are already late-safe by
  their own notes; no selector change.
- **Regression tests:** bank-schema test that at least one non-loaded
  `core_balance_support` entry is eligible for SPP in `d21_to_d14` and in
  `d13_to_d8`; e2e S01 asserts a trunk member exists in week 1.
- **Interaction:** low; the late-window evaluator and safety gates are unchanged.

### F03 · P1 · RC-A — The delegated trunk subsystem cannot deliver and nothing checks that it did

- **Reproduction:** the 25 completed scenarios that select `trunk_strength`
  and `repro/deleg_probe.py` (21/35/56 days): **zero suitable trunk exposures
  were produced by `session_composition.trunk_support` in any scenario.** The only
  trunk content that appeared came from other owners: rehab for a low-back
  injury (S21), the strength microdose floor (F06) or an unsuitable embedded
  item (F04).
- **Mechanism (three independent dead ends):**
  1. Strength path — `_select_bounded_records`
     (`fightcamp/session_composition.py:612-665`) adds a trunk record only
     `if preserve_trunk_support and len(selected) < cap` **after** the role's
     required family groups are filled. `transfer_strength_day` and
     `neural_plus_strength_day` have two required groups and drop to
     `effective_exercise_cap = 2` at pressure ≥ 1 (any active cut, moderate
     fatigue or injury), so the branch can never run. In the known case the
     cap was 2 because of the moderate 4.4 % cut (`cut_pressure 1`).
  2. Recognition — the branch also needs `core_balance_support` on the
     *record*; `strength_session_quality.py:232-236` excludes `rehab_support`
     ("Dead-bug breathing" in the SPP pool can never qualify) and, because of
     F01/F02, no other core record exists.
  3. Conditioning path — the embedded trunk add-on
     (`session_composition.py:2045-2079`) requires `workload_met`, pressure
     < 2, no adjacent hard spar *and* a record from
     `_low_load_trunk_support_records(strength_slots)`; the strength pool has
     none (F01/F02), and in the known case the only normal-camp conditioning
     role is empty (F08), whose skip reason is recorded as
     `conditioning_workload_unmet`.
- **Contract gap:** `goal_preservation._WEAKNESS_DELEGATED_SUBSYSTEMS`
  (`fightcamp/goal_preservation.py:97-103`) records `resolution: delegated`
  and, by design and test (`test_goal_preservation_e2e.py:127-134`), creates
  no obligation. The comment states the subsystem "services them from the same
  weak-area selection"; no code checks it. Balance and coordination are
  delegated the same way (see R1).
- **Earliest stage:** athlete priorities → goal contract (delegation without a
  verifier); composition cap ordering.
- **Silent override:** yes — the role cap silently overrides a selected
  limiter, and the brief reports "Primary limiter is trunk strength" while
  delivering none.
- **Minimal correction:** (a) give delegated weaknesses a *coverage verdict*
  in `goal_preservation` (evidence = any closed member or embedded support with
  the delegated family, any day ≥ D-2), reported but not floor-repaired;
  (b) reserve the trunk slot before the readiness cap trims (a support item
  does not count against `major_family_limit` and the cap reduction only
  removes development work). Fix F01/F02 first or (b) has nothing to reserve.
- **Regression tests:** e2e on the anonymised boxer fixture (both injury
  variants) asserts ≥ 1 low-load trunk member in each of weeks 1 and 2, the
  D-17 hard day still hard, D-10 and D-3 still technical; a unit test of
  `_select_bounded_records` at pressure 1 for both two-group role keys.
- **Interaction:** must not push a session above its readiness cap in *working*
  sets; dose stays the embedded support dose.

### F04 · P1 (safety-adjacent) · RC-E — "Low-load trunk support" admits heavy sleds, yokes and CNS-high drills, then hides their cost from the calendar

- **Reproduction:** S11 week 1 `aerobic_base_day` embeds **Sled Push
  (Incline)** (bank: "3–5 carries over 20–40 m, heavy but unbroken") as
  `support_dose_category: low_load_trunk` with the prescription "1–2 controlled
  sets x 3–5 slow reps (each side if one-sided); stop before fatigue".
  Static probe (`findings` evidence in `known_case.md` §6): of the 67
  core-balance entries, `_low_load_trunk_support_records`
  (`session_composition.py:729-741`) accepts 39 including Sled Push (Heavy),
  Yoke Walk, Sledgehammer Strikes (`mech_systemic_fatigue`), Boxing Shuffle
  Drill (Ladder), Farmers Walk (Fat Grip), Lateral Raise (Machine) (not a trunk
  exercise) and Split-Stance Wall-Drive Isometric (`mech_cns_high`,
  `mech_ballistic`).
- **Why:** the filter trusts `classify_strength_item`'s `loaded_pattern`, which
  is driven by an equipment allow-list that omits sled, yoke, sledgehammer and
  fat grip (`_slot_uses_loaded_equipment`, `session_composition.py:458-481`),
  and never reads `mechanical_risk_tags` / cost metadata. The rep template is
  chosen by name/quality, so carries and pushes receive "slow reps".
- **Hidden cost:** `realised_session_stress` skips every `embedded_support`
  item (`session_composition.py:962`), so the realised-load calendar
  revalidation never sees the sled.
- **Earliest stage:** session composition (classification).
- **Minimal correction:** require affirmative low-cost metadata
  (`has_verified_low_cost` on movement/impact/systemic fields, no
  `mech_systemic_fatigue` / `mech_cns_high` / `mech_ballistic`) and
  `mech_trunk_*` for low-load trunk support; stop skipping embedded items whose
  metadata is not verified low-cost.
- **Regression tests:** parametrised unit test over the bank that the 7 items
  above are rejected and Plank / Dead Bug (Isometric) / Bird Dog Hold accepted;
  S11 replay has no sled in an embedded slot.

### F05 · P0 · RC-F — Foot injuries do not exclude jumps, landings or sprint starts at any severity

- **Reproduction:** `repro/injury_matrix.py`. Low/stable, low/improving and
  admin-resumed high/stable foot pain all keep **Jump Squat**
  (`mech_landing_impact`, `mech_lower_jump`, `mech_reactive`) in the D-20/D-19
  session; S02/S24 likewise. Ankle, Achilles and knee variants correctly drop it.
  Direct guard check: `injury_decision` returns `allow`, risk 0.0, for Jump
  Squat, Box Jump and Sprint Acceleration (10-20m) with a foot injury at low,
  moderate **and high** severity.
- **Why:** `injury_exclusion_rules.py:740-764` — the foot rule bans only
  rope/pogo/hop keywords and `foot_impact_high`, `forefoot_load_high`,
  `mech_plantarflexion`, `mech_lower_limb_weight_bearing`; it has none of the
  landing/jump/reactive tags the ankle rule has (`:710-739`).
- **Mitigation that exists:** triage blocks moderate/stable (allowlist),
  moderate/worsening and high/stable foot injuries (S03, S20) — but an admin
  triage-resume override (`main._triage_resume_override_allows_continuation`)
  continues into the same unguarded selection, and low-severity pain is
  never triaged.
- **Earliest stage:** injury restriction data.
- **Minimal correction:** add `mech_landing_impact`, `mech_lower_jump`,
  `mech_reactive_rebound`, `mech_max_velocity`, `mech_acceleration` to the foot
  (and toe) ban tags with the same severity weighting the ankle uses; let
  clinical review decide whether low-severity pain allows "modify".
- **Regression tests:** add foot/toe rows to `test_injury_exclusion_hardening.py`
  for those exercises at each severity; e2e S02 has no landing-impact member.
- **Interaction:** foot-pain plans lose power options; expect more empty or
  shorter power roles until F08 is fixed.

### F06 · P0 · RC-C — The weekly priority-exposure microdose bypasses injury, equipment, restriction and load authorities

- **Reproduction:** every scenario with a speed/strength/power build goal.
  *Reactive Start Burst* ("3 x 4 sec @ RPE 7, full rest", a sprint start) is
  attached on D-20 for foot (S02, S24), ankle sprain (S29), Achilles and knee
  (`injury_matrix.py`). *Loaded Carry Touch* ("2 x 20 m @ RPE 7") is attached
  for a **bodyweight-only** athlete (S27, D-27 and D-19) and for a BJJ athlete
  with shoulder pain, as the *only* member of `aerobic_base_day` and
  `fight_pace_repeatability_day` (S16).
- **Why:** `_MICRODOSE_SPECS` (`goal_preservation.py:415-470`) are hard-coded
  exercises and doses with no bank entry, tags, equipment or
  `mechanical_risk_tags`. `_attach_goal_microdose` (`:893-990`) checks host
  category, D-day > 13, protected days and goal-coverage regression only;
  `_sync_microdose_membership` (`:510-560`) then appends the microdose to the
  host's **closed** `selected_exercise_assignments`, `effective_strength_prescriptions`
  and envelope allow-list. It runs inside `reconcile_goal_preservation`, after
  `apply_realised_load_calendar_revalidation`, so the calendar never judges it.
- **Contract conflict:** `PLANNER_ARCHITECTURE_CONTRACT.md` §3 lets
  goal preservation restore only retained `goal_repair_candidates` and forbids
  "inventing a new role, exercise, dose"; invariant 11 forbids adding to a
  closed role downstream. The microdose tier (#2516, #2517, #2521, #2540)
  postdates the contract text and was never written into it.
- **Earliest stage:** goal preservation (downstream of every safety owner).
- **Silent override:** yes — closed membership, injury filtering and equipment
  filtering are all overridden without a record.
- **Minimal correction:** make microdose candidates come from the phase pool
  (the same `strength_slots` / conditioning slots, already injury- and
  equipment-filtered) and pass the host through the realised-load check; if no
  pool item qualifies, record `floor_no_safe_candidate` instead of inventing one.
- **Regression tests:** S02/S29 have no `Reactive Start Burst`; S27 has no
  loaded item; S16 has no microdose on a conditioning host whose own membership
  is empty; `test_weekly_priority_exposure_floor.py` gains injury/equipment
  negative cases.

### F07 · P1 · RC-C / RC-E — A carry microdose certifies "build strength" while the same role marks it unloaded support

- **Reproduction:** S12 (professional MMA, strength primary, 42 days) — every
  strength witness is *Loaded Carry Touch* (D-41, D-34, D-25, D-18); S16 — all
  three witnesses are carries inside conditioning sessions; S27 — two of three.
  All report `strength: build, satisfied`.
- **Why:** `_microdose_stimuli` (`goal_preservation.py`) emits the spec's
  `intents: ["meaningful_strength"]` without the quality-class / loaded-anchor
  test `_strength_stimuli` applies (docs/goal_preservation.md: "a loaded
  anchor class"), while `_sync_microdose_membership` stamps the same exercise
  `effective_loaded: False`, `dose_role_kind: support`.
- **Effect:** goal preservation's verdict hides real loss — S12's GPP
  "primary strength" session is one farmer-carry hold plus the 2 x 20 m carry
  (the KB swing and every DB press/RDL/pull-up were dropped by the cap and
  pre-hard-contact pruning, see R6).
- **Minimal correction:** a microdose witness may satisfy `maintain`, never
  `build`, and only for intents its own envelope agrees with.
- **Regression tests:** S12 strength is `defer`/unsatisfied with a cited
  constraint, or satisfied by an `anchor_loaded` witness.

### F08 · P1 · RC-B — Conditioning (and late) roles are scheduled with no possible member and ship empty

- **Reproduction:** known case S01 — `fight_pace_repeatability_day`, Saturday
  D-15, `selected_exercise_assignments: []`. Also S02, S04, S05, S07 (two empty
  conditioning roles on the same day), S08, S23–S25, S28; empty "converted
  mobility / rehab-friendly support" days in S16 and S28; empty late-tail
  strength/alactic roles in S14, S16, S28.
- **Why (known case):** the role map creates conditioning roles from the
  weekly stress map's `conditioning_sequence`
  (`stage2_role_map.py:3532-3602`) without consulting
  (a) the Stage 1 pool — SPP `missing_systems: ["glycolytic"]` is only written
  to the omission ledger (`stage2_payload.py:2188-2196`); or
  (b) the bridge rule that set the pool's glycolytic allowance to zero:
  `glycolytic_touch_max` is 0 at D-15…D-17 and is forced to 0 by any declared
  hard day in the bridge (`stage2_payload_late_fight.py:777-826`, `:1040-1043`).
  `_bridge_allows_pressure_touch` (`stage2_role_map.py:3210`) is consulted only
  by the combat-pressure floor, not by the base SPP glycolytic role.
  In S07 the alactic slot's only candidate (*Explosive Boxing Burst Intervals*)
  is `fulfillment_authority: false`, which conditioning composition rejects
  (`session_composition.py:1878-1892`).
- **Downstream:** composition writes
  `underfill_reason: phase_system_workload_unmet` — **no code reads it**; no
  validator or planner-authority rule checks an empty *normal-camp* closed role
  (`planner_authority_integrity.py:296-317` covers late-tail roles only); the
  render manifest emits it as a closed role with `selected_count: 0`
  (`stage2_payload.py:3047-3059`) and the Stage 2 prompt forbids filling it
  ("An empty selected_exercise_assignments list is not creative freedom").
  The athlete therefore gets a titled session with no content, or AI filler
  prose.
- **Meanwhile:** the secondary conditioning goal reads `maintain: satisfied`
  from an 8-minute *Shadowboxing Aerobic Flow* support insert on D-16 (policy-
  compliant, see R4).
- **Earliest stage:** weekly role budget (role existence).
- **Minimal correction:** at role creation, a conditioning system the scheduled
  day cannot legally host (bridge/late caps) or the phase pool cannot supply is
  not created; the role-budget owner either substitutes the next system in the
  sequence that *has* a legal candidate or records the role as suppressed with
  a reason. Late-tail/converted roles with empty membership become `suppressed`
  with their diagnostics rather than surviving.
- **Regression tests:** invariant over the scenario matrix: no surviving
  strength/conditioning role with an empty closed list unless it carries an
  authoritative body (`render_authority`); S01 week 1 has either a populated
  conditioning role or a recorded suppression.
- **Interaction:** weekly physical session counts can fall; goal preservation
  must see the suppression reason to defer honestly.

### F09 · P1 · RC-D — Strength membership is composed before the governor, and later moves stack sessions

- **Evidence of order:** `stage2_payload._build_planning_brief`
  (`fightcamp/stage2_payload.py:1491-1499`) runs
  `compose_normal_strength_assignments` **before**
  `apply_late_camp_role_morph`, which itself runs
  `apply_final_calendar_integrity` and the pre-hard-contact cap
  (`late_camp_role_morph.py:390-415`). The contract (§2, §4) states the
  opposite order ("membership … run after the governor").
- **Consequences reproduced:**
  - S25 (MMA 21 d): `transfer_strength_day` composed for Friday D-16, then the
    governor moved it to Thursday D-17 (`adjacent_day_systemic_then_mechanical`)
    — the same day as `neural_plus_strength_day`. Two strength sessions on one
    day, inside the bridge window where `double_stress_day_allowed` is false.
  - S09/S11 (56/70 d): composition's own adjacent-strength-recovery path
    (`session_composition.py:1036-1160`, calling
    `calendar_integrity.relocate_or_suppress_role_for_recovery` at `:1147`)
    moved `neural_plus_strength_day` Tuesday → Saturday, onto the day that
    already holds `fight_pace_repeatability_day`, in three consecutive weeks.
  - S11: the stale composition (built for D-19) meets the D-15 envelope → F10.
- **Why:** `_best_destination` (`calendar_integrity.py:170-203`) ranks
  `ALLOW` before occupancy, so an occupied `ALLOW` day beats an empty
  `DEPRIORITIZE` day; only the realised-load revalidation passes
  "never onto a day that already carries a physical session". Three callers,
  three destination doctrines.
- **Also:** composition is documented as calendar-read-only, yet it relocates
  and suppresses roles.
- **Minimal correction:** move strength composition after the morph/governor
  (as documented) and recompose — not only re-dose — a strength role the
  governor relocates; give the mover one destination doctrine (occupied
  physical days are excluded unless the occupant is coexistable).
- **Regression tests:** matrix invariant "no two strength roles on one day
  D-14+, no strength role relocated onto a day holding glycolytic conditioning";
  `test_calendar_integrity_characterization.py` gains an occupied-ALLOW vs
  empty-DEPRIORITIZE case.
- **Interaction:** high — this changes placement for many long camps; ship
  behind the full matrix.

### F10 · P1 · RC-E — Two definitions of "loaded" turn ordinary plans into deterministic holds

- **Reproduction:** S11 week 8 (Barbell Thruster, Woodchopper (Cable) at D-15)
  and S30 week 2 (Kettlebell Swing at D-16): `planner_authority_findings`
  returns `selected_loaded_exercise_forbidden` (severity *blocker*).
- **Why:** the scheduled-day envelope says `loaded_allowed: false`
  (`late_camp_strength_retention`); `prescription_resolver` still doses the
  items, classifying them as `power` with `effective_loaded: False`
  ("3 x 2 at max speed"). The authority gate classifies by equipment
  (`planner_authority_integrity.py:242-253`, barbell/kettlebell/cable are
  loaded) and `governed_release_policy` (`:564-613`) sets
  `release_decision: hold`. Composition consults neither.
- **Production effect (contract §3.1):** Stage 2 holds, the structured card is
  never attempted, persistence releases the markdown as
  `publishable_with_flags`. The athlete gets a plan without the card; admins
  see a "planner bug" signal on a plan whose inputs were valid.
- **Minimal correction:** one `is_loaded(item)` owned by the dose resolver,
  imported by the authority gate; composition filters by the scheduled-day
  envelope (after F09's reorder) instead of letting the gate catch it.
- **Regression tests:** S11 and S30 replay with no authority blocker; a
  resolver/gate agreement test over every strength-bank item.

### F11 · P1 · RC-F — Long wrestling and Muay Thai camps crash with `TacticalWatchBankExhausted`

- **Reproduction:** `repro/crash_probe.py`: wrestling 35 d, 42 d (with or
  without hard days), 70 d; Muay Thai 56 d and 84 d → exception
  `no unused Tactical Watch for style='generic' phase='TAPER'`. Boxing, MMA,
  kickboxing and BJJ at the same lengths succeed.
- **Why:** the generic TAPER bank holds 2 watches for wrestling/BJJ/Muay Thai
  (6 for boxing); `select_tactical_watch` raises when every key is used
  (`tactical_watch_library.py:351-375`); `camp_week_fillers.apply_camp_week_fillers`
  calls it unguarded (`camp_week_fillers.py:486`), inside
  `build_stage2_outputs`, which `fightcamp/main.py:405` does not wrap. The
  orchestrator records a failed generation.
- **Minimal correction:** allow reuse (least-recently-used) or a zero-cost skip
  with a recorded reason when the bank is exhausted, matching the open-plan
  path that already catches it (`stage2_payload_open_ongoing.py:132`); add
  TAPER watches for the three sports.
- **Regression tests:** parametrised e2e over every supported sport × {35, 56,
  84} days must return a plan.

### F12 · P1 · RC-A — A strength goal or weakness is silently erased at ≤ 20 days with any declared hard day

- **Reproduction:** `repro/strength_drop_probe.py`. 20 days, Thursday hard
  sparring, goals strength + speed, primary strength, weakness strength →
  `key_goals ['speed']`, weaknesses `[]`, primary goal speed, disposition
  `none`. 21 days or no hard day → preserved.
- **Why:** `PlanInput.from_payload` (`fightcamp/input_parsing.py:34`,
  `:1131-1147`) strips `strength` from goals and weak areas when
  `days_until_fight <= 20` and any hard day is declared — even though the
  sparring resolver will convert most of those days to technical (D-14 cutoff).
  No disposition, constraint or note is recorded; goal preservation never
  learns the goal existed. Likely origin #1908.
- **Classification note:** limiting *strength development* this close to a
  fight may be intended policy; erasing the selection without a recorded
  deferral is the defect.
- **Minimal correction:** keep the selection and let goal preservation record
  `defer` with a `fight_proximity` / `hard_contact` constraint (its existing
  mechanism).
- **Regression tests:** the probe's 20-day case keeps `strength` in
  `goal_preservation` with state `defer` or `maintain` and a cited constraint.

### F13 · P2 · RC-E — Goal-coverage windows and fight-proximity deferral disagree with the calendar

- **Reproduction:** S18 (wrestling, 14 days): conditioning `build` window is
  `[D-14, D-14]`, but the first plannable day is D-13 — unsatisfiable by
  construction → `goal_preservation_failed`. S14 (10 d) and S19 (3 d): speed
  `maintain` carries reason `fight_proximity` but no constraint → failed.
- **Why:** `_requirements` (`goal_preservation.py:833-863`) anchors windows at
  `days_until_fight`, not the first calendar day; `_deferral_constraints`
  (`:1135-1141`) accepts fight proximity only at ≤ 1 day (≤ 7 for strength),
  although the classifier (`classify_goal_preservation`) already marks ≤ 13 as
  fight-proximity limited, and the late-fight path skips repair entirely.
- **Effect:** every short-notice camp ships `publishable_with_flags` with a
  goal failure that is not a planner defect (alert fatigue).
- **Minimal correction:** clamp windows to the calendar; accept the
  classifier's `fight_proximity` as a deferral for maintain obligations inside
  D-13.
- **Regression tests:** S14/S18/S19 report `defer` with `fight_proximity`.

### F14 · P2 — "Rehab-friendly low-load support" sessions contain kettlebell-swing EMOMs (or nothing)

- **Reproduction:** S16 and S28 (BJJ, low/improving shoulder pain): converted
  support days labelled *Rehab-friendly low-load support* hold *Kettlebell
  Swings (EMOM Aerobic)* (600 s active work); week-1 equivalents are empty.
- **Why:** converted roles keep `preferred_system: aerobic` and draw from the
  ordinary aerobic slot; nothing checks the "low-load" label against the
  member's cost metadata.
- **Minimal correction:** converted low-load/rehab-friendly roles take only
  members with verified low-cost metadata (same predicate as F04).

### F15 · P3 — Dead or misleading planner state

- `double_stress_day_allowed` is computed by `compute_bridge_rules` and never
  read (`grep` shows writes only).
- `underfill_reason` / `workload_limited` (`session_composition.py`) and
  `missing_systems` (outside the omission ledger) have no consumer.
- Compression reason codes are athlete context, not cause: S01 suppresses the
  *recovery* day "to protect freshness under active weight cut"
  (`stage2_role_map.py:2979-3000`); S06 repeats the same deferral constraints 15
  times.
- `session_composition._role_days_until_fight` (`:769-783`) is a fourth D-day
  resolver (reads `countdown_offset` first, never `scheduled_d_day`), the same
  smell the contract removed from the validator (§9.2 item 10); S11's policy
  records day 19 for a D-15 role.
- Contract drift: §4 execution order (F09), §3 goal-preservation authority
  (F06) and invariant 11 describe code that no longer exists.

---

## Probable risks (evidence-backed, not proven defective)

| ID | Risk | Evidence | Why not "confirmed" |
| --- | --- | --- | --- |
| R1 | Balance/coordination weaknesses (delegated to `coordination_support_library`) are also undelivered | 0 `coordination_support` inserts in 9 probes (`deleg_probe.py`) and in S30; the insert competes for a discretionary filler slot (`camp_week_fillers.py:497-509`) | S30 does get an `aerobic_coordination_day`; coordination may be served by role choice rather than the library. Needs a coverage verdict (F03a) to decide |
| R2 | High-skill plyometrics for 0-0 novices (Depth Jump to Sprint, Barbell Thruster, Ballistic Box Jump in S10/S22) | Matrix | `competitive_maturity` is deliberately wording-only (`stage2_payload.py:2323`); the intake has no training-age field. Policy gap, not a code defect |
| R3 | Structured cards are faithful to Stage 2 text, not to closed membership | `api/structured_plan_faithfulness.py` checks the markdown source | By contract; not exercised without live model calls |
| R4 | A secondary conditioning goal is "maintained" for D-21…D-2 by one 8-minute shadow flow | S01 evidence | Documented policy ("explicit conditioning-maintenance inserts can maintain") — quality question only |
| R5 | Same late-tail primer repeated (Pocket Frame-Burst Touch D-13 and D-5; Explosive First-Step Cue ×3 in S18) and strength-labelled days with no strength | Matrix | Deliberate style-taper preference (`stage2_payload.py:1057-1084`); `support_only_fill` is recorded |
| R6 | Pre-hard-contact policy turns a whole camp into "D-17…D-14 retention" doses when every training day neighbours a hard day (S12: one strength role, D-41 onward, reduced to a farmer-carry hold) | S12 envelope `dose_adjustment_reason: pre_hard_contact_strength_retention` at D-41 | The rule is documented (#2435); the resolver also prunes members (`prescription_resolver.py:940-960`), a second membership writer the contract does not list |
| R7 | Audit ran without spaCy (degraded injury parsing) | Environment | Guided-injury paths do not depend on spaCy; free-text injuries were not tested |

## Deliberate policy decisions verified as working (not bugs)

- **Hard-sparring cutoff.** Known case: D-17 Thursday stays hard
  (`hard_as_planned`); D-10 and D-3 convert to technical with
  `d14_hard_sparring_ban`. High fatigue (S06) brings it forward:
  D-17 converts with `d17_hard_sparring_ban`. Low/stable foot pain does not
  elevate risk (S02), consistent with `docs/hard_sparring_cutoff.md`.
- **Injury triage gates.** Moderate/worsening foot (S03), moderate/stable
  ankle sprain (S13) and high/stable knee (S20) route to `needs_review`.
- **Late-fight ownership.** D-13 inward is owned by the tail in every dated
  camp; no normal role was re-placed inside it.
- **Two-hard-day / pre-hard-contact single strength exposure** (S12, S16, S30).
- **Determinism.** Seeds 7 and 99 produce identical calendars and membership
  (S01 vs S23, S02 vs S24); repeated runs are identical. All findings above are
  deterministic Stage 1 behaviour, not AI variability.
- **Release invariant.** Validator findings never block; holds are released
  with flags by persistence (test-locked).
