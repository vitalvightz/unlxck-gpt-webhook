# Rehab pathway families and regional profiles

A live rehab policy is composed, not hand-written per injury:

```
pathway family      shared CALM→RESTORE→LOAD→DYNAMIC→RETURN structure + shared requirements
+ regional profile  location, injury type, reviewed drills, stages, bundles, restrictions,
                    region-specific transition criteria, exceptions, sources
= ClinicalPolicy    what the resolver, scheduler, Today and camp generation already use
```

Everything lives in `data/rehab_pathways.json`. `fightcamp.rehab_clinical.load_clinical_policies()` composes each profile with its family; callers are unchanged. Activation is a software/data validation step, not clinician approval.

## Families

Families are keyed by injury type (the taxonomy in `fightcamp/injury_taxonomy.py`), never by location. Every musculoskeletal rehab type belongs to exactly one family. `tools/validate_rehab_clinical.py` and `tests/test_rehab_pathways.py` enforce this.

| Family | Injury types | Bank drills | Why this boundary |
| --- | --- | --- | --- |
| `muscle_strain` | strain | 103 | Contractile-tissue tear: protect, pain-free range, progressive load, then speed/sport. |
| `ligament_sprain_or_instability` | sprain, instability | 135 | Passive restraint injury or its chronic sequel: protected range, control/balance, load, reactive demands. |
| `tendon_rehab` | tendonitis | 75 | Regional tendon load management; contraction order and resistance progression require condition-specific evidence. |
| `joint_irritation_or_impingement` | impingement | 48 | Symptom-provoking joint position: settle, restore range/control, load through tolerated range. |
| `hyperextension_or_joint_trauma` | hyperextension | 42 | Joint trauma where structural injury is screened first; end-range control precedes loading. |
| `contusion` | contusion | 60 | Direct-blow bruise: different early care (no forced stretch over haematoma), otherwise progressive. |
| `nonspecific_msk_symptoms` | pain, soreness, tightness, stiffness, swelling | 358 | Symptom reports with no tissue diagnosis. Symptom-led and conservative; no diagnosis implied. Swelling follows the taxonomy's `symptom` category. |

Outside the families:

- **Wound care** (cut, abrasion, laceration, graze, blister) is a separate care pathway with no loading metadata.
- **`unspecified`** is not a family; an episode without a type gets `missing_information`. Its 664 bank drills are shared regional pools that any profile at the same location may review and use. The clinical bank validator already accepts `unspecified` groups.
- **Structural and urgent types** (tears, ruptures, fractures, dislocation, concussion and others) are not rehab-safe and remain medical gates.

## Families route; profiles activate

A family is a routing and shared-structure choice, not a diagnosis or support claim. Belonging to a family activates nothing:

- A live policy exists only for an explicit `(region, injury_type)` profile. Every other combination resolves to `unsupported_prescription` with legacy behaviour unchanged. Chest sprain, unexplained wrist instability, and unprofiled contusion, tendonitis, impingement, hyperextension or symptom reports stay unsupported. Eight strain, ten sprain/instability and eight tendonitis profiles now have explicit baseline coverage; see `strain-family-rollout.md`, `sprain-family-rollout.md` and `tendon-family-rollout.md`.
- `nonspecific_msk_symptoms` does not make pain, swelling or stiffness reports rehab-eligible. A reviewed profile would have to exist for that region and type.
- Families carry no drills, stages, restrictions or criteria of their own beyond requirements a source supports for the whole family. There are none today.

`tests/test_rehab_pathway_safety_invariants.py` pins these boundaries.

## Transitions and requirements

CALM→RESTORE is the existing baseline report ladder (`api/contracts/rehab_stage.py`): a follow-up report that is not worse. Setbacks hold at CALM until a later explicit improvement report. Every higher step is a declared transition (`restore->load`, `load->dynamic`, `dynamic->return`) composed from three layers:

1. The catalog's `safety_baseline`, applied to every transition of every family. Setback, complete-history and response checks are `product_safety`, so no profile can remove them; the reviewed-exposure check is `data_sufficiency`:
   - no unresolved setback
   - complete episode history
   - at least one completed exposure to reviewed work from the current stage
   - during-session response not worse
   - next-day response known and not worse
