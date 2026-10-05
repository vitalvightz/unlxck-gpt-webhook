# Rehab-bank rationalisation

## Executive summary

Current inputs contain **755 groups / 1601 drills**, **64 active profiles**, and **103 unique live MSK identities** (6.43% of the whole bank).

This report is generated read-only: the audit itself never rewrites bank content, review history, profile hashes or stage activation. It describes current selectable inventory; retired exact identities and their complete provenance are preserved separately in data/rehab_archive/exact_duplicates.json when consolidation has been applied. Each retained drill has exactly one primary bucket. Secondary flags overlap; duplicate clusters overlap and must not be summed as distinct drills.

Classification is evidence-backed inventory triage, not a clinical approval of dormant content. Name-based future-stage screening proposes a mechanical hypothesis only. Missing metadata remains missing; no dose, pain ceiling or checkpoint is invented.

| Primary bucket | Drills |
| --- | ---: |
| LIVE | 103 |
| ADVANCED_CANDIDATE | 57 |
| KEEP_DORMANT | 208 |
| REPAIR | 1149 |
| DUPLICATE_OR_MERGE | 0 |
| MISPLACED | 17 |
| DEPRECATE | 67 |

Reviewed: **162 / 1601 (10.12%)**; MSK-only reviewed percentage: **10.82%**. Dormant potentially useful: **88.32%** (ADVANCED_CANDIDATE + KEEP_DORMANT + REPAIR). Likely eventually removable: **4.18%** (DEPRECATE + exact duplicate surplus); MISPLACED means relocation review, not removal.

## Production footprint

| Live stage | Unique identities |
| --- | ---: |
| CALM | 64 |
| RESTORE | 39 |
| LOAD | 0 |
| DYNAMIC | 0 |
| RETURN | 0 |

Active profiles by stages: `{"calm": 26, "calm+restore": 38}`. Reviewed identities referenced by active profiles: **103**. Advanced live profiles: **0**.

Reachability means the profile/baseline can select a stage in principle; it is not clearance for every athlete. Severity, red flags, clinician restrictions, side, complete history and setbacks remain authoritative. CALM/RESTORE use the existing report ladder. Advanced availability requires a live target, a promotable clinical transition and captured required checkpoints.

### Surface inventory caveat

**104 wound-care identities** are outside the MSK review ledger and the 64-profile model. They are not counted as live MSK work. `fightcamp/rehab_protocols.py::_collect_surface_drills` and `_rehab_drills_for_phase` can still enumerate this inventory; main generation renders a single wound-care note. Therefore 'dormant from active profiles' does not mean unreachable by every legacy helper.

**Separate safety finding:** `heel_blister_sterile_drainage_if_tense` instructs needle drainage without limiting it to a clinician. NHS blister guidance says not to burst a blister yourself and describes sterile-needle drainage as GP treatment. It is a DEPRECATE candidate and must be addressed in a separate surface-content/consumer review; this PR does not change behavior.

## Breakdown

### Injury type

| Injury type | Drills |
| --- | ---: |
| abrasion | 24 |
| blister | 16 |
| contusion | 69 |
| cut | 24 |
| graze | 20 |
| hyperextension | 48 |
| impingement | 54 |
| instability | 72 |
| laceration | 20 |
| pain | 88 |
| soreness | 78 |
| sprain | 61 |
| stiffness | 72 |
| strain | 95 |
| swelling | 44 |
| tendonitis | 72 |
| tightness | 80 |
| unspecified | 664 |

### Canonical region

| Canonical region | Drills |
| --- | ---: |
| achilles | 27 |
| ankle | 49 |
| biceps | 65 |
| calf | 37 |
| chest | 30 |
| core | 46 |
| elbow | 63 |
| eye | 44 |
| face | 52 |
| fingers | 44 |
| foot | 38 |
| forearm | 61 |
| glute | 46 |
| groin | 49 |
| hamstring | 31 |
| hand | 84 |
| heel | 19 |
| hip | 36 |
| jaw | 44 |
| knee | 41 |
| lower back | 70 |
| neck | 65 |
| obliques | 54 |
| quads | 33 |
| shin | 41 |
| shoulder | 101 |
| toe | 37 |
| triceps | 53 |
| unspecified | 58 |
| upper back | 54 |
| wrist | 129 |

### Pathway family

| Pathway family | Drills |
| --- | ---: |
| contusion | 69 |
| hyperextension_or_joint_trauma | 48 |
| joint_irritation_or_impingement | 54 |
| ligament_sprain_or_instability | 133 |
| muscle_strain | 95 |
| nonspecific_msk_symptoms | 362 |
| surface_wound_care | 104 |
| tendon_rehab | 72 |
| unspecified_fallback | 664 |

### Review state

| Review state | Drills |
| --- | ---: |
| needs_review | 1335 |
| outside_msk_review_ledger | 104 |
| reviewed | 162 |

Aliases are resolved by the existing registry: bicep → biceps, hamstrings → hamstring, glutes → glute, lower_back → lower back, upper_back → upper back. The report retains the original group location/index; no bank vocabulary is rewritten.

