# Planner Architecture Contract

Status: **current and closed after Step 10**. This contract describes the live
fight-camp planner. It is not a future migration plan and does not change
training doctrine.

## 1. Core rule

Every planner decision has exactly one canonical owner. A downstream layer may
consume, represent, decorate, dose-reduce through its own explicit contract, or
reject a decision. It must not independently re-decide that decision.

```text
athlete input
  -> athlete model
  -> phase / role intent
  -> sparring resolver (declared contact -> effective load)
  -> role budget (which app-owned roles survive)
  -> day / countdown placement
  -> countdown dose morph (how much, never where)
  -> optional support inserts through shared legality
  -> final calendar governor
  -> valid calendar
  -> read-only renderer
  -> AI finalizer (wording / permitted coaching expression)
  -> validator / release (validate, never repair architecture)
```

## 2. Current canonical ownership

| Decision | Canonical owner today | Permitted consumers | Forbidden secondary ownership |
| --- | --- | --- | --- |
| Raw input and athlete facts | `input_parsing.py`, runtime/planning-brief model builders | All planners read canonical fields | Reconstructing athlete intent from prose when structured truth exists |
| Phase and weekly stress intent | runtime/phase helpers and `stage2_planning_brief.py` | Role-budget owners | Fillers or renderers inventing intent |
| Declared contact -> hard/reduced/technical/off | `sparring_dose_planner.py` | Role maps, `calendar_context.py`, placement, fillers, governor | Re-resolution from a role key, countdown threshold, declared weekday, or display label |
| Normal app-owned role budget | `stage2_role_map.py` | Normal placement and later read-only consumers | Payload, filler, renderer, or finalizer restoring suppressed work |
| Late-fight app-owned role budget | `stage2_payload_late_fight.py` permission/budget path | Late-fight placement and later consumers | Normal planner or filler restoring compressed work |
| Normal-camp placement | `stage2_role_map._assign_declared_day_hints` plus `normal_calendar_placement.fill_missing_session_days` completion | Morph, governor, renderer | Payload, filler, renderer, finalizer, or validator running another normal placement engine |
| Late-fight placement | `stage2_payload_late_fight.py` | Finished-tail reuse and later consumers | Generic placement wrapper or normal planner re-placement |
| Collision legality and directive ordering | `combat_load_policy.py` | Placement owners, fillers, governor | Local ALLOW/DEPRIORITIZE/FORBID or hard-contact-spacing doctrine |
| Canonical calendar-event representation | `calendar_context.py` | Placement owners, fillers, governor | Representation adapters deciding legality |
| Scheduled-day countdown dose | `late_camp_role_morph.py` and canonical countdown dosage helpers | Governor and presentation | Dose code moving sessions; placement code absorbing dose doctrine |
| Camp-week support insertion | `camp_week_fillers.py` / `camp_week_fillers_impl.py` | Shared legality decides whether the proposed slot is legal | Meaningful stress beyond filler contract; moving anchors/contact; bypassing suppression |
| Late-fight gap insertion | `gap_fill_inserts.py` | Shared legality decides whether the proposed slot is legal | Independent physical-session scheduling or collision doctrine |
| Final deterministic legality | `calendar_integrity.py` | Renderer, finalizer packet, validation/release consume its result | Removing defence in depth because upstream placement already checks legality |
| Fight-day protocol / D-0 | `fight_day_override.py` | Render protocol only | Any training insertion or fallback on D-0 |
| D-14 / D-13 handoff | normal architecture through D-14; `stage2_payload_late_fight.py` and `late_fight_tail.py` from D-13 inward | `camp_week_fillers.py` may splice the finished tail | Normal placement rebuilding or reclaiming tail-owned sessions |
| Athlete-facing role labels | `role_labels.py` | Render/finalizer | Labels changing role, load, or placement truth |
| Renderer | `weekly_plan_render.py` (presentation only) | Reads deterministic state | Assigning weekdays, restoring/creating work, changing contact/load, or repairing a calendar |
| AI finalizer | Stage 2 finalizer boundary (wording, cues, and explicitly permitted same-role expression only) | Release validation | Role survival, day placement, contact state, collision repair, insertion, or D-0 override |
| Validator / release | `stage2_validator.py`, `plan_contract_validator.py`, `stage2_pipeline.py`, `stage2_policy.py`, `stage2_repair.py` | Report, retry, flag, or release | Becoming a scheduler or silently repairing planner architecture |

## 3. State ownership

Only placement may originate or relocate `scheduled_day_hint`,
`scheduled_countdown_label`, `countdown_offset`, `real_weekday`, or authoritative
session ordering. A support-insert owner may set these fields only on the new
support role it owns and only after shared legality permits the slot.

Only the sparring resolver and countdown dose owner may originate effective
contact state, `effective_hard_sparring_days`, `stress_class`, `cost_class`,
`meaningful_stress`, and countdown dose caps within their respective contracts.
A supplied resolved plan is authoritative even when it is empty or contains no
effective hard contact. Declared-day fallback is permitted only when resolver
state is unavailable (`hard_sparring_plan is None`), never when it is `[]`.

Only role-budget/compression owners write suppression and intentional-compression
state. Fillers, renderers, and finalizers must not restore it. Presentation may
write labels, explanations, coaching cues, and formatting without changing role
identity, load, dose ownership, or placement.

## 4. Production order and final authority

Normal dated-camp production order is:

```text
athlete model / candidate pools
  -> planning brief and weekly stress intent
  -> stage2_role_map role budget and declared-day placement
  -> normal_calendar_placement completion
  -> permitted support fillers through shared legality
  -> finished D-13 tail splice when applicable
  -> late_camp_role_morph
  -> calendar_integrity final governor
  -> labels/finalizer handoff/read-only rendering
  -> validation/release
```

