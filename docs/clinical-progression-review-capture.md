# Shared clinical progression review capture

Base: latest Main after #2758 (`d5e06c52`, including #2763 and #2764). This implements the persistence/trust step described in [the design](clinical-progression-review-design.md) and [the contract](clinical-progression-review-contract.md). It does not define a real clinical criterion, supply an Achilles option, activate LOAD, or change clinician clearance. This describes the #2765 baseline. The later [Achilles shadow pilot](achilles-restore-load-criterion.md) registers the first dormant criterion/option without activating LOAD.

## Storage and permissions

One shared review event, `clinical_progression_review`, stores exactly the #2758 `ClinicalProgressionReview` payload in `injury_episode_events.payload`. One shared append-only lifecycle event, `clinical_progression_review_lifecycle`, stores `ReviewLifecycleChange`. No profile tables or clinical interpretation in SQL.

Migration: `20261007133906_clinical_progression_review_capture.sql`. It adds a private `clinical_capture` receipt column to the existing table, restricts owner-select RLS to nonclinical events, creates uniqueness constraints for replacement/lifecycle actions, and supplies service-only snapshot/writer RPCs. Clinical rows cannot be updated. Their capture receipts hold the server policy version, authenticated recorder ID, factual request digest, exact envelope digest, opaque statement reference and exact independently confirmed statement text. The server computes SHA-256 of that text's exact UTF-8 bytes without trimming/rewriting it; hydration checks it against the shared provenance digest. Ordinary observation rows must have no capture receipt.

Neither anon nor authenticated users can invoke either RPC or insert/update/delete review rows. This applies equally to athletes, unrelated users and browser admins. Owner read is deliberately **denied for both clinical event types**, including their clinical decisions: the generic owner-visible stream must not disclose operational confirmation or qualification references. No public summary API is added. The service reads the raw private history; the admin capture response returns only event/review IDs, recording time and event type. Existing nonclinical owner reads remain available.

## Admin channel and actor separation

The route uses existing `require_admin`: a verified authenticated profile must have stored role `admin` **and** email membership in the server `UNLXCK_ADMIN_EMAILS` allowlist. The service repeats this rule before reading or writing. SQL rechecks the recorder's current stored admin role while holding a row share lock. A service-role key supplies transport privilege; it is not API authorisation.

The clinical author is the independently identified qualified clinician/physio. The authenticated operator is separately recorded as both verifier and recorder. Neither the athlete nor the operator may be named as clinical author, including alternate casing of a UUID. Actor roles, provenance channel, trust receipts and hashes are server-built. The admin does not become a clinician.

Operational rule: submit a `ConfirmedClinicalStatement` **only after independently checking the clinician identity, qualification, criterion scope and exact statement/decision**. Supply an auditable qualification reference (professional registration or equivalent internal verification reference), statement reference, independent confirmation reference and actual aware review/confirmation timestamps. If that confirmation cannot be performed, do not submit. Empty/missing references, an inappropriate scope, impersonation, future confirmation or incomplete provenance are refused. This is a manual attestation channel, not an automatic professional-registry lookup; a reference by itself is not an external registry validation.

`PersistedClinicalReviewTrust` derives authority from complete raw service-store rows written by that boundary, checking the private receipt against the exact canonical envelope bytes, recorder/verifier identities, independent-confirmation channel, author separation and qualification evidence. Altered payloads cannot inherit the receipt. The pure #2758 evaluator still defaults to unsupported trust. Athlete reports, document uploads/verification, clinician-direct submissions and provider integrations stay unsupported.

## API and exact binding

Admin-only JSON endpoints:

- `GET /api/admin/athletes/{athlete_id}/injuries/{injury_id}/episodes/{episode_id}/clinical-review-packet?criterion_id=...&criterion_version=...`
- `POST /api/admin/clinical-progression-reviews`
- `POST /api/admin/clinical-progression-reviews/lifecycle`

