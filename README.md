# UNLXCK Fight Camp Builder

This repository generates fight camp programs by combining local training modules. The main script reads athlete data, assembles strength, conditioning, recovery and other blocks, then exports the result directly to PDF and markdown formats.

## Quick Start

The application reads athlete data from a JSON file and generates a complete training plan. Example invocations:

### Local Usage

```bash
# Generate plan with default test data (outputs markdown, HTML, and PDF)
python -m fightcamp.main
```

The `generate_plan()` function returns a dictionary with:
- `plan_text` - Full training plan in markdown format
- `pdf_url` - URL to uploaded PDF (if Supabase credentials configured) 
- `coach_notes` - Coach review notes and selection rationale
- `why_log` - Reason log for exercise/drill selections

Input data format (see `test_data.json`):
```json
{
  "data": {
    "fields": [
      { "label": "Full name", "value": "Luca Mensah" },
      { "label": "Age", "value": "22" },
      { "label": "Fighting Style (Technical)", "value": ["boxer"] },
      { "label": "Any injuries or areas you need to work around?", "value": "right hamstring tightness" }
    ]
  }
}
```

### Repository Structure

```
data/      → JSON banks (exercise_bank.json, conditioning_bank.json, rehab_bank.json)
fightcamp/ → Python package with all modules and API entrypoint
tests/     → Test suite (pytest)
notes/     → Reference JSON and tag documentation
```

## Module Map

The `fightcamp` package contains the complete plan generation pipeline:

### Core Modules

- **`main.py`** - Entry point and orchestration. Loads athlete data via `PlanInput`, calculates phase weeks, generates all training blocks (strength, conditioning, rehab, recovery, nutrition), assembles the final markdown plan, and exports to HTML/PDF. Returns plan text, PDF URL, and coach notes.

- **`strength.py`** - Strength exercise selection and scoring. Loads `exercise_bank.json`, scores exercises based on weakness tags (+0.6 each), goal tags (+0.5), style tags (+0.3), phase tags (+0.4), and equipment availability. Applies fatigue penalties (-0.75 high, -0.35 moderate) and rehab penalties (-0.7 GPP, -1.0 SPP, -0.75 TAPER). Passes shortlist through injury guard for final selection.

- **`conditioning.py`** - Conditioning drill selection and scoring. Uses both `conditioning_bank.json` (general drills) and `style_conditioning_bank.json` (style-specific drills). Scoring: style match +1.5, phase match +1.0, energy system match +0.75, equipment match +0.5, weakness/goal tags +0.6/+0.5 each. Applies fatigue penalty (-1.0 high, -0.5 moderate) for high CNS drills. Energy system ratios vary by phase (GPP: 50% aerobic, SPP: 50% glycolytic, TAPER: 70% alactic).

- **`injury_guard.py`** - Injury exclusion and safe replacement logic. Implements `injury_decision()` which scores exercises against parsed injuries using region-specific thresholds, tag-based risk multipliers, and pattern matching. Returns EXCLUDE, CAUTION, or ALLOW decisions. `pick_safe_replacement()` finds safer alternatives by matching fallback tag hierarchies. Logs all exclusions when `INJURY_DEBUG=1`.

- **`rehab_protocols.py`** - Rehab drill selection and injury guardrails generation. Matches parsed injuries against `rehab_bank.json` by type, location, and phase progression. Returns up to 2 drills per injury per phase. `format_injury_guardrails()` builds injury summary, phase-specific rehab priorities, red-flag warnings, and taper conditioning cautions.

- **`mindset_module.py`** - Mental block classification and phase-specific cues. `classify_mental_block()` parses free-text mental challenges into categories (motivation, confidence, focus, gas_tank, injury_fear, rushing). Filters out style-inappropriate blocks (e.g., "fear of takedowns" for pure strikers). `get_phase_mindset_cues()` returns targeted mental guidance for each training phase.

### Supporting Modules

- **`camp_phases.py`** - Phase week calculation using `BASE_PHASE_RATIOS` with style-specific adjustments. Professional status shifts 5-10% from GPP to SPP based on fatigue, weight cut, and mindset. Style rules enforce minimums/maximums (e.g., pressure fighters require ≥45% SPP).

- **`training_context.py`** - Session allocation logic via `allocate_sessions()`. Returns phase-appropriate split of strength, conditioning, and recovery sessions based on weekly frequency (1-6 sessions/week). Calculates exercise counts per session using `calculate_exercise_numbers()`.

