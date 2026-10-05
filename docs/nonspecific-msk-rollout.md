# Nonspecific MSK production coverage rollout

Initial baseline Main `2db8d0d3`, after #2736 merged on 2026-10-05. Subsequently synchronized with Main `54acd889`; its intervening exercise-media changes do not touch rehab data or contracts.

Uses the existing `nonspecific_msk_symptoms` family, five canonical symptom types, review ledger, profile catalog and progression engine. A symptom is not a diagnosis. No new taxonomy, progression engine, database schema or contact-clearance system.

## 1–7. Entire original inventory

**358 original drills across 121 exact type/region combinations and 31 canonical regions.** Counts by type: pain **86** (28 regions), soreness **76** (24), tightness **84** (29), stiffness **68** (20), swelling **44** (20). All were `needs_review`, with null stage/equipment/load/impact/velocity. No symptom profile was previously active.

The table below identifies every region for each type; `-` means absent inventory, not an invitation to invent coverage. Every original ID, name, instruction, source/content hash, phase instruction and mechanical field is retained in [the full audit](nonspecific-msk-bank-audit.md) and [original records](nonspecific-msk-bank-audit.json).

| Region | pain | soreness | tightness | stiffness | swelling |
| --- | ---: | ---: | ---: | ---: | ---: |
| achilles | 4 | - | - | - | - |
| ankle | - | - | 2 | - | 2 |
| biceps | 2 | 4 | 2 | 2 | 2 |
| calf | - | - | 4 | - | - |
| chest | 2 | 2 | 2 | 2 | 2 |
| core | 2 | 4 | 2 | - | - |
| elbow | 2 | 2 | 2 | 2 | 2 |
| eye | 4 | 2 | 2 | 2 | - |
| face | 4 | 4 | 2 | 2 | 4 |
| fingers | 2 | 2 | 2 | 4 | 2 |
| foot | 2 | 2 | 2 | - | - |
| forearm | 2 | 4 | 2 | 4 | 2 |
| glute | 4 | 4 | 4 | 2 | 2 |
| groin | 4 | 4 | 2 | 4 | 2 |
| hamstring | 2 | 2 | 2 | - | - |
| hand | 4 | 2 | 2 | 4 | 2 |
| heel | - | - | - | - | 2 |
| hip | 2 | 2 | 2 | - | - |
| jaw | 2 | 4 | 2 | 4 | 2 |
| knee | 4 | - | 4 | - | - |
| lower back | 6 | 6 | 4 | 4 | 2 |
| neck | 2 | 4 | 2 | 4 | 2 |
| obliques | 4 | 4 | 6 | 6 | 2 |
| quads | 2 | 2 | 2 | - | - |
| shin | 4 | - | 4 | - | - |
| shoulder | 4 | 4 | 4 | 4 | 4 |
| toe | 2 | - | 2 | 2 | - |
| triceps | 2 | 2 | 4 | 2 | 2 |
| unspecified | 4 | 4 | 4 | 6 | 2 |
| upper back | 4 | 2 | 4 | 2 | 2 |
| wrist | 4 | 4 | 6 | 6 | 2 |


Aliases are resolved through the existing registry: bank `bicep` → `biceps`, `hamstrings` → `hamstring`, `glutes` → `glute`, `lower_back` → `lower back`. Original group spelling is retained in bank target metadata; new profiles use canonical region identities. No vocabulary is added.

## 8. Duplicate and problematic content

346 drills contain camp instructions, 232 mix distinct phases, 45 match explicit hidden-progression wording, and 105 match vague mobility/flush/release/activation/recovery wording. These are audit flags, not a claim that every unflagged drill is sound.

16 normalized-name duplicate clusters cover 32 identities; 12 instruction clusters repeat normalized notes. Fifteen name clusters repeat within one exact type/region, and one repeats across forearm/wrist swelling. No exact normalized-name cluster crosses canonical symptom types. The audit lists all duplicate IDs. All remain dormant; none is approved twice to inflate coverage.

