# Achilles progression input contract

Current follow-up: [Achilles RESTORE → LOAD clinical review](achilles-restore-load-criterion.md) adds a versioned fail-closed review and a Today reporting form. The original #2743 capture contract below remains intact. LOAD/DYNAMIC/RETURN are still closed; no profile, bank or prescription changed.

This adds capture and readers for `achilles_tendonitis`, using the missing inputs identified in the #2742 review. LOAD stays closed; `achilles_tendonitis_eccentric_calf_drops_on_step` stays dormant. No clinical transition, threshold, profile, dose, bank identity or hash changes.

## Write and read paths

The future injury check-in UI submits the existing authenticated `POST /api/today/injury-episode-observation` endpoint with `event_type: "rehab_progression_assessment"`. Health-feature consent is required. Use the server-issued injury and episode IDs and the episode's exact side; do not ask the athlete to select a different episode or side. Unknown values can be omitted except the required side, assessment timestamp and assessor. Do not instruct an athlete to perform an assessment through this API; it records an assessment that actually occurred.

Example body (illustrative observations, **not a prescription or readiness rule**):

```json
{
  "injury_id": "22222222-2222-4222-8222-222222222222",
  "injury_episode_id": "33333333-3333-4333-8333-333333333333",
  "event_type": "rehab_progression_assessment",
  "report_id": "44444444-4444-4444-8444-444444444444",
  "assessment": {
    "schema_version": 1,
    "assessment_kind": "achilles_tendon_progression_v1",
    "protocol_version": 1,
    "side": "left",
    "assessed_at": "2026-10-05T15:00:00Z",
    "assessor": "clinician_physio",
    "payload": {
      "site": "insertional",
      "incompatible_pathology": "excluded",
      "suspected_rupture": false,
      "marked_weakness": false,
      "traumatic_loss_of_function": false,
      "clinician_restriction": false,
      "heel_rise_completed": true,
      "heel_rise_mode": "single_leg",
      "heel_rise_quality": "controlled",
      "heel_rise_repetitions": 1,
      "heel_rise_assessor_usable": true,
      "loading_task": "heel_rise_assessment",
      "loading_performed_at": "2026-10-04T15:00:00Z",
      "during_symptoms": 3,
      "delayed_symptoms": 4,
      "delayed_response_at": "2026-10-05T15:00:00Z",
      "range_assessed": true,
      "permitted_range": "floor_level",
      "resistance": "bodyweight",
      "range_load_tolerance": "tolerated",
      "range_load_assessor_usable": true
    }
  }
}
```

The server returns the persisted episode-event object, including `id`, server-owned `athlete_id`, `injury_id`, `injury_episode_id`, `created_at` and `payload`. The server payload records `region: achilles`, `injury_type: tendonitis`, `profile_id: achilles_tendonitis`, derived `medical_concern` and actual `observation_times`, the complete normalized `assessment`, `source: athlete_reported`, `externally_verified: false` and server-read injury text context. Keep `report_id` stable for retries; changing the payload with the same ID returns 409. Send a new report ID for a new observation. Delayed answers require resubmitting the complete updated snapshot with a new report ID, preserving the actual loading/assessment times.

Today loads the existing episode-event history and exposes `open_injuries[].rehab_decision.assessment_inputs` only for an Achilles episode with captured inputs. Each entry has `status`, `reason_code`, observation ID, assessor, verification and clinical-promotion usability. `evaluate_transition` reads the same registered inputs only for `kind: input_availability`, `basis: data_sufficiency`. Availability alone cannot make a transition promotable. Clinical functional requirements remain missing input even when an availability result passes. Production profiles declare no such new requirements in this PR. Existing Today payloads and CALM/RESTORE behavior stay unchanged when no new observation exists.

## Fields and unknowns

| Assessment fields | Allowed values / meaning |
|---|---|
| `side`, `assessed_at`, `assessor` | Required. Exact `left/right/bilateral/unknown`; timezone-aware observation time; `self_reported/clinician_physio/coach_observed/unknown`. |
| `site` | `midportion/insertional/unknown`; default unknown, never inferred. |
| `incompatible_pathology` | `excluded/suspected/not_assessed/unknown`; default not assessed. Exclusion is a reported assessment, not a diagnosis. |
| `suspected_rupture`, `marked_weakness`, `traumatic_loss_of_function`, `clinician_restriction` | Strict boolean or null (unknown). Any true, or suspected incompatible pathology, holds this episode for medical review. |
| `heel_rise_completed`, `heel_rise_assessor_usable` | Strict boolean or null. Usability is the assessor's reported judgment, not server clinical clearance. |
| `heel_rise_mode`, `heel_rise_quality`, `heel_rise_repetitions` | `single_leg/double_leg/unknown`; `controlled/reduced_control/unable/unknown`; optional nonnegative integer. No rep or quality readiness cutoff. |
| `loading_task`, `loading_performed_at` | `heel_rise_assessment/clinician_selected/unknown`; actual timezone-aware loading timestamp or null. |
| `during_symptoms`, `delayed_symptoms`, `delayed_response_at` | Actual numeric reports on a 0–10 symptom scale or null; delayed observation timestamp or null. Scale bounds validate data, not readiness. No pain cutoff or categorical-to-numeric conversion. Delayed time must follow loading; both must precede server recording. |
| `range_assessed`, `range_load_assessor_usable` | Strict boolean or null. |
| `permitted_range`, `resistance`, `resistance_kg`, `range_load_tolerance` | `floor_level/clinician_limited/unknown`; `bodyweight/external/unknown`; optional nonnegative external kg; `tolerated/not_tolerated/unknown`. No fixed load or range threshold. Further detail may be needed for a clinical rule involving clinician-limited range. |

