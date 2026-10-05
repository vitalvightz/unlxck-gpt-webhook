# Original nonspecific MSK inventory audit

Baseline Main: 2db8d0d3, after #2736 merged. Total original drills: 358 across 121 exact combinations and 31 canonical regions. Audit before rollout edits. All stage/load/impact/velocity/equipment values were null; all originals needs_review; no symptom profiles active. The JSON retains complete original mechanical fields, aliases and hashes.

346 have camp-phase instructions, 232 mix distinct phases, 45 contain explicit hidden-progressions, 105 contain vague mobility/flush/release/activation/recovery wording. Equipment and actual demand cannot be established from these labels alone. Canonical aliases: bicep/biceps, hamstrings/hamstring, glutes/glute, lower_back/lower back.

Subsequent clinical review selected 16 exact profiles (listed in nonspecific-msk-rollout.md); all other original combinations remain inactive. The inventory below preserves the pre-change audit.

## pain: 86 drills

### achilles: 4

- `achilles_pain_isometric_holds_in_tip_toe`: Isometric Holds in Tip-Toe; needs_review; SPP: Load tendon without movement → TAPER: Pre-drill activation
- `achilles_pain_banded_heel_push_with_hold`: Banded Heel Push with Hold; needs_review; SPP: Strengthen in shortened position → TAPER: Use as low-fade neural primer
- `achilles_pain_isometric_holds_in_tip_toe_2`: Isometric Holds in Tip-Toe; needs_review; SPP: Load tendon without movement → TAPER: Pre-drill activation
- `achilles_pain_banded_heel_push_with_hold_2`: Banded Heel Push with Hold; needs_review; SPP: Strengthen in shortened position → TAPER: Use as low-fade neural primer

### biceps: 2

- `bicep_pain_wall_bicep_isometric_straight_arm`: Wall Bicep Isometric (Straight Arm); needs_review; SPP: Reduce tendon sensitivity → TAPER: Maintain readiness with minimal load
- `bicep_pain_triceps_stretch_with_shoulder_extension`: Triceps Stretch with Shoulder Extension; needs_review; SPP: Offload anterior shoulder tension → TAPER: Balance flexor–extensor tension

### chest: 2

- `chest_pain_chest_supported_banded_row`: Chest-Supported Banded Row; needs_review; GPP: Train posterior chain safely → SPP: Rebalance push-pull system
- `chest_pain_isometric_chest_squeeze_swiss_ball`: Isometric Chest Squeeze (Swiss Ball); needs_review; GPP: Activate without movement → SPP: Add tempo hold

### core: 2

- `core_pain_isometric_hollow_hold`: Isometric Hollow Hold; needs_review; SPP: Maximize midline tension → TAPER: Short holds to maintain readiness
- `core_pain_glute_bridge_march_heel_loaded`: Glute Bridge March (Heel Loaded); needs_review; SPP: Support lumbar offload → TAPER: Retain cross-chain firing

### elbow: 2

- `elbow_pain_neutral_grip_db_curls_isometric`: Neutral Grip DB Curls (Isometric); needs_review; SPP: Minimize joint strain while restoring load → TAPER: Maintain activation under low fatigue
- `elbow_pain_wall_press_iso_at_90_elbow_flexion`: Wall Press Iso at 90° Elbow Flexion; needs_review; SPP: Static control with low irritation → TAPER: CNS-safe tension before fight

### eye: 4

- `eye_pain_saccadic_eye_jumps_horizontal_vertical`: Saccadic Eye Jumps (Horizontal/Vertical); needs_review; SPP: Rebuild rapid gaze redirection with intent → TAPER: Reduce rep count for light CNS prep
- `eye_pain_blink_tolerance_training`: Blink Tolerance Training; needs_review; SPP: Condition discomfort threshold → TAPER: Integrate fast flinch control
- `eye_pain_laser_pointer_rapid_switch_left_right_center`: Laser Pointer Rapid Switch (Left–Right–Center); needs_review; GPP: Restore speed without load → SPP: Layer in head movement and light footwork
- `eye_pain_peripheral_light_tap_drill`: Peripheral Light Tap Drill; needs_review; GPP: Boost visual span awareness → SPP: React to lateral cues with limb coordination

### face: 4

- `face_pain_low_frequency_tens_infraorbital_region`: Low-Frequency TENS (Infraorbital Region); needs_review; SPP: Dull local sensitivity → TAPER: Retain contact tolerance before competition
- `face_pain_facial_percussion_taps_forehead_cheeks`: Facial Percussion Taps (Forehead, Cheeks); needs_review; SPP: Normalize contact sensation → TAPER: Final prep for glove impact
- `face_pain_topical_desensitization_tap_hold`: Topical Desensitization Tap + Hold; needs_review; GPP: Reduce nociceptive sensitivity → SPP: Sustain pressure threshold during glove drills
- `face_pain_trigger_point_press_tmj_and_cheekbone`: Trigger Point Press (TMJ and Cheekbone); needs_review; GPP: Release referred facial tension → SPP: Combine with head movement patterns

### fingers: 2

- `fingers_pain_finger_isometrics_against_resistance_band`: Finger Isometrics Against Resistance Band; needs_review; SPP: Build tolerance in neutral grip → TAPER: Maintain output with no irritation
- `fingers_pain_ice_massage_rolling_small_ball`: Ice Massage Rolling (Small Ball); needs_review; SPP: Control inflammation post-training → TAPER: Use as pre-session reset

### foot: 2

- `foot_pain_short_foot_doming`: Short Foot Doming; needs_review; GPP: Rebuild arch activation → SPP: Progress to standing or loaded stances
- `foot_pain_toe_spreads_with_band`: Toe Spreads with Band; needs_review; GPP: Mobilize transverse arch → SPP: Add tempo or band tension

### forearm: 2

- `forearm_pain_isometric_wrist_neutral_hold_dumbbell`: Isometric Wrist Neutral Hold (Dumbbell); needs_review; GPP: Avoid joint motion → SPP: Add time under tension for grip
- `forearm_pain_towel_twists_isometric`: Towel Twists (Isometric); needs_review; GPP: Isolate torsion safely → SPP: Build tolerance gradually

### glute: 4

- `glutes_pain_banded_clamshells`: Banded Clamshells; needs_review; SPP: Local glute activation → TAPER: Short sets pre-training to prevent under-recruitment
- `glutes_pain_foam_roll_side_glute_sweep`: Foam Roll – Side Glute Sweep; needs_review; SPP: Release lateral glute line → TAPER: Decrease soreness before fight night
- `glutes_pain_supine_band_abducted_march`: Supine Band-Abducted March; needs_review; GPP: Restore pain-free glute medius drive → SPP: Add volume under fatigue
- `glutes_pain_wall_sit_with_glute_squeeze`: Wall Sit with Glute Squeeze; needs_review; GPP: Activate without dynamic load → SPP: Introduce time-under-tension

### groin: 4

- `groin_pain_isometric_squeeze_with_ball`: Isometric Squeeze with Ball; needs_review; GPP: Pain-free static activation → SPP: Progress to dynamic concentric reps
- `groin_pain_adductor_bridge_feet_on_bench`: Adductor Bridge (Feet on Bench); needs_review; GPP: Build eccentric strength → SPP: Add tempo or single-leg bias
- `groin_pain_ball_squeeze_in_supine_bridge`: Ball Squeeze in Supine Bridge; needs_review; GPP: Load posterior chain + adductors pain-free → SPP: Increase hold or reps
- `groin_pain_band_adducted_lunge_hold`: Band-Adducted Lunge Hold; needs_review; GPP: Activate under guidance → SPP: Reinforce joint position

### hamstring: 2

- `hamstrings_pain_short_range_nordic_drops_assisted`: Short-Range Nordic Drops (Assisted); needs_review; SPP: Controlled exposure → TAPER: Reduce ROM, keep tension sharp
- `hamstrings_pain_foam_roll_full_hamstring_sweep`: Foam Roll – Full Hamstring Sweep; needs_review; SPP: Post-load recovery → TAPER: Reset tone pre-comp

### hand: 4

- `hand_pain_hand_iso_hold_around_grip_trainer`: Hand Iso Hold Around Grip Trainer; needs_review; SPP: Low-motion tension → TAPER: Retain isometric control with low CNS cost
- `hand_pain_fingertip_holds_on_wall`: Fingertip Holds on Wall; needs_review; SPP: Stimulate contact point control → TAPER: Taper down intensity, not precision
- `hand_pain_friction_ball_circles_palm_fingers`: Friction Ball Circles (Palm + Fingers); needs_review; GPP: Desensitize contact zones → SPP: Maintain mobility under neural tension
- `hand_pain_hand_floss_shake_outs`: Hand Floss + Shake-Outs; needs_review; GPP: Clear neural irritation → SPP: Maintain input through light reactive drills

### hip: 2

- `hip_pain_standing_hip_cars`: Standing Hip CARs; needs_review; GPP: Control hip through full pain-free ROM → SPP: Add tension or hold at end ranges
- `hip_pain_massage_gun_deep_glute_line`: Massage Gun – Deep Glute Line; needs_review; GPP: Loosen surrounding tissue → SPP: Use post-drill to avoid flare-up

