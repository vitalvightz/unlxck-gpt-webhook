# Achilles RESTORE → LOAD clinical review, version 1

**Activation: closed.** No Achilles LOAD prescription or transition is activated. DYNAMIC and RETURN remain closed. This implements outcome B: a deterministic review of the captured inputs and explicit clinical blockers, together with an athlete reporting flow. It does not claim a clinically approved PASS criterion.

Base: Main `2454c9000779158802ffbebbf053fd43664d2f8b`, after #2743 merged. Its shared envelope, protocol registry, episode context, append-only event storage, ownership, provenance, timestamp readers and persistent medical holds are retained. No new event type, table, migration, verification channel or rules DSL is introduced.

## Evidence inspected

Reviewed on 6 October 2026. The final 2024 CPG PDF and Dutch guideline full text were inspected; the September 2024 draft is not used. Sources justify clinical principles, not a universal numerical threshold for Unlxck's RESTORE → LOAD transition.

| Source and location | A: directly supported clinical statement | B: product interpretation / limitation |
|---|---|---|
| [Dutch multidisciplinary guideline, de Vos et al., 2021](https://bjsm.bmj.com/content/55/20/1125), diagnosis module 2; treatment module 4 and figure 3. [Open-access full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC8479731/). | Diagnosis combines local symptoms, load-related pain, thickening and palpation findings; early thickening can be absent. Exercise is individualised, with pain during/after exercise and fatigue guiding progression. Initial insertional exercise should use a flat surface. | A broad athlete-entered label/site is insufficient to establish this clinical diagnosis or select an individual prescription. The figure is not evidence for a universal product-stage cutoff. |
| [Chimenti et al., final 2024 midportion CPG](https://www.orthopt.org/uploads/content_files/files/Achilles_Pain_revision_2024.pdf), CPG2, CPG3–4, CPG10–13. DOI: 10.2519/jospt.2024.0302. | Midportion recommendations may not generalise to insertional disease. Loading is first-line for midportion tendinopathy without presumed structural frailty; intensity reflects pain tolerance and/or functional capacity. The final frequency recommendation is at least three times weekly, with tolerated intensity. | This is a treatment recommendation, not evidence that three sessions, a pain score or a reported heel rise opens this gate. It does not determine the dose of the current unilateral lowering candidate. |
| [Kent Community Health NHS insertional guidance](https://www.kentcht.nhs.uk/leaflet/achilles-insertional-tendinopathy/), loading exercises, dated 2 December 2024. | Supported bilateral rises/lowering on a flat surface precede podiatrist-advised single-leg progression. The advice is to be followed under healthcare-professional guidance. | The dormant candidate lowers on the affected leg. Floor-level execution alone does not justify prescribing it automatically for insertional cases. |
| [Silbernagel et al., 2020 clinical concepts review](https://pmc.ncbi.nlm.nih.gov/articles/PMC7249277/), functional impairments and rehabilitation phases. DOI: 10.4085/1062-6050-356-19. | Heel-rise testing assesses function; symptom recovery alone does not establish functional recovery. Loading progression considers tolerance and functional recovery. | A reported count and quality label do not capture an assessment of adequacy for this selected task. Running/hopping criteria and example later-phase doses are not imported into this early gate. |
| [Gatz et al., partial rupture narrative review, 2020](https://pmc.ncbi.nlm.nih.gov/articles/PMC7589987/), introduction and diagnosis. DOI: 10.3390/jcm9103380. | Partial tears can resemble aggravated tendinopathy; sharp onset, weakness and inability to load require differential consideration. Evidence and consensus for partial-tear management are limited. | A heel rise or low symptom score cannot exclude a partial tear. Suspected structural pathology is outside this proposed gate. No partial-tear rehabilitation is implemented. |

C (unsupported for this gate): pain ≤3/10, ten heel rises, 80% symmetry, two sessions, seven days since injury, a 48-hour expiry, fixed kg, mandatory isometric-first treatment, or automatic superiority of eccentrics. None is implemented. The symptom scale's 0–10 bounds validate a reported measurement; they are not readiness thresholds. No universal assessment age limit was justified by the reviewed sources.

## Applicability and provenance

Only the exact `achilles_tendonitis` profile/current episode/side is considered. Midportion and insertional remain separate interpretation branches in code. Unknown site is UNKNOWN; no location is inferred from pain text. Acute traumatic loss of function, suspected rupture, marked weakness, incompatible/structural pathology and clinician loading restrictions prevent progression. Other posterior-heel pathology, mixed/uncertain subtype, diagnosis and structural applicability require individual clinical assessment; the current protocol does not verify them. This is not a pathway for rupture, partial tear or another injury profile.

Symptoms can be recorded by the athlete. Coach or clinician-attributed heel-rise observations can describe function, but they do not establish diagnosis, structural safety, a permitted load or clinical adequacy. Range/pathology fields describe advice the athlete reports receiving. Selecting clinician/physio does not authenticate that person, verify an examination, or confer clinical authority.

**B: product safety decision:** clinical judgments about applicability, functional adequacy for the proposed unilateral task, acceptable symptom response and an individual loading prescription must have trustworthy clinician/physio provenance before this product can promote on those judgments. The sources do not prescribe this app's authentication model. #2743's only production write path records `source: athlete_reported`, `externally_verified: false`; it cannot supply that trusted review. The form does not create a substitute verification mechanism.

## Deterministic compiled review

ID: `achilles_restore_load_review_v1`; criterion version 1; assessment protocol remains `achilles_tendon_progression_v1`, version 1. Implementation: `api/contracts/achilles_restore_load.py`. The review consumes `AssessmentContext` and the existing four registered readers:

| Availability input | What is recorded | What is still unavailable for clinical PASS |
|---|---|---|
| `achilles_site_assessed` | Explicit reported site and assessor | Verified applicability/diagnosis and structural exclusion |
| `achilles_heel_rise_assessed` | Completed observation, mode, quality, optional actual count, reported usability | Clinical adequacy for the selected LOAD exercise, rather than test usability |
| `achilles_loading_response_assessed` | Actual task/time, during and delayed symptoms/time | A reviewed interpretation of acceptable response to the selected prescription; no baseline trajectory or clinician judgment is captured |
| `achilles_range_load_assessed` | Reported assessed range, resistance/actual kg where external, tolerance and assessor usability | An individual actionable range/load/dose prescription with trusted provenance; “clinician limited” has no actual limit detail |

Evaluation order:

1. Exact profile applicability; medical concern/current worse report → FAIL.
2. Shared input readers enforce attribution, chronology, latest snapshot, history and setbacks. Missing/invalid input → UNKNOWN; reported unusable/not-tolerated input → FAIL. These are conservative product exclusions, not new numerical clinical thresholds.
3. Unknown safety exclusions cannot be read as negative findings.
4. Midportion reports retain a structural-applicability review blocker; insertional reports retain a clinician-directed unilateral-progression blocker.
5. Even four availability PASSes leave UNKNOWN: trusted clinical review, selected-task functional adequacy, acceptable symptom interpretation and a usable individual prescription are unavailable. All blocker codes are returned.

**There is no PASS path.** `promotion_allowed` and `externally_verified` are literal false. This review is exposed as `rehab_decision.achilles_load_review`, including when no assessment has been recorded. The existing transition engine can evaluate this exact checkpoint for the exact profile and RESTORE → LOAD only, but the production catalog does not declare an approved clinical requirement or activate it. The captured *clinical* checkpoint registry remains empty. Test-only proposed transitions prove that an open stage cannot bypass the review's UNKNOWN/FAIL.

Family/profile transition composition remains authoritative. Future completion of this criterion requires clinically reviewed judgments, real capture with acceptable provenance and a usable prescription, then a separate reviewed production declaration. Changing a JSON flag or accepting a client verification claim cannot make this review pass.

## Freshness, history and safety

No arbitrary time-to-injury or maximum assessment-age rule is added. The shared latest whole snapshot supersedes earlier snapshots even if incomplete. Observation times must belong to the current episode and be no later than recording; replay uses an explicit aware `as_of` and ignores later-recorded assessment snapshots. The caller supplies the injury state for the replay. A later episode setback invalidates earlier assessment/loading/delayed-response evidence; an improvement can restore baseline behaviour but cannot revive the old assessment for promotion. Truncated/incomplete history remains UNKNOWN. Malformed newest snapshots cannot fall back to an earlier success.

Medical concerns remain authoritative across later reassuring reports or athlete-reported clearance. The existing hold/clearance hierarchy, multi-injury conservative precedence, completion/exposure ownership, safety revisions and frozen-prescription semantics are unchanged. The form records concerns through the existing API; it has no hold-release operation.

## Candidate and prescription decision

Reinspected `achilles_tendonitis_eccentric_calf_drops_on_step`: the current name is **Floor-level controlled Achilles lowering**. The historical ID is retained. Mechanics: stable support, both heels rise, weight transfers to the affected leg, that heel lowers slowly only to the floor. No step, deep dorsiflexion, speed increase or added weight is permitted. This is bodyweight unilateral eccentric/control work, rather than the current seated RESTORE movement, so a LOAD classification is plausible; classification does not prove readiness or prescribe it.

The current candidate has `dose: null` and no active clinical prescription. Bodyweight does not encode the proportion of weight/support transferred or an individual tolerated demand. Its range restriction is conservative; an individual clinician-limited range cannot be assumed equal to its fixed range. Insertional bilateral-first guidance is not satisfied merely by starting the rise with both legs and lowering on one. Midportion loading evidence does not select this exact mode/dose for every athlete.

No other current exact-profile reviewed LOAD candidate supplies the missing prescription. Unreviewed massage content is not a substitute. Changing the anchor into bilateral movement or inventing a dose would change clinical meaning or introduce unsupported precision, so no bank repair is made. **Selected active LOAD drills: none.** No sets/reps, tempo, kg, daily frequency or hidden progression is added. CALM/RESTORE text, cadence and dose remain exactly as before.

## Product flow and remaining blockers

Today shows a collapsible “Record Achilles assessment” form only for a backend-identified Achilles review with a current episode and known side. The side is server-owned. It collects assessment context/assessor/site/safety, actual heel-rise observations, actual loading/delayed symptoms and assessed range/load. Unknown defaults remain unknown; numeric answers are never derived from completion, time or status. Datetime entries use the athlete's local time and submit aware ISO timestamps. Missing delayed responses can be recorded as unavailable; adding them later requires a complete new snapshot. Unchanged failed writes keep their report ID for idempotent retry.

The form records an assessment that already occurred; it does not prescribe a new test. It explains reported provenance and that LOAD remains closed. Unknown side requires correcting injury details. A successful save refreshes Today; a refresh failure still acknowledges persistence. Generated API types remain the request/response source of truth.

Activation blockers are independent:

- Verifiable clinician/physio review cannot be captured through the athlete-owned API.
- Reported test usability is not selected-task clinical adequacy.
- Symptom numbers lack an approved interpretation for this exact prescription/population.
- The fixed unilateral candidate lacks a usable reviewed individual prescription/dose; insertional progression additionally needs separate clinical review.

This PR does not solve those blockers by inventing measurements, attestation fields, thresholds or a second persistence model. All 64 profile identities/hashes, the bank, review ledger, exact-duplicate archive and pathway catalog remain unchanged. No other injury profile changes. No LOAD, DYNAMIC or RETURN activation.

## Verification

Targeted tests cover availability versus clinical evaluation, subtype separation, identity/side/episode ownership, incomplete/newer snapshots, setbacks, persistent concerns and restrictions, no completion/count/time/phase proxies, false verification claims, explicit replay, the proposed engine checkpoint and all-profile preservation. Web tests cover unknown and actual numeric reports, owned submission, retry identity, refresh failure, omitted/invalid attribution and missing times. Browser layout/accessibility fixtures render the actual component on mobile/desktop in dark/light themes; React DOM tests cover its submission handlers. Existing authenticated backend capture tests exercise the owned, consent-protected endpoint.

Run progression/pathway, Today, completion/exposure, clearance/multi-injury, surface, archive/rationalisation, generated-schema and migration suites, then Ruff/import checks and web typecheck/lint/unit/build/browser tests. Hosted PostgREST deployment and real clinician verification are not claimed. Apply #2743's existing migration through the normal release process before using its capture API in a deployed environment.

Local results: 35 clinical-review/preservation cases; existing Achilles capture/shared-boundary/auth cases; 1,912 broader progression/pathway/Today/completion/exposure/clearance/multi-injury/surface/archive/rationalisation/schema/migration checks; 16 real PostgreSQL migration/concurrency cases; 1,683 web unit tests; four Chromium mobile/desktop dark/light layout/accessibility cases. All passed. Ruff, changed-module imports/compile checks, generated API types, typecheck, production build and all three preservation audit `--check` commands passed. ESLint passed with 51 existing warnings and zero errors. GitHub CI status is reported on the PR separately; these local results do not claim the full remote Python suite passed.