2. Family requirements a source supports for the whole family. There are none today.
3. The profile's `transition_overrides`. These add region-specific requirements, remove non-safety requirements, or close a transition (an exception). Every override states a `reason`.

Each requirement declares its `kind` and its `basis`:

| Basis | Meaning | Rules |
| --- | --- | --- |
| `clinical` | Source-backed readiness criterion | Must cite `sources`. A transition with no clinical requirement can never promote. |
| `product_safety` | App-wide safety invariant (never progress on worse, stopped or unknown) | Cannot cite clinical sources; a profile cannot remove it. |
| `data_sufficiency` | Enough observation exists to evaluate | May carry an observation `minimum`. It is labelled as a product data requirement, never as clinical readiness. |

Requirement kinds:

- `completed_reviewed_exposure`. Work performed as shown (quantified, or "done as shown") on this policy's reviewed drill for the stage being left. It must match the bank content (`bank_hash`) and have a stated demand. With `requires_defined_dose`, "done as shown" counts only when the prescription carried a defined dose; self-paced work never counts as completing a dose.
- `during_session_response` / `next_day_response`. Evaluated on the latest reviewed response group. `not_reported`, `not_sure` and `not_yet_known` are unknown, never a pass.
- `no_unresolved_setback`. A current worse report or a negative latest response group fails it. An older negative that a later report resolved stays unknown until a profile defines a sourced resolution rule.
- `complete_history`. Truncated history is unknown.
- `measured_dose`. Requires a quantified completion. Use it only when the transition really needs a measured dose; it is never a global rule.
- `functional_checkpoint`. A named check from the catalog's `functional_checkpoints`. If the app does not capture its input, the result is `missing_input` and progression stays blocked. Data cannot claim capture: only `CAPTURED_FUNCTIONAL_CHECKPOINTS` in `api/contracts/rehab_progression.py` makes a checkpoint evaluable, and today it is empty.
- `minimum_observations`. A count of distinct response groups (one athlete answer copied onto several bundle drills counts once). As `data_sufficiency` it is a product requirement; as `clinical` it needs a source for that number.

## The one progression path

`api/contracts/rehab_progression.py` is the only stage-progression evaluator for policy-backed episodes:

- `resolve_reviewed_progression` applies the unchanged baseline (CALM/RESTORE plus the setback hold).
- Then, one rung at a time, it evaluates the composed transition out of the current stage. It promotes only when the transition is open, has a clinical requirement, every requirement passes, and the target stage is in the policy's `live_stages`.
- `evaluate_transition` is pure. It reads only exact athlete/injury/episode/region/side exposure events (`api/contracts/rehab_evidence.py`).
- Clinician clearance, camp phase, elapsed time and whole-athlete signals are not inputs.

The outcome is exposed as `rehab_decision.progression.next_transition`: status (`met`, `blocked`, `closed`), per-requirement results, `missing_inputs` and ignored-evidence counts. Today logs it as `rehab_next_transition` without any extra reads.

`ClinicalPolicy` validation keeps activation honest:

- A stage above RESTORE may be live only if every lower stage is live, an open transition into it declares a sourced clinical criterion, and the profile has a reviewed prescription for it.
- Only promotable transitions are part of the policy content hash. So adding the safety baseline left existing hashes, and therefore accepted frozen Today snapshots, unchanged.

### Removed or retired paths

- `api/contracts/load_eligibility.py` and its `LOAD_CRITERIA_REGISTRY` were removed. They were a second, per-injury-type rule registry, shadow-only, with no entries. They also did an extra exposure read per injury in Today. Their evidence primitives now live in `rehab_evidence.py`, used by the one evaluator.
- `ClinicalTransition` (count-based, never used, rejected on active policies) was replaced by requirement-based `PathwayTransition`.
- The pre-pathway policy file format is still readable (the equivalence fixture uses it), but it cannot declare transitions or a live stage above RESTORE. It is not an activation route.
- The "v1 routines are limited to calm and restore" and "disabled in v1" bans were replaced by the structural activation rules above.
- `rehab_stage.MAX_RESOLVABLE_STAGE` remains the ceiling of the baseline report ladder only.