### jaw: 2

- `jaw_pain_jaw_taps_knuckle_percussion`: Jaw Taps (Knuckle Percussion); needs_review; SPP: Desensitize superficial jaw pain → TAPER: Maintain contact tolerance during deload
- `jaw_pain_mouthguard_clench_holds_short_bursts`: Mouthguard Clench Holds (Short Bursts); needs_review; SPP: Simulate real-fight biting effort → TAPER: Sharpen reflex under CNS constraint

### knee: 4

- `knee_pain_terminal_knee_extensions_tkes`: Terminal Knee Extensions (TKEs); needs_review; GPP: Target VMO → SPP: Increase band load or reps
- `knee_pain_massage_gun_quad_sweep_to_patella`: Massage Gun – Quad Sweep to Patella; needs_review; GPP: Reduce tracking tension → SPP: Use after TKE or compound lifts
- `knee_pain_terminal_knee_extensions_tkes_2`: Terminal Knee Extensions (TKEs); needs_review; GPP: Target VMO → SPP: Increase band load or reps
- `knee_pain_massage_gun_quad_sweep_to_patella_2`: Massage Gun – Quad Sweep to Patella; needs_review; GPP: Reduce tracking tension → SPP: Use after TKE or compound lifts

### lower back: 6

- `lower_back_pain_supine_90_90_breathing`: Supine 90/90 Breathing; needs_review; GPP: Reduce spinal tone → SPP: Integrate with trunk movement
- `lower_back_pain_wall_dead_bug_with_iso_hold`: Wall Dead Bug with Iso Hold; needs_review; GPP: Teach bracing → SPP: Extend hold or add band reach
- `lower_back_pain_supine_pelvic_tilts`: Supine Pelvic Tilts; needs_review; GPP: Reintroduce control with no load
- `lower_back_pain_bird_dog_hold_only`: Bird Dog (Hold Only); needs_review; GPP: Low-stress spinal engagement
- `lower_back_pain_supine_90_90_breathing_2`: Supine 90/90 Breathing; needs_review; GPP: Downregulate spinal tone → SPP: Tie into movement bracing
- `lower_back_pain_wall_dead_bug_iso_hold`: Wall Dead Bug Iso Hold; needs_review; GPP: Lock lumbar control → SPP: Add reach or band tension

### neck: 2

- `neck_pain_wall_supported_neck_isometrics`: Wall-Supported Neck Isometrics; needs_review; SPP: Build low-risk tolerance → TAPER: Retain tension pre-comp without fatigue
- `neck_pain_neck_extension_with_towel_resistance`: Neck Extension with Towel Resistance; needs_review; SPP: Develop concentric control → TAPER: Reduce load, maintain range

### obliques: 4

- `obliques_pain_isometric_side_plank_short_repeats`: Isometric Side Plank – Short Repeats; needs_review; SPP: Maintain engagement under control → TAPER: Preserve tone with low volume
- `obliques_pain_pallof_press_light_band`: Pallof Press (Light Band); needs_review; SPP: Reinforce anti-rotation → TAPER: Keep transverse activation sharp
- `obliques_pain_isometric_side_plank_on_elbow`: Isometric Side Plank on Elbow; needs_review; GPP: Safe reintroduction to load → SPP: Progress with reach or band
- `obliques_pain_wall_cable_isometric_hold_lateral`: Wall Cable Isometric Hold (Lateral); needs_review; GPP: Minimal-movement tension → SPP: Add diagonal force

### quads: 2

- `quads_pain_mini_band_tkes_terminal_knee_extensions`: Mini-Band TKEs (Terminal Knee Extensions); needs_review; SPP: Activate quad without overload → TAPER: Maintain pattern without fatigue
- `quads_pain_isometric_quad_flex_straight_leg`: Isometric Quad Flex (Straight Leg); needs_review; SPP: Rebuild control through tension → TAPER: Use between sets to keep motor pattern sharp

### shin: 4

- `shin_pain_heel_walks`: Heel Walks; needs_review; SPP: Train anterior chain under low impact → TAPER: Maintain foot strike tolerance
- `shin_pain_isometric_toe_lift_holds`: Isometric Toe Lift Holds; needs_review; SPP: Load without range → TAPER: Quick tension cues pre-sprint or drill
- `shin_pain_heel_walks_2`: Heel Walks; needs_review; SPP: Train anterior chain under low impact → TAPER: Maintain foot strike tolerance
- `shin_pain_isometric_toe_lift_holds_2`: Isometric Toe Lift Holds; needs_review; SPP: Load without range → TAPER: Quick tension cues pre-sprint or drill

### shoulder: 4

- `shoulder_pain_isometric_wall_push_shoulder_level`: Isometric Wall Push (Shoulder Level); needs_review; SPP: Activate without motion (anterior) → TAPER: Sustain low-level tension
- `shoulder_pain_banded_face_pull_iso_hold`: Banded Face Pull Iso Hold; needs_review; SPP: Posterior activation without elevation → TAPER: Retain postural control
- `shoulder_pain_wall_angels_floor_version_if_needed`: Wall Angels (Floor Version if Needed); needs_review; SPP: Low-load reactivation of full chain (posterior + lateral)
- `shoulder_pain_overhead_isometric_hold_with_band`: Overhead Isometric Hold with Band; needs_review; TAPER: Reinforce pain-free tension for anterior deltoid

### toe: 2

- `toe_pain_isometric_big_toe_press_into_ground`: Isometric Big Toe Press into Ground; needs_review; SPP: Load without movement → TAPER: Use light holds to retain signal
- `toe_pain_toe_flexor_resistance_band_pulls`: Toe Flexor Resistance Band Pulls; needs_review; SPP: Rebuild control → TAPER: Low fatigue, low movement

### triceps: 2

- `triceps_pain_neutral_grip_cable_extensions`: Neutral-Grip Cable Extensions; needs_review; SPP: Mid-range output with low strain → TAPER: Maintain groove without locking out
- `triceps_pain_isometric_triceps_bridge_wall_hold`: Isometric Triceps Bridge (Wall Hold); needs_review; SPP: Rebuild stability → TAPER: Sustain tone under zero motion

### unspecified: 4

- `unspecified_pain_breathwork_parasympathetic_ground_flow`: Breathwork + Parasympathetic Ground Flow; needs_review; Releases tension. 4s inhale / 8s exhale, paired with gentle mobility.
- `unspecified_pain_neuro_friendly_band_activation`: Neuro-Friendly Band Activation; needs_review; Band retraction, extension, rotation drills. 3 sets light resistance.
- `unspecified_pain_breath_guided_joint_mobilization`: Breath-Guided Joint Mobilization; needs_review; Focus on 3–4 joint circles or controlled articulations paired with slow nasal breathing. → SPP: convert to low-load tempo exercises for the affected region.
- `unspecified_pain_elevate_wrap_protocol`: Elevate + Wrap Protocol; needs_review; Advise light compression wrap and elevation above heart for 10–15 min post-training. → SPP: if pain subsides, begin reintroducing low RPE movement.

### upper back: 4

- `upper_back_pain_wall_angels`: Wall Angels; needs_review; SPP: Improve scapular glide → TAPER: Retain postural awareness
- `upper_back_pain_massage_gun_t_spine_sweep`: Massage Gun – T-Spine Sweep; needs_review; SPP: Reduce local tone → TAPER: Flush tension post-spar
- `upper_back_pain_band_lat_stretch_underhand_grip`: Band Lat Stretch (Underhand Grip); needs_review; GPP: Offload posterior tension → SPP: Blend into active range
- `upper_back_pain_kneeling_band_row_to_external_rotation`: Kneeling Band Row to External Rotation; needs_review; GPP: Introduce scapular control → SPP: Build external rotator strength

### wrist: 4

- `wrist_pain_isometric_dumbbell_wrist_hold_neutral`: Isometric Dumbbell Wrist Hold (Neutral); needs_review; SPP: Controlled tension → TAPER: Light prepare prior to session
- `wrist_pain_forearm_supination_pronation_paused`: Forearm Supination/Pronation Paused; needs_review; SPP: Reload torsion control → TAPER: Retain mid-range readiness
- `wrist_pain_pronation_supination_with_band`: Pronation/Supination with Band; needs_review; SPP: Controlled rotation under tension → TAPER: Reduce amplitude, sharpen reflex
- `wrist_pain_grip_trainer_soft_ball_pulse`: Grip Trainer – Soft Ball Pulse; needs_review; SPP: Low-resistance endurance → TAPER: CNS-friendly activation

## soreness: 76 drills

### biceps: 4

