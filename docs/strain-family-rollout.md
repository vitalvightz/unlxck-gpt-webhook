# Muscle strain production coverage rollout

Based on Main `b2a9b14c` (includes #2709 family/profile architecture and #2712 vocabulary guardrail).
The complete pre-edit inventory is in [strain-family-pre-rollout-audit.json](strain-family-pre-rollout-audit.json).
Re-run `python tools/audit_strain_family.py` to inspect the current bank; do not overwrite the pre-edit snapshot.

## Whole-family audit before edits

25 canonical regions; 92 drills across 45 strain groups. All 92 ledger records initially
said `needs_review`, including the two already sourced, live chest routines. This is a
metadata-ledger provenance gap, not proof that chest lacked clinical prescriptions.
Chest was the only live strain profile. Ankle sprain belongs to another family.

Canonical labels use the existing location registry: hamstrings -> hamstring,
bicep -> biceps, glutes -> glute, lower_back -> lower back. No taxonomy was added.

| Canonical region | Drills before | Metadata ledger before | Live profile before | Production disposition |
| --- | ---: | --- | --- | --- |
| biceps | 4 | 4 needs_review | none | Defer: available resistance drills lack sufficient acute muscle-strain-specific evidence; tendon/surgical sources are not substitutes |
| calf | 8 | 8 needs_review | none | Activate fixed double-leg raise baseline |
| chest | 4 | 4 needs_review | chest_strain | Keep existing sourced routines; reconcile ledger |
| core | 2 | 2 needs_review | none | Defer: no reviewed staged strain-specific set |
| elbow | 2 | 2 needs_review | none | Defer: no reviewed staged strain-specific set |
| eye | 4 | 4 needs_review | none | Defer: specialist or nonspecific content does not establish a regional muscle-strain pathway |
| fingers | 4 | 4 needs_review | none | Defer: no reviewed staged strain-specific set |
| foot | 2 | 2 needs_review | none | Defer: no reviewed staged strain-specific set |
| forearm | 2 | 2 needs_review | none | Defer: no reviewed staged strain-specific set |
| glute | 4 | 4 needs_review | none | Defer: no reviewed staged strain-specific set |
| groin | 2 | 2 needs_review | none | Activate fixed side-lying adduction baseline |
| hamstring | 2 | 2 needs_review | none | Activate fixed bridge baseline |
| hand | 4 | 4 needs_review | none | Defer: no reviewed staged strain-specific set |
| jaw | 2 | 2 needs_review | none | Defer: specialist or nonspecific content does not establish a regional muscle-strain pathway |
| knee | 8 | 8 needs_review | none | Defer: no reviewed staged strain-specific set |
| lower back | 4 | 4 needs_review | none | Defer: no reviewed staged strain-specific set |
| neck | 4 | 4 needs_review | none | Defer: no reviewed staged strain-specific set |
| obliques | 6 | 6 needs_review | none | Defer: no reviewed staged strain-specific set |
| quads | 2 | 2 needs_review | none | Activate supported knee movement from regional unspecified pool |
| shoulder | 4 | 4 needs_review | none | Defer: available resistance drills lack sufficient acute muscle-strain-specific evidence; tendon/surgical sources are not substitutes |
| toe | 2 | 2 needs_review | none | Defer: no reviewed staged strain-specific set |
| triceps | 4 | 4 needs_review | none | Defer: available resistance drills lack sufficient acute muscle-strain-specific evidence; tendon/surgical sources are not substitutes |
| unspecified | 2 | 2 needs_review | none | Defer: specialist or nonspecific content does not establish a regional muscle-strain pathway |
| upper back | 4 | 4 needs_review | none | Defer: no reviewed staged strain-specific set |
| wrist | 6 | 6 needs_review | none | Defer: no reviewed staged strain-specific set |

### Duplicates and demand flags

Calf has four exact duplicate pairs; knee has four exact duplicate pairs. The JSON
snapshot names every identity in each pair. Near duplicates: glute bridge iso holds /
glute bridge with isometric hold; lower-back glute bridge walkout / walkouts;
calf wall push / tip-toe wall press; oblique seated / wall medicine-ball tosses.
Cross-region template similarities also include wrist curls in forearm/wrist, elbow-flexion holds in biceps/elbow, finger extension in hand/fingers, and wall presses in chest/shoulder/triceps. These are review candidates, not assertions of interchangeable clinical demand; canonical region boundaries are retained.

The existing detector flagged 9 strain records for VARIABLE_DEMAND_PROGRESSION and
SPEED_PROGRESSION_IN_NOTES, and none for POSSIBLE_DRILL_SPLIT. The snapshot records
the exact flags. Its separate mixed_camp_demand field records arrows even where the
heuristic misses a progression; absence of a flag does not mean fixed or safe demand.
Selected parent movements retain their original identities, notes, source hashes,
review states and flags. No duplicate is prescribed or approved merely for existing.

## Activated profiles and reviewed prescriptions

Four new profiles use muscle_strain. All explicitly own region, strain type,
reviewed prescriptions, restrictions, evidence and live stages. Contact limit is
none; their anatomical regions and existing restriction aliases are blocked from conflicting training. Quadriceps includes quads, quad and knee from the location registry. No new bundle
is needed for a single baseline movement. The existing ankle bundle is preserved.

| Profile | CALM identity | RESTORE identity | Movement lineage | Live stages |
| --- | --- | --- | --- | --- |
| hamstring_strain | hamstring_strain_recovery_support | hamstring_strain_reviewed_restore | hamstrings_strain_isometric_hamstring_bridge | CALM, RESTORE |
| calf_strain | calf_strain_recovery_support | calf_strain_reviewed_restore | calf_strain_double_leg_calf_raises | CALM, RESTORE |
| groin_strain | groin_strain_recovery_support | groin_strain_reviewed_restore | groin_strain_side_lying_hip_adduction | CALM, RESTORE |
| quads_strain | quads_strain_recovery_support | quads_strain_reviewed_restore | quads_unspecified_sliding_leg_extensions_towel_under_foot | CALM, RESTORE |

Chest_strain keeps chest_strain_recovery_support and chest_strain_comfortable_movement,
CALM/RESTORE and its original bank and policy hashes. Only those two existing ledger
records are marked reviewed with the classifications already supported by their sources.

There are ten genuinely reviewed ledger records: eight new fixed variants plus those
two chest records. None of the variable-demand parent records is marked reviewed.
The four new recovery-support routines fill the missing protective stage; the four
RESTORE variants constrain existing bank movements rather than inventing regions.
Quadriceps reuses quads_unspecified_sliding_leg_extensions_towel_under_foot because
the strain group itself only offers wall sits and foam rolling. Regional unspecified
pools are already permitted by the existing architecture.

The fixed variants state stage, function, equipment, impact, load, velocity, target
regions/tissues, laterality, contraction, general-rehab specificity and no contact.
Bridge and calf raise are conservatively classified moderate bodyweight demand,
not low simply because they are baseline work. Their double-leg performance is
region-wide (not_applicable), not a unilateral strength test. Adduction and knee
movement need an identified side; unknown-side RESTORE for these stays unsupported.
CALM retains unknown contraction: protective guidance is not a contraction exercise.

All prescriptions are self-paced with no fabricated numerical dose, pain ceiling,
clinical recovery threshold or return-to-sport criterion. Low/moderate eligibility
retains the product safety ceiling; it is not a diagnosis of clinical injury grade.
Default scheduled_sessions / minimum_gap_days=1 is product allocation cadence, not
an evidence claim about a clinical exercise frequency. Instructions retain source
prerequisites such as pain-free movement. A RESTORE report alone is not clearance
to ignore those prerequisites.

## Evidence reviewed and limits

- **All profiles: protective stage:** [https://www.nhs.uk/conditions/sprains-and-strains/](https://www.nhs.uk/conditions/sprains-and-strains/). General acute strain protection, comfortable movement, early massage/heat avoidance and escalation advice. No regional loading or sport clearance inferred.
- **Hamstring:** [https://pmc.ncbi.nlm.nih.gov/articles/PMC2867336/](https://pmc.ncbi.nlm.nih.gov/articles/PMC2867336/). Heiderscheit et al., JOSPT 2010. Phase I includes a supine bent-knee bridge and avoids excessive lengthening. A fixed double-leg bridge is the baseline interpretation; the published example dose is intentionally not generalized.
- **Calf:** [https://www.hey.nhs.uk/patient-leaflet/soft-tissue-injury-calf-strain/](https://www.hey.nhs.uk/patient-leaflet/soft-tissue-injury-calf-strain/). Hull University Teaching Hospitals leaflet, updated June 2025. Supported double-leg heel raising follows settled pain, no crutch need and pain-free toe standing. Keep level ground and both feet; do not import the single-leg progression.
- **Groin/adductor:** [https://pmc.ncbi.nlm.nih.gov/articles/PMC10569248/](https://pmc.ncbi.nlm.nih.gov/articles/PMC10569248/). Thorborg, Journal of Athletic Training 2023. Side-lying limb-weight exercises and slow initial contractions support a constrained unresisted variant. Symptom/irritability monitoring remains required; no Copenhagen, cable or fatigue progression is imported.
- **Quadriceps:** [https://pmc.ncbi.nlm.nih.gov/articles/PMC2941577/](https://pmc.ncbi.nlm.nih.gov/articles/PMC2941577/). Kary, Current Reviews in Musculoskeletal Medicine 2010. Active rehabilitation includes range of motion as recovery allows. Supported towel sliding is the implementation interpretation of active pain-free knee movement, not a named protocol tested in that paper. The acute 120-degree flexion instruction in the paper is for contusions and is not imported into this strain profile.

Biceps and triceps search results largely concerned tendinopathy, distal repairs or
post-dislocation exercise, so they do not justify acute muscle-strain prescriptions.
Shoulder bank content genuinely names deltoid strain, but no sufficiently specific
staged protocol was established here. Quadriceps wall sits are deferred rather than
using generic isometric evidence to approve their unspecified effort/angle/instability.

## Advanced stages remain closed

| Profile | What prevents LOAD | What prevents DYNAMIC / RETURN |
| --- | --- | --- |
| hamstring_strain | No reviewed LOAD content; published walking/jogging/submaximal strength checks are not captured by the product | No reviewed advanced drills, evaluable strength/speed criteria or sport checks |
| calf_strain | No reviewed LOAD content or evaluable source-backed functional transition | No evaluated strength/range/brisk-walking or graded sport evidence |
| groin_strain | No reviewed LOAD content; irritability, strength and clinical readiness measurements are not captured | No reviewed sport/strength-test criteria evaluable by this engine |
| quads_strain | No reviewed LOAD content; pain-free strength/range readiness cannot be evaluated | No reviewed advanced content, strength comparison or return-to-sport checks |
| chest_strain | Existing missing clinical criteria and reviewed LOAD content | Existing missing advanced content and captured clinical checks |

The family safety baseline and progression engine remain unchanged. The existing centralized urgent phrase vocabulary also gains major tear, major muscle tear, complete tear and full thickness tear: safety tests found that a stored strain label could otherwise bypass the medical gate for these serious reports. No injury type is added. No transition
overrides are invented; no transition is promotable. Elapsed time, camp phase,
clearance or favorable whole-athlete readiness never activate advanced stages.

## Unknown-side attribution and migration

Yes, a migration is required. Apply
`supabase/migrations/20261002234842_pathway_profile_unknown_side.sql` before the
application rollout. It replaces only record_rehab_exposure with the existing body
plus a generic frozen-policy match. No table, RLS or environment changes are needed.
Existing service_role-only execution remains; public/anon/authenticated receive no
new permission. supabase/schema.sql mirrors the same definition.

The Python allowlist is replaced by nonempty frozen policy provenance, preserving
exact injury/episode/region identity and baseline stage restrictions. SQL additionally
requires a done/modified owner completion with the exact revision, injury, episode,
drill, policy id, matching baseline stage and not_applicable laterality. A future
profile needs no SQL list edit. Ordinary unknown-side legacy work remains refused.
Unknown-side observations retain feedback but remain excluded from positive capacity
evidence by read_exact_events / side_matches. Named-side exercises still require side.

The same existing location registry now reconciles clinical bank aliases with profile
regions (hamstrings versus hamstring). No broader tissue or neighbouring-region fallback
is introduced. New reviewed target_regions explicitly include the canonical spelling.

## Exact increase in coverage

Live strain region/type combinations: 1 -> 5 (+4, +400%). All live injury profiles:
2 -> 6 (+4, +200%). Strain profile/stage combinations: 2 -> 10 (+8).
Bank strain drills: 92 -> 100 (+8 fixed routines); regions remain 25. All bank drills:
1545 -> 1553. Advanced live coverage increase: zero. This is code/catalog activation;
production deployment and the prerequisite database migration are not applied here.

## Per-identity deferred / rejected inventory

All identities below remain needs_review and outside the live prescription whitelist,
except the two sourced chest routines. Deferral is a rollout decision, not a new ledger
review state or a claim of clinical review for every legacy record.

### biceps

- `bicep_strain_isometric_bicep_curl_hold_mid_range` (Isometric Bicep Curl Hold (Mid-Range)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `bicep_strain_band_resisted_eccentric_curl` (Band-Resisted Eccentric Curl): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `bicep_strain_cable_curl_with_fat_grip` (Cable Curl with Fat Grip): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `bicep_strain_supinated_isometric_elbow_hold` (Supinated Isometric Elbow Hold): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### calf

- `calf_strain_double_leg_calf_raises` (Double-Leg Calf Raises): Deferred original mixed-demand routine; fixed derivative reviewed for RESTORE only. Ledger flags: none; mixed camp demand: True.
- `calf_strain_isometric_wall_push_hold` (Isometric Wall Push Hold): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: VARIABLE_DEMAND_PROGRESSION, SPEED_PROGRESSION_IN_NOTES; mixed camp demand: True.
- `calf_strain_isometric_tip_toe_wall_press` (Isometric Tip-Toe Wall Press): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `calf_strain_active_band_calf_pumps` (Active Band Calf Pumps): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `calf_strain_double_leg_calf_raises_2` (Double-Leg Calf Raises): Rejected for this rollout as an exact duplicate; original record retained as migration debt. Ledger flags: none; mixed camp demand: True.
- `calf_strain_isometric_wall_push_hold_2` (Isometric Wall Push Hold): Rejected for this rollout as an exact duplicate; original record retained as migration debt. Ledger flags: VARIABLE_DEMAND_PROGRESSION, SPEED_PROGRESSION_IN_NOTES; mixed camp demand: True.
- `calf_strain_isometric_tip_toe_wall_press_2` (Isometric Tip-Toe Wall Press): Rejected for this rollout as an exact duplicate; original record retained as migration debt. Ledger flags: none; mixed camp demand: True.
- `calf_strain_active_band_calf_pumps_2` (Active Band Calf Pumps): Rejected for this rollout as an exact duplicate; original record retained as migration debt. Ledger flags: none; mixed camp demand: True.

### chest

- `chest_strain_isometric_wall_push_chest_height` (Isometric Wall Push (Chest Height)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `chest_strain_resistance_band_chest_fly` (Resistance Band Chest Fly): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `chest_strain_recovery_support` (Chest strain recovery support): Reviewed existing sourced baseline; unchanged prescription and hashes. Ledger flags: none; mixed camp demand: False.
- `chest_strain_comfortable_movement` (Comfortable chest-region movement): Reviewed existing sourced baseline; unchanged prescription and hashes. Ledger flags: none; mixed camp demand: False.

### core

- `core_strain_dead_bug_with_band_resistance` (Dead Bug with Band Resistance): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: VARIABLE_DEMAND_PROGRESSION, SPEED_PROGRESSION_IN_NOTES; mixed camp demand: True.
- `core_strain_forearm_plank_eccentric_reaches` (Forearm Plank – Eccentric Reaches): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### elbow

- `elbow_strain_isometric_elbow_flexion_hold_90` (Isometric Elbow Flexion Hold (90°)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `elbow_strain_pronation_supination_with_light_dumbbell` (Pronation/Supination with Light Dumbbell): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### eye

- `eye_strain_near_far_focal_shifts` (Near-Far Focal Shifts): Deferred: specialist/nonspecific content does not support a regional muscle-strain profile. Ledger flags: none; mixed camp demand: True.
- `eye_strain_pencil_push_ups` (Pencil Push-Ups): Deferred: specialist/nonspecific content does not support a regional muscle-strain profile. Ledger flags: none; mixed camp demand: True.
- `eye_strain_fitlight_reflex_matrix` (FitLight Reflex Matrix): Deferred: specialist/nonspecific content does not support a regional muscle-strain profile. Ledger flags: none; mixed camp demand: True.
- `eye_strain_multi_task_gaze_balance` (Multi-Task Gaze + Balance): Deferred: specialist/nonspecific content does not support a regional muscle-strain profile. Ledger flags: none; mixed camp demand: True.

### fingers

- `fingers_strain_rubber_band_finger_extensions` (Rubber Band Finger Extensions): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `fingers_strain_isometric_finger_pinch_plate_or_towel` (Isometric Finger Pinch (Plate or Towel)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `fingers_strain_digit_specific_flexion_holds_putty_or_band` (Digit-Specific Flexion Holds (Putty or Band)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `fingers_strain_elastic_finger_push_press` (Elastic Finger Push-Press): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### foot

- `foot_strain_resisted_toe_pulls_with_band` (Resisted Toe Pulls with Band): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `foot_strain_mid_foot_isometric_holds_band_loop` (Mid-Foot Isometric Holds (Band Loop)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### forearm

- `forearm_strain_wrist_curls_slow_tempo` (Wrist Curls (Slow Tempo)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `forearm_strain_finger_extension_band_flicks` (Finger Extension Band Flicks): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### glute

- `glutes_strain_glute_bridge_iso_holds` (Glute Bridge Iso Holds): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `glutes_strain_massage_gun_glute_max_line` (Massage Gun – Glute Max Line): Deferred: passive recovery claims do not establish staged active strain rehab; avoid early massage. Ledger flags: none; mixed camp demand: True.
- `glutes_strain_glute_bridge_with_isometric_hold` (Glute Bridge with Isometric Hold): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: VARIABLE_DEMAND_PROGRESSION, SPEED_PROGRESSION_IN_NOTES; mixed camp demand: True.
- `glutes_strain_quadruped_kickbacks_band_optional` (Quadruped Kickbacks (Band Optional)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### groin

- `groin_strain_side_lying_hip_adduction` (Side-Lying Hip Adduction): Deferred original mixed-demand routine; fixed derivative reviewed for RESTORE only. Ledger flags: VARIABLE_DEMAND_PROGRESSION, SPEED_PROGRESSION_IN_NOTES; mixed camp demand: True.
- `groin_strain_standing_cable_adduction` (Standing Cable Adduction): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### hamstring

- `hamstrings_strain_isometric_hamstring_bridge` (Isometric Hamstring Bridge): Deferred original mixed-demand routine; fixed derivative reviewed for RESTORE only. Ledger flags: none; mixed camp demand: True.
- `hamstrings_strain_massage_gun_biceps_femoris_sweep` (Massage Gun – Biceps Femoris Sweep): Deferred: passive recovery claims do not establish staged active strain rehab; avoid early massage. Ledger flags: none; mixed camp demand: True.

### hand

- `hand_strain_wrist_flexor_isometric_press_palm_down` (Wrist Flexor Isometric Press (Palm Down)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `hand_strain_finger_walks_on_wall` (Finger Walks on Wall): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `hand_strain_loaded_palm_extensions_rubber_band` (Loaded Palm Extensions (Rubber Band)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `hand_strain_isometric_grip_on_towel` (Isometric Grip on Towel): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: VARIABLE_DEMAND_PROGRESSION, SPEED_PROGRESSION_IN_NOTES; mixed camp demand: True.

### jaw

- `jaw_strain_isometric_jaw_clench_mouthguard_in` (Isometric Jaw Clench (Mouthguard In)): Deferred: specialist/nonspecific content does not support a regional muscle-strain profile. Ledger flags: none; mixed camp demand: True.
- `jaw_strain_lateral_jaw_pushes_finger_resistance` (Lateral Jaw Pushes (Finger Resistance)): Deferred: specialist/nonspecific content does not support a regional muscle-strain profile. Ledger flags: VARIABLE_DEMAND_PROGRESSION, SPEED_PROGRESSION_IN_NOTES; mixed camp demand: True.

### knee

- `knee_strain_wall_sit_short_arc` (Wall Sit (Short Arc)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `knee_strain_mini_band_lateral_walks` (Mini-Band Lateral Walks): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `knee_strain_lateral_step_downs` (Lateral Step-Downs): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `knee_strain_band_assisted_lateral_lunges` (Band-Assisted Lateral Lunges): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `knee_strain_wall_sit_short_arc_2` (Wall Sit (Short Arc)): Rejected for this rollout as an exact duplicate; original record retained as migration debt. Ledger flags: none; mixed camp demand: True.
- `knee_strain_mini_band_lateral_walks_2` (Mini-Band Lateral Walks): Rejected for this rollout as an exact duplicate; original record retained as migration debt. Ledger flags: none; mixed camp demand: True.
- `knee_strain_lateral_step_downs_2` (Lateral Step-Downs): Rejected for this rollout as an exact duplicate; original record retained as migration debt. Ledger flags: none; mixed camp demand: True.
- `knee_strain_band_assisted_lateral_lunges_2` (Band-Assisted Lateral Lunges): Rejected for this rollout as an exact duplicate; original record retained as migration debt. Ledger flags: none; mixed camp demand: True.

### lower back

- `lower_back_strain_glute_bridge_walkout` (Glute Bridge Walkout): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `lower_back_strain_quadruped_rock_backs` (Quadruped Rock Backs): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `lower_back_strain_glute_bridge_walkouts` (Glute Bridge Walkouts): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `lower_back_strain_bird_dog_with_reach` (Bird Dog with Reach): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### neck

- `neck_strain_isometric_neck_flexion_wall` (Isometric Neck Flexion (Wall)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: VARIABLE_DEMAND_PROGRESSION, SPEED_PROGRESSION_IN_NOTES; mixed camp demand: True.
- `neck_strain_neck_retraction_with_band` (Neck Retraction with Band): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `neck_strain_supine_band_resisted_neck_flexion` (Supine Band-Resisted Neck Flexion): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `neck_strain_neck_clock_isometrics` (Neck Clock Isometrics): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### obliques

- `obliques_strain_side_plank_with_band_row` (Side Plank with Band Row): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `obliques_strain_rotational_med_ball_toss_seated` (Rotational Med Ball Toss (Seated)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `obliques_strain_side_plank_with_reach_under` (Side Plank with Reach Under): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `obliques_strain_dead_bug_with_banded_chop` (Dead Bug with Banded Chop): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `obliques_strain_half_kneeling_cable_chop` (Half-Kneeling Cable Chop): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `obliques_strain_rotational_med_ball_toss_wall` (Rotational Med Ball Toss (Wall)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### quads

- `quads_strain_isometric_wall_sit_mid_range` (Isometric Wall Sit (Mid-Range)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `quads_strain_foam_roller_quad_sweep` (Foam Roller – Quad Sweep): Deferred: passive recovery claims do not establish staged active strain rehab; avoid early massage. Ledger flags: none; mixed camp demand: True.

### shoulder

- `shoulder_strain_wall_slides_with_foam_roller` (Wall Slides with Foam Roller): Deferred: passive recovery claims do not establish staged active strain rehab; avoid early massage. Ledger flags: none; mixed camp demand: True.
- `shoulder_strain_landmine_shoulder_press` (Landmine Shoulder Press): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `shoulder_strain_isometric_wall_press_90_abduction` (Isometric Wall Press (90° Abduction)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: False.
- `shoulder_strain_banded_y_raise` (Banded Y-Raise): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: False.

### toe

- `toe_strain_toe_towel_slides_loaded_variant` (Toe Towel Slides (Loaded Variant)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `toe_strain_manual_toe_flexor_resistance_band` (Manual Toe Flexor Resistance (Band)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### triceps

- `triceps_strain_isometric_wall_triceps_press` (Isometric Wall Triceps Press): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `triceps_strain_overhead_band_triceps_extensions` (Overhead Band Triceps Extensions): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `triceps_strain_push_up_to_tabletop_flow` (Push-Up to Tabletop Flow): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `triceps_strain_kettlebell_crush_press_light` (Kettlebell Crush Press (Light)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### unspecified

- `unspecified_strain_general_isometric_holds_5_position_circuit` (General Isometric Holds (5-position circuit)): Deferred: specialist/nonspecific content does not support a regional muscle-strain profile. Ledger flags: none; mixed camp demand: False.
- `unspecified_strain_foam_rolling_tempo_eccentrics` (Foam Rolling + Tempo Eccentrics): Deferred: passive recovery claims do not establish staged active strain rehab; avoid early massage. Ledger flags: none; mixed camp demand: False.

### upper back

- `upper_back_strain_prone_swimmers` (Prone Swimmers): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `upper_back_strain_scapular_push_ups` (Scapular Push-Ups): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `upper_back_strain_suspended_row_trx_or_rings` (Suspended Row (TRX or Rings)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: VARIABLE_DEMAND_PROGRESSION, SPEED_PROGRESSION_IN_NOTES; mixed camp demand: True.
- `upper_back_strain_resistance_band_reverse_flys` (Resistance Band Reverse Flys): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

### wrist

- `wrist_strain_wrist_curl_light_dumbbell` (Wrist Curl (Light Dumbbell)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `wrist_strain_reverse_wrist_curl` (Reverse Wrist Curl): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `wrist_strain_cable_reverse_curl_eccentric` (Cable Reverse Curl (Eccentric)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `wrist_strain_wrist_flexion_bear_hug_iso` (Wrist Flexion Bear Hug Iso): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `wrist_strain_wrist_roller_light_plate` (Wrist Roller (Light Plate)): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.
- `wrist_strain_farmer_s_hold_with_wrist_control` (Farmer’s Hold with Wrist Control): Deferred: unreviewed or variable resistance/range/speed/sport demand; no defensible fixed baseline prescription established in this review. Ledger flags: none; mixed camp demand: True.

Quadriceps movement parent outside the strain inventory:
`quads_unspecified_sliding_leg_extensions_towel_under_foot` stays needs_review with
its original hash; only the slow, supported fixed strain derivative is reviewed.

## Verification

Run the family coverage suite together with rehab pathways/equivalence, bundles,
completion, exposure, metadata, selector, progression, scheduling and Today safety
suites. Run clinical/bank/ledger validators, the metadata applicator --check and the
injury vocabulary audit. `tools/test_rehab_migration.mjs` exercises the migration in
isolated PGlite PostgreSQL, including a future policy id absent from the catalog,
owner and provenance mismatch rejections, frozen snapshots and idempotent feedback.
It does not verify multi-connection advisory-lock races or production deployment.

Validation performed in this workspace:

- Clinical/profile, metadata-ledger and bank validators: passed; no errors, warnings or stale reviews. Bank information messages remain historical migration debt.
- Metadata applicator --check: no pending changes or stale reviews.
- Injury vocabulary audit: passed; 33 canonical types and 7 families remain unchanged.
- Family, stage and vocabulary test run: 263 passed.
- Rehab/progression/selector/scheduling/completion/generation/Today regression run: 728 passed, 15 PostgreSQL concurrency tests skipped because REHAB_TEST_DATABASE_URL is unset.
- Family/journey/multi-injury/clearance/Today safety/readiness/restraint run: 338 passed.
- Pathway composition/equivalence, bundles, metadata and exposure assertions also passed in the broader review run; the old zero-reviewed ledger assertion was updated and its complete suite subsequently passed.
- Isolated PostgreSQL migration harness: 17 acceptance checks passed, including generic future-profile attribution and negative owner/policy/stage/revision/drill cases. Actual multi-connection database race behavior remains unverified here.
- Changed Python modules compile, Ruff passes, git diff --check passes, and the curated seed is byte-idempotent.
- No frontend changes; no frontend build was required. No production migration, deployment or clinical sign-off is claimed.

- Final urgent-taxonomy/triage and structured-triage regression run: 204 passed.
- Ideal advanced evidence was explicitly tested against all six shipped profiles: 6 passed; none progresses beyond RESTORE.