Unknown enum fields default to unknown; optional booleans/numbers/times default to null. Extra fields, numeric strings, numeric booleans, naive dates, impossible timestamp ordering and results without an assessment are rejected. A completed assessment can report inability; completion is distinct from successful function.

## Checkpoint registry and reader

The existing `functional_checkpoints` declarations in `data/rehab_pathways.json` own the four stable IDs, each explicitly `basis: data_sufficiency`, `assessment_kind: achilles_tendon_progression_v1`, `protocol_version: 1`. `api/contracts/rehab_assessment.py::input_definitions` validates and binds these declarations to the registered typed protocol reader. Unknown IDs/kinds/versions fail closed. No clinical functional checkpoint is captured yet. Profile composition rejects a requirement whose basis differs from its declaration; the engine never consumes availability as a clinical functional PASS.

| Stable ID | Exact fields and evaluator |
|---|---|
| `achilles_site_assessed` | Known `site` with a known assessor. Self reports retain their source; no inferred diagnosis. |
| `achilles_heel_rise_assessed` | Completed assessment, known mode and quality, reported usable=true, with clinician/physio attribution or coach observation. Self-only/unknown source is unknown. Reported inability or unusable result is fail. No rep threshold. |
| `achilles_loading_response_assessed` | Known loading task and both actual during and delayed numeric symptoms with valid loading/delayed times. Missing delayed response is unknown. Numeric magnitude does not establish acceptable tolerance. |
| `achilles_range_load_assessed` | Clinician/physio attribution, reported pathology exclusion, assessed known range/resistance, reported tolerated and usable=true. External resistance requires an actual kg value. Self/coach-only, unspecified pathology/range/load are unknown; not tolerated or unusable is fail. |

`pass` means sufficient **reported input**, not satisfied clinical readiness. Every result explicitly has `usable_for_clinical_promotion: false` and `externally_verified: false`. The athlete API cannot verify an assessor, submit proof of clinician identity or acquire clinician privileges. Coach observations may describe function but cannot establish pathological exclusion/permitted loading. A future promotion rule must define clinical interpretation and acceptable provenance/verification; it must not promote solely because these input-availability checkpoints pass.

## Ownership, freshness and safety

The authenticated athlete ID comes from the profile, never the request. The writer checks active Achilles/tendonitis identity and the current episode. The existing service-only RPC holds the athlete advisory lock, checks the current owned episode and exact stored side, and compares the server-read injury text before appending. Owner-select RLS and service-only writes remain in force.

The reader checks athlete, injury, episode, region, exact type and exact side again. Left never supplies right or bilateral; unknown side never passes. A valid left insertional report belongs only to that left episode. Right-side, elbow-tendonitis or prior-episode attribution cannot satisfy it. An unknown site stays unknown.

The newest recorded whole snapshot supersedes the older one, even if incomplete; no fallback to an older pass. All observation times must be within this episode and at/before recording, and recording cannot be in the future. The start is the first current-episode injury audit event, falling back to injury creation. Any later episode setback invalidates the earlier assessment/loading/delayed timestamps. Incomplete assessment history or truncated exposure history is unknown. The store reads all episode-event pages through an explicit completeness contract; no default PostgREST page is treated as complete history. `AssessmentContext` requires an aware explicit `as_of`; public policy/resolver calls accept it for deterministic replay and use one server clock value when omitted. A replay ignores records written after its cutoff. There is no arbitrary age limit, session count, elapsed-time readiness rule or clearance proxy; a clinically sourced freshness interval remains a future decision.

Safety concerns persist for the same episode even after a reassuring assessment or athlete-reported clearance. They feed the existing shared medical-hold and clinician-clearance hierarchy, stop Today training execution and withhold rehab prescriptions without diagnosing rupture. Concern capture updates the injury's revision timestamp atomically so a previously fetched unstarted prescription must be refreshed. Frozen prescription contents remain untouched. This narrow API has no medical-hold release operation; resolution must use the existing injury lifecycle and a new episode cannot reuse old checkpoint data.

## Storage, migration and remaining gate