- `bicep_soreness_lacrosse_ball_compression_distal_bicep`: Lacrosse Ball Compression (Distal Bicep); needs_review; TAPER: Flush DOMS and restore elbow mobility
- `bicep_soreness_active_supination_elbow_flexion`: Active Supination + Elbow Flexion; needs_review; TAPER: Retain contractile control with minimal load
- `bicep_soreness_gentle_arm_circles_neutral`: Gentle Arm Circles (Neutral); needs_review; TAPER: Restore mobility and blood flow
- `bicep_soreness_soft_tissue_glide_massage_stick`: Soft Tissue Glide – Massage Stick; needs_review; TAPER: Downregulate tension pre-fight

### chest: 2

- `chest_soreness_wall_pec_stretch_elbow_high`: Wall Pec Stretch (Elbow High); needs_review; TAPER: Decompress upper pecs post-session
- `chest_soreness_arm_cross_pull_with_deep_breathing`: Arm Cross Pull with Deep Breathing; needs_review; TAPER: Reset tension and breathing patterns

### core: 4

- `core_soreness_belly_breathing_90_90_reset`: Belly Breathing + 90/90 Reset; needs_review; TAPER: Reduce trunk tone → Improve diaphragm/core synergy
- `core_soreness_massage_gun_diagonal_core_sweep`: Massage Gun – Diagonal Core Sweep; needs_review; TAPER: Use short blasts across oblique chain
- `core_soreness_banded_anti_extension_pressouts`: Banded Anti-Extension Pressouts; needs_review; SPP: Reinforce trunk under fatigue → TAPER: Use short sets to keep tension sharp
- `core_soreness_bird_dog_reaches`: Bird Dog Reaches; needs_review; SPP: Control midline with breath → TAPER: Integrate pre-drill for trunk priming

### elbow: 2

- `elbow_soreness_lacrosse_ball_forearm_elbow_floss`: Lacrosse Ball Forearm/Elbow Floss; needs_review; TAPER: Clear tight tissue pre-spar
- `elbow_soreness_cable_low_tension_curls_long_rom`: Cable Low-Tension Curls (Long ROM); needs_review; TAPER: Mobilize and activate without overload

### eye: 2

- `eye_soreness_cool_compress_post_contact`: Cool Compress (Post-Contact); needs_review; GPP: Reduce superficial orbital tension post-strike
- `eye_soreness_visual_meditation_gaze_anchor`: Visual Meditation (Gaze Anchor); needs_review; GPP: Reset focus and pressure via visual stillness

### face: 4

- `face_soreness_manual_facial_tension_release_temporalis`: Manual Facial Tension Release (Temporalis); needs_review; GPP: Release global face tension → TAPER: Keep relaxation pre-fight
- `face_soreness_jaw_to_face_gentle_pulses`: Jaw-to-Face Gentle Pulses; needs_review; GPP: Reset jaw-to-face tension chain → TAPER: Downregulate threat reflex
- `face_soreness_face_focused_box_breathing`: Face-Focused Box Breathing; needs_review; GPP: Downregulate facial tone → TAPER: Anchor parasympathetic state pre-fight
- `face_soreness_facial_stretch_flow_eyes_closed_guided`: Facial Stretch Flow (Eyes Closed Guided); needs_review; GPP: Reset face and breath links → TAPER: Prime CNS clarity

### fingers: 2

- `fingers_soreness_active_finger_flicks`: Active Finger Flicks; needs_review; TAPER: Flush light DOMS → Can pair with hand warm-up drills
- `fingers_soreness_mini_massage_gun_sweep_finger_extensors`: Mini Massage Gun Sweep (Finger Extensors); needs_review; TAPER: Reset tone post-padwork or grappling

### foot: 2

- `foot_soreness_foot_massage_with_lacrosse_ball`: Foot Massage with Lacrosse Ball; needs_review; TAPER: Decrease residual tension → TAPER: Use nightly or post-conditioning
- `foot_soreness_pedal_flush_reverse_bike_low_intensity`: Pedal Flush – Reverse Bike Low Intensity; needs_review; TAPER: Light recovery flush → TAPER: Maintain oxygen to tissue

### forearm: 4

- `forearm_soreness_passive_wrist_circles_tabletop_support`: Passive Wrist Circles (Tabletop Support); needs_review; SPP: Maintain range without loading → TAPER: Gentle recovery
- `forearm_soreness_rice_bucket_twists`: Rice Bucket Twists; needs_review; SPP: Light endurance stimulus → TAPER: Maintain mobility + heat
- `forearm_soreness_massage_gun_on_flexors_extensors`: Massage Gun on Flexors/Extensors; needs_review; TAPER: Loosen up post-grip volume
- `forearm_soreness_light_squeeze_ball_reps`: Light Squeeze Ball Reps; needs_review; TAPER: Wake up forearm tone without tension

### glute: 4

- `glutes_soreness_massage_gun_glute_sweep_30s`: Massage Gun – Glute Sweep (30s); needs_review; TAPER: Improve circulation + reduce stiffness on fight week
- `glutes_soreness_isometric_glute_hold_in_bridge`: Isometric Glute Hold in Bridge; needs_review; TAPER: Reinforce tension without adding fatigue
- `glutes_soreness_light_banded_side_steps`: Light Banded Side Steps; needs_review; TAPER: Gentle reactivation post-DOMS
- `glutes_soreness_massage_gun_sweep_glute_max`: Massage Gun Sweep – Glute Max; needs_review; TAPER: Break residual tightness pre-skill work

### groin: 4

- `groin_soreness_glider_slides_short_range`: Glider Slides (Short Range); needs_review; TAPER: Maintain controlled groin function under no fatigue
- `groin_soreness_massage_gun_sweep_adductor_line`: Massage Gun Sweep (Adductor Line); needs_review; TAPER: Reduce DOMS across adductor group pre-activation
- `groin_soreness_groin_compression_with_band_ice`: Groin Compression with Band + Ice; needs_review; TAPER: Reduce DOMS in taper week
- `groin_soreness_gentle_open_chain_hip_circles`: Gentle Open Chain Hip Circles; needs_review; TAPER: Maintain movement without tension

### hamstring: 2

- `hamstrings_soreness_massage_gun_hamstring_line`: Massage Gun – Hamstring Line; needs_review; TAPER: Clear stiffness from sprint/kick load
- `hamstrings_soreness_reverse_airbike_pedal_low_intensity`: Reverse AirBike Pedal (Low Intensity); needs_review; TAPER: Restore blood flow without adding fatigue

### hand: 2

- `hand_soreness_cold_ball_palm_roll`: Cold Ball Palm Roll; needs_review; TAPER: Flush DOMS and reduce nerve tension
- `hand_soreness_gentle_webbing_massage`: Gentle Webbing Massage; needs_review; TAPER: Reduce soft tissue fatigue in high-load weeks

### hip: 2

- `hip_soreness_glute_foam_roll_slow_sweep`: Glute Foam Roll – Slow Sweep; needs_review; TAPER: Reduce DOMS and promote recovery
- `hip_soreness_mini_band_standing_hip_abduction`: Mini-Band Standing Hip Abduction; needs_review; TAPER: Keep activation without triggering fatigue

### jaw: 4

- `jaw_soreness_jaw_circles_controlled_articulation`: Jaw Circles (Controlled Articulation); needs_review; TAPER: Restore capsule glide and reduce DOMS post-spar
- `jaw_soreness_soft_tissue_sweep_massage_gun_mandible_line`: Soft Tissue Sweep (Massage Gun – Mandible Line); needs_review; TAPER: Clear inflammation from high-contact areas without overstim
- `jaw_soreness_manual_jaw_glide_clinician_support_sim`: Manual Jaw Glide (Clinician Support Sim); needs_review; TAPER: Promote mobility and pain-free control for final prep
- `jaw_soreness_ice_vibration_combo_massage_wand`: Ice + Vibration Combo (Massage Wand); needs_review; TAPER: Calm surface tissue while reducing delayed soreness

### lower back: 6

- `lower_back_soreness_foam_roller_sweep_lumbar`: Foam Roller Sweep – Lumbar; needs_review; TAPER: Restore blood flow without CNS load
- `lower_back_soreness_wall_sit_with_neutral_pelvis`: Wall Sit with Neutral Pelvis; needs_review; TAPER: Maintain posture while letting soreness downregulate
- `lower_back_soreness_wall_support_march`: Wall Support March; needs_review; GPP: Control spinal rhythm during step pattern
- `lower_back_soreness_90_90_hip_lift_breathing`: 90/90 Hip Lift + Breathing; needs_review; GPP: Reactivate core-trunk link safely
- `lower_back_soreness_lying_knee_to_chest_hold`: Lying Knee to Chest Hold; needs_review; TAPER: Flush lower back tension gently
- `lower_back_soreness_foam_roll_low_spine_sweep`: Foam Roll – Low Spine Sweep; needs_review; TAPER: Reset post-training stiffness

### neck: 4

- `neck_soreness_self_massage_traps_cervical`: Self-Massage (Traps & Cervical); needs_review; TAPER: Reduce postural overload and restore blood flow
- `neck_soreness_gentle_neck_tilts_assisted`: Gentle Neck Tilts (Assisted); needs_review; TAPER: Maintain low-stress mobility without stimulating CNS
- `neck_soreness_neck_towel_oscillation_drill`: Neck Towel Oscillation Drill; needs_review; GPP: Promote blood flow safely → TAPER: Use as flush in taper days
- `neck_soreness_gentle_isometric_hold_forehead_press`: Gentle Isometric Hold (Forehead Press); needs_review; GPP: Initiate low-grade motor unit work → TAPER: Retain activation for posture

