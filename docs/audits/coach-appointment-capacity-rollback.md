# Surgical rollback of #3035 appointment capacity

Restores the pre-#3035 app allocation budget: hard sparring is reserved during
compression; declared light coached work is inserted later without consuming the
non-sparring app budget. Both generic and boxing crowded-week paths are restored.
The new filler veto and initial build-repair session-cap opt-in are removed.
#3034's existing maintenance-retry budget remains. The new causal capacity-refusal
ledger writes are removed; live stale-reason checks remain for old ledgers.

Injury-readiness provenance, medical/contact restrictions, semantic primary-strength
matching, closed exercise membership, goal validation and athlete-facing explanations
are preserved. No conditioning prescriptions, exercise-count limits or injury-impact
classifications change.

## Deterministic comparison

Baseline: `315a469f` (parent of #3035); rollback based on `bd040135`.
Python 3.12, requirements-dev-fast.txt, no spaCy model. Fixture:
`tests/fixtures/injury_readiness/sam_like.json`; seed 7; clock pinned to
2026-10-24 15:06. Four sessions requested; Tue/Fri light coached work;
Wed/Sun hard sparring; open and 2026-12-05 dated camps. Compared no-injury
and legacy intake-derived moderate tracker / low knee-symptom variants.
Captured the first reconciled planning brief, as in the regression test,
and compared ordered role keys, category, weekday and countdown label per week.
This is a representative replay, not the historical production plan.

| Variant | Pre-#3035 | Rollback |
| --- | --- | --- |
| No injury, open (4 weeks) | Strength + conditioning each week | All role/day projections identical |
| No injury, dated (6 weeks) | Phase-specific strength, conditioning, fight-week recovery | All role/day projections identical |
| Legacy knee, open | No strength in all 4 weeks | Monday primary strength + Tuesday aerobic each week; Thursday mobility/rehab or joint prep restored |
| Legacy knee, dated | No strength in weeks 1–4 | Primary strength weeks 1–2; neural-plus strength week 3; strength touch week 4; conditioning retained |
| Legacy knee, dated tail | Strength touch, primer and fight-week recovery | Weeks 5–6 role/day projections identical |

Remaining limits: dated knee week 4 uses Thursday maintenance strength rather than
a development anchor; the lawful conditioning slot is Tuesday. The retained injury,
contact/load and phase authorities still govern this outcome. Secondary goal/weakness
coverage is not promised. Strict combined coach-plus-app appointment totals are no
longer guaranteed: fillers can add work, including in a three-session declaration,
as before #3035. This is the requested allocation policy rollback.

## Verification

`tests/test_injury_readiness_replay.py` covers open/dated, knee/shoulder/no-injury,
with/without coached days, and three-session recovery. It checks real strength
membership, conditioning, recovery, protected coached days, availability,
provenance and rejection of forged unjustified goal deferral. Provenance unit tests
retain independent high/severe/manual/clinician/worsening protections and exercise
both sport variants without charging light coached days.

Final replay/provenance run: 53 passed.
Broader allocation/goal/injury-impact/filler/readiness run: 222 passed.
Ruff, compilation and diff hygiene pass. Fast-environment parsing limits apply.

No live model finalization, production writes, merge or deployment.
