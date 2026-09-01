# Planner Architecture Contract

Status: architecture contract for the fight-camp planner. This document defines ownership boundaries for planner decisions. It is intentionally stricter than the current code layout where compatibility layers and post-processing still share responsibility.

This contract is documentation-only. It does not change runtime behaviour.

## 1. Core rule

Every planner decision must have exactly one canonical owner.

Downstream layers may:
- consume a decision;
- decorate it with labels, explanations, or metadata;
- reduce a dose when an explicitly-owned safety/countdown rule requires it;
- reject an invalid result during validation.

Downstream layers must not independently re-decide the same planning question.

The primary architecture smell this contract is designed to prevent is multiple writers to the same scheduling state.

## 2. End-to-end authority order

The intended authority chain is:

```text
athlete input
  -> canonical athlete model
  -> phase / role intent
  -> combat-contact load resolution
  -> role budget / survival
  -> day placement
  -> scheduled-day countdown dose morph
  -> optional support inserts through shared legality checks
  -> final calendar integrity check
  -> read-only rendering
  -> AI finalization of wording / exact compliant coaching detail
  -> validation / release policy
```

No lower layer may silently override a higher layer's ownership.

## 3. Decision ownership matrix

| Decision | Current implementation surfaces | Canonical owner | Allowed downstream behaviour | Forbidden downstream behaviour |
| --- | --- | --- | --- | --- |
| Parse raw planner input | `fightcamp/input_parsing.py`, `fightcamp/main.py` | `input_parsing.py` | Reject malformed input; carry parsing metadata | Reinterpret athlete intent later from free text when canonical fields exist |
| Injury triage mode | `fightcamp/injury_triage.py`, `fightcamp/main.py` | `injury_triage.py` | Carry restrictions/triage state downstream | Renderer/finalizer independently deciding whether a blocked plan may proceed |
| Canonical athlete/runtime model | `plan_pipeline_runtime.py`, `stage2_planning_brief.py`, `stage2_payload.py` | runtime + planning-brief model builders | Derive immutable planning facts from canonical input | Later scheduling code rebuilding conflicting athlete facts |
| Phase mapping | `plan_pipeline_runtime.py`, phase helpers | phase/runtime layer | Consume phase and countdown context | Session renderer inventing a different phase interpretation |
| Candidate exercise/drill selection pool | `plan_pipeline_blocks.py`, `strength.py`, `conditioning.py`, rehab modules | Stage 1 content-selection layer | Finalizer may choose a stronger compliant same-role candidate | Candidate-selection modules deciding calendar placement |
| Athlete priorities / limiter | `stage2_planning_brief.py`, `priority_profile.py`, goal-priority helpers | `stage2_planning_brief.py` + priority profile | Calendar allocator consumes priorities | Renderer/filler re-ranking athlete goals independently |
| Weekly stress intent | `stage2_planning_brief.py` | `stage2_planning_brief.py` | Role allocator converts intent to role slots | Fillers adding new meaningful stress because a week looks sparse |
| Declared contact ownership | `sparring_dose_planner.py`, `stage2_role_map.py`, `stage2_payload_late_fight.py` | `sparring_dose_planner.py` | Calendar allocator consumes resolved contact state | Other layers inferring hard-vs-technical from raw declared weekday alone |
| Effective contact load: hard / technical-only / deloaded / suppressed | `sparring_dose_planner.py`, late-fight logic, role-map logic | `sparring_dose_planner.py` | Countdown logic may request a dose transition through this contract | Compression/filler code treating every declared contact as hard load after resolution |
| Weekly role budget / which app-owned roles survive | `stage2_role_map.py`, `stage2_payload.py`, late-fight permission/budget code | Normal camp: `stage2_role_map.py`; D-13 inward: late-fight permission/budget path | Finalizer renders only surviving roles | Renderer/finalizer restoring suppressed roles to make a week look complete |
| Fight-week override | fight-week helpers, `fight_day_override.py`, late-fight payload | fight-week override layer; D-0 specifically `fight_day_override.py` | Remove/limit roles according to override | Generic allocator overriding D-0 or fight-week caps |
| Normal-camp day placement | `stage2_role_map.py`, `stage2_payload.py`, `normal_calendar_placement.py`, remaining renderer fallback | `stage2_role_map.py` + placement-owned completion | Later integrity pass may reject or relocate only through shared calendar policy | Renderer assigning dayless roles; payload post-processing creating a second placement algorithm |
| Late-fight day placement | `late_fight_placement.py`, `stage2_payload_late_fight.py` | `late_fight_placement.py` | Tail reuse preserves finished placement | Normal fillers re-place tail-owned sessions |
| Hard-sparring adjacency / collision legality | `stage2_role_map.py`, `stage2_payload.py`, `late_fight_placement.py`, `gap_fill_inserts.py` | Shared calendar legality policy to be introduced; until then allocator-specific placement layer is authoritative | Fillers query legality before inserting | Each layer maintaining its own incompatible hard-contact spacing doctrine |
| Crowded-week compression | `stage2_role_map.py`, `stage2_payload.py` | `stage2_role_map.py` | `stage2_payload.py` may decorate governance only | Re-compressing an already-compressed week in a second layer |
| Sandwiched-day protection | `stage2_role_map.py`, `stage2_payload.py` | Shared calendar legality policy; currently normal allocator | Suppress/relocate through one rule | Separate preference vs prohibition implementations for the same collision |
| Intentionally unused training days | `stage2_role_map.py`, post-processing | allocator/calendar layer | Recovery conversion only through explicit low-load support policy | Renderer automatically filling unused days |
| Missing-day completion | `normal_calendar_placement.py`; `weekly_plan_render.py` retains a temporary compatibility re-export only | Normal calendar placement / allocator-owned completion | Renderer may display the assigned day; compatibility imports may delegate to the owner | Renderer implementing or independently choosing a missing day |
| Camp-week support fillers | `camp_week_fillers.py`, `camp_week_fillers_impl.py` | support-insert layer, subordinate to shared calendar legality | Add only zero/low-cost support that passes budget and collision checks | Adding new meaningful stress or mutating authoritative anchor/contact placement |
| Late-fight gap fillers | `gap_fill_inserts.py` | support-insert layer, subordinate to late-fight placement + shared legality | Add permitted low-cost/tactical support to legal gaps | Functioning as an independent physical-session scheduler |
| Tactical Watch placement | `camp_week_fillers.py`, `gap_fill_inserts.py`, tactical watch library | support-insert layer | Zero-load coexistence where explicitly allowed | Consuming physical training budget unless policy says it should |
| Long-camp D-14 -> D-13 handoff | `camp_week_fillers.py`, `late_fight_tail.py` | `late_fight_tail.py` for finished tail; `camp_week_fillers.py` only splices it | Preserve tail metadata and finished sequence | Re-running normal placement inside D-13 -> D-1 |
| Scheduled-day late-camp dose morph | `late_camp_role_morph.py` | `late_camp_role_morph.py` | Reduce role dose/semantic load after D-day is known; record intent validation | Changing which calendar day owns the role or adding replacement stress silently |
| Strength taper dose | `late_camp_role_morph.py`, late-fight dosage helpers | Countdown dose policy | Reduce sets/reps/RPE and label accordingly | Normal renderer/finalizer inventing a harder dose than the cap |
| Conditioning taper dose | `late_camp_role_morph.py`, late-fight dosage helpers | Countdown dose policy | Morph hard fight-pace into low-cost rhythm where required | Retaining old `meaningful_stress` metadata after morph |
| Fight-day protocol | `fight_day_override.py`, renderer/finalizer rules | `fight_day_override.py` | Render protocol only | Any other layer scheduling S&C on D-0 |
| Athlete-facing role labels | `role_labels.py` | `role_labels.py` | Rename for display without changing semantic class | Labels changing load classification or placement |
| Stage 1 draft rendering | `plan_pipeline_rendering.py` | renderer | Describe deterministic state | Encode independent training doctrine that conflicts with deterministic scheduling |
| Finalizer packet | `stage2_finalizer_packet.py`, `_impl.py`, `stage2_llm_boundary.py` | finalizer boundary | Compact deterministic facts and hard rules | Omitting authoritative calendar facts then expecting the LLM to reconstruct them |
| AI finalizer | Stage 2 prompt / model boundary | AI only for exact compliant exercise choice, wording, and presentation inside deterministic structure | Improve specificity, replace violating candidate with same-role compliant option | Change session count, day ownership, contact status, fight-week caps, or deterministic safety decisions |
| Stage 2 validator | `stage2_validator.py`, `plan_contract_validator.py` | validator | Detect violations and report them | Becoming the primary scheduler or silently repairing calendar architecture |
| Release / retry policy | `stage2_pipeline.py`, `stage2_policy.py`, `stage2_repair.py` | release-policy layer | Decide publish/retry/flags using validator result | Redefine planner architecture to make a failing plan pass |

