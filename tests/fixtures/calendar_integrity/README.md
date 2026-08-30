# Calendar-integrity characterization baselines

Frozen **semantic** planner projections used by
`tests/test_calendar_integrity_characterization.py` (Stage 3A).

Each JSON file is the expected `_semantic_projection(...)` of one representative
scenario, captured from the **pre-Stage-3B** deterministic planner (Main /
PR #2396's base). The test asserts the live projection equals the baseline, so
Stage 3B's calendar-integrity governor can only change a calendar that violates
the shared `combat_load_policy` seam — every other row here must be preserved,
and any drift shows up as an exact diff against these files.

These are deliberately **not** full Stage 2 payload dumps. Exercise names,
athlete-facing copy, HTML, render formatting, and LLM wording are all excluded.

## Row schema (positional)

Rows are positional arrays, sorted for stability:

- **`roles[]`** — `[week_index, phase, role_key, category, weekday, d_day,
  late_fight_tail_owned, late_camp_role_morph, late_camp_strength_morph,
  stress_class, cost_class]`
- **`contacts[]`** — `[week_index, weekday, status, effective_load]`
- **`suppressed[]`** — `[week_index, role_key, category, replacement_role_key,
  compression_reason_codes]`

Plus the top-level `generator_mode`, `payload_variant`, and `tail_handoff`
(the D-14/D-13 handoff metadata).

## Scenarios

| File | Days out | Hard sparring | What it pins |
| --- | --- | --- | --- |
| `d24_no_contact.json` | 24 | none | Clean normal-camp role/day/D-day structure |
| `d24_one_hard.json` | 24 | Thursday | One resolved hard-contact day + finished tail |
| `d24_two_hard.json` | 24 | Tue, Fri | Two declared contacts (pre-governor baseline, defects included) |
| `d16_technical_conversion.json` | 16 | Tue, Fri | Declared contact converted away from effective hard |
| `d14_boundary.json` | 14 | Thursday | Normal planner still owns D-14 |
| `d13_direct.json` | 13 | Thursday | Direct D-13 uses the late-fight Stage 2 payload |
| `d28_finished_tail.json` | 28 | Thursday | Long camp; finished D-13→D-1 tail is immutable |
| `d24_high_fatigue.json` | 24 | Tue, Fri | High-fatigue suppression semantics |

`d24_two_hard.json` intentionally captures the pre-governor defect surface (a
lone effective-hard week-1 Friday, compressed week-1 strength, a duplicate
tail-spliced Friday). It is a baseline to diff against, **not** a statement of
desired behaviour.

## Regenerating

If Stage 3B legitimately changes one of these calendars, update the affected
baseline in the same PR and explain in review exactly which rows changed and
why the shared calendar policy required it.