## Adding coverage

To add a regional profile, for example calf strain, add one entry to `profiles`:

```json
{
  "policy_id": "calf_strain", "version": 1, "pathway_family": "muscle_strain",
  "region": "calf", "injury_type": "strain", "evidence_sources": ["…"],
  "prescriptions": [ … reviewed drills with bank hashes, stages, instructions, sources … ],
  "stage_bundles": { … }, "blocked_regions": ["calf"], "contact_limit": "none",
  "live_stages": ["calm", "restore"],
  "transition_overrides": {
    "restore->load": {"reason": "…", "add_requirements": [ … sourced clinical criteria … ]}
  },
  "status": "active", "activation": "live", "content_hash": "…"
}
```

Workflow:

1. Mark the chosen drills `reviewed` in `data/rehab_metadata_review.json` and apply them; the ledger remains the review gate. Pick only enough good drills for useful stage coverage. Unreviewed entries stay `needs_review`; 100% bank review is not a prerequisite.
2. Write the profile with sources. Compute `content_hash` with `policy_review_hash(compose_policy(catalog, profile))`; the seed tools show the pattern.
3. To open LOAD, add sourced clinical requirements to `restore->load`, add reviewed LOAD prescriptions, then add `"load"` to `live_stages`. DYNAMIC and RETURN follow the same pattern, one rung at a time.
4. If a source's criterion needs an input the app does not capture, add the checkpoint to `functional_checkpoints` and require it. It reports `missing_input` until code reads that input and adds the id to `CAPTURED_FUNCTIONAL_CHECKPOINTS`.
5. Run `python tools/validate_rehab_clinical.py`, `python tools/validate_rehab_bank.py`, `python tools/validate_rehab_metadata_review.py` and the rehab tests.

A requirement shared by every profile in a family belongs in that family's `transitions`, but only when a source supports it for the whole family. No progression code changes are needed for new coverage.

## Current state and what still blocks higher stages

- `chest_strain` and `ankle_sprain` retain their previous reviewed prescriptions, live stages, bundles and policy hashes. `tests/fixtures/rehab_clinical_policies_v2_legacy.json` freezes that file, and `tests/test_rehab_pathway_equivalence.py` proves identical decisions, schedules, reconciled snapshots, Today views and generation output. The strain rollout adds CALM/RESTORE profiles for hamstring, calf, groin, quads, biceps, triceps and shoulder, and repairs all 28 original strain exercises in these regions plus chest. See `strain-family-rollout.md`.
- No profile declares a clinical criterion, so no transition is promotable. LOAD, DYNAMIC and RETURN are closed for every user.
- Sprain/instability adds nine regional profiles: ankle, knee and shoulder instability, plus toe, wrist, elbow, shoulder, hand and finger sprains. The existing ankle sprain anchor and all strain profiles retain their policy hashes. The whole 117-drill pre-rollout inventory is in `sprain-family-bank-audit.json`; rollout details are in `sprain-family-rollout.md`.
- Tendonitis adds Achilles, shoulder, biceps, forearm, elbow, wrist, hand and fingers CALM/RESTORE profiles. Six reviewed resistance drills remain dormant inventory. Every previous profile and original bank identity is preserved. No functional checkpoint is currently captured, so no tendon LOAD/DYNAMIC/RETURN transition is activated; see `tendon-family-rollout.md` for regional sources and missing inputs.
- Missing for real progression:
  - Sourced clinical criteria per family/profile.
  - Prescription-level approval of LOAD/DYNAMIC/RETURN drills; a mechanical bank review alone does not activate them.
  - Captured functional inputs (`pain_free_walking`, `low_speed_running_tolerance`, `pain_free_submaximal_isometric` are declared, none captured).
  - Defined source-backed doses where a criterion needs completed dose.
  - A sourced rule for when an older negative response is resolved.
- The strain coverage rollout generalizes unknown-side baseline guidance attribution using exact frozen profile provenance. Apply `supabase/migrations/20261002234842_pathway_profile_unknown_side.sql` before activating its new profiles. Unknown-side feedback never qualifies positive advanced-stage capacity evidence. See `strain-family-rollout.md` for the full inventory and rollout boundaries.
