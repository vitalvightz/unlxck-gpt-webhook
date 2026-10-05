# Surface/wound safety review

Reviewed 2026-10-05 against Main `7143f25f12c8b7017a065b9d9227484c3073a719`.
Audited every drill for abrasion, cut, laceration, graze and blister: **104 identities**,
21 distinct instruction templates. All three camp phases were inspected.

## Decision and scope

Option A: `heel_blister_sterile_drainage_if_tense` is deprecated from automatic
output. The unchanged bank is archival inventory, not permission to prescribe.
25 identities are approved as-is; 21 are clinician-only, 32 are removed from
automatic output, 25 require review, and 1 is deprecated. All 79 non-approved
identities are filtered. No individual bank instruction was rewritten or deleted.
Uncertain exclusions are conservative approval decisions, not claims that every
underlying dressing, topical agent or prevention technique is medically unsafe.

The explicit review in `data/safety/surface_wound_review.json` binds approval to
both ID and the exact name/notes hash. Unknown IDs and edited approved content
fail closed. If no approved match remains, legacy surface selection returns the
single consolidated wound-care note. Existing safe blister protection is retained.
The separate safety ledger is tested directly; it is not a training bank target.

## Reachability before the change

Reproduced: `rehab_drill_options_for_phase('blister', 'heel', 'GPP')` returned
the needle instruction as the third option with the default limit of four.
`normalize_rehab_location('heel')` includes heel and foot. There is no severity,
skin-integrity, clearance or clinician-role gate in this helper. It therefore
returns the instruction for any heel blister, regardless of wound state, in GPP.
The lower-level collector also exposes it for an explicit heel candidate; foot-only
candidates do not include heel. SPP/TAPER return the same identity's dressing/
competition wording rather than the puncture sentence.

Exact legacy path: bank -> `_collect_surface_drills` ->
`rehab_drill_options_for_phase` -> `_rehab_drills_for_phase` -> helper consumer.
The returned option contains raw rendered text and `drill=None`, so older name/text
snapshots may lack the stable bank ID. This is a real helper exposure, but **no
current automatic planner/Today route was found assigning this needle instruction**:

- `generate_rehab_protocols`, `format_injury_guardrails` and `build_coach_review_entries`
  skip surface exercise lists and render a consolidated note. That note is a constant;
  it is not assembled from bank drill instructions.
- Stage 2 `_build_rehab_slots` skips surface groups before calling the option helper;
  no surface exercise/alternate payload is created there.
- Today `_with_injury_policy` -> `resolve_injury_policy` returns `wound_care` before
  resolving a clinical prescription. The reviewed selector rejects surface pathways.
  The frontend injury-care status consumes that advisory outcome, not raw bank text.
- `_legacy_rehab_drills_for_episode` -> `_all_phase_drills` -> `_phase_drill_line`
  is another legacy render adapter. It now filters withdrawn surface inventory too.
- `recovery._fetch_injury_drills` reads the bank independently. No production call
  site was found. Its ASCII phase splitter currently fails to match the surface
  bank's Unicode progression arrows. It is nevertheless guarded, with a test that
  enables the ASCII path so delimiter repair cannot silently expose unsafe content.
- `rehab_drill_by_id` can recover bank metadata for completion/snapshot callers;
  withdrawn surface identities now resolve to None. `api.rehab_labels` reads names
  for classification, never instructions, and ignores surface injury flags.

## Frozen prescriptions, completion and API output

`reconcile_session_prescription` previously deep-copied accepted work unchanged,
then applied current clinical gates. That could preserve legacy surface text even
when the current injury only receives advisory wound care, especially without
injury ownership. It now removes withdrawn identity blocks, puts the consolidated
guidance in the existing session objective, and
places changed accepted prescriptions on a safety hold. Exact saved names, IDs
and phase instruction fragments are recognised, including cues with no ID.
The same check covers live legacy session input before the no-policy early return.

