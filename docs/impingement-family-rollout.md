# Impingement regional production coverage

This rollout uses the existing `joint_irritation_or_impingement` family and
canonical `impingement` type. It adds no taxonomy, architecture or progression
engine. It never maps generic pain, soreness, tightness, stiffness, swelling,
tendonitis or instability into these profiles.

## Original inventory

Baseline is Main `66e6b9f6`. The complete 48-drill, 20-region snapshot, original
IDs, notes, mechanical fields and review/source/content hashes are in
`impingement-family-bank-audit.json`; the readable ID table is in
`impingement-family-bank-audit.md`. Shoulder, wrist, hand and neck each contain
four drills. Ankle, hip, groin, glute, obliques, lower back, upper back, chest,
biceps, triceps, forearm, elbow, fingers, jaw, face and unspecified each contain
two. There were no active impingement profiles, reviewed drills or stage values.
44 drills mixed camp instructions; every load, impact, velocity and equipment
field was unreviewed. The two same-name wrist band-distraction drills have
different notes and remain near-duplicates, not interchangeable prescriptions.

## Reviewed content and activation

| Profile | Live stages | RESTORE bank identity | Sources |
|---|---|---|---|
| `shoulder_impingement` | CALM, RESTORE | `shoulder_impingement_scapular_wall_slides_with_chin_tuck` | [RJAH NHS guidance](https://www.rjah.nhs.uk/our-services/therapy/supported-self-care/rotator-cuff-related-shoulder-pain/) |
| `hip_impingement` | CALM, RESTORE | `hip_impingement_90_90_hip_switches` | [Leeds NHS FAI guidance](https://leedscommunityhealthcare.nhs.uk/our-services-a-z/musculoskeletal-msk/hip-problems/known-diagnosed-hip-problems/hip-femoroacetabular-impingement-fai/), [ISHA consensus](https://pmc.ncbi.nlm.nih.gov/articles/PMC8349584/) |
| `ankle_impingement` | CALM, RESTORE | `ankle_impingement_reviewed_restore` | [NHS anterior ankle guidance](https://msk-bexley.nhs.uk/conditions/foot-and-ankle-pain/anterior-front-ankle-impingement), [NHS posterior ankle guidance](https://msk-bexley.nhs.uk/conditions/foot-and-ankle-pain/posterior-back-ankle-impingement) |
| `elbow_impingement` | CALM, RESTORE | `elbow_impingement_elbow_cars` | [UTHealth orthopaedic guidance](https://med.uth.edu/ortho/posterior-impingement-of-the-elbow/) |
| `wrist_impingement` | CALM only | None | [Peer-reviewed middorsal wrist review](https://pmc.ncbi.nlm.nih.gov/articles/PMC9036339/) |

All sources were inspected directly. Where PMC's browser page challenged access,
the primary full text was retrieved through Europe PMC's fullTextXML service
(PMC8349584 and PMC9036339). The wrist ulnar-impaction guideline and Oxford
shoulder PDF could not be fetched directly; no rule from those inaccessible
documents is encoded. Postoperative portions of these papers are not used to
authorize automatic rehab. An anatomical inventory group is not a diagnosis.

Three originals are repaired and reviewed, preserving their IDs and original
source history:

- Shoulder wall slides become one supported comfortable slide, without forced
  chin tuck, posture correction, resistance, overhead progression or camp-phase
  changes. The source supports wall slides; the bounded baseline is conservative.
- Hip switches become small supported supine hip rotation, without the deep
  seated 90/90 position, adduction, forced range or added band/tempo. The
  non-operative ISHA section supports pain-free ROM that avoids joint irritation.
- Elbow CARs become supported unweighted bend/straighten movement, without
  forced terminal extension or loaded end-range control. Mechanical blocking or
  locking calls for assessment; physical therapy is part of conservative care.

Six entries are new: five `{region}_impingement_recovery_support` CALM guidance
entries and `ankle_impingement_reviewed_restore`. The ankle baseline uses a small
unweighted middle range; the product cannot select front/back subtype-specific
end-range exercises. All nine entries are reviewed and explicitly prescribed by
their owning regional profiles. There are 54 impingement inventory drills after
rollout. There is no reviewed dormant LOAD drill and no fabricated prescription
for an unsuitable original.

45 originals remain dormant and `needs_review`, with unchanged content/source
hashes: the original two ankle drills, one hip distraction, three other shoulder
drills, one elbow distraction, all four wrist drills and all 34 drills in the
15 unsupported regions. Band traction/undefined external load/end-range
compression and push-up variants do not establish safe baseline demand.
Kettlebell, therapist-or-self manipulation, biting and facial-fascial variants
lack a defensible role for these profiles. Groin/glute/arm/chest/scapular groups
do not establish which joint is diagnosed; spine/neck/face/jaw content can overlap
neurological or other conditions; unspecified has no anatomical identity.
Hand/finger traction and tendon glides do not establish a regional impingement
protocol. None automatically inherits another region's drills.

## Regional boundaries and missing progression inputs

The family remains shared mechanics; the profiles own content and restrictions.
Each has an exact region/type, contact limit none, its own reviewed identities,
evidence sources and live stages. `blocked_regions` represents the involved
joint using existing vocabulary. Advice about positions remains in the fixed
prescription; no new runtime position detector or diagnosis heuristic is added.
Camp availability is GPP/SPP/TAPER for baseline-bearing groups, independently
of rehabilitation stage. Legacy sibling notes remain dormant.

| Region | Why LOAD remains closed; missing evidence/input |
|---|---|
| Shoulder | No reviewed LOAD set or sourced incoming clinical criterion. Exercise ease, individually selected resistance and functional movement tolerance are not captured checkpoints; qualitative symptom improvement alone cannot substitute. |
| Hip | No reviewed LOAD set or sourced incoming clinical criterion. Individual ROM, strength, neuromuscular control and provoking activity assessment are not captured; the non-operative consensus is individualized and postoperative RTS criteria are not transferred. |
| Ankle | No reviewed LOAD set or sourced incoming clinical criterion. Front/back impingement identity, provoking range, individual weight-bearing/functional tolerance and selected resistance are not captured. A calendar interval in one subtype's guidance cannot unlock the generic regional profile. |
| Elbow | No reviewed LOAD set or sourced incoming clinical criterion. Mechanical block/locking assessment, tolerable extension range and an individualized strength/activity assessment are not captured. A throwing programme is neither a combat-sport clearance rule nor an evaluable product checkpoint. |
| Wrist | RESTORE itself remains closed. Dorsal capsular and other wrist presentations can require protection/splinting; subtype, immobilization status and permitted motion are not captured. No reviewed movement/LOAD set or sourced evaluable transition exists. Postoperative ROM/strength timelines are not applicable. |

These gaps are not invented thresholds or encoded progression rules. They
explain why the sources cannot establish a product-evaluable transition.
`CAPTURED_FUNCTIONAL_CHECKPOINTS` stays empty. Zero RESTORE → LOAD transitions
become promotable. LOAD, DYNAMIC and RETURN remain closed for all five profiles.
Missing input, truncated history, unresolved setback, an unsupported target
stage, generic readiness, camp phase or clearance cannot open them. Wrist
improvement pointing to non-live RESTORE fails closed with `stage_not_activated`.

No sets/reps/duration/external load/pain ceiling are inferred. Low/moderate
eligibility and minimum-gap cadence remain existing product rules. Comfortable
non-provoking motion is a conservative baseline constraint, not a universal
claim that pain means damage or that all impingement exercise must be pain-free.
Hip pain-free ROM is specifically supported by the non-operative consensus.

## Safety and preservation

All 26 previous raw profiles, hashes and prescriptions are exactly preserved;
regressions compare their decisions, schedules and frozen prescriptions at
CALM/RESTORE with known and unknown sides. All 1,589 original bank IDs remain;
only the three listed impingement originals change. Non-impingement bank content
is unchanged. Medical routes, clinician hierarchy, setback responses, bundles,
Today readiness, allocation ceilings, completion ownership and delayed feedback
continue through the existing engine. No database schema/RLS/migration change
or production database mutation is required.

Two previously unrecognized serious phrases, `full thickness rotator cuff tear`
and `major structural tear`, are added to the existing urgent phrase set so a
stored impingement label cannot override them. The 33 canonical types are
unchanged. Tendon seeding replaces existing profiles in place to preserve byte
order when later families are added; its profile content is unchanged. Its
historical tests now compare the tendon inventory and named previous profiles
without forbidding future families. This rollout's fixture still proves every
other original drill remains unchanged.

## Verification and coverage

The family suite covers exact type/region, reviewed identity/hash selection,
stale content, worsening, severe/high and structural reports, no symptom/type
absorption, unknown-side recording without capacity credit, exact episode
ownership, closed advanced stages, dormant metadata, real completed exposures,
negative delayed responses, complete/truncated history, unchanged previous
profiles, preserved IDs/source history and byte-idempotent bank/review/profile
seeding. Five profile/type pairs are added: 26 → 31 (+5); four also add RESTORE
coverage while wrist adds CALM protection only.

Validation: 169 focused impingement tests; 2,280 relevant rehab/previous-family
regressions passed, with 15 real PostgreSQL lock tests skipped locally because
`REHAB_TEST_DATABASE_URL` is not configured (these run in CI). All 26 isolated
database acceptance checks pass. Bank, clinical, metadata and vocabulary
validators, metadata ledger/application checks, Ruff, Python import checks and
`pip check` pass. The bank validator has zero errors/warnings and existing
migration-debt information only. The unrelated full repository suite and hosted
CI results are not claimed by the local focused verification.