## Mechanical metadata

### Family classification

| Identity | LIVE | ADVANCED_CANDIDATE | KEEP_DORMANT | REPAIR | DUPLICATE_OR_MERGE | MISPLACED | DEPRECATE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| contusion | 16 | 0 | 5 | 33 | 0 | 0 | 15 |
| hyperextension_or_joint_trauma | 6 | 0 | 2 | 40 | 0 | 0 | 0 |
| joint_irritation_or_impingement | 9 | 0 | 3 | 41 | 0 | 0 | 1 |
| ligament_sprain_or_instability | 21 | 32 | 5 | 70 | 0 | 0 | 5 |
| muscle_strain | 16 | 19 | 4 | 52 | 0 | 0 | 4 |
| nonspecific_msk_symptoms | 19 | 0 | 31 | 299 | 0 | 1 | 12 |
| surface_wound_care | 0 | 0 | 103 | 0 | 0 | 0 | 1 |
| tendon_rehab | 16 | 6 | 2 | 47 | 0 | 0 | 1 |
| unspecified_fallback | 0 | 0 | 53 | 567 | 0 | 16 | 28 |

### Region classification

| Identity | LIVE | ADVANCED_CANDIDATE | KEEP_DORMANT | REPAIR | DUPLICATE_OR_MERGE | MISPLACED | DEPRECATE |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| achilles | 2 | 1 | 0 | 24 | 0 | 0 | 0 |
| ankle | 7 | 4 | 3 | 35 | 0 | 0 | 0 |
| biceps | 5 | 5 | 1 | 53 | 0 | 0 | 1 |
| calf | 2 | 3 | 1 | 31 | 0 | 0 | 0 |
| chest | 2 | 2 | 2 | 23 | 0 | 0 | 1 |
| core | 0 | 0 | 0 | 41 | 0 | 4 | 1 |
| elbow | 11 | 3 | 11 | 37 | 0 | 0 | 1 |
| eye | 0 | 0 | 4 | 0 | 0 | 0 | 40 |
| face | 0 | 0 | 48 | 0 | 0 | 0 | 4 |
| fingers | 8 | 4 | 4 | 28 | 0 | 0 | 0 |
| foot | 0 | 0 | 6 | 32 | 0 | 0 | 0 |
| forearm | 3 | 1 | 11 | 45 | 0 | 0 | 1 |
| glute | 0 | 0 | 0 | 43 | 0 | 3 | 0 |
| groin | 2 | 1 | 2 | 44 | 0 | 0 | 0 |
| hamstring | 2 | 0 | 1 | 27 | 0 | 1 | 0 |
| hand | 8 | 4 | 12 | 56 | 0 | 2 | 2 |
| heel | 1 | 0 | 1 | 16 | 0 | 0 | 1 |
| hip | 3 | 0 | 4 | 29 | 0 | 0 | 0 |
| jaw | 0 | 0 | 42 | 0 | 0 | 0 | 2 |
| knee | 3 | 2 | 9 | 27 | 0 | 0 | 0 |
| lower back | 3 | 0 | 0 | 63 | 0 | 2 | 2 |
| neck | 4 | 0 | 9 | 51 | 0 | 0 | 1 |
| obliques | 0 | 0 | 0 | 53 | 0 | 1 | 0 |
| quads | 3 | 1 | 2 | 26 | 0 | 0 | 1 |
| shin | 1 | 0 | 12 | 26 | 0 | 0 | 2 |
| shoulder | 16 | 13 | 2 | 68 | 0 | 1 | 1 |
| toe | 3 | 2 | 2 | 30 | 0 | 0 | 0 |
| triceps | 3 | 4 | 5 | 41 | 0 | 0 | 0 |
| unspecified | 0 | 0 | 10 | 45 | 0 | 1 | 2 |
| upper back | 0 | 0 | 2 | 51 | 0 | 0 | 1 |
| wrist | 11 | 7 | 2 | 104 | 0 | 2 | 3 |

### rehab_stage

| Value | Drills |
| --- | ---: |
| calm | 64 |
| dynamic | 5 |
| load | 54 |
| missing | 1437 |
| restore | 41 |

### function

| Value | Drills |
| --- | ---: |
| activation | 155 |
| control | 186 |
| isometric_analgesia | 182 |
| missing | 525 |
| mobility | 234 |
| recovery_downregulation | 191 |
| tendon_loading | 128 |

### equipment

| Value | Drills |
| --- | ---: |
| bands+wall | 1 |
| barbell+landmine | 1 |
| cable_machine | 1 |
| cable_machine+fat_grip | 1 |
| chair | 1 |
| cloth+wall | 1 |
| dumbbell | 1 |
| dumbbell+table | 3 |
| dynamometer | 1 |
| foam_pad | 1 |
| foam_pad+stable_support | 2 |
| foam_roller | 1 |
| foam_roller+wall | 1 |
| kettlebell | 2 |
| massage_gun | 1 |
| mat | 1 |
| mini_band | 2 |
| missing | 1437 |
| none_required | 102 |
| plate | 1 |
| resistance_band | 16 |
| soft_ball | 1 |
| stable_support | 4 |
| table | 6 |
| table+tape | 1 |
| towel | 1 |
| towel+wall | 1 |
| wall | 9 |

