# Training Goal coverage implementation

Base: Main `371cbeed29cc20eed693f4b8abdbe5540c1cc030`.

Original verified Goal coverage: **222/1,010 (22.0%)**. Added **28 assignments on 28 previously unclassified Training entries**: 24 Coordination, four Balance. Updated coverage: **250/1,010 (24.8%)**. Existing assignments corrected: **0**.

The existing discovery-only `shared/training-metadata.json` projection holds the reviews. Every assignment binds the original catalogue ID to its unchanged row SHA256 and the original missing-Goal issue in PR #2822. The preview retains exact `why`, `cue`, `qualities`, `duration_min`, `rpe`, `support_only` and `meaningful_stress` evidence. These entries prescribe eight minutes at RPE 4, explicitly as controlled support practice.

## Exact records and intended adaptations

| Original catalogue ID | Goal | Original stated purpose (`why`) |
|---|---|---|
| `coordination/grappling.json:grapple.hipheist_base` | Coordination | Coordinate opposite hand-foot support through a common scramble transition. |
| `coordination/grappling.json:grapple.pass_recover_base` | Coordination | Build smooth transitions between passing movement and a stable base. |
| `coordination/grappling.json:grapple.shrimp_frame_recover` | Coordination | Coordinate hip escape with frame recovery instead of treating them as separate actions. |
| `coordination/kicks.json:kick.cross_leadkick_switch` | Coordination | Improve upper-to-lower sequencing when the strike changes sides. |
| `coordination/kicks.json:kick.jab_lowkick_reset` | Coordination | Link hand entry, lower-body rotation and stance recovery. |
| `coordination/kicks.json:kick.kick_and_stick` | Balance | Teach every kick to finish in a stable stance rather than a loose landing. |
| `coordination/kicks.json:kick.knee_step_recover` | Coordination | Coordinate the knee action with a stable return step. |
| `coordination/kicks.json:kick.longguard_teep_reset` | Coordination | Coordinate upper-body frame position with a long-range lower-body action. |
| `coordination/kicks.json:kick.punch_kick_pivot_chain` | Coordination | Coordinate a mixed striking chain that finishes in a new lane. |
| `coordination/kicks.json:kick.rearkick_punch_exit` | Coordination | Turn kick recovery into a usable punching and exit position. |
| `coordination/kicks.json:kick.switchkick_stance_recovery` | Balance | Make the switch step and kick return to an organised stance. |
| `coordination/kicks.json:kick.teep_recover_jab` | Coordination | Coordinate long-range kicking with immediate hand readiness. |
| `coordination/mma_transitions.json:mma.jab_doubleleg_pattern` | Coordination | Link a simple striking entry to wrestling footwork. |
| `coordination/mma_transitions.json:mma.kick_levelchange_reset` | Coordination | Train the athlete to recover from a kick into wrestling-ready posture. |
| `coordination/mma_transitions.json:mma.strike_levelchange` | Coordination | Connect striking posture to a clean level change without a pause or collapse. |
| `coordination/striking.json:strike.check_hook_exit` | Coordination | Coordinate the scoring hook with the exit rather than spinning away from stance. |
| `coordination/striking.json:strike.corner_exit_sequence` | Coordination | Coordinate defence, turn and exit when space is restricted. |
| `coordination/striking.json:strike.cutoff_step_combo` | Coordination | Coordinate ring cutting with a short scoring sequence. |
| `coordination/striking.json:strike.double_jab_exit_angle` | Coordination | Link forward scoring actions to a balanced angle exit. |
| `coordination/striking.json:strike.jab_step_sync` | Coordination | Synchronise the lead hand with the lead step so range is gained without reaching. |
| `coordination/striking.json:strike.pivot_reset_shadow` | Balance | Make the pivot end in a usable fighting stance instead of a loose spin. |
| `coordination/striking.json:strike.pocket_roll_return` | Coordination | Improve close-range timing without turning the drill into a high-output exchange. |
| `coordination/striking.json:strike.pressure_step_slip_hook` | Coordination | Link forward pressure, head movement and a compact return. |
| `coordination/striking.json:strike.rear_hand_weight_transfer` | Coordination | Coordinate rear-side force transfer without falling over the front leg. |
| `coordination/striking.json:strike.rope_line_counter` | Coordination | Link head movement to stance recovery and a controlled counter. |
| `coordination/striking.json:strike.three_beat_combo_rhythm` | Coordination | Develop clean sequencing across a short three-action combination. |
| `coordination/universal.json:universal.cross_body_pattern_reset` | Coordination | Improve opposite-side coordination used in striking, hand fighting and level changes. |
| `coordination/universal.json:universal.single_leg_posture_reset` | Balance | Improve balance recovery after kicks, checks, shots and scrambles. |

The per-entry rationale, execution cue and source hash are in the shared review records; they are not derived from names, equipment, mechanical tags, search synonyms or energy-system labels.

## Generator and historical evidence

Generator behaviour is unchanged. Strength scores goal/weakness matches against bank tags; conditioning and coordination consume their original banks, quality, dose and phase declarations. None imports the discovery projection. No bank, scoring map, eligibility, ranking, programmed dose, adaptive selection, injury rule, rehab rule, contact permission, permanent ID, exercise key or media association changes.

The added Goal labels are excluded from lexical aliases and the search word bag. Existing query membership/order and relevance scores remain unchanged. Equipment, sport, type and body-focus filters retain their independent AND semantics. Original phase declarations remain untouched (the library has no phase filter).

PR #2822-#2827 reports/baselines are retained. The historical replay removes this later Goal-review section from its frozen projection and content revision; it still reproduces 222 verified entries and the exact original browser fixture. No catalogue identity rebinding is necessary because no source row changes.

## Verification

- 37 new Goal tests passed: every reviewed record filters correctly, raw preview/API evidence survives, existing filters and lexical inputs are unchanged, stale hashes/missing identities fail closed, and misleading names/mechanisms/energy labels do not grant Goals.
- 74 Goal/projection tests passed (including those 37); two expensive original fixed-seed report tests were excluded from this focused run.
- 88 catalogue/library tests passed, including all query anchors, exclusions, identity and API controls.
- Generator regression selection: 1,609 passed; one Windows MemoryError. Retrying its entire module passed all seven tests. This selection covers strength, conditioning, Goal/weakness matching, priority, injury, phase, restrictions, coordination, stable identity and media.
- Four frontend interaction tests passed, including selecting the Goal filter and opening its evidence preview. TypeScript passed on retry; full ESLint completed with zero errors and 47 existing warnings. Ruff, Python import/compile checks and API type generation checks passed.
- Bank validator completed successfully in audit mode; its existing 847 errors/273 warnings are unrelated bank findings, not new source edits.
- Full local Next build is blocked by Turbopack rejecting the shared dependency junction outside its filesystem root. Hosted CI uses a normal npm install; build/full-suite CI is requested by this PR.

## Remaining limitations

Coverage remains intentionally incomplete: **760 Training entries** have no verified Goal. This batch excludes the less-specific Open-Stance Lead-Foot Battle, Stand-Up-to-Guard Reset and Tempo Footwork Switch; technical practice alone does not establish the reviewed Coordination/Balance purpose. Other strength/conditioning candidates need sufficiently specific source guidance and dose review. This PR makes no programming migration or efficacy-certification claim.
