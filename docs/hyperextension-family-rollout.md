# Hyperextension family production coverage

Based on Main `47963020`, after impingement PR #2734 merged. Canonical type remains `hyperextension`; family remains `hyperextension_or_joint_trauma`. No taxonomy, schema, progression engine or family layer is added.

## 1–3. Complete original inventory

The pre-change [JSON audit](hyperextension-family-bank-audit.json) records every ID, original name/notes, source hash, review state, camp instructions, stage and mechanical fields. The [readable audit](hyperextension-family-bank-audit.md) lists every ID by region.

| Canonical region | Original drills |
| --- | ---: |
| toe | 2 |
| groin | 2 |
| obliques | 2 |
| lower back | 2 |
| upper back | 2 |
| chest | 2 |
| shoulder | 4 |
| biceps (bank spelling `bicep`) | 2 |
| triceps | 2 |
| forearm | 2 |
| elbow | 2 |
| wrist | 4 |
| hand | 2 |
| fingers | 2 |
| neck | 2 |
| jaw | 2 |
| unspecified | 6 |
| **Total: 17 regions** | **42** |

No knee or ankle hyperextension group exists. There were no active hyperextension profiles. All originals were `needs_review`, with null stage/load/impact/velocity/equipment. Null means unreviewed; it has not been reinterpreted as low demand.

## 4. Problematic legacy content

No exact duplicate IDs or names. Near-duplicates: wrist palmar push/knuckle press/knuckle push-up, shoulder pressout/bottom-range push-up, and unspecified guarding/antagonist isometrics.

38 drills contain camp-phase instructions; 34 explicitly mix multiple phases. The unspecified eccentric and wrap entries hide progression behind SPP without a GPP label. Two shoulder drills prescribe a single camp phase. Camp availability is orthogonal to clinical readiness; all eight groups belonging to the six activated regions now declare `GPP → SPP → TAPER`. Profile live stages still decide eligibility, and no legacy sibling gains activation.

The inventory includes terminal-range loading, passive finger overstretching, variable band/weight/tempo progression, BOSU/plank work, contact preparation, reflex loading and invented generic `3x6` dosing. A muscle-region label or vague “joint-specific” instruction cannot establish an injured joint, stability or safe movement range.

## 5–8. Bank and review decisions

**Repaired originals: 0. Newly added: 6. Newly reviewed: 6. Original drills dormant: all 42.** There is no defensible existing injured-joint exercise to activate without structural assessment and protection inputs. Relabeling a loaded exercise as protection guidance would lose its identity; the six advice entries therefore receive new IDs. Original IDs, names, instructions, hashes and review history are preserved without pretending they have clinical approval.

New reviewed CALM identities:

- `toe_hyperextension_recovery_support`
- `fingers_hyperextension_recovery_support`
- `elbow_hyperextension_recovery_support`
- `wrist_hyperextension_recovery_support`
- `hand_hyperextension_recovery_support`
- `shoulder_hyperextension_recovery_support`

These are regional protection advice, not exercises or stability tests. Actual mechanical metadata: `recovery_downregulation`, minimal load, no impact/contact, low velocity, no equipment, general rehab, not-applicable laterality, regional joint tissue. Contraction remains `unknown` because advice has no specified contraction. No dose, pain ceiling, brace duration, grading rule or clearance threshold is inferred. Existing product low/moderate eligibility and scheduled cadence are retained.

Dormant reasons by region (the audit names every original identity):

