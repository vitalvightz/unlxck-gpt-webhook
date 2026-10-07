# Clinical progression review: architecture decision

Investigation date: 7 October 2026. Base: Main `7f8494d12397eea573d2168020cc89f0cb9313d3`, fetched after [#2748](https://github.com/vitalvightz/unlxck-gpt-webhook/pull/2748) merged. [#2743](https://github.com/vitalvightz/unlxck-gpt-webhook/pull/2743) introduced the shared assessment boundary; #2748 added a deliberately non-passing Achilles review and athlete reporting UI.

**Recommendation: C — add shared clinical progression review infrastructure as an optional clinical criterion, using existing episode-event storage.** Keep training/contact clearance separate. Start with independently confirmed clinician decisions recorded by an authenticated admin, with bounded prescription selection. A clinician portal and a new clinical-review table are not justified now.

This is a design, not an implemented contract. All proposed names below are illustrative. This PR changes documentation only. LOAD/DYNAMIC/RETURN remain unavailable. It adds no migration, account, endpoint, bank change, profile hash change, clearance behavior or elbow implementation.

## 1. What existing infrastructure already solves

The repository has reusable infrastructure, but its names do not establish clinical authority.

| Inspected implementation | Existing capability to reuse |
|---|---|
| [`rehab_assessment.py`](../api/contracts/rehab_assessment.py): `RehabProgressionAssessment`, `AssessmentProtocol`, `AssessmentContext`, `read_assessment_input` | Typed/versioned payload dispatch; exact athlete/injury/episode/side attribution; applicability; aware observation times; latest whole assessment; complete-history and setback checks. Availability is explicitly not clinical promotion. |
| [`achilles_progression.py`](../api/contracts/achilles_progression.py): `AchillesProgressionInput`, `read_achilles_input` | Actual site, functional observations, symptom observations and range/load reports, with unknowns and structural consistency validation. |
| [`injury_episode_service.py`](../api/services/injury_episode_service.py): `record_episode_observation`, `apply_episode_observations` | Owned episode writes, stable report identity, hydration, latest clearance after setbacks, persistent assessment concerns. |
| [`store.py`](../api/store.py): `list_injury_episode_events`, `record_injury_episode_event` | Exact-episode keyset history through an empty page, and service-only RPC access. |
| [`episode history migration`](../supabase/migrations/20260930173118_injury_episode_prescription_history.sql), [`assessment migration`](../supabase/migrations/20261005215205_add_achilles_progression_observations.sql) | JSON event payloads, episode history index, owner-select RLS, restricted writer, athlete lock before injury lock, context recheck, equal-payload retry versus conflicting replay. Report observations are append-only through the API; injury-checkin audit rows have their own trigger/upsert behavior. |
| [`clinician_clearance.py`](../api/contracts/clinician_clearance.py) | Three scope ceilings: rehab only, training without contact, training with contact. Lowest reported scope wins across contributing active injuries; baseline relaxation is per eligible episode. Missing clearance is not a universal clearance requirement and does not erase other injury restrictions. |
| [`rehab_progression.py`](../api/contracts/rehab_progression.py): `evaluate_transition`, `resolve_reviewed_progression` | One authoritative higher-stage engine; consecutive transitions; separate clinical, product-safety and data-sufficiency requirements; target activation check. |
| [`injury_policy.py`](../api/contracts/injury_policy.py): `resolve_injury_policy`, `reconcile_session_prescription` | Medical review, exact profile resolution, bank integrity, conservative combined restrictions, loading holds, prescription selection, frozen-content safety overlays. |
| [`rehab_clinical.py`](../fightcamp/rehab_clinical.py), [`rehab_pathways.py`](../fightcamp/rehab_pathways.py), [`rehab_pathways.json`](../data/rehab_pathways.json) | Seven families compose regional profiles; reviewed prescription identities/hashes, sources, dose/cadence, stage bundles and activation validation. |
| [`rehab_schedule.py`](../api/contracts/rehab_schedule.py), [`rehab_completion.py`](../api/contracts/rehab_completion.py) | Daily allocation/cadence, exact prescription/exposure attribution, explicit dose completion, immutable performed history. Ordinary session completion does not manufacture a measured dose. |
| [`today_service.py`](../api/services/today_service.py): `_with_injury_policy`, `_build_today_command_view`; [`Today injury manager`](../web/components/today/today-injury-manager.tsx), [`Achilles form`](../web/components/today/achilles-assessment-form.tsx) | Current assessments, clearance status, injury safety and prescriptions reach Today through backend decisions. The form reports an assessment already performed; it does not prescribe testing or verify its assessor. |
| [`auth.py`](../api/auth.py), [`dependencies.py`](../api/dependencies.py), [`compliance_guards.py`](../api/compliance_guards.py), [`Today routes`](../api/routes/today.py) | Verified Supabase user, approved profile, effective admin check, ownership and explicit health-feature access gate on athlete observations. |

Read-only composition on this base confirms **64 profiles, seven families, 103 prescription identities, only CALM/RESTORE live, and zero promotable higher-stage transitions**. `CAPTURED_FUNCTIONAL_CHECKPOINTS` is empty. `policy_review_hash` explicitly measures content integrity, not clinician sign-off. These distinctions must survive the next implementation.

## 2. What it does not solve

Current assessment and clearance writes stamp `source: athlete_reported` and `externally_verified: false` on the server. Selecting `clinician_physio` is reported attribution. Neither contract identifies/authenticates an external clinician, records independent confirmation, captures their judgment of selected-task adequacy, or approves an actionable individual prescription.

[`achilles_restore_load.py`](../api/contracts/achilles_restore_load.py) returns only FAIL/UNKNOWN. Its four remaining blockers concern provenance, functional adequacy, acceptable symptoms for the task, and prescription. There is no production clinical PASS declaration to switch on.

Some evidence also remains insufficiently specified: `loading_task: clinician_selected` does not identify the actual movement/dose, `clinician_limited` does not state a usable range limit, and the capture lacks a complete selected-prescription symptom trajectory. A verified identity alone cannot repair those gaps.

The existing `admin_reviews` table is an operations queue: athlete/injury flag, reason, pending/acknowledged/resolved, resolution note and resolver. It is mutable and lacks episode/side/criterion/prescription binding. Resolving that queue is not a clinical decision. Its service-role access is reusable for operations, not an approval source.

Only athlete/admin roles are live; coach/gym-owner roles are reserved, and there is no clinician role. The private `feedback-screenshots` bucket accepts PNG/JPEG/WebP, is limited to feedback, and is not clinical-document storage. Neither an upload workflow nor clinical document retention/access controls are already solved.

## 3. Is trusted review genuinely required for Achilles LOAD?

**For the current candidate and missing interpretation, yes as a product safety choice; not as a universal guideline requirement for every observation or every future transition.** There is no reviewed deterministic rule that turns the current reports into applicability, functional adequacy and a dose for that candidate. Requiring a traceable qualified clinical decision is defensible until such a rule is specified and validated. Authentication is a product trust policy; the clinical sources do not prescribe an app identity system.

Clinical sources inspected:

- [Dutch multidisciplinary guideline, 2021](https://bjsm.bmj.com/content/55/20/1125), [open full text](https://pmc.ncbi.nlm.nih.gov/articles/PMC8479731/), diagnosis module 2 and treatment module 4/figure 3: diagnosis combines clinical findings; imaging is not mandatory when diagnostic criteria fit. Strengthening is individualised, with symptoms during/after exercise and fatigue informing progression. Initial insertional work uses a flat surface.
- [Final 2024 midportion CPG](https://www.orthopt.org/uploads/content_files/files/Achilles_Pain_revision_2024.pdf), CPG2–4 and CPG10–13, DOI `10.2519/jospt.2024.0302`: loading is first-line without presumed structural frailty; progression intensity reflects pain tolerance and/or functional capacity. Midportion recommendations may not generalise to insertional disease. This is the final publication, not the September draft.
- [Kent Community Health NHS insertional guidance](https://www.kentcht.nhs.uk/leaflet/achilles-insertional-tendinopathy/), loading section, 2 December 2024: supported bilateral flat-surface exercise precedes podiatrist-advised single-leg progression.

**Product inference:** these principles do not establish an Unlxck RESTORE→LOAD cutoff, universal rep count, universal pain ceiling, compulsory scan, fixed resistance, or fixed approval expiry. The current dormant candidate lowers on the affected leg; its prescription cannot be inferred from the existence of a floor-level bank drill. Better capture is necessary but insufficient without a reviewed interpretation and prescription.

Use proportionate verification of the person whose clinical judgment the product relies on. Do not demand a verified clinician to report pain or count repetitions. Do not declare all loading medically gated forever. A later independently reviewed automated criterion could replace the human requirement for a defined population/task without changing transport or storage.

## 4. Achilles domains: observation, interpretation and authority

The following is a proposed allocation of product authority, not a new clinical threshold or a change to current readers.

| Domain | Observation can come from | Automatic now / after better capture | Clinical judgment retained for this candidate |
|---|---|---|---|
| During/delayed symptoms | Athlete; observed task and times attached | Validate scale/time/trajectory completeness; retain worse/unknown holds. A numerical acceptable-response rule needs separate evidence/review before automation. | Whether that response is acceptable for the identified movement, range and dose. |
| Heel-rise completion and repetitions | Athlete or coach/clinician observation, explicitly labelled | Validate completed test, mode, count and provenance; do not interpret a count as readiness. | Whether observed capacity supports the proposed prescription. |
| Movement quality | Coach/clinician observation; athlete label remains a report | Consistency checks; a standardised protocol may improve repeatability. No approved universal quality cutoff exists here. | Selected-task adequacy, especially ambiguous results; observation is not diagnosis. |
| Known site | Athlete location report or clinician assessment | Store explicit midportion/insertional/unknown and route the correct branch. | Diagnosis/applicability when ambiguous; reported site alone cannot exclude another presentation. |
| Structural pathology exclusion | Athlete may report concerns or advice | Any concern can close/hold safely; unknown is not exclusion. | Qualified clinical applicability assessment. No requirement to scan every athlete. |
| Permitted range | Athlete can report actual movement/advice | Enforce an approved template's fixed limits. Better capture must make any restriction executable. | Individual restriction and whether the selected option fits it. |
| Resistance / load selection | Athlete can record actual equipment/kg | Validate units, allowed mode and bounds; later reduce within an explicitly reviewed rule. | Initial individual option and load appropriate to capacity. Bodyweight does not specify support/weight transfer. |
| Dose and frequency | Report actual work separately from prescribed work | Render/schedule the approved selection; reductions only where the option expressly allows them. | Choose the individual dose/cadence within reviewed options; no automatic increase from symptom improvement. |

Current `read_achilles_input` demands coach/clinician attribution for heel-rise usability and clinician attribution for range/load availability. Those are conservative capture policies, not proof that the raw measurements inherently require external verification. A future clinical-review evaluator should distinguish direct clinician assessment from athlete evidence references; it must not upgrade an athlete event's provenance or blindly require every historical availability flag if a reviewed protocol legitimately supplies the missing evidence.

### Human review should be an optional criterion

| Criterion class | Architecture consequence |
|---|---|
| Safely automatic product invariants | Ownership, version match, complete history, concern/setback/revocation checks, dose bounds and no out-of-bank prescription. These do not establish clinical readiness. |
| Automatic after better measurement **and a reviewed clinical rule** | Defined task/dose symptom trajectory or standardised functional measure for an appropriate population. Capture alone cannot justify a cutoff. |
| Human reviewed | Ambiguous applicability, selected-task adequacy and individual prescription decisions for which an approved deterministic rule is absent. Some may later become automatic; context-dependent judgment may remain. |
| Always medically gated **within a defined pathway's safety policy** | Suspected rupture/structural injury, traumatic loss of function, severe impairment or unresolved medical restriction. The app must not infer their resolution from a low pain score. A gate does not mean permanently closed after appropriate assessment. |

Do not make human review the central stage mechanism. The existing compiled criterion evaluators can consume human decisions when a profile requires them and measured evidence when a different reviewed criterion supports automation.

## 5. Keep clearance separate

| Concept | Question answered | Effect |
|---|---|---|
| Clinician clearance | What broad rehab/training/contact scope has been reported? | Independent ceiling and eligible baseline relaxation, under current semantics. |
| Clinical progression review | Is this presentation/function/response adequate for this specified transition and proposed work? | Evidence for one clinical requirement; never a stage write. |
| Individual prescription | Exactly what reviewed movement, range, resistance, dose, frequency and restrictions apply? | Materialised bounded work, subject to policy, scheduler and combined safety gates. |

Reuse clearance's ownership, episode lifecycle, history ordering, lock discipline, idempotency, safety projection and freshness pattern. Do not add `restore_to_load` as a fourth clearance scope: clearance has a total scope hierarchy; progression and prescriptions vary by criterion, side, task and version. Combining them would permit nonsensical ranking and replacement.

A review may reference the clearance event considered by the reviewer, where one exists, but it neither creates clearance nor requires `training` clearance for otherwise permitted rehab. A broader later clearance cannot revive a stale review. A current rehab-only ceiling can coexist with approved rehab loading, subject to existing medical restrictions. Training without contact does not approve Achilles LOAD, and LOAD does not approve training/contact.

## 6. The individual prescription problem

`ClinicalPrescription` currently pins a drill hash, stage, instructions, optional `ClinicalDose` (sets/reps/time), cadence/gap, severities, stop rules and sources. Camp/readiness doses can only reduce the baseline. It has no individual load/range selection record. The live Achilles CALM/RESTORE prescriptions have null dose; completing them is not a quantitative LOAD test.

The dormant ID `achilles_tendonitis_eccentric_calf_drops_on_step` now names **Floor-level controlled Achilles lowering**: supported bilateral rise, transfer to the affected leg, unilateral lowering to floor. Its dose is null; its notes prohibit added weight, step depth and speed progression. There is no live LOAD prescription. The unreviewed `_2` legacy step variant is not a reviewed alternative. The bank's categorical `load: moderate` does not encode an individual resistance.

| Representation | Assessment |
|---|---|
| A: predefined profile prescription | Smallest if an exact option/dose is clinically defensible for the intended population. Not currently established for Achilles; a universal dose would hide the missing judgment. |
| B: clinician chooses reviewed options | Recommended first executable model. Each option has reviewed mechanics, indication, dose choices and restrictions. Selection records an individual decision. |
| C: clinician edits bounded parameters | Add only parameters with explicit reviewed ranges, units, compatibility and validation. Useful later; an empty min/max chosen by engineering is not a clinical bound. |
| D: athlete-derived prescription | Suitable only with separately reviewed derivation rules and verified inputs where needed. Current symptom/count reports cannot derive this LOAD prescription. |
| E: arbitrary external/free-text plan | Keep as an external care reference or note; never executable by this engine. It bypasses bank and workload safety. |

Start with B, supported by reviewed templates; add narrow C where evidence and clinical review justify it. Do not build a general prescription language.

## 7. Trust model: beta now, upgrade later

Trust means the server has a defensible chain from the clinical author to this exact decision, scope and prescription. It does not prove diagnostic correctness. Separate **clinical author**, **provenance verifier**, and **authenticated recorder**. An admin may check origin and transcribe; admin status alone does not qualify them to judge clinical adequacy or invent a dose.

| Model | Security / impersonation | Traceability | Operations / UX | Scale / beta suitability / upgrade |
|---|---|---|---|---|
| A: athlete reports clinician advice | Current owned report; easily misattributed and self-asserted | Athlete assertion only | Lowest burden/friction | Keep as evidence now; insufficient for required trusted judgment. Later corroborate without rewriting it. |
| B: document + manual verification | Upload is not verification; independently confirm author, date, exact patient/episode/side and statement | Source document plus verifier/confirmation record | More athlete/admin work; unclear documents need clarification | Practical small pilot if access/retention controls exist; upgrade to structured confirmation. Not supported as a clinical upload today. |
| C: scoped clinician code/link | A bearer link alone can be forwarded to the athlete; link must reach independently checked provider contact and require a separate challenge | Structured author decision, delivery/challenge and scope audit | Less transcription; invite/contact checking remains | Good next trust channel if volume justifies it; same review envelope. Link delivery alone is not professional identity verification. |
| D: clinician account/workflow | Authentication proves account control; qualification, scope, onboarding and revocation still needed | Good repeat-author audit | Largest setup and UI burden | Later repeated-provider use; unnecessary for first beta. Existing roles do not supply this. |
| E: staged hybrid | Manual independently confirmed clinical decision now; checked-contact structured submission later | Same decision/provenance contract across channels | Low platform complexity, bounded pilot throughput | Recommended. Measure review volume and turnaround before building accounts. |
| Verified external provider data | Must validate provider connection, patient match, author and consent; imported observations are not automatically decisions | Potentially strong structured origin | High integration burden and incomplete clinical content | Later if an actual partner provides usable review/prescription content. No current integration found. |
| Signed structured assessment | Signature proves control of a key, not qualifications, patient match or clinical scope | Can protect bytes, still needs identity/lifecycle | Additional key management and failure modes | Not needed now. Authenticated server submission plus immutable audit is sufficient for this design; no signature platform proposed. |
| Existing manual admin record | Existing admin auth can protect recording; current queue resolution cannot establish clinical authority | Add explicit clinical author and independently checked source per review | Smallest backend-operated pilot | Use admin as recorder/verifier through a new restricted writer, not `admin_reviews.resolution_notes` as approval. |

**Now:** retain ordinary athlete reporting and design a small manually operated, independently confirmed structured review pilot. Before acceptance, use contact obtained independently of the athlete's claim (for example an established provider relationship or checked professional/provider listing), confirm the author is appropriately qualified for the stated scope, and confirm their exact statement about this athlete/episode/side/task. Record method, verifier, confirmation time and minimal evidence. A generic “fit to train” letter fails completeness. If there is no clinician available, review stays pending/unknown; an admin cannot substitute clinical judgment.

The minimum channel need not upload documents: an independently confirmed structured statement can be recorded with an auditable confirmation reference and statement snapshot. If evidence cannot be retained/accessed under an approved process, do not label it verified. Do not route documents through feedback screenshots, emails embedded in public payloads, or application logs. Document upload is an optional later project with separate private storage/access/retention work.

**Later:** checked-contact scoped link plus separate confirmation challenge, with short token lifetime for access security, single-use submission and revocation. Token expiry is not a medical approval expiry. Introduce accounts only for recurring reviewers needing persistent access; do not add a clinician role to the ordinary athlete signup flow or complex organisation permissions.

## 8. Storage decision

| Candidate | Benefit | Cost / reason to reject or defer |
|---|---|---|
| Current clearance report payload | Existing persistence | Wrong semantics and explicitly athlete-reported. Do not overload it. |
| `injury_episode_events`, one shared review event type | Exact-episode history, owner-read boundary, indexed retrieval, append-only observation writer and transaction locks already exist | Needs a future shared constraint/RPC extension, lifecycle reduction, trusted actor boundary and freshness integration. Existing RPC rejects this event today. |
| Dedicated shared clinical-review table | Easier structured cross-athlete queues, reviewer foreign keys and independent access/retention | Duplicates lifecycle/locking/read paths without current requirement; no demonstrated need for it now. Reconsider for measured query volume or different confidentiality requirements. |
| `admin_reviews` | Existing operational queue | Mutable notes/status, no exact clinical binding/versioning; use at most as a work item referencing a review, never truth. No new queue required initially. |
| Frozen prescriptions / exposures | Exact work history | Output/measurement records, not author decisions. They should reference approval, not store its source of truth. |

Recommend **one shared event type**, conceptually `clinical_progression_review`, with a strict discriminated action of `record`, `supersede` or `revoke`. All profiles use the same lifecycle. Replacement/revocation appends a new event linked to the previous review; it does not edit it. A later storage projection can improve querying without changing the logical contract or stage authority.

Important privacy boundary: `injury_episode_events` grants the athlete direct owner SELECT over the whole payload. Store only athlete-disclosable clinical decision/provenance there. No token hashes, contact secrets, private verification correspondence or third-party patient material. An opaque evidence reference must resolve only through an independently authorised private evidence service/process; it must not be a public URL. If the pilot requires confidential verifier-only content that cannot stay outside this payload with a durable controlled reference, revisit a shared private evidence store before accepting reviews. This conditional evidence need does not justify a new clinical-approval table now.

## 9. Minimum conceptual review object

Keep existing evidence events separate. One immutable review event can contain **distinct interpretation, clinical decision and prescription selection sections**, atomically bound to the evidence packet. Three additional tables would add joins and partial-write hazards without improving this first workflow.

| Section | Essential content |
|---|---|
| Envelope / binding | Server event/review ID; schema version; athlete, injury, episode, known side; exact profile; from/to stage and criterion ID/version. No family-level or body-region-only approval. |
| Reviewed packet | Assessment event IDs and protocol versions; exact selected task/observation details or references; complete relevant history through a server cutoff; injury/context and packet hashes. Cross-episode or opposite-side references rejected. |
| Interpretation | Typed profile-specific applicability/subtype, function adequacy for proposed work, response interpretation and rationale/reason codes. Unknown/deferred supported. The common envelope does not impose one universal clinical form. |
| Decision | `approve`, `reject` or `defer` for this clinical requirement and specified work. The server computes criterion PASS/FAIL/UNKNOWN; authors do not submit an engine stage. |
| Prescription selection | Reviewed option/template ID/version/hash; pinned drill/hash; concrete permitted parameters, dose, frequency/gap, stop rules and restrictions; immutable selection hash/version. Required for an approval whose criterion needs individual work. |
| Provenance | Qualified clinical author identifier/display identity and scope; confirmation method/reference/time; server-derived authenticated recorder/verifier identity; source statement/evidence reference and integrity digest where available. Origin trust is a server outcome, not a client boolean. |
| Time / lifecycle | Clinical assessment/review time, server received/verified time; optional justified `valid_until`; prior review ID for supersede/revoke; reason and effective time. Author history remains readable after invalidation. |
| Context references | Clearance/restriction event considered, if present; episode safety revision. Absence of clearance is explicit, not fabricated. |

Essential validation rejects missing author provenance, undefined work, unsupported criterion/template/version, malformed references and out-of-bounds parameters. A denial/defer can legitimately omit a prescription. `revoke` has a smaller typed payload referencing a prior record; it cannot carry an approval or a replacement dose.

Avoid duplicated full athlete profile data, organisations, clinician scheduling, a global medical identity registry, generic scoring and general condition schemas. For the manual pilot, a per-review confirmed author reference suffices; no clinician account/table is required. Persist the clinically relevant source statement/interpretation, not merely a boolean saying someone checked it.

## 10. Engine integration

Reuse `functional_checkpoint` with a compiled clinical evaluator registered by criterion ID/version. Add a shared review-context validator/lifecycle reader behind that evaluator, not a universal clinical algorithm. A new `clinical_review` requirement kind is unnecessary unless implementation proves the existing checkpoint contract cannot carry an auditable result.

The evaluator checks identity, trusted provenance, evidence binding, lifecycle, current safety, required interpretation and bounded prescription. A valid clinical approval makes **one clinical requirement** PASS. It cannot remove a product-safety or data-sufficiency requirement. `evaluate_transition` still evaluates all requirements; `resolve_reviewed_progression` still advances one rung only when the target is live and the transition is met.

`resolve_injury_policy` must then materialise the exact approved selection instead of choosing a different higher-priority option. Its bank checks, medical precedence, equipment checks, severity bounds, restrictions, scheduler and allocation checks remain authoritative. Approval can exist while Today still reports a block from another requirement or incompatible equipment.

Keep #2748's v1 review as historical non-passing behavior. A future clinically complete evaluator should use a new criterion version/identity; do not turn v1's literal false fields into client-editable flags or reinterpret old approvals. The production catalog would declare that new criterion only in a separately reviewed activation change.

All consumers need the same authoritative resolved policy result. Inspect generation before activation: [`rehab_stage_snapshot.py`](../api/services/rehab_stage_snapshot.py) currently annotates generation with the baseline stage resolver and exposures, not the full new review/evaluation context. That annotation is not already proof of future LOAD eligibility. Do not create an intake `approved_stage` field; wire shared resolution where needed and test Today/generation consistency before opening the stage.

## 11. Invalidation, restrictions and frozen prescriptions

These are proposed conservative product rules. They do not introduce an arbitrary medical age cutoff.

| Change after a review | Effective behavior |
|---|---|
| Worse check-in, worse during/delayed exposure or stopped work indicating setback | Approval becomes unusable for promotion/current loading. Existing setback logic wins. Later improvement can restore baseline behavior; it cannot revive the previous approval. New assessment/review and any sourced setback-resolution rule are required. |
| Medical concern/hold or new restriction | Hold dominates, even if a review says approve. Review submission is not a hold-release operation. |
| Clearance update | Re-evaluate the independent ceiling; stricter scope blocks affected work immediately. Any clearance change invalidates the packet binding proposed for the pilot and requires reconfirmation of approval; permissive clearance is not review renewal. |
| New relevant assessment, including incomplete/unknown | The reviewed packet is no longer current; return pending/unknown. Do not fall back to an older approved packet. Pilot rule is deliberately conservative; a later clinically reviewed policy may define which nonmaterial observations preserve approval. |
| Injury edit, profile/subtype change, new episode or opposite side | Exact binding fails. No inheritance or region-only matching. A resolved/closed episode cannot supply current approval. |
| Other more restrictive injury | Combined medical/loading/contact/equipment/workload restrictions win. One episode's approval cannot clear another. |
| Explicit supersede/revoke or later rejection | Old approval is unusable. Latest valid lifecycle decision wins; invalid newest record/incomplete history cannot revive an older approval. No expiry of a rejection/restriction silently returns to PASS. |
| Reviewer trust withdrawn or original source found fraudulent | Authorised revocation records identify affected reviews; current evaluation rejects them. Historical replay can still explain what was trusted at the time. |
| Criterion/profile/template/drill changed | Version/hash mismatch blocks use for new work. See section 12; never migrate approval silently. |
| Health consent withdrawn | No new health-dependent review processing/submission/activation; target-athlete consent gate applies even to admin recording. Existing historical reads follow current policy. |

**Restriction release is distinct from approval revocation.** Revoking a positive review removes permission. Revoking/correcting a restrictive clinical statement requires explicit authorised replacement describing what is released and why; removing an approval must not remove an associated medical concern. #2743 concerns are persistent across reassuring snapshots. Current code has no assessment-hold release path. If needed, design and review a separate shared, scoped hold-resolution action; do not smuggle it into `approve` or bypass it in the evaluator.

For unstarted work, a new review/supersede/revoke/restriction or relevant assessment must invalidate the outstanding server prescription revision under the same athlete lock used at acceptance. For started/completed work, retain the original content and references; apply live safety overlays to stop further unsafe work. Never rewrite performed work, regenerate its dose, or reclassify its exposure.

Current freeze reconciliation already checks episode, selected membership, policy hash and loading/medical/clearance holds. It does **not** check the proposed individual selection hash or review lifecycle. Add these explicit future dependencies. If an approved dose changes while the same drill ID survives, membership alone cannot protect frozen work. An unsafe/stale started prescription must be held, not replaced in place.

## 12. Versioning and deterministic replay

Minimum independent pins:

- Review envelope schema version and clinical criterion ID/version (including evaluator semantics).
- Referenced assessment kind/protocol version and immutable evidence event IDs/content binding.
- Profile ID/version and existing content hash; criterion and selection must also be pinned independently because closed/non-promotable transition diagnostics are excluded from `policy_review_hash` today.
- Reviewed template/option version/hash and exact bank drill content hash.
- Concrete individual prescription selection version/hash, including mechanics/parameters/dose/cadence/restrictions.
- Author/provenance confirmation, clinical review time and server recorded time; lifecycle events and relevant injury/clearance/safety packet revision.

Drills currently use identity plus content hash; do not invent an existing numeric drill version. A reviewed template version is new content metadata, not a substitute for the bank hash. A selection hash detects altered parameters; it does not authenticate their clinical author.

Evaluation receives an aware explicit `as_of` plus the injury/safety/config state for that replay. Consider only evidence/review/verification/lifecycle events recorded by that cutoff, with clinical times no later than recording. Old decisions remain attached to the exact versions they reviewed. Updated logic produces a new criterion version; old approval is unknown for it until re-reviewed, even if the new text seems equivalent. Retain versioned evaluator/config artifacts for historical replay.

Freshness primarily depends on invalidating events and packet binding. Referenced readiness observations and the clinical review must follow the last invalidating setback; a later admin transcription/verification timestamp cannot make an older clinical assessment fresh. Support a clinician-specified or evidence-justified expiry with a recorded reason, but do not invent 48 hours/7 days globally. “No fixed expiry” is not “valid forever”: new observations, setbacks, restrictions and version changes can invalidate immediately. Review-link lifetime concerns access security, not clinical validity.

## 13. Bank and prescription safety boundaries

Bank presence is inventory, not permission. [`rehab_metadata_review.json`](../data/rehab_metadata_review.json), [`review library`](../tools/rehab_metadata_review_lib.py), [`advanced candidate decisions`](../tools/rehab_advanced_candidate_decisions.json) and [`rehab_bank.json`](../data/rehab_bank.json) distinguish reviewed/stale/unknown/dormant material. Live policy/hash validation is a further boundary. A bank classification or `status: active` alone is not clinician approval.

| Parameter | Product authority | Individual reviewer authority |
|---|---|---|
| Movement identity, bilateral/unilateral mode | Allowlist reviewed exact options; an option cannot silently alter the bank movement | Choose an option within approved indication. Current unilateral candidate cannot be converted to bilateral by a checkbox. |
| Range | Enforce option mechanics and typed actionable limits | Choose an expressly reviewed limited range/variant; cannot introduce below-floor depth into the current candidate. |
| Resistance mode/amount | Enforce reviewed modes, units and bounds; reject missing kg where required | Select within those bounds; cannot add weight to a bodyweight-only option. |
| Sets/reps/time and frequency/gap | Enforce reviewed choices/bounds, schedule and daily ceilings | Select a justified dose/cadence; cannot omit essential quantity or exceed reviewed bounds. |
| Stop rules/restrictions | Preserve mandatory rules and apply stricter combined gates | Add supported typed restrictions; cannot delete product safety rules or clear unrelated injuries. |
| Camp/readiness adaptations | Reduce only through explicitly reviewed rules, record resulting work | No authority to raise load because of camp phase or whole-athlete readiness. |
| Out-of-bank movement or arbitrary plan | Reject as executable work; preserve an external-care note if appropriate | Request content review. New movement/variant requires bank/template review and versioning first. |

Bounds must be clinically reviewed before use; this report supplies no numerical range, resistance or dose. Even a seemingly smaller range/dose must be supported by the option's rules rather than assumed equivalent. A changed prescription is a new immutable selection plus review/supersession. Previous bank hash and selected work remain in frozen history.

## 14. Achilles future flow, with existing code participation

| Step | Existing participant | Small future addition / boundary |
|---|---|---|
| 1. Record assessment | Today Achilles form → `POST /api/today/injury-episode-observation` → `record_episode_observation` | Athlete evidence remains athlete-reported. No clinical trust inferred. |
| 2. Match current episode/side | `assessment_payload`, RPC context checks, `AssessmentContext` | Reviewer packet binds this exact context and current server cutoff. |
| 3. Reviewer sees relevant inputs | `list_injury_episode_events`, exact exposure history, `apply_episode_observations`, existing assessment readers | Minimal packet includes actual task/dose/range, observations, unknowns, setbacks, current restrictions and other limiting injuries. Fill missing task details with a reviewed typed protocol extension or direct clinical observation; do not fabricate them. |
| 4. Assess applicability | #2748's site/medical/exclusion diagnostics | Qualified author confirms applicable subtype/presentation. Unknown/structural concern remains blocked. |
| 5. Judge function/response | `AchillesProgressionInput` observations and v1 missing-interpretation reasons | New typed selected-task interpretation with rationale; no generic numerical cutoff. |
| 6. Choose reviewed LOAD work | Bank candidate review; `ClinicalPrescription` concepts | First create a clinically reviewed exact option/dose and permitted parameters. If no option fits, defer; no bilateral/weighted substitution without content review. |
| 7. Record review | Existing episode ownership/history/RPC pattern | Restricted writer creates shared event with server provenance, evidence binding, selection and idempotency. Admin records confirmed clinician statement, not their own invented clinical judgment. |
| 8. Evaluate transition | `evaluate_transition`, `resolve_reviewed_progression`, `resolve_injury_policy` | New versioned evaluator consumes effective review and satisfies only its clinical requirement. All other requirements and current holds still apply. |
| 9. LOAD becomes available | Policy activation validation → `schedule_rehab` → `reconcile_session_prescription` → Today | Only after a separately authorised clinical/content activation change. Exact selected prescription is pinned through acceptance, completion and exposure provenance. Missing equipment/other injuries can still hold it. |
| 10. Later setback | Injury check-in or during/delayed response, hydration and setback calculation | Same safety path invalidates review use and outstanding prescription revision. |
| 11. Prior approval inactive | Episode/setback context and frozen hold checks | Derived inactive reason plus retained audit record; explicit revoke/supersede where applicable. Improvement never resurrects old approval. |

This flow cannot be completed by the current code merely by adding a trusted record. A usable option, interpretation, evaluator, freshness integration and deliberate stage activation are separate prerequisites.

## 15. Lateral elbow reuse test — thought experiment only

The current generic `elbow_tendonitis` identity must not imply lateral extensor tendinopathy. The reviewed dormant extensor-lowering candidate and its individual dumbbell/load gap are identified in `rehab_advanced_candidate_decisions.json`; this report defines no elbow criterion or treatment thresholds.

| Profile-specific content needed | Shared infrastructure reused |
|---|---|
| Typed subtype/applicability, relevant ROM, observed grip/function and selected-task load response | `RehabProgressionAssessment` envelope, protocol registration, episode attribution, history and safety context |
| Compiled lateral-elbow criterion with reviewed interpretation and sources | Same criterion dispatch and review validity/provenance checks |
| Exact reviewed movement options and bounded resistance/dose/restrictions | Same selection envelope, bank hashes and materialisation validator |
| Protocol/criterion/config tests, unknown/wrong-subtype cases | Same ownership, trust, supersede/revoke, replay, freshness and multi-injury tests |

Adding it should require typed payload/evaluator/options/config/tests and a transport union/registry extension. **No new persistence table, SQL event name, verification system or approval envelope.** Reviewer form content differs; the workflow shell and endpoint can be shared. If implementation needs `ElbowClinicianReview` storage, the abstraction failed.

## 16. Future UI surfaces

- **Athlete:** keep reporting separate from approval. Show awaiting review, missing information, verified clinical author/method, decision scope, stale/revoked reason and exact approved work. “Clinical requirement approved; progression still blocked by X” is valid. Athlete cannot edit approved parameters; changes create a new request/evidence packet. No self-verification toggle.
- **Reviewer/recorder:** start with a backend-operated structured packet/submission tool, not a portal. Show exact episode/side/subtype, all required observations and unknowns, selected task, relevant history, other limiting injuries, clearance/restrictions and option versions. Allow defer/reject, selection only within reviewed bounds, reasons and supersede/revoke. Clinical author and admin verifier/recorder are visibly distinct. Neither can override holds, activate a stage, change a drill, or grant contact through this surface.
- **Today:** display only the server-resolved stage and actual selected prescription, including range/resistance/dose/cadence/stop rules. Loading availability is separate from general training clearance. Show blockers and frozen safety holds; do not derive stage from an approval badge or hide limitations behind a success state.

No UI is built by this PR. A future private document surface requires its own controlled access/retention design; current feedback tooling is not that surface.

## 17. Security and abuse handling

| Abuse / failure | Required server behavior |
|---|---|
| Athlete impersonates clinician or selects clinician attribution | Athlete endpoint cannot submit review events. Independent source confirmation and qualified author scope are required; recorder identity comes from authenticated server context. |
| Forged `externally_verified`, author, role or stage | Strict request allowlist; server owns trust result, identity, timestamps and materialisation. User-editable auth metadata cannot confer approval authority. |
| Old approval replay / wrong episode or side | Exact identity, criterion, packet and safety-revision validation under lock. Never match by region or exercise name. |
| Altered prescription or same drill with a different dose | Verify immutable option/selection hashes and bounds; bind frozen blocks/exposures to review/selection. Reject conflict rather than recompute silently. |
| Stale review / new incomplete observation | Latest relevant packet/lifecycle plus complete history; unknown newest evidence cannot fall back to old PASS. |
| Revoked approval or restrictive advice | Append authorised revocation/supersession; restrictions persist until explicit justified release. Medical hold cannot be cleared by approval. |
| Changed bank or criterion | Mismatch prevents new use; preserve historical snapshot/version. |
| Duplicate submit, delayed retry or competing supersession | Scoped idempotency key; identical payload returns same event, changed payload conflicts. Compare expected current packet/prior review under lock. Supersession cannot fork into two current approvals. |
| Forwarded clinician link | Later channel: independently checked contact, separate challenge, short-lived scoped token, one submission and explicit revocation. No secrets or health details in URLs/logs. |
| Cross-athlete access / admin overreach | `require_admin` or explicit scoped reviewer grant, target ownership/context check, target consent and minimal disclosed packet. Existing general admin access is not clinical qualification. |
| Source withdrawal, fraud or inability to confirm | Pending/unknown or explicit revocation. No self-asserted trust upgrade. |

The backend uses service-role credentials, which bypass RLS; Python route authorization remains essential ([repository checklist](service-role-authorization-checklist.md)). The current admin gate requires a live profile role and email allowlist; reuse it for recording, not as proof of clinical competence. Auth token verification is cached briefly; approval permission must use current server authorization rather than trusting cached metadata.

`require_health_feature_access` exempts non-athlete actors. A future admin recorder must evaluate **the target athlete's** current health consent/access, not merely call that helper on the admin. Sharing a reviewer packet needs explicit scoped athlete authorization and documented health-data handling; current self-report consent does not establish a new external sharing workflow. Recheck on submission and revoke packet access on withdrawal. Preserve current historical-read/deletion policy rather than inventing retention exemptions.

For a future migration, keep owner SELECT and client write denial; keep trusted writer service-only, fixed search path, and actor/target validation. Do not expose verifier secrets in the owner-readable event. [Supabase RLS guidance](https://supabase.com/docs/guides/database/postgres/row-level-security) distinguishes grants, row policies and service-role bypass. The changelog and relevant [September PostgreSQL patch notice](https://supabase.com/changelog/postgres-15-19-17-11-breaking-changes) were inspected; this design needs no platform upgrade or feature assumption. Hosted grants/deployed migration state were not audited.

## 18. Minimum future migration/API impact

This PR contains **no migration or API change**. Implementation would require a shared extension, not “existing JSON can already accept it”:

1. Add one shared event type/action contract and a restricted trusted writer. Prefer a separate review RPC/route boundary so the athlete observation endpoint and its three-type union cannot gain approval authority. Reuse locks, ownership, exact context and idempotent insertion helpers rather than duplicating clinical logic in SQL.
2. Add server actor/provenance, packet/current-prior-review checks and atomic supersede/revoke handling. The RPC must reject unsupported versions/actions and invalid targets; compiled Python validates profile-specific clinical content. SQL must still validate the trusted envelope and concurrency context. Service-only privileges do not replace API authorization.
3. Hydrate review events separately from athlete assessments. Do not change `AssessmentContext.parsed` to reinterpret reported evidence as verified. Shared validity context can reuse its chronology/history/setback primitives.
4. Extend `AppStore.get_rehab_schedule_revision` and `preserve_started_prescription` **together** to include shared review lifecycle and relevant assessment events. Both currently consider only check-in/delayed response/clearance for event freshness. #2743 medical-concern capture also updates injury `updated_at`, but a non-concern assessment or future approval does not get this protection automatically. Use a stable event/context revision plus individual selection identity and test acceptance races under the athlete lock.
5. Carry review ID, criterion version, option/selection hash and materialised parameters through backend response models, generated API types, frozen snapshots and exposure provenance. Add live hold checks for invalidated selected work. Keep existing snapshot immutability and allocation/cadence ceilings.
6. Test migration replay, anon/authenticated denial, authorized writer access, target consent, forged trust, opposite-side/episode, complete pagination, concurrent setback/revoke versus acceptance, supersession conflicts and old-version replay. Use a synthetic second protocol to prove reuse without implementing elbow.

No profile-specific SQL, event type, reviewer role or new approval table is needed. Later private document storage or clinician-link capability records may justify their own shared access model; keep them separate from clinical stage truth and assess them only when the chosen channel requires them.

## 19. What not to build

No clinician platform, hospital identity network, medical rules DSL, blockchain/signature system, unrestricted plans, injury-specific approval tables/events, universal assessment form/scoring, family-wide numerical cutoffs, organisation RBAC, automatic kg/dose guessing, client trust flag or second stage engine.

Do not equate a verified source with sufficient clinical content. Do not use queue resolution, file upload, `policy_review_hash`, bank membership, clearance, elapsed time, camp phase, observation count or symptom improvement as a surrogate for the missing criterion.

## 20. Next three PRs

| PR | Small reviewable scope | Acceptance boundary |
|---|---|---|
| 1. Shared review contract and validity evaluator | Strict conceptual envelope turned into typed contract; pure lifecycle/packet/version/prescription-selection validation; optional compiled checkpoint integration exercised with test-only profiles and a synthetic second protocol. No writer, migration, UI, trust assertion or activation. | Replay and invalidation tests; distinction between qualified author/verifier/recorder; reject client trust, wrong side/episode, altered selection, incomplete/newer packet, superseded/revoked and mismatched versions. Production profiles/hashes/bank and v1 behavior identical. |
| 2. Restricted manual-confirmation capture | One shared event type and service-only writer, authenticated admin recording of independently confirmed qualified-author statements, target consent/access, idempotency/supersession and freshness/freeze integration. Backend-operated tool; no clinician account/document upload required. | Real PostgreSQL privilege/concurrency/migration tests; authorization and source-completeness cases; review/assessment/revocation invalidates unstarted acceptance; frozen work held without rewriting. LOAD stays closed. Pilot operational source-confirmation process must exist before marking trust. |
| 3. Reviewed Achilles option and interpretation pilot | Qualified clinical review of exact applicability, actionable range/resistance/dose/cadence options and criterion; typed missing task evidence; materialisation and minimal athlete/Today pending/decision visibility. Exercise the complete flow in shadow with shared capture. | Clinical sign-off and exact candidate bounds, source/provenance, no fabricated cutoff, selected-work/frozen/exposure consistency, hold/clearance/multi-injury/setback behavior and all-consumer resolution. Keep production LOAD closed while reviewing results. |

After these, an **explicitly scoped activation PR** can decide whether the evidence, clinical review, real pilot operation and full safety flow justify opening Achilles LOAD. Activation is not bundled with infrastructure. Elbow remains a later content/protocol/evaluator project using the same envelope.

## Investigation verification and limits

Inspected the contracts/services/migrations/UI/data identified above, including the actual latest-Main changes after #2748. Executed read-only policy/catalog composition and confirmed the 64/7/103/zero-promotable state. Reviewed the final CPG text, Dutch guideline and Kent guidance; distinguished source-supported principles from this report's product decisions. No new medical thresholds were derived.

Validation passed: Markdown repository links (no missing targets), all 20 requested report sections, production directories with an empty diff, and catalog/bank/ledger/archive Git blob hashes matching Main with checkout newline filters respected. The existing preservation commands also passed:

```text
python tools/audit_rehab_bank_rationalisation.py --check
python tools/review_rehab_advanced_candidates.py --check
python tools/consolidate_rehab_exact_duplicates.py --check
```

These confirmed 103 live identities, unchanged profile hashes, no activated stages and 29 preserved historical duplicate identities. The staged PR diff is checked with `git diff --cached --check` and restricted to this document. A document-only change does not require rerunning the application build or full runtime test suite; this investigation makes no new runtime-pass claim. No hosted database, provider identity, clinical service, source-verification workflow, deployment or real patient prescription was tested.

## Final decision and smallest next implementation

**C — shared clinical progression review infrastructure, optional per criterion, separate from clearance and backed by existing episode events.** This supplies the missing auditable clinical judgment and bounded prescription without inventing an injury-specific subsystem. It supports future automatic criteria as well as human decisions, while the current engine retains stage authority.

The smallest next implementation is **PR 1: the typed shared review contract and pure validity evaluator, tested with synthetic contexts, with every production stage/profile/hash/bank and v1 review unchanged**. Persisting trusted reviews follows only after the author/provenance boundary, bounded selection and invalidation rules are concrete and reviewed.
