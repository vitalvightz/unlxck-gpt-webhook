#!/usr/bin/env python3
"""
Robust and deterministic JSON bank validator for all non-rehab/non-coordination banks.

This tool validates all *.json bank files in /data (excluding rehab*, coordination*, 
and tag_vocabulary.json) for:
- Schema consistency (supports both root list and object with items/data arrays)
- Required keys (name, tags)
- Tag types (tags must be a list of strings)
- Tag vocabulary presence
- Injury exclusion rule coverage (prints safe/blocked counts by ban_tags)

Exit codes:
- 0: All validations passed
- 1: One or more validation failures detected

Usage:
    python tools/validate_banks.py

Example output:
    Discovering banks in /data...
    Found 8 banks to validate.
    
    Loading tag vocabulary from /data/tag_vocabulary.json...
    Tag vocabulary loaded: 190 tags
    
    Loading INJURY_RULES from fightcamp.injury_exclusion_rules...
    INJURY_RULES loaded: 28 regions
    
    ========================================
    Validating: exercise_bank.json
    ========================================
    Schema: root list with 47 entries
    
    Required key validation:
      ✓ All entries have 'name'
      ✓ All entries have 'tags'
      ✓ All 'tags' are lists
      ✓ All tag values are strings
    
    Ban tag coverage for 'head':
      Safe: 47 | Blocked: 0
    Ban tag coverage for 'neck':
      Safe: 47 | Blocked: 0
    ...
    
    Ban tags not found in any bank or tag vocabulary:
      - contact (from region: head)
      - sparring (from region: head)
    
    ========================================
    VALIDATION SUMMARY
    ========================================
    Total banks validated: 8
    Total entries validated: 1234
    ✓ All validations passed
"""

import json
import os
import sys
from pathlib import Path
from collections import defaultdict
from typing import Dict, List, Any, Tuple, Set


# Paths
REPO_ROOT = Path(__file__).parent.parent
DATA_DIR = REPO_ROOT / "data"
TAG_VOCAB_FILE = DATA_DIR / "tag_vocabulary.json"


def discover_banks() -> List[Path]:
    """
    Discover all *.json bank files in /data except those containing:
    - rehab
    - coordination
    - tag_vocabulary.json
    - bank_inferred_tags.json (metadata file)
    - format_* (configuration files)
    - injury_exclusion_map.json (configuration file)
    """
    print(f"Discovering banks in {DATA_DIR}...")
    
    banks = []
    for file_path in sorted(DATA_DIR.glob("*.json")):
        filename = file_path.name.lower()
        
        # Skip excluded files
        if (
            "rehab" in filename 
            or "coordination" in filename 
            or filename == "tag_vocabulary.json"
            or filename == "bank_inferred_tags.json"
            or filename.startswith("format_")
            or filename == "injury_exclusion_map.json"
        ):
            continue
        
        banks.append(file_path)
    
    print(f"Found {len(banks)} banks to validate.\n")
    return banks


def load_tag_vocabulary() -> Set[str]:
    """
    Load tag vocabulary from /data/tag_vocabulary.json.
    Handles both list and object (items/data array) schemas.
    """
    print(f"Loading tag vocabulary from {TAG_VOCAB_FILE}...")
    
    with open(TAG_VOCAB_FILE, 'r') as f:
        data = json.load(f)
    
    # Handle list schema
    if isinstance(data, list):
        tags = set(data)
        print(f"Tag vocabulary loaded: {len(tags)} tags (list schema)\n")
        return tags
    
    # Handle object schema with items or data array
    if isinstance(data, dict):
        if "items" in data:
            tags = set(data["items"])
            print(f"Tag vocabulary loaded: {len(tags)} tags (object schema with 'items')\n")
            return tags
        elif "data" in data:
            tags = set(data["data"])
            print(f"Tag vocabulary loaded: {len(tags)} tags (object schema with 'data')\n")
            return tags
    
    raise ValueError(f"Unrecognized tag vocabulary schema in {TAG_VOCAB_FILE}")


