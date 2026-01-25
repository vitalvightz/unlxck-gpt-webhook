#!/usr/bin/env python3
"""
Validation script to verify mechanism tags are correctly applied.

This script:
1. Loads the updated exercise bank
2. Displays exercises grouped by mechanism tag type
3. Provides statistics and spot-check examples
"""

import json
import sys
from pathlib import Path
from collections import defaultdict

# Add the parent directory to the path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fightcamp.injury_filtering import _infer_mechanism_tags_from_name


def validate_mechanism_tags(exercise_bank_path: str):
    """Validate mechanism tags in the exercise bank."""
    with open(exercise_bank_path, 'r', encoding='utf-8') as f:
        exercises = json.load(f)
    
    # Group exercises by mechanism tag
    mech_tag_groups = defaultdict(list)
    exercises_with_mech = []
    exercises_without_mech = []
    
    for ex in exercises:
        name = ex.get('name', '')
        tags = set(ex.get('tags', []))
        mech_tags = {t for t in tags if t.startswith('mech_')}
        
        if mech_tags:
            exercises_with_mech.append(ex)
            for tag in mech_tags:
                mech_tag_groups[tag].append(name)
        else:
            exercises_without_mech.append(ex)
    
    # Print statistics
    print("=" * 80)
    print("MECHANISM TAG VALIDATION REPORT")
    print("=" * 80)
    print(f"\nTotal exercises: {len(exercises)}")
    print(f"Exercises with mechanism tags: {len(exercises_with_mech)}")
    print(f"Exercises without mechanism tags: {len(exercises_without_mech)}")
    
    # Display mechanism tag distribution
    print("\n" + "=" * 80)
    print("MECHANISM TAG DISTRIBUTION")
    print("=" * 80)
    
    for tag in sorted(mech_tag_groups.keys()):
        count = len(mech_tag_groups[tag])
        print(f"\n{tag}: {count} exercises")
        # Show first 3 examples
        for name in mech_tag_groups[tag][:3]:
            print(f"  - {name}")
        if count > 3:
            print(f"  ... and {count - 3} more")
    
    # Velocity/Impact Category
    print("\n" + "=" * 80)
    print("VELOCITY/IMPACT MECHANISM TAGS")
    print("=" * 80)
    velocity_tags = ['mech_max_velocity', 'mech_acceleration', 'mech_deceleration',
                     'mech_change_of_direction', 'mech_landing_impact', 'mech_reactive_rebound']
    for tag in velocity_tags:
        if tag in mech_tag_groups:
            print(f"{tag}: {len(mech_tag_groups[tag])} exercises")
    
    # Trunk Mechanism Tags
    print("\n" + "=" * 80)
    print("TRUNK MECHANISM TAGS")
    print("=" * 80)
    trunk_tags = ['mech_rotation_high_torque', 'mech_anti_rotation', 'mech_axial_heavy']
    for tag in trunk_tags:
        if tag in mech_tag_groups:
            print(f"{tag}: {len(mech_tag_groups[tag])} exercises")
    
    # Lower Body Mechanism Tags
    print("\n" + "=" * 80)
    print("LOWER BODY MECHANISM TAGS")
    print("=" * 80)
    lower_tags = ['mech_hinge_eccentric', 'mech_hinge_isometric', 'mech_squat_deep',
                  'mech_knee_over_toe', 'mech_lateral_shift']
    for tag in lower_tags:
        if tag in mech_tag_groups:
            print(f"{tag}: {len(mech_tag_groups[tag])} exercises")
    
    # Upper Body Mechanism Tags
    print("\n" + "=" * 80)
    print("UPPER BODY MECHANISM TAGS")
    print("=" * 80)
    upper_tags = ['mech_overhead_dynamic', 'mech_overhead_static', 'mech_horizontal_push',
                  'mech_horizontal_pull', 'mech_vertical_pull_heavy']
    for tag in upper_tags:
        if tag in mech_tag_groups:
            print(f"{tag}: {len(mech_tag_groups[tag])} exercises")
    
    # Grip/Carry Mechanism Tags
    print("\n" + "=" * 80)
    print("GRIP/CARRY MECHANISM TAGS")
    print("=" * 80)
    grip_tags = ['mech_grip_intensive', 'mech_grip_static', 'mech_loaded_carry']
    for tag in grip_tags:
        if tag in mech_tag_groups:
            print(f"{tag}: {len(mech_tag_groups[tag])} exercises")
    
    # Sample exercises without mechanism tags
    print("\n" + "=" * 80)
    print("SAMPLE EXERCISES WITHOUT MECHANISM TAGS (First 15)")
    print("=" * 80)
    print("These exercises don't match specific high-risk mechanism patterns,")
    print("which is expected for many general training exercises.")
    print()
    for ex in exercises_without_mech[:15]:
        print(f"- {ex['name']} ({ex.get('category', 'N/A')} / {ex.get('movement', 'N/A')})")
    
    if len(exercises_without_mech) > 15:
        print(f"\n... and {len(exercises_without_mech) - 15} more")
    
    # Validation checks
    print("\n" + "=" * 80)
    print("VALIDATION CHECKS")
    print("=" * 80)
    
    # Check 1: Verify all mechanism tags match inference
    mismatches = []
    for ex in exercises:
        name = ex.get('name', '')
        stored_mech = {t for t in ex.get('tags', []) if t.startswith('mech_')}
        inferred_mech = _infer_mechanism_tags_from_name(name)
        
        if stored_mech != inferred_mech:
            mismatches.append({
                'name': name,
                'stored': stored_mech,
                'inferred': inferred_mech
            })
    
    if mismatches:
        print(f"\n⚠️  Found {len(mismatches)} exercises with tag mismatches:")
        for m in mismatches[:5]:
            print(f"\n  {m['name']}:")
            print(f"    Stored: {m['stored']}")
            print(f"    Inferred: {m['inferred']}")
        if len(mismatches) > 5:
            print(f"\n  ... and {len(mismatches) - 5} more")
    else:
        print("\n✓ All mechanism tags match inference rules")
    
    # Check 2: No duplicate tags
    duplicates = []
    for ex in exercises:
        tags = ex.get('tags', [])
        if len(tags) != len(set(tags)):
            duplicates.append(ex['name'])
    
    if duplicates:
        print(f"\n⚠️  Found {len(duplicates)} exercises with duplicate tags:")
        for name in duplicates[:5]:
            print(f"  - {name}")
    else:
        print("✓ No duplicate tags found")
    
    print("\n" + "=" * 80)
    print("VALIDATION COMPLETE")
    print("=" * 80)


def main():
    """Main entry point."""
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    exercise_bank_path = repo_root / 'data' / 'exercise_bank.json'
    
    if not exercise_bank_path.exists():
        print(f"Error: Exercise bank not found at {exercise_bank_path}")
        sys.exit(1)
    
    validate_mechanism_tags(str(exercise_bank_path))


if __name__ == '__main__':
    main()
