# Rehabilitation stage vs. camp phase

**Rehabilitation stage now represents injury recovery state, while GPP/SPP/TAPER
represents fight-camp periodisation. Camp phase cannot advance rehabilitation
stage.**

## Before and after

Before, one axis carried both meanings. The rehab bank keys its drills on
`phase_progression` (`"GPP → SPP"`), its notes read as a recovery arc
(`"GPP: Rebuild proprioception → SPP: Progress to dynamic balance under
fatigue"`), and `combine_three_phase_drills` walked that arrow as if it were a
rehab ladder — handing drill 1 to the first phase and drill 2 to the second. So
"where the athlete is in camp" and "what the tissue tolerates" were the same
number.

That is wrong in both directions:

| Situation | Old reading | Actual state |
| --- | --- | --- |
| Ankle sprained in fight week | TAPER — late, advanced | Brand new. `calm`. |
| Six-week-old ankle the athlete keeps reporting as improving, early camp | GPP — early, basic | Settling. `restore`. |

After, they are two independent axes:

```
REHAB STAGE   what can this tissue tolerate?      calm → restore → load → dynamic → return
CAMP PHASE    where is the athlete in camp?       GPP → SPP → TAPER
```

Camp phase keeps its job — dose and fatigue exposure — and loses the one it
should never have had.

## Why camp phase cannot affect the stage

Not by rule, by construction: **camp phase is not a parameter of
`resolve_rehab_stage`.** There is no argument to ignore and no branch to audit.
The `phase` column that exists on `today_checkins` rows is never read, and a test
permutes it across every check-in in the history to prove the resolved stage and
its reasons are byte-identical.

The stage vocabulary is PR1's `fightcamp.rehab_schema.REHAB_STAGES` — imported,
not restated. `api.models.RehabStage` derives its `Literal` from the same tuple,
so the API schema cannot drift from the enum either.

## Where it lives

| Concern | Owner |
| --- | --- |
| Stage vocabulary | `fightcamp/rehab_schema.py` (PR1) |
| Resolution | `api/contracts/rehab_stage.py` |
| Exposure on Today | `api/services/today_service.py` (`_with_rehab_stage`) |
| API shape | `api/models.py` (`InjuryFlagRecord.rehab_stage`) |

`api/contracts/` is where the project already keeps pure, storage-agnostic,
deterministic logic over plain mappings (`injury_checkin`, `injury_signal`,
`recommendation`), which is exactly what this is.

## Two kinds of evidence, and only one may progress

Everything comes from records that already exist. No new representation of pain,
severity, injury status or history was introduced. But those records fall into
two categories that must never be confused.

**Injury-specific** — facts about *this* injury, from its own flag row. Only
these may move a stage **up**.

| Source | Fields | Used for |
| --- | --- | --- |
| `injury_flags` | `severity`, `status`, `latest_reported_status`, `created_at`, `body_area`/`description` | per-injury state, onset, follow-up, urgency, surface routing |
| prior `injury_flags` | `status`, `resolved_at`, `body_area` | detecting a cleared injury that has been re-reported |

**Whole-athlete** — nothing here can say *which* injury it belongs to. **It
moves no stage, in either direction.**

| Source | Fields | Used for |
| --- | --- | --- |
| `today_checkins` | the seven `SAFETY_FLAGS` | raising `medical_gate` |
| `today_checkins` | `active_injury`, `pain`, `recommendation_state` | reported on the decision for explainability; never applied to it |
| `session_completions` | `status`, `pain_after` | same — reported, never applied |
| `today_checkins.phase` | — | **deliberately never read** |

Both halves of that matter. A comfortable shoulder session is not evidence that
an ankle tolerated load — and a flaring shoulder is not evidence that the ankle
went backwards. Stage is tissue state, so every movement in it, up or down,
needs evidence attributable to that tissue.

The split is structural, not conventional: the stage is computed by `_progress`,
which takes an `InjuryEvidence` and has no access to `AthleteDayContext` at all
— the same trick that keeps camp phase out. Tests assert the signature, and
assert that adding *any* amount of whole-athlete history — good or bad — leaves
the resolved stage untouched.

Red-flag toggles come from `api.contracts.checkin_decision.SAFETY_FLAGS`, urgent
injury vocabulary from `fightcamp.injury_taxonomy.derive_urgent_injury_tokens()`,
surface routing from `classify_injury_surface`, and the high post-session pain
mark from `injury_signal.HIGH_PAIN_AFTER`. Every one is the project's existing
canonical source.