The strict capture request supplies stable request and subject/episode IDs, a compiled criterion/version, confirmed factual statement, bounded selection choices and optional prior review ID. It does not accept profile, side, policy/bank hash, evidence IDs, materialised hash, recorder/verifier roles, trust flags, stage or criterion PASS. The statement's `reviewed_packet_revision` must equal the current **server-built** packet; it is a compare token, not authority to choose evidence. Obtain/export the packet for the clinician first. A changed packet requires a decision on the changed evidence; transcription time cannot freshen an older judgment.

The service derives the profile from the current injury identity and active compiled policy. It requires the criterion to belong to that profile's exact transition and to be the current compiled version. It computes the selected option/drill/bank/version hashes and materialised selection digest from the code-owned option, then delegates strict payload and bounded choice validity to #2758. No production criterion currently matches, so production capture fails closed before any clinical record is written. Tests inject two invented criteria; there is no request, setting or test-mode switch that enables them in production.

## Target athlete consent

The subject must be an existing **athlete** with approved access. `require_health_feature_access` runs on the target's freshly read profile, not the operator's profile: usable age/date of birth at the existing minimum age, current accepted Terms, and current separate explicit health consent. A missing grant, superseded consent version, false consent boolean or withdrawal at least as recent as the grant refuses processing. Existing product constants and guards are reused.

The locked snapshot includes the complete profile row. The writer takes a share lock on that profile, rechecks the current consent/access floor, and compares the whole snapshot to the validated one. Withdrawal, Terms/consent version changes, target access changes or role changes between preparation and submit therefore reject the write; a concurrent profile update either commits before this check or waits until the authorised capture transaction finishes. A retry still requires current target access/consent. Lifecycle capture also uses this target policy. It can revoke on a closed current episode, but cannot rebind a replaced episode.

## Evidence and replay

`clinical_review_capture_context` returns one complete exact-episode snapshot of current injury, target profile, episode events and rehab exposures under the existing athlete lock. RPC aggregation has no first-page truncation. Python constructs a deterministic packet and safety revision from this state; clinical review/lifecycle records are excluded from the evidence digest so recording a review does not invalidate itself. The cutoff is the latest relevant state/evidence timestamp, not the query clock. Clinical review must follow that cutoff and episode start, then confirmation, then recording.

The packet hashes complete episode observation/exposure bytes and injury context, and pins observation protocol/version/content/times, exposures, current side, policy and current option bank content. Assessment concerns persist via the existing observation helper. Setbacks include symptom-stopped/worse rehab responses. Pre-setback evidence remains in the full packet/audit export but cannot become fresh readiness references. A clearance reference remains a clearance observation, never a clinical approval or wider training/contact scope.

Hydration reconstructs complete criterion history and its lifecycle events, supplies private byte-bound trust, and always uses `evaluate_clinical_review`; no mutable `current_review_pass` is stored. New assessments, worse responses, setbacks, persistent medical concerns, restrictions/clearance changes and other changed relevant evidence invalidate the packet or safety context. Current policy/criterion version, bank and option integrity are independently checked. Malformed, missing or foreign history fails closed. Historical replay requires the corresponding historical server snapshot and compiled artifacts, as in #2758; this is not an automatic historical-snapshot service.

## Idempotency, lifecycle and concurrency

An event ID derives deterministically from the globally stable request ID. Subject/injury/episode are separately validated; reusing the request for another valid subject also conflicts. Same factual request digest and authenticated recorder return the original result, including its original recording time, even after that current episode closes. Changed payload under the same ID conflicts. The writer repeats this check under the lock, so concurrent duplicates insert once. A client cannot choose server timestamps/hashes to manufacture an equivalent request.

Replacing a review must name the latest review for that criterion. The new review and its supersession lifecycle event are committed atomically. The original record remains unchanged. Duplicate replacement captures return the same review. Unique constraints and the locked snapshot prevent competing replacements, self-supersession, forks, duplicate lifecycle actions and foreign replacement targets. The lifecycle endpoint validates an existing exact-scope target; a supersession must name an existing replacement which points to that target. Attempting to append a second supersession for an already replaced review conflicts. Revoke is an append-only confirmed operational action; its stable retry returns the original lifecycle event. A valid independent replacement can follow a revoked older review; revocation never revives the old review.

