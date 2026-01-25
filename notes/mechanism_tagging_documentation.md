# Mechanism Tag Documentation

## Overview
This document describes the manual clinical tagging process for `mech_*` mechanism tags across the universal GPP strength and style-specific exercise banks. These tags are critical for injury exclusion logic and biomechanical safety auditing.

## Mechanism Tag Taxonomy

### Lower Body Mechanisms
- **mech_lower_squat**: Knee-dominant squat patterns (front squat, back squat, goblet squat)
- **mech_lower_hip_hinge**: Hip-dominant hinge patterns (deadlifts, RDLs, good mornings, sled work)
- **mech_lower_lunge**: Single-leg lunge patterns (split squats, walking lunges, reverse lunges)
- **mech_lower_lateral**: Lateral movement patterns (side lunges, lateral shuffles, cossacks)
- **mech_lower_jump**: Jumping movements (box jumps, broad jumps, vertical jumps)

### Upper Body Mechanisms
- **mech_upper_press**: Pressing patterns (bench press, push-ups, dips)
- **mech_upper_pull**: Pulling patterns (pull-ups, rows, lat pulldowns)
- **mech_shoulder_overhead**: Overhead shoulder loading (overhead press, snatches, overhead carries)
- **mech_upper_carry**: Upper body loaded carries (farmer's carries, suitcase carries)

### Trunk/Core Mechanisms
- **mech_trunk_stability**: Core stability and anti-movement patterns (all compound movements)
- **mech_trunk_rotation**: Rotational trunk patterns (wood chops, landmine twists, sledgehammer slams)
- **mech_trunk_flexion**: Trunk flexion patterns (med ball slams, sit-ups, ab wheel)

### Grip Mechanisms
- **mech_grip_support**: Grip endurance/support (deadlifts, carries, pull-ups)
- **mech_grip_crush**: Grip crushing/intensity (plate pinches, wrist rollers, heavy hangs)

### Dynamic/Ballistic Mechanisms
- **mech_ballistic**: Ballistic/explosive movements (swings, slams, throws)
- **mech_reactive**: Reactive/plyometric patterns (depth jumps, reactive hops)
- **mech_landing_impact**: Landing impact stress (depth jumps, box jumps)
- **mech_deceleration**: Deceleration patterns (stick landings, change of direction)
- **mech_max_velocity**: Maximum velocity running (sprints, flying runs)

### Systemic Load
- **mech_cns_high**: High CNS demand movements (heavy Olympic lifts, max effort throws)
- **mech_systemic_fatigue**: High systemic fatigue load (thrusters, sled pushes, heavy conditioning)

## Tagging Principles

### Clinical Safety Rationale
1. **Comprehensive Coverage**: Every exercise receives all appropriate mechanism tags based on biomechanical analysis
2. **Injury Risk Alignment**: Tags align with injury exclusion rules to enable precise filtering
3. **Movement Pattern Focus**: Tags describe the movement pattern, not just the muscle groups
4. **Compound Awareness**: Most exercises include `mech_trunk_stability` as compound movements require core engagement

### Tag Application Guidelines

#### When to Apply Multiple Tags
- **Compound Movements**: Apply all relevant mechanisms (e.g., Thruster = squat + press + overhead)
- **Dynamic Movements**: Include both pattern and quality tags (e.g., Jumping Lunge = lunge + jump + ballistic + reactive + landing)
- **Complex Movements**: Tag all phases of movement (e.g., Turkish Get-Up = overhead + rotation + stability + grip)

#### Common Tag Combinations
- All squats: `mech_lower_squat` + `mech_trunk_stability`
- All deadlifts/hinges: `mech_lower_hip_hinge` + `mech_trunk_stability` + `mech_grip_support`
- All presses: `mech_upper_press` + `mech_trunk_stability`
- All pulls: `mech_upper_pull` + `mech_trunk_stability` + `mech_grip_support`
- Overhead work: `mech_shoulder_overhead` + relevant press/carry/stability tags
- Ballistic movements: `mech_ballistic` + base pattern + `mech_cns_high` (if appropriate)

## Exercise-by-Exercise Rationale

### Universal GPP Strength (12 exercises)

#### 1. Barbell Back Squat
- **Tags**: `mech_lower_squat`, `mech_trunk_stability`
- **Rationale**: Classic knee-dominant squat pattern with high trunk stability demand
- **Injury Considerations**: Excluded for knee, quad, and lower back injuries

#### 2. Trap Bar Deadlift
- **Tags**: `mech_lower_hip_hinge`, `mech_trunk_stability`, `mech_grip_support`
- **Rationale**: Hip-dominant hinge with moderate trunk loading and grip demand
- **Injury Considerations**: Excluded for lower back, SI joint, hamstring, and glute injuries

#### 3. Push-Up or Bench Press
- **Tags**: `mech_upper_press`, `mech_trunk_stability`
- **Rationale**: Horizontal pressing pattern requiring trunk stability (especially push-ups)
- **Injury Considerations**: Excluded for chest, shoulder, elbow, and wrist injuries

#### 4. Barbell or DB Overhead Press
- **Tags**: `mech_upper_press`, `mech_shoulder_overhead`, `mech_trunk_stability`
- **Rationale**: Vertical pressing with overhead shoulder loading and core bracing
- **Injury Considerations**: Excluded for shoulder injuries; double-protected via press + overhead tags

#### 5. DB Split Squat
- **Tags**: `mech_lower_lunge`, `mech_trunk_stability`
- **Rationale**: Single-leg lunge pattern with balance and stability demands
- **Injury Considerations**: Excluded for hip flexor and quad injuries

#### 6. Pull-Up or Inverted Row
- **Tags**: `mech_upper_pull`, `mech_grip_support`, `mech_trunk_stability`
- **Rationale**: Vertical/horizontal pulling with grip endurance and anti-extension
- **Injury Considerations**: Excluded for shoulder, forearm, and hand injuries

#### 7. Sled Push or Drag
- **Tags**: `mech_lower_hip_hinge`, `mech_trunk_stability`, `mech_systemic_fatigue`
- **Rationale**: Hip-dominant push/pull with high metabolic cost
- **Injury Considerations**: Excluded for lower back and SI joint injuries

#### 8. Trap Bar or DB Shrugs
- **Tags**: `mech_grip_support`, `mech_trunk_stability`
- **Rationale**: Isometric grip hold with trunk bracing
- **Injury Considerations**: Excluded for forearm and hand injuries

#### 9. Neck Harness Isometrics
- **Tags**: `mech_trunk_stability`
- **Rationale**: Cervical isometric work with neck-specific stability (not a full trunk pattern but uses stability principles)
- **Injury Considerations**: Excluded for neck injuries via keyword matching

#### 10. Landmine Rotations
- **Tags**: `mech_trunk_rotation`, `mech_trunk_stability`
- **Rationale**: Rotational trunk pattern requiring anti-rotation control
- **Injury Considerations**: Safe for most injuries; provides rotational training

#### 11. 90/90 Banded Shoulder CARs
- **Tags**: `mech_trunk_stability`
- **Rationale**: Controlled shoulder mobility with trunk stabilization
- **Injury Considerations**: Safe mobility drill; not excluded for most injuries

#### 12. Low Hurdle Hop (Rhythm Focus)
- **Tags**: `mech_reactive`, `mech_lower_jump`, `mech_landing_impact`
- **Rationale**: Low-intensity plyometric with landing stress and reactive quality
- **Injury Considerations**: Excluded for knee, ankle, and shin injuries via `mech_landing_impact`

### Style-Specific Exercises (16 exercises)

#### 1. Plate Pinch Holds
- **Tags**: `mech_grip_crush`, `mech_grip_support`
- **Rationale**: High-intensity pinch grip with static hold component
- **Injury Considerations**: Excluded for hand and forearm injuries

#### 2. Wrist Roller Extensions
- **Tags**: `mech_grip_crush`, `mech_trunk_stability`
- **Rationale**: Grip crusher via wrist extension with trunk bracing during hold
- **Injury Considerations**: Excluded for forearm and wrist injuries

#### 3. Barbell Thruster
- **Tags**: `mech_lower_squat`, `mech_upper_press`, `mech_shoulder_overhead`, `mech_ballistic`, `mech_cns_high`, `mech_trunk_stability`, `mech_systemic_fatigue`
- **Rationale**: Complex movement combining squat, press, overhead load, explosive quality, high CNS demand
- **Injury Considerations**: Excluded for multiple injuries (knee, shoulder, lower back) via comprehensive tagging

#### 4. Turkish Get-Up
- **Tags**: `mech_shoulder_overhead`, `mech_trunk_stability`, `mech_trunk_rotation`, `mech_grip_support`
- **Rationale**: Complex multi-plane movement with overhead hold, rotational transitions, and grip demand
- **Injury Considerations**: Excluded for shoulder injuries; requires full-body integration

#### 5. Bulgarian Split Squat
- **Tags**: `mech_lower_lunge`, `mech_trunk_stability`
- **Rationale**: Elevated rear-foot lunge variant with stability demand
- **Injury Considerations**: Excluded for hip flexor, quad, and knee injuries

#### 6. Walking Lunges
- **Tags**: `mech_lower_lunge`, `mech_trunk_stability`
- **Rationale**: Dynamic lunge pattern with continuous trunk stabilization
- **Injury Considerations**: Excluded for hip flexor and quad injuries

#### 7. Weighted Pull-Up
- **Tags**: `mech_upper_pull`, `mech_grip_support`, `mech_trunk_stability`
- **Rationale**: Vertical pull with increased grip demand from added load
- **Injury Considerations**: Excluded for shoulder, forearm, and hand injuries

#### 8. Kettlebell Swing
- **Tags**: `mech_lower_hip_hinge`, `mech_ballistic`, `mech_grip_support`, `mech_trunk_stability`
- **Rationale**: Ballistic hip hinge with grip endurance and trunk anti-flexion
- **Injury Considerations**: Excluded for lower back, hamstring, and grip injuries

#### 9. Barbell Landmine Twist
- **Tags**: `mech_trunk_rotation`, `mech_trunk_stability`, `mech_grip_support`
- **Rationale**: Loaded rotational pattern with grip hold and anti-rotation control
- **Injury Considerations**: Safe for most injuries; provides rotational strength

#### 10. Pallof Press
- **Tags**: `mech_trunk_stability`
- **Rationale**: Pure anti-rotation stability drill
- **Injury Considerations**: Safe for all; rehab-friendly

#### 11. Overhead Med Ball Slam
- **Tags**: `mech_shoulder_overhead`, `mech_ballistic`, `mech_trunk_flexion`, `mech_trunk_stability`, `mech_cns_high`
- **Rationale**: Overhead extension to explosive trunk flexion with high CNS demand
- **Injury Considerations**: Excluded for shoulder injuries; high-intensity ballistic work

#### 12. Farmer's Carry
- **Tags**: `mech_grip_support`, `mech_upper_carry`, `mech_trunk_stability`
- **Rationale**: Loaded carry with grip endurance and anti-lateral flexion
- **Injury Considerations**: Excluded for forearm and hand injuries

#### 13. Weighted Sled Push
- **Tags**: `mech_lower_hip_hinge`, `mech_trunk_stability`, `mech_systemic_fatigue`
- **Rationale**: Hip-dominant push with high metabolic demand
- **Injury Considerations**: Excluded for lower back and SI joint injuries

#### 14. Jumping Lunge
- **Tags**: `mech_lower_lunge`, `mech_lower_jump`, `mech_ballistic`, `mech_reactive`, `mech_landing_impact`, `mech_trunk_stability`
- **Rationale**: Plyometric lunge with jump, reactive switch, landing stress, and trunk control
- **Injury Considerations**: Excluded for knee, hip flexor, and ankle injuries via multiple mechanisms

#### 15. Sledgehammer Slam
- **Tags**: `mech_trunk_rotation`, `mech_trunk_flexion`, `mech_grip_support`, `mech_trunk_stability`, `mech_ballistic`
- **Rationale**: Rotational trunk pattern with explosive flexion, grip hold, and ballistic quality
- **Injury Considerations**: Safe for most; provides rotational power training

#### 16. Medicine Ball Slam
- **Tags**: `mech_trunk_flexion`, `mech_ballistic`, `mech_trunk_stability`, `mech_cns_high`
- **Rationale**: Explosive trunk flexion with high CNS demand (non-overhead variant)
- **Injury Considerations**: Excluded for lower back if trunk flexion is banned; high-intensity work

## Validation Results

### Coverage Statistics
- **Universal GPP Strength**: 12 exercises, 27 mech_* tags (avg 2.25 tags/exercise)
- **Style-Specific Exercises**: 16 exercises, 56 mech_* tags (avg 3.5 tags/exercise)
- **Total**: 28 exercises, 83 mech_* tags

### Injury Exclusion Testing
All exercises tested against injury exclusion rules show correct behavior:
- **Positive cases**: Exercises excluded when appropriate (e.g., Trap Bar Deadlift for lower_back)
- **Negative cases**: Exercises not excluded when safe (e.g., Trap Bar Deadlift for shoulder)
- **Multi-mechanism**: Complex movements excluded for multiple injuries (e.g., Thruster for knee, shoulder, back)

## Future Maintenance

### Adding New Exercises
1. Analyze biomechanics and movement patterns
2. Identify primary and secondary mechanisms
3. Apply all appropriate mech_* tags
4. Include `mech_trunk_stability` for compound movements
5. Test against injury exclusion rules
6. Verify no duplicate tags

### Reviewing Existing Tags
1. Re-assess if injury exclusion logic changes
2. Update when new mechanism tags are added to taxonomy
3. Validate against clinical literature
4. Test with real athlete injury profiles

### Quality Assurance
- All exercises must have at least one mech_* tag (except pure mobility/stretching)
- Compound movements should have 2+ mech_* tags
- High-complexity movements (thrusters, TGU) should have 4+ mech_* tags
- No duplicate tags within the same exercise
- JSON validation must pass

---

**Last Updated**: 2026-01-25
**Author**: Clinical Tagging Audit
**Status**: Complete for universal_gpp_strength.json and style_specific_exercises
