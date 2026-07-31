# Block 4 — UX Hierarchy Addendum

## Status

**Contract lock — read before building any Today/Overview UI.**

The top-level navigation hierarchy is approved:

| Tab        | Role                                  |
| ---------- | ------------------------------------- |
| Overview   | Camp status (read-only mirror)        |
| Today      | Decision + execution                  |
| Plan       | Full map                              |
| Intake     | Setup                                 |

The hierarchy was **not fully locked** because several product contracts were
missing. This addendum captures those contracts so we do not rework the
Today/Overview UI after building it.

Do **not** implement new Today/Overview UI until the rules below are honoured.
This document is the human-readable contract; where an executable contract is
named, the UI and API must use that module rather than open-coding the rule.
It extends — and where noted, refines — `docs/live-athlete-flow.md`.

---

## 1) State-dependent landing

The app landing target depends on user state. The landing resolver is the
single source of truth for "where does the athlete go when they open the app".

The table is ordered from most-specific to most-generic state. The resolver
evaluates rows **top-to-bottom and the first matching row wins**, so specific
session states must sit above the broader check-in states.

| # | User state                                   | Landing target                                                        |
| - | -------------------------------------------- | --------------------------------------------------------------------- |
| 1 | No active plan                               | Intake / Create Plan empty state                                      |
| 2 | New / cold user **with** an active plan      | Overview                                                              |
| 3 | Session **started but unfinished**           | Resume session (Today, resuming the in-progress session)             |
| 4 | Session **completed today**                  | Keep normal navigation / last tab                                     |
| 5 | Returning user, **already checked in** today | Today                                                                 |
| 6 | Returning user, **no** check-in today        | Overview with one dominant **"Check in / Open Today"** CTA            |

Rules:

- "Today" for landing purposes is the athlete's **local training day** as
  defined in §3 (timezone + `day_rollover_hour`), not the UTC calendar day.
- "Returning vs cold" is about whether the athlete has interacted before, not
  about plan freshness. A cold user always lands on Overview (orientation
  first); a returning user is routed toward the next decision.
- Exactly **one** dominant CTA is allowed in the "no check-in today" state. Do
  not present competing primary actions.
- **Precedence is unambiguous — first matching row wins:**
  - the **session-resume** state (row 3) beats any check-in state (rows 5–6);
  - the **completed-session** state (row 4) beats the generic checked-in state
    (row 5);
  - because session states (rows 3–4) sit above check-in states (rows 5–6), a
    returning user who has already checked in today never shadows an unfinished
    or completed session for today.

---

## 2) Overview is read-only

Overview **mirrors state only**.

- Overview MUST NOT contain the check-in form.
- **Today is the only place** where check-in input is collected and where the
  recommendation is produced.
- Overview MAY display the **latest valid** recommendation (subject to the TTL
  in §3) and route the athlete to Today.
- Any action on Overview that would change state is a **navigation** to Today
  (or another tab), never an inline mutation.

Rationale: separating the read model (Overview) from the write/decision surface
(Today) keeps Overview cheap to render, safe to cache, and resilient to plan
schema changes (§7).

---

## 3) Recommendation TTL and day-boundary

A recommendation is valid only for the athlete's **local training day**.

- Use the **athlete's timezone**.
- Use `day_rollover_hour = 03:00` local time.
- The training day for a timestamp `t` is the local calendar date of
  `t - 3h` (i.e. 00:00–02:59 local still belongs to the previous training day).
- After rollover, the previous recommendation **expires** and recommendation
  state returns to `not_checked_in`.
- **Never** show yesterday's recommendation as today's live readiness.

Display rule:

- An expired recommendation may be shown only as clearly-labelled **history**,
  never as the current/live readiness state.
- `recommendation_state` defaults to `not_checked_in` whenever no valid
  recommendation exists for the current training day.

Reconciliation with `docs/live-athlete-flow.md`:

- That doc currently describes check-in upsert keyed by **UTC day**. This
  addendum supersedes that for the recommendation/landing layer: the
  **training day** (athlete-local, 03:00 rollover) is the key used to decide
  recommendation validity, landing state, and completion-record `training_day`.
  Storage may remain UTC-backed, but the training-day derivation above is the
  contract used by the UI and decision logic.

---

## 4) Check-in decision table v1

The check-in produces one of three decisions. The decision is computed by a
single deterministic evaluator (the **executable contract** for this section)
so the API, Today UI, and tests share one implementation. The UI must not
re-derive the decision.

### Inputs

| Input              | Values                                        |
| ------------------ | --------------------------------------------- |
| `sleep`            | `poor` / `okay` / `good`                      |
| `body`             | `flat` / `normal` / `sharp`                   |
| `pain`             | `none` / `manageable` / `high`                |
| `phase`            | `GPP` / `SPP` / `TAPER` / `REINTEGRATION`     |
| `active_injury`    | `none` / `stable` / `worse`                   |
| `previous_session` | `none` / `normal` / `very_hard`               |

### Outputs

- `train_as_planned`
- `modify`
- `pull_back`

### Hard overrides (evaluated first; any match ⇒ `pull_back`)

These dominate all other rules and phase bias:

- `pain = high`
- `active_injury = worse`
- sharp pain / instability / swelling / neurological symptoms
- illness symptoms
- cannot warm into movement
- previous session caused **worse next-day pain**

