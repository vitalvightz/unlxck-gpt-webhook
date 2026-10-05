# Contusion production coverage rollout

Based on Main `4a00b8fd`, after #2735 merged on 2026-10-05. Uses the existing `contusion` family, canonical injury type, review ledger, profile catalog and progression engine. No architecture, taxonomy, database schema or contact-clearance changes.

## 1–3. Complete original inventory

The pre-change audit contains every original ID, name, instruction, review state, source hash, phase instruction and mechanical field: [audit](contusion-family-bank-audit.md), [machine-readable original records](contusion-family-bank-audit.json).

| Canonical region | Original drills |
| --- | ---: |
| heel | 2 |
| shin | 8 |
| quads | 2 |
| groin | 2 |
| core | 2 |
| obliques | 2 |
| lower back | 4 |
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
| eye | 2 |
| face | 4 |
| unspecified | 4 |
| **Total: 22 regions** | **60** |

There were no active contusion profiles. All 60 originals were `needs_review`; stage, equipment, load, impact and velocity were unreviewed. No absent region was invented.

## 4. Problematic legacy content

58 originals contain camp-phase instructions; 38 mix distinct phases. Others hide progression inside GPP. Camp phase is availability, not clinical readiness. Activated groups now consistently allow GPP/SPP/TAPER; exact clinical stages remain profile-owned.

Four shin exercises repeat identical names/instructions under `_2` IDs: foam-roller circles, soft-stick tapping, light percussion and wall shin slides. These remain declared duplicate debt and dormant. Near-duplicate massage, rolling and percussion variants add no defensible staged coverage.

Other issues include direct pressure on acute bruises, impact desensitization, vague circulation/flush claims, variable band/weight/tempo demand, aggressive groin stretching, facial/orbital/trunk pressure, and removing support when bruise colour fades. None is approved by inventory membership.

## 5–7. Repairs, additions and reviews

Three original identities repaired and reviewed, with original source hashes retained in ledger history:

| Preserved ID | Fixed movement |
| --- | --- |
| `shoulder_contusion_passive_arm_hang_trap_bar_support` | Supported unweighted shoulder pendulum; no bar, hanging load or resistance |
| `elbow_contusion_gentle_elbow_slides_on_wall` | Comfortable unloaded elbow movement; no wall pressure or forced extension |
| `wrist_contusion_wrist_flexion_extension_passes` | Supported unloaded wrist movement; empty hand, no grip or resistance |

13 new identities: `{region}_contusion_recovery_support` for heel, shin, quads, biceps, triceps, forearm, shoulder, elbow, wrist, hand and fingers; plus `hand_contusion_reviewed_restore` and `fingers_contusion_reviewed_restore`.

**16 reviewed identities total:** 11 CALM protection guidance and five RESTORE movements. All have reviewed demand, equipment, tissue, region, laterality and contact metadata. Passive pendulum contraction remains `unknown`. The bank spelling `bicep` remains consistent in target regions; profiles resolve canonical `biceps`. No sets, repetitions, holds, external loads, numeric pain ceilings, clinical severity grades or progression thresholds are fabricated.

## 8. Dormant originals

**57 original drills remain dormant and `needs_review`**, retaining their identities, content hashes and original ledger source hashes. They are outside every activated contusion prescription.

| Region | Dormant originals | Reason |
| --- | ---: | --- |
| heel | 2 | Direct pressure/heel loading; depth and bony differential unresolved |
| shin | 8 | Duplicates, percussion, tapping and pressure are unsuitable automatic acute-bruising treatment |
| quads | 2 | Variable loading/stretching needs individual contusion assessment |
| groin | 2 | Forced stretching/pressure; no defensible automatic regional protocol established |
| core, obliques | 2 each | Trunk impact cannot establish absence of internal injury |
| lower back | 4 | Pressure/variable movement with unassessed trauma |
| upper back, chest | 2 each | Trunk trauma and pressure; no automatic profile activated |
| shoulder | 3 | Pressure/percussion/variable demand; one fixed pendulum retained |
| biceps, triceps, forearm | 2 each | Pressure, stretching or resisted variants need assessment |
| elbow | 1 | Percussion/direct pressure; only unloaded movement retained |
| wrist | 3 | Pressure/impact/variable demand; only unloaded movement retained |
| hand, fingers | 2 each | Heat, pressure, grip or impact variants; replaced with fixed unloaded movement |
| neck, jaw, eye | 2 each | Head/neck/orbital impact safety and unsupported treatment |
| face | 4 | Facial pressure/impact cannot establish safe injury classification |
| unspecified | 4 | Unknown tissue/location and mixed unsupported automatic protocols |