| Region | Reason all original entries remain dormant |
| --- | --- |
| toe | Towel curls hide weight/volume progression; toe-loaded kettlebell does not establish forefoot tolerance or injury grade. |
| groin | Loaded lateral lunges and band walks concern muscle/adductor mechanics without a defined joint-trauma presentation. |
| obliques | Banded side plank and explosive medicine-ball toss do not establish a joint diagnosis or safe loading. |
| lower back | Loaded/banded hinge and wall deadlift progressions lack a defined spinal injury and safe restrictions. |
| upper back | Bench retraction/end-range holds and progressively loaded shrugs do not define the injured structure. |
| chest | Isometric pressing and vague scapular/chest drills cross muscle/shoulder boundaries without stability assessment. |
| shoulder | Wall-slide-to-landmine progression, resistance fly/power progression, bottom-range push-up and band pressout all require assessed range and stability. |
| biceps | Banded terminal elbow control and wall push-up progression are elbow loading with unknown resistance/speed, not a defined biceps trauma protocol. |
| triceps | Band recoil/reflex loading and TRX eccentric work need stability and known demand. |
| forearm | BOSU wrist/plank progression and palm-down crawls load an unassessed wrist; they do not define forearm joint trauma. |
| elbow | Band-behind-elbow end-range defense and progressively deeper wall presses need stability and permitted extension/load. |
| wrist | Palmar/knuckle pressure, perturbation/reflex work, partial-extension push-ups and dorsal holds have uncertain resistance and protection requirements. |
| hand | Finger pull-back holds risk recreating the injury; backhand wall crawls progress toward punching with no joint identity or safe range. |
| fingers | Isometric holds progress to loaded grip; passive flexor stretching can recreate backward bending. Protection/volar-plate assessment is absent. |
| neck | Traumatic neck movement and band/prone neck lifting cannot bypass assessment of cervical/head injury. |
| jaw | Resisted clench and towel traction lack a defined assessed jaw injury and may cross dislocation/structural gates. |
| unspecified | Six generic antagonist/slider/band/eccentric/wrap/guarding/strength entries have no exact joint identity, undefined mechanics, hidden progression or support removal. |

## 9–12. Activated profiles and regional evidence

Six active/live profiles: `toe_hyperextension`, `fingers_hyperextension`, `elbow_hyperextension`, `wrist_hyperextension`, `hand_hyperextension`, `shoulder_hyperextension`. **Each has only CALM live.** Each explicitly owns its exact region/type, reviewed bank hash, prescriptions, restrictions, sources and empty transition overrides. Family membership and a reviewed drill activate nothing independently.

Sources were opened directly on 5 October 2026. These are assessed-injury patient guidance, not evidence that an app label establishes a diagnosis. Only conservative protection advice is encoded; condition-specific exercise, dose, time and return protocols are withheld.