def load_injury_rules() -> Dict[str, Dict[str, List[str]]]:
    """
    Load INJURY_RULES from fightcamp.injury_exclusion_rules.
    """
    print("Loading INJURY_RULES from fightcamp.injury_exclusion_rules...")
    
    # Add parent directory to path to import fightcamp
    sys.path.insert(0, str(REPO_ROOT))
    
    from fightcamp.injury_exclusion_rules import INJURY_RULES
    
    print(f"INJURY_RULES loaded: {len(INJURY_RULES)} regions\n")
    return INJURY_RULES


def parse_bank_schema(data: Any) -> Tuple[List[Dict], str]:
    """
    Parse bank data and return list of entries with schema description.
    
    Supports:
    - Root list: [{"name": ..., "tags": ...}, ...]
    - Object with "items": {"items": [...]}
    - Object with "data": {"data": [...]}
    
    Returns:
        (entries, schema_description)
    """
    if isinstance(data, list):
        return data, f"root list with {len(data)} entries"
    
    if isinstance(data, dict):
        if "items" in data and isinstance(data["items"], list):
            entries = data["items"]
            return entries, f"object with 'items' array containing {len(entries)} entries"
        elif "data" in data and isinstance(data["data"], list):
            entries = data["data"]
            return entries, f"object with 'data' array containing {len(entries)} entries"
    
    raise ValueError(f"Unrecognized bank schema structure. Expected list or object with items/data array.")


def validate_bank(bank_path: Path, tag_vocab: Set[str], injury_rules: Dict) -> Tuple[bool, int, Set[str]]:
    """
    Validate a single bank file.
    
    Returns:
        (success, entry_count, all_tags_in_bank)
    """
    print("=" * 40)
    print(f"Validating: {bank_path.name}")
    print("=" * 40)
    
    # Load bank data
    with open(bank_path, 'r') as f:
        data = json.load(f)
    
    # Parse schema
    try:
        entries, schema_desc = parse_bank_schema(data)
        print(f"Schema: {schema_desc}\n")
    except ValueError as e:
        print(f"❌ ERROR: {e}\n")
        return False, 0, set()
    
    # Validation flags
    has_errors = False
    all_tags_in_bank = set()
    
    # Validate required keys and types
    print("Required key validation:")
    
    # Check 'name' key
    missing_name = [i for i, entry in enumerate(entries) if not isinstance(entry, dict) or "name" not in entry]
    if missing_name:
        print(f"  ❌ Missing 'name' key at indices: {missing_name[:10]}{'...' if len(missing_name) > 10 else ''}")
        has_errors = True
    else:
        print("  ✓ All entries have 'name'")
    
    # Check 'tags' key
    missing_tags = [i for i, entry in enumerate(entries) if not isinstance(entry, dict) or "tags" not in entry]
    if missing_tags:
        print(f"  ❌ Missing 'tags' key at indices: {missing_tags[:10]}{'...' if len(missing_tags) > 10 else ''}")
        has_errors = True
    else:
        print("  ✓ All entries have 'tags'")
    
    # Check 'tags' is a list
    non_list_tags = [i for i, entry in enumerate(entries) if isinstance(entry, dict) and "tags" in entry and not isinstance(entry["tags"], list)]
    if non_list_tags:
        print(f"  ❌ 'tags' is not a list at indices: {non_list_tags[:10]}{'...' if len(non_list_tags) > 10 else ''}")
        has_errors = True
    else:
        print("  ✓ All 'tags' are lists")
    
    # Check all tag values are strings
    non_string_tags = []
    for i, entry in enumerate(entries):
        if isinstance(entry, dict) and "tags" in entry and isinstance(entry["tags"], list):
            for tag in entry["tags"]:
                if not isinstance(tag, str):
                    non_string_tags.append(i)
                    break
                all_tags_in_bank.add(tag)
    
    if non_string_tags:
        print(f"  ❌ Non-string tag values at indices: {non_string_tags[:10]}{'...' if len(non_string_tags) > 10 else ''}")
        has_errors = True
    else:
        print("  ✓ All tag values are strings")
    
    print()
    
    # Count safe/blocked by ban_tags for each injury region
    if not has_errors:
        print("Ban tag coverage by injury region:")
        for region, rules in sorted(injury_rules.items()):
            ban_tags = rules.get("ban_tags", [])
            if not ban_tags:
                continue
            
            blocked_count = 0
            safe_count = 0
            
            for entry in entries:
                if not isinstance(entry, dict) or "tags" not in entry:
                    continue
                
                entry_tags = set(entry.get("tags", []))
                if any(ban_tag in entry_tags for ban_tag in ban_tags):
                    blocked_count += 1
                else:
                    safe_count += 1
            
            print(f"  {region}: Safe={safe_count} | Blocked={blocked_count}")
        
        print()
    
    if has_errors:
        print(f"❌ Validation FAILED for {bank_path.name}\n")
        return False, len(entries), all_tags_in_bank
    
    print(f"✓ Validation PASSED for {bank_path.name}\n")
    return True, len(entries), all_tags_in_bank