`supabase/migrations/20261005215205_add_achilles_progression_observations.sql` adds one event type to `public.injury_episode_events` and extends `record_injury_episode_event`. It contains no clinical protocol branch: it validates the common envelope, exact owned current episode/side, aware timestamps, server-read injury text context and server-derived concern boolean. Registered service code owns typed payload validation, canonical profile applicability and concern interpretation. It uses the existing append-only observation table, history index, owner RLS and service RPC; clinical data never enters completion/exposure rows. Apply this migration through the normal release process before deploying the API. This PR does not apply it to a hosted database or deploy the service.

All 64 clinical profiles, hashes, live identities and CALM/RESTORE prescriptions are unchanged. The current rationalisation audit lists the four captured assessment inputs for Achilles only, separately from clinical functional checkpoints. Only the four nonclinical catalog declarations were added; no profile changed. The #2742 review remains a dated snapshot with its original capture state and original production fingerprints; its generator explicitly uses that snapshot's empty capture registry and continues checking bank/profile/archive/surface/completion fingerprints. Its snapshot comparison excludes only validated nonclinical input declarations when reconstructing the original pathway-file hash; all original catalog/profile content remains protected. Its historical progression-runtime fingerprint remains recorded, but is no longer a constraint preventing this authorized reader implementation.

Before RESTORE → LOAD can activate, the next review must source and approve the exact clinical criterion, site-specific interpretation, acceptable assessment provenance/verification, pathology exclusion, functional/range/load adequacy and symptom/delayed-response interpretation, including any required freshness rule. No threshold is invented here. LOAD/DYNAMIC/RETURN remain closed and zero production transitions become promotable.

Verification covers real authenticated capture/consent, retries, strict input validation, exact attribution, source differences, latest unknown snapshots, setbacks, no proxy measurements, medical holds/Today execution, and all-profile baseline invariants. The rewritten SQL migration was applied twice and exercised in a disposable real PostgreSQL 17 database. All 16 migration/concurrency tests passed, including a synthetic protocol payload using the same discriminator, exact episode/side/context/future rejection, retry conflicts, concern revision updates and service-only privileges. Full Supabase/PostgREST integration and deployment are not verified locally.

## Revision of #2743

Shared infrastructure: `RehabProgressionAssessment`, `AssessmentProtocol`, `AssessmentContext`, exact ownership/side, protocol/profile applicability, aware timestamps, episode start, latest whole snapshot per kind, complete history, later setbacks, server provenance, deterministic `as_of`, and persistent concern routing. Injury/episode IDs remain in the existing outer request/event; athlete ID and recording time are server-owned. The concrete API schema currently accepts only `AchillesProgressionAssessment`, whose payload remains `AchillesProgressionInput`.

Final discriminator: `rehab_progression_assessment`. Only supported clinical kind: `achilles_tendon_progression_v1`; schema version 1, protocol version 1. Heel-rise, tendon site, loading/delayed symptoms, permitted range/resistance, tolerance and pathology concerns remain Achilles-specific. A future protocol registers its typed envelope/payload, applicability, input reader, observation-time adapter and concern adapter, and adds catalog declarations/API schema membership; it reuses the writer, SQL discriminator, exact attribution, provenance, context/setbacks and input-availability engine branch. No elbow/ankle protocol is implemented. A synthetic fixture proves this boundary only in tests.

Medical concerns are computed from the registered payload by trusted service code and persisted as `medical_concern`. The common RPC updates the injury revision on a newly inserted concern, never on a retry. Readers re-evaluate all exact protocol concerns and route them through `progression_assessment_medical_hold` and the existing medical gate/clearance hierarchy. Later reassuring reports/clearance do not clear them. Frozen prescriptions are unchanged.

Migration state was checked read-only on 6 October 2026: connected project `leienvqynijrgghhzczt` and its branch inventory, migration history, live RPC definition and event constraint all showed the #2743 migration absent. Therefore the existing unmerged `20261005215205` migration was rewritten, with no forward migration. No hosted schema was changed.

API types are regenerated by `python tools/generate_api_types.py`. `submitInjuryEpisodeObservation` now takes the generated request type rather than a duplicate handwritten event union. No capture UI or clinical measurement is invented.

The next PR must source and define the actual Achilles RESTORE → LOAD clinical criterion, including interpretation and acceptable provenance. LOAD, DYNAMIC and RETURN remain closed; input records do not activate them.

Validation also covers pathway equivalence, all-profile hashes, surface/archive regressions, completion/exposure/frozen semantics, Today and multi-injury holds. `test_generated_types_match_the_api_schema` passes; enum rendering is now sorted because equivalent Python Literal aliases can expose different member orders depending on imports. Web typecheck and ESLint pass (52 existing warnings); Python Ruff/import/diff checks pass.

The previously observed filler failure (`test_live_wrapper_counts_meaningful_coverage_from_other_scheduled_week`) reproduces unchanged on PR base Main commit `9ca8b48e4db3a88a8b649b40bb7d5282ce66a21b`. The fallback authoritative-dose test passes locally on both the revised branch and that base; its earlier CI failure is not reproduced locally. These generation modules remain unchanged. Hosted PostgREST integration, deployment and clinician sign-off are not verified by this PR.
