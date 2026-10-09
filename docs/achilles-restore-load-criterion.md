# Achilles RESTORE → LOAD conditional activation

**Only Achilles LOAD is conditionally live.** Profile `achilles_tendonitis`, policy version 2, declares the existing v1 clinical criterion and its four availability inputs. The current progression engine can advance RESTORE → LOAD only when the trusted clinical review, exact selected work and all product safety/history requirements pass. DYNAMIC/RETURN remain disabled. Approval grants no training/contact clearance.

Activation base: Main `2c849735`, after shadow PR #2796 merged. The original shadow base was Main `d0c4dd7b`, after #2765. This uses #2743 assessment capture, #2748 input diagnostics and #2757/#2758/#2765 shared review contracts, trust, persistence, lifecycle and freeze checks. No new table, migration, review channel or rules architecture. Existing shadow approvals bind the previous policy hash and require a fresh clinician decision against policy version 2 before production use.

## Applicability

Only `achilles_tendonitis`, RESTORE → LOAD, one exact current left or right episode, clinician-established **midportion Achilles tendinopathy** appropriate for this option. The clinician must affirm diagnosis applicability and absence of presumed structural frailty. An app label or athlete-entered site is not diagnosis.

Insertional, unknown/mixed/uncertain site and bilateral episodes are outside v1. Suspected rupture/partial tear, traumatic loss of function, marked weakness, incompatible pathology and preventing clinician restriction cannot pass. Unknown safety flags are not negative findings. No elbow or other profile is registered. Acute/atypical presentations require differential assessment; the clinician must judge source/population applicability rather than extrapolating from the app label.

## Evidence and rule classification

Evidence rechecked 9 October 2026. Primary guideline content and the 2025 consensus were inspected; the final 2024 CPG is used, not its September draft. Some publisher full-text URLs returned 403; indexed primary-source passages and the university-hosted consensus PDF supplied the relevant content.