- **`input_parsing.py`** - Input validation and normalization via `PlanInput` dataclass. Parses Tally form fields into structured data, normalizes equipment lists, validates dates, and handles optional fields.

- **`injury_scoring.py`** - Injury phrase scoring and medical term detection. Scans for urgent terms (fracture, dislocation, infection, nerve) and mechanical red flags. Scores canonical injury types against synonym maps.

- **`injury_filtering.py`** - Injury matching and exclusion mapping. `build_injury_exclusion_map()` constructs region→tag/pattern exclusions. `match_forbidden()` checks exercise names/tags against exclusion lists with word boundary enforcement.

- **`injury_formatting.py`** - Injury parsing and laterality extraction. `parse_injury_entry()` splits injury text, extracts left/right side, and returns formatted summaries.

- **`injury_synonyms.py`** - Injury text normalization and canonicalization. `split_injury_text()` handles punctuation, conjunctions, and spaCy segmentation. `parse_injury_phrase()` routes through injury type and location canonicalizers.

### Shared Utilities

- **`bank_schema.py`** - Training item validation. `validate_training_item()` checks required fields (name, tags, phases, systems) and logs schema violations once per source file.

- **`tagging.py`** - Tag normalization and synonym handling. `normalize_tag()` converts `"muay thai"` → `"muay_thai"`, `"skill refinement"` → `"skill_refinement"`, etc. `normalize_item_tags()` marks tags as explicit or inferred for injury exclusion logic.

- **`config.py`** - Centralized constants. Defines `DATA_DIR`, phase equipment boosts, phase tag boosts, energy system ratios, style conditioning ratios, exercise counts per session, and injury guard shortlist size.

- **`build_block.py`** - HTML/PDF export. `build_html_document()` constructs semantic HTML from phase blocks. `html_to_pdf()` converts HTML to PDF using pdfkit. `upload_to_supabase()` uploads PDFs to Supabase storage (requires `SUPABASE_URL` and `SUPABASE_SERVICE_ROLE_KEY` env vars).

Run the application with `python -m fightcamp.main` from the project root.

## Injury Risk Scoring

The injury pipeline transforms free-form injury notes into exercise exclusions and safe replacements that appear in the final plan.

### How It Works

1. **Parsing** - `injury_synonyms.py` splits injury text into phrases, extracts laterality (left/right), and canonicalizes injury type and body location.

2. **Scoring** - `injury_scoring.py` scans for medical urgency terms (fracture, dislocation, nerve damage) and mechanical flags (swelling, instability, pain descriptors). Each parsed injury gets a severity level (mild/moderate/severe).

3. **Exclusion Rules** - `injury_guard.py` scores each exercise against active injuries:
   - Base risk score combines region severity multipliers (e.g., knee: 1.15, shoulder: 1.2)
   - Tag-based multipliers (e.g., `high_impact_plyo`: 1.5x, `overhead`: 1.1x)
   - Pattern matching in exercise names (e.g., "bench press" for shoulder injuries)
   - Thresholds: EXCLUDE (>1.8), CAUTION (>1.2), ALLOW (≤1.2)

4. **Replacement** - When an exercise is excluded, `pick_safe_replacement()` searches fallback tag hierarchies to find safer alternatives. For example, shoulder injuries replace overhead presses with rows or core work.

5. **Guardrails** - `rehab_protocols.py` generates phase-specific injury guardrails that appear in the final plan output, listing excluded patterns, recommended modifications, and rehab priorities.

### Logging

When `INJURY_DEBUG=1` environment variable is set, the injury pipeline logs detailed exclusion decisions:

```bash
export INJURY_DEBUG=1
python -m fightcamp.main
```

Log format:
```
[INJURY_EXCLUSION] strength_GPP | name=Barbell Overhead Press | region=shoulder | severity=moderate | risk_score=2.640 | triggers=['overhead', 'press_heavy']
[INJURY_REPLACEMENT] strength_GPP | excluded=Barbell Overhead Press | replacement=Chest-Supported Dumbbell Row
```

All logged exclusions and replacements reflect the final plan contents - the injury guard runs after initial scoring but before final selection, so the markdown/PDF output matches the logged decisions.

## Logging & Debugging

### INJURY_DEBUG Environment Variable

Set `INJURY_DEBUG=1` to enable detailed logging of injury exclusion decisions:

```bash
export INJURY_DEBUG=1
python -m fightcamp.main
```

This enables logging in:
- `injury_guard.py` - Exclusion decisions with risk scores and triggers
- `injury_filtering.py` - Pattern matching details and replacement selections  
- `strength.py` - Replacement context for strength exercises
- `conditioning.py` - Replacement context for conditioning drills

### Log Output Format

Exclusion logs show:
- Context (module and phase, e.g., `strength_GPP`, `conditioning_SPP`)
- Exercise/drill name
- Matched injury region and severity
- Calculated risk score
- Triggering tags/patterns

Replacement logs show:
- Context (module and phase)
- Excluded exercise name
- Selected replacement name

### Verifying Logs Match Final Output

The injury guard processes exercises in the same order they appear in the final plan. To verify:

1. Run with `INJURY_DEBUG=1` and capture logs
2. Open generated markdown plan or PDF
3. Search for exercise names in the phase blocks
4. Confirm excluded exercises are absent and replacements are present
5. Check injury guardrails section for documented exclusion patterns

The logs reflect the exact state after injury filtering but before markdown formatting, so there is 1:1 correspondence between logged replacements and final plan contents.

## Testing

The test suite uses pytest to validate core functionality across injury guardrails, tag provenance, and plan generation.

### Running Tests

```bash
# Install pytest if not already installed
pip install pytest

# Run all tests
pytest

# Run specific test files
pytest tests/test_injury_guard.py
pytest tests/test_tag_provenance.py

# Run with verbose output
pytest -v

# Run tests matching a pattern
pytest -k "injury"
```

### Core Test Coverage

**Injury Guardrail Tests** (`test_injury_guard.py`)
- Pattern matching with word boundaries (avoids "pressure fighter" matching "press")
- Tag-based exclusion logic
- Severity normalization (mild/moderate/severe)
- Replacement selection and fallback hierarchies
- Risk score calculations with regional multipliers
- Integration with strength and conditioning modules

**Tag Provenance Tests** (`test_tag_provenance.py`)
- Explicit vs. inferred tag marking
- Tag-based exclusion only triggers on explicit tags
- Pattern/keyword exclusions work independently of tag source
- `ensure_tags()` correctly labels tag origins

**Plan Output Tests** (`test_mindset_module.py`, `test_style_logic.py`)
- Mental block classification and filtering
- Phase mindset cue generation
- Style-specific phase rules and ratios
- Session allocation logic

**Input Parsing Tests** (`test_input_parsing.py`)
- Field validation and normalization
- Equipment list parsing
- Date handling and fight date calculations

**Injury Pipeline Tests** (`test_injury_pipeline.py`, `test_injury_formatting.py`, `test_injury_scoring.py`)
- Free-text injury parsing
- Laterality extraction (left/right)
- Canonical injury type mapping
- Medical urgency detection
- Phrase splitting and negation handling

### Test Data

Tests use fixtures from `tests/conftest.py` and sample data that mirrors the structure in `test_data.json`. The test suite validates that changes to scoring logic, injury rules, and module weightings don't break existing behavior.

Recent updates removed the OpenAI dependency and now build plans entirely from the module outputs. Short-camp handling and style-specific rules still adjust the phase weeks correctly via the helper `_apply_style_rules()`.

The **Fighting Style (Technical)** field accepts a comma-separated list when an athlete has more than one technical base (e.g. `boxing, wrestling`). The style that appears first in this list sets the fight format while conditioning drills consider every style provided.

### Professional Status

Setting the **Professional Status** field to `pro` or `professional` adjusts the camp ratios when the camp is four weeks or longer. The shift from GPP to SPP depends on fatigue, weight cutting and mindset:

- **Elite Tier 3** – low fatigue, no weight cut and mindset blocks only `generic` or `confidence`: **+10%** SPP
- **Tier 2** – low/moderate fatigue, cutting ≤5% bodyweight and no `motivation`, `gas tank` or `injury fear` blocks: **+7.5%** SPP
- **Tier 1** – all other pros: **+5%** SPP

GPP is reduced by the same amount but never drops below 15% of the total camp.

### Module Weightings & Scoring

The generator ranks drills and exercises based on a simple heuristic score. Each module applies its own weights:

**Strength module** (`strength.py`)

