# Injury Mapping Fix: Patellar Tendon Classification

## Problem Statement

The injury mapping logic was misclassifying certain tendon-related terms as contusions (bruises/impact injuries) instead of tendonitis. This affected rehab recommendations and exercise guardrails.

### Misclassified Terms
- "patellar tendon"
- "patellar tendinopathy"
- "jumper's knee" / "jumpers knee"
- "tendon pain" (when used with "knee")

### Root Cause
The word **"knee"** was included in the `contusion` synonym list in `injury_synonyms.py` (line 260). This caused any injury phrase containing "knee" to match the contusion pattern, even when the phrase was clearly describing a tendon injury rather than a bruise.

**Example:**
```
Input: "left knee pain (patellar tendon)"
Before fix: classified as contusion ❌
After fix: classified as tendonitis ✅
```

## Solution

### 1. Updated `injury_synonyms.py`

**Removed from contusion synonyms:**
- `"knee"` - Too generic and caused false positives

**Note:** The terms `"kneed"` (verb - being struck by a knee) and `"from knee"` (impact description) remain in the contusion list as they correctly indicate impact injuries.

**Added to tendonitis synonyms:**
- `"patellar"`
- `"patellar tendon"`
- `"patellar tendinopathy"`
- `"jumper's knee"`
- `"jumpers knee"`
- `"jumper knee"`

### 2. Added Unit Tests (`tests/test_injury_scoring.py`)

Created 5 new tests to validate correct classification:

1. **`test_patellar_tendon_classified_as_tendonitis`**
   - Input: "left knee pain (patellar tendon)"
   - Expected: tendonitis

2. **`test_patellar_tendinopathy_classified_as_tendonitis`**
   - Input: "right knee patellar tendinopathy"
   - Expected: tendonitis

3. **`test_jumpers_knee_classified_as_tendonitis`**
   - Input: "left jumper's knee"
   - Expected: tendonitis

4. **`test_tendon_pain_classified_as_tendonitis`**
   - Input: "knee tendon pain"
   - Expected: tendonitis

5. **`test_knee_contusion_still_works`** (regression test)
   - Input: "knee bruise from kick"
   - Expected: contusion (still works correctly)

## Impact

### Before Fix
```
"patellar tendon" → contusion → incorrect exercise exclusions
```

### After Fix
```
"patellar tendon" → tendonitis → correct rehab protocols
```

## Testing Results

✅ **All new tests pass** (5/5)
✅ **All existing injury_scoring tests pass** (9/9)  
✅ **No regressions introduced**

## Future Considerations

### Quality Assurance
To prevent similar issues in the future, consider:

1. **Specificity Review**: Periodically review synonym lists for overly generic terms that could cause false positives
2. **Conflict Detection**: Add automated checks for terms that might match multiple injury types
3. **Test Coverage**: Expand test cases for boundary conditions and edge cases

### Potential Ambiguous Cases
These terms should be monitored for correct classification:
- Generic location words (e.g., "knee", "shoulder", "back") without context
- Multi-word phrases where individual words might trigger different classifications
- Regional variations in medical terminology

## Related Files

- `fightcamp/injury_synonyms.py` - Injury synonym mappings (modified)
- `tests/test_injury_scoring.py` - Unit tests (modified)
- `fightcamp/injury_scoring.py` - Injury classification logic (uses synonyms)
- `fightcamp/injury_guard.py` - Exercise exclusion logic (downstream consumer)
- `fightcamp/rehab_protocols.py` - Rehab recommendations (downstream consumer)

## References

- **Issue Description**: Problem statement detailing the misclassification
- **Test Data**: `test_data.json` line 29 contains the original failing case
- **Canonical Injury Types**: sprain, strain, tendonitis, contusion, pain, soreness, unspecified

## Maintenance Notes

When adding new injury synonyms:
1. Ensure terms are specific enough to avoid false positives
2. Check for conflicts with existing synonyms in other injury types
3. Add corresponding unit tests
4. Test with real-world injury descriptions
5. Document the rationale for adding the term