### load

| Value | Drills |
| --- | ---: |
| low | 38 |
| minimal | 95 |
| missing | 1437 |
| moderate | 15 |
| unknown | 16 |

### impact

| Value | Drills |
| --- | ---: |
| missing | 1437 |
| none | 159 |
| unknown | 5 |

### velocity

| Value | Drills |
| --- | ---: |
| high | 2 |
| low | 159 |
| missing | 1437 |
| moderate | 3 |

### laterality_applicability

| Value | Drills |
| --- | ---: |
| bilateral_only | 1 |
| missing | 104 |
| not_applicable | 74 |
| side_specific | 89 |
| unknown | 1333 |

### contraction_type

| Value | Drills |
| --- | ---: |
| eccentric | 5 |
| isometric | 26 |
| missing | 104 |
| mixed | 67 |
| unknown | 1399 |

### sport_specificity

| Value | Drills |
| --- | ---: |
| combat_sport | 2 |
| general_rehab | 162 |
| missing | 104 |
| unknown | 1333 |

### contact_level

| Value | Drills |
| --- | ---: |
| missing | 104 |
| none | 164 |
| unknown | 1333 |

### target_regions

| Value | Drills |
| --- | ---: |
| achilles | 27 |
| ankle | 47 |
| bicep | 63 |
| bicep+biceps | 2 |
| calf | 37 |
| chest | 28 |
| core | 46 |
| elbow | 55 |
| eye | 40 |
| face | 44 |
| fingers | 40 |
| fingers+wrist | 1 |
| foot | 32 |
| forearm | 53 |
| glutes | 46 |
| groin | 49 |
| hamstring | 20 |
| hamstring+hamstrings | 2 |
| hamstrings | 9 |
| hand | 74 |
| heel | 17 |
| hip | 32 |
| jaw | 40 |
| knee | 33 |
| lower_back | 70 |
| missing | 104 |
| neck | 57 |
| obliques | 54 |
| quads | 33 |
| shin | 31 |
| shoulder | 99 |
| toe | 35 |
| triceps | 53 |
| unspecified | 48 |
| upper back | 32 |
| upper_back | 20 |
| wrist | 128 |

### target_tissues

| Value | Drills |
| --- | ---: |
| Achilles tendon | 3 |
| ankle joint region | 2 |
| ankle joint supporting soft tissues | 6 |
| ankle region soft tissues | 3 |
| biceps muscle | 6 |
| biceps muscle region | 1 |
| biceps tendons | 3 |
| chest region soft tissues | 2 |
| common wrist extensor tendon at elbow | 1 |
| elbow joint region | 3 |
| elbow joint supporting soft tissues | 4 |
| elbow region; symptom cause unspecified | 2 |
| elbow soft tissue region | 2 |
| elbow tendons | 2 |
| finger joint region | 1 |
| finger soft tissue region | 2 |
| finger tendons | 2 |
| fingers joint supporting soft tissues | 6 |
| fingers region; symptom cause unspecified | 1 |
| forearm extensor tendons | 1 |
| forearm flexor and extensor tendons | 2 |
| forearm muscle region | 1 |
| gastrocnemius and soleus muscles | 5 |
| hamstring muscles | 3 |
| hand flexor tendons | 2 |
| hand joint region | 1 |
| hand joint supporting soft tissues | 6 |
| hand region; symptom cause unspecified | 1 |
| hand soft tissue region | 2 |
| heel soft tissue region | 1 |
| hip adductor muscles | 3 |
| hip joint region | 2 |
| hip region; symptom cause unspecified | 1 |
| knee joint supporting soft tissues | 4 |
| knee region; symptom cause unspecified | 1 |
| lower back region; symptom cause unspecified | 3 |
| missing | 1437 |
| neck region; symptom cause unspecified | 4 |
| pectoral muscles | 2 |
| quadriceps muscle region | 1 |
| quadriceps muscles | 4 |
| rotator cuff+scapular stabilizers | 1 |
| shin soft tissue region | 1 |
| shoulder joint and rotator cuff region | 2 |
| shoulder joint region | 1 |
| shoulder joint supporting soft tissues | 12 |
| shoulder muscles | 6 |
| shoulder region; symptom cause unspecified | 3 |
| shoulder soft tissue region | 2 |
| shoulder tendons | 3 |
| toe joint region | 1 |
| toe joint supporting soft tissues | 4 |
| triceps muscle | 6 |
| triceps muscle region | 1 |
| wrist and finger extensors | 1 |
| wrist and forearm tendons | 2 |
| wrist flexor tendons | 1 |
| wrist joint region | 2 |
| wrist joint supporting soft tissues | 8 |
| wrist region; symptom cause unspecified | 3 |
| wrist soft tissue region | 2 |