## Progression, and where the ladder stops

The ladder is cumulative: each rung is only tested once every rung beneath it is
met, which is what makes skipping a stage structurally impossible rather than
merely discouraged.

| Rung | Requires | Reachable in PR2 |
| --- | --- | --- |
| `restore` | this injury reported on again since onset, not worsening, not `severe` | yes |
| `load` | that *this tissue* tolerated progressive load | no |
| `dynamic` | that *this tissue* tolerated speed and impact | no |
| `return` | that *this tissue* is near unrestricted sport | no |

**There are no count thresholds.** A number of "good days" or "good sessions"
required before an injury may be loaded is a rehabilitation criterion, and PR2
does not write those. Reaching `restore` needs a per-injury follow-up report —
either the flag sits in `monitoring`/`resolved` (a status only an
`improving`/`resolved` report produces) or it was written again on a later day.

`load`, `dynamic` and `return` all assert that the injured tissue tolerated
something, and **no such record exists**: nothing in the system ties an exposure
to a body area. So the ladder stops at `MAX_RESOLVABLE_STAGE` (`restore`) and
says why, with `insufficient_injury_specific_progression_evidence`. PR4 raises
that ceiling once a per-injury exposure record exists.

The rules the spec asked for fall out of that shape:

* **Time alone never progresses.** A 60-day-old injury nobody has reported on is
  `calm`.
* **Camp phase never progresses.** It is not an input.
* **A comfortable athlete never progresses an injury.** Thirty days of perfect
  check-ins and pain-free sessions leave an unreported ankle at `calm`.
* **No multi-stage jumps.** `restore` is the most any evidence currently buys.
* **Silence is not tolerance.** A follow-up is proven only by a non-default
  `latest_reported_status` (`improving`/`worse`/`resolved`) — the athlete's own
  per-injury daily report. A generic `updated_at` bump is not one, nor is an
  intake-seeded `monitoring` status; both can happen without the athlete
  reassessing the tissue.

## Holding at `calm`, and the `regressed` flag

Some injury-attributable signals hold an injury at `calm` — the most protective
stage — instead of letting it reach `restore`. Every one is read off the
injury's own flag row:

| Signal | Stage |
| --- | --- |
| `latest_reported_status == "worse"` | `calm` |
| `severity == "severe"` | `calm` |
| Cleared and re-reported within 14 days | `calm` |
| Urgent injury type in this flag's own text | `calm`, `medical_gate` |

There is no whole-athlete setback path. An earlier revision let a count of bad
*days* cap every open injury, which meant a flaring shoulder could drag a
settled ankle backwards — the same contamination as the progression bug, in the
other direction. It is gone: whole-athlete context moves no stage at all.

**A hold at `calm` is not reported as a regression.** The record stores no prior
rehab stage, so a first `worse` or `severe` follow-up that leaves an injury at
`calm` is `calm → calm` — nothing proves the tissue was ever above `calm`, and a
`worse` report cannot even reconstruct its own prior state (it resets `status`
to `open`). So `regressed` is never inferred in PR2; PR4, which stores a
per-injury stage, is where a real `restore → calm` step down becomes provable.

`symptoms_not_worsening` is never reported next to `injury_reported_worse`, and
an injury that has been followed up is never called `newly_reported_injury`
however protectively it is being held.

## Missing data

The repository does not record several things that a full rehab model would want,
and none of them were invented:

* **no per-injury day-by-day history** — `latest_reported_status` is a single
  overwritten column, so "this ankle worsened three days running" is only
  visible through athlete-level check-ins;
* **no per-injury pain score** — `today_checkins.pain` and
  `session_completions.pain_after` are whole-athlete readings;
* **no per-drill or per-region tolerance** — nothing records that *the injured
  tissue* tolerated the work;
* **no clinician clearance field** — there is nowhere to record that a
  professional cleared a return.

Where evidence is absent the resolver stays at the safest defensible stage and
says so, in machine-readable codes:
`insufficient_injury_specific_progression_evidence`,
`no_injury_specific_followup_report`, `newly_reported_injury`,
`injury_onset_unknown`.

An earlier revision of this PR bridged that gap with day and session counts
drawn from whole-athlete history. That was wrong twice over: it manufactured
tissue-specific evidence out of records that carry no body area, and the counts
themselves were de facto rehabilitation criteria. Both are gone.

## Safety precedence

