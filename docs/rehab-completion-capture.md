# Wiring rehab completion to injury evidence

PR3 built the evidence model. This is the path an athlete actually walks to fill
it: a completed session containing rehab becomes an injury-specific question,
and the answer becomes one immutable, attributable observation.

## Two different questions

| Asked | Answers | Where it lives |
| --- | --- | --- |
| "How was the session?" | difficulty, instructions, plan accuracy, comment | existing session feedback, unchanged |
| "How did **this injury** respond to **this rehab exposure**?" | during-response, reduce/stop | `api/contracts/rehab_completion.py` |

They stay separate concepts and separate screens. General session feedback is
programming feedback; it is not injury evidence and cannot become any.

## The pipeline

```
plan generation
    ↓  reconcile_rehab_drill_ids()          stamps the canonical bank id on rehab blocks
session marked done / modified
    ↓  session_rehab_items()                reads ids + stable block occurrence; never a display name
resolve canonical injury_id + episode_id
    ↓  resolve_rehab_exposure_candidate()   refuses rather than guesses
capture actual completed dose
    ↓  completed_dose_from_session()        completion semantics, not the prescription
ask injury-specific response
    ↓  build_rehab_response_prompts()       one prompt per injury, named
POST /api/today/rehab-responses
    ↓  record_rehab_exposures()             re-resolves everything but the answers
store append-only evidence                  PR3's validated RPC
```

## Identity, not display names

Rehab reaches the athlete as rendered text (`"Name – notes"`), and the canonical
bank `id` used to be dropped at the `_rehab_drills_for_phase` boundary, which
returns `list[str]`. Matching a completed item back by display name would be
exactly the fragile string matching this must avoid — and Stage 2 rewrites that
text anyway.

`rehab_drill_options_for_phase()` now returns each option as
`{"line", "drill", "location", "type"}`, keeping the bank drill (and its `id`
and `target_regions`) attached. `_rehab_drills_for_phase()` is a thin wrapper
over it, so the two cannot diverge and the rendered text is unchanged — verified
byte-identical across all 3,159 location × type × phase × limit cases. The id
then rides into Stage 2's candidate pool as `rehab_drill_id`.

### Why the id is resolved server-side

The markdown→JSON conversion never sees `candidate_pools` — the prompt drops
them, deliberately, because the full brief is 100k+ characters. So the model
converting a plan cannot carry the id itself, however the schema is shaped.

`reconcile_rehab_drill_ids()` therefore resolves it once, deterministically,
against that plan's own option set, and stores it on the block. This is the one
place a display name goes anywhere near rehab identity, and it is bounded: an
exact normalized-name match, against the handful of options actually offered for
this plan, accepted only when exactly one option matches. Everything downstream
reads the stored id.

Anything that does not resolve is left `None` — a rewritten name, an ambiguous
one, a non-rehab block. The completion gate then reports `not_rehab_work` and
writes nothing, which is the right answer: an unidentifiable drill is not proof
that a particular tissue did particular work.

## Refusing is the point

An exposure asserts "this specific tissue did this specific work". Every part
must be known. When any is not, the resolver returns a code and writes nothing:

| Code | Meaning |
| --- | --- |
| `not_rehab_work` | no canonical bank id or target region — not loggable rehab |
| `not_completed` | the athlete did not do any of it |
| `attribution_unknown` | no open injury matches the drill's region |
| `multiple_possible_injuries` | more than one does, and nothing says which |
| `laterality_unknown` | region matches but side does not resolve |
| `episode_unknown` | no episode identity, so evidence could not be isolated |

All reasons are collected in one pass, so the whole gap is visible at once
rather than one blocker at a time.

## Unreviewed demand is recordable, and is not capacity evidence

PR3 migrated `target_regions` onto the bank and left `load`, `impact` and
`velocity` explicitly unreviewed on all 1,434 musculoskeletal drills — "all more
specific clinical fields stay explicitly unknown until reviewed".

That is a gap in *how much* the work demanded, not in *whose* tissue did it. It
does not break attribution, so it does not block the exposure. All three enums
accept `"unknown"` — in the Python contract, the rehab schema and validator, and
the RPC's own validation — and `_resolve_demand()` records exactly that. An
unrecognised value in the bank also reads as `"unknown"` rather than being
accepted, so a malformed row cannot be laundered into a demand claim.

What an unknown level must never do is count as *positive* evidence of capacity:
"demand not stated" is not "demand was low".
`RehabExposureEvent.has_unknown_demand` marks those events, and PR4 must exclude
them from LOAD / DYNAMIC / RETURN qualification rather than reading an unstated
demand as a low one.