> Note: several hard-override signals (instability, swelling, neurological
> symptoms, illness, cannot-warm-in, worse-next-day-pain) are **safety flags**
> beyond the six structured inputs above. Today must collect them (e.g. as
> check-in safety toggles) so the override can fire. They are red-flag inputs,
> not derived from sleep/body/pain alone.

### Normal rules (evaluated after overrides do not fire)

- `good`/`okay` sleep + `sharp`/`normal` body + no pain → `train_as_planned`
- `poor` sleep → `modify`
- `flat` body → `modify`
- `manageable` pain → `modify`
- `poor` sleep + `flat` body + `manageable` pain →
  - `pull_back` in **TAPER** / **REINTEGRATION**
  - otherwise `modify`
- `high` pain → `pull_back` (also covered by hard override)

When multiple normal rules match, the **most conservative** outcome wins
(`pull_back` > `modify` > `train_as_planned`).

### Phase bias

- **GPP** — allows more work if pain-free.
- **SPP** — modifies sooner when fatigue or pain appears.
- **TAPER** — conservative; must **not** chase fatigue (never escalate volume to
  "make up" for a poor day).
- **REINTEGRATION** — conservative; pain/instability dominates.

Phase bias may make a decision **more** conservative; it must never override a
hard `pull_back`, and it must never upgrade a `pull_back`/`modify` to
`train_as_planned`.

### Reason strings

- Reason strings are **generated from the triggered inputs** (which rule/inputs
  fired), not selected from random canned explanations.
- Each decision carries a `recommendation_reason` derived from the specific
  inputs/flags that triggered it (e.g. "Poor sleep + flat body in taper").
- The reason is stored on the recommendation and surfaced verbatim on Today
  (and as read-only history on Overview).

---

## 5) Completion state (must exist before or inside Today)

Today needs a **thin completion model immediately**. Block-level logging can
wait, but the completion record cannot — Today's "session completed today"
landing (§1) and the `completion_status` in the command view (§7) depend on it.

### Completion status values

- `not_started`
- `started`
- `done`
- `modified`
- `skipped`

### Minimum fields

| Field                | Notes                                                   |
| -------------------- | ------------------------------------------------------- |
| `user_id`            | owner                                                   |
| `plan_id`            | plan the session belongs to                             |
| `session_id`         | the session being completed                             |
| `training_day`       | athlete-local training day (§3), `YYYY-MM-DD`           |
| `status`            | one of the values above                                 |
| `session_rpe`        | session RPE                                             |
| `pain_after`         | pain after session                                      |
| `modification_reason`| why the session was modified (when `status = modified`) |
| `notes`              | free text                                               |
| `started_at`         | timestamp                                               |
| `completed_at`       | timestamp                                               |

Rules:

- One completion record per `(user_id, session_id, training_day)`.
- `started` requires `started_at`; `done`/`modified` require `completed_at`.
- `modified` should carry a `modification_reason`.
- Completion is the signal that drives the "session started but unfinished"
  (`started`) and "session completed today" (`done`/`modified`/`skipped`)
  landing states in §1.

---

## 6) Risk-watch governance

- Show a maximum of **2 visible risks**, then **"+N more"**.
- Risks are ordered by the priority below; the two highest-priority risks are
  the visible ones.

### Priority order

1. stop / pull-back red flags
2. active injury worsening
3. high pain
4. weight-cut caution
5. phase / taper caution
6. poor sleep / fatigue
7. general reminders

### Encoding

- Do **not** encode risk by **colour alone**.
- Every risk uses **icon + label + short text + colour** so meaning survives for
  colour-blind users, greyscale, and screen readers.

---

## 7) Normalized command-view contract

Overview MUST NOT parse raw `structured_plan` directly. Instead it reads a
**normalized command view / read model**. This protects Overview from
`structured_plan` schema changes (and aligns with the `structured_plan`
display-payload separation already noted in `docs/state_machine.md`).

### Shape

```json
{
  "active_plan": {},
  "today": {
    "training_day": "YYYY-MM-DD",
    "recommendation_state": "not_checked_in",
    "recommendation_reason": null,
    "next_session": {},
    "completion_status": "not_started"
  },
  "risk_watch": [],
  "week_summary": {},
  "quick_actions": []
}
```

### Field contract

- `active_plan` — minimal plan identity/summary; not the full structured plan.
- `today.training_day` — athlete-local training day (§3).
- `today.recommendation_state` — `not_checked_in` until a valid recommendation
  exists for the current training day (§3); otherwise the decision from §4
  (`train_as_planned` / `modify` / `pull_back`).
- `today.recommendation_reason` — generated reason string (§4), or `null`.
- `today.next_session` — the session Today will execute against.
- `today.completion_status` — one of the §5 status values.
- `risk_watch` — ordered list per §6 (already prioritised; consumer renders the
  top 2 + "+N more").
- `week_summary` — read-only week roll-up for Overview.
- `quick_actions` — declarative navigation actions (e.g. "Open Today"); per §2
  these are routes, not inline mutations.

Rules:

- Overview consumes only this view. If a field is missing, Overview degrades
  gracefully (empty state) rather than reaching into `structured_plan`.
- The command view is **derived** state. It is built from the persisted plan +
  recommendation + completion records; it is not a new source of truth.

---

## Out of scope (Block 4)

- adaptive plan mutation
- wearable readiness scores
- full calendar rewrite
- coach dashboard
- nutrition tracker
- social / marketplace features

## Goal

Lock these contracts **before** building Today/Overview UI so we avoid rework.