Surface loading fields are intentionally absent. Empty equipment lists mean no equipment required; they are not missing. The JSON separates whole-bank missing counts, MSK-only missing counts and explicit unknowns. Unreviewed keyword functions/archetypes are not verified mechanics. Group phase availability is orthogonal to rehab_stage; the audit flags camp-phase demand changes inside instructions, not availability alone.

## Biggest debt areas

- **93 duplicate/near-duplicate/uncertain clusters**, involving **227 unique drills**; kinds: `{"intentionally_distinct": 44, "near_duplicate": 22, "uncertain": 27}`.
- **1410** drills contain camp-phase instructions; **1172** contain arrows or hidden progression signals.
- **117** have mechanism-language or naming flags; kinds: `{"clinically_unsafe_implication": 23, "harmless_naming_debt": 15, "none": 1484, "unsupported_mechanism_language": 79}`.
- **64** have general-training/performance signals. Only explicit indication-free tasks receive primary MISPLACED; a compound lift or mobility exercise is not automatically non-rehab.

### Hidden progression breakdowns

| injury_type | Flagged drills |
| --- | ---: |
| abrasion | 24 |
| blister | 16 |
| contusion | 40 |
| cut | 24 |
| graze | 20 |
| hyperextension | 36 |
| impingement | 41 |
| instability | 56 |
| laceration | 20 |
| pain | 74 |
| soreness | 16 |
| sprain | 20 |
| stiffness | 58 |
| strain | 56 |
| swelling | 16 |
| tendonitis | 45 |
| tightness | 74 |
| unspecified | 536 |

| canonical_region | Flagged drills |
| --- | ---: |
| achilles | 20 |
| ankle | 32 |
| biceps | 43 |
| calf | 26 |
| chest | 22 |
| core | 35 |
| elbow | 41 |
| eye | 40 |
| face | 46 |
| fingers | 28 |
| foot | 36 |
| forearm | 45 |
| glute | 34 |
| groin | 35 |
| hamstring | 24 |
| hand | 62 |
| heel | 16 |
| hip | 29 |
| jaw | 37 |
| knee | 32 |
| lower back | 54 |
| neck | 53 |
| obliques | 46 |
| quads | 22 |
| shin | 38 |
| shoulder | 45 |
| toe | 30 |
| triceps | 40 |
| unspecified | 28 |
| upper back | 48 |
| wrist | 85 |

| review_state | Flagged drills |
| --- | ---: |
| needs_review | 1068 |
| outside_msk_review_ledger | 104 |

| classification | Flagged drills |
| --- | ---: |
| DEPRECATE | 55 |
| KEEP_DORMANT | 190 |
| MISPLACED | 14 |
| REPAIR | 913 |

### Live instruction findings

- `ankle_sprain_gentle_movement`: bounded_self_paced_amount. Existing bounded self-paced wording must be distinguished from changing load/impact/contact; review separately, preserve its hash here.
- `ankle_sprain_supported_balance`: bounded_self_paced_amount. Existing bounded self-paced wording must be distinguished from changing load/impact/contact; review separately, preserve its hash here.

## Advanced inventory: good mechanics versus repair debt

| Candidate stage | All dormant screening candidates | Fixed reviewed candidates |
| --- | ---: | ---: |
| LOAD | 501 | 52 |
| DYNAMIC | 36 | 5 |
| RETURN | 3 | 0 |

Fixed reviewed candidates are mechanically defined movements; their exact regional prescriptions and readiness gates still need clinical evidence. Reviewed unknown load/impact stays unknown and requires individual demand assessment, not invented precision. Reviewed passive massage/rolling entries tagged LOAD are deliberately excluded from loading candidates. Other screened candidates often require substantial repair and are NOT ready for review/activation. Unspecified-type regional inventory is screened mechanically too, but its indication/ownership is unassigned; it is never silently converted into a diagnosis or borrowed across profile types. Each JSON row states content defects, review state, stage hypothesis, evidence/transition/input gaps and safety blocks.

### Active-profile candidate matrix