Important semantic duplicates/near-duplicates across labels or regions include:

- `foot_pain_toe_spreads_with_band` / `foot_tightness_toe_spreading_with_resistance_band`: resisted toe spreading under different symptom labels.
- `forearm_swelling_elevated_wrist_pumps` / `wrist_swelling_elevated_wrist_pumps`: identical named wrist movement in different regional groups.
- `neck_soreness_gentle_neck_tilts_assisted` / `neck_stiffness_gentle_neck_side_tilts_passive_stretch`: assisted/passive neck tilt; actual assistance is not standardized.
- `wrist_stiffness_wrist_cars` / `wrist_stiffness_wrist_cars_controlled_articular_rotations`: wrist rotation with differing hidden resistance/tempo instructions.
- `shoulder_stiffness_pvc_shoulder_pass_throughs` / `shoulder_stiffness_pvc_pass_throughs`: pass-through variants with uncontrolled end-range demand.
- `lower_back_pain_supine_90_90_breathing`, its `_2` sibling, `lower_back_soreness_90_90_hip_lift_breathing`, and `lower_back_swelling_90_90_breathing_with_feet_elevated`: similar positioning with materially different bracing/lifting/drainage claims; not interchangeable prescriptions.
- `glutes_tightness_pigeon_pose_glute_stretch` / `glutes_stiffness_elevated_pigeon_stretch`: similar stretch with position-dependent demand.

Incorrect or unestablished regional mechanisms include `bicep_pain_triceps_stretch_with_shoulder_extension`, `bicep_stiffness_stick_shoulder_dislocates`, and `obliques_swelling_copenhagen_iso_short_lever`. Other legacy notes diagnose DOMS, inflammation, capsule/fascial restriction or drainage from a symptom label; foam rolling, percussion, aggressive stretching, loaded isometrics, contact preparation and variable equipment do not become approved by these claims. IDs are unique; similar ID/name semantics do not establish equivalent mechanical demand.

## 9–11. Repaired, added and reviewed identities

**Three original IDs repaired and reviewed:**

| Original ID retained | Fixed RESTORE movement |
| --- | --- |
| `lower_back_pain_supine_pelvic_tilts` | Small comfortable supine pelvic tilt, normal breathing, no forced arch/hold |
| `neck_stiffness_neck_cars_controlled_articular_rotations` | Small comfortable unassisted seated neck rotation; no circles/resistance/traction |
| `wrist_stiffness_stick_roll_wrist_flex_ext` | Supported unloaded wrist flexion/extension; no stick/grip/resistance |

**16 new CALM guidance IDs:** `{policy_id}_recovery_support` for each of the 16 profiles in the table below. These contain symptom-specific activity/protection guidance rather than relabeling massage or resistance drills as safe.

**19 reviewed identities total:** 16 guidance entries plus the three repaired movements. Original repaired source hashes remain in ledger history. Reviewed mechanical metadata explicitly describes minimal load, no impact, low velocity, actual equipment, regional unspecified tissue, laterality and no contact. Guidance contraction is `unknown`; active movements are `mixed`. No fabricated sets/reps/holds, resistance, pain ceilings, swelling thresholds, clinical severity grading or progression criteria. Low/moderate eligibility and cadence are existing product rules.

## 12. Dormant inventory

**355 originals remain dormant and `needs_review`**, with IDs, content and original ledger source hashes unchanged. They are not referenced by activated prescriptions. That includes every swelling drill, all exact duplicate clusters, pressure/percussion/heat prescriptions, vague recovery work, diagnostic claims, hidden progression, uncontrolled resistance, contact preparation and all unselected exercise variants.

Dormant original counts by type: pain **85**, soreness **76**, tightness **84**, stiffness **66**, swelling **44**. The only changes to original identities are one lower-back pain drill, one neck stiffness drill and one wrist stiffness drill.

The original audit is the complete per-ID list. Dormancy is intentional clinical deferral, not deletion. Metadata review and profile activation remain separate.