### obliques: 4

- `obliques_soreness_crocodile_breathing`: Crocodile Breathing; needs_review; TAPER: Reduce lateral wall tone
- `obliques_soreness_ball_rolling_on_oblique_chain`: Ball Rolling on Oblique Chain; needs_review; TAPER: Gentle tissue flush to improve comfort
- `obliques_soreness_standing_side_bends_bodyweight`: Standing Side Bends (Bodyweight); needs_review; TAPER: Mobilize trunk gently without added strain
- `obliques_soreness_wall_slide_iso_side_hold`: Wall Slide Iso (Side Hold); needs_review; TAPER: Light activation for postural balance

### quads: 2

- `quads_soreness_massage_gun_sweep_vl_to_vm`: Massage Gun – Sweep (VL to VM); needs_review; TAPER: Reset tone without overstimulating CNS
- `quads_soreness_slow_cycling_or_airbike`: Slow Cycling or AirBike; needs_review; TAPER: Light flush to reduce DOMS and stiffness

### shoulder: 4

- `shoulder_soreness_massage_gun_posterior_head`: Massage Gun (Posterior Head); needs_review; TAPER: Reduce tension in posterior deltoid after heavy pull days
- `shoulder_soreness_wall_clock_circles_bodyweight`: Wall Clock Circles (Bodyweight); needs_review; TAPER: Active mobility without strain
- `shoulder_soreness_lateral_raise_isometric_at_45`: Lateral Raise Isometric at 45°; needs_review; TAPER: Maintain deltoid tone under low fatigue
- `shoulder_soreness_soft_ball_wall_roll_posterior_shoulder`: Soft Ball Wall Roll (Posterior Shoulder); needs_review; TAPER: Target rear deltoid tension release

### triceps: 2

- `triceps_soreness_light_band_kickbacks`: Light Band Kickbacks; needs_review; TAPER: Flow triceps through low-resistance reps
- `triceps_soreness_straight_arm_downward_swings`: Straight Arm Downward Swings; needs_review; TAPER: Pump blood flow and prep extension pattern

### unspecified: 4

- `unspecified_soreness_recovery_circuit_airdyne_row_band_mobility`: Recovery Circuit (Airdyne, Row, Band Mobility); needs_review; Low RPE movement with mobility and breath pacing. 3–4 rounds.
- `unspecified_soreness_epsom_salt_bath_active_rom_post_soak`: Epsom Salt Bath + Active ROM Post-Soak; needs_review; 20 mins hot soak + unloaded movement to promote circulation and recovery.
- `unspecified_soreness_light_aerobic_flow_stretch`: Light Aerobic Flow + Stretch; needs_review; 5–10 mins of cyclical movement (e.g. bike, jog) into a 3-round mobility flow. → SPP: taper flow to 1–2 rounds and reduce aerobic duration if recovery improves.
- `unspecified_soreness_epsom_salt_soak_or_contrast_shower`: Epsom Salt Soak or Contrast Shower; needs_review; Passive recovery aid to flush DOMS. 15–20 mins soak or 5 cycles of hot/cold shower. → SPP: reserve for high soreness or poor sleep.

### upper back: 2

- `upper_back_soreness_band_pull_aparts_high_rep`: Band Pull-Aparts (High Rep); needs_review; TAPER: Maintain blood flow and rhythm
- `upper_back_soreness_foam_roll_t_spine_sweep`: Foam Roll – T-Spine Sweep; needs_review; TAPER: Reset tightness before drills

### wrist: 4

- `wrist_soreness_massage_gun_sweep_along_wrist`: Massage Gun Sweep Along Wrist; needs_review; TAPER: Flush DOMS post-heavy gripping
- `wrist_soreness_soft_rice_bucket_twists`: Soft Rice Bucket Twists; needs_review; TAPER: Release tension while working grip
- `wrist_soreness_contrast_wrist_baths`: Contrast Wrist Baths; needs_review; TAPER: Flush soreness and inflammation through temperature modulation
- `wrist_soreness_light_grip_iso_hold_towel_squeeze`: Light Grip Iso Hold (Towel Squeeze); needs_review; TAPER: Maintain neuromuscular firing without joint load

## tightness: 84 drills

### ankle: 2

- `ankle_tightness_loaded_dorsiflexion_rocks_barbell_front_foot`: Loaded Dorsiflexion Rocks (Barbell Front Foot); needs_review; SPP: Open ankle range → TAPER: Use in taper for glide maintenance
- `ankle_tightness_massage_gun_anterior_line`: Massage Gun – Anterior Line; needs_review; SPP: Release tight tibialis → TAPER: Short bursts pre-drill

### biceps: 2

- `bicep_tightness_foam_roll_bicep_line`: Foam Roll – Bicep Line; needs_review; GPP: Release fascial knots → SPP: Use pre-session for mobility prep
- `bicep_tightness_banded_arm_extension_stretch`: Banded Arm Extension Stretch; needs_review; GPP: Open long head → SPP: Load into extension before dynamic drills

### calf: 4

- `calf_tightness_wall_calf_stretch_bent_knee`: Wall Calf Stretch (Bent Knee); needs_review; GPP: Target deep soleus tension → TAPER: Maintain length without CNS cost
- `calf_tightness_massage_gun_sweep_soleus_line`: Massage Gun Sweep – Soleus Line; needs_review; GPP: Reduce posterior tightness → TAPER: Use after sparring or jumps
- `calf_tightness_wall_calf_stretch_bent_knee_2`: Wall Calf Stretch (Bent Knee); needs_review; GPP: Target deep soleus tension → TAPER: Maintain length without CNS cost
- `calf_tightness_massage_gun_sweep_soleus_line_2`: Massage Gun Sweep – Soleus Line; needs_review; GPP: Reduce posterior tightness → TAPER: Use after sparring or jumps

### chest: 2

- `chest_tightness_foam_roller_pec_stretch_open_arm`: Foam Roller Pec Stretch (Open Arm); needs_review; GPP: Reset anterior chain posture → TAPER: Maintain soft tissue length
- `chest_tightness_wall_slide_with_overhead_reach`: Wall Slide with Overhead Reach; needs_review; GPP: Restore scapulo-humeral rhythm → TAPER: Keep thoracic glide active

### core: 2

- `core_tightness_cat_cow_pelvic_tilts`: Cat-Cow Pelvic Tilts; needs_review; GPP: Improve anterior-posterior control → TAPER: Use as warmup to downregulate tone
- `core_tightness_massage_gun_abdominals_sweep`: Massage Gun – Abdominals Sweep; needs_review; GPP: Release fascial tightness → TAPER: Use 30s pulse pre-sparring

### elbow: 2

- `elbow_tightness_forearm_wall_slides`: Forearm Wall Slides; needs_review; GPP: Mobilize flexor tendon line → TAPER: Maintain capsule glide without stress
- `elbow_tightness_massage_gun_sweep_medial_elbow`: Massage Gun Sweep (Medial Elbow); needs_review; GPP: Reduce fascial restriction → TAPER: Use before sparring for fluid range

### eye: 2

- `eye_tightness_eye_circles_clockwise_counter`: Eye Circles (Clockwise & Counter); needs_review; GPP: Restore extraocular mobility → TAPER: Maintain smooth gaze range under low arousal
- `eye_tightness_palming_breath_reset`: Palming + Breath Reset; needs_review; GPP: Downregulate eye tension → TAPER: Use as parasympathetic reset post-spar

### face: 2

- `face_tightness_facial_yoga_cheek_lift_holds`: Facial Yoga – Cheek Lift Holds; needs_review; GPP: Restore motor control and mobility → SPP: Add duration or jaw load
- `face_tightness_diagonal_facial_slide_forehead_to_jaw`: Diagonal Facial Slide (Forehead to Jaw); needs_review; GPP: Break up tension planes → SPP: Integrate with neck rotation

### fingers: 2

- `fingers_tightness_finger_cars`: Finger CARs; needs_review; GPP: Restore joint articulation → TAPER: Maintain capsule glide pre-fight
- `fingers_tightness_ball_squeeze_with_pause`: Ball Squeeze with Pause; needs_review; GPP: Encourage full ROM and control → TAPER: Add tempo holds without fatigue

### foot: 2

- `foot_tightness_toe_spreading_with_resistance_band`: Toe Spreading with Resistance Band; needs_review; GPP: Loosen foot structures → TAPER: Maintain mobility for balance
- `foot_tightness_lacrosse_ball_roll_arch_to_base`: Lacrosse Ball Roll – Arch to Base; needs_review; GPP: May reduce perceived stiffness → TAPER: Use daily pre-warmup

### forearm: 2

