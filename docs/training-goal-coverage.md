# Training Goal coverage implementation

Base: Main `371cbeed29cc20eed693f4b8abdbe5540c1cc030`.

Original verified Goal coverage: **222/1,010 (22.0%)**. Added **44 assignments on 44 previously unclassified Training entries**. Updated coverage: **266/1,010 (26.3%)**. Existing assignments corrected: **0**.

Assignments: 24 Coordination, 4 Balance, 2 Strength, 1 Maximal strength maintenance, 4 Power, 2 Speed, 3 Stamina, 2 Conditioning, 2 Reaction speed.

## Evidence and scope

Each review lives in the existing discovery-only `shared/training-metadata.json` projection and binds the original catalogue ID to its unchanged source-row SHA256 and original missing-Goal issue from PR #2822. The preview retains raw execution, method/quality, phase, intensity and dose evidence. No Goal is inferred automatically from a name, apparatus, mechanical tag, energy label or search synonym.

- Strength: Back Squat and Front Squat combine explicit strength method and loaded squat movement with their existing SPP dose of 3-5 sets of 3-5 at 85-90% 1RM. This supports Strength, without claiming every GPP dose builds maximal strength.
- Strength maintenance: Trap Bar Deadlift explicitly declares retention, familiarity, non-grinding execution, low volume and D-21 to D-8 restrictions.
- Power: light/full-rest hip-driven scoop throws, crisp low-volume Olympic lifting, explicit BikeErg power-adaptation repeats and explosive airborne push-ups with full rests.
- Speed: explicit sprint acceleration qualities with maximum-speed/full-rest programming, and punch-fast/release instructions with a handspeed cue and short sets.
- Aerobic endurance: Arm Ergometer, Nasal Breathing Ruck March and Hiking prescribe 35-60 continuous minutes at Zone 2; conversational-pace guidance adds evidence for the ruck. They use the existing Stamina label, not a new vocabulary ID.
- Anaerobic conditioning: Battle Ropes Tempo Burner and Heavy Bag Power Intervals combine explicit glycolytic purpose/high lactate load with 30-40-second hard bouts and their actual work/rest structure. They use the existing canonical Conditioning goal; explosive tags do not make these fatigue protocols Power drills.
- Reaction speed: an unpredictable partner toss cue or explicit coach go-cue initiates repeated responses with recovery. Generic reactive/rebound mechanisms are excluded.
- Coordination/Balance: explicit sequencing, limb-timing, landing and stance-recovery purposes are practised for eight minutes at RPE 4.

Programming context is retained only for the five strength-bank reviews that need it, with the exact existing classifier, phase, archetype, dose, source file and source hash. This is a review receipt, not a programming change.

## Exact catalogue records