Today sanitizes next-session and completion payload copies before building the
command view, including completed prescriptions that do not undergo reconciliation.
The completion mutation refuses training against a withdrawn saved prescription;
stopping already-started work remains available. `session_rehab_items` excludes
all surface inventory from rehab/exposure ownership, even if an old snapshot
contains drill metadata. Surface wound care remains advisory, not completable MSK work.
Tests exercise actual Today output and completion refusal with a saved needle block.

Stored plans/completion history are not migrated or rewritten. The guard recognises
reviewed inventory identities and exact legacy text, not arbitrary paraphrases or
unknown historical instructions. This does not certify every historical free-text
plan/export or add a generic medical-text scanner. No API endpoint serving the raw
rehab bank was found. Historical-data sampling is a separate follow-up if warranted.

## Evidence and safety boundaries

Directly checked sources on 2026-10-05:

- [NHS blisters](https://www.nhs.uk/conditions/blisters/): protection and cleanliness;
  avoid deliberate bursting/skin removal; avoid causative equipment until healed;
  seek help for very painful, recurrent or infected blisters. Needle treatment is
  described under GP treatment, not self-care. Supports drainage deprecation,
  exclusion of callus trimming, and preservation of intact-blister protection.
- [NHS cuts and grazes](https://www.nhs.uk/conditions/cuts-and-grazes/): rinse small
  wounds, dress and keep dressings clean/dry; professional assessment for serious
  wounds and infection. Supports closure exclusions and the note's escalation for
  uncontrolled bleeding, deep wounds, retained debris/objects and sensory/movement
  changes. Do not remove embedded objects. Medical treatment includes wound closure.
- [NATA acute skin trauma statement summary](https://www.nata.org/press-release/nata-publishes-new-position-statement-acute-skin-trauma-journal-athletic-training):
  dressings including nonadherent/hydrocolloid options, ongoing observation,
  clinician-dependent debridement, caution with antiseptics, and referral for
  contamination, tendon/nerve injury or infection. Supports dressing approvals
  and holding underspecified debridement/ointment content for review. It does not
  establish a blanket prohibition on all topical antimicrobials.

`contact boundary` in the identity table means the **existing conservative product
rule**, not a newly inferred universal medical return-to-play standard: open skin
routes to `surface_no_contact`; covering and low pain do not clear contact.
The old note said to return to full contact once closed; the replacement explicitly
preserves clinician/contact restrictions and says closure alone is insufficient.
Safe legacy helper lines now carry that restriction boundary. No return stages,
clearance scopes, routing classes, diagnostic thresholds or multi-injury priority
rules changed. Existing bleeding/infection/drainage/severity/red-flag gates remain
authoritative. Deep/gaping wounds, retained objects, bites/punctures, contamination,
and sensation/circulation changes are addressed in the note, without extending
the structured classifier's vocabulary or automatically diagnosing them.

No self-suturing, explicit foreign-body probing, flap removal, tissue cutting or
aggressive debridement instruction was found beyond the flagged drainage/trim and
ambiguous debride templates. No timed drainage threshold was added. Covering advice
does not disable infection checks. Product contact restrictions are deliberately
stricter than basic first-aid dressing advice.

## Preservation and verification

`rehab_bank.json`, `rehab_pathways.json`, `rehab_metadata_review.json`, duplicate
debt, vocabulary and rationalisation reports/baseline are unchanged. All 64 active
profiles, raw profile hashes, review hashes, bank IDs, stage activation and MSK
progression/completion behavior are preserved. No new database migration,
environment-variable change, frontend edit or deployment is required.

Run the focused surface-safety suite plus existing surface, Today, clearance,
multi-injury, completion, metadata, vocabulary, bundle and rationalisation suites.
Run the bank, clinical and metadata validators and rationalisation `--check`.
The broad bank audit reports existing non-surface debt; compare its output with
Main rather than claiming a clean strict whole-bank validation.

Validation results: 833 broader surface/Today/completion/metadata tests and 59
bundle/vocabulary tests passed. After final changes, 327 surface-safety/legacy
surface/clearance/Today tests and 112 surface-safety/rationalisation tests passed
(overlapping suites). All-bank Ruff, changed-module imports and `git diff --check`
passed. Clinical, rehab-bank, metadata, injury vocabulary and tag authority gates,
both migration checks and rationalisation `--check` passed. The broad bank audit
completed with unchanged existing debt (827 errors, 327 warnings), zero tag
vocabulary violations and zero config/rehab-schema errors. No frontend build,
full repository pytest run, production-data inspection or deployment was performed.

Changed files: `fightcamp/surface_wound_safety.py`,
`data/safety/surface_wound_review.json`, `fightcamp/rehab_protocols.py`,
`fightcamp/recovery.py`, `api/contracts/injury_policy.py`,
`api/services/today_service.py`, `api/services/rehab_completion_service.py`,
`tests/test_surface_wound_safety.py`, and this report.

Follow-up: clinically review the 25 uncertain identities and, separately, decide
whether to retire or replace the archived 54 clearly excluded identities. Do not
use the archival bank directly for future athlete-facing output. The allowlist
and content hash must remain the boundary. No broader duplicate or LOAD work is
part of this change.

## Complete identity review

Every non-`SAFE_AS_IS` row below is filtered; no row was deleted from the bank.

| Identity | Classification | Reason | Evidence |
| --- | --- | --- | --- |
| ankle_blister_footwear_sock_strategy | UNCERTAIN_REQUIRES_REVIEW | Pre-taping before sessions lacks instruction to avoid causative equipment until healed. | NHS blisters |
| ankle_blister_protect_the_intact_blister | SAFE_AS_IS | Do not pop; padded/hydrocolloid protection and avoid friction. | NHS blisters |
| chest_abrasion_friction_offloading | REMOVE_FROM_AUTOMATIC_OUTPUT | Taping before grappling over raw skin implies contact readiness. | contact boundary |
| chest_abrasion_skin_barrier_ointment | UNCERTAIN_REQUIRES_REVIEW | Unspecified antiseptic on raw skin with routine repeat dosing; agents/indications differ. Not a blanket ban on topical treatment. | NATA trauma |
| elbow_abrasion_debride_clean_thoroughly | UNCERTAIN_REQUIRES_REVIEW | Name says debride; rinse ALL debris lacks embedded-object/remaining-contamination boundary. Text does not explicitly order cutting or probing. | NHS cuts; NATA trauma |
| elbow_abrasion_joint_pad_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Explicit live rolls over raw skin protected only by a pad. | contact boundary |
| elbow_cut_daily_infection_check | SAFE_AS_IS | Infection surveillance and review/pause; closed skin is not independent clearance. | NHS cuts |
| elbow_cut_no_reopen_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Padding before sparring implies conditional contact with a healing wound. | contact boundary |
| elbow_graze_joint_pad_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Explicit live rolls over raw skin protected only by a pad. | contact boundary |
| elbow_graze_skin_barrier_ointment | UNCERTAIN_REQUIRES_REVIEW | Unspecified antiseptic on raw skin with routine repeat dosing; agents/indications differ. Not a blanket ban on topical treatment. | NATA trauma |
| elbow_laceration_no_reopen_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Padding before sparring implies conditional contact with a healing wound. | contact boundary |
| elbow_laceration_scar_mobility_once_closed | UNCERTAIN_REQUIRES_REVIEW | Closure alone scopes scar massage and contact tolerance; no patient/assessment context. | contact boundary |
| eye_cut_brow_orbital_cut_care | CLINICIAN_ONLY | Automatic closure near the eye and sparring advice without assessment. | NHS cuts; contact boundary |
| eye_cut_no_reopen_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Padding before sparring implies conditional contact with a healing wound. | contact boundary |
| eye_laceration_brow_orbital_cut_care | CLINICIAN_ONLY | Automatic closure near the eye and sparring advice without assessment. | NHS cuts; contact boundary |
| eye_laceration_clean_approximate_edges | CLINICIAN_ONLY | Automatic closure with glue/strips and repeated edge taping without assessment. | NHS cuts |
| face_abrasion_debride_clean_thoroughly | UNCERTAIN_REQUIRES_REVIEW | Name says debride; rinse ALL debris lacks embedded-object/remaining-contamination boundary. Text does not explicitly order cutting or probing. | NHS cuts; NATA trauma |
| face_abrasion_facial_wound_protection | CLINICIAN_ONLY | Butterfly closure; headgear/control sparring is not wound or contact clearance. | NHS cuts; contact boundary |
| face_cut_clean_approximate_edges | CLINICIAN_ONLY | Automatic closure with glue/strips and repeated edge taping without assessment. | NHS cuts |
| face_cut_facial_wound_protection | CLINICIAN_ONLY | Butterfly closure; headgear/control sparring is not wound or contact clearance. | NHS cuts; contact boundary |
| face_graze_facial_wound_protection | CLINICIAN_ONLY | Butterfly closure; headgear/control sparring is not wound or contact clearance. | NHS cuts; contact boundary |
| face_graze_skin_barrier_ointment | UNCERTAIN_REQUIRES_REVIEW | Unspecified antiseptic on raw skin with routine repeat dosing; agents/indications differ. Not a blanket ban on topical treatment. | NATA trauma |
| face_laceration_clean_approximate_edges | CLINICIAN_ONLY | Automatic closure with glue/strips and repeated edge taping without assessment. | NHS cuts |
| face_laceration_facial_wound_protection | CLINICIAN_ONLY | Butterfly closure; headgear/control sparring is not wound or contact clearance. | NHS cuts; contact boundary |
| fingers_blister_deroof_infection_watch | REMOVE_FROM_AUTOMATIC_OUTPUT | Healed OR fully protected before fight night suggests dressing alone clears contact. | NHS blisters; contact boundary |
| fingers_blister_grip_friction_strategy | REMOVE_FROM_AUTOMATIC_OUTPUT | Trim torn calluses flat could remove living blister skin; no clinical scope. | NHS blisters |
| fingers_cut_knuckle_cut_wrapping | CLINICIAN_ONLY | Automatic knuckle closure; hand wounds may need assessment. | NHS cuts |
| fingers_cut_waterproof_occlusive_dressing | SAFE_AS_IS | Clean dry dressing, changed when wet/dirty; does not authorise contact. | NHS cuts |
| foot_blister_footwear_sock_strategy | UNCERTAIN_REQUIRES_REVIEW | Pre-taping before sessions lacks instruction to avoid causative equipment until healed. | NHS blisters |
| foot_blister_protect_the_intact_blister | SAFE_AS_IS | Do not pop; padded/hydrocolloid protection and avoid friction. | NHS blisters |
| foot_cut_daily_infection_check | SAFE_AS_IS | Infection surveillance and review/pause; closed skin is not independent clearance. | NHS cuts |
| foot_cut_waterproof_occlusive_dressing | SAFE_AS_IS | Clean dry dressing, changed when wet/dirty; does not authorise contact. | NHS cuts |
| foot_graze_friction_offloading | REMOVE_FROM_AUTOMATIC_OUTPUT | Taping before grappling over raw skin implies contact readiness. | contact boundary |
| foot_graze_skin_barrier_ointment | UNCERTAIN_REQUIRES_REVIEW | Unspecified antiseptic on raw skin with routine repeat dosing; agents/indications differ. Not a blanket ban on topical treatment. | NATA trauma |
| forearm_abrasion_friction_offloading | REMOVE_FROM_AUTOMATIC_OUTPUT | Taping before grappling over raw skin implies contact readiness. | contact boundary |
| forearm_abrasion_moist_healing_dressing | SAFE_AS_IS | Non-stick/hydrocolloid protection; does not authorise contact. | NATA trauma |
| forearm_cut_no_reopen_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Padding before sparring implies conditional contact with a healing wound. | contact boundary |
| forearm_cut_waterproof_occlusive_dressing | SAFE_AS_IS | Clean dry dressing, changed when wet/dirty; does not authorise contact. | NHS cuts |
| forearm_graze_friction_offloading | REMOVE_FROM_AUTOMATIC_OUTPUT | Taping before grappling over raw skin implies contact readiness. | contact boundary |
| forearm_graze_moist_healing_dressing | SAFE_AS_IS | Non-stick/hydrocolloid protection; does not authorise contact. | NATA trauma |
| forearm_laceration_clean_approximate_edges | CLINICIAN_ONLY | Automatic closure with glue/strips and repeated edge taping without assessment. | NHS cuts |
| forearm_laceration_no_reopen_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Padding before sparring implies conditional contact with a healing wound. | contact boundary |
| hand_abrasion_daily_infection_check | SAFE_AS_IS | Infection surveillance and review/pause; closed skin is not independent clearance. | NHS cuts |
| hand_abrasion_friction_offloading | REMOVE_FROM_AUTOMATIC_OUTPUT | Taping before grappling over raw skin implies contact readiness. | contact boundary |
| hand_blister_grip_friction_strategy | REMOVE_FROM_AUTOMATIC_OUTPUT | Trim torn calluses flat could remove living blister skin; no clinical scope. | NHS blisters |
| hand_blister_protect_the_intact_blister | SAFE_AS_IS | Do not pop; padded/hydrocolloid protection and avoid friction. | NHS blisters |
| hand_cut_daily_infection_check | SAFE_AS_IS | Infection surveillance and review/pause; closed skin is not independent clearance. | NHS cuts |
| hand_cut_knuckle_cut_wrapping | CLINICIAN_ONLY | Automatic knuckle closure; hand wounds may need assessment. | NHS cuts |
| hand_graze_friction_offloading | REMOVE_FROM_AUTOMATIC_OUTPUT | Taping before grappling over raw skin implies contact readiness. | contact boundary |
| hand_graze_skin_barrier_ointment | UNCERTAIN_REQUIRES_REVIEW | Unspecified antiseptic on raw skin with routine repeat dosing; agents/indications differ. Not a blanket ban on topical treatment. | NATA trauma |
| hand_laceration_clean_approximate_edges | CLINICIAN_ONLY | Automatic closure with glue/strips and repeated edge taping without assessment. | NHS cuts |
| hand_laceration_knuckle_cut_wrapping | CLINICIAN_ONLY | Automatic knuckle closure; hand wounds may need assessment. | NHS cuts |
| heel_blister_footwear_sock_strategy | UNCERTAIN_REQUIRES_REVIEW | Pre-taping before sessions lacks instruction to avoid causative equipment until healed. | NHS blisters |
| heel_blister_sterile_drainage_if_tense | DEPRECATE | Athlete-directed needle puncture/drainage. GP assessment/treatment is separate. | NHS blisters |
| hip_abrasion_friction_offloading | REMOVE_FROM_AUTOMATIC_OUTPUT | Taping before grappling over raw skin implies contact readiness. | contact boundary |
| hip_abrasion_skin_barrier_ointment | UNCERTAIN_REQUIRES_REVIEW | Unspecified antiseptic on raw skin with routine repeat dosing; agents/indications differ. Not a blanket ban on topical treatment. | NATA trauma |
| hip_graze_friction_offloading | REMOVE_FROM_AUTOMATIC_OUTPUT | Taping before grappling over raw skin implies contact readiness. | contact boundary |
| hip_graze_moist_healing_dressing | SAFE_AS_IS | Non-stick/hydrocolloid protection; does not authorise contact. | NATA trauma |
| jaw_cut_facial_wound_protection | CLINICIAN_ONLY | Butterfly closure; headgear/control sparring is not wound or contact clearance. | NHS cuts; contact boundary |
| jaw_cut_waterproof_occlusive_dressing | SAFE_AS_IS | Clean dry dressing, changed when wet/dirty; does not authorise contact. | NHS cuts |
| jaw_laceration_facial_wound_protection | CLINICIAN_ONLY | Butterfly closure; headgear/control sparring is not wound or contact clearance. | NHS cuts; contact boundary |
| jaw_laceration_no_reopen_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Padding before sparring implies conditional contact with a healing wound. | contact boundary |
| knee_abrasion_joint_pad_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Explicit live rolls over raw skin protected only by a pad. | contact boundary |
| knee_abrasion_moist_healing_dressing | SAFE_AS_IS | Non-stick/hydrocolloid protection; does not authorise contact. | NATA trauma |
| knee_cut_no_reopen_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Padding before sparring implies conditional contact with a healing wound. | contact boundary |
| knee_cut_scar_mobility_once_closed | UNCERTAIN_REQUIRES_REVIEW | Closure alone scopes scar massage and contact tolerance; no patient/assessment context. | contact boundary |
| knee_graze_joint_pad_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Explicit live rolls over raw skin protected only by a pad. | contact boundary |
| knee_graze_skin_barrier_ointment | UNCERTAIN_REQUIRES_REVIEW | Unspecified antiseptic on raw skin with routine repeat dosing; agents/indications differ. Not a blanket ban on topical treatment. | NATA trauma |
| knee_laceration_daily_infection_check | SAFE_AS_IS | Infection surveillance and review/pause; closed skin is not independent clearance. | NHS cuts |
| knee_laceration_no_reopen_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Padding before sparring implies conditional contact with a healing wound. | contact boundary |
| neck_abrasion_debride_clean_thoroughly | UNCERTAIN_REQUIRES_REVIEW | Name says debride; rinse ALL debris lacks embedded-object/remaining-contamination boundary. Text does not explicitly order cutting or probing. | NHS cuts; NATA trauma |
| neck_abrasion_friction_offloading | REMOVE_FROM_AUTOMATIC_OUTPUT | Taping before grappling over raw skin implies contact readiness. | contact boundary |
| neck_cut_clean_approximate_edges | CLINICIAN_ONLY | Automatic closure with glue/strips and repeated edge taping without assessment. | NHS cuts |
| neck_cut_no_reopen_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Padding before sparring implies conditional contact with a healing wound. | contact boundary |
| neck_graze_debride_clean_thoroughly | UNCERTAIN_REQUIRES_REVIEW | Name says debride; rinse ALL debris lacks embedded-object/remaining-contamination boundary. Text does not explicitly order cutting or probing. | NHS cuts; NATA trauma |
| neck_graze_skin_barrier_ointment | UNCERTAIN_REQUIRES_REVIEW | Unspecified antiseptic on raw skin with routine repeat dosing; agents/indications differ. Not a blanket ban on topical treatment. | NATA trauma |
| neck_laceration_clean_approximate_edges | CLINICIAN_ONLY | Automatic closure with glue/strips and repeated edge taping without assessment. | NHS cuts |
| neck_laceration_no_reopen_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Padding before sparring implies conditional contact with a healing wound. | contact boundary |
| shin_abrasion_debride_clean_thoroughly | UNCERTAIN_REQUIRES_REVIEW | Name says debride; rinse ALL debris lacks embedded-object/remaining-contamination boundary. Text does not explicitly order cutting or probing. | NHS cuts; NATA trauma |
| shin_abrasion_shin_sleeve_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Guard/sleeve protection alone is not contact clearance. | contact boundary |
| shin_blister_fix_the_friction_source | UNCERTAIN_REQUIRES_REVIEW | Pre-taping/lubricant before sessions lacks distinction between prevention and an active blister. | NHS blisters |
| shin_blister_shin_sleeve_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Guard/sleeve protection alone is not contact clearance. | contact boundary |
| shin_cut_daily_infection_check | SAFE_AS_IS | Infection surveillance and review/pause; closed skin is not independent clearance. | NHS cuts |
| shin_cut_waterproof_occlusive_dressing | SAFE_AS_IS | Clean dry dressing, changed when wet/dirty; does not authorise contact. | NHS cuts |
| shin_graze_shin_sleeve_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Guard/sleeve protection alone is not contact clearance. | contact boundary |
| shin_graze_skin_barrier_ointment | UNCERTAIN_REQUIRES_REVIEW | Unspecified antiseptic on raw skin with routine repeat dosing; agents/indications differ. Not a blanket ban on topical treatment. | NATA trauma |
| shin_laceration_clean_approximate_edges | CLINICIAN_ONLY | Automatic closure with glue/strips and repeated edge taping without assessment. | NHS cuts |
| shin_laceration_waterproof_occlusive_dressing | SAFE_AS_IS | Clean dry dressing, changed when wet/dirty; does not authorise contact. | NHS cuts |
| shoulder_abrasion_friction_offloading | REMOVE_FROM_AUTOMATIC_OUTPUT | Taping before grappling over raw skin implies contact readiness. | contact boundary |
| shoulder_abrasion_moist_healing_dressing | SAFE_AS_IS | Non-stick/hydrocolloid protection; does not authorise contact. | NATA trauma |
| toe_blister_footwear_sock_strategy | UNCERTAIN_REQUIRES_REVIEW | Pre-taping before sessions lacks instruction to avoid causative equipment until healed. | NHS blisters |
| toe_blister_offload_substitute | SAFE_AS_IS | Reduce irritated-tissue volume and substitute low-friction work; no contact clearance. | NHS blisters |
| unspecified_abrasion_debride_clean_thoroughly | UNCERTAIN_REQUIRES_REVIEW | Name says debride; rinse ALL debris lacks embedded-object/remaining-contamination boundary. Text does not explicitly order cutting or probing. | NHS cuts; NATA trauma |
| unspecified_abrasion_moist_healing_dressing | SAFE_AS_IS | Non-stick/hydrocolloid protection; does not authorise contact. | NATA trauma |
| unspecified_blister_fix_the_friction_source | UNCERTAIN_REQUIRES_REVIEW | Pre-taping/lubricant before sessions lacks distinction between prevention and an active blister. | NHS blisters |
| unspecified_blister_protect_the_intact_blister | SAFE_AS_IS | Do not pop; padded/hydrocolloid protection and avoid friction. | NHS blisters |
| unspecified_cut_clean_approximate_edges | CLINICIAN_ONLY | Automatic closure with glue/strips and repeated edge taping without assessment. | NHS cuts |
| unspecified_cut_no_reopen_protection | REMOVE_FROM_AUTOMATIC_OUTPUT | Padding before sparring implies conditional contact with a healing wound. | contact boundary |
| unspecified_graze_debride_clean_thoroughly | UNCERTAIN_REQUIRES_REVIEW | Name says debride; rinse ALL debris lacks embedded-object/remaining-contamination boundary. Text does not explicitly order cutting or probing. | NHS cuts; NATA trauma |
| unspecified_graze_skin_barrier_ointment | UNCERTAIN_REQUIRES_REVIEW | Unspecified antiseptic on raw skin with routine repeat dosing; agents/indications differ. Not a blanket ban on topical treatment. | NATA trauma |
| unspecified_laceration_clean_approximate_edges | CLINICIAN_ONLY | Automatic closure with glue/strips and repeated edge taping without assessment. | NHS cuts |
| unspecified_laceration_daily_infection_check | SAFE_AS_IS | Infection surveillance and review/pause; closed skin is not independent clearance. | NHS cuts |
| upper_back_abrasion_friction_offloading | REMOVE_FROM_AUTOMATIC_OUTPUT | Taping before grappling over raw skin implies contact readiness. | contact boundary |
| upper_back_abrasion_moist_healing_dressing | SAFE_AS_IS | Non-stick/hydrocolloid protection; does not authorise contact. | NATA trauma |