def main():
    """Main validation routine."""
    # Discover banks
    banks = discover_banks()
    
    if not banks:
        print("No banks found to validate.")
        return 0
    
    # Load tag vocabulary
    try:
        tag_vocab = load_tag_vocabulary()
    except Exception as e:
        print(f"❌ ERROR loading tag vocabulary: {e}")
        return 1
    
    # Load injury rules
    try:
        injury_rules = load_injury_rules()
    except Exception as e:
        print(f"❌ ERROR loading INJURY_RULES: {e}")
        return 1
    
    # Validate all banks
    all_success = True
    total_entries = 0
    all_tags_seen = set()
    
    for bank_path in banks:
        try:
            success, entry_count, bank_tags = validate_bank(bank_path, tag_vocab, injury_rules)
            all_success = all_success and success
            total_entries += entry_count
            all_tags_seen.update(bank_tags)
        except Exception as e:
            print(f"❌ ERROR validating {bank_path.name}: {e}\n")
            all_success = False
    
    # Build comprehensive data structures for diagnostics
    all_ban_tags = set()
    all_bank_tags = all_tags_seen
    valid_tags = tag_vocab
    REGION_BAN_TAGS = {}
    had_errors = not all_success
    
    for region, rules in injury_rules.items():
        ban_tags = rules.get("ban_tags", [])
        if ban_tags:
            REGION_BAN_TAGS[region] = ban_tags
            all_ban_tags.update(ban_tags)
    
    # Build tag_to_regions map: for each tag in REGION_BAN_TAGS, show which regions reference it
    tag_to_regions = defaultdict(list)
    for region, ban_tags in REGION_BAN_TAGS.items():
        for tag in ban_tags:
            tag_to_regions[tag].append(region)
    
    # Enhanced diagnostics section
    print("=" * 40)
    print("Ban tags diagnostics:")
    print("=" * 40)
    
    # A) Ban tags missing from tag_vocabulary
    missing_from_vocab = []
    for ban_tag in sorted(all_ban_tags):
        if ban_tag not in valid_tags:
            regions = tag_to_regions.get(ban_tag, [])
            missing_from_vocab.append((ban_tag, regions))
    
    if missing_from_vocab:
        print("\nBan tags missing from tag_vocabulary:")
        for ban_tag, regions in missing_from_vocab:
            print(f"  - {ban_tag} (regions: {', '.join(regions)})")
    
    # B) Ban tags unused in any bank
    unused_in_banks = []
    for ban_tag in sorted(all_ban_tags):
        if ban_tag not in all_bank_tags:
            regions = tag_to_regions.get(ban_tag, [])
            unused_in_banks.append((ban_tag, regions))
    
    if unused_in_banks:
        print("\nBan tags unused in any bank:")
        for ban_tag, regions in unused_in_banks:
            print(f"  - {ban_tag} (regions: {', '.join(regions)})")
    
    if not missing_from_vocab and not unused_in_banks:
        print("  ✓ All ban_tags are present in tag vocabulary and used in banks")
    
    print()
    
    # Print summary
    print("=" * 40)
    print("VALIDATION SUMMARY")
    print("=" * 40)
    print(f"Total banks validated: {len(banks)}")
    print(f"Total entries validated: {total_entries}")
    
    if had_errors:
        print("❌ Some validations failed")
        return 1
    else:
        print("✓ All validations passed")
        return 0


if __name__ == "__main__":
    sys.exit(main())