Lock order is unchanged: `pg_advisory_xact_lock(hashtextextended('injury:' || athlete_id,0))` before injury row share locks. Review writes, lifecycle changes, assessments, exposures, setbacks, closure/replacement and prescription acceptance share this athlete lock. The writer compares the entire profile/injury/event/exposure snapshot after taking it; changed state or competing review history rejects the in-flight capture. No new advisory key or lock hierarchy is introduced.

## Transition and frozen work

Today can hydrate only code-registered clinical checkpoints from server history and pass their inputs through `resolve_injury_policy` and `resolve_reviewed_progression` to the existing `evaluate_transition`. Hydration failure supplies no passing input. The review satisfies only its matching requirement; exposure, symptom, safety, closed transition and stage activation rules remain authoritative. The Achilles v1 branch still runs first and remains FAIL/UNKNOWN only. Training/contact clearance supplies no review; a review supplies no clearance.

`get_rehab_schedule_revision` and the existing `preserve_started_prescription` freshness check now include assessments, clinical review and lifecycle events. Saved **unstarted** snapshots must also recheck this context. Existing bundle/daily allocation checks are preserved. A server helper can store validated option/selection content with `FrozenClinicalReviewPin` inside future blocks; it is exercised only by synthetic work. No Today prescription generator emits such work yet.

The prospective Today overlay hydrates/evaluates pins and holds unstarted acceptance or started continuation when a pin no longer matches. It preserves the historical block content. A restricted database trigger rechecks pin scope/versions/selection hash, open episode, lifecycle and evidence identity under the same acceptance lock, preventing a revocation racing acceptance. Refreshing an evidence ID cannot make a revoked pin valid. Started work may record stopping under the existing safety semantics. Completed/modified snapshots retain immutable history and are not replayed as future approvals; completed exposures are not changed. No frozen prescription subsystem is rebuilt.

## Verification and remaining work

Tests cover route authorisation, strict requests, target consent, exact context and actors, manual-source receipts, bounded selections, deterministic packets, later evidence/version/policy/bank changes, idempotency, lifecycle and frozen safety. Real disposable PostgreSQL 17.11 tests exercise anon/authenticated/owner/unrelated role boundaries, service writes, immutable/private history, concurrent duplicate insertion, assessment/setback/closure/episode/consent/role races, competing replacement/revoke races and revocation versus acceptance. CI runs them alongside the existing PostgreSQL lock tests. The deployment schema requirements include the new receipt column and restricted functions: apply the migration before deploying the API. Coordinate those steps because the extended SQL freshness source and the API revision source must agree; acceptance through the old API may briefly reject an assessment-aware snapshot until the new API is deployed. The migration is tested locally; this PR does not apply it to a live database.

Preservation remains 64 active profiles, 103 live identities, CALM/RESTORE only, zero promotable higher-stage transitions, unchanged bank/review ledger/archive, clinician clearance, multi-injury precedence, surface/wound rules and completion/exposure semantics. No clinician portal, public admin/athlete UI, upload, provider integration, lateral elbow implementation or production activation. The Achilles criterion/option is now defined by the separate shadow pilot.

The **ACHILLES REVIEWED LOAD OPTION + CLINICAL INTERPRETATION PILOT** now uses this channel. It keeps `achilles_restore_load_review_v1` non-passing and production pathway data unchanged. Production activation remains a separate PR.

## Current shadow packet bindings

The prepared packet additionally returns this exact injury context, compiled reviewed options with their hashes, and the registry-controlled interpretation schema. Its revision includes current policy version/hash, criterion/version, interpretation schema, option hashes and current reviewed bank hashes. A material change after preparation requires a new clinical decision before recording; capture cannot silently stamp the changed configuration onto the old statement.

The first real criterion can be captured while its exact target stage is disabled and its transition non-promotable, even though the production pathway does not yet declare the checkpoint. A live target still requires its exact declaration. This uses the existing append-only writer/receipt/lifecycle flow and requires no additional migration.