| Region | Direct evidence | CALM-only boundary / exact missing input |
| --- | --- | --- |
| toe | [AAOS Turf Toe](https://www.orthoinfo.org/diseases--conditions/turf-toe/) | Treatment depends on examined grade/stability and sometimes imaging. The canonical toe region does not identify the big toe/MTP joint. Missing exact injured toe/joint, assessed stability/structural exclusion, authorized weight-bearing and movement/protection status. No generalization of big-toe taping, boot or return protocol. |
| fingers | [Guy’s and St Thomas’ volar plate injuries](https://www.guysandstthomas.nhs.uk/health-information/volar-plate-injuries-finger) | Backward bending can involve tear or bone injury; movement is tied to hand assessment and a specific splint. Missing assessed joint/volar-plate stability, fracture/tear exclusion, splint position/status and permitted protected ROM. No automatic removal of straps, passive stretch or grip loading. |
| elbow | [Royal United Hospitals Bath soft-tissue elbow advice](https://ruh.nhs.uk/patients/patient_information/ORT047_Advice_after_a_soft_tissue_injury_of_the_elbow.pdf) | The leaflet explicitly assumes assessment found no broken bones. Missing that structural assessment, joint stability, permitted extension and sling/movement restrictions. Its full-range exercises cannot be transferred to unassessed hyperextension. |
| wrist | [Hull wrist/hand soft-tissue guidance](https://www.hey.nhs.uk/patient-leaflet/soft-tissue-injury-wrist-hand/) | Relative protection is supported; exercises presume an assessed soft-tissue injury. Missing fracture/ligament assessment, wrist stability, permitted ROM and individualized splint/protection release. No symptom-driven splint taper or loaded extension. |
| hand | [Hull wrist/hand soft-tissue guidance](https://www.hey.nhs.uk/patient-leaflet/soft-tissue-injury-wrist-hand/) | Protection is supported for the hand; the bank region does not identify the injured joint. Missing exact joint/structure, assessed stability, allowed ROM and protection status. It does not inherit a wrist or volar-plate movement protocol. |
| shoulder | [Gateshead shoulder injury guidance](https://www.gatesheadhealth.nhs.uk/resources/shoulder-injury/) | Comfortable support and avoiding heavy/sport demands are supported. Missing assessed structural stability/dislocation exclusion, permitted directions/range and individualized sling restrictions. The leaflet’s pendulums/overhead exercises and time-based sequence are not automatically transferred. |

Every profile additionally cites [NHS sprains and strains](https://www.nhs.uk/conditions/sprains-and-strains/) for protection and escalation for worsening, major swelling, inability to bear weight, deformity, altered sensation or cold/changed-colour limbs. No universal regional exercise protocol or numeric pain limit is derived from that general advice.

## 13–15. Stage investigation

**Promotable RESTORE → LOAD transitions: 0. LOAD, DYNAMIC and RETURN remain closed in every new profile. RESTORE also remains closed in all six.** No reviewed LOAD prescription or sourced/evaluable progression criterion is added. CALM-only is a deliberate useful protection boundary, not a diagnosis or a claim of restored capacity.

In addition to the exact structural/protection inputs above, LOAD would need region-specific assessed ROM and strength/control or functional tolerance: toe weight-bearing/push-off tolerance; finger protected motion/grip function; elbow extension/load tolerance; wrist ROM/grip/hand weight-bearing tolerance; hand joint-specific grip/use; shoulder ROM/control/load tolerance. The sources do not supply one universal threshold, and the product captures none of these functional checkpoints (`CAPTURED_FUNCTIONAL_CHECKPOINTS` remains empty). A generic clearance scope, symptom improvement, complete exposure history, camp phase or elapsed time cannot substitute. DYNAMIC/RETURN would additionally need defensible sport/impact/contact criteria and captured testing.

Missing criteria fail closed through the existing profile and progression contracts. A RESTORE request yields `stage_not_activated` and no prescription. Persisted LOAD/DYNAMIC/RETURN cannot inject an advanced prescription; the existing engine resets that unsupported starting stage to CALM. Worsening remains on the safer CALM state. No session-count/time criterion or functional proxy is invented.

## 16. Preservation and narrowly scoped safety fix

The existing medical gate missed mechanical/vascular/function-loss phrases under a stored hyperextension label. This was identified and explained before adding the small hyperextension-specific text check in `rehab_stage._is_urgent_injury`. Giving way, locking, suspected instability, vascular change, deformity, major swelling and inability to use/bear weight now route to medical review before profile selection, including when clearance exists. A new giving-way report also holds a frozen prescription. Existing structural/neurological/head-trauma and severe/high routes remain authoritative.

This adds no diagnosis, type or progression path. The additional screen is specific to hyperextension presentations; existing families retain their current rules. It is a conservative phrase screen, not a clinical stability assessment; absence of a matched phrase never opens RESTORE or loading.

All 31 previous raw profiles, policy hashes, prescriptions, bundles and stages remain identical. Baseline fixtures verify equivalent CALM/RESTORE decisions, schedules and frozen snapshots for left/unknown sides. All 1,595 original drill IDs and hashes remain identical. Historical family tests now compare their named original profiles/inventory so later family additions do not invalidate their preservation assertions.

## 17. Verification

Focused hyperextension suite: **342 passed**. Broader rehab/previous-family regression suite: **2,628 passed, 15 skipped**, with one existing HTTP status deprecation warning. The earlier combined hyperextension/impingement/shared-pathway run passed 680 checks. Isolated PostgreSQL acceptance: **32 passed**. Bank and clinical validators, metadata validator/generator/applicator checks, vocabulary audit (33 canonical types, 12 normal MSK types, seven families), Ruff, Python compilation and dependency checks all pass.

Coverage includes exact region/type, cross-family exclusion, reviewed identity/hash checks, stale content, CALM and closed RESTORE, worsening, serious text/severity, frozen medical holds, unknown-side ownership, dormant/persisted advanced gates, clearance/camp/time, episode history and previous 31-profile equivalence. The new seed and ledger are byte-idempotent; prior family seed checks remain green.

Run bank/clinical/metadata validators, metadata generator/applicator checks, vocabulary audit, Python Ruff/import/dependency checks, the focused hyperextension suite and broader rehab suites. The isolated PostgreSQL acceptance harness includes all six new profiles. No Supabase schema/migration changes or production database writes are needed for this content rollout. Real multi-connection locking tests require `REHAB_TEST_DATABASE_URL` and run separately in CI.

## 18. Exact production coverage increase

**31 → 37 live exact region/type profiles: +6. Hyperextension: 0 → 6 CALM profiles.** Reviewed active bank identities increase by six; total bank inventory is 1,601, with 48 hyperextension identities (42 dormant originals plus six active protection entries). No additional RESTORE, LOAD, DYNAMIC or RETURN coverage is claimed.