| Profile | Live stages | Fixed reviewed advanced IDs | Other exact-type candidates | Unassigned regional candidates |
| --- | --- | --- | ---: | ---: |
| achilles_tendonitis | calm, restore | achilles_tendonitis_eccentric_calf_drops_on_step | 1 | 13 |
| ankle_impingement | calm, restore | none | 0 | 16 |
| ankle_instability | calm, restore | ankle_instability_foam_pad_jump_stick, ankle_instability_lateral_hop_stick_drill | 0 | 16 |
| ankle_sprain | calm, restore | ankle_sprain_banded_ankle_circles, ankle_sprain_single_leg_balance_on_foam_pad | 0 | 16 |
| biceps_contusion | calm | none | 0 | 19 |
| biceps_strain | calm, restore | bicep_strain_band_resisted_eccentric_curl, bicep_strain_cable_curl_with_fat_grip, bicep_strain_isometric_bicep_curl_hold_mid_range, bicep_strain_supinated_isometric_elbow_hold | 0 | 19 |
| biceps_tendonitis | calm, restore | bicep_tendonitis_incline_db_curl_eccentric_focus | 1 | 19 |
| calf_strain | calm, restore | calf_strain_active_band_calf_pumps, calf_strain_isometric_tip_toe_wall_press, calf_strain_isometric_wall_push_hold | 0 | 18 |
| chest_strain | calm, restore | chest_strain_isometric_wall_push_chest_height, chest_strain_resistance_band_chest_fly | 0 | 2 |
| elbow_contusion | calm, restore | none | 0 | 10 |
| elbow_hyperextension | calm | none | 2 | 10 |
| elbow_impingement | calm, restore | none | 0 | 10 |
| elbow_pain | calm | none | 2 | 10 |
| elbow_sprain | calm, restore | elbow_sprain_overhead_band_triceps_extension, elbow_sprain_wrist_wall_slides_elbow_straight | 0 | 10 |
| elbow_stiffness | calm | none | 0 | 10 |
| elbow_tendonitis | calm, restore | elbow_tendonitis_eccentric_reverse_wrist_curls | 1 | 10 |
| fingers_contusion | calm, restore | none | 0 | 0 |
| fingers_hyperextension | calm | none | 1 | 0 |
| fingers_pain | calm | none | 1 | 0 |
| fingers_sprain | calm, restore | fingers_sprain_finger_band_expansions, fingers_sprain_finger_taps_on_hard_surface, fingers_sprain_mini_band_finger_spread_hold, fingers_sprain_tape_assisted_plyo_taps | 0 | 0 |
| fingers_tendonitis | calm, restore | none | 2 | 0 |
| forearm_contusion | calm | none | 1 | 5 |
| forearm_tendonitis | calm, restore | forearm_tendonitis_eccentric_wrist_extensions | 1 | 5 |
| groin_strain | calm, restore | groin_strain_standing_cable_adduction | 0 | 11 |
| hamstring_strain | calm, restore | none | 0 | 12 |
| hand_contusion | calm, restore | none | 0 | 6 |
| hand_hyperextension | calm | none | 2 | 6 |
| hand_pain | calm | none | 1 | 6 |
| hand_sprain | calm, restore | hand_sprain_band_resisted_finger_abduction, hand_sprain_finger_band_extensions, hand_sprain_hook_grip_plate_pinches, hand_sprain_palm_squeeze_with_soft_ball | 0 | 6 |
| hand_tendonitis | calm, restore | none | 4 | 6 |
| heel_contusion | calm | none | 0 | 2 |
| hip_impingement | calm, restore | none | 0 | 5 |
| hip_pain | calm | none | 0 | 5 |
| knee_instability | calm, restore | knee_instability_mini_band_lateral_walks, knee_instability_reactive_knee_bounces_foam_pad | 0 | 16 |
| knee_pain | calm | none | 0 | 16 |
| lower_back_pain | calm, restore | none | 2 | 8 |
| lower_back_stiffness | calm | none | 3 | 8 |
| neck_soreness | calm | none | 1 | 5 |
| neck_stiffness | calm, restore | none | 0 | 5 |
| neck_tightness | calm | none | 0 | 5 |
| quads_contusion | calm | none | 0 | 9 |
| quads_strain | calm, restore | quads_strain_isometric_wall_sit_mid_range | 0 | 9 |
| shin_contusion | calm | none | 0 | 8 |
| shoulder_contusion | calm, restore | none | 2 | 15 |
| shoulder_hyperextension | calm | none | 4 | 15 |
| shoulder_impingement | calm, restore | none | 0 | 15 |
| shoulder_instability | calm, restore | shoulder_instability_banded_overhead_carries, shoulder_instability_kb_bottom_up_carry, shoulder_instability_quadruped_weight_shifts_arm_reaches, shoulder_instability_wall_walks_isometric | 0 | 15 |
| shoulder_pain | calm | none | 3 | 15 |
| shoulder_soreness | calm | none | 1 | 15 |
| shoulder_sprain | calm, restore | shoulder_sprain_90_90_external_rotation_holds, shoulder_sprain_isometric_banded_row, shoulder_sprain_overhead_scapular_pull_aparts, shoulder_sprain_wall_supported_external_rotation | 0 | 15 |
| shoulder_strain | calm, restore | shoulder_strain_banded_y_raise, shoulder_strain_isometric_wall_press_90_abduction, shoulder_strain_landmine_shoulder_press, shoulder_strain_wall_slides_with_foam_roller | 0 | 15 |
| shoulder_tendonitis | calm, restore | shoulder_tendonitis_banded_scaption_holds | 3 | 15 |
| shoulder_tightness | calm | none | 0 | 15 |
| toe_hyperextension | calm | none | 1 | 5 |
| toe_sprain | calm, restore | toe_sprain_double_leg_pogo_jumps, toe_sprain_toe_off_isometric_presses | 0 | 5 |
| triceps_contusion | calm | none | 0 | 9 |
| triceps_strain | calm, restore | triceps_strain_isometric_wall_triceps_press, triceps_strain_kettlebell_crush_press_light, triceps_strain_overhead_band_triceps_extensions, triceps_strain_push_up_to_tabletop_flow | 0 | 9 |
| wrist_contusion | calm, restore | none | 0 | 17 |
| wrist_hyperextension | calm | none | 4 | 17 |
| wrist_impingement | calm | none | 1 | 17 |
| wrist_pain | calm | none | 2 | 17 |
| wrist_sprain | calm, restore | wrist_sprain_band_assisted_wrist_flexion_hold, wrist_sprain_band_stabilization_circles, wrist_sprain_isometric_wall_wrist_press, wrist_sprain_isometric_wrist_holds_various_angles, wrist_sprain_plank_to_palm_rockbacks, wrist_sprain_wrist_stability_drill_with_dynamometer | 0 | 17 |
| wrist_stiffness | calm, restore | none | 1 | 17 |
| wrist_tendonitis | calm, restore | wrist_tendonitis_eccentric_wrist_flexion_with_dumbbell | 2 | 17 |

