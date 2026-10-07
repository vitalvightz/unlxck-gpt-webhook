# Clinical progression review: implemented contract

This page records the #2758 contract step. Its later persistence/trust/freshness implementation is described in [clinical progression review capture](clinical-progression-review-capture.md); the production criterion registry remains empty.

Implements the contract/evaluator step of [the merged decision](clinical-progression-review-design.md) (#2757). These are internal Python types and pure functions. No real review is stored, trusted or used by Today. Production remains CALM/RESTORE only, with 64 active profiles, 103 live prescription identities and zero promotable higher-stage transitions.

## Files and public entry points

| File | Contract/function |
|---|---|
| [`clinical_progression_review.py`](../api/contracts/clinical_progression_review.py) | `ClinicalProgressionReview[PayloadT]`, author/provenance/evidence types, `ReviewLifecycleChange`, `CriterionReviewDefinition`, `CriterionReviewRegistry`, `ReviewTrustPolicy` |
| [`reviewed_prescription.py`](../api/contracts/reviewed_prescription.py) | `ReviewedPrescriptionOption`, `ReviewedPrescriptionSelection`, dose/cadence/resistance types, `validate_prescription_selection`, `materialised_selection_hash` |
| [`clinical_review_validity.py`](../api/contracts/clinical_review_validity.py) | `ReviewValidityContext`, `ClinicalReviewInput`, `evaluate_clinical_review`, `ReviewEvaluation`, `FrozenClinicalReviewPin`, `evaluate_frozen_review` |
| [`rehab_progression.py`](../api/contracts/rehab_progression.py) | Optional explicit `clinical_review_input` argument to `evaluate_transition` for shadow evaluation of an existing `functional_checkpoint` |

Every nested contract forbids extra fields and is frozen. Versions are positive strict integers; identifiers are nonblank; digests are SHA-256 hex; timestamps are timezone-aware; numeric selections reject nonfinite values. Profile-specific interpretation is a concrete `ReviewModel` subclass registered in compiled code, parsed through `ClinicalProgressionReview[definition.payload_type]`. It is not an arbitrary JSON payload. There is no generic clinical scoring algorithm or editable rules DSL.

## Review envelope and actors

The immutable review pins `review_id`, schema version, criterion ID/version, profile ID, policy version/hash, athlete/injury/episode/known side and a consecutive target transition. It carries clinical and recorded times, a reviewed evidence packet, author, provenance, decision, typed interpretation, optional selected prescription, rationale, structured reasons and an optional prior review identity. An optional expiry requires an explicit reason; the evaluator invents no medical age cutoff.

`ClinicalAuthor` identifies the person whose judgment is relied on, their displayed identity, qualification reference and clinical scopes. `OperationalActor` separately identifies the recorder and verifier. The athlete is the review subject. An operational recorder cannot double as the clinical author; the athlete cannot be any authority actor. A clinician direct submission can identify the recorder as the clinical author, but still needs independently established provenance. Scope/qualification claims in a payload do not establish qualification.

`ReviewSource` expresses athlete reporting, independent confirmation of a clinician statement, clinician direct submission, provider integration and manual document verification. `ReviewProvenance` records the recorder, verifier, confirmation timestamp, opaque confirmation reference and statement digest. These are athlete-disclosable references, not contact secrets, URLs or private correspondence. A declaration of a channel is not verification.

`ReviewTrustPolicy` is a separate server-side dependency receiving the exact review/lifecycle object and explicit `as_of`. The default `UnsupportedReviewTrust` rejects **every** source. The production `CLINICAL_REVIEW_REGISTRY` is empty. There is no synthetic trust switch or trusted enum in a request. Tests alone implement `SyntheticAttestations`, an in-memory allowlist of exact object digests that fails when an author, decision or selection is forged.

## Validity, decision and criterion satisfaction

`ReviewDecision` has `approved`, `not_approved` and `deferred`. Revocation and supersession are append-only `ReviewLifecycleChange` objects with `revoked`/`superseded`, a target review, effective/recorded times, provenance and reason. A supersession names its replacement; a revocation cannot carry a replacement dose or clinical approval.

`ReviewEvaluation` exposes these separately:

- `validity`: whether the review is usable against this replay context.
- `trusted`: the independent provenance policy outcome, which alone grants nothing.
- `clinical_decision`: the author's decision, including denials/deferments.
- `criterion_status`: PASS/FAIL/UNKNOWN from decision plus the compiled interpretation evaluator.
- `prescription_valid`: independent bounded selection validation, or absent for a decision without work.
- Structured `reason_codes`, explicit `evaluated_at`, review identity and an optional frozen pin.

A valid trusted deferred review is UNKNOWN. A valid denial is FAIL. A valid trusted approval with inadequate or unknown typed interpretation is FAIL/UNKNOWN. Only usable approval plus a passing interpretation and any required valid prescription can satisfy the checkpoint. Approval without a required prescription is unusable. Denial/deferment may omit work. None of these outputs writes a stage or a clearance.

## Explicit replay context and invalidation

`evaluate_clinical_review(context, reviews, as_of=..., lifecycle=..., registry=..., trust=...)` takes all state explicitly. The caller must supply a complete, exactly scoped review history and the server-owned replay snapshot: subject/episode/side, current profile/policy/criterion versions, target transition, episode start/current status, current evidence packet, bank digests, safety history and persistent medical/restriction holds. Replaying an earlier cutoff requires the corresponding historical packet, safety/policy/bank/criterion artifacts and trust state, not today's snapshot.

`ReviewedEvidencePacket` pins the evidence cutoff, packet and safety revision digests, exact assessment event IDs/protocol versions/content digests/observation and recording times, and optional clearance reference. The future server packet builder must establish each reference's ownership and completeness and compute those revisions; a review cannot supply the authoritative current packet. Exact packet equality conservatively invalidates a changed or incomplete relevant packet. Advancing `as_of` without changing the packet does not invent expiry.

Clinical review must follow the evidence cutoff and episode start, confirmation must follow review, and recording must follow confirmation. Review/verification and visible context times cannot be in the future. Readiness references predating an invalidating setback remain unusable; later transcription cannot freshen an old clinical observation. Safety events are explicit exact-episode inputs; a foreign event makes completeness uncertain. Persistent holds cannot be released by approval.

Records after `as_of` are excluded. Evaluation uses the latest whole visible record; it never searches for the best historical approval. The newest malformed, denied, deferred, wrong-version or revoked record cannot revive an older approval. Duplicate identities, equal-time competing records, missing prior records and a forked replacement chain fail closed. Lifecycle events require independently trusted provenance; even an unconfirmed withdrawal prevents use until resolved. A new independently usable replacement can follow an old revocation; the original never becomes active again.

Reason enums provide the full machine-readable vocabulary:

| Checks | Reason codes |
|---|---|
| Missing/malformed | `clinical_review_missing`, `clinical_review_malformed`, `review_criterion_not_registered` |
| Exact identity | `review_athlete_mismatch`, `review_injury_mismatch`, `review_episode_mismatch`, `review_side_mismatch`, `review_profile_mismatch`, `review_criterion_mismatch`, `review_criterion_version_mismatch`, `review_transition_mismatch` |
| Versions/context | `review_schema_version_unsupported`, `review_policy_version_or_hash_mismatch`, `review_episode_not_current`, `review_history_incomplete`, `review_evidence_packet_mismatch`, `review_engine_context_mismatch` |
| Time | `review_future_timestamp`, `review_chronology_invalid`, `review_before_episode`, `review_expired` |
| Safety | `review_invalidated_by_setback`, `review_invalidated_by_medical_hold`, `review_invalidated_by_restriction`, `review_invalidated_by_new_assessment`, `review_invalidated_by_clearance_change` |
| Authority | `review_provenance_incomplete_or_malformed`, `review_actor_separation_invalid`, `review_author_scope_mismatch`, `review_trust_channel_unsupported_or_unconfirmed` |
| Lifecycle | `review_duplicate_or_conflicting_identity`, `review_supersession_history_conflict`, `review_revoked`, `review_superseded`, `review_lifecycle_malformed_or_untrusted` |
| Selection | `review_required_prescription_missing`, `review_selection_or_option_malformed`, `review_option_missing`, `review_option_binding_mismatch`, `review_option_version_or_hash_changed`, `review_drill_identity_or_hash_changed`, `review_range_not_allowed`, `review_resistance_not_allowed`, `review_dose_not_allowed`, `review_cadence_not_allowed`, `review_restrictions_not_preserved`, `review_materialised_hash_or_version_mismatch` |

Compiled clinical evaluators supply their own structured interpretation reasons after shared validity succeeds. Denial and deferment have explicit `clinical_decision_not_approved` and `clinical_decision_deferred` reasons.

## Registry, bounded work and hashes

The immutable registry binds `(criterion_id, version)` to profiles, transition, concrete payload type, required author scope, reviewed options, whether work is required, and a deterministic typed evaluator. Duplicate keys/options and foreign option bindings are rejected. Retained versions can support historical replay; evaluation against the current version does not migrate an old approval.

An option fixes one exact drill ID/bank digest, instructions/mechanics, range choice identifiers, reviewed resistance modes/bounds, finite dose choices, cadence choices and mandatory/allowed restriction identifiers. A range identifier denotes a reviewed actionable variant, not free-text permission to change mechanics. There are no default clinical doses, range limits or resistance bounds. External resistance requires explicit min/max kg; bodyweight carries no kg.

A selection pins option ID/version/hash, drill identity/hash, the concrete range/resistance/dose/cadence, canonical restrictions, selection version and materialised prescription digest. Pure validation enforces registry membership, exact scope/transition, current bank content, allowed choices and preserved mandatory restrictions. It rejects arbitrary drills, movement substitution, unreviewed text, added contact permission and deleted stop rules. There is no instruction field to override the option's mechanics.

Existing `fightcamp.rehab_clinical.content_hash` hashes canonical JSON. Option hashes cover the complete option, including fixed mechanics and bounds. The materialised selection hash covers the complete option plus all selected parameters and their version, excluding its own digest. This digest describes prospective executable content; this PR does not produce a live `ClinicalPrescription` or persist anything. A content hash protects integrity, not provenance. Independently pin criterion/schema/policy/option/selection versions: closed diagnostics are deliberately excluded from the existing policy hash, so a policy hash alone cannot pin clinical evaluator logic. Existing policy hash rules are unchanged. Bank identity uses the existing digest, not an invented numeric bank version.

## Engine, clearance and frozen work

`evaluate_transition` accepts an optional `ClinicalReviewInput` only with explicit `as_of`. It checks its own injury/profile/policy/transition identity, active episode, history and known medical/setback gates before delegating to the shared evaluator. The result satisfies only its matching `functional_checkpoint`. All other requirements, closed-transition rules and target activation remain authoritative. There is no default review hydration, and `resolve_reviewed_progression`/Today production calls are unchanged. Achilles v1 retains its existing branch before shadow shared bindings and remains FAIL/UNKNOWN only.

Clinician clearance keeps exactly its existing rehab/training/contact scopes and ceiling semantics. A review neither creates nor widens clearance; training/contact clearance supplies no clinical checkpoint approval. Tests run the existing session reconciliation to show a restrictive ceiling still holds contact even alongside a valid synthetic approval. Medical and multi-injury safety remain separate.

`FrozenClinicalReviewPin` identifies review ID, criterion ID/version, option ID/version, selection version and materialised prescription digest. `evaluate_frozen_review` is a prospective pure overlay, not persistence wiring. Only current, passing, exact pins may accept unstarted work. Invalidated unstarted work is held; started work keeps immutable history and is held from continuing. Completed exposures remain immutable completed history. A valid new review/selection cannot silently replace an old frozen pin. The function returns safety/acceptance flags and reasons; it does not return or rewrite work content. Actual acceptance-lock/revision/snapshot/exposure integration is the next PR.

## Synthetic proof and production boundaries

[`clinical_review_fixtures.py`](../tests/clinical_review_fixtures.py) contains two invented profiles/criteria, different concrete interpretation payloads, reviewed option sets and byte-bound independent attestations. Both use the same envelope, registry, ownership/side/time/lifecycle/evidence validation, selection validation and shadow engine integration. Fixture numbers are invented test values, not Achilles or elbow prescriptions.

The test files cover shared contracts/actors, replay/invalidation, bounded selections and engine/freeze/clearance separation. Existing #2748 and baseline preservation tests additionally pin all 64 profile hashes, bank/ledger/archive content and non-passing Achilles behavior. Audit tools confirm 103 live identities, no newly activated stages and 29 retained historical duplicate identities. No production bank, pathway declaration, ledger, archive, clearance, exposure, service, route or web UI is changed.

Unimplemented: any database event type/migration/RPC, writer/API/admin tool, clinician account/portal, upload flow, real trust channel, packet hydration/compiler, individual work materialisation into Today, acceptance locking, scheduler revisions or snapshot/exposure persistence. There is no production review definition or reviewed Achilles LOAD option; LOAD/DYNAMIC/RETURN remain closed. No other injury protocol is implemented.

Next PR: restricted manual-confirmation capture using one shared episode-event type and a service-only trusted writer, with an authenticated admin recording independently confirmed qualified-clinician decisions. It must establish server provenance, target consent/access, source completeness, exact packet/reference ownership, idempotency, lifecycle concurrency and review/assessment/revocation freshness under acceptance locks. Keep LOAD closed.

Later Achilles work supplies a newly reviewed typed interpretation/criterion and clinically reviewed exact option set; it must not turn `achilles_restore_load_review_v1` into PASS. A future elbow protocol can register its own payload/evaluator/options in this same envelope after separate clinical content review, without a new storage model, authority mechanism or episode evaluator. Activation needs a separate explicit PR.