- `forearm_tightness_forearm_flexor_stretch_wall`: Forearm Flexor Stretch (Wall); needs_review; GPP: Restore anterior line length → TAPER: Use pre-comp to free wrist glide
- `forearm_tightness_massage_gun_sweep_flexor_mass`: Massage Gun Sweep (Flexor Mass); needs_review; GPP: Downregulate tension → TAPER: Flush local tissue pre-fight

### glute: 4

- `glutes_tightness_pigeon_pose_glute_stretch`: Pigeon Pose Glute Stretch; needs_review; GPP: Open up posterior hip → TAPER: Hold 20–30s post-sparring or kicking
- `glutes_tightness_lacrosse_ball_glute_med_sweep`: Lacrosse Ball – Glute Med Sweep; needs_review; GPP: Release bound-up tissue → TAPER: Use short bursts to maintain hip mobility
- `glutes_tightness_seated_figure_4_stretch`: Seated Figure-4 Stretch; needs_review; GPP: Loosen posterior capsule → TAPER: Maintain range pre-spar
- `glutes_tightness_foam_roll_glute_med_and_max`: Foam Roll – Glute Med and Max; needs_review; GPP: Release high-tension points → TAPER: Quick flush for prep

### groin: 2

- `groin_tightness_frog_stretch_with_breathing`: Frog Stretch with Breathing; needs_review; GPP: Open adductors and hips → TAPER: Hold shorter duration to maintain range
- `groin_tightness_adductor_foam_roll`: Adductor Foam Roll; needs_review; GPP: Release dense tissue bands → TAPER: Pre-spar mobility prep

### hamstring: 2

- `hamstrings_tightness_active_hamstring_kicks_banded`: Active Hamstring Kicks (Banded); needs_review; GPP: Mobilize + contract → TAPER: Use during warm-up to maintain speed range
- `hamstrings_tightness_lacrosse_ball_under_hamstring`: Lacrosse Ball Under Hamstring; needs_review; GPP: Release trigger points → TAPER: Use short passes pre-drill

### hand: 2

- `hand_tightness_finger_flossing_with_band`: Finger Flossing with Band; needs_review; GPP: Mobilize connective tissue → TAPER: Maintain glide without CNS drain
- `hand_tightness_manual_stretch_wrist_extension_finger_spread`: Manual Stretch (Wrist Extension + Finger Spread); needs_review; GPP: Release palmar tension → TAPER: Maintain soft tissue readiness

### hip: 2

- `hip_tightness_hip_flexor_stretch_on_wall`: Hip Flexor Stretch on Wall; needs_review; GPP: Open front hip chain → TAPER: Maintain range with 30s holds post-spar
- `hip_tightness_massage_gun_tfl_to_hip_line`: Massage Gun – TFL to Hip Line; needs_review; GPP: Release lateral tightness → TAPER: Use pre-drill to clear anterior restriction

### jaw: 2

- `jaw_tightness_tmj_release_massage_ball_under_cheekbone`: TMJ Release (Massage Ball Under Cheekbone); needs_review; GPP: Break up muscular tension and trigger points → TAPER: Maintain jaw relaxation before high-pressure sessions
- `jaw_tightness_open_close_control_drill_slow_tempo`: Open-Close Control Drill (Slow Tempo); needs_review; GPP: Retrain smooth TMJ motion → TAPER: Use for cooldown neuromuscular reset

### knee: 4

- `knee_tightness_quad_hip_flexor_stretch`: Quad & Hip Flexor Stretch; needs_review; GPP: Loosen anterior chain → TAPER: Maintain extension without CNS load
- `knee_tightness_massage_gun_rectus_line`: Massage Gun – Rectus Line; needs_review; GPP: Clear quad tone → TAPER: Use 30s glides before skill drills
- `knee_tightness_quad_hip_flexor_stretch_2`: Quad & Hip Flexor Stretch; needs_review; GPP: Loosen anterior chain → TAPER: Maintain extension without CNS load
- `knee_tightness_massage_gun_rectus_line_2`: Massage Gun – Rectus Line; needs_review; GPP: Clear quad tone → TAPER: Use 30s glides before skill drills

### lower back: 4

- `lower_back_tightness_child_s_pose_with_side_reach`: Child’s Pose with Side Reach; needs_review; GPP: Decompress posterior chain → TAPER: Light reset between drills
- `lower_back_tightness_massage_gun_lumbar_sweep`: Massage Gun – Lumbar Sweep; needs_review; GPP: Reduce deep fascial tension → TAPER: 30s pre-bed or post-sparring
- `lower_back_tightness_child_s_pose_with_side_reach_2`: Child’s Pose with Side Reach; needs_review; GPP: Decompress posterior chain → TAPER: Reset tension during taper week
- `lower_back_tightness_massage_gun_lumbar_sweep_2`: Massage Gun – Lumbar Sweep; needs_review; GPP: Flush fascial tightness → TAPER: Light pulse post-session

### neck: 2

- `neck_tightness_seated_neck_circles_slow_tempo`: Seated Neck Circles (Slow Tempo); needs_review; GPP: Restore capsule mobility → TAPER: Maintain movement prep pre-fight
- `neck_tightness_lacrosse_ball_scm_release`: Lacrosse Ball SCM Release; needs_review; GPP: Break up fascial restriction → TAPER: Downregulate before comp

### obliques: 6

- `obliques_tightness_standing_side_stretch`: Standing Side Stretch; needs_review; GPP: Regain side-chain length → TAPER: Maintain mobility pre-fight
- `obliques_tightness_massage_gun_external_obliques_sweep`: Massage Gun – External Obliques Sweep; needs_review; GPP: Release superficial tension → TAPER: Fast glide post-training
- `obliques_tightness_side_lying_open_book_stretch`: Side-Lying Open Book Stretch; needs_review; GPP: Restore side-line rotation → TAPER: Use as cooldown reset
- `obliques_tightness_massage_gun_sweep_oblique_ridge`: Massage Gun Sweep (Oblique Ridge); needs_review; GPP: Break up fascial tension → TAPER: Quick flush pre-spar
- `obliques_tightness_foam_roll_oblique_line`: Foam Roll – Oblique Line; needs_review; GPP: Target fascial knots → SPP: Maintain mobility with control
- `obliques_tightness_side_plank_march`: Side Plank March; needs_review; GPP: Reset pelvic control → SPP: Advance to dynamic marching

### quads: 2

- `quads_tightness_wall_quad_stretch_knee_to_wall`: Wall Quad Stretch (Knee to Wall); needs_review; GPP: Improve anterior chain mobility → TAPER: Use daily to maintain stride/kick length
- `quads_tightness_massage_gun_rectus_sweep`: Massage Gun – Rectus Sweep; needs_review; GPP: Loosen quad belly → TAPER: Use short bursts pre-drill

### shin: 4

- `shin_tightness_seated_anterior_shin_stretch`: Seated Anterior Shin Stretch; needs_review; GPP: Loosen tibialis tension → TAPER: Maintain front chain length post-training
- `shin_tightness_lacrosse_ball_glide_tibialis`: Lacrosse Ball Glide – Tibialis; needs_review; GPP: May reduce perceived stiffness → TAPER: Use short sessions pre-spar
- `shin_tightness_seated_anterior_shin_stretch_2`: Seated Anterior Shin Stretch; needs_review; GPP: Loosen tibialis tension → TAPER: Maintain front chain length post-training
- `shin_tightness_lacrosse_ball_glide_tibialis_2`: Lacrosse Ball Glide – Tibialis; needs_review; GPP: May reduce perceived stiffness → TAPER: Use short sessions pre-spar

### shoulder: 4

- `shoulder_tightness_sleeper_stretch`: Sleeper Stretch; needs_review; GPP: Release posterior capsule → TAPER: Maintain horizontal rotation range
- `shoulder_tightness_cross_body_band_stretch`: Cross-Body Band Stretch; needs_review; GPP: Improve tissue glide → TAPER: Quick pre-session opener
- `shoulder_tightness_sleeper_stretch_on_wall`: Sleeper Stretch on Wall; needs_review; GPP: Improve posterior capsule glide
- `shoulder_tightness_massage_gun_sweep_rear_deltoid`: Massage Gun Sweep – Rear Deltoid; needs_review; TAPER: Downregulate tone in posterior deltoid

### toe: 2

- `toe_tightness_toe_extensor_stretch_wall_dorsiflex`: Toe Extensor Stretch (Wall Dorsiflex); needs_review; TAPER: Downregulate toe tension → TAPER: Use post-session or AM
- `toe_tightness_band_assisted_toe_extension_hold`: Band-Assisted Toe Extension Hold; needs_review; TAPER: Maintain smooth end range → TAPER: Low load activation

### triceps: 4

- `triceps_tightness_triceps_wall_stretch`: Triceps Wall Stretch; needs_review; GPP: Open up posterior shoulder line → TAPER: Use post-session to reduce neural tension
- `triceps_tightness_foam_roll_long_head_sweep`: Foam Roll – Long Head Sweep; needs_review; GPP: Loosen fascial chain → TAPER: Target lateral head for lockout fluidity
- `triceps_tightness_overhead_rope_stretch`: Overhead Rope Stretch; needs_review; SPP: Open line through lat and triceps → TAPER: Maintain end range
- `triceps_tightness_stick_triceps_opener_elbow_up`: Stick Triceps Opener (Elbow Up); needs_review; SPP: Target fascia through arm path → TAPER: Use for recovery