| Source | A — directly source-supported | B — product interpretation |
|---|---|---|
| [Dutch multidisciplinary guideline, 2021](https://pmc.ncbi.nlm.nih.gov/articles/PMC8479731/), treatment module 4, figure 3 | Individualise strengthening and progression using pain during/after exercise and fatigue. Insertional exercise initially uses a flat surface. | Require a clinician to interpret the actual symptoms/function and selected work. No numeric stage cutoff follows from this guideline. |
| [Final midportion CPG, 2024](https://www.orthopt.org/uploads/content_files/files/Achilles_Pain_revision_2024.pdf), CPG2/12 and differential diagnosis | Loading is first-line for midportion disease without presumed structural frailty, with tolerated intensity and at least three weekly sessions. Exercise methods/doses vary; insertional generalisation is limited. | Midportion only; a clinician must judge whether this bounded bodyweight starting task is appropriate. It is not a complete or optimal strengthening programme for every athlete. |
| [Dynamic Health NHS, ankle tendon pain](https://www.dynamichealth.nhs.uk/help-and-advice/foot-or-ankle-pain/ankle-tendon-pain/), Phase 1 B | Both feet rise from the floor, weight transfers to the affected leg, then slow lowering to the floor. Choose repetitions by symptoms, up to ten, once daily. | V1 offers exactly one bout/set of ten, only for someone whose clinician selects ten. This is one supported choice within the source's limit, not a universal starting minimum. Other doses require another reviewed choice/version. The source's other exercises/timed phases are not imported. |
| [Demangeot et al., 2025 Delphi consensus](https://udspace.udel.edu/server/api/core/bitstreams/93b8e496-494a-4728-88c2-4f14e2e9b6f1/content), abstract/discussion, DOI 10.1136/bjsports-2025-110183 | Relevant parameters differ by subtype; intensity, repetition/set count and, for insertional cases, dorsiflexion deserve specific attention. | Do not claim bodyweight-only work is an optimal long-term programme or use one range option across subtypes. The clinician must affirm resistance and dose appropriateness for this starting task. |

B also includes exact episode/side/packet binding, independent clinical confirmation, all-judgment conjunction, conservative stop rules, and refusing external load. These are explicit product protections, not trial-derived progression thresholds.

C — not supported enough for this gate: universal pain ceiling, baseline-change formula, heel-rise count/symmetry cutoff, days since injury, mandatory session count, maximum kg, fixed lowering seconds, automatic eccentric superiority, automatic progression or arbitrary review expiry. None is implemented. A 0–10 symptom scale validates data, not readiness. The daily cadence's `minimum_gap_days=1` represents the existing calendar-day convention, not an invented 24-hour clinical recovery rule.

## Compiled criterion and interpretation

Criterion: `achilles_restore_load_clinical_review_v1`, version **1**. Schema: `AchillesRestoreLoadInterpretationV1`, `schema_version=1`, frozen/extra-forbidden. Clinical scope: `qualified_msk_clinician_achilles_tendinopathy`, independently confirmed qualified MSK clinician/physio with relevant Achilles scope. The admin records and verifies the source; the admin is not the clinical author.

The interpretation names the exact latest assessment event/content hash, supported subtype and materialised selected-prescription hash. Each judgment is `supported`, `not_supported` or `unknown`: diagnosis applicability, no presumed structural frailty, functional adequacy, loading-task appropriateness, during response, delayed response, range, resistance, dose, cadence, no incompatible pathology, no preventing restriction. Omitted judgments default to unknown; booleans/arbitrary PASS fields are rejected by server registry parsing. The request's transport dictionary grants no schema/authority choice.

**PASS** requires shared validity/trust and an approved decision, a current valid bounded selection, schema v1, midportion, every judgment supported, and matching evidence/prescription bindings. The contextual evaluator then reads the actual latest server assessment through the existing four data-sufficiency readers. All inputs must be available; observed site must be midportion, side must be unilateral, safety flags explicitly false, incompatible pathology excluded, a heel-rise count recorded, and observed permitted range/resistance must match floor/bodyweight. No external kg is accepted.

**FAIL** represents explicit not-approved clinical decision or any explicit negative judgment. Unusable/not-tolerated assessment evidence also fails the contextual check when shared safety has not already invalidated the review.

**UNKNOWN** includes deferral, missing/incomplete interpretation, unsupported schema/subtype/side, insufficient observation/provenance/history, assessment/prescription mismatch, unsupported choices, uncertain exclusions and every shared invalidation. A persistent medical/restriction hold makes shared validity invalid/UNKNOWN before clinical approval can be used. Negative flags can therefore be FAIL or invalid/UNKNOWN; neither can advance.

The four existing domains remain availability only: `achilles_site_assessed`, `achilles_heel_rise_assessed`, `achilles_loading_response_assessed`, `achilles_range_load_assessed`. Their PASS does not imply clinical PASS. The legacy `achilles_restore_load_review_v1` and `rehab_decision.achilles_load_review` remain the original non-passing athlete-report diagnostic.

## Exact production prescription

Option: `achilles_midportion_floor_lowering_bodyweight_v1`, version **1**, required by this criterion. Drill: `achilles_tendonitis_eccentric_calf_drops_on_step`. Current display name is **Floor-level controlled Achilles lowering**. Keep the historical ID for compatibility: name/instructions already correct the legacy `on_step` semantics. No drill ID, bank mechanics, metadata review or historical reference changes.

Pinned bank SHA-256: `557056e938e245ccf7bda3621958820389212034a4eb47c3fb4d04d3e58bad2f`.

Exact instructions are the current bank notes: beside stable support on firm level ground, raise both heels, transfer weight to the affected leg and slowly lower only to the floor; no step, deep dorsiflexion, depth/speed/weight increase; stop for worsening during/after symptoms. The option contains the exact text, not an editable instruction field.

| Parameter | Only allowed choice |
|---|---|
| Range | `floor_level`; no below-floor dorsiflexion or clinician-limited free-text variant |
| Resistance | `bodyweight`; no external kg or invented upper bound |
| Dose | `sets=1`, `reps=10`, no duration/hold choice |
| Cadence | `daily`, `minimum_gap_days=1`; no automatic session/course progression |

All mandatory restrictions must remain, with no arbitrary additions: bodyweight only; floor/no step or below-floor dorsiflexion; stable support and controlled lowering; no speed/bouncing/hopping/automatic progression; stop for worsening during/delayed symptoms and seek review; stop/seek assessment for snap, sudden pain or loss of function; follow clinician restrictions and grant no training/contact clearance. Their exact identifiers are `RESTRICTIONS` in the compiled option. Existing selection validation checks range, resistance, dose, cadence, restriction membership, option/version/hash, bank ID/hash and materialised hash.

## Symptom and function judgments

The clinician separately interprets actual during and delayed numeric symptoms/timestamps for the selected prescription. No fixed acceptable pain range or automatic comparison between those two measurements is inferred; neither is a captured pre-task baseline. Stop rules remain conservative. New worsening/setback evidence invalidates approval.

Heel-rise completion/mode/quality/repetitions and assessor usability describe function; they do not prove adequacy for ten controlled unilateral lowerings. The clinician must explicitly affirm selected-task adequacy and the selected dose. A recorded count is required as information; no count or symmetry readiness threshold is imposed. Coach observation may provide some availability evidence, but cannot establish trusted clinical approval; current range/load availability still requires a clinician-attributed assessment.

## Packet, provenance and invalidation

The existing authenticated admin independent-confirmation channel is the only trust source. Exact clinician statement, independent author/qualification/scope, confirmation and private byte-bound receipt are preserved. Athlete-reported clinician claims, self-report alone and unconfirmed reviews cannot pass. No automated regulator lookup is claimed.

The prepared packet exposes only this authorised injury/episode: current injury safety context, Achilles assessment values/site/function/loading response/range/resistance/assessor/concerns, full relevant observations, exposures, setbacks, clearance/restrictions, complete-history/current-episode status, policy version/hash, criterion/schema, fixed options/option hashes and current bank hashes. Clinical review/lifecycle source rows are excluded from the evidence packet. The packet revision now also binds policy, criterion/schema, options and bank, so a change between preparation and recording requires a new decision. No unrelated athlete episode/profile data is added.

Shared replay pins exact athlete/injury/episode/side, current packet and safety revision, criterion/schema/policy/option/selection versions, bank hash and materialised prescription hash. New assessment, later setback, medical/restriction hold, changed clearance/context, incomplete history, replacement/closure, wrong side/version, changed option/bank/policy/schema, revocation/supersession or reasoned expiry prevents reuse. There is no arbitrary age expiry. Clinically material evaluator changes require a criterion version bump. Packet/schema binding conservatively invalidates changed payload definitions; no implicit backward compatibility.

The shared registry's optional contextual evaluator is a narrow extension to the existing compiled definition. It consumes complete server-owned assessment event bytes after shared trust/validity and typed judgments succeed, using the existing protocol readers. It is not another persistence or review architecture.

## Today, acceptance and continuation

Production capture accepts a compiled exact profile/transition binding before a pathway declaration only when the target stage is disabled **and** the existing transition is non-promotable. A live target requires its exact declared clinical checkpoint. This exception cannot create a criterion from client JSON.

Today hydrates the existing private review channel and runs the current engine. An exact LOAD prescription must also be eligible for the current injury severity, side and equipment. Stable support must be selected explicitly in the intake; gym presets do not imply it. Missing equipment prevents LOAD promotion. Without trusted approval Today remains conservative. Unrelated injury restrictions and clinician clearance retain their existing precedence.

The selected dose, range, resistance, cadence, instructions and seven restrictions are materialised into the actual Today block with the shared frozen review pin and selection sidecar. Camp phase, readiness adjustments and alternate-drill scheduling cannot substitute or escalate this work. Existing daily slot limits, same-day allocation checks and minimum calendar-day gap apply. Acceptance and continuation replay current review validity and match the executable block against the exact selection, bank snapshot and policy restrictions.

Unstarted saved work is held after invalidation. Started work remains immutable and unsafe continuation is rejected; stopping remains available. Completed snapshots and exposure history remain historical. Unexpected hydration, evaluator or frozen-work failures fail closed and log the failure category without clinical payloads or exception messages; expected missing/malformed authority is logged separately.

All other 63 profile hashes, bank identities/mechanics, metadata review ledger and historical duplicate archive are unchanged. Current inventory is 104 LIVE identities and 56 dormant advanced candidates: one exact Achilles LOAD identity moved into production. Dated #2742 planning and archive fingerprints use an exact approved activation projection, while current audits and runtime use the actual catalog.

The isolated shadow fixture still proves that clinical PASS cannot open a disabled target. Production now declares the clinical checkpoint explicitly. Remaining evidence limits are unchanged: no universal stage threshold or optimal-dose proof, automatic external loading, insertional progression or sport/contact clearance. V1 depends on the exact qualified clinical judgment; DYNAMIC/RETURN stay closed.

## Verification

`tests/test_achilles_load_activation.py` exercises registration → structured assessment → trusted capture → LOAD → actual Today → acceptance → completion → exact exposure. It covers unapproved/inapplicable cases, missing support, frozen invalidation/tampering, completed history and safe failure logging. `tests/test_achilles_shadow_pilot.py` retains all-judgment, observation, attribution, lifecycle, version/hash/packet, clearance and isolated closed-target checks. The existing PostgreSQL capture suite includes the real Achilles criterion/option through the service-only writer and revocation, alongside frozen acceptance/race tests. It requires the disposable localhost database supplied by existing CI. Local runs without `REHAB_TEST_DATABASE_URL` skip it; no live database is touched.
