#!/usr/bin/env python3
"""
Script to add mechanism tags (mech_*) to all exercises in exercise_bank.json.

This script:
1. Loads all exercises from the exercise bank
2. Uses the existing _infer_mechanism_tags_from_name function to identify appropriate mechanism tags
3. Merges mechanism tags with existing tags (preserving original tags, no duplication)
4. Writes the updated exercise bank back to the file
"""

import json
import sys
from pathlib import Path

# Add the parent directory to the path so we can import fightcamp modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from fightcamp.injury_filtering import _infer_mechanism_tags_from_name


def add_mechanism_tags_to_exercises(exercise_bank_path: str) -> dict:
    """
    Add mechanism tags to all exercises in the exercise bank.
    
    Returns a dict with statistics about the update.
    """
    # Load the exercise bank
    with open(exercise_bank_path, 'r', encoding='utf-8') as f:
        exercises = json.load(f)
    
    stats = {
        'total': len(exercises),
        'updated': 0,
        'already_had_mech_tags': 0,
        'no_mech_tags_found': 0,
        'tags_added': 0
    }
    
    # Process each exercise
    for exercise in exercises:
        name = exercise.get('name', '')
        existing_tags = set(exercise.get('tags', []))
        
        # Check if already has mechanism tags
        existing_mech_tags = {tag for tag in existing_tags if tag.startswith('mech_')}
        
        # Infer mechanism tags from the exercise name
        inferred_mech_tags = _infer_mechanism_tags_from_name(name)
        
        if not inferred_mech_tags:
            stats['no_mech_tags_found'] += 1
            continue
        
        # Merge with existing tags (no duplicates)
        new_tags = existing_mech_tags | inferred_mech_tags
        
        if existing_mech_tags:
            stats['already_had_mech_tags'] += 1
        
        # Only add tags that weren't already present
        tags_to_add = new_tags - existing_mech_tags
        if tags_to_add:
            # Combine with existing non-mechanism tags
            all_tags = sorted(existing_tags | inferred_mech_tags)
            exercise['tags'] = all_tags
            stats['updated'] += 1
            stats['tags_added'] += len(tags_to_add)
    
    # Write back to file with proper formatting
    with open(exercise_bank_path, 'w', encoding='utf-8') as f:
        json.dump(exercises, f, indent=2, ensure_ascii=False)
        f.write('\n')  # Add trailing newline
    
    return stats


def main():
    """Main entry point for the script."""
    # Determine the path to the exercise bank
    script_dir = Path(__file__).parent
    repo_root = script_dir.parent
    exercise_bank_path = repo_root / 'data' / 'exercise_bank.json'
    
    if not exercise_bank_path.exists():
        print(f"Error: Exercise bank not found at {exercise_bank_path}")
        sys.exit(1)
    
    print(f"Processing exercise bank at: {exercise_bank_path}")
    print("=" * 70)
    
    # Process the exercises
    stats = add_mechanism_tags_to_exercises(str(exercise_bank_path))
    
    # Print statistics
    print(f"\nStatistics:")
    print(f"  Total exercises: {stats['total']}")
    print(f"  Exercises updated: {stats['updated']}")
    print(f"  Exercises already with mech tags: {stats['already_had_mech_tags']}")
    print(f"  Exercises with no mechanism tags found: {stats['no_mech_tags_found']}")
    print(f"  Total mechanism tags added: {stats['tags_added']}")
    print("=" * 70)
    print(f"\n✓ Exercise bank updated successfully!")


if __name__ == '__main__':
    main()