### unspecified: 4

- `unspecified_tightness_global_mobility_flow_full_body`: Global Mobility Flow (Full Body); needs_review; 12–15 mins of dynamic stretching, PNF holds, and breath-led movement.
- `unspecified_tightness_contrast_showers_deep_tissue_tooling`: Contrast Showers + Deep Tissue Tooling; needs_review; 1 min hot / 1 min cold x5 + lacrosse ball on most restricted areas.
- `unspecified_tightness_global_foam_roll_pnf_stretch_target_problem_area`: Global Foam Roll + PNF Stretch (target problem area); needs_review; Start with 60–90s foam roll across main tension zones, then add 3x15s PNF contract-relax sets. → SPP: progress to dynamic end-range mobility drills (e.g. CARS, banded openers).
- `unspecified_tightness_full_body_mobility_circuit`: Full-Body Mobility Circuit; needs_review; Include inchworms, world’s greatest stretch, deep lunge opens. 2–3 rounds. → SPP: add mild loaded mobility (e.g. goblet squat hold, elevated Cossack stretch).

### upper back: 4

- `upper_back_tightness_foam_roll_thoracic_extension`: Foam Roll Thoracic Extension; needs_review; GPP: Restore upper spine mobility → TAPER: Maintain posture prep
- `upper_back_tightness_wall_slides_with_chin_tuck`: Wall Slides with Chin Tuck; needs_review; GPP: Improve scapular rhythm → TAPER: Use pre-warmup
- `upper_back_tightness_active_thread_the_needle`: Active Thread the Needle; needs_review; SPP: Mobilize spine actively → TAPER: Maintain with low CNS drain
- `upper_back_tightness_band_assisted_overhead_reach`: Band-Assisted Overhead Reach; needs_review; SPP: Lengthen lat and upper back tissue → TAPER: Short reps only

### wrist: 6

- `wrist_tightness_flexor_stretch_palm_up_wall`: Flexor Stretch (Palm Up, Wall); needs_review; GPP: Open anterior wrist line → TAPER: Maintain mobility pre-session
- `wrist_tightness_extensor_stretch_palm_down`: Extensor Stretch (Palm Down); needs_review; GPP: Release posterior chain → TAPER: Keep free before sparring
- `wrist_tightness_finger_extension_stretch_elastic`: Finger Extension Stretch (Elastic); needs_review; SPP: Restore finger-wrist glide → TAPER: Short holds pre-session
- `wrist_tightness_resisted_wrist_flexor_sweep`: Resisted Wrist Flexor Sweep; needs_review; SPP: Maintain open tissue → TAPER: Light activation before fight
- `wrist_tightness_four_point_rock_backs_wrist_extension`: Four-Point Rock Backs (Wrist Extension); needs_review; GPP: Open anterior wrist → TAPER: Maintain contact tolerance
- `wrist_tightness_massage_ball_wrist_sweep`: Massage Ball Wrist Sweep; needs_review; GPP: Release fascia tension → TAPER: Short bursts for neural calm

## stiffness: 68 drills

### biceps: 2

- `bicep_stiffness_stick_shoulder_dislocates`: Stick Shoulder Dislocates; needs_review; GPP: Restore anterior line range → TAPER: Maintain freedom under no load
- `bicep_stiffness_standing_arm_opener_wall_anchor`: Standing Arm Opener (Wall Anchor); needs_review; GPP: Reset capsule glide → TAPER: Use for daily ROM preservation

### chest: 2

- `chest_stiffness_pec_minor_doorway_stretch`: Pec Minor Doorway Stretch; needs_review; SPP: Mobilize under control → TAPER: Sustain mobility for upper-body rhythm
- `chest_stiffness_band_pull_apart_with_pause`: Band Pull-Apart with Pause; needs_review; SPP: Reinforce scapular glide → TAPER: Reduce tightness without overworking

### elbow: 2

- `elbow_stiffness_active_elbow_flexion_extension_with_dowel`: Active Elbow Flexion/Extension with Dowel; needs_review; GPP: Restore joint rhythm → SPP: Reinforce ROM under light resistance
- `elbow_stiffness_wrist_to_shoulder_slides_on_wall`: Wrist-to-Shoulder Slides on Wall; needs_review; GPP: Coordinate upper limb motion → SPP: Add tempo or band

### eye: 2

- `eye_stiffness_eye_tracking_figure_8_pattern`: Eye Tracking: Figure 8 Pattern; needs_review; GPP: Improve orbital fluidity → TAPER: Use as low-CNS warmup
- `eye_stiffness_360_gaze_anchor_drill`: 360° Gaze Anchor Drill; needs_review; GPP: Expand peripheral control → TAPER: Maintain range without visual strain

### face: 2

- `face_stiffness_facial_cars_controlled_articular_rotations`: Facial CARs (Controlled Articular Rotations); needs_review; GPP: Re-engage multi-directional facial motor control → TAPER: Sharpen awareness pre-fight
- `face_stiffness_resistance_band_jaw_pull_facial_hold`: Resistance Band Jaw-Pull + Facial Hold; needs_review; GPP: Activate jaw-to-face chain → TAPER: Integrate under light spar stress

### fingers: 4

- `fingers_stiffness_warm_water_finger_mobility`: Warm Water Finger Mobility; needs_review; SPP: Loosen before drill → TAPER: Use pre-fight as warm-up primer
- `fingers_stiffness_finger_slide_along_table_edge`: Finger Slide Along Table Edge; needs_review; SPP: Gentle full-range extension → TAPER: Maintain motion with control
- `fingers_stiffness_finger_flossing_rubber_band_curl`: Finger Flossing (Rubber Band + Curl); needs_review; SPP: Mobilize soft tissue glide → TAPER: Light warmup integration
- `fingers_stiffness_open_close_rapid_cycles`: Open-Close Rapid Cycles; needs_review; SPP: Sharpen neural speed → TAPER: Light pulse drills before mitts

### forearm: 4

- `forearm_stiffness_controlled_wrist_cars`: Controlled Wrist CARs; needs_review; GPP: Restore capsule glide → SPP: Add banded distraction or control
- `forearm_stiffness_wrist_wave_mobility_stick_roll`: Wrist Wave Mobility (Stick Roll); needs_review; GPP: Coordinate full wrist path → SPP: Add tempo or pause
- `forearm_stiffness_banded_forearm_floss`: Banded Forearm Floss; needs_review; GPP: Restore soft tissue glide → SPP: Maintain pliability under stress
- `forearm_stiffness_forearm_twists_with_light_plate`: Forearm Twists with Light Plate; needs_review; GPP: Mobilize grip rotation → SPP: Add duration and load

### glute: 2

- `glutes_stiffness_90_90_hip_rotations`: 90/90 Hip Rotations; needs_review; GPP: Mobilize internal/external rotation → SPP: Apply tempo under control
- `glutes_stiffness_elevated_pigeon_stretch`: Elevated Pigeon Stretch; needs_review; GPP: Deep stretch glute max → SPP: Progress to band-assisted flow

### groin: 4

- `groin_stiffness_sumo_pulse_squats`: Sumo Pulse Squats; needs_review; GPP: Mobilize deep groin tissue → SPP: Load pattern gradually
- `groin_stiffness_wide_stance_rdl_with_pause`: Wide Stance RDL with Pause; needs_review; GPP: Lengthen adductors → SPP: Add eccentric load to deepen range
- `groin_stiffness_standing_groin_mobilization_band_pull`: Standing Groin Mobilization (Band Pull); needs_review; SPP: Reestablish active end-range → TAPER: Maintain feel without load
- `groin_stiffness_pulse_cossack_holds`: Pulse Cossack Holds; needs_review; SPP: Build capacity through tight angles → TAPER: Lower reps pre-comp

### hand: 4

- `hand_stiffness_tendon_gliding_series_hook_straight_fist`: Tendon Gliding Series (Hook, Straight, Fist); needs_review; GPP: Free tendon sheaths → SPP: Add volume and banded resistance
- `hand_stiffness_ball_rolling_under_palm`: Ball Rolling Under Palm; needs_review; GPP: Stimulate fascia release → SPP: Control slow reps under pressure
- `hand_stiffness_hand_wave_mobilization_palm_up_down`: Hand Wave Mobilization (Palm Up/Down); needs_review; GPP: Restore joint glide control → SPP: Progress to band-assisted flow
- `hand_stiffness_finger_fan_outs_on_table`: Finger Fan-Outs on Table; needs_review; GPP: Improve soft tissue glide → SPP: Add tempo + finger spread control

### jaw: 4

