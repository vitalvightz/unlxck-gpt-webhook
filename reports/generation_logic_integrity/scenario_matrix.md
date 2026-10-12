# Scenario matrix

All scenarios run the real Stage 1 path (`generate_plan_sync`) with clock
2026-01-04 12:00 UTC, seed 7 unless stated, timezone UTC, availability
Monday–Saturday unless stated, a full gym equipment list unless stated, and
amateur 0-0 boxing at 68 → 65 kg unless stated. Definitions live in
`repro/matrix.py`; full per-week output is in
`evidence/scenario_matrix_run.txt` and a one-line-per-scenario summary in
`evidence/scenario_summary_table.txt`.

Dimensions covered (pairwise, not exhaustive): camp length 3 → 84 days and
open camp; render modes normal / late-fight / open-ongoing; phases GPP, SPP,
TAPER; all six supported sports; amateur novice, experienced and professional;
frequency 2, 3, 4, 5, 6; zero to three hard days; no cut, moderate (4–5 %) and
7 % cuts; low / moderate / high fatigue; full gym, bodyweight-only and
strongman equipment; no injury, foot, ankle, Achilles, knee, shoulder and
low-back injuries at several severities/trends, plus the admin triage-resume
path.

## Results

Legend — **trunk**: trunk/core members actually delivered (any owner);
**empty**: surviving strength/conditioning roles with empty closed
membership; **md**: priority microdoses invented by goal preservation;
**gp**: goal-preservation state (`✗` = unmet); **auth**: planner-authority
findings (blockers hold release).

