# Restriction Parsing Documentation

## Overview

The restriction parsing module provides a clean separation between actual injuries and physical constraints/restrictions. Previously, phrases like "avoid deep knee flexion under load" were incorrectly parsed as injuries (e.g., `injury_type="contusion"`, `severity="moderate"`). This module properly identifies and categorizes them as restrictions.

## Key Concepts

### ParsedRestriction Model

A `ParsedRestriction` is a TypedDict with the following fields:

- **`restriction`** (str): Canonical restriction key (e.g., `"deep_knee_flexion"`, `"heavy_overhead_pressing"`, `"generic_constraint"`)
- **`region`** (str | None): Anatomical region affected (e.g., `"knee"`, `"shoulder"`, `"ankle"`)
- **`strength`** (str): Intensity level - one of `"avoid"`, `"limit"`, `"reduce"`, or `"flare"`
  - Note: This is called "strength" NOT "severity" to avoid confusion with injury severity
- **`side`** (str | None): Laterality if specified (`"left"` or `"right"`)
- **`original_phrase`** (str): The original text phrase

### Trigger Tokens

Constraint phrases are detected using trigger tokens:
- `avoid`, `no`, `not`, `don't`, `do not`
- `limit`, `limited`, `restricted`, `restriction`
- `not comfortable`, `flare`, `flares`
- `contraindicated`, `skip`, `reduce`

### Canonical Restrictions

Common constraint phrases are mapped to canonical restriction keys:
- `"deep knee flexion"` → `deep_knee_flexion` (region: knee)
- `"heavy overhead pressing"` → `heavy_overhead_pressing` (region: shoulder)
- `"high impact"` → `high_impact` (region: None)
- `"loaded flexion"` → `loaded_flexion` (region: None)
- `"max velocity"` → `max_velocity` (region: None)

Phrases that don't match canonical restrictions are categorized as `generic_constraint`.

## Usage

### Basic Usage: Separate Injuries from Restrictions

```python
from fightcamp.injury_formatting import parse_injuries_and_restrictions

text = "Right shin splints. Avoid deep knee flexion under load."
injuries, restrictions = parse_injuries_and_restrictions(text)

# injuries: List of injury dicts (legacy format)
# [{'injury_type': 'pain', 'canonical_location': 'shin', 'side': 'right', ...}]

# restrictions: List of ParsedRestriction objects
# [{'restriction': 'deep_knee_flexion', 'region': 'knee', 'strength': 'avoid', ...}]
```

### Legacy Compatibility: Filter Constraints Automatically

The existing `parse_injury_entry()` function now automatically filters out constraint phrases:

```python
from fightcamp.injury_formatting import parse_injury_entry

# Constraint phrase - returns None
result = parse_injury_entry("avoid deep knee flexion under load")
# result = None

# Actual injury - returns injury data
result = parse_injury_entry("left ankle sprain")
# result = {'injury_type': 'sprain', 'canonical_location': 'ankle', 'side': 'left', ...}
```

### Format Restriction Summaries

```python
from fightcamp.injury_formatting import format_restriction_summary

restriction = {
    'restriction': 'deep_knee_flexion',
    'region': 'knee',
    'strength': 'avoid',
    'side': 'left',
}

summary = format_restriction_summary(restriction)
# "Left Knee — Deep Knee Flexion (Strength: Avoid)"
```

## Examples

### Example 1: Pure Constraint Input

```python
text = "avoid deep knee flexion under load"
injuries, restrictions = parse_injuries_and_restrictions(text)

# Result:
# injuries = []
# restrictions = [{
#     'restriction': 'deep_knee_flexion',
#     'region': 'knee',
#     'strength': 'avoid',
#     'side': None,
#     'original_phrase': 'avoid deep knee flexion under load'
# }]
```

### Example 2: Mixed Input

```python
text = "Knee soreness. Avoid deep squats and heavy lifting. Shoulder strain."
injuries, restrictions = parse_injuries_and_restrictions(text)

# Result:
# injuries = [
#     {'injury_type': 'contusion', 'canonical_location': 'knee', ...},
#     {'injury_type': 'strain', 'canonical_location': 'shoulder', ...}
# ]
# restrictions = [
#     {'restriction': 'deep_knee_flexion', 'region': 'knee', 'strength': 'avoid', ...},
#     {'restriction': 'generic_constraint', 'region': None, 'strength': 'avoid', ...}
# ]
```

### Example 3: Lateralized Restrictions

```python
text = "avoid left knee flexion"
injuries, restrictions = parse_injuries_and_restrictions(text)

# Result:
# restrictions = [{
#     'restriction': 'deep_knee_flexion',
#     'region': 'knee',
#     'side': 'left',
#     'strength': 'avoid',
#     ...
# }]
```

### Example 4: Strength Variations

```python
# Avoid strength
text1 = "avoid heavy lifting"
_, restrictions = parse_injuries_and_restrictions(text1)
# restrictions[0]['strength'] = 'avoid'

# Limit strength
text2 = "limit overhead work"
_, restrictions = parse_injuries_and_restrictions(text2)
# restrictions[0]['strength'] = 'limit'

# Flare strength
text3 = "knee flares with running"
_, restrictions = parse_injuries_and_restrictions(text3)
# restrictions[0]['strength'] = 'flare'
```

## Backward Compatibility

All existing code that uses `parse_injury_entry()` continues to work exactly as before, with the added benefit that constraint phrases are now automatically filtered out instead of being misidentified as injuries.

Functions like `_build_parsed_injury_dump()` and `_normalize_injury_entries()` in `injury_guard.py` and `rehab_protocols.py` will automatically skip constraint phrases since `parse_injury_entry()` returns `None` for them.

## Integration with Existing Code

To integrate restriction handling into your injury processing pipeline:

1. Replace calls to `split_injury_text()` + `parse_injury_entry()` with `parse_injuries_and_restrictions()`
2. Process the two lists separately:
   - Use `injuries` list for existing injury logic
   - Use `restrictions` list for constraint-based filtering or recommendations
3. Format restrictions using `format_restriction_summary()` for display

## Testing

Comprehensive tests are available in `tests/test_restriction_parsing.py`:
- Trigger token detection
- Canonical restriction parsing
- Generic constraint parsing
- Laterality extraction
- Strength inference
- Mixed injury/restriction parsing
- Backward compatibility verification

All tests pass and verify that:
- Constraint phrases are NOT parsed as injuries
- Existing injury parsing behavior is unchanged
- Restrictions have `strength` field (not `severity`)