| Original catalogue ID | Exercise | Goal | Raw evidence excerpt |
|---|---|---|---|
| `coordination/grappling.json:grapple.hipheist_base` | Hip-Heist to Base | Coordination | Coordinate opposite hand-foot support through a common scramble transition. |
| `coordination/grappling.json:grapple.pass_recover_base` | Pass-Recover-Base Flow | Coordination | Build smooth transitions between passing movement and a stable base. |
| `coordination/grappling.json:grapple.shrimp_frame_recover` | Shrimp-Recover-Frame | Coordination | Coordinate hip escape with frame recovery instead of treating them as separate actions. |
| `coordination/kicks.json:kick.cross_leadkick_switch` | Cross-Lead Kick Switch | Coordination | Improve upper-to-lower sequencing when the strike changes sides. |
| `coordination/kicks.json:kick.jab_lowkick_reset` | Jab-Low Kick Reset | Coordination | Link hand entry, lower-body rotation and stance recovery. |
| `coordination/kicks.json:kick.kick_and_stick` | Kick-and-Stick | Balance | Teach every kick to finish in a stable stance rather than a loose landing. |
| `coordination/kicks.json:kick.knee_step_recover` | Knee-Step-Recover | Coordination | Coordinate the knee action with a stable return step. |
| `coordination/kicks.json:kick.longguard_teep_reset` | Long Guard-Teep Reset | Coordination | Coordinate upper-body frame position with a long-range lower-body action. |
| `coordination/kicks.json:kick.punch_kick_pivot_chain` | Punch-Kick-Pivot Chain | Coordination | Coordinate a mixed striking chain that finishes in a new lane. |
| `coordination/kicks.json:kick.rearkick_punch_exit` | Rear Kick-Punch Exit | Coordination | Turn kick recovery into a usable punching and exit position. |
| `coordination/kicks.json:kick.switchkick_stance_recovery` | Switch-Kick Stance Recovery | Balance | Make the switch step and kick return to an organised stance. |
| `coordination/kicks.json:kick.teep_recover_jab` | Teep-Recover-Jab | Coordination | Coordinate long-range kicking with immediate hand readiness. |
| `coordination/mma_transitions.json:mma.jab_doubleleg_pattern` | Jab-to-Double-Leg Entry Pattern | Coordination | Link a simple striking entry to wrestling footwork. |
| `coordination/mma_transitions.json:mma.kick_levelchange_reset` | Kick-to-Level-Change Reset | Coordination | Train the athlete to recover from a kick into wrestling-ready posture. |
| `coordination/mma_transitions.json:mma.strike_levelchange` | Strike-to-Level-Change | Coordination | Connect striking posture to a clean level change without a pause or collapse. |
| `coordination/striking.json:strike.check_hook_exit` | Check Hook Exit | Coordination | Coordinate the scoring hook with the exit rather than spinning away from stance. |
| `coordination/striking.json:strike.corner_exit_sequence` | Corner Exit Sequence | Coordination | Coordinate defence, turn and exit when space is restricted. |
| `coordination/striking.json:strike.cutoff_step_combo` | Cut-Off Step to Combination | Coordination | Coordinate ring cutting with a short scoring sequence. |
| `coordination/striking.json:strike.double_jab_exit_angle` | Double Jab to Exit Angle | Coordination | Link forward scoring actions to a balanced angle exit. |
| `coordination/striking.json:strike.jab_step_sync` | Jab-Step Sync | Coordination | Synchronise the lead hand with the lead step so range is gained without reaching. |
| `coordination/striking.json:strike.pivot_reset_shadow` | Pivot-Reset Shadowboxing | Balance | Make the pivot end in a usable fighting stance instead of a loose spin. |
| `coordination/striking.json:strike.pocket_roll_return` | Pocket Roll-Return | Coordination | Improve close-range timing without turning the drill into a high-output exchange. |
| `coordination/striking.json:strike.pressure_step_slip_hook` | Pressure Step-Slip-Hook | Coordination | Link forward pressure, head movement and a compact return. |
| `coordination/striking.json:strike.rear_hand_weight_transfer` | Rear-Hand Weight Transfer Reset | Coordination | Coordinate rear-side force transfer without falling over the front leg. |
| `coordination/striking.json:strike.rope_line_counter` | Rope-Line Head Movement to Counter | Coordination | Link head movement to stance recovery and a controlled counter. |
| `coordination/striking.json:strike.three_beat_combo_rhythm` | Three-Beat Combination Rhythm | Coordination | Develop clean sequencing across a short three-action combination. |
| `coordination/universal.json:universal.cross_body_pattern_reset` | Cross-Body Pattern Reset | Coordination | Improve opposite-side coordination used in striking, hand fighting and level changes. |
| `coordination/universal.json:universal.single_leg_posture_reset` | Single-Leg Posture Reset | Balance | Improve balance recovery after kicks, checks, shots and scrambles. |
| `exercise_bank.json:1090492c-7713-4845-89fc-f311b9088445` | Back Squat | Strength | strength; SPP: 3–5x3–5 @ 85–90% 1RM with contrast training (pair with explosive move). |
| `exercise_bank.json:21c9e4b8-181f-4f8d-a5d9-6ad56668c05c` | Front Squat | Strength | strength; SPP: 3–5x3–5 @ 85–90% 1RM with contrast training (pair with explosive move). |
| `exercise_bank.json:922966c7-4c19-430c-bee0-9c97e685f2c0` | Trap Bar Deadlift | Maximal strength maintenance | Low-dose strength-retention touch, D-21 to D-8 only, and only for fighters who already train the trap-bar deadlift (familiarity_required): never introduce it cold in the final stretch. Keep it non-grinding, no failure, no back-off volume, no soreness target; stop on any bar-speed or quality loss. The taper dose caps thin sets/reps as the fight nears. Not for D-7 or later. |
| `exercise_bank.json:4cf92eb8-9a32-4521-955f-5e0e3ef3fb2f` | Med Ball Scoop Toss | Power | Use a light medicine ball and full rest; drive from the hips and transfer force through the torso without chasing fatigue.; SPP: 4–6x2–5 reps at max speed; full rest 60–120s. |
| `exercise_bank.json:b83eb2e1-57a2-4c80-a80d-ac9cfc004047` | Hang Power Clean | Power | Technical Olympic-lift option for experienced MMA and wrestling athletes during GPP only; use low-volume, crisp reps.; GPP: 3–5x4–6 reps (or 6–10 throws) at crisp intent; rest 60–90s. |
| `conditioning_bank.json:84ac1db1-3346-4327-ba39-4d47f2936b2d` | BikeErg Power Repeats | Power | Brief hard efforts; excellent for power adaptation; 8x15s max, 45s rest |
| `conditioning_bank.json:173f1f90-762c-4560-9638-9b7253cad899` | Plyo Push-Up on Knees | Power | Push explosively, hands leave floor. Submax only. Full rest between sets.; 4x4 reps, 60s rest |
| `exercise_bank.json:a8de6b79-4ace-4600-8927-6cf645fbdb04` | Sprint Acceleration (10-20m) | Speed | sprint; SPP: 4–6x2–5 reps at max speed; full rest 60–120s. |
| `conditioning_bank.json:878abc67-af77-418f-a9b7-3ea58530dd96` | Band-Resisted Straight Punch Release | Speed | Band attached to rear hand. Punch fast and release. Cue: handspeed.; 3x5/side, 30s rest |
| `conditioning_bank.json:34750d3e-8926-439b-8523-5dbe9524bacd` | Arm Ergometer | Stamina | 35min |
| `conditioning_bank.json:47e35cda-985c-49e8-b92f-4b3df08b420d` | Nasal Breathing Ruck March | Stamina | Conversational pace, nasal breathing throughout.; 45-60min zone 2 |
| `conditioning_bank.json:4c71189e-8498-4901-94dc-489d5c87bdc6` | Hiking (Weighted Vest) | Stamina | 60min |
| `conditioning_bank.json:1f94dcf3-dc9c-4e90-bc4b-d81a364eb954` | Battle Ropes Tempo Burner | Conditioning | Upper body glycolytic work; lower body unloaded; 4x40s hard, 20s rest |
| `conditioning_bank.json:351fc3b2-c9ec-4332-9f57-a767794fef13` | Heavy Bag Power Intervals | Conditioning | 16oz gloves. Power shots only (RPE 8); 8x30s on/1:30 off |
| `conditioning_bank.json:2c6f32bb-6455-4af3-b9af-4430dc3a5315` | Reactive Med Ball Chest Pass | Reaction speed | Partner gives unpredictable toss cue. Ball: 3–5kg. Emphasize snap.; 6x3 reps, 45s rest |
| `conditioning_bank.json:867b1778-d022-4cd8-8d4c-39ec00cc0d36` | Wall Reactive Jump (Cue Start) | Reaction speed | Start facing wall, coach gives go-cue. Jump straight up.; 5x3 reps, 1min rest |