| ID | Scenario | Mode | trunk | empty | md | gp | auth / gp findings | Findings |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| S01 | Boxer 21 d, no injury (known case) | normal | — | D-15 glycolytic | Reactive Start Burst | speed build ✓, cond maintain ✓ | — | F01–F03, F06, F08 |
| S02 | S01 + foot low/stable | normal | — | D-15 | Reactive Start Burst | ✓ | — | F05, F06, F08 |
| S03 | S01 + foot moderate/worsening | **triage blocked** | | | | | | policy ✓ |
| S04 | S01, exactly 4 available days | normal | — | D-15 | RSB | ✓ | — | F08 |
| S05 | S01, no weight cut | normal | — | D-15 | RSB | ✓ | — | F03 (cap 3 still no core), F08 |
| S06 | S01, high fatigue | normal | — | — | — | speed defer ✗ | — | D-17 converts ✓; F15 duplicate constraints |
| S07 | S01, frequency 6 | normal | — | D-15 alactic + D-15 glycolytic | RSB | ✓ | — | F08 (two empty roles, same day) |
| S08 | S01, bodyweight only | normal | — | D-15 | RSB | ✓ | — | F08 |
| S09 | Boxer 56 d | normal | — | — | RSB | ✓ | — | F01, F09 (strength + glycolytic stacked ×3) |
| S10 | Boxer 56 d, novice, freq 3, strength primary | normal | carry microdose | — | Loaded Carry Touch | ✓ | — | F07, R2 |
| S11 | Boxer 70 d, strength/power, strongman equipment | normal | carry, sled (embedded) | — | Loaded Carry Touch | ✓ | **2 × selected_loaded_exercise_forbidden (hold)** | F04, F09, F10 |
| S12 | MMA 42 d pro, strength primary, gas-tank weakness, moderate fatigue, 2 hard | normal | carries | — | Loaded Carry Touch | strength build ✓ (carries only), power defer | — | F07, R6 |
| S13 | Muay Thai 28 d, ankle sprain moderate/stable, 7 % cut | **triage blocked** | | | | | | policy ✓ |
| S14 | Kickboxing 10 d | late-fight | — | late D-6, D-1 (omittable) | — | speed maintain ✗ | goal_preservation_failed | F13 |
| S15 | Boxing open camp 8 w | open-ongoing | n/a | n/a | n/a | n/a (by design) | — | out of goal-contract scope |
| S16 | BJJ 35 d, shoulder low/improving, 2 hard | normal | carry microdose | 2 converted + 3 late | Loaded Carry Touch on conditioning hosts | strength build ✓ (carries only) | 3 × late_physical_role_missing_assignment (flag) | F06, F07, F08, F14 |
| S17 | Boxer 21 d pro 10-2, 3 hard, 10 x 3 | normal | — | — | RSB | ✓ | — | — |
| S18 | Wrestling 14 d, conditioning primary | normal (tail) | — | — | — | cond build ✗ | goal_preservation_failed | F13 (window D-14 outside calendar) |
| S19 | Boxer 3 d | late-fight | — | — | — | speed maintain ✗ | goal_preservation_failed | F13 |
| S20 | S01 + knee high/stable | **triage blocked** | | | | | | policy ✓ |
| S21 | Boxer 35 d, low-back tightness, power/speed | normal | rehab trunk ✓ | — | Med-Ball Rotational Throw | power ✓, speed defer | — | trunk only via rehab |
| S22 | Boxer 28 d, no hard sparring, conditioning primary | normal | — | — | — | ✓ | — | R2 (depth jumps for novice) |
| S23 | S01, seed 99 | normal | identical to S01 | | | | | determinism ✓ |
| S24 | S02, seed 99 | normal | identical to S02 | | | | | determinism ✓ |
| S25 | MMA 21 d, strength primary | normal | — | D-15 | — | speed maintain ✗ | goal_preservation_failed | F08, **F09 (two strength roles D-17)** |
| S26 | Boxer 49 d, frequency 2 | normal | — | — | RSB | ✓ | — | — |
| S27 | Boxer 35 d, bodyweight only, strength/power | normal | Hollow Body Hold, carry | — | **Loaded Carry Touch (no equipment)** | ✓ | — | F06, F07 |
| S28 | BJJ 35 d, shoulder low, 1 hard | normal | — | 5 normal + 3 late | — | strength ✓ | 3 × late missing (flag) | F08, F14 |
| S29 | S01 + ankle low sprain | normal | — | D-15 | RSB on injured athlete | ✓ | — | F06 |
| S30 | Muay Thai 28 d, no injury, 7 % cut, balance weakness | normal | anti-rotation hold | — | — | ✓ | **selected_loaded_exercise_forbidden (hold)** | F10, R1 |
| S31 | Wrestling 42 d | **crash** `TacticalWatchBankExhausted` | | | | | | F11 |
| S32 | Kickboxing 35 d, speed/power | normal | farmer carry hold | — | RSB | power maintain ✗ | goal_preservation_failed | F01 |

Targeted probes (not in the table): `repro/injury_matrix.py` (foot
moderate/stable blocked; foot low/improving and admin-resumed foot high keep
Jump Squat; ankle/Achilles/knee drop it), `repro/crash_probe.py` (sport ×
length crash grid), `repro/strength_drop_probe.py` (20 vs 21 days),
`repro/deleg_probe.py` (balance / coordination / trunk × 21 / 35 / 56 days —
zero delegated exposures).

## Aggregate signals

Counts over the 27 completed dated scenarios (32 total minus 3 triage blocks,
1 crash and the open camp):

- Trunk-strength weakness selected in 25 (primary in 23); the delegated
  subsystem produced **0** suitable exposures, and 1 unsuitable one (S11 sled).
- Empty closed physical roles survived in the normal-camp calendar of 12
  (late-fight direct sequences not counted).
- Invented microdoses appeared in 20, including 5 injured athletes and 1
  bodyweight-only athlete.
- 2 carry a planner-authority **hold**; 5 ship with an observational
  `goal_preservation_failed`; 1 of 32 inputs crashes.

## AI variability

None of these results involves a model call. Stage 1 is fully deterministic
for a fixed clock and input (seed 7 = seed 99 = repeated runs). Stage 2 can add
variability only in wording and in open roles; every finding here exists in
the deterministic handoff the model is told not to change.
