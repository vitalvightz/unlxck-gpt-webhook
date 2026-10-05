# Exact-duplicate rehab cleanup

Base: Main `21ba71d28ff2815d8701906e35d46322bb00969a` after #2740, reviewed 2026-10-05.

## Exact results

| Measure | Before | After |
| --- | ---: | ---: |
| Exact-duplicate clusters | 29 | 0 |
| Selectable bank identities | 1,630 | 1,601 |
| Bank groups | 769 | 755 |
| MSK review records in active ledger | 1,526 | 1,497 |
| Declared duplicate-debt combinations | 29 | 0 |
| Active profiles | 64 | 64 |
| LIVE identities | 103 | 103 |
| Live CALM / RESTORE identities | 64 / 39 | 64 / 39 |
| ADVANCED_CANDIDATE identities | 57 | 57 |
| REPAIR identities | 1,149 | 1,149 |
| Near / uncertain / intentionally distinct clusters | 22 / 27 / 44 | 22 / 27 / 44 |

29 surplus identities removed from selectable inventory and retained as archival
compatibility identities. No cluster was reclassified during revalidation; none
of the near/uncertain clusters was selected for cleanup. No active prescription
ID, profile hash, review hash, clinical instruction, demand, dose, stop rule,
progression rule or contact/clearance rule changed. LOAD/DYNAMIC/RETURN remain
closed. Surface bank content, identity/content approval and runtime guards from
#2740 are unchanged.

## Revalidation and selection

The migration recomputes the rationalisation audit from actual Main bank, ledger
and pathway data, rather than trusting a stale cluster file. For all 29 pairs,
**every drill field except `id` is exactly equal**. This covers instructions,
movement/name, equipment, stage, function, load, impact, velocity, laterality,
contraction/contact level, target tissues/regions, dose, severity/pain constraints,
progression/regression/stop rules and evidence notes. Full group context also
matches, including region, injury type and camp phase progression.

Review state, review version, flags, archetype and proposed metadata match within
each pair. Historical name/instruction revisions match. ID-dependent source
hashes differ as expected; both complete original review records and histories
are preserved, not normalised away or promoted to a new review. Current source
hashes are checked against the original source text. Exactness is not an efficacy
approval: unreviewed or unsafe keepers retain their existing review/classification.

Only one pair contains a LIVE identity: `calf_strain_double_leg_calf_raises`.
That ID is kept. In the other pairs, review state and historical provenance are
equal, so established unsuffixed naming wins after profile/test reference
priority. Original group/drill positions and migration naming support this stable
choice; no lexical tidying displaces a live identity. The table below records
each decision. No profile references a retired ID.

## Historical compatibility and provenance

`data/rehab_archive/exact_duplicates.json` stores each retired drill under its
**original ID**, its complete metadata review/source history, the keeper's prior
review record, original group context/positions, original audit cluster and
selection reason. It also retains the original debt ledger and pre-cleanup input
hashes/summary. No large modification to the clinical bank schema was introduced.

This archive is not an alias registry and is never read by candidate selection.
`rehab_drill_by_id` continues to resolve current bank identities only; retired IDs
return None. `archived_rehab_drill_by_id` explicitly recovers a copy of the old
drill with the old ID. The only production consumer is the completion reader's
fallback for a stored block whose active lookup fails and which lacks a frozen
drill snapshot. Existing frozen metadata is read unchanged. These are places
where persisted plans/accepted sessions can already carry bank IDs, so deleting
those IDs without historical handling would lose completion attribution.

Accepted snapshots, completion rows, exposure rows and historical plans are not
rewritten. Old exposure IDs, drill IDs, episode ownership and policy provenance
remain their original values; there is no remapping that could double-credit
old work toward a retained prescription. Existing occurrence/event idempotence
continues to govern credit. A repeated serialization of the same block remains
one occurrence, including a mixed old/current-ID representation. Separate physical
block IDs retain their existing semantics. Unknown demands continue to be refused
by existing exposure validation; archival lookup does not approve unreviewed work.

The 14 groups that become empty are removed. No non-empty group is otherwise
changed except for removing the surplus drill. All retained drill and review
objects remain equal to Main. Tests reconstruct the entire original bank and
review ledger from current inventory plus archive and compare against the
immutable original rationalisation baseline hashes. The baseline is not reset.

## Reproduction and verification

- `python tools/consolidate_rehab_exact_duplicates.py --check`
- `python tools/audit_rehab_bank_rationalisation.py --check`
- `python -m pytest tests/test_rehab_exact_duplicate_cleanup.py tests/test_rehab_bank_rationalisation.py tests/test_rehab_bank_schema.py tests/test_rehab_drill_identity.py`
- `python tools/validate_rehab_bank.py`
- `python tools/validate_rehab_metadata_review.py`
- `python tools/validate_rehab_clinical.py`
- `python tools/audit_injury_vocabulary.py`
- `python tools/check_tag_registry.py`
- `python tools/migrate_rehab_bank_schema.py --check`
- `python tools/migrate_tag_registry_data.py --check`
- `python -m ruff check api fightcamp tests tools`

The bounded migration's `--write` is a no-op after its archive exists: it verifies
the applied migration instead of selecting more cleanup. Tests check byte-level
idempotence, deterministic reconstruction, historical snapshot lookup with and
without metadata, candidate exclusion, source preservation and before/after
CALM/RESTORE decision/session equality for all 64 profiles. Existing completion,
multi-injury, clearance, surface and family/seed suites supply additional coverage.
The three rationalisation reports are written only by the deterministic audit tool.

