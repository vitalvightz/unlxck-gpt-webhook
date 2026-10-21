# Rehab RESTORE expansion

Based on Main `a9f428c` (after #2983–#2985). Uses the existing bank publication
route (`fightcamp/rehab_publication.py`), the five-stage ladder and the existing
selector. No new architecture, stage, transition, threshold or approval record.
Software validation and cited leaflets are not clinician sign-off.

## Result

| Metric | Before | After |
| --- | ---: | ---: |
| Published unique exercise identities | 111 | 130 |
| Published physical identities (function other than recovery guidance) | 48 | 67 |
| Profiles with published CALM | 64 | 64 |
| Profiles with published RESTORE | 38 | 52 |
| Profiles with published LOAD | 4 | 4 |
| Profiles with published DYNAMIC / RETURN | 0 / 0 | 0 / 0 |

All 130 live identities are returned by the real selector for some reported
equipment setup (`approved_never_surfaced_ids` is empty in the
[reachability report](rehab-bank-reachability.md)). The brief's "47 physical
identities" counts one fewer than this repository's function-based count; the
same rule is used before and after.

## Published identities

Each dose is the explicit number, the lower bound of a range, or the "up to" figure in the cited
leaflet. Holds are written in the instructions; only static holds carry a
`duration_seconds` dose. Cadence is the existing product rule (one round per
scheduled rehab session, minimum gap one day); leaflets that advise several
rounds a day are not over-prescribed. Severity is low/moderate as for every
existing RESTORE option. Prop-specific options use priority 5 over an
equipment-free default (the existing groin/elbow/shoulder pattern), so each one
is selected for athletes who report that prop.

| Profile(s) | Identity → reviewed name | Props | Dose | Source |
| --- | --- | --- | --- | --- |
| knee_pain | `knee_pain_heel_slide_knee_bend` → Heel slide knee bend | – | 10 reps | [UHCW knee & leg injury](https://www.uhcw.nhs.uk/download/clientfiles/files/Patient%20Information%20Leaflets/Emergency%20Medicine/Emergency%20Department/Knee%20and%20leg%20injury%20-%20Care%20advice%20(1516).pdf), [HEY knee](https://www.hey.nhs.uk/patient-leaflet/soft-tissue-injury-knee/) |
| knee_pain | `knee_pain_seated_knee_straightening_hold` → Seated knee straightening hold | chair | 10 reps (3 s hold) | UHCW |
| knee_pain | `knee_pain_heel_lift_over_rolled_towel` → Heel lift over a rolled towel | towel | 10 reps (3 s hold) | UHCW, HEY knee |
| quads_contusion | `quads_pain_isometric_quad_flex_straight_leg` → Static quads for a bruised thigh | – | 10 × 3 s | UHCW, [AAOS contusion](https://www.orthoinfo.org/diseases--conditions/muscle-contusion-bruise/) |
| quads_contusion | `quads_unspecified_sliding_leg_extensions_towel_under_foot` → Heel slide knee bend on a towel | towel | 10 reps | UHCW, AAOS |
| neck_tightness, neck_soreness | `neck_soreness_seated_forward_neck_bend` → Seated forward neck bend | – | up to 10 (5 s hold) | [NHS Fife neck pain](https://www.nhsfife.org/media/2sfgwql9/neck_pain_v7.pdf) |
| neck_tightness, neck_soreness | `neck_tightness_seated_neck_side_tilt` → Seated neck side tilt | chair | up to 10 each side (5 s hold) | NHS Fife |
| shoulder_pain, _tightness, _soreness | `shoulder_unspecified_lying_assisted_arm_raise` → Lying assisted arm raise | – | 5 reps | [Leeds shoulder](https://www.leedsth.nhs.uk/patients/resources/early-advice-and-exercises-for-soft-tissue-injuries-of-the-shoulder/), [Royal Berkshire](https://royalberkshire.nhs.uk/media/5scpbnrh/shoulder-active-and-assisted-exercises_oct22.pdf) |
| shoulder_pain, _tightness, _soreness | `shoulder_swelling_pendulum_circles` → Supported shoulder pendulum swing | stable_support | 60 s | Leeds, Royal Berkshire |
| elbow_pain, elbow_stiffness | `elbow_stiffness_elbow_bend_and_straighten` → Elbow bend and straighten | – | 10 reps | [ESHT elbow soft tissue (Nov 2025)](https://www.esht.nhs.uk/wp-content/uploads/2026/01/2029.pdf) |
| biceps_contusion | `biceps_contusion_comfortable_elbow_bend` → Comfortable elbow bend for a bruised front of the arm | – | 10 reps | ESHT, AAOS |
| triceps_contusion | `triceps_contusion_comfortable_elbow_bend` → Comfortable elbow bend for a bruised back of the arm | – | 10 reps | ESHT, AAOS |
| forearm_contusion | `forearm_contusion_elbow_at_side_forearm_turn` → Elbow-at-side forearm turn | – | 5 reps (5 s holds) | [CUH active wrist](https://www.cuh.nhs.uk/patient-information/hand-therapy-active-wrist-exercises/), ESHT, AAOS |
| forearm_contusion | `forearm_contusion_supported_wrist_bend` → Supported wrist bend forward and back | table | 5 reps (5 s holds) | CUH, AAOS |
| wrist_pain | `wrist_pain_forearm_supination_pronation_paused` → Elbow-at-side forearm turn with pause | – | 5 reps (5 s holds) | CUH |
| wrist_pain | `wrist_pain_side_to_side_wrist_bend` → Side-to-side wrist bend on a table | table | 5 reps (5 s holds) | CUH |
| wrist_stiffness, wrist_sprain | `wrist_unspecified_finger_extension_with_wrist_flexion` → Active wrist tenodesis | – | 5 reps (5 s holds) | CUH |
| hip_pain | `hip_pain_double_leg_bridge_hold` → Double-leg bridge with 5-second hold | – | 5 reps | [WMAS hip pain (Feb 2026)](https://wellbeing.wmas.nhs.uk/wp-content/uploads/2026/02/ADV121-Hip-Pain.pdf) |
| hip_pain | `hip_pain_supported_standing_hip_abduction` → Supported standing hip abduction | stable_support | 5 reps (5 s hold) | WMAS |

### Exercise identity

An exercise ID also identifies demonstration media (`exercise_key` is derived
from it) and recorded work. Where the reviewed movement differs from what the
original ID names (a different movement, position or equipment), it is published
under a **new ID**, and the original bank entry and ledger record stay exactly as
on Main, unpublished. 14 movements use new IDs. Five IDs that still name the
exact movement were reviewed in place, with the previous name and notes in
`source_history`: `quads_pain_isometric_quad_flex_straight_leg`,
`quads_unspecified_sliding_leg_extensions_towel_under_foot`,
`shoulder_swelling_pendulum_circles`, `wrist_pain_forearm_supination_pronation_paused`
and `wrist_unspecified_finger_extension_with_wrist_flexion`. None of the 19
original IDs had a seeded media row or alias. None was ever a published
prescription, so no rehab exposure references them.

RESTORE was added to `live_stages` for the 14 profiles above that were CALM only
(profile version +1, content hash recomputed). CALM→RESTORE remains the existing
report ladder: a follow-up that is not worse. Banded, weighted
and circling variants are not published. Stop rules add region-specific red flags (for example, a tense thigh
or arm after a bruise).

Wrist sprain/stiffness already had a table-based default. The tenodesis is only
selected when no table is reported, replacing the CALM fallback. Every previous
selection for every equipment setup is otherwise unchanged
(`tests/test_rehab_restore_expansion.py`).

Plan generation previously lost the drill ID for biceps profiles (`bicep` bank
spelling vs `biceps` region). `reviewed_rehab_drill_id_for_line` now
canonicalises both, so generation and Today agree.

## Families

| Family | New useful content |
| --- | --- |
| Contusions | Quads, biceps, triceps and forearm open RESTORE. Heel/shin stay CALM: depth and bony impact not established. |
| Nonspecific symptoms | Knee, hip, shoulder (pain, tightness, soreness), elbow (pain, stiffness), wrist pain and neck (tightness, soreness) open RESTORE. |
| Sprains | Wrist sprain gains an equipment-free alternative. |
| Muscle strains, tendons, impingement, hyperextension | None. See below. |

## Still blocked

**Reviewed candidates (58): none published.**

- **49 LOAD candidates in profiles without a live LOAD stage.** Publishing would
  need a profile-specific sourced `restore->load` clinical criterion and
  permission reader, like the four existing LOAD profiles. Every candidate also
  lacks a sourced dose, and 12 have clinician-selected or unknown resistance.

| biceps_strain | `bicep_strain_band_resisted_eccentric_curl`, `bicep_strain_cable_curl_with_fat_grip`, `bicep_strain_isometric_bicep_curl_hold_mid_range`, `bicep_strain_supinated_isometric_elbow_hold` |
| biceps_tendonitis | `bicep_tendonitis_incline_db_curl_eccentric_focus` |
| calf_strain | `calf_strain_active_band_calf_pumps`, `calf_strain_isometric_tip_toe_wall_press`, `calf_strain_isometric_wall_push_hold` |
| chest_strain | `chest_strain_isometric_wall_push_chest_height`, `chest_strain_resistance_band_chest_fly` |
| elbow_sprain | `elbow_sprain_overhead_band_triceps_extension`, `elbow_sprain_wrist_wall_slides_elbow_straight` |
| fingers_sprain | `fingers_sprain_finger_band_expansions`, `fingers_sprain_mini_band_finger_spread_hold` |
| forearm_tendonitis | `forearm_tendonitis_eccentric_wrist_extensions` |
| groin_strain | `groin_strain_standing_cable_adduction` |
| hamstring_strain | `hamstrings_strain_massage_gun_biceps_femoris_sweep` |
| hand_sprain | `hand_sprain_band_resisted_finger_abduction`, `hand_sprain_finger_band_extensions`, `hand_sprain_hook_grip_plate_pinches`, `hand_sprain_palm_squeeze_with_soft_ball` |
| knee_instability | `knee_instability_mini_band_lateral_walks`, `knee_instability_reactive_knee_bounces_foam_pad` |
| quads_strain | `quads_strain_foam_roller_quad_sweep`, `quads_strain_isometric_wall_sit_mid_range` |
| shoulder_instability | `shoulder_instability_banded_overhead_carries`, `shoulder_instability_kb_bottom_up_carry`, `shoulder_instability_quadruped_weight_shifts_arm_reaches`, `shoulder_instability_wall_walks_isometric` |
| shoulder_sprain | `shoulder_sprain_90_90_external_rotation_holds`, `shoulder_sprain_isometric_banded_row`, `shoulder_sprain_overhead_scapular_pull_aparts`, `shoulder_sprain_wall_supported_external_rotation` |
| shoulder_strain | `shoulder_strain_banded_y_raise`, `shoulder_strain_isometric_wall_press_90_abduction`, `shoulder_strain_landmine_shoulder_press`, `shoulder_strain_wall_slides_with_foam_roller` |
| toe_sprain | `toe_sprain_toe_off_isometric_presses` |
| triceps_strain | `triceps_strain_isometric_wall_triceps_press`, `triceps_strain_kettlebell_crush_press_light`, `triceps_strain_overhead_band_triceps_extensions`, `triceps_strain_push_up_to_tabletop_flow` |
| wrist_sprain | `wrist_sprain_band_assisted_wrist_flexion_hold`, `wrist_sprain_band_stabilization_circles`, `wrist_sprain_isometric_wall_wrist_press`, `wrist_sprain_isometric_wrist_holds_various_angles`, `wrist_sprain_plank_to_palm_rockbacks`, `wrist_sprain_wrist_stability_drill_with_dynamometer` |
| wrist_tendonitis | `wrist_tendonitis_eccentric_wrist_flexion_with_dumbbell` |

- **4 LOAD candidates in LOAD-live profiles.** Each existing entry criterion
  covers only its starter (seated heel raise, wall push-up, hand-weight wrist
  extension):
  - `ankle_sprain_banded_ankle_circles` and
    `shoulder_tendonitis_banded_scaption_holds`: `resistance` accepts only
    bodyweight or explicit kg, and intake reports `bands`, not `resistance_band`.
  - `ankle_sprain_single_leg_balance_on_foam_pad`: `foam_pad` is not a
    reportable prop.
  - `elbow_tendonitis_eccentric_reverse_wrist_curls`: clinician-selected
    dumbbell with no kg, and intake reports `dumbbells`, not `dumbbell`.
- **5 DYNAMIC candidates.** `ankle_instability_foam_pad_jump_stick`,
  `ankle_instability_lateral_hop_stick_drill`,
  `fingers_sprain_finger_taps_on_hard_surface`,
  `fingers_sprain_tape_assisted_plyo_taps` and
  `toe_sprain_double_leg_pogo_jumps` have no `load->dynamic` transition, unknown
  impact and no reviewed entry criteria. A Better report is not readiness for
  impact.

**Other gaps found during this work.**

- `calf_unspecified_towel_stretch_with_isometric_hold` (HEY calf, 10 × 5 s) was
  withdrawn. The selector's laterality ranking would let it displace the
  existing calf raise for athletes with a chair, and priority cannot place it
  between the calf raise and the CALM fallback.
- `knee_pain_terminal_knee_extensions_tkes` is the keeper of an archived exact
  duplicate. Editing it would break archive integrity.
- Lower-back stiffness: the only dosed leaflet found (WWL Level 1) expired in
  January 2024.
- Hand/finger pain: no accessible leaflet with a dose was found.
- Hamstring: no NHS leaflet gives a dose.
- Hyperextension (6 profiles) and wrist impingement stay CALM. Structural
  stability, splinting and immobilisation status are not captured.

## Progression dependencies

- LOAD remains live only for Achilles, lateral elbow, ankle sprain and shoulder
  tendinopathy. Every other profile needs a sourced, profile-specific clinical
  criterion and a captured input before LOAD can open.
- DYNAMIC and RETURN need reviewed entry criteria and pass/fail conditions. No
  impact or speed readiness input is captured.
- Reduced-training (pull back) days: dosed prescriptions without a reviewed
  reduced dose give no rehab, and activation work is held as loading. These
  existing rules apply unchanged to the new options.
- GPP/SPP/TAPER cannot change stage, selection or dose (tested).
