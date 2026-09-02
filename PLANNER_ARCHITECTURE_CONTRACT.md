# Planner Architecture Contract

Status: **closed and frozen** (Step 10). This document defines ownership boundaries for planner decisions and, as of Step 10, describes the architecture that exists in `Main` today rather than a migration target. The staged migration (Steps 0-9B) is complete: every planner decision listed below has exactly one canonical owner.

Section 3 is the canonical ownership matrix. Section 9 records what the migration removed and the small non-blocking debt that remains. Section 12 states the architecture freeze rule that governs future change.

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
| Normal-camp day placement | `stage2_role_map.py`, `normal_calendar_placement.py` | `stage2_role_map.py` (`_assign_declared_day_hints`) + placement-owned completion (`normal_calendar_placement.py`) | Later integrity pass may reject or relocate only through shared calendar policy | Renderer assigning dayless roles; payload post-processing creating a second placement algorithm (Step 9A removed the dead `stage2_payload.py` boxing placement engine and its `_assign_declared_day_hints` duplicate) |
| Late-fight day placement | `stage2_payload_late_fight.py` (`_build_late_fight_session_sequence`), `late_fight_tail.py` (finished-tail reuse) | `stage2_payload_late_fight.py` | Tail reuse preserves finished placement | Normal fillers re-place tail-owned sessions |
| Hard-sparring adjacency / collision legality | `stage2_role_map.py`, `stage2_payload_late_fight.py`, `gap_fill_inserts.py` | `combat_load_policy.py` (shared calendar legality), consumed via the `calendar_context.py` adapter by both placement owners and the fillers (Step 9B) | Owners generate candidate days/slots and query the policy; fillers query legality before inserting; final governor re-validates | Any layer re-deciding ALLOW/DEPRIORITIZE/FORBID with its own hard-contact spacing doctrine |
| Crowded-week compression | `stage2_role_map.py`, `stage2_payload.py` | `stage2_role_map.py` | `stage2_payload.py` may decorate governance only | Re-compressing an already-compressed week in a second layer |
| Sandwiched-day protection | `stage2_role_map.py`, `stage2_payload.py` | `combat_load_policy.py` (between-effective-hard-contact legality); the normal allocator's structural glycolytic suppression queries it via `calendar_context` (Step 9B) | Owner keeps only its role-budget suppression *scope* and no-legal-slot action | Re-deriving a local `sandwiched` legality verdict; separate preference vs prohibition implementations for the same collision |
| Intentionally unused training days | `stage2_role_map.py`, post-processing | allocator/calendar layer | Recovery conversion only through explicit low-load support policy | Renderer automatically filling unused days |
| Missing-day completion | `normal_calendar_placement.py` (`fill_missing_session_days`) | Normal calendar placement / allocator-owned completion | Fills a surviving dayless role only onto a day the shared `combat_load_policy` does not FORBID; renderer may display the assigned day | Renderer implementing or independently choosing a missing day (the Step 8 renderer re-export is deleted); completion committing a forbidden day |
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

Current Main executes the normal dated-camp planning brief as follows:

```text
build athlete model / candidate pools
  -> build limiter + sport load + weekly stress map
  -> build week-by-week progression
  -> stage2_role_map._build_weekly_role_map
       (role budget/compression, then _assign_declared_day_hints placement
        through shared combat_load_policy legality)
  -> normal_calendar_placement.fill_missing_session_days
       (placement completion, same shared legality)
  -> apply_camp_week_fillers            (support inserts, gated by shared legality)
  -> splice finished D-13 tail when applicable
  -> apply_late_camp_role_morph
       (countdown dose, then apply_final_calendar_integrity — the governor is the
        last deterministic stage and re-runs dose-only morph if it relocates a role)
  -> stamp labels
  -> build finalizer handoff
```

The governor is deliberately the final deterministic stage: every layer that can
mutate the calendar (placement, completion, fillers, dose morph) runs before it.
Changes must still be reviewed against this whole chain, not only
`stage2_role_map.py`.

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

