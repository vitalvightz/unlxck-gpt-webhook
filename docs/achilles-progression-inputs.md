# Achilles progression input contract

This adds capture and readers for `achilles_tendonitis`, using the missing inputs identified in the #2742 review. LOAD stays closed; `achilles_tendonitis_eccentric_calf_drops_on_step` stays dormant. No clinical transition, threshold, profile, dose, bank identity or hash changes.

## Write and read paths

The future injury check-in UI submits the existing authenticated `POST /api/today/injury-episode-observation` endpoint with `event_type: "achilles_progression_input"`. Health-feature consent is required. Use the server-issued injury and episode IDs and the episode's exact side; do not ask the athlete to select a different episode or side. Unknown values can be omitted except the required side, assessment timestamp and assessor. Do not instruct an athlete to perform an assessment through this API; it records an assessment that actually occurred.

Example body (illustrative observations, **not a prescription or readiness rule**):

```json
{
  "injury_id": "22222222-2222-4222-8222-222222222222",
  "injury_episode_id": "33333333-3333-4333-8333-333333333333",
  "event_type": "achilles_progression_input",
  "report_id": "44444444-4444-4444-8444-444444444444",
  "assessment": {
    "side": "left",
    "assessed_at": "2026-10-05T15:00:00Z",
    "assessor": "clinician_physio",
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
```

The server returns the persisted episode-event object, including `id`, server-owned `athlete_id`, `injury_id`, `injury_episode_id`, `created_at` and `payload`. The payload records `region: achilles`, `injury_type: tendonitis`, the complete normalized `assessment`, `source: athlete_reported`, `externally_verified: false` and server-read injury text context. Keep `report_id` stable for retries; changing the payload with the same ID returns 409. Send a new report ID for a new observation. Delayed answers require resubmitting the complete updated snapshot with a new report ID, preserving the actual loading/assessment times.

Today loads the existing episode-event history and exposes `open_injuries[].rehab_decision.achilles_input_checkpoints` only for an Achilles episode with captured inputs. Each entry has `status`, `reason_code`, observation ID, assessor, verification and clinical-promotion usability. `evaluate_transition` reads the same checkpoints when a requirement explicitly names one. Production profiles declare no such new requirements in this PR. Existing Today payloads and CALM/RESTORE behavior stay unchanged when no new observation exists.

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

All four IDs are registered by `api/contracts/achilles_progression.py` and exported through `CAPTURED_FUNCTIONAL_CHECKPOINTS`. They are scoped to this exact Achilles type; registering them adds no clinical criterion to any profile.

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

The newest recorded whole snapshot supersedes the older one, even if incomplete; no fallback to an older pass. All observation times must be within this episode and at/before recording, and recording cannot be in the future. The start is the first current-episode injury audit event, falling back to injury creation. Any later episode setback invalidates the earlier assessment/loading/delayed timestamps. Truncated exposure history is unknown. There is no arbitrary age limit, session count, elapsed-time readiness rule or clearance proxy; a clinically sourced freshness interval remains a future decision.

Safety concerns persist for the same episode even after a reassuring assessment or athlete-reported clearance. They feed the existing shared medical-hold and clinician-clearance hierarchy, stop Today training execution and withhold rehab prescriptions without diagnosing rupture. Concern capture updates the injury's revision timestamp atomically so a previously fetched unstarted prescription must be refreshed. Frozen prescription contents remain untouched. This narrow API has no medical-hold release operation; resolution must use the existing injury lifecycle and a new episode cannot reuse old checkpoint data.

## Storage, migration and remaining gate

`supabase/migrations/20261005215205_add_achilles_progression_observations.sql` adds one event type to `public.injury_episode_events` and extends `record_injury_episode_event`. It uses the existing append-only observation table, history index, owner RLS and service RPC; clinical data never enters completion/exposure rows. Apply this migration through the normal release process before deploying the API. This PR does not apply it to a hosted database or deploy the service.

All 64 clinical profiles, hashes, live identities and CALM/RESTORE prescriptions are unchanged. The current rationalisation audit now lists the four captured IDs for Achilles only. The #2742 review remains a dated snapshot with its original capture state and original production fingerprints; its generator explicitly uses that snapshot's empty capture registry and continues checking bank/profile/archive/surface/completion fingerprints. Its historical progression-runtime fingerprint remains recorded, but is no longer a constraint preventing this authorized reader implementation.

Before RESTORE → LOAD can activate, the next review must source and approve the exact clinical criterion, site-specific interpretation, acceptable assessment provenance/verification, pathology exclusion, functional/range/load adequacy and symptom/delayed-response interpretation, including any required freshness rule. No threshold is invented here. LOAD/DYNAMIC/RETURN remain closed and zero production transitions become promotable.

Verification covers real authenticated capture/consent, retries, strict input validation, exact attribution, source differences, latest unknown snapshots, setbacks, no proxy measurements, medical holds/Today execution, and all-profile baseline invariants. The SQL migration was compiled and exercised in an isolated PGlite PostgreSQL runtime for ownership/side/type/context/future rejection, retry conflicts, concern revision updates and service-only privileges. Full Supabase/PostgREST integration and deployment are not verified locally.
