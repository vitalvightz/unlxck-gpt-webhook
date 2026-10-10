# Lateral elbow: consumer rehabilitation workflow

PR #2813 merged externally on 10 October 2026 before the questionnaire correction was published. Draft follow-up #2814 updates the existing implementation on Main `4d7dd5cf`. It removes the worksheet **and its mandatory eligibility dependency**, rather than leaving new athletes permanently blocked. No automatic merge.

## 1. Exact applicability

Only canonical `elbow_tendonitis`, an owned active left/right episode, mild/moderate severity and explicitly reported outside-of-elbow location can consider this starter. One optional location answer lives in the existing injury editor: Outside of elbow / Elsewhere / Not sure. A valid existing lateral observation can supply location when no location marker exists; an explicit unknown, other or conflicting answer cannot be overridden by older evidence. Free-text labels alone do not establish applicability. This is a report of location, not a diagnosis.

Medial, posterior, generic tightness/pain, severe, traumatic, structural, neurological or conflicting presentations do not gain this LOAD option. Existing conservative baselines and unsupported-injury recovery monitoring remain intact.

## 2. Evidence and interpretation

Directly inspected sources:

| Source | Evidence used | Boundary |
| --- | --- | --- |
| [JOSPT/APTA 2022 CPG](https://www.orthopt.org/uploads/content_files/files/lucado_et_al_2022_lateral_elbow_pain_and_muscle_function_impairments.pdf), [DOI](https://www.jospt.org/doi/10.2519/jospt.2022.0302) | Full guideline inspected. Wrist-extensor resistance exercise for subacute/chronic lateral tendinopathy; elbow/wrist motion, grip, irritability and loading tolerance inform assessment. Differential diagnosis includes neural and joint/instability conditions. | Does not validate an app stage algorithm or universal pain, grip, ROM or starting-load cutoff. Suggested training protocols are not automatic promotion rules. |
| [RJAH NHS specialist guidance](https://www.rjah.nhs.uk/our-services/therapy/supported-self-care/tennis-elbow/) | Direct page inspection: supported palm-down forearm, raise wrist, lower slowly over five seconds, 10–15 repetitions. Red flags require assessment. | Written instructions do not specify added weight; linked exercise images were unavailable. Empty hand is an explicit conservative product restriction, not a claim that all patients should use zero external resistance. |
| [Yoon et al. 2021 systematic review](https://pmc.ncbi.nlm.nih.gov/articles/PMC8432114/) | Full article inspected. Eccentric work can improve pain/strength in studied programmes; six trials, heterogeneous dosing and limitations. | No universal load/progression rule or guaranteed superiority for every outcome. |
| [Peterson et al. 2011 RCT](https://pmc.ncbi.nlm.nih.gov/articles/PMC3207303/) | Full article inspected: 81 participants with chronic symptoms, supported forearm and progressive external resistance. Pain improved; strength/function differences were not statistically significant. | Its sex-specific starting weights, 3×15 dose and weekly increments are not imported into this option. |
| [Leicestershire NHS leaflet, May 2026](https://www.leicspart.nhs.uk/wp-content/uploads/2026/06/LPT-CHSMSK17-Tennis-Elbow.pdf) | Full leaflet inspected. Supported palm-down forearm, assisted raise/slow lowering, 10 repetitions; external household/dumbbell resistance is described. | No defensible universal kilogram boundary; supports keeping the external-weight bank candidate dormant until individual load selection is available. |
| [Peterson et al. 2014 RCT abstract](https://pubmed.ncbi.nlm.nih.gov/24634444/) | PubMed abstract inspected, not full text. Progressive eccentric/concentric exercise comparison provides context. | Not used to invent a prescription threshold. |

Product interpretation: the 2022 clinician guideline supports assessment and resistance exercise; it does not establish an eight-field consumer worksheet as a mandatory entry rule for every gentle movement. RJAH patient guidance directly supplies supported palm-down wrist raising and five-second lowering with symptom monitoring and red flags. The consumer criterion therefore considers **only this empty-hand starter**, within reported clinician loading permission, after actual reviewed RESTORE work and attributable non-worsening responses. It does not certify grip strength, range of motion, disease course, medical clearance or readiness for external resistance.

Ten repetitions use the lower end of RJAH guidance. One set and maximum once daily remain conservative product ceilings, not a validated complete treatment programme or universal cadence. No added resistance, forceful grip, speed, forced range or automatic increase. Follow clinician restrictions and stop for worsening. Known adverse clinician observations remain a veto even after a reassuring check-in or later positive assessment.

## 3. Shared infrastructure

Reuse clinician_clearance_report, injury details and episode ownership, the shared progression engine, existing exposure and delayed-response tracking, Today scheduling/allocation, generation context and frozen-prescription checks. No new engine, form, portal, table, endpoint or clearance system. The old typed assessment readers and v1 criterion remain available for historical evidence; no fake observations or verified-clinician pins are created.

## 4. Exact interaction counts

One selection, field entry or button activation counts as one interaction; individual keystrokes/picker mechanics do not. No repeated permissions when advice is unchanged.

| Step | Before worksheet correction | Final consumer workflow |
| --- | --- | --- |
| Elbow eligibility questions | 8 dropdown answers + manually entered assessment date/time = **9 answers**; open clearance + expand worksheet + Save = **12 interactions** | **1 location answer**, once, in existing injury details. Edit + answer + Save = **3 interactions** from an expanded card; **4** if the card first needs expansion. **0** extra assessment answers or timestamps. |
| Existing clinical clearance, both permissions change | **2 choices + open + Save = 4** | **4**, unchanged; no additional exercise-clearance question |
| Achilles location | **1** once in injury details | **1**, unchanged |
| Achilles assessment in Today | **0** | **0** |
| Standalone rehab completion | **1** Completed/Modified/Skipped tap | **1**, unchanged |
| Injury response after rehab | **1** Better/Same/Worse tap | **1**, unchanged |
| Next-day follow-up when pending | **1** existing injury-response tap | **1**, unchanged; internally records the exact pending exposure response |

Normal standalone rehab remains **2 interactions on the rehab day**, plus **1 existing response tap on the next day when needed**. Modified work records changed work; skipped work does not create exposure. Earlier check-ins cannot become tolerance for future work. Multi-injury responses remain individual and episode-bound. Mixed S&C sessions retain their existing training log and rehab completion choice.

The active Today session panel uses `rehab_tracking=injury_checkin`. Actual completion creates exposure; a same-day explicit injury response after that exposure supplies the during-work response; the existing pending next-day tap supplies the delayed response. Legacy assessment/response questionnaire components are not mounted by Today.

## 5. Versioned eligibility and stage authority

New criterion `lateral_elbow_reported_load_permission_v2` explicitly replaces the **mandatory v1 functional-assessment dependency** for the bounded starter. Elbow profile becomes v3; the starter option becomes v2. Retained v1 assessment contracts are not relabelled or automatically passed.

LOAD requires all of:

- Exact active injury/episode/side, supported tendon presentation and explicit lateral location (or valid existing lateral observation).
- Current episode self-reported rehabilitation permission `loading` or `sport_specific`; training/contact permission alone is insufficient.
- Completed reviewed RESTORE exposure, stated demand and attributable after-rehab and next-day Better/Same responses.
- Complete exposure/observation history, no unresolved worsening, no explicit restriction, medical, structural or neurological hold, and no known adverse assessment finding.
- Reviewed target content, available table support and existing daily allocation/multi-injury protections.

Permission, a Better response or completion alone cannot promote. Missing location/permission/response/history explains its specific blocker. The shared engine alone chooses the stage; no manual stage flag. DYNAMIC and RETURN remain closed.

## 6. Fixed prescription and video preparation

Retain the same supported empty-hand wrist-extension identity and mechanics: forearm palm-down on table, wrist free, comfortable range within clinician restrictions, five-second lowering, **1×10 maximum once daily**. Instructions no longer claim a clinician measured the athlete's range. External-weight wrist curls and unrelated elbow exercises remain dormant. Table access uses existing equipment settings.

YouTube preparation stays on the existing approved exercise_media/S&C player path. Exact canonical exercise keys decorate presentation after freezing; videos cannot alter dose, eligibility or historical prescriptions. The 41-row curation CSV still contains intentionally blank URLs pending reviewed clips/import. No video was invented or published. Elbow clips must show empty-hand mechanics; Achilles clips must show floor-level mechanics.

## 7. Frozen history, scope and storage

Re-evaluate unstarted work when permission/location, evidence, equipment or safety changes. Old-policy/content hashes hold incompatible unstarted work. Started/completed snapshots remain unchanged. Self-reported permission is never treated as independent clinical verification.

Only the elbow LOAD criterion and starter copy change. Both elbow CALM/RESTORE prescriptions, the Achilles profile and all 63 other profiles remain unchanged. One existing elbow bank record and its metadata review are revised; no new exercises or profiles are activated. Policy v3 hash: `76ddc4dcf6375467549933670e7268829a2496a34a7e7e503fece71f456b0ff5`; drill hash: `7d9132531396ef0ad7d694eacb5ec60721afb5094fa54d79056f2941dc45a2a5`. Historical tooling accepts only these exact documented revisions when reconstructing old inventories; old baseline entries are preserved. Deterministic current rationalisation reports are regenerated.

**No database migration.** Location uses the existing injury description/event mechanism, like Achilles; clinician permissions and historical observations retain existing contracts. Internal location markers are hidden from labels and editable notes.

## 8. Verification and limitations

Final local checks and exact-head CI results are recorded in the PR description. Tests cover new consumers without assessments, actual RESTORE completion/check-in attribution, missing/worsening responses, unsupported locations, old training-only permission, adverse findings, ownership, freeze/history, daily allocation, generation, bank/history preservation and the Achilles/frontend journeys.

This is a conservative software eligibility rule for a limited starter, not a clinically validated diagnostic or return-to-sport tool. Red flags and known restrictions continue to require appropriate review. Unknown site remains conservative; no external load or later-stage escalation is offered. Video curation remains outstanding. No production athlete data or deployment settings were modified.