- Weakness tags: `+0.6` each
- Goal tags: `+0.5` each
- Style tags: `+0.3` each with a small synergy bonus (`+0.2` for two matches, `+0.1` for three or more)
- When three or more total tags match, add `+0.2`
- Phase tag matches add `+0.4` each
- Fatigue penalties: `-0.75` (high) or `-0.35` (moderate)
- Missing required equipment removes the exercise (`-999`)
  - Rehab exercises incur `-0.7` in GPP, `-1.0` in SPP and `-0.75` in TAPER

**Conditioning module** (`conditioning.py`)

- Style match (exact): `+1.5`
- Phase match: `+1.0`
- Energy system match: `+0.75`
- Equipment match: `+0.5`
- Weakness tag match: `+0.6` each (max one)
- Goal tag match: `+0.5` each (max one)
- Fatigue penalty: `-1.0` (high) or `-0.5` (moderate) if the drill has `high_cns`
- Random noise: `±0.2`

Energy system emphasis per phase is set by `PHASE_SYSTEM_RATIOS` and the ratio of style‑specific to general drills uses `STYLE_CONDITIONING_RATIO`.

#### Style Matching in Conditioning

Two banks feed the conditioning generator:

1. `conditioning_bank.json` – general drills for any athlete.
2. `style_conditioning_bank.json` – drills written for specific fighting styles.

`STYLE_CONDITIONING_RATIO` sets how many style drills appear in each phase:

```
GPP   → 20% style drills
SPP   → 60% style drills
TAPER → 5%  style drills
```

In the **general bank**, style tags simply add `+1.0` each to a drill’s score. A drill can still be chosen without them because ranking, not filtering, determines selection.

In the **style bank**, every drill already matches a tactical style. Tag overlap is used only to rank which style drills are pulled first.

The style-match score never changes the bank ratio above—it just sorts the options within each bank.

**Phase calculation** (`camp_phases.py`)

Phase weeks come from `BASE_PHASE_RATIOS` with style adjustments. Professional athletes shift 5% from GPP to SPP. Ratios are rebalanced so the weeks always sum to the camp length and taper is capped at two weeks. When multiple styles move the same phase in one direction, the combined adjustment is capped at **7%** to keep camps balanced.

### Style-Specific Phase Rules

Certain tactical styles impose hard minimums or maximums on the camp phases. These rules come from `STYLE_RULES` in `camp_phases.py` and are enforced both when the ratios are first calculated and again after the weeks are rounded:

- **Pressure fighter**
  - `SPP_MIN_PERCENT: 0.45` – at least 45% of the schedule must be SPP. Weeks are pulled from GPP if needed.
  - `MAX_TAPER: 0.10` – taper can be no more than 10% of the camp. Excess taper weeks go back into SPP.
- **Clinch fighter**
  - `TAPER_MAX_DAYS: 9` – taper tops out at nine days (roughly 1–1.5 weeks). Extra days shift to SPP.
  - `SPP_CLINCH_RATIO: 0.40` – requires at least 40% of the camp in SPP.
- **Grappler**
  - `GPP_MIN_PERCENT: 0.35` – guarantees at least 35% of the camp in GPP. SPP is reduced if necessary.

These constraints ensure fighters with those styles emphasize the most relevant phases even after other adjustments.

### Hybrid Tactical Style

The `hybrid` style tag refers to stance-switching ability rather than mixing multiple sports. Drills labeled with this tag focus on unilateral movements, footwork or rapid transitions between orthodox and southpaw. Exercises that simply blend striking and grappling no longer carry `hybrid`.

### Injury Modules

The injury pipeline turns free-form injury notes into guardrails, rehab drills, and coach review callouts.

**Parsing and canonicalization** (`injury_synonyms.py`, `injury_formatting.py`)

- Free-form injury notes are split into phrases with `split_injury_text()`, handling punctuation, conjunctions, and common separators before falling back to spaCy sentence segmentation when available.【F:fightcamp/injury_synonyms.py†L861-L887】
- Each phrase is normalized into a canonical injury type and body location via `parse_injury_phrase()`, which routes through injury type and location canonicalizers after stripping negated phrases.【F:fightcamp/injury_synonyms.py†L848-L859】
- Laterality is extracted separately (`left`/`right`) so summaries can be labeled as “Left Shoulder,” “Right Knee,” etc.【F:fightcamp/injury_formatting.py†L10-L38】

**Scoring and flags** (`injury_scoring.py`)

