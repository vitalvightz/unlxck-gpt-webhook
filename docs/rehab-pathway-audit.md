# Rehab pathway audit

21 October 2026. Pulled Main at `7f4ef5d8`, including merged #2982.
Audit only. No app code, prescriptions, clinical rules or stages changed.

## Coverage now

Counts show profiles with published content. Athlete eligibility still applies.

| Family | Profiles | CALM | RESTORE | LOAD | DYNAMIC | RETURN |
|---|---:|---:|---:|---:|---:|---:|
| Strains | 8 | 8 | 8 | 0 | 0 | 0 |
| Sprains / instability | 10 | 10 | 10 | 1 | 0 | 0 |
| Tendons | 8 | 8 | 8 | 3 | 0 | 0 |
| Joint irritation / impingement | 5 | 5 | 4 | 0 | 0 | 0 |
| Hyperextension / joint trauma | 6 | 6 | 0 | 0 | 0 | 0 |
| Contusions | 11 | 11 | 5 | 0 | 0 | 0 |
| Nonspecific symptoms | 16 | 16 | 3 | 0 | 0 | 0 |
| **Total** | **64** | **64** | **38** | **4** | **0** | **0** |

The seven family structures already exist. None has shared clinical progression criteria. Only the Achilles, elbow, ankle and shoulder pilots have LOAD criteria.

There are **111 published exercise identities**, used in 112 prescriptions: 64 CALM, 43 RESTORE and 5 LOAD references. One wall slide serves two profiles.

The bank holds **1,604 entries**. Mechanics reviews cover 169; 58 of those are unpublished. A mechanics review does not establish a safe dose or readiness to progress. Five entries are labelled DYNAMIC, all outside the four LOAD pilots. None is published. No entry is labelled RETURN.

Another 1,433 entries have no stage, including 104 surface-care entries outside the seven families. Do not infer stages from names.

## Full inventory

- [64 profiles across five stages: 320 rows](rehab-pathway-audit-stages.csv). Exercise IDs/names, exact prescriptions and limits, current criteria, sources and gaps.
- [All 1,604 bank entries](rehab-pathway-audit-bank.csv). Review state, publication, equipment, dose and missing metadata.
- [Counts, input hashes and existing readers](rehab-pathway-audit-summary.json).

A location/type match means a candidate to inspect, not clinical suitability. Regional pools stay unassigned. Historical review notes are labelled because later publication changed some results.

## What we can reuse

| Existing part | Reuse | Does not prove |
|---|---|---|
| Engine, families and profiles | Shared decisions and safety checks | Missing clinical criteria |
| Injury reports and setbacks | Current symptoms and safety history | Strength or sport readiness |
| Completed rehab and responses | Work done and response to that work | Tolerance of harder work |
| Reported permission and subtype | Bounded LOAD entry | Impact or contact readiness |
| Achilles assessment records | Site, heel-rise, symptoms, range and resistance | A DYNAMIC pass/fail rule |
| Elbow assessment records | Reported movement, grip and wrist-extension findings | Readiness for fast or sport work |
| Today, completion and video UI | Existing athlete flow | Unpublished clinical content |

The backend has five assessment-input readers and six functional-checkpoint evaluators. Its one compiled clinical-review criterion covers Achilles RESTORE → LOAD. The older Achilles form exists but is not shown in current Today. Stored observations still need an applicable reviewed rule; their presence is not a pass.

## Clinical questions still open

These are review questions, not proposed thresholds.

| Family | Decisions needed |
|---|---|
| Strains | Safe loading, range and speed for each muscle; separate sprinting, kicking and other sport demands. |
| Sprains / instability | Joint-specific stability, balance/control and impact evidence. |
| Tendons | Tendon/site-specific load and impact tolerance tied to the next task. |
| Joint irritation / impingement | Safe range, load and function for the diagnosed presentation. |
| Hyperextension / joint trauma | Suitable RESTORE movement first, with structural concerns and end-range limits. |
| Contusions | When movement/loading is appropriate and which site limits apply. Six profiles lack RESTORE. |
| Nonspecific symptoms | Which symptoms support guided progression without assuming a diagnosis. Thirteen lack RESTORE. |

Every new transition needs **a criterion, evidence source, collection method, reviewed pass/fail rule and published next exercise**. Family rules cannot weaken mandatory safety checks or injury-specific limits.

## First pathway to investigate

**Start with Achilles LOAD → DYNAMIC planning.** It has the most existing assessment and review plumbing to reuse. This ranking is based on code reuse; clinical review may change the order.

| Pilot | Reuse | Missing before DYNAMIC |
|---|---|---|
| Achilles | 2 LOAD options; site, heel-rise, symptom and range/load records | Applicable functional criterion, exact DYNAMIC prescription and any essential extra task evidence. |
| Elbow | 1 LOAD option; movement/grip/tolerance records | Task-specific capacity evidence and DYNAMIC prescription. |
| Ankle | 1 seated LOAD option; subtype and permission | Functional assessment evidence and DYNAMIC prescription. Seated work does not prove balance or impact tolerance. |
| Shoulder | 1 wall-push-up LOAD option; subtype and permission | Strength/control and sport-task evidence, plus DYNAMIC prescription. |

Groin has two RESTORE options but no LOAD pathway. Its LOAD criteria are a separate earlier task.

For Achilles: agree the criterion, map existing data, review one bounded next prescription, then add only missing essential capture. Test the full Today journey before publication. Reuse shared reader/evaluator structures; do not add an approval record per exercise. Clinical review determines what assessment is necessary.

## Checks and limits

Clinical, bank, review-ledger and reachability validators passed. The bank validator reported 1,913 informational notices, no errors or warnings. IDs and review joins are clean. Normalized input hashes match the current reachability report.

The [older candidate review](rehab-advanced-candidate-review.md) is historical. Its old no-LOAD totals are not current status. Source links are included in the inventory; a URL alone is not a reviewed clinical rule.

Relevant starting sources include the [2024 midportion Achilles guideline](https://www.orthopt.org/content/s/achilles-pain-stiffness-and-muscle-power-deficits-midportion-achilles-tendinopathy-revision-2024) and [PAASS ankle consensus](https://pubmed.ncbi.nlm.nih.gov/34158354/). Fresh checks were limited to indexed pages/abstracts because direct publisher/PDF requests returned 403. No new clinical review or thresholds were completed here.

The video manifest has 46 blank-URL rows for 47 published physical exercises. `shoulder_tendonitis_wall_push_up` is missing. This is a curation gap, not a clinical blocker. Live media and production athlete data were not inspected.