## Generator and preservation

Generator behaviour is unchanged. Strength scoring still matches original bank tags against athlete goals/weaknesses; conditioning and coordination still consume original bank qualities, doses and phases. None imports the discovery projection. No bank, scoring map, eligibility, priority, ranking, adaptive plan, dose, fatigue, injury rule, rehab rule, contact permission, permanent ID, exercise key or media association changes. No source identity rebinding is needed.

New Goal facets are excluded from lexical aliases and the search word bag. Query ordering/anchors and equipment, sport, type and body-focus AND filters remain unchanged. Phase declarations remain original; the library has no phase filter.

Original audit reports and baselines remain untouched. Historical replay excludes later Goal reviews and keeps original content revisions, 222-entry Goal coverage and browser fixtures. The original equipment report also retains its historical consumer line references after later library code additions move functions.

## Verification

- Expanded batch: 141 Goal/catalogue/library tests passed, covering every review, raw preview/API evidence, existing filters, canonical vocabulary, actual strength dose receipts, all query anchors and exclusions, stale/missing identity rejection and misleading-tag negative controls.
- Ruff and TypeScript checks passed. The previous batch also passed 1,609 generator regressions; its sole Windows MemoryError passed on retry of all seven tests in that module. Planner inputs remain unchanged in this expansion.
- Previous historical metadata compatibility run: all 14 passed. The frozen equipment-report check is rerun for this expansion; original reports are not refreshed.
- Existing frontend interaction tests cover Goal selection and preview evidence. Hosted CI runs full build and regression checks on the updated PR; no additional inventory or full audit report is generated.

## Remaining limitations

**744 Training entries remain without verified Goals.** A generic strength method without a verified dose does not establish maximal strength; gripping does not establish Grip Strength; aerobic demand alone does not establish aerobic development. Less-specific technical practice entries and candidates with insufficient purpose/dose evidence remain unresolved. There is no coverage quota, programming migration or efficacy-certification claim.
