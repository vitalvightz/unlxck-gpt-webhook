# Tendonitis regional production coverage

Based on Main `ebbac9dd` after #2719. This uses the existing `tendon_rehab`
family, canonical `tendonitis` type, profile activation boundary, bank, ledger
and progression engine. No architecture, taxonomy, migration or engine is added.

## Original whole-family inventory

The pre-change audit contains every ID, original note, review state, stage,
mechanical field, duplicate link and source hash in
`tendon-family-bank-audit.json`; the readable inventory is
`tendon-family-bank-audit.md`.

| Canonical region | Original drills | New profile | Original disposition |
| --- | ---: | --- | --- |
| foot | 2 | No | Fascia/stretch/percussion content does not identify a tendon condition |
| heel | 2 | No | Fascia/toe-elevated loading does not establish Achilles diagnosis |
| shin | 4 | No | Duplicate wall raises/percussion; no identified regional tendon condition |
| achilles | 4 | Yes | One fixed floor-level LOAD repair; duplicate and percussion copies deferred |
| groin | 2 | No | Adductor versus other groin entities not established; band/Cossack demand unresolved |
| obliques | 2 | No | Generic trunk loading does not establish a regional tendon condition |
| lower back | 4 | No | Mixed hinge/hyperextension variants with no identified tendon condition |
| upper back | 2 | No | Scapular exercises do not establish a tendon diagnosis |
| chest | 2 | No | Pec stretch/press without tendon-site or condition evidence |
| shoulder | 4 | Yes | One fixed dormant scaption repair; unsupported raises/Y-to-W variants deferred |
| biceps | 2 | Yes | One fixed dormant seated-curl repair; full-line band variant deferred |
| triceps | 2 | No | Resistance variants lack a verified condition-specific prescription/selection rule |
| forearm | 2 | Yes | One fixed dormant extensor repair; reverse-curl variant deferred |
| elbow | 2 | Yes | One fixed dormant extensor repair; triceps/explosive variant deferred |
| wrist | 6 | Yes | Supported turn reused for RESTORE; one dormant flexor repair; four others deferred |
| hand | 4 | Yes | All four resisted/unclear originals deferred; unloaded baseline added |
| fingers | 2 | Yes | Putty/ball originals deferred; unloaded baseline added |
| neck | 2 | No | Cervical resistance without an identified tendon condition |
| jaw | 2 | No | Bite/TMJ variants lack a defensible tendon prescription |
| unspecified | 8 | No | Target/equipment/dose vary; no regional diagnosis; never a tendon profile |
| **Total** | **60** | **8** | **7 repaired; 53 originals remain needs_review** |

There is no knee/patellar tendonitis group. No knee profile is invented.
Before this change all 60 originals were `needs_review`, all stages were null,
and load/impact/velocity/equipment lacked reviewed values. 49 entries mixed
camp phases; 33 had variable-demand instructions. Four exact duplicate pairs
exist (shin wall raises/percussion; Achilles drops/percussion). Near duplicates
include the lower-back hinge/hyper variants, regional wrist-extensor eccentrics
and unspecified holds/eccentrics. Duplicated original IDs are retained but not
approved. The snapshot is an audit, not clinical approval.

## Counts and bank/profile separation

- Original tendon inventory: 60; final tendon inventory: 75.
- Originals repaired/reviewed: 7, retaining every original ID and source history.
- Newly added/reviewed: 15 (eight CALM, seven RESTORE).
- Total tendon entries reviewed: 22; six are dormant LOAD inventory.
- Active identities: 16, including the repaired original wrist turn.
- The 15 added IDs are `{region}_tendonitis_recovery_support` for all eight
  activated regions, and `{region}_tendonitis_reviewed_restore` for Achilles,
  shoulder, biceps, forearm, elbow, hand and fingers. Wrist RESTORE reuses its
  original ID instead of adding an alias.
- Dormant originals in automatic profiles: 59 (53 unreviewed plus six reviewed
  LOAD drills). Nothing becomes active just because the ledger says reviewed.
- Active regional injury/type pairs increase from 18 to 26: **+8**, two live
  baseline stages each. This is baseline coverage, not eight complete graded
  resistance or return-to-sport protocols.

### The seven repaired identities

| Original ID | Current fixed movement | Stage | Activation |
| --- | --- | --- | --- |
| `achilles_tendonitis_eccentric_calf_drops_on_step` | Supported floor-level eccentric lowering; no step/deep dorsiflexion | LOAD | Dormant |
| `shoulder_tendonitis_banded_scaption_holds` | Individually advised fixed-range band hold; no overhead progression | LOAD | Dormant |
| `bicep_tendonitis_incline_db_curl_eccentric_focus` | Seated curl with arm by side; no incline stretch | LOAD | Dormant |
| `forearm_tendonitis_eccentric_wrist_extensions` | Supported fixed-weight extensor lowering | LOAD | Dormant |
| `elbow_tendonitis_eccentric_reverse_wrist_curls` | Supported fixed-weight extensor lowering | LOAD | Dormant |
| `wrist_tendonitis_eccentric_wrist_flexion_with_dumbbell` | Supported fixed-weight flexor lowering | LOAD | Dormant |
| `wrist_tendonitis_pronation_supination_twists` | Supported unresisted comfortable turn; no pulses/weight | RESTORE | Live |