`stage2_payload_late_fight.py` owns late-fight placement: it constructs the countdown `session_sequence` directly (`_build_late_fight_session_sequence` plus `ensure_declared_coach_combat_spine` / the visible-calendar sequence). `late_fight_tail.py` owns reuse of the finished D-13 -> D-1 path inside a longer camp. The normal planner must not re-place tail-owned sessions after handoff. (Step 9A: a separate `late_fight_placement.py` engine existed but had no production caller — the sequence was always built by `stage2_payload_late_fight.py` — so it was removed.)

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
- New late-fight placement rules belong in `stage2_payload_late_fight.py` (the live late-fight placement owner).
- New countdown dose-reduction rules belong in `late_camp_role_morph.py` / the canonical countdown dosage policy.
- New filler types belong in the filler library, but their placement must use the shared legality contract.
- New rendering copy belongs in rendering/label modules and must describe existing state only.
- New finalizer rules may constrain wording or compliant exercise substitution but must not compensate for deterministic calendar defects.

Specifically prohibited as new architecture:
- new planner behaviour in `weekly_plan_render.py`;
- new independent hard-spar spacing logic in `stage2_payload.py`;
- new `*_patch.py` forwarding layers for behaviour that can be placed in an existing canonical owner;
- prompt-only fixes for deterministic scheduling defects.

## 9. Migration record and remaining debt

### 9.1 Canonical ownership summary

The staged migration (Steps 0-9B) is complete. Every decision below has exactly one
canonical owner in `Main` today:

| Decision | Canonical owner |
| --- | --- |
| Sparring / effective contact resolution (hard, reduced, technical, off) | `sparring_dose_planner.py` |
| Normal-camp role budget, compression, suppression | `stage2_role_map.py` |
| Late-fight role budget / permission | `stage2_payload_late_fight.py` (permission + budget path) |
| Normal-camp day placement | `stage2_role_map.py` (`_assign_declared_day_hints`) + `normal_calendar_placement.py` (completion) |
| Late-fight countdown placement | `stage2_payload_late_fight.py` |
| Combat collision legality (ALLOW / DEPRIORITIZE / FORBID) | `combat_load_policy.py` |
| Canonical calendar-event representation | `calendar_context.py` (representation only — never a verdict) |
| Countdown dose morph | `late_camp_role_morph.py` |
| Support inserts / fillers | `camp_week_fillers.py`, `gap_fill_inserts.py` — subordinate to shared legality |
| Final deterministic calendar legality | `calendar_integrity.py` |
| Rendering | `weekly_plan_render.py` — read only |
| AI finalizer | wording / compliant exercise expression only |
| Validation & release | validator / release layer — never repairs architecture |

Both placement owners consume the same `combat_load_policy` legality through
`calendar_context`, and both consume the sparring resolver's own resolved contact
state. They remain **separate sequencing owners** — candidate generation, anchors,
countdown targets and tie-breaking are local — but they cannot disagree about
legality. Chronological positions are weekday indices (normal camp, monday=0) and
`-countdown_offset` (late fight); raw D-day numbers are never used as positions.

### 9.2 Historical migration notes

Recorded only to explain architecture that no longer exists, so a future reader does
not reintroduce it:

1. **Renderer placement (removed, Step 4/8).** `weekly_plan_render.py` once inferred
   weekdays for dayless roles. It is now read-only: `_resolve_role_weekdays` reads the
   placement-assigned `scheduled_day_hint` and the compatibility re-export is deleted. A
   role the placement layer leaves dayless renders without a weekday.
2. **Duplicate sandwiched-day allow-list (removed, Step 6).** `stage2_payload.py` kept
   its own list of loads legal between two effective hard contacts; it now defers the
   verdict to `combat_load_policy`.
3. **Wrapper chain (removed, Step 7).** `stage2_role_map_patch.py` ->
   `stage2_role_map_integration.py` forwarding is collapsed; `stage2_role_map.py` calls
   `allocator_priority.py` directly and both wrapper modules are deleted.
4. **Dead placement engines (removed, Step 9A).** The `stage2_payload.py` boxing
   placement engine (`_boxing_*` / `_main_job_day_class` / `_sort_roles_by_scheduled_day`),
   its duplicate `_assign_declared_day_hints` + `_declared_day_sets`, and the whole
   `late_fight_placement.py` module had no production caller and were deleted. The
   countdown sequence was always built by `stage2_payload_late_fight.py`.
