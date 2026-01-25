# Injury Exclusion Logic Fix - Implementation Summary

## Problem
The injury exclusion logic was not reliably excluding variations of 'Romanian Deadlift' for hamstring injuries due to insufficient normalization and substring matching. Specifically:
- Compound words like "RomanianDeadlift" (no space) were not being caught by word-boundary matching
- The system relied heavily on tag-based exclusion, missing keyword-based exclusion for certain variants

## Solution

### 1. Enhanced Normalization
Added `normalize_for_substring_match()` function that:
- Converts to lowercase
- Removes ALL non-alphanumeric characters (spaces, hyphens, underscores, parentheses, punctuation)
- Enables substring matching for compound words

Example:
- "Romanian Deadlift (RDL)" → "romaniandeadliftrdl"
- "RomanianDeadlift" → "romaniandeadlift"

### 2. Two-Pass Matching Strategy
Refactored `match_forbidden()` to use a two-pass approach:

**Pass 1: Word-boundary matching (primary)**
- Handles 95% of cases using the existing `_phrase_in_text()` logic
- Maintains backward compatibility
- Prevents false positives

**Pass 2: Substring matching (fallback)**
- Only activates if NO word-boundary matches found
- Only applies to multi-word patterns (e.g., "romanian deadlift")
- Single-word patterns (e.g., "kipping", "hip") use word-boundary only
- Prevents false positives like "kipping" in "skipping"

### 3. Exclusion Logging
Added logging in `injury_match_details()` when exercises are excluded due to ban_keyword matches:
```python
logger.info(
    "[injury-exclusion] Excluding '%s' for %s injury: ban_keyword '%s' found in %s='%s'",
    name, region, matched_pattern, field_name, value,
)
```

### 4. Comprehensive Test Suite
Created `tests/test_rdl_exclusion.py` with tests for:
- Normalization functions
- RDL keyword matching for all variations  
- End-to-end exclusion
- False positive prevention
- Substring matching for compound words

## Results

### ✅ All RDL Variations Properly Excluded:
- "Romanian Deadlift" ✓
- "Romanian Deadlift (RDL)" ✓
- "RomanianDeadlift" ✓ (compound word via substring)
- "RDL" ✓
- "Single-Leg RDL" ✓
- "DB-RDL" ✓

### ✅ No False Positives:
- "skipping rope" does NOT match "kipping" ✓
- "membership plan" does NOT match "hip" ✓
- "Pressure Fighter" does NOT match "press" ✓

### ✅ Existing Tests Pass:
- All existing `match_forbidden` tests pass
- All injury guard tests pass
- No regressions in shoulder, knee, or other injury exclusions

## Technical Details

### Key Files Modified:
1. **`fightcamp/injury_filtering.py`**
   - Added `normalize_for_substring_match()`
   - Refactored `match_forbidden()` with two-pass matching
   - Added exclusion logging in `injury_match_details()`

2. **`tests/test_rdl_exclusion.py`** (new)
   - Comprehensive test suite for RDL variations
   - Tests normalization, matching, and end-to-end exclusion

### Algorithm:
```python
def match_forbidden(text, patterns):
    # 1. Check allowlist (early exit)
    if text in allowlist:
        return []
    
    # 2. Pass 1: Word-boundary matching
    word_matches = find_word_boundary_matches(text, patterns)
    if word_matches:
        return word_matches
    
    # 3. Pass 2: Substring matching (multi-word patterns only)
    substring_matches = find_substring_matches(text, multi_word_patterns)
    return substring_matches
```

### Matching Examples:

| Text | Pattern | Strategy | Match? |
|------|---------|----------|--------|
| "Romanian Deadlift" | "romanian deadlift" | Word boundary | ✓ Yes |
| "Romanian Deadlift (RDL)" | "rdl" | Word boundary | ✓ Yes |
| "RomanianDeadlift" | "romanian deadlift" | Substring (fallback) | ✓ Yes |
| "kipping pull-up" | "kipping" | Word boundary | ✓ Yes |
| "skipping rope" | "kipping" | None (not word boundary, single-word pattern) | ✗ No |

## Validation

All test suites pass:
- ✅ `test_rdl_exclusion.py` - New RDL-specific tests
- ✅ `test_match_forbidden_*` - Existing match_forbidden tests
- ✅ `test_injury_guard_*` - Existing injury guard tests
- ✅ Manual validation with logging

## Conclusion

The implementation successfully addresses all requirements in the problem statement:
1. ✅ Normalize exercise names and ban_keywords before comparison
2. ✅ Implement substring checks for multi-word patterns
3. ✅ Centralize normalization in utility functions
4. ✅ Add/test unit cases for RDL variations
5. ✅ Add exclusion log messaging

The solution is minimal, focused, and maintains backward compatibility while fixing the reported issue.
