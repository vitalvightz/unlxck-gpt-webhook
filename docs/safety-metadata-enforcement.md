# Safety metadata enforcement and confirmed source findings

Base: `Main` at `5b8f4fbf` (2026-10-20), after merged #2853. This review covers the six requested fields and the two named source findings. It does not reclassify the original 196 findings. No clinical policy, clinical dose, exercise identity, historical exposure, vocabulary or deployment configuration is migrated.

## Producer → consumer audit

Counts describe the source banks at the base revision. “Retained” means raw catalogue/hash/provenance retention, not evidence that a restriction affects selection.

| Field | Producer / normalisation | Decision consumers and verified effect | Classification |
| --- | --- | --- | --- |
| `avoid_if` | Two rows in `data/conditioning_bank.json`: Jump Rope (Recovery Pace), Split-Step Ankle Snap Pogo. Lists name anatomical exclusions. Bank loaders retain them; `training_catalogue.METADATA_FIELDS` exposes their raw state. | Previously no named programming reader. Now [injury_match_details](../fightcamp/injury_filtering.py#L871) matches active injury regions using the existing exclusion vocabulary, and [injury_decision](../fightcamp/injury_guard.py#L909) excludes a match before severity scoring/cached mechanical decisions. Strength/conditioning alternate reservoirs reuse the settled verdict. API customisation already calls the shared injury matcher. | **Enforced** regional restriction after this change; previously unused for enforcement. |
| `contraindications` | Eleven exercise-bank rows and two conditioning-bank rows; human-authored prose. Raw values are retained, not converted into movement tags. | Previously planner injury scoring ignored the field; `api.services.exercise_customisation.SafetyContext.contraindicated` separately interpreted current injured regions. The shared matcher/guard hard-rejects a recognised anatomical match only when the note is met by the active injury itself (`avoid if shoulder symptoms are active`, `symptom-limited`). Response-conditional notes (`skip if pain spikes…`, `…already flared…`) become `flag`-level warnings that adapt through the ordinary severity-weighted score (low allow, moderate modify, high exclude), so a body-region match alone does not exclude. Ten of the thirteen rows contain regions recognised by the existing exclusion vocabulary. No injury means no metadata rejection. Notes about missing pins, blood pressure, cut severity, trunk rotation or speed quality are not new clinical measurements. | **Enforced** active-symptom regional prohibitions; **warning** (severity-weighted) for response-conditional prose. Other conditional prose stays advisory. |
| `block_if_fight_within_days` | Three conditioning rows: Pad EMOM (5x5 format), 10; 5-10-15 Ladder (Box Jumps/Push-Ups/KB Swings), 21; EMOM: 5 Squat Cleans + 5 Burpees, 21. No loader previously interpreted the values. | [fight_proximity_allowed](../fightcamp/late_selector_windows.py#L73) now blocks at or inside the authored inclusive limit. [Conditioning evaluation](../fightcamp/conditioning.py#L1035) checks the generation countdown even outside an active late window; [late_window_allowed](../fightcamp/late_selector_windows.py#L88), reached by `stage2_payload._slot_late_window_allowed` and `planner_authority_integrity`, checks the dated assignment against original bank authority. A late-window opt-in cannot override the limit. A stated limit with unknown countdown or malformed limit fails closed; absent/null limits leave existing gates intact. | **Enforced** after this change; previously unused for enforcement. |
| `rehab_stage` | `data/rehab_bank.json`: 1,500 MSK declarations, including 1,333 nulls; `rehab_schema.REHAB_STAGES` defines the ladder. Athlete stages are produced independently by `api.contracts.rehab_stage`, then carried through generation snapshots/input parsing. | [filter_rehab_candidates](../fightcamp/rehab_selector.py#L355) rejects stages above the athlete's live stage, unknown stated stages and inactive stages. `rank_rehab_candidates` ranks exact stage over conservative fallback over unstated stage. [validate_clinical_bank](../fightcamp/rehab_clinical.py#L222) requires reviewed bank/prescription stage equality. [resolve_injury_policy](../api/contracts/injury_policy.py#L70) applies [reviewed progression](../api/contracts/rehab_progression.py#L245), evidence, medical gates, equipment and clinical permission before rendering. Camp phase cannot advance rehab stage. | **Enforced** on stage-aware/reviewed routes. Legacy null-stage compatibility remains; it is not evidence for higher-stage activation. **Unresolved** migration of legacy coverage. |
| `pain_ceiling` | MSK bank/schema: 1,492 nulls, six explicit `unrestricted`, two numeric values of 3. `validate_rehab_bank.validate_pain_ceiling` validates shape/range; `None` means unmigrated, not unrestricted. | No runtime numeric-pain comparator exists for this bank field. Catalogue, drill snapshots and review hashes retain it. Live policies use their reviewed instructions/stop rules; stale bank content prevents prescription. The two numeric rows are `shoulder_unspecified_scapular_wall_slide_band_external_rotation_reset` and `wrist_unspecified_wrist_finger_activation_micro_reset`; neither is a live policy prescription. No new numerical threshold or clearance is inferred. | **Unused for numeric runtime enforcement; unresolved clinical integration.** Shape validation/hash integrity are enforced, but do not enforce a pain limit. |
| `dose` | MSK bank: 1,491 nulls and nine non-null objects (five empty). Separate authoritative doses are authored in `data/rehab_pathways.json` and modelled by `ClinicalPrescription` / `ClinicalDose`; clinician-selected work uses the reviewed prescription contract. | Raw bank dose does not independently prescribe work. `resolve_injury_policy` uses the reviewed dose, camp reductions, readiness reductions and any exact validated clinician-selected dose. `ClinicalPrescription.bounded_camp_dose` forbids context doses above reviewed bounds. `rehab_protocols._reviewed_rehab_for_episode` renders that result; completion/evidence contracts distinguish measurable, unknown and self-paced completion. Unknown dose/demand cannot qualify as measured progression evidence. | Raw bank field **advisory / unused as prescription authority**. Reviewed policy/selection `dose` **enforced**. Null may intentionally mean self-paced reviewed guidance; it does not invent a measurable dose or capacity evidence. |

The catalogue's metadata state, source/row hashes and discovery projections do not authorize exercise selection. Existing `normalize_selection_metadata` deduplicates list metadata for programming payloads, but does not make every retained safety field an enforcement rule. These corrections leave goal/style scores, fatigue thresholds, taper rules, equipment requirements and dose resolution unchanged.

## Functional training impact (athlete's three choices)

`not_limiting`, `limiting` and `cant_train` (web/lib/injury-impact.ts) describe training impact, not a diagnosis. Their `low/moderate/high` and `mild/moderate/severe` bands are compatibility mappings; the stored `[training_impact:…]` marker is the provenance (`fightcamp.injury_awareness.reported_training_impact`).

| Choice | Generation | Today readiness | Exercise editor | Rehab policy |
| --- | --- | --- | --- | --- |
| `not_limiting` (triage-cleared) | dropped from planning (unchanged, `plan_pipeline_runtime`) | **was** treated as an active injury (hard combat work limited); now awareness only | **was** a region restriction; now ignored | unchanged |
| `limiting` | ordinary injury guard; conditional metadata adapts with severity | unchanged | unchanged | unchanged |
| `cant_train` | high-severity guard (unchanged) | stop unchanged; copy **was** "Active severe injury", now "Can't train normally" | unchanged | **was** `medical_review` ("Get this injury checked") on severity alone; now the ordinary policy path |
| missing / legacy | unchanged (treated as limiting) | unchanged | unchanged | severe without provenance still `medical_review` |

Independent medical evidence always wins over the athlete's choice (`has_independent_medical_override`): current-report medical-hold reasons (red flags, serious-injury triage), `medical_hold`, `restriction_hold`, `rehab_medical_gate`, structural/neurological consequence, a "worse" report, a severe band on a not-limiting report, and surface wounds (which stay with the surface/contact pathway).

Also found: `parse_injury_entry` returned `None` for any text containing `[training_impact:cant_train]` or `[training_impact:not_limiting]` ("cant"/"not" read as negation), so Today flags with those markers lost their region and type (the rehab policy reported `missing_injury_identity`). The marker is now stripped before parsing.

`cant_train` now reaches the rehab selector, but the clinical bank has no prescriptions for the severe band, so it reports "no suitable rehab yet; keep to your restrictions" instead of a review hold. Whether it should draw CALM-stage drills from a lower band is a clinical decision and is deferred.

The editor (`SafetyContext.contraindicated`) now also enforces `block_if_fight_within_days` with the same `fight_proximity_allowed` reader. No fight date means no countdown; an unreadable date fails closed.

### One decision for generation and manual changes

- `fightcamp.injury_filtering.is_absolute_safety_note` is the single absolute-vs-conditional classification, used by the generation guard and the editor.
- The editor's `SafetyContext.planner_excludes` holds a bank row exactly where `injury_decision` excludes it at the flag's reported severity. Previously it refused any flag-level region match.
- `contraindicated()` counts only absolute notes.
- The editor's own movement-demand checks are unchanged: an exercise that loads the injured region, or has no load evidence, is refused while a limiting injury is active. So are its rehab-policy and fight-cutoff checks.

### Medical checks before awareness-only

`api.services.today_service.restrictive_injuries` drops a `not_limiting` report only after its episode observations (which can set `rehab_medical_gate` / `progression_assessment_medical_hold`), holds and clinical policy have been evaluated. Today and the editor both use it. Unreadable observations or a failed consequence classification never clear an injury. Previously the editor filtered before applying observations.

| Complete programme (boxing, left-knee report, D49) | Strength picks |
| --- | --- |
| No injury | 28 |
| `not_limiting` | identical to no injury |
| `limiting` | 26, knee-adapted |
| `cant_train` | `triage_blocked` (normal planning paused for review) |

The six-programme comparison fixture is re-anchored to current Main (`c8ef0f26`, after #2959/#2960). This branch reproduces all six programmes byte-for-byte in plan text and Stage 2 payload.

## Confirmed defects and actual programming comparisons

The same real source rows and athlete flags were run in separate base/branch worktrees. Tests also remove only the field under test to prove that its consumer changes the decision, rather than merely coinciding with another exclusion.

| Scenario | Base Main | Corrected branch |
| --- | --- | --- |
| Punch-Specific Max Isometric Hold; mild wrist pain; SPP D-18 | Guard `modify`; selected and present in alternate pool | Guard `exclude`; omitted from work and pool |
| Overcoming Split-Squat Isometric; mild knee pain; SPP D-18 | Guard `allow`; selected and present in alternate pool | Guard `exclude`; omitted from work and pool |
| Jump Rope (Recovery Pace); mild shin pain; GPP D-18 | Guard `modify`; not selected, but retained as an alternate | Guard `exclude`; removed from alternate pool as well |
| Each authored 21-day conditioning row; SPP D-20 / D-21; conditioning priority | Selected and available as a candidate | Omitted from work and candidate pool |
| Same conditioning rows at D-22 / D-35 | Selected | Identical programming and dose |
| Same isometrics without injuries | Selected | Identical programming and dose |
| Pad EMOM; authored ten-day limit | Other existing taper gates already omit it at D-10 | Remains omitted; direct and dated-assignment tests prove its explicit limit independently, including against an `all` late-window opt-in |
| Upper-back selector lookup using raw `upper_back`, with bank aliases | Only 20 matching region candidates | Same 52 region candidates as canonical `upper back`; no stage, severity, equipment or clinical permission is granted by this lookup |

The injury metadata rejection is deliberately separate from severity-weighted mechanical scoring: an authored prohibition must not become `allow` or `modify` merely because symptoms are mild. The matcher cache now includes those source fields. Dictionary injuries reuse the existing canonical location reader. Alternate pools apply the same verdict so later session composition cannot reintroduce a prohibited exercise. Injury replacement still checks candidate mechanics; no new loading classifications or fallback exercises are introduced.

### Complete programmes

`tools/canonical_metadata_plan_probe.py` ran in both worktrees with the same clock (2026-10-11 09:00 UTC), random seed 7, hash seed 0, installed spaCy/NegEx/model and existing payloads in `tests/fixtures/tag_retirement_plans.json`:

- `boxing_gpp_power_conditioning`
- `mma_spp_counter_striker`
- `boxing_taper_shoulder_limited`
- `boxing_final_day`
- `mma_taper_no_equipment`
- `kickboxing_taper_speed`

All six complete plan texts and all six complete Stage 2 payloads compare equal, including ordered exercise membership, dose, calendar/periodisation and personalisation. [Current-Main comparison hashes](../tests/fixtures/safety_metadata_programmes.json) are new evidence tied to the base commit; the older #2853 fixtures and audit baselines are unchanged. The new regression invokes the whole planner and checks every output against those base hashes. This is representative regression evidence, not an exhaustive athlete-state proof.

## Deferred source findings

### MI-119224a94808: corrected

All fourteen named style-taper rows still contain literal duplicate tokens. This change removes exactly 22 repeated occurrences, preserving the first occurrence and every distinct risk in its original order. No `tags`, exercise names, doses, phases, load/cost classifications or clinical fields change.

[Exact before/after field deltas and row bindings](../tools/safety_metadata_source_changes.json) enumerate every affected identity. Only those fourteen row-hash keys in `training_catalogue_ids.json` are rebound to their existing IDs. No shared discovery or equipment review binds to these rows; no clinical policy references the style-taper bank. Existing normalised selection metadata and `session_composition.option_mechanical_risk_tags` are exactly equal before/after for every corrected row. Injury matches/decisions also compare equal across ankle, knee, back, shoulder and wrist scenarios. Complete programmes remain equal.

`tools/replay_safety_metadata.py` reverses only these explicit edits for historical audit/retirement verification, rejecting tampered rows and manifest bindings. The original frozen digests remain authoritative. Four production source receipts for changed files are retained from the original audit commit `ad82c28911103e11915a5567fc18623c056ba7d4`, individually checked against the existing baseline hashes; no original baseline or report is refreshed.

### MI-1af3d6723e44: alias join corrected; source rename retained as blocked

The 52 affected MSK rows comprise 32 `target_regions: ["upper back"]` and 20 `["upper_back"]`. The established identifiers are namespace-specific:

- `injury_location_registry.LOCATION_REGISTRY` uses canonical location **`upper back`**.
- The same entry uses exclusion-rule region **`upper_back`** and explicitly lists both rehab aliases.
- Bank groups use both location spellings; existing drill IDs use the `upper_back_` prefix.

Consequently the original report's proposed blanket rename to `upper_back` is not sufficient evidence of clinical canonical identity. `get_rehab_location_candidates` previously looked up its argument directly; a noncanonical alias therefore missed the registry entry. It now calls the existing canonicalizer first. Tests check both spellings against all 52 target-region rows. Exercise IDs and source rows remain byte-identical.

Historical clinical attribution is intentionally stricter: `api.contracts.rehab_evidence.read_exact_events`, `rehab_selector._event_matches_injury` and `RehabExposureEvent.is_attributable_to` require exact episode/region identity. The exposure contract also requires `body_region` to occur in `demand.target_regions`. A regression proves an existing `upper_back` event remains attributable to that exact identity, is not silently attributed to `upper back`, and is never mutated. Current shipped policies have no upper-back profile. Source normalisation would require a reviewed policy/exposure compatibility design and evidence about persisted records that is unavailable here. **No bank, policy hash, exposure, migration or clinical alias is rewritten.** This is the explicit source-correction blocker allowed by the task constraints.

## Validation and baseline failures

Python 3.12; pinned runtime/test dependencies, including spaCy 3.8.14, NegEx and `en_core_web_sm` 3.8.0. No frontend files change.

| Check | Result |
| --- | --- |
| `pytest -q tests/test_safety_metadata_enforcement.py` | 43 passed, including actual generator changes, dated source authority, source/identity parity, exact historical regions, clinical hash rejection and six complete programmes |
| Primary relevant regression set (21 modules: injury guard/exclusions/locations/restrictions; rehab selector, selection pipeline, metadata/schema, transition/pathway safety, reviewed progression and generation boundary; style-taper, late selection, strength/conditioning scoring, mechanical/equipment/history/customisation) | 1,119 passed; eight failures, each reproduced individually on untouched Main |
| Additional relevant set (13 modules: injury pipeline/regression; rehab bundles/exposure/stages/assessment/pathway equivalence; late strength/load/calendar; footwork injury) | 1,034 passed; five failures, each reproduced individually on untouched Main |
| Metadata-integrity and canonical-metadata test modules | 39 passed, six failed, thirteen setup errors on both untouched Main and branch; identical failing test IDs |
| Strict training bank validation | Same 860 errors, 276 warnings, 3 informational findings on both worktrees, across 14 targets / 4,410 inspected entries / 234 unique tags; output differs only in checkout paths |
| Rehab bank validation; `validate_clinical_bank(load_clinical_policies(), get_rehab_bank())` | No validation errors; pending bank migration remains explicitly reported; clinical validation returns `[]` |
| Ruff on changed Python files; Python compilation; `git diff --check` | Passed |
| Historical metadata/canonical CLI audits | Blocked identically by pre-existing `api/contracts/external_training.py` historical replay drift |
| Tag retirement checker | Same five protected-source drift findings on untouched Main and branch; the corrected style-taper bank is not an additional failure |

The relevant commands are the named test modules above plus `python tools/validate_banks.py --mode strict`, `python tools/validate_rehab_bank.py`, `python tools/audit_metadata_integrity.py --historical --check`, `python tools/audit_canonical_metadata.py --check` and `python tools/check_tag_retirement.py`. Historical assertions were not relaxed and failing tests were not marked expected/disabled.

### Investigation of #2853's four failures and thirteen setup errors

At #2853, `api/contracts/injury_policy.py` differed from the frozen audit production hash and lacked an original-source receipt. Current Main already contains a receipt that matches that original hash; that earlier blocker has moved. Current replay fails first on `api/contracts/external_training.py`: #2946 added `exercise_count` and its comment, while the inverse replay only reverses the earlier additions. Retrieving the original contract from the original audit commit matches the frozen digest exactly. No runtime defect or altered clinical permission follows from this replay failure.

Current Main also has a stale discovery expectation for `gas tank` (412 results rather than the frozen query result). Together these produce the current **six failures and thirteen setup errors**, reproduced before any changes and unchanged afterwards. The four additional frozen-replay-related failing assertions share the first drift exception or fail their expected diagnostic because replay stops earlier. We retain the failed historical assertions rather than updating their baselines to current product behaviour.

Other primary-suite baseline failures are the fixed inventory count (2,869 current rows versus 2,855 frozen), five protected source hashes changed since #2853, old complete-programme hashes, two Rope Climb equipment-candidate cases plus its before/after case, an equipment-history test blocked by the same replay exception, and the existing Tempo Hill Runs `dose_required` expectation. Each of the eight failing test IDs reproduces in the clean base worktree. The five additional-suite failures also reproduce there: four injury-pipeline guided/raw-string expectations and the existing Today bundle safety-hold expectation for `worse` feedback. None is introduced by these changes.

## Remaining unresolved work

1. **Upper-back source migration:** retain all 52 rows until exact clinical/exposure compatibility can be demonstrated. The alias lookup defect is fixed; historical attribution is unchanged.
2. **Numerical pain ceilings:** the two stored values have no runtime pain comparator or approved integration with injury-specific measurements. Preserve the values and clinical boundary; do not invent thresholds, missing-data clearance or sign-off.
3. **Unstructured contraindication prose:** blood pressure/cut conditions, trunk-rotation limitation and movement-quality conditions lack a verified structured comparison here. Recognised anatomical matches are enforced; the remaining conditions need an explicit sourced contract before automatic enforcement.
4. **Legacy rehab coverage:** null stage/dose/ceiling metadata and legacy non-stage-aware rendering are not clinically migrated. Existing tests intentionally preserve that compatibility. Only reviewed stage-aware routes can claim the documented clinical enforcement; do not interpret nulls as recovery/capacity evidence.
5. **Historical test/audit maintenance:** retain the pre-existing failing checks, protected evidence and older programme fixtures. Repair exact replay receipts/diagnostics and review product changes independently rather than refreshing the historical truth. This PR adds separate current-Main comparison evidence only.