## 4. Current normal-camp execution order

Current Main executes the normal dated-camp planning brief approximately as follows:

```text
build athlete model / candidate pools
  -> build limiter + sport load + weekly stress map
  -> build week-by-week progression
  -> stage2_role_map._build_weekly_role_map
  -> boxing post-processing in stage2_payload
  -> normal_calendar_placement.fill_missing_session_days
  -> apply_camp_week_fillers
  -> splice finished D-13 tail when applicable
  -> apply_late_camp_role_morph
  -> stamp labels
  -> build finalizer handoff
```

This order is recorded because several current layers still mutate the calendar after the base allocator. Until the later consolidation steps are complete, changes must be reviewed against the full mutation chain, not only `stage2_role_map.py`.

## 5. Current late-fight execution ownership

D-13 inward is treated as a distinct planning path.

Its architecture should remain:

```text
permission
  -> role budget
  -> placement
  -> preserve declared combat spine
  -> permitted gap/support inserts
  -> visible calendar sequence
  -> finalizer
```

`late_fight_placement.py` owns late-fight placement. `late_fight_tail.py` owns reuse of the finished D-13 -> D-1 path inside a longer camp. The normal planner must not re-place tail-owned sessions after handoff.

## 6. State fields and who may write them

The following scheduling fields are treated as planner state, not presentation state.