## 13–17. Exact activation, live stages, exclusions and sources

Directly inspected source keys:

- **SH:** [NHS shoulder pain](https://www.nhs.uk/symptoms/shoulder-pain/) — activity modification, gentle movement, serious features and no self-diagnosis.
- **EL:** [NHS elbow/arm pain](https://www.nhs.uk/symptoms/elbow-and-arm-pain/) — assessment boundaries and no self-diagnosis. **J:** [NHS joint pain](https://www.nhs.uk/symptoms/joint-pain/) — limited rest while retaining movement, hot/swollen/systemic and weight-bearing red flags.
- **WR:** [NHS wrist pain](https://www.nhs.uk/symptoms/hand-pain/wrist-pain/) — mild pain/stiffness movement and provoking grip/load modification.
- **HA:** [NHS palm pain](https://www.nhs.uk/symptoms/hand-pain/pain-in-the-palm-of-the-hand/). **FI:** [NHS finger pain](https://www.nhs.uk/symptoms/hand-pain/finger-pain/) — regional provoking-task modification and assessment boundaries.
- **KN:** [NHS knee pain](https://www.nhs.uk/symptoms/knee-pain/). **HI:** [NHS hip pain](https://www.nhs.uk/symptoms/hip-pain/) — regional activity/load reduction and mechanical/systemic red flags.
- **BA:** [NHS back pain](https://www.nhs.uk/conditions/back-pain/). **CSP:** [Chartered Society of Physiotherapy back movements](https://www.csp.org.uk/conditions/back-pain/video-exercises-back-pain) — ordinary activity, avoid prolonged bed rest, and the pelvic-tilt mechanics; follow individual clinical advice.
- **NE:** [NHS neck pain/stiff neck](https://www.nhs.uk/symptoms/neck-pain-and-stiff-neck/). **FL:** [NHS flexibility exercises linked by that neck guidance](https://www.nhs.uk/live-well/exercise/flexibility-exercises/) — ordinary movement/position changes and comfortable unassisted neck rotation.
- **SU:** [University Hospitals Sussex elbow/wrist movements](https://www.uhsussex.nhs.uk/resources/elbow-and-wrist-exercises/) — wrist up/down mechanics only. Its injury-specific healing, strengthening, grip escalation, time and dose instructions are not imported into a nonspecific profile. WR supplies the nonspecific mild-stiffness rationale.
- **SW:** [NHS swelling/oedema](https://www.nhs.uk/conditions/oedema/) — cause-dependent treatment and unexplained one-sided limb swelling assessment.

Some NHS Inform pages returned HTTP 403 on direct retrieval. No rule is encoded from those inaccessible pages; the accessible sources above support the shipped content. Conservative small/comfortable movement is a restriction of this baseline, not a universal claim that movement must always be pain-free.

| Exact profile | Live stages | Sources | CALM-only reason where applicable |
| --- | --- | --- | --- |
| `shoulder_pain` | CALM | SH | Existing resistance/isometric/variable wall variants are not justified by an undiagnosed symptom |
| `elbow_pain` | CALM | EL, J | Existing loaded curls/presses require more specific clinical context |
| `wrist_pain` | CALM | WR | Existing resisted grip/rotation variants are not safe fixed baseline content |
| `hand_pain` | CALM | HA | Grip/fingertip holds/pressure/flush variants not justified |
| `fingers_pain` | CALM | FI | Existing resistance/ice-pressure movements not justified |
| `knee_pain` | CALM | KN | Loaded TKE/massage variants cannot establish the cause or safe demand |
| `hip_pain` | CALM | HI | Full-range CARs/massage are not a defensible fixed low-risk baseline |
| `lower_back_pain` | CALM, RESTORE | BA, CSP | Only the fixed pelvic tilt is activated |
| `neck_stiffness` | CALM, RESTORE | NE, FL | Only the fixed unassisted neck rotation is activated |
| `elbow_stiffness` | CALM | EL, J | No verified nonspecific regional fixed exercise rationale; injury-specific protocols are not substituted |
| `wrist_stiffness` | CALM, RESTORE | WR, SU | Only fixed unloaded wrist up/down movement is activated |
| `lower_back_stiffness` | CALM | BA, J | Resistance/loaded articulation or unbounded mobility variants not selected |
| `neck_tightness` | CALM | NE | No shortening inferred; circle/pressure variants not justified |
| `shoulder_tightness` | CALM | SH | No shortening inferred; forced capsule/band/pressure variants not justified |
| `neck_soreness` | CALM | NE | No DOMS diagnosis; assistance, pressure or resisted variants not justified |
| `shoulder_soreness` | CALM | SH | No DOMS diagnosis; pressure, loaded holds or unbounded wall movement not justified |

**105 original exact combinations intentionally remain inactive.** All absent combinations also remain unsupported. No extension from pain to soreness/tightness/stiffness/swelling is implicit. All 20 swelling combinations stay inactive: the product does not establish cause, benign status or an appropriate intervention. Unexplained/increasing/hot/systemic swelling needs assessment; one-sided lower-limb swelling routes to medical review instead of being presumed benign. A known specific injury retains its specific pathway. No automatic swelling RESTORE or compression/massage/drainage protocol.

Other inactive combinations lack a verified regional symptom rationale and fixed reviewed movement in this controlled rollout. Particular exclusions are head/eye/face/jaw, chest/core/obliques and unspecified presentations, whose symptoms may not be routine MSK. Distal/tendon/muscle-region inventory is not silently relabeled as strain, tendonitis, DOMS or inflammation. This PR completes first family-level coverage, not all inventory review or universal region coverage.

## 18–20. Progression and exact missing evidence/inputs

**Zero RESTORE → LOAD transitions became promotable. LOAD/DYNAMIC/RETURN remain closed.** No advanced symptom prescription is approved. No source-supported nonspecific clinical transition criterion with captured inputs is present, and criteria are not borrowed from injury-specific families.

| Profiles | Missing evidence and product input |
| --- | --- |
| `shoulder_pain`, `shoulder_tightness`, `shoulder_soreness` | Nonspecific shoulder loading-readiness criteria; evaluated regional movement/function and strength response are not captured |
| `elbow_pain`, `elbow_stiffness` | Nonspecific elbow loading-readiness criteria; evaluated elbow range/function and load tolerance are not captured |
| `wrist_pain`, `wrist_stiffness` | Nonspecific wrist loading-readiness criteria; evaluated wrist/grip/function tolerance is not captured |
| `hand_pain`, `fingers_pain` | Nonspecific hand/finger loading-readiness criteria; evaluated individual movement/grip function and structural safety are not captured |
| `knee_pain` | Nonspecific knee loading-readiness criteria; evaluated walking/weight-bearing and mechanical function are not captured |
| `hip_pain` | Nonspecific hip loading-readiness criteria; evaluated gait/movement and loading response are not captured |
| `lower_back_pain`, `lower_back_stiffness` | Nonspecific back loading-readiness criteria; assessed regional function and response to progressively demanding work are not captured |
| `neck_stiffness`, `neck_tightness`, `neck_soreness` | Nonspecific neck loading-readiness criteria; assessed regional motion/function and clinical exercise suitability are not captured |

These describe missing evidence, not newly invented checkpoint IDs or thresholds. The activation catalog declares no clinical criterion for these profiles. Existing requirements for complete history, resolved setbacks, evaluable sourced criteria and explicit live-stage activation remain authoritative. Time, good sessions, symptom improvement, clinician/contact clearance and camp phase do not establish advancement.

## 21–23. Routing, ownership, multi-injury and preservation

Stored specific canonical injury types retain their existing pathways when symptom words also occur: hamstring strain, ankle sprain, Achilles tendonitis, shoulder impingement, elbow hyperextension and quad contusion are tested explicitly.

A stored generic type conflicting with a non-negated specific injury in the description or stored rehab type fails closed with `specific_injury_identity_conflict`. It receives no symptom prescription and holds frozen work; the identity must be corrected rather than silently diagnosed, retagged or downgraded. The existing parser handles negation; no new synonym taxonomy is added.

Additional red-flag handling is scoped to nonspecific canonical episodes (including the existing description fallback for records without a type). It covers major trauma/deformity, inability to use/bear weight, marked/increasing/unexplained swelling, hot/red joints/systemic illness, neurological/vascular changes, severe unexplained pain, mechanical blocks/giving way and concerning trunk/calf presentations. Specific-family gates and global urgent vocabulary are unchanged.

Frozen nonspecific completion and exposure evidence now retain the exact symptom label as well as existing episode/region/side ownership. A pain profile cannot credit soreness in the same episode. The check derives the expected canonical type from the existing profile ID; no new schema or exposure format. Stored type is authoritative, with the existing parser fallback for untyped records. Unknown-side guidance remains recordable, but does not qualify positive capacity evidence.

Tests cover strain+soreness, sprain+swelling, tendonitis+pain, contusion+stiffness, two symptom types in one region and symptoms in different regions. Conservative restrictions and contact limits remain authoritative. Multiple symptom words in one canonical episode create one Today work item, not one item per word. Separate real episodes retain separate owners and existing allocation ceilings.

All **48 previous raw profiles and their hashes are identical**. Regression comparisons cover CALM/RESTORE, known/unknown side, decisions, schedules and frozen snapshots. All **1,614 original bank IDs** remain; only the three declared symptom repairs change hash. All original repaired source history is preserved. Totals after rollout: **1,630 bank drills**, **374 symptom-family inventory identities**, **1,526 ledger records**. Existing family seed idempotence remains covered by the broader suite.

## 24. Validation

- Final symptom-family suite: **894 passed**, including hot swollen joints without fever, identity conflicts, exact completion/exposure type ownership and preserved older profiles.
- Updated tendon/sprain suites: **423 passed**. Historical assertions now verify own-type pain coverage and the closed legacy bank-only route, rather than assuming pain can never have a profile.
- Catalog safety suite: **197 passed**, including unilateral ankle swelling medical routing.
- Isolated migration/ownership/unknown-side database acceptance suite: **59 passed**.
- Bank validator: **zero errors and warnings**; duplicate/unmigrated dormant inventory remains informational debt.
- Clinical validator: **seven families, 64 active profiles, zero promotable transitions**.
- Metadata validation/generation/application checks: pass, **zero pending applications or stale skips**.
- Vocabulary audit: pass, unchanged **33 canonical types, 12 normal MSK types, seven families**.
- Repository Ruff, compilation/import collection and `pip check`: pass.
- Runtime requirements audit: **no known vulnerabilities found**; `en-core-web-sm` 3.8.0 is not on PyPI and cannot be audited.
- Byte-idempotent seeding, original source/history/hash preservation and previous-family equality are covered by passing tests.
- Unknown-side RESTORE checks for all three live RESTORE profiles select region-wide CALM guidance safely.
- Latest Main checked again after synchronization; no rehab baseline drift.

Broader rehab/injury-policy/all-family/Today/completion/vocabulary rerun: **4,130 passed, 15 skipped**, with one existing HTTP 422 deprecation warning. Skips require `REHAB_TEST_DATABASE_URL` for real PostgreSQL lock/concurrency tests. The 32 additional hot-swollen-joint cases are included in the final 894-test symptom suite above. No production migration is introduced; isolated database acceptance checks exercise the existing migration and ownership contracts. Full unrelated repository tests and real PostgreSQL concurrency checks remain PR CI work.

## 25. Exact live coverage increase

**48 → 64 active regional profiles: +16.** Pain +8, stiffness +4, tightness +2, soreness +2, swelling +0. All 16 support CALM; three support RESTORE, 13 are CALM-only; no advanced stages become live. Coverage now exists in all seven MSK families without treating the five symptom labels as diagnoses or interchangeable aliases.