External weight/band demand remains `unknown` where no measured resistance is
defined. Mechanical classification does not establish efficacy, dose or
eligibility for that condition. No reps, sets, holds, numeric external weight,
pain ceiling, clinical severity threshold or return criterion is encoded.
Existing low/moderate product eligibility and minimum scheduling gaps are
preserved; they are not clinical exercise doses.
The resolved Achilles step-drop duplicate allowance is removed from the debt
ledger: the repaired floor-level variant no longer duplicates the untouched,
unreviewed step variant. No original copy is removed or automatically approved.

## Profile sources, baseline and LOAD decision

All profiles activate **CALM and RESTORE only**. CALM provides regional activity
modification and medical escalation advice; it does not impose prolonged rest,
universal isometric-first treatment or an acute healing timeline. RESTORE is
comfortable regional movement, not proof of strength or loading readiness.
Pain-free movement is a conservative product limit here, not a claim that all
tendon exercise must be pain-free. No eccentrics-superiority claim is made.
The seated Achilles exercise is classified as low-demand tendon loading, so
the existing Today readiness hold applies even though it belongs to RESTORE.

All profiles use [NHS tendonitis guidance](https://www.nhs.uk/conditions/tendonitis/)
for comfortable movement, aggravating activity modification and rupture concern.
Region-specific sources were opened and inspected directly on 2026-10-03:

| Policy | RESTORE | Additional evidence | Exact missing evidence/input for LOAD |
| --- | --- | --- | --- |
| `achilles_tendonitis` | Seated heel movement, no added weight | [BNSSG Achilles guidance](https://myjointhealthhub.bnssg.nhs.uk/foot-ankle-pain/achilles-tendinopathy/), [Kent insertional guidance](https://www.kentcht.nhs.uk/leaflet/achilles-insertional-tendinopathy/) | Source progression refers to the exercise being doable/easy and comfortable heel-raise performance. App has no per-exercise functional ease/heel-raise assessment, measured resistance, or insertional/midportion identification. Below-floor loading remains excluded. |
| `shoulder_tendonitis` | Unweighted rotation, elbow by side | [RJAH rotator-cuff-related guidance](https://www.rjah.nhs.uk/our-services/therapy/supported-self-care/rotator-cuff-related-shoulder-pain/) | Source adds weight when unweighted movement is easy; app does not capture that movement-quality/ease checkpoint, assessed usable range or selected resistance. No rule proves the repaired band hold suitable for every shoulder tendon. |
| `biceps_tendonitis` | Comfortable unloaded elbow movement | [Bexley biceps guidance](https://msk-bexley.nhs.uk/conditions/shoulder-pain/biceps-tendinopathy) | Source concerns proximal shoulder tendon and individually tolerated resistance. Product cannot distinguish proximal/distal tendon site, assess curl range/strength or select resistance. No common validated RESTORE-to-curl threshold is established. |
| `forearm_tendonitis` | Supported unweighted wrist movement | [Bexley elbow tendon guidance](https://msk-bexley.nhs.uk/conditions/elbow-pain/tennis-elbow), [CUH active wrist movement](https://www.cuh.nhs.uk/patient-information/hand-therapy-active-wrist-exercises/) | Product lacks flexor/extensor tendon-site assessment, resisted grip/wrist functional testing and selected tolerable resistance. An extensor protocol cannot be assigned to every forearm tendon. |
| `elbow_tendonitis` | Comfortable unloaded elbow movement | [Bexley elbow tendon guidance](https://msk-bexley.nhs.uk/conditions/elbow-pain/tennis-elbow) | Lateral/medial/posterior site, clinically assessed grip/wrist-extension function and chosen resistance are not captured. Lateral-elbow pain/dose allowances cannot be generalized. |
| `wrist_tendonitis` | Supported unweighted turn | [CUH active wrist movement](https://www.cuh.nhs.uk/patient-information/hand-therapy-active-wrist-exercises/), [Dorset tenosynovitis guidance](https://www.mskdorset.nhs.uk/hand-and-wrist-pain/hand-and-wrist-pain-de-quervains-tenosynovitis/) | Flexor/extensor/thumb-sheath subtype, comfortable resisted function and prescribed resistance are absent. Gentle movement advice does not establish when the dormant flexor eccentric is appropriate. |
| `hand_tendonitis` | Gentle unweighted hook/return | [North Tees trigger-finger guidance](https://www.nth.nhs.uk/resources/hand-therapy-trigger-finger/), [North Tees tendon glides](https://www.nth.nhs.uk/resources/hand-therapy-tendon-gliding-exercises/) | No reviewed LOAD prescription or verified broad hand-tendon loading threshold; app lacks tendon/site/splint assessment, observed catching/locking and measured graded grip tolerance/resistance. Unloaded mobility is not permission for a gripper. |
| `fingers_tendonitis` | Gentle unweighted bend/straighten | [North Tees trigger-finger guidance](https://www.nth.nhs.uk/resources/hand-therapy-trigger-finger/), [North Tees tendon glides](https://www.nth.nhs.uk/resources/hand-therapy-tendon-gliding-exercises/) | No reviewed LOAD prescription or verified broad finger-tendon loading threshold; app lacks individual tendon/site/protection assessment, observed locking and measured putty/ball tolerance/resistance. |

These baselines do not infer a subtype diagnosis: hand/finger gliding is used
only as gentle movement, not an automatic trigger-finger or postoperative
protocol. Existing surgery/rupture gates remain authoritative. Biceps movement
does not import a proximal loading protocol into a distal complaint. Forearm,
elbow and wrist baselines do not assign extensor strengthening to flexor pain.

### Progression investigation

The rotator-cuff CPG (JOSPT 2025, DOI 10.2519/jospt.2025.13182) and lateral-elbow
CPG (JOSPT 2022, DOI 10.2519/jospt.2022.0302) were investigated through primary
publisher/academy indexed text. Direct publisher/PDF fetches were blocked, so
no inaccessible CPG-specific numeric criterion was encoded. Directly readable
NHS sources above govern the concrete baseline content. Adductor and distal
biceps/triceps reviews were investigated; no diagnosis-specific groin or
triceps protocol was assigned from a broad region label.

`CAPTURED_FUNCTIONAL_CHECKPOINTS` remains empty. The product captures attributable
work, qualitative during/next-day responses and episode history; these are
valuable safety data, but are not a measured strength, comfortable functional
task, exercise-ease, tendon-site or prescribed-resistance checkpoint. No
clinical transition criterion is fabricated. **Zero RESTORE-to-LOAD transitions
are promotable. DYNAMIC and RETURN remain closed for every profile.**
The existing engine still requires a sourced clinical criterion, complete
history, no unresolved setback, every input passing and a live target stage.
Missing input fails closed; count/time/readiness/clearance cannot proxy it.

## Preservation and verification

All 18 previous profiles, hashes, prescriptions, decisions, schedules and frozen
snapshots are compared against their pre-tendon fixture. All 1,574 original bank
IDs survive; only the seven listed originals change. Existing injury taxonomy,
families, safety routes, RLS, migrations and engine code are untouched.

`test_tendon_family_coverage.py` checks exact region/type ownership, reviewed
identity/hash integrity, stale content, CALM/RESTORE, worsening, severe/high,
rupture/major tear/surgery/neurological gates, unrelated pain, unknown-side
recording without capacity evidence, closed-stage injection, dormant LOAD,
source history, original identity preservation, vocabulary and byte-idempotent
bank/ledger/profile seeding. Broader rehab tests cover multi-injury precedence,
readiness, ownership, delayed responses, allocation ceilings and existing
ankle/chest behavior. No production database mutation is required.

## Review clarifications

`phase_progression` describes camp-phase inventory availability, independently
of `rehab_stage`; it never grants recovery-stage access. Wrist tendonitis groups
containing the reviewed CALM/RESTORE baselines now list GPP, SPP and TAPER,
because those baselines are not restricted to late camp phases. Untouched
phase-keyed drills retain their own legacy notes and remain dormant.

Biceps tendon drills retain the bank's `bicep` target spelling. Clinical
selection now passes the existing registry aliases to both selector calls,
matching the existing bank lookup convention while preserving the canonical
`biceps_tendonitis` profile and untouched sibling hashes. Completion matching
canonicalizes the same existing aliases before applying episode/side ownership.

Achilles seated heel raises retain `function: tendon_loading`: plantar flexion
loads the tendon even without added weight. The existing NHS Achilles source
describes seated heel raises in its loading programme for both insertional and
mid-portion presentations. Runtime consumers were checked: the selector uses
function for ranking only after stage eligibility; injury policy derives
`is_loading`, which gives RESTORE the existing readiness, delayed-response and
same-region training holds; the legacy renderer still classifies text, and
`resolve_drill_function` has no runtime callers. Function does not activate a
stage. Explicit tests exercise Achilles `pull_back` holds, mobility baselines'
different scheduling behavior, and injected advanced stages returning to CALM.
LOAD, DYNAMIC and RETURN remain closed.