D-13 inward uses the late-fight permission, budget, and live countdown sequence
in `stage2_payload_late_fight.py`. `late_fight_tail.py` preserves that finished
sequence when it is spliced into a longer camp. The final governor intentionally
runs after base placement, fillers, and dose morph. Upstream prevention plus
final enforcement is defence in depth, not duplicate policy ownership.

## 5. Mandatory invariants

1. Resolved effective contact outranks raw declarations and labels downstream.
2. Sparring remains coach-owned; classification may change dose, not invent a schedule.
3. ALLOW is preferred, DEPRIORITIZE is a legal fallback, and FORBID is unavailable.
4. Role survival, placement, and dose are separate decisions with separate owners.
5. Fillers are subordinate to the role budget and shared legality.
6. Post-placement morph changes dose, not calendar ownership.
7. D-0 is immutable and cannot become a training day.
8. D-13 tail ownership is immutable after handoff; D-14 remains normal-owned.
9. The renderer is read-only. A dayless role remains dayless.
10. The AI and validators cannot repair deterministic planner architecture.
11. Unknown or invalid deterministic state fails validation rather than gaining a fallback.
12. A compatibility facade may delegate but may not become a second policy owner.

## 6. Canonical legality contract

`combat_load_policy.py` owns the following established matrix. Tests freeze the
full directive and representative reason-code equivalence across normal-weekday
and late-fight-countdown representations.

| Context | Load | Directive |
| --- | --- | --- |
| Same-day exclusive physical/contact collision | Physical/contact | FORBID |
| Consecutive effective hard contact | Hard contact | FORBID |
| Between two effective hard contacts | Off, zero, recovery, low-load aerobic | ALLOW |
| Between two effective hard contacts | Low-load physical, technical contact, reduced contact | DEPRIORITIZE |
| Between two effective hard contacts | Meaningful strength/conditioning, neural microdose | FORBID |
| Immediately after hard contact | Meaningful strength/conditioning | FORBID |
| Immediately after hard contact | Neural microdose, reduced contact | DEPRIORITIZE |
| Immediately after hard contact | Technical, low-cost, recovery | ALLOW |
| Immediately before hard contact | Meaningful strength/conditioning, neural microdose, reduced contact | DEPRIORITIZE |
| Immediately before hard contact | Technical and low-cost work | ALLOW |

Normal and late-fight planners may rank otherwise-equivalent candidates by their
own sequencing preferences. They may not disagree on legality or let an owner
preference outrank the shared directive tier.

## 7. Compatibility and non-blocking debt

The Step 10 audit retained these compatibility surfaces deliberately:

- `camp_week_fillers.py` / `camp_week_fillers_impl.py`: the facade is part of the
  established import surface. Filler selection remains in this pair, but shared
  legality remains external and canonical. Removing the facade would add risk
  without improving decision ownership.
- `stage2_finalizer_packet.py` / `_impl.py`: the facade delegates packet building
  across an established boundary. It does not own calendar policy. Removing it
  would be compatibility cleanup, not architecture closure.
- `stage2_payload.py`: this remains a compatibility/orchestration surface with
  established post-processing responsibilities. Its dead boxing placement engine
  is gone. Broad consolidation would change trace shape and risk behaviour.
- `weekly_plan_render.py` may retain presentation helpers and stable imports, but
  it contains no missing-day completion or recovery placement.

These are trace-depth or compatibility debt, not duplicate live policy owners.
They should not be removed without separate characterization and a concrete need.

## 8. Historical migration notes

Steps 0-9 moved the planner from overlapping decision writers to the ownership
model above. The following removed paths must not return:

- `late_fight_placement.py` (dead duplicate engine);
- the dead boxing weekday-placement helper tree and duplicate
  `_assign_declared_day_hints` in `stage2_payload.py`;
- `stage2_role_map_patch.py` and `stage2_role_map_integration.py` forwarding layers;
- renderer-owned missing-day placement;
- Stage 2's local sandwiched-day legality allow-list.

Step 9B connected both surviving placement owners to `combat_load_policy.py` via
`calendar_context.py`. The #2406 follow-up made late-fight placement consume the
sparring resolver's authoritative `(countdown_offset, effective_load)` values,
preserving hard, reduced, technical, and off/suppressed states without
re-resolution.

## 9. Architecture freeze rule

After Step 10, architecture refactors are closed by default. New architecture
work requires at least one of:

1. a demonstrated production correctness defect;
2. a new feature that cannot be implemented within existing canonical ownership;
3. measured performance or scalability evidence requiring structural change.

Do not refactor merely because another abstraction looks cleaner. New features
enter through existing owners: injury constraints through athlete facts, role
budget, or canonical legality as appropriate; contact types through the sparring
resolver and combat-load classification; readiness through athlete facts, role
budget, or dose ownership; coach overrides through one explicit deterministic
owner; fillers through the filler library plus shared legality; and new rendering
through the renderer only.

No new planner manager, placement engine, policy wrapper, rule registry, calendar
abstraction, role classifier, `*_patch.py`, or `*_integration.py` may be introduced
without satisfying the freeze rule.

## 10. Review checklist

Every planner change must identify its decision and canonical owner, prove no
secondary writer is introduced, state whether it changes survival, placement,
load, dose, or presentation, preserve resolved-contact authority and the D-14 /
D-13 boundary, keep rendering and AI subordinate, and name focused regressions
covering the complete mutation chain.