5. **Placement collision doctrine (unified, Step 9B).** Both surviving placement owners
   now consume `combat_load_policy`. Normal camp evaluates every physical candidate day
   through `calendar_context.normal_week_legality`; the late-fight slot scorers rank
   assignments by the lexicographic legality key `(-forbid, -deprioritize, owner_score)`,
   so no owner preference can outrank canonical legality. FORBID means *unavailable*: a
   role with no legal day is left to the owner's existing dayless/suppression contract
   rather than being placed illegally.
6. **Second sparring resolver in placement (removed, Step 9B follow-up).** Late-fight
   placement reconstructed hard-vs-technical from `role_key` + countdown offset. It now
   consumes `resolve_late_fight_contacts` — the sparring resolver's authoritative
   `(countdown_offset, effective_load)` output, the same source the gap fillers use —
   preserving the full hard / reduced / technical / off vocabulary.
7. **Resolver authority (fixed, Step 9B).** A supplied `hard_sparring_plan` is
   authoritative even when it resolves to zero effective hard contact. Declared hard days
   stand in **only** when the plan is `None` (the resolver did not run); an empty or
   fully-downgraded plan never resurrects declared hard days.

### 9.3 Remaining non-blocking debt

These are real but do not affect decision ownership, and are explicitly **not** scheduled
work (see the freeze rule in section 12):

1. `camp_week_fillers.py` / `camp_week_fillers_impl.py` remain a facade/implementation
   pair. The facade holds real orchestration (tail splicing, tactical-watch insertion), so
   it is not pure indirection and was not collapsed. Ownership is unambiguous: filler
   selection is the filler layer's, legality is `combat_load_policy`'s.
2. `stage2_finalizer_packet.py` / `_impl.py` are likewise a facade/implementation pair
   holding real packet-building logic. Same conclusion.
3. `stage2_payload.py` remains a large compatibility/orchestration surface. Its dead
   placement policy is gone; what remains is orchestration and re-exports.
4. `weekly_schedule_view.py` normalises resolver `status` -> display `effective_load` for
   the API/validator view layer. This is presentation-side normalisation of resolver
   output, downstream of every planner decision; it is not a second contact authority.


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

## 11. Achieved convergence

The migration's goal was not a rewrite; it was to reduce the number of writers to planner
state. As of Step 10 the convergence below is **achieved**, not aspirational:

```text
stage2_planning_brief.py
    owns intent

sparring_dose_planner.py
    owns effective contact load

stage2_role_map.py + shared calendar legality
    own normal role budget and placement

stage2_payload_late_fight.py
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

## 12. Architecture freeze rule (Step 10)

**After Step 10, planner architecture refactors are closed by default.**

The staged migration achieved its goal: one canonical owner per decision, one collision
legality doctrine, one contact resolver, a final governor, and a read-only renderer.
Further structural change now costs more than it returns, and each refactor risks
reintroducing the multi-writer bugs the migration removed.

New architecture work requires **one** of the following, stated explicitly in the PR:

1. a demonstrated production correctness defect that cannot be fixed inside an existing
   canonical owner;
2. a new feature that genuinely cannot be implemented within existing ownership;
3. measured performance/scalability evidence that requires a structural change.

"Another abstraction would be cleaner" is **not** a sufficient reason.

### Where new work belongs

New features enter through the existing owners:

| New work | Enters through |
| --- | --- |
| New injury constraint | athlete model / role budget / canonical legality, as appropriate |
| New combat contact type | `sparring_dose_planner` (resolution) + `combat_load_policy` (classification) |
| New readiness signal | athlete model / role budget / dose owner |
| New coach override | an explicit deterministic owner (never the renderer or finalizer) |
| New filler type | filler library + shared legality |
| New rendering | renderer only, read-only |
| New collision rule | `combat_load_policy` only |

### Specifically prohibited

- a second module that returns ALLOW / DEPRIORITIZE / FORBID;
- a second placement engine, or a generic "planner manager" / orchestrator over the
  existing owners;
- new `*_patch.py` / `*_integration.py` forwarding layers;
- another calendar abstraction or another role classifier;
- re-deriving effective contact from declared weekdays, role keys, or countdown
  thresholds when resolved sparring state is available;
- moving placement, contact, or role-survival authority into the renderer, the AI
  finalizer, or the validator.

The architecture regressions in `tests/test_step10_architecture_closure.py` and
`tests/test_placement_ownership.py` enforce this. A change that requires editing the
canonical legality matrix in those tests is, by definition, a change to training
collision doctrine and must be argued as such — not slipped in as a refactor.
