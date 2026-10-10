# Lateral elbow RESTORE to LOAD implementation

Started from Main `8d125da5`, then integrated latest Main `0d6022d9` (through #2811), retaining its Today and session-preview updates. PR #2802 was confirmed merged before work began. The bounded elbow option can execute only with existing valid suitability evidence. The consumer workflow does not collect clinical assessments: without that evidence LOAD stays blocked. Production use requires merging and deploying the PR.

Consumer-workflow correction: GitHub reports #2813 merged at `2026-10-10T14:14:27Z`, before these corrections were published. The correction is a separate unmerged follow-up against Main `4d7dd5cf`; it removes the athlete worksheet rather than weakening or replacing its backend safeguard.

## 1. Exact applicability

Canonical `elbow_tendonitis`, exact left/right episode, mild/moderate severity, reported clinician-assessed lateral presentation with subacute/chronic course. The clinician must have assessed the relevant function and recommended the exact empty-hand starter. Medial, posterior, unknown, generic pain/tightness, traumatic, suspected structural/neurological and conflicting descriptions cannot borrow this gate. Existing conservative baselines remain available where appropriate; unsupported injuries retain #2802 recovery monitoring.

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

Product interpretation: require reported clinician judgment rather than invent quantitative cutoffs, plus separate loading permission, current reviewed RESTORE exposure and during/delayed responses. Ten repetitions use the lower end of RJAH guidance. One set and a maximum once daily are a conservative exposure ceiling, not an evidence-proven complete treatment programme or universal rehabilitation cadence. The clinician must specifically recommend this bounded option; a recommendation for a different programme is insufficient.

Unsupported assumptions deliberately excluded: numeric pain/ROM/grip cutoffs, universal external weights, elapsed-time promotion, a fixed number of successful sessions, automatic resistance increases, completion as measured function, and self-report as independently verified review.

## 3. Shared infrastructure reused

Existing typed `RehabProgressionAssessment` envelope and protocol registry, `rehab_progression_assessment` event, injury-episode observation endpoint/table, ownership reader, pathway requirement model, progression resolver, reviewed fixed-prescription contracts, clinician_clearance_report, exposure/delayed-response capture, Today scheduling/allocation, generation context and frozen-work checks. No new engine, generic clinical layer, event type, endpoint, portal or persistence table.

## 4. Athlete interaction and retained observations

No new athlete assessment fields. The removed elbow questionnaire had eight dropdowns and an assessment date/time input. Retained backend `lateral_elbow_progression_v1` v1 observations can evaluate existing valid data: subtype, course, safety_screen, pain_irritability, elbow_wrist_motion, grip_task, grip_function, wrist_extension_task, wrist_extension_tolerance, option_recommended. These are not inferred from permission, symptom trend or completion. Shared ownership, side, actual observation time and provenance checks remain unchanged; no timestamp or acceptable result is manufactured.

The form, import, form tests and its CSS are removed. The existing progression view explains that LOAD is on hold because current records cannot establish grip, movement and tolerance for this starter; it does not direct the athlete to fill another form. Permission, injury details, completion and Better/Same/Worse remain the only existing consumer inputs. No new form, question, portal, upload or UI section replaces the worksheet.

### Exact journey counts before and after this rework

Count one selection, field entry or button activation as one interaction; exclude individual keyboard keystrokes/native picker mechanics. These counts describe successful single-injury actions, not network retries or clinically necessary injury reclassification.

| Journey step | Before | After |
| --- | --- | --- |
| Elbow progression worksheet, enough data to attempt eligibility | 9 answers (8 selections + 1 date/time), Save, open clearance, expand form = **12 interactions** | **0 answers, 0 extra interactions**; missing evidence blocks LOAD |
| Achilles assessment in Today | **0** (already not rendered) | **0** |
| Clinician advice changes, both permission levels updated | 2 decisions + open + Save = **4** | **4**, unchanged; no repeat when advice is unchanged |
| Achilles location clarification within existing injury details | **1** selection, once; existing injury save | **1**, unchanged; unknown location cannot unlock the midportion starter |
| Standalone rehab completion | **1** Completed/Modified/Skipped tap | **1**, unchanged |
| Injury response after rehab | **1** Better/Same/Worse tap | **1**, unchanged |
| Next-day response, when pending | **1** existing injury-response tap | **1**, unchanged; same tap records the exact-episode follow-up |

Normal standalone rehab remains **2 interactions on the rehab day**: complete the work and report the injury response when needed. A pending next-day response takes **1 existing injury-response tap**; no separate duplicate answer or Save. Mixed S&C sessions retain their normal session log and one existing rehab-completion choice. Multi-injury reports stay separate and episode-bound; no answer for one injury supplies another's evidence.

The legacy Achilles assessment and post-rehab questionnaire components are not mounted by Today. The active session panel sends `rehab_tracking=injury_checkin`; actual completion creates exposure, a same-day explicit response after that exposure supplies attributable tolerance, and the existing next-day tap records the delayed response. Earlier check-ins do not prove future tolerance. We retain those safeguards and do not modify unused components to claim a UX improvement.

## 5. Criterion and PASS

`lateral_elbow_restore_load_v1`, version 1, registered with the existing functional checkpoint evaluation. `lateral_elbow_function_assessed_v1` is availability only: recorded observations can pass availability while failing clinical suitability.

PASS requires known lateral/subacute-or-chronic presentation; clear safety screen; clinician-reported suitable irritability, elbow/wrist movement, grip task/function and exact supported empty-hand wrist-extension tolerance; exact-option recommendation; explicit current loading/sport-specific rehab permission; exact owned side/episode; assessment within the episode, no future or pre-setback assessment; complete history; no later unsatisfactory functional assessment; and no medical, restriction, structural or neurological hold. Shared current-stage reviewed exposure, attributable during/next-day responses, unresolved-setback and target-content requirements must also pass. Permission alone, assessment alone and exercise completion alone cannot promote. Missing observations return UNKNOWN; unsuitable observations return FAIL.

## 6. Exercise review

Selected: new minimum content `elbow_tendonitis_supported_hand_weight_wrist_extension`.

Existing `elbow_tendonitis_eccentric_reverse_wrist_curls` has plausible lateral-extensor mechanics but needs individual external-load selection; retain identity/history and leave dormant. Triceps band content targets a different tissue and is not activated for lateral extensor tendinopathy. No unrelated elbow inventory was cleaned or restaged.

## 7. Prescription

Supported hand-weight wrist extension: affected forearm palm-down on a table, wrist free, empty hand; raise within the clinician-assessed comfortable range, lower over five seconds. One set of ten, maximum once daily, no automatic increase. No added weight/band, forceful grip, speed or forced end range. Stop for worsening during/delayed symptoms; trauma, loss of function, numbness, hot/red swelling or fever require assessment. Existing clinician restrictions and training/contact ceilings apply. Table access must be reported in the existing equipment settings.

## 8–9. Activation, Today and generation

The elbow option is executable through the shared engine only when existing valid evidence satisfies every gate. A consumer with permission, completion and improving symptoms but no starter-suitability evidence remains at RESTORE: there is no new consumer questionnaire or automatic route around that blocker. For valid existing records Today can schedule a real block, freeze it at start and capture completion/exposure; generation uses the same owned decision. Daily allocation, stripped incoming client context and exact identities remain authoritative. No manual stage flag is introduced.

Training can coexist only where existing clearance and multi-injury safety allow it. Elbow progression grants no contact permission. DYNAMIC and RETURN stay closed.

## 10. Unknown and unsupported cases

Unknown/missing/incomplete or wrong-side/episode/provenance/timestamp observations cannot promote. Unsupported sites/descriptions receive no lateral LOAD. Reduced permission, new setbacks, lost equipment, missing current-stage responses or safety holds invalidate incompatible unstarted work. Started/completed historical snapshots are preserved. Unsupported injury cards retain recovery monitoring, and resolved injuries remain recovered.

## 11–12. Storage and preservation

No migration is required: the existing episode-event JSON stores the new versioned payload. No fake clinical approval or verified-clinician pin is created. Media uses the existing backend exercise_media table and approval filtering; no public data was written.

Only elbow_tendonitis changes among 64 profiles: version 1 to 2, hash `54ed5be1448e7127798c4cdf958d022fa6842b13bf25f22314284a6604a83728`. All 63 other profiles and every existing ordered rehab-bank record remain unchanged from the starting Main. CALM/RESTORE prescription content is preserved. New drill hash: `56ba697662f47d146b43af38d56c4712d0e645d986b4a51b5a5ffc3ecbd711ef`.

Historical inventory tooling projects only the exact new reviewed addition and elbow activation through a pinned baseline, keeping old source/report checks meaningful. Current rationalisation reports are regenerated; their large generated JSON diff reflects the additional captured checkpoint, not bulk clinical edits.

## 13. Verification

Local results and GitHub CI are recorded in the PR description. Relevant coverage includes shared assessment/transition, elbow and Achilles activation, real Today start/completion/allocation, generation ownership, bank/pathway inventory, frozen prescriptions, clearance and multi-injury safety. Frontend typecheck, lint, production build and form/player tests are included. Browser QA uses actual components with synthetic data and a mocked API; it does not verify a production clinician assessment or real video availability.

## 14. Remaining limitations and video preparation

This criterion is a conservative product rule, not a clinically validated diagnostic or return-to-sport instrument. Assessments remain self-reported and must come from a clinician/physio; Unlxck does not independently verify them. The fixed starter is unsuitable when the clinician prescribes another resistance/dose, and there is no automatic escalation. The external-weight candidate and later stages remain closed.

[Video preparation](rehab-video-curation.md) and the 41-row CSV reuse the S&C player/curation workflow. Today resolves exact canonical rehab IDs, separately from frozen prescription identity. Blank video URLs are intentional; reviewed clips still need curation/import. Achilles must show floor-level mechanics despite its historical on_step ID; elbow must show empty-hand mechanics. Missing media leaves cues available.

## 15. Exact Achilles comparison

| Concern | Current Main Achilles | This elbow implementation |
| --- | --- | --- |
| Applicability | Explicit midportion site | Reported assessed lateral, subacute/chronic, exact side |
| Permission | Explicit self-reported rehab loading/sport-specific | Same existing permission contract |
| Functional gate | Old worksheet/admin/trusted-review gates are not mandatory after #2797 | Existing suitability evidence must satisfy the retained typed criterion; no consumer questionnaire and no inferred PASS |
| Stage authority | Shared progression engine and exposure responses | Same engine and requirement evaluation |
| Prescription | Floor-level controlled lowering, bodyweight, 1×10 maximum daily | Supported empty-hand wrist extension, 1×10 maximum daily |
| Persistence | Existing episode events | Same event/endpoint/table; one typed payload member |
| Materialisation/freeze | Fixed reviewed option with no verified-clinician pin | Same mechanics, plus current elbow functional/stage revalidation for unstarted work |
| Later stages | DYNAMIC/RETURN closed | DYNAMIC/RETURN closed |

Achilles profile v2/hash `5ff715a474424088cf1549c6b38cc3f1fa51b25b7da118ec1ca767f330d55a1a` and clinical behavior are unchanged. Shared code gains a second option mapping, not a second backend subsystem. Across profiles, rehab blocks gain canonical media identity and presentation metadata only.
