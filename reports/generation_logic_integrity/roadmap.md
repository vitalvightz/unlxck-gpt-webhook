# Prioritised repair roadmap

The 15 confirmed findings reduce to six shared root causes (`findings.md`
RC-A…RC-F). The plan below repairs them in **six focused PRs**, each inside an
existing canonical owner, each adding no new rule layer. Nothing here changes
the D-14/D-17 hard-sparring cutoffs, triage gates, taper bands, late-tail
ownership or the release invariant.

Each PR lands with: the scenario matrix replayed (`repro/matrix.py`), the
listed invariants added as tests, and a written before/after for the
anonymised boxer case.

## Order and rationale

| # | PR | Root cause | Findings closed | Severity | Owner touched | Risk |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Close the safety bypasses | RC-C, RC-F | F05, F06 (+F07 partial) | P0 | `injury_exclusion_rules.py`; `goal_preservation.py` microdose tier | Low–medium |
| 2 | Stop crashing and silently dropping | RC-F, RC-A | F11, F12 | P1 | `camp_week_fillers` / `tactical_watch_library`; `input_parsing` + `goal_preservation` deferral | Low |
| 3 | A role exists only if it can be filled | RC-B | F08, F14 | P1 | `stage2_role_map` (role budget); `session_composition` (converted roles) | Medium |
| 4 | One calendar order, one destination doctrine, one "loaded" | RC-D, RC-E | F09, F10, F15 (D-day resolver) | P1 | `stage2_payload` orchestration order; `calendar_integrity`; `prescription_resolver` → `planner_authority_integrity` | High |
| 5 | Weaknesses that the planner can actually deliver | RC-A, RC-E | F01, F02, F03, F04 | P1 | `strength` selector input; bank metadata; `session_composition` trunk reserve; `goal_preservation` delegated verdict | Medium–high |
| 6 | Honest goal evidence and contract sync | RC-C, RC-E | F07, F13, F15, contract drift | P2/P3 | `goal_preservation`; `PLANNER_ARCHITECTURE_CONTRACT.md` | Low |

PR 1 goes first because it is safety and small. PR 4 precedes PR 5 because
the trunk reserve (PR 5) must be composed on the final calendar, otherwise it
inherits F09/F10. PR 3 precedes PR 5 because the embedded-trunk path depends
on non-empty conditioning roles.

---

## PR 1 — Close the safety bypasses (P0)

**Change**
- Foot and toe rules: add `mech_landing_impact`, `mech_lower_jump`,
  `mech_reactive_rebound`, `mech_max_velocity`, `mech_acceleration` with the
  ankle's severity weighting (clinical sign-off on the low-severity
  allow/modify boundary).
- Microdose tier: draw the microdose from the week's already-filtered phase
  pool (same intents), never from `_MICRODOSE_SPECS` literals; if no pool item
  qualifies, record `floor_no_safe_candidate`. Refuse a host whose own closed
  membership is empty (conditioning host with nothing in it).

**Tests**
- `test_injury_exclusion_hardening.py`: foot × {low, moderate, high} ×
  {Jump Squat, Box Jump, Sprint Acceleration, Reactive-start-type items}.
- `test_weekly_priority_exposure_floor.py`: injured athlete (foot, ankle,
  knee, Achilles, shoulder) and bodyweight-only athlete receive no
  non-compliant microdose.
- Matrix invariant: no assignment on an injured athlete carries a tag banned
  for that region; no assignment requires equipment the athlete lacks.

**Must not regress:** speed/power build coverage where a compliant pool item
exists (S01 still covers speed in week 1 if a compliant item exists; if not,
it reports an honest gap).

## PR 2 — Stop crashing and silently dropping (P1)

**Change**
- Tactical Watch: least-recently-used reuse (or a recorded zero-cost skip)
  when the bank is exhausted, as the open-plan path already does; add TAPER
  watches for wrestling, BJJ and Muay Thai.
- Intake: keep a `strength` goal/weakness at ≤ 20 days with hard sparring;
  express the restriction as a goal-preservation deferral with a cited
  constraint instead of erasing the selection.

**Tests**
- e2e grid: 6 sports × {14, 35, 56, 84} days × {0, 2 hard days} returns a
  plan.
- Intake test: 20-day strength-primary athlete keeps `strength` in
  `goal_preservation` with `defer`/`maintain` and a constraint.

## PR 3 — A role exists only if it can be filled (P1)

**Change** (role-budget owner only)
- When creating a conditioning role for a scheduled day, ask the existing
  bridge/late caps (`compute_bridge_rules` for that D-day) and the phase pool's
  eligible systems. If the system is not legal or has no fulfilment-authorised
  candidate, take the next system in `conditioning_sequence` that has one, or
  record the role as suppressed (`no_eligible_candidate`, with the system).
- Converted low-load / rehab-friendly roles accept only members with verified
  low-cost metadata; otherwise suppress.
- Late-tail roles that end with empty membership are suppressed with their
  `late_assignment_diagnostics` (today they survive and are only "explained").

**Tests**
- Matrix invariant: no surviving strength/conditioning role with an empty
  closed list unless `render_authority` supplies its body.
