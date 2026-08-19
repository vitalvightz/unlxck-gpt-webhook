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
| `injury_flags` | `severity`, `status`, `latest_reported_status`, `created_at`, `updated_at`, `body_area`/`description` | per-injury state, onset, follow-up, urgency, surface routing |
| prior `injury_flags` | `status`, `resolved_at`, `body_area` | detecting a cleared injury that has been re-reported |

**Whole-athlete** — nothing here can say *which* injury it belongs to. A
comfortable shoulder session is not evidence that an ankle tolerated load. These
may only ever move a stage **down**, or gate it on medical grounds.

| Source | Fields | Used for |
| --- | --- | --- |
| `today_checkins` | `active_injury`, `pain`, `recommendation_state`, the seven `SAFETY_FLAGS` | red-flag gate, worsening days |
| `session_completions` | `status`, `pain_after` | high post-session pain as a worsening day |
| `today_checkins.phase` | — | **deliberately never read** |

That split is enforced structurally, not by convention. Progression is computed
by `_progress`, which takes an `InjuryEvidence` and has no access to
`AthleteDayContext` at all — the same trick that keeps camp phase out. A test
asserts the signature, and another asserts that adding *any* amount of
whole-athlete history can never raise a resolved stage.

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
* **Silence is not tolerance.** A same-day edit is not a follow-up; a session
  with no pain reading proves nothing; a *failed history read* falls back to
  `calm` rather than to "nothing bad reported".

## Regression

A setback applies a **cap**. A cap is a ceiling, never a floor: it can only pull
a stage down, so a worsening report can never be the reason an injury moves up.

| Signal | Cap |
| --- | --- |
| `latest_reported_status == "worse"`, or one worsening day in the recent window | `restore` |
| Two or more worsening days in the recent window | `calm` |
| Either of the above with `severity == "severe"` | `calm` |
| `severity == "severe"` on its own | `calm` |
| Cleared and re-reported within 14 days | `calm` |

A worsening day is a check-in reporting `active_injury: worse`, `pain: high`, a
`pull_back` recommendation, or any red-flag toggle — or a completed session
logged at or above `HIGH_PAIN_AFTER`. Deliberately broad, because over-including
in the *regression* direction is the safe error, and because a cap can only ever
hold a stage down. That is exactly what makes it safe to read a whole-athlete
worsening against every open injury: the worst it can do is be over-protective.

The windows this uses (three most recent reported days, two of them worsening to
count as repeated, a fourteen-day re-report window) govern regression and
identity only. None of them can raise a stage, so none functions as a
rehabilitation criterion.

When the cap bites, it becomes the whole explanation: the rungs the evidence had
reached are no longer why the athlete is where they are, and
`symptoms_not_worsening` is never reported next to `injury_reported_worse`.

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

An urgent injury or a red-flag check-in pins the stage to `calm` and sets
`medical_gate=True`. A perfect tolerance history cannot talk a suspected fracture
into `return`: the gate is evaluated before the ladder is ever consulted, and the
existing urgent handling — not the stage — decides what happens next. The stage
carries no permission to train.

## Multiple injuries

There is no athlete-level stage. `resolve_rehab_stages` returns one decision per
flag id, and a left ankle at `restore` and a right shoulder at `calm` are both
true at once.

Isolation is the point. Each decision reads progression evidence only from its
own flag, so a settled shoulder cannot lift an unreported ankle — not even six
settled injuries can out-vote one unsettled one. The whole-athlete context is
shared, and safely so: it can only gate or lower a stage, never raise one.
Clearing one injury changes nothing about another, and a worsening shoulder does
not gate a separate settled ankle.

## Surface injuries

Skin wounds are not on the ladder. A cut, graze, abrasion, blister or laceration
resolves to `stage=None`, `care_pathway="wound_care"`, reason
`surface_injury_wound_care_pathway`, and never reports a transition. The existing
surface pathway and its danger gates are untouched.

## Derived, not stored

There is no rehab-stage column, deliberately: a stored stage is a second source
of truth that drifts from the injury record the moment a flag is edited, cleared
or re-reported. Every call recomputes from the authoritative history.

`progressed` / `regressed` are derived the same way — the resolver replays itself
over the evidence *as it stood before today's check-in* and compares ranks. No
transition log, no migration, and refresh/retry is idempotent by construction: a
pure function cannot accumulate progression.

## Not in this PR

* **PR3** migrates the rehab bank's clinical content, including the drill-level
  `rehab_stage` values PR1 left `null`.
* **PR4** adds the per-injury exposure record that `load`, `dynamic` and
  `return` require, and makes stage-aware candidate scoring authoritative for
  selection.

Until then, rehab drill selection is exactly what it was. Null drill stages do
not filter anything out, `rehab_protocols` does not import the resolver, and a
test asserts the module never will in PR2.