Profiles with no screened viable advanced inventory: `fingers_contusion`.

Profiles with no exact-type candidate (regional unassigned inventory may exist): `ankle_impingement`, `biceps_contusion`, `elbow_contusion`, `elbow_impingement`, `elbow_stiffness`, `fingers_contusion`, `hamstring_strain`, `hand_contusion`, `heel_contusion`, `hip_impingement`, `hip_pain`, `knee_pain`, `neck_stiffness`, `neck_tightness`, `quads_contusion`, `shin_contusion`, `shoulder_impingement`, `shoulder_tightness`, `triceps_contusion`, `wrist_contusion`.

Profiles with no fixed reviewed advanced inventory: `ankle_impingement`, `biceps_contusion`, `elbow_contusion`, `elbow_hyperextension`, `elbow_impingement`, `elbow_pain`, `elbow_stiffness`, `fingers_contusion`, `fingers_hyperextension`, `fingers_pain`, `fingers_tendonitis`, `forearm_contusion`, `hamstring_strain`, `hand_contusion`, `hand_hyperextension`, `hand_pain`, `hand_tendonitis`, `heel_contusion`, `hip_impingement`, `hip_pain`, `knee_pain`, `lower_back_pain`, `lower_back_stiffness`, `neck_soreness`, `neck_stiffness`, `neck_tightness`, `quads_contusion`, `shin_contusion`, `shoulder_contusion`, `shoulder_hyperextension`, `shoulder_impingement`, `shoulder_pain`, `shoulder_soreness`, `shoulder_tightness`, `toe_hyperextension`, `triceps_contusion`, `wrist_contusion`, `wrist_hyperextension`, `wrist_impingement`, `wrist_pain`, `wrist_stiffness`.

Promotable advanced transitions: **0**. Captured functional checkpoints: `[]`. Which regional strength/function/tolerance tests are necessary remains a literature/clinical decision; the audit does not substitute whole-athlete readiness, elapsed time, session counts or a different input. This audit activates no stage.

## Deprecation candidates

These are candidates for a separate review, not deletion instructions. Every ID remains in the bank.