- `jaw_stiffness_passive_jaw_drops_guided_with_hand`: Passive Jaw Drops (Guided with Hand); needs_review; GPP: Restore range into opening → SPP: Build slow eccentric return control
- `jaw_stiffness_mirror_controlled_chewing_motion_drill`: Mirror-Controlled Chewing Motion Drill; needs_review; GPP: Reinforce symmetrical control → SPP: Apply in guard scenarios with tension
- `jaw_stiffness_open_hold_release_protocol`: Open-Hold-Release Protocol; needs_review; SPP: Challenge end-range with hold → TAPER: Reduce effort, maintain pattern
- `jaw_stiffness_tongue_circle_control_against_palate`: Tongue Circle Control (Against Palate); needs_review; SPP: Guide mandible path with tongue pressure → TAPER: Maintain control while minimizing fatigue

### lower back: 4

- `lower_back_stiffness_glute_wall_press_iso`: Glute Wall Press (Iso); needs_review; SPP: Rebuild posterior chain → TAPER: Prime activation
- `lower_back_stiffness_standing_band_pull_throughs`: Standing Band Pull-Throughs; needs_review; SPP: Load hip hinge → TAPER: Keep low volume
- `lower_back_stiffness_cat_cow_with_deep_breathing`: Cat-Cow with Deep Breathing; needs_review; GPP: Restore spinal rhythm → SPP: Improve active control
- `lower_back_stiffness_jefferson_curl_light_db`: Jefferson Curl (Light DB); needs_review; GPP: Train loaded articulation → SPP: Extend ROM with tempo

### neck: 4

- `neck_stiffness_neck_cars_controlled_articular_rotations`: Neck CARs (Controlled Articular Rotations); needs_review; GPP: Expand multi-directional range → SPP: Integrate slow resistance patterns
- `neck_stiffness_partner_assisted_neck_mobility`: Partner-Assisted Neck Mobility; needs_review; GPP: Restore safety in end ranges → SPP: Add light resistance or timed holds
- `neck_stiffness_gentle_neck_side_tilts_passive_stretch`: Gentle Neck Side Tilts (Passive Stretch); needs_review; TAPER: Restore lateral mobility with zero CNS cost
- `neck_stiffness_trap_bar_hang_neck_relaxation`: Trap Bar Hang & Neck Relaxation; needs_review; TAPER: Passive lengthening of cervical chain under light traction

### obliques: 6

- `obliques_stiffness_side_bridge_with_top_leg_lift`: Side Bridge with Top Leg Lift; needs_review; SPP: Add complexity → TAPER: Reduce hold time, keep activation
- `obliques_stiffness_seated_banded_twists`: Seated Banded Twists; needs_review; SPP: Train low-velocity control → TAPER: Use quick sets pre-workout
- `obliques_stiffness_seated_lateral_flexion_holds`: Seated Lateral Flexion Holds; needs_review; GPP: Restore lateral range → SPP: Increase hold duration under band load
- `obliques_stiffness_banded_lateral_step_trunk_rotation`: Banded Lateral Step + Trunk Rotation; needs_review; GPP: Reintegrate motion pattern → SPP: Load diagonal plane safely
- `obliques_stiffness_wall_lat_oblique_opener`: Wall Lat + Oblique Opener; needs_review; SPP: Restore range in side lines → TAPER: Use as pre-session opener
- `obliques_stiffness_seated_banded_overhead_reach`: Seated Banded Overhead Reach; needs_review; SPP: Isolate lateral lines safely → TAPER: Maintain length under fatigue

### shoulder: 4

- `shoulder_stiffness_pvc_shoulder_pass_throughs`: PVC Shoulder Pass-Throughs; needs_review; GPP: Mobilize anterior and lateral lines → SPP: Increase speed and range
- `shoulder_stiffness_banded_internal_rotations`: Banded Internal Rotations; needs_review; GPP: Free up subscap/tendon → SPP: Add tempo resistance
- `shoulder_stiffness_pvc_pass_throughs`: PVC Pass-Throughs; needs_review; GPP: Open shoulder capsule and anterior chain
- `shoulder_stiffness_wall_slides_with_band`: Wall Slides with Band; needs_review; SPP: Reinforce upward rotation through serratus (posterior chain)

### toe: 2

- `toe_stiffness_toe_cars_controlled_articular_rotations`: Toe CARs (Controlled Articular Rotations); needs_review; GPP: Rebuild capsule range → TAPER: Maintain full ROM pre-fight
- `toe_stiffness_band_toe_pulls_end_range`: Band Toe Pulls – End Range; needs_review; GPP: Control full motion → TAPER: Reinforce control under fatigue

### triceps: 2

- `triceps_stiffness_wall_slides_overhead_elbow_flexed`: Wall Slides (Overhead Elbow Flexed); needs_review; GPP: Mobilize long head → TAPER: Maintain overhead position
- `triceps_stiffness_band_elbow_opener`: Band Elbow Opener; needs_review; GPP: Target posterior arm length → TAPER: Keep end range

### unspecified: 6

- `unspecified_stiffness_loaded_cars_controlled_articular_rotations`: Loaded CARs (Controlled Articular Rotations); needs_review; Strengthen joint control. 3 reps per direction, per joint.
- `unspecified_stiffness_breath_guided_dynamic_stretch_flow`: Breath-Guided Dynamic Stretch Flow; needs_review; Mobility tied to exhale. Repeat sequence x3 rounds full body.
- `unspecified_stiffness_active_range_expansion_with_isometrics`: Active Range Expansion with Isometrics; needs_review; Contract-relax against resistance (e.g. doorway press, glute bridge hold). 3x20s. → SPP: build into controlled eccentrics or flowing mobility reps.
- `unspecified_stiffness_loaded_mobility_toolwork`: Loaded Mobility Toolwork; needs_review; Massage gun or lacrosse ball across the stuck tissue pre-movement. → SPP: replace with movement-based mobility under low load.
- `unspecified_stiffness_active_mobility_circuits_full_body_or_region_specific`: Active Mobility Circuits (Full Body or Region-Specific); needs_review; Mobilize through dynamic movement. Emphasize rhythmic motion, not static stretching.
- `unspecified_stiffness_heat_then_move_protocol_e_g_hot_pack_flow`: Heat-then-Move Protocol (e.g., Hot Pack + Flow); needs_review; Apply localized heat for 10 min, then transition into controlled movement or CARs to expand usable range.

### upper back: 2

- `upper_back_stiffness_wall_leaning_thoracic_opener`: Wall-Leaning Thoracic Opener; needs_review; GPP: Isolate T-spine articulation → SPP: Add controlled deep breath holds
- `upper_back_stiffness_quadruped_rockbacks_with_rotation`: Quadruped Rockbacks with Rotation; needs_review; GPP: Restore lateral rotation → SPP: Add pause or band tension

### wrist: 6

- `wrist_stiffness_wrist_cars`: Wrist CARs; needs_review; GPP: Restore capsule glide → SPP: Add band for resistance
- `wrist_stiffness_stick_roll_wrist_flex_ext`: Stick Roll Wrist Flex/Ext; needs_review; GPP: Mobilize fascial line → SPP: Train control under load
- `wrist_stiffness_theraband_wrist_abduction_adduction`: Theraband Wrist Abduction/Adduction; needs_review; SPP: Load rarely used axes → TAPER: Short reps priming
- `wrist_stiffness_palm_march_wrist_stretch`: Palm-March Wrist Stretch; needs_review; SPP: Enhance flexor-chain glide → TAPER: Reset under no stress
- `wrist_stiffness_wrist_cars_controlled_articular_rotations`: Wrist CARs (Controlled Articular Rotations); needs_review; GPP: Reinforce capsule control → SPP: Add tempo to fluid motion
- `wrist_stiffness_wrist_slides_on_wall`: Wrist Slides on Wall; needs_review; GPP: Train straight-line control → SPP: Add band or incline

## swelling: 44 drills

### ankle: 2

- `ankle_swelling_elevated_ankle_pumps`: Elevated Ankle Pumps; needs_review; TAPER: Gentle symptom-limited movement → TAPER: Use in cooldown to reduce flare
- `ankle_swelling_wall_ankle_circles_no_load`: Wall Ankle Circles (No Load); needs_review; TAPER: Gentle ROM recovery → TAPER: Keep joint active under zero stress

### biceps: 2

- `bicep_swelling_arm_elevation_with_active_wrist_pumps`: Arm Elevation with Active Wrist Pumps; needs_review; TAPER: Promote drainage via venous return
- `bicep_swelling_forearm_supination_pronation_waves`: Forearm Supination–Pronation Waves; needs_review; TAPER: Gentle flush through elbow–bicep track

### chest: 2

- `chest_swelling_open_chain_arm_circles`: Open Chain Arm Circles; needs_review; TAPER: Promote blood flow without resistance
- `chest_swelling_wall_slide_pec_activation`: Wall Slide Pec Activation; needs_review; TAPER: Gentle prep before upper-body sessions

### elbow: 2

