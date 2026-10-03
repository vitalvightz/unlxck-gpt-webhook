# Sprain and instability regional baseline rollout

The complete family audit covers 117 original drills in 57 groups across 25 bank
regions. The original descriptions and source hashes are retained in
`sprain-family-bank-audit.json`.

Nine new exact region/type profiles join the existing ankle sprain profile:

| Region | Type | RESTORE baseline |
| --- | --- | --- |
| Ankle | Instability | Supported balance on firm ground |
| Knee | Instability | Supported heel slide |
| Toe | Sprain | Comfortable seated toe movement |
| Wrist | Sprain | Supported wrist bend and straighten |
| Elbow | Sprain | Supported elbow bend and straighten |
| Shoulder | Sprain | Supported pendulum |
| Shoulder | Instability | Gentle shoulder blade setting |
| Hand | Sprain | Gentle opening and closing |
| Fingers | Sprain | Gentle finger bend and straighten |

Each new profile has separate CALM protective guidance and a single RESTORE
movement. Instability guidance avoids testing giving way and calls for assessment;
it does not copy acute sprain healing timelines. Unknown-side injuries receive
CALM guidance rather than side-specific RESTORE work. Numeric doses and positive
capacity evidence are not invented.

## Bank repairs and boundaries

34 original drills now describe one fixed movement, equipment requirement and
demand. Their original IDs remain; previous descriptions and hashes are preserved
in the review ledger. These repaired drills remain outside active prescriptions
in LOAD/DYNAMIC stages. Mechanical review does not establish clinical efficacy,
dose or readiness for their equipment variants.

18 new baseline entries and the three preserved ankle prescriptions bring the
family to 55 reviewed entries. The other 80 originals remain dormant in automatic
pathway prescriptions. Muscle/head/unspecified labels do not establish a joint
diagnosis. Unexplained wrist, hand, finger and other regional instability does not
inherit a sprain profile. No knee sprain group exists in the audited bank.

All nine previous profile hashes and their prescriptions remain unchanged.
There are now 18 active regional profiles across the strain and ligament families;
the seven-family taxonomy and serious-injury medical gates are unchanged.
LOAD/DYNAMIC/RETURN remain closed until separately sourced progression criteria
and the inputs needed to evaluate them exist.

## Sources and verification

Sources are recorded beside each prescription and bank entry. They include
[NHS sprain guidance](https://www.nhs.uk/conditions/sprains-and-strains/),
[the ankle clinical practice guideline](https://doi.org/10.2519/jospt.2021.0302),
[NHS ankle movement guidance](https://www.rightdecisions.scot.nhs.uk/patient-information-leaflets/primary-community-services/physiotherapy/ankle-injuries/),
[knee soft-tissue guidance](https://www.hey.nhs.uk/patient-leaflet/soft-tissue-injury-knee/),
[supported wrist movement](https://www.cuh.nhs.uk/patient-information/hand-therapy-active-wrist-exercises/),
[hand and finger movement](https://www.leedsth.nhs.uk/patients/resources/the-hand-and-wrist/),
[elbow injury guidance](https://www.nbt.nhs.uk/our-services/a-z-services/emergency-department/ed-miu-patient-information/elbow-injuries),
[shoulder soft-tissue guidance](https://www.leedsth.nhs.uk/patients/resources/early-advice-and-exercises-for-soft-tissue-injuries-of-the-shoulder/)
and [shoulder instability guidance](https://msk-bexley.nhs.uk/conditions/shoulder-pain/shoulder-instability).
Toe guidance uses the general comfortable-movement baseline; it does not claim a
diagnosis-specific MTP protocol or return-to-sport criteria.

`tests/test_sprain_family_coverage.py` verifies exact pairing, bank hashes,
completion/exposure attribution, scheduling, symptom regression, unknown-side
fallback, medical gates and closed advanced stages. Existing pathway equivalence
tests retain the ankle and strain behavior. The SQL acceptance harness also checks
wrist sprain and ankle instability attribution. No new migration is required:
the generic frozen-profile migration shipped with #2718 already supports them.

The text-only option adapter now scopes its policy guard to the exact injury
type as well as region. A new knee instability profile therefore cannot erase
the bank identity of legacy knee pain work; active profiles still cannot gain
alternates without per-episode evidence. Unknown-demand and camp-phase tests
use explicit fixtures rather than assuming repaired originals remain unreviewed.