- `bicep_contusion_massage_gun_sweep_bicep_belly`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `chest_contusion_massage_gun_sweep_pec_major`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `core_contusion_lacrosse_ball_ab_wall_desensitization`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `elbow_contusion_massage_gun_pass_lateral_elbow`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `eye_contusion_gentle_orbital_massage_around_socket`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_contusion_tactile_reflex_training_hand_sways`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_instability_colored_cue_shadow_boxing`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_instability_head_eye_coordination_drills`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_instability_laser_pointer_target_tracing`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_instability_vertical_ball_toss_with_gaze_lock`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_pain_blink_tolerance_training`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_pain_laser_pointer_rapid_switch_left_right_center`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_pain_peripheral_light_tap_drill`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_pain_saccadic_eye_jumps_horizontal_vertical`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_soreness_cool_compress_post_contact`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_soreness_visual_meditation_gaze_anchor`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_stiffness_360_gaze_anchor_drill`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_stiffness_eye_tracking_figure_8_pattern`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_strain_fitlight_reflex_matrix`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_strain_multi_task_gaze_balance`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_strain_near_far_focal_shifts`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_strain_pencil_push_ups`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_tightness_eye_circles_clockwise_counter`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_tightness_palming_breath_reset`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_ball_drop_reaction_catch`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_ballistic_saccades_dot_to_dot`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_blink_rate_reminders_timer`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_brock_string_convergence`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_diplopia_double_vision_correction_drills`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_inhibitory_saccades_look_away_from_cue`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_king_devick_test_practice`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_light_board_tracking_e_g_fitlight`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_partner_flash_cue_coloured_gloves`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_peripheral_number_recognition_while_dribbling`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_photophobia_desensitization_controlled_led_exposure`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_pupillary_response_drills_penlight`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_reaction_ball_catch_unpredictable_bounce`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_reaction_ball_wall_ties_multi_color`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_smooth_pursuit_with_cognitive_load`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_snellen_chart_pursuits_horizontal_vertical`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_sticky_fixation_drills`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_stroop_test_with_peripheral_awareness`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_virtual_reality_depth_perception_drills`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `eye_unspecified_warm_compress_lid_massage`: Eye labels are not an MSK diagnosis; gaze/pressure work cannot be justified as automatic injury rehab from this label.
- `face_impingement_neuro_fascial_release_zygomatic_pull`: Unsupervised invasive, forceful, treatment-product or speculative mechanism identity; not a defensible automatic rehab movement.
- `face_stiffness_resistance_band_jaw_pull_facial_hold`: Unsupervised invasive, forceful, treatment-product or speculative mechanism identity; not a defensible automatic rehab movement.
- `face_unspecified_facial_cupping_cheekbone_drainage`: Unsupervised invasive, forceful, treatment-product or speculative mechanism identity; not a defensible automatic rehab movement.
- `face_unspecified_trigeminal_nerve_flossing_jaw_side_glides`: Unsupervised invasive, forceful, treatment-product or speculative mechanism identity; not a defensible automatic rehab movement.
- `forearm_unspecified_ulnar_nerve_tensioners_shamrock_pattern`: Neural tensioning requires a neurological indication and assessment not established by this bank label.
- `hand_unspecified_rotational_wrist_wrenching`: Unsupervised invasive, forceful, treatment-product or speculative mechanism identity; not a defensible automatic rehab movement.
- `hand_unspecified_ulnar_nerve_tensioners`: Neural tensioning requires a neurological indication and assessment not established by this bank label.
- `heel_blister_sterile_drainage_if_tense`: Unsupervised invasive, forceful, treatment-product or speculative mechanism identity; not a defensible automatic rehab movement.
- `jaw_contusion_cheek_tap_drill_fingertip_percussion`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `jaw_sprain_resisted_jaw_opening_with_band`: Unsupervised invasive, forceful, treatment-product or speculative mechanism identity; not a defensible automatic rehab movement.
- `lower_back_contusion_foam_roll_sweep_erector_zone`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `lower_back_contusion_percussion_gun_lumbar_focus`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `neck_stiffness_trap_bar_hang_neck_relaxation`: Unsupervised invasive, forceful, treatment-product or speculative mechanism identity; not a defensible automatic rehab movement.
- `quads_contusion_light_quad_percussion_massage_gun`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `shin_contusion_foam_roller_circles_mid_shin`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `shin_contusion_light_shin_percussion`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `shoulder_contusion_soft_tissue_roll_with_lacrosse_ball`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `unspecified_contusion_soft_tissue_flushing_foam_roller_or_ball`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `unspecified_tendonitis_slow_tempo_eccentrics_on_major_lifts`: No single reproducible movement identity or demand is specified; retain provenance while reviewing deprecation.
- `upper_back_contusion_lacrosse_ball_wall_roll_t_spine`: Direct massage/percussion of a bruise lacks injury timing/severity clearance; this identity is unsuitable for automatic use as written.
- `wrist_unspecified_cbd_topical_application_circular_massage`: Unsupervised invasive, forceful, treatment-product or speculative mechanism identity; not a defensible automatic rehab movement.
- `wrist_unspecified_timed_grip_endurance_various_objects`: No single reproducible movement identity or demand is specified; retain provenance while reviewing deprecation.
- `wrist_unspecified_ulnar_nerve_tensioners`: Neural tensioning requires a neurological indication and assessment not established by this bank label.

## Misplaced candidates

| ID | Likely destination |
| --- | --- |
| core_unspecified_farmer_s_carry_neutral_spine_focus | general strength/performance; no injury-specific indication currently established |
| core_unspecified_standing_cable_chop_low_to_high | general strength/performance; no injury-specific indication currently established |
| core_unspecified_suitcase_carry_kettlebell | general strength/performance; no injury-specific indication currently established |
| core_unspecified_weighted_plank_plate_on_back | general strength/performance; no injury-specific indication currently established |
| glutes_unspecified_romanian_deadlift_3s_eccentric | general strength/performance; no injury-specific indication currently established |
| glutes_unspecified_single_leg_rdl_with_overhead_reach | general strength/performance; no injury-specific indication currently established |
| glutes_unspecified_suitcase_carry_contralateral_load | general strength/performance; no injury-specific indication currently established |
| hamstring_unspecified_single_leg_romanian_deadlift_trx_assisted | general strength/performance; no injury-specific indication currently established |
| hand_unspecified_sledgehammer_levering | general strength/performance; no injury-specific indication currently established |
| hand_unspecified_taped_wrist_shadowboxing | sport skill/contact preparation; athlete clearance remains required |
| lower_back_unspecified_deadlift_pattern_with_dowel_hip_contact | general strength/performance; no injury-specific indication currently established |
| lower_back_unspecified_suitcase_carry_contralateral_loading | general strength/performance; no injury-specific indication currently established |
| obliques_unspecified_standing_cable_chop_eccentric_focus | general strength/performance; no injury-specific indication currently established |
| shoulder_unspecified_turkish_get_up_half_kneeling_only | general strength/performance; no injury-specific indication currently established |
| unspecified_soreness_recovery_circuit_airdyne_row_band_mobility | conditioning or recovery; split mixed circuits before relocation |
| wrist_unspecified_hammer_grip_rotations_sledgehammer | general strength/performance; no injury-specific indication currently established |
| wrist_unspecified_sledgehammer_tire_strikes_over_under | general strength/performance; no injury-specific indication currently established |

