# Strain family rollout

Seven new active muscle-strain profiles: hamstring, calf, groin, quads, biceps,
triceps and shoulder. Existing chest strain and ankle sprain prescriptions retain
their reviewed policy hashes. All nine profiles use the existing resolver.

## Bank repair

All 28 original strain entries in those seven regions plus chest are now reviewed.
Their camp-phase progression text has been replaced with fixed exercise instructions,
explicit equipment and mechanical demand. Original IDs remain; original names,
notes and source hashes are retained in ledger source_history. Current hashes match
the edited content. Unknown external load stays unknown.

Hamstring bridge, double-leg calf raise and side-lying hip adduction now use their
original bank IDs directly in RESTORE prescriptions. The three duplicate variants
introduced in this unmerged branch were removed. Four pre-existing calf duplicates
remain with the same four debt allowances; only their stage/name keys changed.

Eleven additional fixed routines supply CALM support and the missing early movements.
The bank contains 1,556 drills and the ledger contains 41 reviewed strain records.
Twenty-five original region groups are inventoried in strain-family-pre-rollout-audit.json.
Other regions were not clinically rejected; they have no active regional prescription.

## Active prescriptions

| Region | CALM | RESTORE |
| --- | --- | --- |
| Hamstring | Protective guidance | Bent-knee double-leg bridge |
| Calf | Protective guidance | Supported double-leg heel raise |
| Groin | Protective guidance | Unresisted side-lying adduction |
| Quads | Protective guidance | Supported knee movement |
| Biceps | Protective guidance | Supported elbow movement |
| Triceps | Protective guidance | Supported elbow movement |
| Shoulder | Protective guidance | Supported pendulum |
| Chest | Existing guidance | Existing comfortable movement |

Baseline work has no invented numerical dose. CALM/RESTORE eligibility is the
existing low/moderate product safety gate, not a diagnosis grade. Calf raises retain
the source's prerequisites: settled pain, no crutches and pain-free toe standing.
Unknown-side RESTORE uses CALM fallback for movements needing a known affected side.

Reviewed resisted bank exercises are classified LOAD and retained for later use.
Their mechanical review does not establish efficacy, dose or clearance for a specific
equipment variant. LOAD/DYNAMIC/RETURN remain closed until the app can evaluate
sourced clinical transitions. Massage/rolling is excluded from acute prescriptions.

## Sources

- General protection and comfortable movement: https://www.nhs.uk/conditions/sprains-and-strains/
- Hamstring staged rehabilitation: https://pmc.ncbi.nlm.nih.gov/articles/PMC2867336/
- Calf strain advice: https://www.hey.nhs.uk/patient-leaflet/soft-tissue-injury-calf-strain/
- Adductor rehabilitation: https://pmc.ncbi.nlm.nih.gov/articles/PMC10569248/
- Quadriceps strain: https://pmc.ncbi.nlm.nih.gov/articles/PMC2941577/
- Upper-arm early elbow movement: https://www.nbt.nhs.uk/our-services/a-z-services/emergency-department/ed-miu-patient-information/elbow-injuries
- Shoulder soft-tissue movement: https://www.leedsth.nhs.uk/patients/resources/early-advice-and-exercises-for-soft-tissue-injuries-of-the-shoulder/

Upper-arm guidance supports gentle elbow movement for uncomplicated muscle strains;
it is not a biceps/triceps tendon-rupture or surgical-repair protocol. Shoulder advice
supports early pendulum movement, not clearance for loaded pressing or contact sport.

## Rollout and checks

Apply supabase/migrations/20261002234842_pathway_profile_unknown_side.sql before
activating new profiles in production. It generalizes existing completion attribution
using exact frozen profile ownership; unknown-side feedback cannot provide positive
advanced-stage capacity evidence. No production migration has been applied here.

Reproduce content with python tools/seed_strain_family.py. Validate with the bank,
clinical and metadata validators, then run the strain, pathway, completion, selector,
scheduling, readiness and injury-safety tests. The seed is byte-idempotent.