### Placement-owned fields

Only the calendar allocator / placement layer may originate or relocate:
- `scheduled_day_hint`
- `scheduled_countdown_label`
- `countdown_offset`
- `real_weekday`
- authoritative session ordering / day ownership

Support inserts may create these fields only for the new support role they own, after a legality check. Renderers must be read-only.

### Load-owned fields

Combat-contact resolver and countdown dose policy own:
- effective hard-contact state
- `effective_hard_sparring_days`
- hard / technical-only / suppressed contact semantics
- `stress_class`
- `cost_class`
- `meaningful_stress`
- dose caps that arise from countdown safety

Other modules may read these fields but must not infer replacements from raw labels.

### Suppression-owned fields

Role-budget/compression owners write:
- `suppressed_roles`
- `intentional_compression`
- `intentionally_unused_days`
- session-count reduction reasons

Fillers and renderers must not restore a role that appears in the authoritative suppression state.

### Presentation-owned fields

Presentation layers may write:
- athlete-facing labels
- explanation text
- purpose/why-today wording
- display formatting

They must not use presentation fields to redefine role identity or load.

## 7. Mandatory invariants

These invariants apply to every future planner change.

1. **One owner per decision.** A new rule must modify the canonical owner, not create a parallel interpretation downstream.
2. **Declared contact is not synonymous with effective hard load.** All load-sensitive logic must consume resolved effective contact state.
3. **Rendering is read-only.** Rendering may not assign weekdays, restore sessions, add physical work, or alter load semantics.
4. **Fillers are subordinate.** A filler may not create meaningful training stress unless an explicit planner role budget requested that stress.
5. **Post-placement morphs reduce dose, not calendar ownership.** If a morph materially changes semantic load, final calendar integrity must be re-evaluated without silently adding replacement work.
6. **D-0 is immutable.** Fight-day protocol overrides every ordinary weekday role.
7. **D-13 tail ownership is immutable after handoff.** Normal-camp fillers may not rebuild the late-fight tail.
8. **The AI cannot repair deterministic architecture.** If the deterministic calendar is invalid, fix the deterministic planner.
9. **Validator findings do not authorize hidden planner changes.** Validator/release policy remains QA/release logic.
10. **No compatibility facade becomes a second source of truth.** Backward-compatible exports may delegate; they should not host divergent implementations of the same planning decision.

## 8. New-code placement rules

Until the architecture is consolidated further:

- New normal-camp placement rules belong in `stage2_role_map.py` or a shared calendar-policy module called by it.
- New hard-vs-technical contact semantics belong in `sparring_dose_planner.py`.
- New late-fight placement rules belong in `late_fight_placement.py`.
- New countdown dose-reduction rules belong in `late_camp_role_morph.py` / the canonical countdown dosage policy.
- New filler types belong in the filler library, but their placement must use the shared legality contract.
- New rendering copy belongs in rendering/label modules and must describe existing state only.
- New finalizer rules may constrain wording or compliant exercise substitution but must not compensate for deterministic calendar defects.

Specifically prohibited as new architecture:
- new planner behaviour in `weekly_plan_render.py`;
- new independent hard-spar spacing logic in `stage2_payload.py`;
- new `*_patch.py` forwarding layers for behaviour that can be placed in an existing canonical owner;
- prompt-only fixes for deterministic scheduling defects.

## 9. Known current exceptions / debt

The following current behaviour violates or partially violates the target contract and is recorded explicitly so it is not mistaken for desired architecture:

1. `stage2_payload.py` is both a compatibility facade/orchestrator and a host for real post-processing policy.
2. As of Step 8, `weekly_plan_render.py` is read-only: `_resolve_role_weekdays` reads each role's placement-assigned `scheduled_day_hint` and no longer infers weekdays for dayless roles. Day placement is owned entirely by the calendar/placement layer (`normal_calendar_placement.fill_missing_session_days` plus the allocator), which runs before rendering; a role the placement layer leaves dayless renders without a weekday instead of the renderer inventing one. This satisfies invariant 3 for the weekly renderer.
3. Normal-camp hard-contact collision policy is distributed across `stage2_role_map.py` and `stage2_payload.py`. As of Step 6, `stage2_payload.py` no longer keeps its own allow-list of loads legal between two effective hard contacts: its sandwiched-day suppression classifies roles through the shared `calendar_context` adapter and defers the between-hard-contacts verdict to `combat_load_policy.evaluate_calendar_candidate` (suppressing only a `FORBID`, so the policy's `DEPRIORITIZE` preference is no longer re-imposed as a local prohibition). The remaining distribution — `stage2_role_map.py`'s own inline glycolytic suppression and the boxing day-placement collision scoring still hosted in `stage2_payload.py` — is left for the placement-consolidation step (Step 9).
4. Late-fight collision policy is separately implemented in `late_fight_placement.py`.
5. `gap_fill_inserts.py` still owns filler selection/budget/variety, but as of Step 5 its calendar-collision legality defers to the shared `combat_load_policy` through the canonical `calendar_context` adapter, using resolved sparring state rather than raw declared weekday matching. Its remaining `existing_exclusive_offsets` / raw-day sets survive only as non-legality bookkeeping.
6. `camp_week_fillers.py` can add roles after the base allocator, but as of Step 5 each candidate is gated through the shared `combat_load_policy` (via `calendar_context`) against the whole weekly role map before insertion; it no longer derives effective contact from `declared_hard_sparring_days`.
6a. `calendar_context.py` is the single canonical `planner state -> CalendarEvent[]` adapter shared by the final `calendar_integrity` governor and the upstream fillers, so there is one interpretation of position, resolved contact, load class, scope and contact de-duplication. It is representation only; `combat_load_policy` remains the rule authority.
7. `late_camp_role_morph.py` changes semantic load after placement, so a future final calendar integrity layer must validate the resulting state.
8. Compatibility/adaptor layers that increase trace depth should be consolidated only after characterization tests protect behaviour. As of Step 7 the `stage2_role_map_patch.py` → `stage2_role_map_integration.py` forwarding chain is collapsed: `stage2_role_map.py` now calls `allocator_priority.py` directly (the `late_camp_week_reference_d_day` reference-day resolver moved there, next to the compression-floor helper it feeds), and both wrapper modules are deleted. The remaining such layers — `camp_week_fillers.py`/`_impl.py` and the finalizer facade/impl pairs — still await consolidation.

These are migration targets, not instructions to delete code immediately.

## 10. Required review checklist for planner PRs

Any PR changing planner behaviour should answer:

- What planning decision is changing?
- Which canonical owner from this contract owns that decision?
- Does another file currently implement the same decision?
- Does the change alter role survival, placement, load classification, dose, or presentation only?
- Can any downstream filler/post-processing pass undo the decision?
- Does the change use resolved effective contact state rather than raw declared hard-spar weekdays?
- Does it preserve the D-14 normal / D-13 late-fight ownership boundary?
- Does rendering remain read-only?
- Is the AI still subordinate to deterministic session count/day/safety state?
- Which characterization/regression fixtures prove the behaviour across the full mutation chain?

A planner PR should be treated as architecture-risky when it cannot identify one canonical owner for the behaviour it changes.

## 11. Migration direction

The target is not a rewrite. The target is to reduce the number of writers to planner state.

Preferred convergence:

```text
stage2_planning_brief.py
    owns intent

sparring_dose_planner.py
    owns effective contact load

stage2_role_map.py + shared calendar legality
    own normal role budget and placement

late_fight_placement.py
    owns D-13 inward placement using the same collision semantics

late_camp_role_morph.py
    owns scheduled-day dose reduction

support insert modules
    may only add legal subordinate support

final calendar integrity
    verifies the finished deterministic calendar

render/finalizer
    consume that calendar without rebuilding it
```

The architectural success condition is simple: for any athlete-facing session, a developer should be able to answer **why this role exists, why it survived, why it is on this day, what its effective load is, and which file has authority for each answer** without tracing competing implementations.