- S01: week 1 has a populated conditioning role or a recorded suppression;
  S07: no two empty roles on D-15.
- Goal preservation sees the suppression and defers with that reason.

**Interaction:** weekly session counts can drop; frequency audit and
`session_count_summary` must report the reduction (they already support
`reduced_from_planned`).

## PR 4 — One calendar order, one destination doctrine, one "loaded" (P1)

**Change**
- Orchestration: run `compose_normal_strength_assignments` *after*
  `apply_late_camp_role_morph` (governor + pre-hard cap), as the contract
  already documents; when a later mover relocates a composed strength role,
  recompose it (not only re-dose).
- `calendar_integrity._best_destination`: exclude days that already hold a
  non-coexistable physical session (the rule the realised-load revalidation
  already uses), and honour the bridge `double_stress_day_allowed` (or delete
  it — PR 6). Composition stops calling the mover directly; it reports the
  adjacency conflict and the governor resolves it.
- One `is_loaded(item)` owned by `prescription_resolver`, imported by
  `planner_authority_integrity`; composition filters members against the
  scheduled-day envelope.
- Replace `session_composition._role_days_until_fight` with
  `calendar_context.role_d_day`.

**Tests**
- Matrix invariants: no two strength roles on one D-14+ day; no strength role
  relocated onto a glycolytic day; zero `selected_loaded_exercise_forbidden`
  across the matrix (S11, S30 replay clean).
- `test_calendar_integrity_characterization.py`: occupied-ALLOW vs
  empty-DEPRIORITIZE destination case.
- `test_step10_architecture_closure.py` / `test_placement_ownership.py`:
  composition no longer imports the mover.

**Risk:** highest of the set; placement changes for many long camps. Review
against the full chain (contract §10 checklist) and the calendar-integrity
fixtures.

## PR 5 — Weaknesses the planner can actually deliver (P1)

**Change**
- Strength selector input: expand weaknesses through `WEAKNESS_TAG_MAP`
  (as conditioning does), keeping the priority-profile weights.
- Bank metadata (coordinate with the metadata-integrity roadmap, no new
  vocabulary): author `late_windows`, and SPP phase where the notes already
  say late-safe, for the low-load trunk family (Bird Dog Hold, Dead Bug
  (Isometric), Pallof Press Iso, Plank variants, Side Plank, Suitcase Carry
  Holds).
- Low-load trunk classifier: require `mech_trunk_*` and verified low-cost
  metadata; reject systemic-fatigue, CNS-high and ballistic tags; stop
  skipping unverified embedded items in `realised_session_stress`.
- Composition: when a trunk/balance weakness is selected, reserve one
  embedded support slot before the readiness cap trims development work (it
  does not count toward `major_family_limit`; dose = embedded support dose).
- Goal preservation: delegated weaknesses get a coverage *verdict* (evidence
  of the delegated family at least once per 7 days through D-8), reported in
  the brief and validator, never floor-repaired.

**Tests**
- Known-case e2e (both injury variants): ≥ 1 low-load trunk member in weeks
  1 and 2; D-17 hard; D-10/D-3 technical; no member over the readiness cap.
- 56-day S09: trunk member in at least two GPP/SPP weeks.
- Classifier parametrised over the bank (Sled Push, Yoke Walk, Sledgehammer,
  Lateral Raise rejected; Plank, Bird Dog Hold accepted).
- Delegated verdict reported for balance/coordination (resolves R1).

**Interaction:** re-baselines strength pools for every weakness; run the
whole matrix and the goal-preservation e2e suites.

## PR 6 — Honest goal evidence and contract sync (P2/P3)

**Change**
- A microdose witness may satisfy `maintain`, never `build`, and only for
  intents its own envelope agrees with.
- Coverage windows clamp to the first plannable day; inside D-13 accept the
  classifier's `fight_proximity` as a maintain deferral.
- Deduplicate deferral constraints; compression reason codes name the cause
  (budget vs readiness), not the athlete's whole context.
- Remove or consume dead state: `double_stress_day_allowed`,
  `underfill_reason`, `missing_systems` outside the ledger.
- Update `PLANNER_ARCHITECTURE_CONTRACT.md`: §4 execution order, §3
  goal-preservation authority (microdose tier and its bounds), the
  prescription resolver as a member-dropping owner (pre-hard pruning),
  delegated-weakness verification.

**Tests**
- S12/S16 strength no longer "build satisfied" by carries alone.
- S14/S18/S19 report `defer` with `fight_proximity`, no failure flag.

---

## Verification plan for every PR

1. `python repro/matrix.py` — compare `out/metrics_all.json` against the
   previous run; every change must be explained by the PR.
2. Focused suite (see `verification.md`) plus the full fast lane.
3. Invariants to keep green after all six PRs:
   - D-17 hard / D-10, D-3 technical in the known case; S06 D-17 technical.
   - Triage blocks for S03, S13, S20 unchanged.
   - Late-tail roles never re-placed by normal-camp code.
   - Determinism: seed 7 == seed 99 == repeat run.
   - Release invariant (`test_validator_release_invariant.py`).