## Dose honesty

The session model records completion, not per-drill dose editing. So:

| Completion | Recorded |
| --- | --- |
| `done` | `completion_state: performed_amount_unknown` |
| `modified` | `completion_state: partial_amount_unknown` |
| athlete says "reduced" | partial amount unknown, `stopped_early: true`, not stopped due to symptoms |
| athlete says "stopped" | partial amount unknown, `stopped_early: true`, stopped due to symptoms |

A prescribed `3x10` is **never** echoed back as a completed `3x10`. Marking a
session done is not the athlete confirming every rep, and the dose the tissue
actually saw is not something this layer knows. The prescription is carried
separately in `prescribed_dose`, read from the block and only where it states a
plain number — a rep range is dropped rather than collapsed to one of its ends.
`completed_fraction` remains unset unless a future drill-level capture explicitly
quantifies it.

## The injury-specific question

Raised only when the session contained attributable rehab work, so a normal
training session never shows it. One prompt per injury, addressed by name,
however many drills targeted it:

```
LEFT ANKLE
  How did it feel during the rehab work?      better / same / worse / not_sure
  Did you have to reduce or stop because of it?   no / reduced / stopped
```

Fixed vocabularies shipped by the server with the question, no free text, and no
request for mechanism, diagnosis or interpretation. Skipping is real: an
unanswered injury records nothing, where a default "same" would be a report the
athlete never made.

### How the answers map

`during_response` is a field on `ExposureResponse`, mirroring `next_day_response`
minus `not_yet_known` (which cannot apply to something already done) and plus
`not_reported`.

| Answer | Recorded |
| --- | --- |
| during = better/same/worse/not_sure | `during_response` verbatim |
| limit = stopped | `stopped_due_to_symptoms: true` |
| limit = reduced | `stopped_due_to_symptoms: false`, dose `stopped_early: true` |
| limit = no | both false |
| unanswered | `during_response: not_reported`, flags unset |

Three things it deliberately does not do:

* **No pain score is manufactured.** A better/same/worse answer is not a 0-10
  reading, so `pain_during` and `pain_immediate_after` stay `null`.
* **"Reduced" is not "stopped".** Cutting work short is a real and different
  observation, carried on the dose rather than collapsed into the stop flag.
* **`worse` does not set `worsening_reported`.** A `worse` answer is an
  observation about *this exposure*; `worsening_reported` is liable to be read
  as a broader injury-status setback. Promoting one to the other would let a
  single uncomfortable drill read as the injury itself going backwards.
  `during_response` stays the authoritative record of what was actually said.

`not_reported` is the default at the contract *and* database boundary, so an
exposure logged without asking is never stored as "the athlete said nothing was
wrong". Absence of an answer and an answer of "same" stay distinguishable.

## The submission carries answers, and only answers

`POST /api/today/rehab-responses` takes `plan_id`, `session_id`, an optional
`training_day` and a list of `{injury_id, during_response, limit_response}`. It
takes no drill, no episode, no side and no demand — the model forbids extra
fields outright.

Every one of those is recomputed server-side from the stored plan and the
athlete's injury record, by the same resolution that produced the prompts. A
client cannot assert an attribution it was not given, and an answer for an
injury the session had no attributable rehab for is ignored rather than stored.

The completion is also bound to that exact plan before resolution. A completion
whose `plan_id` differs from the requested, athlete-owned plan is rejected with
no evidence write, even if `session_id` and `training_day` happen to match.

Exposure ids are derived from (athlete, plan, episode, session, training day,
rehab occurrence, drill). The preferred occurrence key is the structured
block's stable `block_id`. Legacy blocks without one use a content fingerprint
that excludes presentation order, with deterministic suffixes for exact stored
duplicates. Two blocks may therefore use the same drill and still produce two
exposures, while retrying either block reuses its original id. Reordering blocks
does not change identity when `block_id` is stable.

`occurred_at` / `recorded_at` come from the training day rather than the clock,
so the whole event remains a pure function of its inputs. A retry or a double
submit re-sends an identical payload under an identical id, and PR3's RPC
returns the existing row instead of appending a second observation.

## Not in this PR

Nothing here interprets an observation. No code decides whether an exposure was
*tolerated*, and nothing can move a rehab stage: `MAX_RESOLVABLE_STAGE` is still
`restore`, and LOAD / DYNAMIC / RETURN remain unreachable. Tests assert both.