## Recommended cleanup order

**P0:** inspect live flags without hash changes here; bounded self-paced ankle wording is not a hidden LOAD gate. Preserve the surface/helper identity-and-content approval boundary from #2740: unsafe needle inventory is archival, not automatic athlete guidance. Any newly discovered critical runtime bug gets a separate PR.

**P1:** consolidate exact same-pair surplus IDs first, preserving review/source history and migrating any references explicitly. Review DEPRECATE items (eye-as-MSK, neural tensioners, invasive/speculative/forceful identities and percussion on bruises). Review MISPLACED fallback performance/conditioning tasks. Never merge cross-label clinical prescriptions merely because mechanics match.

**P2:** repair a small useful set of named movements: remove GPP/SPP/TAPER demand changes, select one execution/equipment/range, remove unsupported mechanism claims and then review truthful metadata. Keep uncertain near duplicates pending comparison.

**P3:** start regional advanced prescription/criteria review from fixed reviewed LOAD candidates. Achilles floor-level lowering, elbow/forearm supported wrist extension and wrist flexion are strong existing mechanical anchors; subtype ambiguity and condition-specific limits still need evidence and captured inputs.

**P4:** lower-value dormant inventory, generic fallback and specialist-indication content can wait; absence from current profiles is not evidence of obsolescence.

**Best next PR after rationalisation:** consolidate duplicated calf/knee identities and target a small tendon resistance set (Achilles and elbow/forearm/wrist). Verify region/subtype-specific prescription evidence and readiness criteria, define and capture exactly the functional inputs required, then selectively open LOAD only for profiles whose full gate is evaluable. If subtype/input ambiguity persists, ship repair/input capture while keeping LOAD closed. No blanket LOAD rollout.

## Evidence and method limits

- [sprains](https://www.nhs.uk/conditions/sprains-and-strains/): Protection and symptom-based movement; early massage/heat and urgent warning boundaries. Not an advanced protocol.
- [tendon](https://www.nhs.uk/conditions/tendonitis/): Regional tendon problems require assessed treatment; sudden severe pain may represent rupture. Does not approve any exact resistance variant.
- [swelling](https://www.nhs.uk/conditions/oedema/): Unexplained unilateral or severe swelling needs assessment; a swelling label does not establish a drainage mechanism.
- [eye](https://www.nhs.uk/conditions/eye-injuries/): Eye trauma with vision change, severe pain or other warning signs requires urgent care; generic MSK loading is not justified.
- [wound](https://www.nhs.uk/conditions/cuts-and-grazes/): Clean and cover small wounds; embedded objects, serious/deep wounds and infection require medical assessment.
- [blister](https://www.nhs.uk/conditions/blisters/): Do not burst a blister yourself; needle drainage is described as GP treatment, not athlete self-care.
- [joint](https://www.nhs.uk/symptoms/joint-pain/): Activity modification, assessment and warning boundaries for undiagnosed joint symptoms; not a diagnosis-specific loading protocol.

Sources were read directly for this audit. They support safety/classification boundaries, not every drill's effectiveness. Inventory evidence is the actual name/notes, current metadata, ledger review/source history and exact profile references, all retained per row. Keyword rules cannot determine diagnosis or semantic equivalence reliably; ambiguous clusters are marked uncertain/near-duplicate, and no unreviewed movement is approved.

## Rerun and verification

Run `python tools/audit_rehab_bank_rationalisation.py` to regenerate docs only, or add `--check` to compare committed output. `--output-dir` supports an isolated output directory. No network, external API or runtime dependency is added. Stable ID sorting and content hashes make repeated output byte-identical. Debt never makes the command fail; genuine integrity errors do.

The original baseline fixture freezes pre-consolidation input hashes, all original IDs and all profile hashes. Tests reconstruct the original bank and review ledger from retained inventory plus the exact-duplicate archive, without replacing that baseline. Tests verify complete classification, live review/reference provenance, exact source/content hashes, valid clusters, advanced dormancy, deterministic/non-mutating output, validator/vocabulary success and seed idempotence. Safety, Today, frozen completion, exposure, unknown-side and multi-injury tests verify that historical lookup preserves original identities while current selection excludes retired duplicates.
