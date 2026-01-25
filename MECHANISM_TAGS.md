# Mechanism Tag Implementation

## Overview

This document describes the comprehensive mechanism tag system applied to all exercises in `data/exercise_bank.json`. Mechanism tags (`mech_*`) identify injury-relevant biomechanical loading patterns for clinical safety screening and exercise exclusion logic.

## Implementation Summary

**Date**: January 2026
**Coverage**: 228 total exercises, 117 with mechanism tags (51.3%)
**Tags Used**: 21 canonical mechanism tags

All mechanism tags are automatically inferred from exercise names using the approved taxonomy defined in `fightcamp/injury_filtering.py`. The system uses clinical expertise and pattern matching to assign tags based on specific keywords in exercise names.

## Mechanism Tag Taxonomy

### Velocity/Impact Mechanisms (23 exercises)
- `mech_max_velocity` (9): Flying sprints, max speed running, track work
- `mech_acceleration` (2): Drive phase, hill sprints, acceleration work
- `mech_deceleration` (2): Stick landings, braking mechanics
- `mech_change_of_direction` (1): COD drills, pro agility, cutting
- `mech_landing_impact` (4): Depth drops, depth jumps, hard landings
- `mech_reactive_rebound` (5): Pogo hops, ankle hops, reactive work

### Trunk Mechanisms (31 exercises)
- `mech_rotation_high_torque` (15): Sledgehammer, scoop toss, rotational power
- `mech_anti_rotation` (4): Pallof press, anti-rotation drills
- `mech_axial_heavy` (12): Back squat, front squat, overhead press, heavy axial load

### Lower Body Mechanisms (18 exercises)
- `mech_hinge_eccentric` (5): Romanian deadlift, tempo hinges, stiff-leg variations
- `mech_hinge_isometric` (7): Isometric deadlift, rack pull holds
- `mech_squat_deep` (0): Pause squats, ATG squats, deep squat patterns
- `mech_knee_over_toe` (2): Pistol squats, sissy squats, ATG variations
- `mech_lateral_shift` (4): Lateral lunges, cossack squats, skater hops

### Upper Body Mechanisms (25 exercises)
- `mech_overhead_dynamic` (3): Push press, thrusters, snatches, jerks
- `mech_overhead_static` (1): Overhead holds, strict press, Z press
- `mech_horizontal_push` (10): Bench press, push-ups, chest press
- `mech_horizontal_pull` (5): Rows, inverted rows, cable/TRX variations
- `mech_vertical_pull_heavy` (6): Pull-ups, chin-ups, lat pulldowns

### Extremity/Global Load (38 exercises)
- `mech_grip_intensive` (12): Wrist roller, fat grip work, towel variations
- `mech_grip_static` (19): Static holds, dead hangs, isometric holds
- `mech_loaded_carry` (7): Farmers walks, suitcase carry, yoke walks

## How Mechanism Tags Are Used

### 1. Injury Exclusion Logic
Mechanism tags enable the injury filtering system (`fightcamp/injury_filtering.py`) to automatically exclude exercises that pose specific biomechanical risks for injured athletes:

```python
# Example: Athlete with shoulder injury
# System automatically excludes exercises tagged with:
# - mech_overhead_dynamic
# - mech_overhead_static
# - mech_vertical_pull_heavy
```

### 2. Tag Provenance System
The system distinguishes between:
- **Explicit tags**: Manually assigned tags in the original JSON
- **Inferred mechanism tags**: Auto-generated from exercise names

For safety, only explicit tags (or mechanism tags) trigger injury exclusions for exercises with inferred tag sources. This prevents false positives from conservative auto-tagging.

### 3. Clinical Safety Guardrails
Mechanism tags provide physio-grade specificity for identifying exercises that stress particular body regions or movement patterns. This ensures athletes with active injuries avoid exercises that could aggravate their condition.

## Coverage Analysis

### By Exercise Category
- **Upper Body**: 72.7% (24/33 exercises)
- **Lower Body**: 60.6% (43/71 exercises)
- **Locomotion**: 63.6% (7/11 exercises)
- **Grip/Neck**: 80.0% (4/5 exercises)
- **Core**: 50.0% (11/22 exercises)
- **Boxing**: 39.1% (9/23 exercises)

### Exercises Without Mechanism Tags
111 exercises (48.7%) don't have mechanism tags because they don't match specific high-risk biomechanical patterns. This is expected and correct behavior:

