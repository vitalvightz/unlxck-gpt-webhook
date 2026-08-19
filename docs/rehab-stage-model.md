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
| Six-week-old ankle, trained on without complaint, early camp | GPP — early, basic | Well tolerated. `load` or beyond. |

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

## Evidence the resolver uses

Everything comes from records that already exist. No new representation of pain,
severity, injury status or history was introduced.

| Source | Fields | Used for |
| --- | --- | --- |
| `injury_flags` | `severity`, `status`, `latest_reported_status`, `created_at`, `body_area`/`description` | per-injury state, onset, urgency, surface routing |
| prior `injury_flags` | `status`, `resolved_at`, `body_area` | detecting a cleared injury that has been re-reported |
| `today_checkins` | `active_injury`, `pain`, `recommendation_state`, the seven `SAFETY_FLAGS` | tolerated vs. worsening days, red-flag gate |
| `session_completions` | `status`, `pain_after` | the only record of tolerated load |
| `today_checkins.phase` | — | **deliberately never read** |

Red-flag toggles come from `api.contracts.checkin_decision.SAFETY_FLAGS`, urgent
injury vocabulary from `fightcamp.injury_taxonomy.derive_urgent_injury_tokens()`,
surface routing from `classify_injury_surface`, and the tolerated-pain floor from
`injury_signal.ELEVATED_PAIN_AFTER`. Every one is the project's existing
canonical source.

## Progression

The ladder is cumulative: each rung is only tested once every rung beneath it is
met, which is what makes skipping a stage structurally impossible rather than
merely discouraged.

| Rung | Requires |
| --- | --- |
| `restore` | ≥1 tolerated check-in day after onset |
| `load` | severity not `severe`, ≥3 tolerated days, ≥1 tolerated session |
| `dynamic` | severity `mild`, reported improving/resolved, ≥6 tolerated days, ≥3 tolerated sessions |
| `return` | reported resolved, ≥5 tolerated sessions |

A *tolerated day* is a submitted check-in with no worsening signal on it. A
*tolerated session* is a completed session with a recorded `pain_after` below the
elevated mark.

The rules the spec asked for fall out of that shape:

* **Time alone never progresses.** The counters count submitted reports, not
  days elapsed. A 60-day-old injury with no check-ins is `calm`.
* **Camp phase never progresses.** It is not an input.
* **No multi-stage jumps.** You cannot have six tolerated days without having had
  three.
* **One good day is not capacity.** `restore` is the most a single day buys.
* **Silence is not tolerance.** Days without a check-in are not counted; a
  completed session with no pain reading is not counted; a *failed history read*
  falls back to `calm` rather than to "nothing bad reported".
* **The onset day does not count.** A check-in filed the day an injury is
  reported says nothing about how it has since held up.

## Regression

A setback applies a **cap**. A cap is a ceiling, never a floor: it can only pull
a stage down, so a worsening report can never be the reason an injury moves up.

| Signal | Cap |
| --- | --- |
| `latest_reported_status == "worse"`, or one worsening day in the recent window | `restore` |
| Two or more worsening days in the recent window | `calm` |
| Any of the above with `severity == "severe"` | `calm` |
| Cleared and re-reported within 14 days | `calm` |

A worsening day is a check-in reporting `active_injury: worse`, `pain: high`, a
`pull_back` recommendation, or any red-flag toggle — deliberately broad, because
over-including in the *regression* direction is the safe error.

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
says so, in machine-readable codes: `insufficient_progression_evidence`,
`no_checkin_history_since_onset`, `no_session_tolerance_recorded`,
`injury_onset_unknown`.

The evidence floors (3 days, 6 days, 1/3/5 sessions) are **architectural
minimums, not clinical criteria** — how many independent reports the system
insists on seeing before it will describe tissue as tolerating more. Nothing
asserts a healing timeline or a return-to-sport clearance.

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
flag id, and a left ankle at `restore` and a right shoulder at `load` are both
true at once. Each decision reads only its own flag's facts; the shared
day-level history applies identically to all of them, so clearing one injury
changes nothing about another, and a worsening shoulder does not gate a separate
ankle.

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
* **PR4** makes stage-aware candidate scoring authoritative for selection.

Until then, rehab drill selection is exactly what it was. Null drill stages do
not filter anything out, `rehab_protocols` does not import the resolver, and a
test asserts the module never will in PR2.