No database migration, frontend change, environment change or deployment is
required. No production-history query was performed; compatibility follows the
existing persisted-ID contracts and is exercised with historical fixtures.
Near duplicates, uncertain inventory, advanced-candidate cleanup and LOAD
activation remain outside this change.

## Validation results and changed files

- Cleanup regression suite: 233 passed.
- Rationalisation, schema, identity, metadata review and surface safety suites: 345 passed.
- Prescription bundles, completion capture/API, multi-injury, clinician clearance,
  selector/pipeline and seven family coverage suites: 2,912 passed initially;
  nine historical-inventory assertions failed because they assumed archived IDs
  remained active. After updating those assertions to reconstruct historical
  inventory, all 25 cases in the affected parameter groups passed.
- Today service/safety matrix, surface readiness/train-through and vocabulary
  coverage suites: 342 passed (existing deprecation warnings).
- Ruff across `api fightcamp tests tools`, changed-module import checks and
  `git diff --check`: passed.
- Consolidation `--check`, deterministic rationalisation `--check`, rehab bank,
  metadata review, clinical policy, vocabulary and tag validators, schema and
  tag migration idempotence checks: passed. Rehab schema has zero errors/warnings;
  clinical policies remain 64 active and zero promotable.
- Whole-bank `validate_banks.py` audit mode exited successfully but still reports
  existing non-rehab inventory debt: 827 errors and 273 warnings. This is not a
  claim that the strict whole-bank gate passes. No full-repository test run or
  production-history/database query was performed.

Changed production files are the active bank/review/debt JSON, the historical
archive, `fightcamp/rehab_duplicate_archive.py` and the completion reader fallback.
The consolidation tool and rationalisation renderer provide reproducible outputs.
The three generated audit documents, this report, cleanup/schema/identity/audit
tests and seven family history assertions supply review evidence. Neither pathway
content nor the #2740 surface safety code/review ledger changed.

## Canonical and retired identities

Each retired ID below remains readable only through archival compatibility.

| Canonical ID retained | Surplus ID archived | Selection reason |
| --- | --- | --- |
| achilles_pain_banded_heel_push_with_hold | achilles_pain_banded_heel_push_with_hold_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| achilles_pain_isometric_holds_in_tip_toe | achilles_pain_isometric_holds_in_tip_toe_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| achilles_tendonitis_massage_gun_achilles_line | achilles_tendonitis_massage_gun_achilles_line_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| calf_strain_active_band_calf_pumps | calf_strain_active_band_calf_pumps_2 | Equal reviewed provenance/history; retain the established unsuffixed identity. |
| calf_strain_double_leg_calf_raises | calf_strain_double_leg_calf_raises_2 | Retain the existing LIVE prescription identity. |
| calf_strain_isometric_tip_toe_wall_press | calf_strain_isometric_tip_toe_wall_press_2 | Equal reviewed provenance/history; retain the established unsuffixed identity. |
| calf_strain_isometric_wall_push_hold | calf_strain_isometric_wall_push_hold_2 | Equal reviewed provenance/history; retain the established unsuffixed identity. |
| calf_tightness_massage_gun_sweep_soleus_line | calf_tightness_massage_gun_sweep_soleus_line_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| calf_tightness_wall_calf_stretch_bent_knee | calf_tightness_wall_calf_stretch_bent_knee_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| knee_instability_mini_band_lateral_walks | knee_instability_mini_band_lateral_walks_2 | Equal reviewed provenance/history; retain the established unsuffixed identity. |
| knee_instability_reactive_knee_bounces_foam_pad | knee_instability_reactive_knee_bounces_foam_pad_2 | Equal reviewed provenance/history; retain the established unsuffixed identity. |
| knee_pain_massage_gun_quad_sweep_to_patella | knee_pain_massage_gun_quad_sweep_to_patella_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| knee_pain_terminal_knee_extensions_tkes | knee_pain_terminal_knee_extensions_tkes_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| knee_strain_band_assisted_lateral_lunges | knee_strain_band_assisted_lateral_lunges_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| knee_strain_lateral_step_downs | knee_strain_lateral_step_downs_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| knee_strain_mini_band_lateral_walks | knee_strain_mini_band_lateral_walks_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| knee_strain_wall_sit_short_arc | knee_strain_wall_sit_short_arc_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| knee_tightness_massage_gun_rectus_line | knee_tightness_massage_gun_rectus_line_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| knee_tightness_quad_hip_flexor_stretch | knee_tightness_quad_hip_flexor_stretch_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| shin_contusion_foam_roller_circles_mid_shin | shin_contusion_foam_roller_circles_mid_shin_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| shin_contusion_light_shin_percussion | shin_contusion_light_shin_percussion_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| shin_contusion_tap_drill_with_soft_stick | shin_contusion_tap_drill_with_soft_stick_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| shin_contusion_wall_shin_slides | shin_contusion_wall_shin_slides_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| shin_pain_heel_walks | shin_pain_heel_walks_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| shin_pain_isometric_toe_lift_holds | shin_pain_isometric_toe_lift_holds_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| shin_tendonitis_massage_gun_sweep_tibialis_line | shin_tendonitis_massage_gun_sweep_tibialis_line_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| shin_tendonitis_wall_toe_raises | shin_tendonitis_wall_toe_raises_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| shin_tightness_lacrosse_ball_glide_tibialis | shin_tightness_lacrosse_ball_glide_tibialis_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
| shin_tightness_seated_anterior_shin_stretch | shin_tightness_seated_anterior_shin_stretch_2 | Equal unreviewed provenance; retain established unsuffixed naming, without approving the movement. |