- General exercises without specific injury-relevant mechanisms
- Low-risk bodyweight movements
- Recovery and mobility work
- Exercises with non-specific loading patterns

These exercises can still be filtered by other tags (e.g., `explosive`, `high_cns`, `balance`) or by keyword matching in the injury exclusion system.

## Tag Assignment Process

### Automated Inference
All mechanism tags are automatically assigned using the `_infer_mechanism_tags_from_name()` function:

```python
from fightcamp.injury_filtering import _infer_mechanism_tags_from_name

# Example
name = "Romanian Deadlift (RDL)"
tags = _infer_mechanism_tags_from_name(name)
# Returns: {'mech_hinge_eccentric'}
```

### Keyword Matching
The system uses a curated list of keywords for each mechanism tag (see `MECH_KEYWORDS` in `injury_filtering.py`):

```python
# Example: mech_hinge_eccentric matches:
# - "tempo hinge", "slow lower", "stiff leg", "romanian", "rdl", etc.
```

### No Manual Overrides
Mechanism tags are **not** manually edited. They are purely derived from exercise names. This ensures:
- Consistency across all exercises
- Reproducibility of tag assignment
- Easy updates when taxonomy evolves
- No human error in tag assignment

## Validation Tools

### 1. Add Mechanism Tags Script
**Location**: `tools/add_mechanism_tags.py`

Processes all exercises and adds mechanism tags:
```bash
python3 tools/add_mechanism_tags.py
```

### 2. Validation Script
**Location**: `tools/validate_mechanism_tags.py`

Comprehensive validation report showing:
- Tag distribution by category
- Coverage statistics
- Sample exercises for each tag
- Validation checks (duplicates, mismatches)

```bash
python3 tools/validate_mechanism_tags.py
```

### 3. Test Suite
**Location**: `tests/test_mechanism_tags.py`

Automated tests verify correct tag inference:
```bash
python3 -m pytest tests/test_mechanism_tags.py -v
```

## Edge Cases and Design Decisions

### 1. Multiple Mechanism Tags
Some exercises receive multiple mechanism tags when they involve multiple distinct biomechanical patterns:

```python
# Example: "Depth Drop → 5m Sprint"
# Tags: mech_landing_impact, mech_max_velocity
```

This is correct and intentional - both mechanisms are present.

### 2. Contrast Sets
Contrast sets (e.g., "Back Squat → Box Jump") inherit mechanism tags from their components:

```python
# "Back Squat → Box Jump"
# Tags: mech_axial_heavy (from squat component)
```

### 3. Exercise Name Variations
Similar exercises with different names may have different mechanism tags based on their specific implementation:

```python
# "Back Squat" → mech_axial_heavy
# "Trap Bar Deadlift" → No mechanism tag (different loading pattern)
```

### 4. Exclusion Safety
The system errs on the side of safety - if uncertain whether a mechanism applies, the exercise name should include explicit keywords to trigger the appropriate tag. This prevents under-tagging of high-risk movements.

## Maintenance

### Adding New Exercises
New exercises added to `exercise_bank.json` will automatically receive mechanism tags when:
1. The exercise name contains keywords from `MECH_KEYWORDS`
2. The `ensure_tags()` function is called (happens automatically in the injury filtering pipeline)

### Updating the Taxonomy
To add or modify mechanism tags:
1. Update `MECH_KEYWORDS` in `fightcamp/injury_filtering.py`
2. Run `python3 tools/add_mechanism_tags.py` to regenerate tags
3. Run `python3 tools/validate_mechanism_tags.py` to verify
4. Run test suite: `python3 -m pytest tests/test_mechanism_tags.py`

### Version History
- **v1.0 (January 2026)**: Initial comprehensive implementation
  - 228 exercises processed
  - 21 canonical mechanism tags
  - 117 exercises tagged (51.3% coverage)
  - Full taxonomy covering velocity/impact, trunk, lower, upper, extremity, and global/CNS load

## References

- **Injury Filtering Module**: `fightcamp/injury_filtering.py`
- **Tag Provenance Tests**: `tests/test_tag_provenance.py`
- **Mechanism Tag Tests**: `tests/test_mechanism_tags.py`
- **Exercise Bank**: `data/exercise_bank.json`
- **Tag Vocabulary**: `data/tag_vocabulary.json`