- `score_injury_phrase()` applies a deterministic scan for medical terms and mechanical red flags, then scores canonical injury types against a synonym map to pick the best match.【F:fightcamp/injury_scoring.py†L11-L170】
- Urgent medical terms (fracture, dislocation, infection, nerve) add escalation flags without blocking downstream rehab lookup.【F:fightcamp/injury_scoring.py†L11-L45】

**Rehab selection + guardrails** (`rehab_protocols.py`)

- Parsed entries are deduplicated by location and type, then matched against the rehab bank by type, location, and phase progression to return up to two drills per injury per phase.【F:fightcamp/rehab_protocols.py†L123-L236】
- `format_injury_guardrails()` builds the injury summary, phase rehab priorities, and red-flag list used in the plan output; taper phases add a glycolytic conditioning caution when injuries are present.【F:fightcamp/rehab_protocols.py†L365-L445】
- Support notes aggregate type-specific recovery guidance for any injuries detected.【F:fightcamp/rehab_protocols.py†L256-L336】

### Mental Modules

The mental workflow focuses on classifying intake blockers, filtering them for style fit, and surfacing phase cues in the plan output.

**Mental block intake + filtering** (`main.py`)

- The intake’s mental blocker text is classified into one or more blocks, then filtered so pure strikers do not receive a “fear of takedowns” cue.【F:fightcamp/main.py†L157-L214】
- Mental blocks are stored in the training context so they can be reused across the phase summaries, coach review notes, and plan header sections.【F:fightcamp/main.py†L240-L267】【F:fightcamp/main.py†L650-L706】

**Phase cues** (`main.py`, `mindset_module.py`)

- Phase mindset cues are retrieved from the mindset module and injected into each phase’s strength block so the plan surfaces a targeted mental focus alongside the physical work.【F:fightcamp/main.py†L254-L312】

**Training context** (`training_context.py`)

The helper `allocate_sessions()` now takes a phase and returns the split for
strength, conditioning and recovery. The schedule adapts across phases:

```
1 session/week
  GPP   → 1 Strength
  SPP   → 1 Conditioning
  Taper → 1 Conditioning

2 sessions/week
  GPP   → 1 Strength, 1 Conditioning
  SPP   → 1 Strength, 1 Conditioning
  Taper → 1 Conditioning, 1 Recovery

3 sessions/week
  GPP   → 1 Strength, 1 Conditioning, 1 Recovery
  SPP   → 1 Strength, 2 Conditioning
  Taper → 1 Strength, 1 Conditioning, 1 Recovery

4 sessions/week
  GPP   → 2 Strength, 1 Conditioning, 1 Recovery
  SPP   → 1 Strength, 2 Conditioning, 1 Recovery
  Taper → 1 Strength, 1 Conditioning, 2 Recovery

5 sessions/week
  GPP   → 2 Strength, 2 Conditioning, 1 Recovery
  SPP   → 2 Strength, 2 Conditioning, 1 Recovery
  Taper → 1 Strength, 1 Conditioning, 3 Recovery

6 sessions/week
  GPP   → 2 Strength, 3 Conditioning, 1 Recovery
  SPP   → 2 Strength, 3 Conditioning, 1 Recovery
  Taper → 1 Strength, 1 Conditioning, 4 Recovery
```

`Weekly Training Frequency` is the number of sessions the athlete plans to
complete each week. The `Time Availability for Training` field simply lists
which days are open. Frequency does **not** automatically equal the count of
available days—a fighter might have seven days free but only train five times
per week. The program schedules sessions based on the provided frequency and
assigns them to the supplied training days.

The function `calculate_exercise_numbers()` expands on this by converting the
weekly session split into actual exercise counts.  Strength days output `7`,
`6` or `4` exercises per session in `GPP`, `SPP` and `TAPER` respectively while
conditioning days use `4`, `3` and `2`.  Recovery is implied by days without
strength or conditioning work.

### Performance Goals

The Tally intake form includes optional key performance goals. Selecting **Skill Refinement** maps to the internal tag `skill_refinement`. The strength and conditioning modules define this goal with tags like `coordination`, `skill`, `footwork`, `cognitive`, `focus`, `reactive` and `decision_speed`. Exercises containing these tags score higher when the plan is built, so drills that refine technique are prioritized across all phases. Additionally, the conditioning module includes a safeguard that inserts at least one style-bank drill tagged with `skill_refinement` whenever this goal is selected.
