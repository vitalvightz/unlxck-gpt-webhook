# Wiring rehab completion to injury evidence

PR3 built the evidence model. This is the gate in front of it: given the rehab
work in a completed session, it decides which drills may become a
`RehabExposureEvent` — and says plainly why the rest may not.

## Two different questions

| Asked | Answers | Where it lives |
| --- | --- | --- |
| "How was the session?" | difficulty, instructions, plan accuracy, comment | existing session feedback, unchanged |
| "How did **this injury** respond to **this rehab exposure**?" | during-response, reduce/stop | `api/contracts/rehab_completion.py` |

They stay separate concepts. General session feedback is programming feedback;
it is not injury evidence and cannot become any.

## The pipeline

```
completed rehab drill
    ↓  rehab_drill_options_for_phase()      canonical bank drill_id, not a display name
resolve canonical injury_id + episode_id
    ↓  resolve_rehab_exposure_candidate()   refuses rather than guesses
resolve drill demand metadata
    ↓
capture actual completed dose
    ↓  completed_dose_from_session()        completion semantics, not the prescription
ask injury-specific response
    ↓  build_rehab_response_prompts()       one prompt per injury, named
POST canonical RehabExposureEvent
    ↓  exposure_response_from_answers()
store append-only evidence                  PR3's validated RPC
```

## Identity, not display names

Rehab reached the athlete as rendered text (`"Name – notes"`), and the canonical
bank `id` was dropped at the `_rehab_drills_for_phase` boundary, which returns
`list[str]`. Matching a completed item back by display name would be exactly the
fragile string matching this must avoid — and Stage 2 rewrites that text anyway.

`rehab_drill_options_for_phase()` now returns each option as
`{"line", "drill", "location", "type"}`, keeping the bank drill (and its `id`
and `target_regions`) attached. `_rehab_drills_for_phase()` is a thin wrapper
over it, so the two cannot diverge and the rendered text is unchanged — verified
byte-identical across all 3,159 location × type × phase × limit cases.

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
| `demand_unknown` | the drill's load/impact/velocity are unreviewed |

All reasons are collected in one pass, so the whole gap is visible at once
rather than one blocker at a time.

## The demand gap blocks every drill today

**No drill in the shipped bank can currently be logged.** `ExposureDemand`
requires `load`, `impact` and `velocity`, and PR3 deliberately left all three
`null` on all 1,434 musculoskeletal drills — its own migration says so:

> A bank group already owns its canonical anatomical region. Carrying that
> identity onto the drill is defensible; all more specific clinical fields stay
> explicitly unknown until reviewed.

So the pipeline is complete and every drill stops at `demand_unknown`. Filling
those levels here would be inventing clinical classification — the exact failure
this pipeline exists to prevent. Closing the gap is a data question:

* review demand for the bank (or a subset), **or**
* add `"unknown"` to the three demand enums so evidence can flow with demand
  honestly marked unreviewed, mirroring how PR3 already models
  `contraction_type`, `sport_specificity`, `contact_level` and `side`.

That decision is deliberately not made here.

## Dose honesty

The session model records completion, not per-drill dose editing. So:

| Completion | Recorded |
| --- | --- |
| `done` | `completed_fraction: 1.0` |
| `modified` | `stopped_early: true`, fraction left unstated |

A prescribed `3x10` is **never** echoed back as a completed `3x10`. Marking a
session done is not the athlete confirming every rep, and the dose the tissue
actually saw is not something this layer knows. The prescription is carried
separately in `prescribed_dose`, and only where the session actually states one.

## The injury-specific question

Raised only when the session contained attributable rehab work, so a normal
training session never shows it. One prompt per injury, addressed by name,
however many drills targeted it:

```
LEFT ANKLE
  How did it feel during the rehab work?      better / same / worse / not_sure
  Did you have to reduce or stop because of it?   no / reduced / stopped
```

Fixed vocabularies, no free text, and no request for mechanism, diagnosis or
interpretation.

### How the answers map

`during_response` is a new field on `ExposureResponse`, mirroring
`next_day_response` minus `not_yet_known` (which cannot apply to something
already done) and plus `not_reported`.

| Answer | Recorded |
| --- | --- |
| during = better/same/worse/not_sure | `during_response` verbatim |
| during = worse | `worsening_reported: true` |
| during = better/same | `worsening_reported: false` |
| during = not_sure | `worsening_reported` left unset — unsure is not "no" |
| limit = stopped | `stopped_due_to_symptoms: true` |
| limit = reduced | `stopped_due_to_symptoms: false`, dose `stopped_early: true` |
| limit = no | both false |
| unanswered | `during_response: not_reported`, flags unset |

Two things it deliberately does not do:

* **No pain score is manufactured.** A better/same/worse answer is not a 0-10
  reading, so `pain_during` and `pain_immediate_after` stay `null`.
* **"Reduced" is not "stopped".** Cutting work short is a real and different
  observation, carried on the dose rather than collapsed into the stop flag.

`not_reported` is the default at the contract *and* database boundary, so an
exposure logged without asking is never stored as "the athlete said nothing was
wrong". Absence of an answer and an answer of "same" stay distinguishable.

## Not in this PR

Nothing here interprets an observation. No code decides whether an exposure was
*tolerated*, and nothing can move a rehab stage: `MAX_RESOLVABLE_STAGE` is still
`restore`, and LOAD / DYNAMIC / RETURN remain unreachable. Tests assert both.
