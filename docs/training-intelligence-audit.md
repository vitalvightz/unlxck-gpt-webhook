# Training intelligence audit

Audit baseline: `3dc625d8` on `Main`, pulled before changes. Synthetic scenarios
use 16 October 2026 and seed 1. No production athlete data is included.

## Findings and corrections

1. **High: strength coverage could expire without the planner noticing.**
   `goal_preservation._requirements` let an opening-week lift satisfy a later
   normal-camp week. Coverage now uses the actual eligible planner weeks and
   effective assigned doses. The D-13 inward tail remains under its existing
   owner; missing normal-camp strength is addressed earlier.
2. **High: selected stimuli could disappear during bounded composition.**
   `strength.generate_strength_block` and
   `session_composition.compose_normal_strength_assignments` now retain genuine
   selected strength and trunk candidates inside existing membership limits.
   Power-only programming does not discharge loaded-strength coverage.
3. **High: an exercise rejected by effective dosing could retain its base dose.**
   `prescription_resolver.apply_effective_strength_prescriptions` now removes
   unpriced strength members from the closed session, including empty results.
4. **Medium: secondary weaknesses were selected but not consistently verified.**
   `goal_preservation.selected_goals` now includes supported secondary physical
   weaknesses once, without promoting them to primary development obligations.
5. **Medium: compound working doses could disappear during card conversion.**
   `structured_plan_deterministic_fallback` preserves the complete contrast
   sequence in execution instructions when scalar card fields cannot express it.
   Numeric prescription templates are unchanged.
6. **Medium: faithful compound doses and separate support appointments could be
   misidentified as strength render violations.** The validator uses its existing
   compound-dose parser and exact authoritative support text. Changed quantities
   remain detectable.

Corrections use the existing selection, composition, dose and goal-preservation
owners. A restored normal-camp candidate still passes the shared legality and
realised-load governor. A redundant app-owned conditioning appointment may fund
it only when other selected-goal coverage survives; coach and tail roles remain
protected. Frequency keeps its existing soft-target semantics.

## Verification status

The draft PR is opened while checks continue, at the user's request.

- Core planner regression run: 528 passed.
- Goal/weakness delivery run: 96 passed.
- New cross-owner contract run: 7 passed.
- Ruff and whitespace checks passed.
- Full 16-scenario final-plan/card checks are being rerun. Remaining failures
  are under investigation; these checks are not yet claimed green.
- Broader historical metadata audits have frozen-source and inventory drift
  failures. They are recorded separately rather than hidden by rebasing their
  expected snapshots.

Full reproducible artifacts:

```powershell
python -m scripts.audit_training_intelligence --output <output-directory>
python -m pytest tests/test_training_intelligence_contract.py tests/test_training_intelligence_e2e.py -q
```

Scientific evidence, the complete before/after comparison and final check results
will be added to this report as the remaining checks complete. The harness uses
the actual deterministic intake-to-card pipeline and finalizer packet, without a
live AI-provider call. No deployment, database migration or UI redesign is part
of this change.