- `elbow_swelling_overhead_elbow_pumps_band_assisted`: Overhead Elbow Pumps (Band-Assisted); needs_review; TAPER: Flush inflammation with passive motion
- `elbow_swelling_compression_wrap_elevation_drill`: Compression Wrap + Elevation Drill; needs_review; TAPER: Reduce pooling and boost blood flow pre-fight

### face: 4

- `face_swelling_lymphatic_drainage_sweep_jaw_to_temple`: Lymphatic Drainage Sweep (Jaw to Temple); needs_review; GPP: Promote drainage and facial decompression → TAPER: Keep fluid balance pre-weigh-in
- `face_swelling_cold_compression_wrap_full_face`: Cold Compression Wrap (Full Face); needs_review; GPP: Reduce acute swelling → TAPER: Flush inflammation without nervous system drag
- `face_swelling_facial_gua_sha_scrape_jaw_to_orbital`: Facial Gua Sha Scrape (Jaw to Orbital); needs_review; SPP: Promote fluid clearance with contour → TAPER: Flush pre-fight congestion
- `face_swelling_alternating_ice_heat_face_wraps`: Alternating Ice + Heat (Face Wraps); needs_review; SPP: Stimulate circulation and reset nerves → TAPER: Prevent chronic inflammation

### fingers: 2

- `fingers_swelling_elevated_finger_pumps`: Elevated Finger Pumps; needs_review; TAPER: Drain excess fluid → Repeat in between spar rounds
- `fingers_swelling_cold_water_soak_with_active_motion`: Cold-Water Soak with Active Motion; needs_review; TAPER: Reduce swelling while preserving dexterity

### forearm: 2

- `forearm_swelling_elevated_wrist_pumps`: Elevated Wrist Pumps; needs_review; TAPER: Flush residual fluid with elevation and pulse
- `forearm_swelling_gentle_finger_flicks`: Gentle Finger Flicks; needs_review; TAPER: Promote drainage while keeping grip awake

### glute: 2

- `glutes_swelling_elevated_legs_with_deep_breathing`: Elevated Legs with Deep Breathing; needs_review; TAPER: Gentle low-load movement for perceived stiffness
- `glutes_swelling_wall_adducted_iso_with_glute_squeeze`: Wall-Adducted Iso with Glute Squeeze; needs_review; TAPER: Maintain slight tension without CNS load

### groin: 2

- `groin_swelling_leg_elevation_with_diaphragmatic_breathing`: Leg Elevation with Diaphragmatic Breathing; needs_review; TAPER: Reduce groin fluid pressure → Downregulate nervous system
- `groin_swelling_wall_adducted_iso_hold`: Wall-Adducted Iso Hold; needs_review; TAPER: Hold light activation without strain to maintain tone

### hand: 2

- `hand_swelling_wrist_elevation_with_passive_opens`: Wrist Elevation with Passive Opens; needs_review; GPP: Drain fluid while restoring motion → TAPER: Keep inflammation low under travel/fight prep
- `hand_swelling_open_close_fists_elevated`: Open-Close Fists (Elevated); needs_review; GPP: Pump lymph manually → TAPER: Maintain circulation

### heel: 2

- `heel_swelling_wall_calf_stretch_straight_leg`: Wall Calf Stretch (Straight Leg); needs_review; TAPER: Drain posterior tightness → TAPER: Restore range pre-fight
- `heel_swelling_elevated_heel_pumps`: Elevated Heel Pumps; needs_review; TAPER: Promote circulation → TAPER: Use between drills or post-session

### jaw: 2

- `jaw_swelling_cold_jaw_glide_with_finger_guide`: Cold Jaw Glide with Finger Guide; needs_review; TAPER: Low-load symptom-limited movement
- `jaw_swelling_gentle_manual_drainage_lymph_sweep_down_jawline`: Gentle Manual Drainage (Lymph Sweep Down Jawline); needs_review; TAPER: Clear residual fluid and minimize puffiness pre-fight

### lower back: 2

- `lower_back_swelling_90_90_breathing_with_feet_elevated`: 90/90 Breathing with Feet Elevated; needs_review; TAPER: Drain pressure via parasympathetic tilt
- `lower_back_swelling_cat_cow_flow_slow_tempo`: Cat-Cow Flow (Slow Tempo); needs_review; TAPER: Restore motion with low CNS load

### neck: 2

- `neck_swelling_elevated_neck_drainage_positioning`: Elevated Neck Drainage Positioning; needs_review; GPP: Passive drain setup → TAPER: Combine with light tilts to reduce fluid
- `neck_swelling_neck_massage_with_ball_cervical_line`: Neck Massage with Ball (Cervical Line); needs_review; GPP: Gentle mobility exposure → TAPER: Symptom-limited recovery work

### obliques: 2

- `obliques_swelling_90_90_breathing_with_lateral_expansion`: 90/90 Breathing with Lateral Expansion; needs_review; TAPER: Encourage oblique drainage and reset breathing
- `obliques_swelling_copenhagen_iso_short_lever`: Copenhagen Iso (Short Lever); needs_review; TAPER: Light trunk bracing without full trunk strain

### shoulder: 4

- `shoulder_swelling_pendulum_circles`: Pendulum Circles; needs_review; TAPER: Drain lymph without active load
- `shoulder_swelling_passive_overhead_stick_stretch`: Passive Overhead Stick Stretch; needs_review; TAPER: Elevation with decompression (anterior deltoid)
- `shoulder_swelling_passive_arm_circles`: Passive Arm Circles; needs_review; TAPER: Promote blood flow and lymph drainage
- `shoulder_swelling_band_traction_inferior_glide`: Band Traction – Inferior Glide; needs_review; TAPER: Create space in GH joint and reduce pressure

### triceps: 2

- `triceps_swelling_elevated_arm_pulses_palm_down`: Elevated Arm Pulses (Palm Down); needs_review; GPP: Pump lymph through posterior arm → TAPER: Maintain tone with minimal CNS load
- `triceps_swelling_massage_gun_sweep_posterior_arm`: Massage Gun Sweep – Posterior Arm; needs_review; GPP: Flush congestion from distal insertion → TAPER: Target medial head flare

### unspecified: 2

- `unspecified_swelling_compression_wrap_with_mobility_flow`: Compression Wrap with Mobility Flow; needs_review; Apply compression bandage, then perform gentle mobility drills to reduce swelling without provoking flare-up.
- `unspecified_swelling_limb_elevation_isometric_squeeze`: Limb Elevation + Isometric Squeeze; needs_review; Elevate the limb above heart level. Perform light squeezes or quad/glute sets to stimulate fluid return.

### upper back: 2

- `upper_back_swelling_arm_elevation_wall_slides`: Arm Elevation Wall Slides; needs_review; TAPER: Gentle post-spar recovery work
- `upper_back_swelling_foam_rolling_vertical_sweep`: Foam Rolling – Vertical Sweep; needs_review; TAPER: Reset inflammation without pressure

### wrist: 2

- `wrist_swelling_elevated_wrist_pumps`: Elevated Wrist Pumps; needs_review; TAPER: Drain inflammation pre-fight
- `wrist_swelling_gentle_wrist_circles_slow`: Gentle Wrist Circles (Slow); needs_review; TAPER: Maintain mobility without strain

## Duplicate names across exact types/regions

- `shin_tightness_seated_anterior_shin_stretch`, `shin_tightness_seated_anterior_shin_stretch_2`
- `shin_tightness_lacrosse_ball_glide_tibialis`, `shin_tightness_lacrosse_ball_glide_tibialis_2`
- `shin_pain_heel_walks`, `shin_pain_heel_walks_2`
- `shin_pain_isometric_toe_lift_holds`, `shin_pain_isometric_toe_lift_holds_2`
- `calf_tightness_wall_calf_stretch_bent_knee`, `calf_tightness_wall_calf_stretch_bent_knee_2`
- `calf_tightness_massage_gun_sweep_soleus_line`, `calf_tightness_massage_gun_sweep_soleus_line_2`
- `achilles_pain_isometric_holds_in_tip_toe`, `achilles_pain_isometric_holds_in_tip_toe_2`
- `achilles_pain_banded_heel_push_with_hold`, `achilles_pain_banded_heel_push_with_hold_2`
- `knee_pain_terminal_knee_extensions_tkes`, `knee_pain_terminal_knee_extensions_tkes_2`
- `knee_pain_massage_gun_quad_sweep_to_patella`, `knee_pain_massage_gun_quad_sweep_to_patella_2`
- `knee_tightness_quad_hip_flexor_stretch`, `knee_tightness_quad_hip_flexor_stretch_2`
- `knee_tightness_massage_gun_rectus_line`, `knee_tightness_massage_gun_rectus_line_2`
- `lower_back_tightness_child_s_pose_with_side_reach`, `lower_back_tightness_child_s_pose_with_side_reach_2`
- `lower_back_tightness_massage_gun_lumbar_sweep`, `lower_back_tightness_massage_gun_lumbar_sweep_2`
- `lower_back_pain_supine_90_90_breathing`, `lower_back_pain_supine_90_90_breathing_2`
- `forearm_swelling_elevated_wrist_pumps`, `wrist_swelling_elevated_wrist_pumps`
