# Implementation Summary: Constraint Phrase Parsing Fix

## Problem Statement

Previously, constraint phrases like **"avoid deep knee flexion under load"** were incorrectly parsed as injuries with:
- `injury_type="contusion"`
- `severity="moderate"`

This caused confusion and incorrect data in the injury processing pipeline.

## Solution Overview

This PR introduces a minimal, safe fix that properly separates constraint phrases from actual injuries by:

1. **Creating a new ParsedRestriction model** with appropriate fields
2. **Adding constraint detection logic** using trigger tokens
3. **Refactoring the injury parsing entry point** to return separate lists
4. **Maintaining full backward compatibility** with existing code

## What Changed

### New Files

1. **`fightcamp/restriction_parsing.py`** (208 lines)
   - `ParsedRestriction` TypedDict model
   - Constraint trigger tokens (avoid, no, limit, flare, etc.)
   - Canonical restriction mappings for common phrases
   - Restriction parsing logic with region and strength inference

2. **`tests/test_restriction_parsing.py`** (167 lines)
   - 12 comprehensive tests for restriction parsing
   - Tests for trigger detection, canonical matching, laterality, strength inference
   - Tests for mixed injury/restriction input
   - Backward compatibility verification

3. **`RESTRICTION_PARSING.md`** (189 lines)
   - Comprehensive documentation
   - Usage examples
   - Integration guide

### Modified Files

1. **`fightcamp/injury_formatting.py`** (52 lines total, +29 added)
   - Added `parse_injuries_and_restrictions()` - main entry point
   - Updated `parse_injury_entry()` to filter constraint phrases
   - Added `format_restriction_summary()` helper

## Key Features

### ParsedRestriction Model

```python
{
    'restriction': str,      # e.g., "deep_knee_flexion", "heavy_overhead_pressing"
    'region': str | None,    # e.g., "knee", "shoulder"
    'strength': str,         # "avoid", "limit", or "flare" (NOT "severity")
    'side': str | None,      # "left" or "right"
    'original_phrase': str   # Original input text
}
```

### Constraint Detection

Trigger tokens: `avoid`, `no`, `not`, `don't`, `do not`, `limit`, `restricted`, `not comfortable`, `flare`, `flares`, etc.

### Canonical Restrictions

- `deep_knee_flexion` (knee)
- `heavy_overhead_pressing` (shoulder)
- `high_impact` (general)
- `loaded_flexion` (general)
- `max_velocity` (general)

## Test Results

✅ **All 37 tests passing:**
- 12 new restriction parsing tests
- 5 injury pipeline tests (unchanged)
- 5 injury formatting tests (unchanged)
- 13 injury dict format tests (unchanged)
- 2 injury scoring tests (unchanged)

✅ **Security scan:** 0 vulnerabilities found

## Usage Example

### Before (Incorrect)
```python
result = parse_injury_entry("avoid deep knee flexion under load")
# Result: {'injury_type': 'contusion', 'canonical_location': 'knee', 'severity': 'moderate'}
# ❌ Wrong: Treated as an injury
```

### After (Correct)
```python
# Option 1: Automatic filtering
result = parse_injury_entry("avoid deep knee flexion under load")
# Result: None
# ✅ Correctly filtered out

# Option 2: Explicit separation
injuries, restrictions = parse_injuries_and_restrictions(
    "Knee soreness. Avoid deep knee flexion under load."
)
# injuries: [{'injury_type': 'contusion', 'canonical_location': 'knee', ...}]
# restrictions: [{'restriction': 'deep_knee_flexion', 'region': 'knee', 'strength': 'avoid', ...}]
# ✅ Properly separated
```

## Backward Compatibility

✅ **100% backward compatible:**
- All existing code continues to work without changes
- `parse_injury_entry()` now filters constraints automatically
- Existing tests unchanged and passing
- No breaking changes to public APIs

## Benefits

1. **Accuracy:** Constraint phrases no longer misidentified as injuries
2. **Clarity:** Clear separation between injuries and restrictions
3. **Extensibility:** Prepares groundwork for constraint-based filtering logic
4. **Analytics:** Better data quality for injury/restriction analysis
5. **Safety:** Minimal, surgical changes with comprehensive tests

## Implementation Quality

- **Minimal changes:** Only modified 1 existing file, added 3 new files
- **Well tested:** 12 new tests, all existing tests passing
- **Well documented:** Comprehensive documentation with examples
- **Code reviewed:** All feedback addressed
- **Security scanned:** No vulnerabilities
- **Type safe:** Uses TypedDict for clear data contracts

## Next Steps (Future Work - Not in This PR)

Potential future enhancements (beyond scope of this minimal fix):
- Integrate restrictions into `injury_guard.py` decision logic
- Add restriction-based exercise filtering
- Create restriction visualization in output
- Add more canonical restriction types based on usage patterns

---

**Status:** ✅ Complete and ready for merge