## 9–12. Activated profiles, stages and verified sources

All 11 have exact region + `contusion` ownership, reviewed bank hashes, explicit restrictions, sources and live stages. No transition override is added.

Sources directly inspected before encoding:

- **A:** [AAOS: Muscle contusion](https://www.orthoinfo.org/diseases--conditions/muscle-contusion-bruise/) — protect from further injury; avoid acute massage; individually guided rehabilitation; compartment syndrome and deeper injury boundaries.
- **B:** [Leicester Hospitals: Minor sprains, strains or bruises](https://yourhealth.leicestershospitals.nhs.uk/library/emergency-specialist-medicine/emergency-department/1660-care-after-minor-sprains-strains-or-bruises-soft-tissue-injuries/file) — protection and reduction of provoking activity; avoid early heat/massage. No timing or dosage imported.
- **C:** [Cleveland Clinic: Heel fat pad syndrome](https://my.clevelandclinic.org/health/diseases/23275-heel-fat-pad-syndrome) and [heel pain differential](https://my.clevelandclinic.org/health/diseases/heel-pain) — impact/pressure and heel-pad bruising; no fat-pad diagnosis or generic heel-pain exercise protocol inferred.
- **D:** [Leeds Hospitals: Shoulder soft-tissue injury](https://www.leedsth.nhs.uk/patients/resources/early-advice-and-exercises-for-soft-tissue-injuries-of-the-shoulder/) — supported gentle pendulum, subject to individual restrictions.
- **E:** [North Bristol: Elbow injuries](https://www.nbt.nhs.uk/our-services/a-z-services/emergency-department/ed-miu-patient-information/elbow-injuries) — bruised/swollen elbow protection and slow gentle movement short of pain; no forced extension.
- **F:** [Leeds Hospitals: Hand and wrist](https://www.leedsth.nhs.uk/patients/resources/the-hand-and-wrist/) — unloaded wrist and finger movements as symptoms allow; no passive forced range, heat protocol or dose imported.
- **G:** [Royal Berkshire: Bruised hand](https://www.royalberkshire.nhs.uk/media/opzgt14c/bruised-hand_dec25.pdf) — hand contusion/finger movement and swelling/function warnings. Massage is withheld because acute injury depth/phase is unknown and AAOS advises against acute muscle-contusion massage.

| Profile | Live stages | Sources | Why RESTORE remains closed where applicable |
| --- | --- | --- | --- |
| `heel_contusion` | CALM | C, B | Heel-pad vs deeper injury cannot be distinguished; no defensible fixed movement selected |
| `shin_contusion` | CALM | B, A | Injury depth/bony impact not established; existing drills use pressure/impact |
| `quads_contusion` | CALM | A, B | Safe knee motion/protection depends on individually assessed injury extent |
| `biceps_contusion` | CALM | A, B | No fixed region-specific active protocol supported without muscle/tendon assessment |
| `triceps_contusion` | CALM | A, B | Existing stretching/pressure variants do not establish safe injured-muscle demand |
| `forearm_contusion` | CALM | A, B | Variable grip/wrist demand and injury depth; no adequate fixed RESTORE selection |
| `shoulder_contusion` | CALM, RESTORE | D, A, B | Supported unweighted pendulum only |
| `elbow_contusion` | CALM, RESTORE | E, A, B | Comfortable unloaded bend/straighten only |
| `wrist_contusion` | CALM, RESTORE | F, B | Supported unloaded wrist motion only |
| `hand_contusion` | CALM, RESTORE | G, F, B | Comfortable unloaded opening/closing only |
| `fingers_contusion` | CALM, RESTORE | G, F, B | Comfortable unloaded finger motion only |

CALM/RESTORE do not establish healing, contact tolerance, brace removal or clearance. Individual clinician restrictions remain authoritative. The existing contusion medical gate additionally screens compartment concerns, expanding hematoma, major swelling/function loss, open/deep wounds, inability to use/bear weight, neurological/circulation symptoms, head trauma and systemic chest/abdominal trauma. Ordinary blue bruise colour alone is not vascular compromise.

## 13–15. Advanced stages and missing inputs

**No RESTORE → LOAD transition became promotable. LOAD, DYNAMIC and RETURN remain closed for every contusion profile.** No reviewed advanced contusion prescription or sourced evaluable transition criterion was activated. No universal pain/time/session threshold is substituted.

The following regional assessments would need source-backed criteria and actual product capture before advanced loading could be considered; they are not fabricated checkpoint IDs or encoded readiness rules:

| Profile | Unavailable relevant assessment/input |
| --- | --- |
| heel | Injury depth/bony differential, assessed weight-bearing function and focal tenderness |
| shin | Bony injury exclusion, tenderness/swelling and assessed walking/loading function |
| quads | Assessed contusion extent, hematoma/protection status, knee range, strength and functional tolerance |
| biceps | Injured tissue extent, elbow/shoulder movement, strength and focal tenderness |
| triceps | Injured tissue extent, elbow motion/extension strength and tenderness |
| forearm | Swelling/circulation assessment, grip strength and wrist/forearm functional tolerance |
| shoulder | Assessed movement/control/strength, tenderness and swelling |
| elbow | Assessed comfortable range, individual support restrictions and strength/loading tolerance |
| wrist | Assessed wrist range, grip/hand weight-bearing function and swelling |
| hand | Assessed finger range/grip function, swelling and tendon/structural safety |
| fingers | Assessed individual finger motion/function, protection status and swelling |

The product captures no functional checkpoints for these criteria. Complete episode history, no unresolved setback, evaluated sourced requirements and explicit live-stage activation remain necessary. Improved symptoms, a clearance record, camp phase, elapsed time and performed guidance do not substitute for them.

## 16. Preservation

All 37 prior raw profiles and policy hashes are identical. Regression tests compare prior/current decisions, scheduling and frozen snapshots for CALM/RESTORE and known/unknown side. All 1,601 pre-existing drill IDs remain; exactly the three declared contusion repairs change content hash. All other pre-existing bank hashes are unchanged. Original repaired source history is retained. New totals: 1,614 bank drills, 73 contusion inventory identities, 1,510 ledger records. Reviewed inventory cannot activate itself.

## 17. Verification

- Focused contusion/hyperextension/catalog safety suite: **1,152 passed**.
- Broader rehab, injury policy, all rolled-out families, Today/completion and vocabulary suite: **3,252 passed, 15 skipped**; one existing HTTP 422 deprecation warning. Skips are the real PostgreSQL concurrency tests requiring `REHAB_TEST_DATABASE_URL`.
- Isolated database migration/ownership/unknown-side acceptance suite: **43 passed**. The existing harness now rolls dates across month boundaries rather than generating November 31 when profile coverage expands.
- Bank validation: **zero errors and warnings**; declared legacy duplicate/unmigrated inventory remains informational debt.
- Clinical validation: **seven families, 48 active profiles, zero promotable transitions**.
- Metadata validation, ledger generation check and metadata application check: pass, **zero pending changes or stale entries**.
- Vocabulary audit: pass, **33 canonical types, 12 normal MSK rehab types, seven families**.
- Repository Python Ruff, changed-file compilation/import collection and `pip check`: pass.
- Byte-idempotent seeding and source/history/hash preservation: covered in passing tests.
- Latest Main fetched and confirmed to match the branch base before committing.

Database checks use an isolated PostgreSQL-compatible database, not production; no migration is introduced by this rollout. Real concurrent advisory-lock checks require the existing local test database URL. The complete unrelated repository test suite is left to PR CI.

## 18. Exact coverage increase

**37 → 48 active regional profiles: +11.** Contusion coverage rises from zero to 11 exact regional profiles: 11 CALM and five RESTORE. Six remain intentionally CALM-only; zero advanced stages are activated.