```
RED FLAG / URGENT MEDICAL GATE     ← above the ladder
        ↓
INJURY SAFETY / TRAINING RESTRICTION
        ↓
REHAB STAGE                        ← this module
        ↓
REHAB EXERCISE SELECTION           ← unchanged in PR2 (PR3/PR4)
        ↓
CAMP-PHASE DOSE MODIFICATION
```

The two medical gates are not the same thing, and the difference is the point:

* an **urgent injury type** is read off *this* flag's own text, so it is
  attributable to this tissue and pins this injury to `calm` with
  `medical_gate=True`. A perfect record cannot talk a suspected fracture into
  training: the gate is evaluated before the ladder is consulted.
* a **red-flag check-in** is whole-athlete. It raises `medical_gate=True`, which
  blocks training and routes medical handling, but it leaves every stage at
  whatever that injury's own record supports. A sprained ankle plus a headache
  today is a gated day, not an ankle that suddenly went backwards.

Either way the existing urgent handling — not the stage — decides what happens
next. The stage carries no permission to train.

## Multiple injuries

There is no athlete-level stage. `resolve_rehab_stages` returns one decision per
flag id, and a left ankle at `restore` and a right shoulder at `calm` are both
true at once.

Isolation is the point, and it runs both ways. Each decision reads stage
evidence only from its own flag, so a settled shoulder cannot lift an unreported
ankle, and a flaring shoulder cannot drag a settled ankle down — not even six
injuries reported worse can out-vote one settled one. The whole-athlete context
is shared, and safely so: it changes no stage at all. Clearing one injury
changes nothing about another, and resolving an injury alone gives the same
decision as resolving it in a crowd.

## Surface injuries

Skin wounds are not on the ladder. A cut, graze, abrasion, blister or laceration
resolves to `stage=None`, `care_pathway="wound_care"`, reason
`surface_injury_wound_care_pathway`, and never reports a transition. The existing
surface pathway and its danger gates are untouched.

## Derived, not stored

There is no rehab-stage column, deliberately: a stored stage is a second source
of truth that drifts from the injury record the moment a flag is edited, cleared
or re-reported. Every call recomputes from the authoritative history.

`progressed` / `regressed` are derived too, and honestly bounded by what the
record can prove. The floor is definitional: every injury starts at `calm` with
nothing reported since onset, and a follow-up that lifts it off `calm` is a
provable move up from that floor. A move *down* is not — it would need a prior
higher stage, and nothing in the record stores one — so `regressed` is never
inferred here. No transition log, no migration, and refresh/retry is idempotent
by construction: a pure function cannot accumulate progression.

## Not in this PR

* **PR3** migrates the rehab bank's clinical content, including the drill-level
  `rehab_stage` values PR1 left `null`.
* **PR4** adds the per-injury exposure record that `load`, `dynamic` and
  `return` require, and makes stage-aware candidate scoring authoritative for
  selection.

Until then, rehab drill selection is exactly what it was. Null drill stages do
not filter anything out, `rehab_protocols` does not import the resolver, and a
test asserts the module never will in PR2.

## RESTORE → LOAD eligibility is blocked on the demand migration

PR4's `RESTORE -> LOAD` interpreter (`api/contracts/load_eligibility.py`) is
implemented and correct, but `LOAD_CRITERIA_REGISTRY` is deliberately empty and
must stay so until the rehab bank carries reviewed clinical **demand** metadata.

Every bank drill currently reports `load`, `impact` and `velocity` as `unknown`
(the values PR1 left `null`), so every recorded exposure is
`has_unknown_demand=True` and is excluded from LOAD qualification. A criterion
added now — however carefully written — could therefore never return `eligible`:
`load in ["low", "moderate"]` cannot match a demand that is always `unknown`.
The interpreter is right to keep returning `insufficient_evidence`; that
conservative answer is safer than inferring an unstated demand.

The order this must happen in:

1. Agree a fixed clinical demand taxonomy (`load` / `impact` / `velocity` /
   `contraction_type` / `target_tissues` value sets).
2. Review and classify each drill's real demand — never guessed by the backend.
   Unknown stays unknown.
3. Migrate the reviewed values into the production bank.
4. Validate coverage: `tests/test_load_criteria_registry_coverage.py` requires
   every enabled criterion to be backed by at least one real drill whose
   reviewed demand can satisfy it, so a rule that can never fire cannot merge.
5. Only then add injury-specific criteria; the interpreter can finally
   distinguish *supports progression* / *does not support* / *insufficient*.

The missing demand migration — not a shortage of criteria — is the
production-readiness blocker for any claim of evidence-based injury progression
from exercise exposure.
