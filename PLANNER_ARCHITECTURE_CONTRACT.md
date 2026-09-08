# Planner Architecture Contract

Status: **closed and frozen** (Step 10). This document defines ownership boundaries for planner decisions and, as of Step 10, describes the architecture that exists in `Main` today rather than a migration target. The staged migration (Steps 0-9B) is complete: every planner decision listed below has exactly one canonical owner.

Section 3 is the canonical ownership matrix and section 3.1 names the only layers that may withhold a plan. Section 9 records what the migration removed and the non-blocking debt that remains. Section 12 states the architecture freeze rule that governs future change.

The contract covers the whole chain, not just the calendar: Stage 1 selection and
placement, the closed session membership and effective dose built on top of it, the
Stage 2 handoff and AI finalization, release policy, and the structured-card
conversion that produces the athlete-facing view. `STAGE2_PAYLOAD_SPEC.md` describes
the payload/brief *shapes*; this document owns the *authority* over them.

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
  -> optional support inserts through shared legality checks
  -> scheduled-day countdown dose morph
  -> final calendar integrity check (the governor, invoked by the morph)
  -> closed session membership (which selected exercises each role renders)
  -> effective prescription resolution (the authoritative render dose)
  -> athlete-facing label stamping
  -> goal-preservation reconciliation (bounded restore; re-runs the governor)
  -> read-only Stage 1 draft rendering
  -> finalizer packet / Stage 2 handoff text
  -> AI finalization of wording / exact compliant coaching detail
  -> validation / release policy
  -> structured-card conversion (the athlete-facing plan view)
```

Support inserts run **before** the dose morph, not after it: the morph and the
governor it invokes are the last layers that may touch the calendar. Membership,
dose resolution and labels run after the governor but are calendar-read-only.

No lower layer may silently override a higher layer's ownership.

## 3. Decision ownership matrix

| Decision | Current implementation surfaces | Canonical owner | Allowed downstream behaviour | Forbidden downstream behaviour |
| --- | --- | --- | --- | --- |
| Parse raw planner input | `fightcamp/input_parsing.py`, `fightcamp/main.py` | `input_parsing.py` | Reject malformed input; carry parsing metadata | Reinterpret athlete intent later from free text when canonical fields exist |
| Injury triage mode | `fightcamp/injury_triage.py`, `fightcamp/main.py` | `injury_triage.py` | Carry restrictions/triage state downstream | Renderer/finalizer independently deciding whether a blocked plan may proceed |
| Canonical athlete/runtime model | `plan_pipeline_runtime.py`, `stage2_planning_brief.py`, `stage2_payload.py` | runtime + planning-brief model builders | Derive immutable planning facts from canonical input | Later scheduling code rebuilding conflicting athlete facts |
| Phase mapping | `plan_pipeline_runtime.py`, phase helpers | phase/runtime layer | Consume phase and countdown context | Session renderer inventing a different phase interpretation |
| Candidate exercise/drill selection pool | `plan_pipeline_blocks.py`, `strength.py`, `conditioning.py`, rehab modules | Stage 1 content-selection layer | Composition draws final membership from this pool; the finalizer may choose a stronger compliant same-role candidate **only for a role with no `selected_exercise_assignments`** | Candidate-selection modules deciding calendar placement; treating the pool itself as session membership |
| Closed session membership (which selected exercises a scheduled role actually renders) | `session_composition.py` (normal camp), `stage2_payload_late_fight.py` + `late_fight_tail.py` assignment attach (countdown) | `session_composition.py` for normal camp; the late-fight assignment builder for D-13 inward | Dose owners may reduce a member's dose; the finalizer renders every member exactly once; an illegal member may be dropped or held | Adding, restoring, replacing or substituting a member downstream; collapsing multi-member membership into one "primary" plus fallbacks |
| Effective render prescription (authoritative dose per selected exercise) | `prescription_resolver.py` | `prescription_resolver.py` | Renderer/finalizer render `effective_prescription` verbatim; readiness/cut/injury state may only reduce it further | Reconciling `base_prescription` against role caps downstream; re-deriving a countdown band (that stays with `late_camp_role_morph.py`) |
| Goal preservation: coverage verdict and bounded role restore | `goal_preservation.py` | `goal_preservation.py` | Restore a role **only** from that week's retained `goal_repair_candidates`, within the original category budget, onto a day the shared legality policy allows, at D-14 or earlier, re-running the morph/governor/composition/dose chain on a trial copy before committing | Inventing a new role, exercise, dose or session slot; overriding intentional compression, a hard suppression reason, a finished tail, or the late-fight path; restoring inside D-13 |
| Athlete priorities / limiter | `stage2_planning_brief.py`, `priority_profile.py`, goal-priority helpers | `stage2_planning_brief.py` + priority profile | Calendar allocator consumes priorities | Renderer/filler re-ranking athlete goals independently |
| Weekly stress intent | `stage2_planning_brief.py` | `stage2_planning_brief.py` | Role allocator converts intent to role slots | Fillers adding new meaningful stress because a week looks sparse |
| Declared contact ownership | `sparring_dose_planner.py`, `stage2_role_map.py`, `stage2_payload_late_fight.py` | `sparring_dose_planner.py` | Calendar allocator consumes resolved contact state | Other layers inferring hard-vs-technical from raw declared weekday alone |
| Effective contact load: hard / technical-only / deloaded / suppressed | `sparring_dose_planner.py`, late-fight logic, role-map logic | `sparring_dose_planner.py` | Countdown logic may request a dose transition through this contract | Compression/filler code treating every declared contact as hard load after resolution |
| Weekly role budget / which app-owned roles survive | `stage2_role_map.py` (with subordinate `pre_hard_contact_strength.py` helper), `stage2_payload.py`, late-fight permission/budget code | Normal camp: `stage2_role_map.py`; D-13 inward: late-fight permission/budget path | Finalizer renders only surviving roles; the subordinate pre-hard-contact helper applies the role-map owner's one-strength-exposure consequence only after final calendar integrity has fixed the normal-camp schedule | Renderer/finalizer restoring suppressed roles to make a week look complete; the helper inventing its own contact/spacing rule |
| Fight-week override | fight-week helpers, `fight_day_override.py`, late-fight payload | fight-week override layer; D-0 specifically `fight_day_override.py` | Remove/limit roles according to override | Generic allocator overriding D-0 or fight-week caps |
| Normal-camp day placement | `stage2_role_map.py`, `normal_calendar_placement.py` | `stage2_role_map.py` (`_assign_declared_day_hints`) + placement-owned completion (`normal_calendar_placement.py`) | Later integrity pass may reject or relocate only through shared calendar policy | Renderer assigning dayless roles; payload post-processing creating a second placement algorithm (Step 9A removed the dead `stage2_payload.py` boxing placement engine and its `_assign_declared_day_hints` duplicate) |
| Late-fight day placement | `stage2_payload_late_fight.py` (`_build_late_fight_session_sequence`), `late_fight_tail.py` (finished-tail reuse) | `stage2_payload_late_fight.py` | Tail reuse preserves finished placement | Normal fillers re-place tail-owned sessions |
| Hard-sparring adjacency / collision legality | `stage2_role_map.py`, `stage2_payload_late_fight.py`, `gap_fill_inserts.py` | `combat_load_policy.py` (shared calendar legality), consumed via the `calendar_context.py` adapter by both placement owners and the fillers (Step 9B) | Owners generate candidate days/slots and query the policy; fillers query legality before inserting; final governor re-validates | Any layer re-deciding ALLOW/DEPRIORITIZE/FORBID with its own hard-contact spacing doctrine |
| Crowded-week compression | `stage2_role_map.py` | `stage2_role_map.py` | Payload post-processing may decorate governance only | Re-compressing an already-compressed week in a second layer |
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
| AI finalizer | Stage 2 prompt / model boundary (`STAGE2_FINALIZER_PROMPT`, `UNLXCK_FINAL_RENDER_CONTRACT`) | AI only for wording, coaching detail, and presentation inside deterministic structure | Improve specificity; for a role **without** `selected_exercise_assignments`, replace a violating candidate with a same-role compliant option | Change session count, day ownership, contact status, fight-week caps, or deterministic safety decisions; add, restore, replace or substitute anything in a closed role (an illegal closed member is dropped or held and the gap is left) |
| Stage 2 validator | `stage2_validator.py`, `stage2_validator_postprocess.py`, `plan_contract_validator.py` | validator | Detect violations and report them | Becoming the primary scheduler or silently repairing calendar architecture |
| Planner-authority preflight (refuse to hand a structurally broken plan to the model) | `planner_authority_integrity.py`, called from `stage2_pipeline.build_stage2_package` | `planner_authority_integrity.py` | Hold the plan before the first model call and demand deterministic repair | Being used as a general validator, or as a way to let the model patch planner defects |
| Release policy (publish / publish_with_flags) | `stage2_policy.apply_stage2_release_policy` (data in `shared/stage2-policy.json`) | `stage2_policy.py` | Classify findings and attach the release decision | Emitting a hold of its own — it never returns `hold`; deterministic holds are applied by the layers named in section 3.1 |
| Repair-attempt ("retry payload") decision and prompt | `stage2_pipeline.build_stage2_retry`, `stage2_repair.build_stage2_repair_prompt`, `stage2_repair.reconcile_selected_conditioning_assignments` | `stage2_pipeline.py` decides whether a repair is warranted; `stage2_repair.py` builds the deterministic fix or the repair prompt | Prefer the deterministic conditioning reconciliation; fall back to at most one extra model call | Looping, or redefining planner architecture to make a failing plan pass |
| Stage 2 orchestration (how many model calls actually happen) | `api/stage2_automation.py` (`OpenAIStage2Automator.finalize`) | `api/stage2_automation.py` | Run first pass, at most one plan-text repair, then the structured-card calls; apply the deterministic holds | Upgrading another layer's hold to a release; adding a second repair round |
| Structured-card conversion (athlete-facing plan view) | `api/structured_plan_generation.py`, `api/structured_plan_models.py`, `api/stage2_automation.attempt_structured_plan_for_result` | `api/structured_plan_generation.py` | Convert approved `plan_text` into `StructuredTrainingPlan`; degrade to the raw markdown fallback on any failure | Holding or blocking a plan because a card failed; deciding any planner question during conversion |
| Final release override (does a held plan reach the athlete?) | `api/generation/persistence._release_held_plan_with_flags` | `api/generation/persistence.py` | Release any held plan with usable content as `publishable_with_flags`, preserving every finding | Erasing findings or `stage2_status` while releasing; releasing a genuinely empty result |

### 3.1 Holds, and what actually happens to them

This is the part of the chain most easily misread, because two layers disagree by
design and the *later* one wins.

**Layer 1 — the release policy never holds.** `apply_stage2_release_policy` always
returns `release_decision` of `publish` or `publish_with_flags` and always sets
`is_athlete_releasable` / `is_publishable` true. Validator findings never block
release on their own.

**Layer 2 — four deterministic owners do hold.** Each says the deterministic plan
itself is unusable, not that the wording is poor. Each applies its hold *after*
the release policy has run:

| Hold | Applied by | Meaning |
| --- | --- | --- |
| Planner preflight | `planner_authority_integrity.late_physical_planner_preflight`, via `build_stage2_package` | Stage 1 handed over a plan the finalizer must not be asked to render; held before the first model call |
| Structural integrity | `stage2_pipeline.apply_structural_integrity_hold`, driven by `_apply_structural_source_repair_and_hold` | Phase/week/session-role structure is missing and deterministic repair could not restore it |
| Conditioning-render | `api/stage2_automation.finalize` | Selected conditioning membership is missing from the render and neither the deterministic reconciliation nor the one repair call resolved it |
| Goal-preservation regeneration | `goal_preservation.validate_goal_preservation` -> `requires_planner_regeneration` | Selected goal coverage is unmet; the fix is deterministic planner repair, never another model call |

A hold sets `release_decision` to `hold`, moves the rendered text to
`final_plan_text`, blanks `plan_text`, and sets plan status `review_required` with
`stage2_status = stage2_failed`. Within Stage 2 the hold is final — nothing inside
`api/stage2_automation.py` may upgrade it, and because
`should_attempt_structured_plan` requires an athlete-displayable status, a held
plan gets **no structured card**.

**Layer 3 — persistence releases the hold anyway.**
`api/generation/persistence._release_held_plan_with_flags` runs last, on every
Stage 2 result. Any plan sitting at `review_required` / `held_for_review` that has
usable text is rewritten to `publishable_with_flags`, and when the hold blanked
`plan_text` it is restored from `final_plan_text`. The validator/contract findings
are preserved untouched. Only a genuinely empty result (no plan text, no final
text, no clean card) stays held. The same override also cancels the
`review_required` downgrade that `_apply_plan_contract_validation` applies on the
line immediately above it.

**Net production behaviour, and how to read a held plan:**

- A deterministic hold is an **audit signal and a card suppressor**, not a release
  gate. The athlete still receives the plan, as `publishable_with_flags`, on the
  raw markdown fallback.
- `stage2_status = stage2_failed` survives the override, so a held-then-released
  plan is still findable by admins.
- The only outcomes that genuinely reach the athlete as *withheld* are Stage 1
  injury triage — which takes a separate persistence path
  (`persist_triage_review_required`) and is not overridden — and an empty result.

The override is deliberate and test-locked (`tests/test_validator_release_invariant.py`).
Do not "fix" a hold by weakening its owner; and do not assume a hold keeps a plan
off the athlete's screen. If a defect must actually block release, that is a change
to the override, argued under section 12.

## 4. Current normal-camp execution order

Current Main executes the normal dated-camp planning brief as follows:

`fightcamp/main.py` renders the phase-level Stage 1 draft (`render_plan_bundle`)
*before* it builds the Stage 2 outputs. Everything below happens inside
`build_stage2_outputs` -> `build_planning_brief`, and only the late-fight draft
override and the lead summary write back into the already-rendered draft text.

```text
build athlete model / candidate pools
  -> build limiter + sport load + weekly stress map
  -> build week-by-week progression
  -> stage2_role_map._build_weekly_role_map
       (role budget/compression, then _assign_declared_day_hints placement
        through shared combat_load_policy legality)
  -> stage2_payload._apply_boxing_crowded_week_post_processing
       (day-identity governance decoration only; it deletes its athlete_model
        argument so it cannot re-decide compression or role survival)
  -> normal_calendar_placement.fill_missing_session_days
       (placement completion, same shared legality)
  -> apply_camp_week_fillers            (support inserts, gated by shared legality;
                                         this is also where the finished D-13 tail
                                         is spliced, via _splice_late_fight_tail)
  -> apply_late_camp_role_morph
       (countdown dose, then apply_final_calendar_integrity — the governor fixes
        the final calendar and re-runs dose-only morph if it relocates a role;
        only after that does the subordinate pre-hard-contact helper apply the
        normal role-budget consequence on D-14+ days, followed by one last
        dose/metadata-only morph pass over the surviving roles)
  -> session_composition.compose_normal_strength_assignments
     session_composition.compose_normal_conditioning_assignments
       (closed session membership; reduce-only from Stage 1's selected slots)
  -> attach late-fight assignments to any spliced tail roles
  -> prescription_resolver.apply_effective_strength_prescriptions
       (authoritative effective_prescription per selected strength exercise)
  -> stamp labels
  -> goal_preservation.reconcile_goal_preservation
       (coverage verdict; a bounded restore re-runs morph + governor +
        composition + dose resolution on a trial copy before committing)
  -> [late-fight only] _render_late_fight_stage1_draft replaces the draft text
  -> render_lead_summary inserted after the plan title
  -> build_stage2_handoff_text (LLM-boundary projection + finalizer packet)
```

The governor is the last stage that may change the calendar: every layer that can
mutate it (placement, completion, fillers, dose morph) runs before or through it.
The stages after it — membership, dose resolution, labels — read the calendar and
never move a role. Goal preservation is the single exception, and it is bounded:
it may re-add a role the planner itself retained as a repair candidate, and it
re-runs the morph and the governor on a trial copy before committing, so the
finished calendar is still governor-verified.

Changes must be reviewed against this whole chain, not only `stage2_role_map.py`.

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

Support inserts may create these fields only for the new support role they own, after a legality check.

`goal_preservation._restore_goal_roles` is the one further writer, and it is
bounded to the same discipline: it may stamp `scheduled_day_hint` /
`scheduled_countdown_label` / `session_index` on a role the planner itself
retained in that week's `goal_repair_candidates`, only on a declared training day
at D-14 or earlier that the shared legality policy allows, only within the
original category budget and the athlete's session cap, and only after a trial
copy re-runs the morph, the governor, composition and dose resolution and proves
no other stimulus was lost. It never invents a role, a day, a dose or capacity.

Renderers must be read-only.

### Load-owned fields

Combat-contact resolver and countdown dose policy own:
- effective hard-contact state
- `effective_hard_sparring_days`
- hard / technical-only / suppressed contact semantics
- `stress_class`
- `cost_class`
- `meaningful_stress`
- dose caps that arise from countdown safety

`prescription_resolver.py` owns the derived render dose:
- `effective_prescription` (authoritative) alongside the preserved `base_prescription`
- `effective_strength_prescriptions` on the role

Other modules may read these fields but must not infer replacements from raw labels.

### Membership-owned fields

`session_composition.py` (normal camp) and the late-fight assignment builder own:
- `selected_exercise_assignments`

A role that carries this list has **closed** membership. Downstream layers may
render it, reduce a member's dose within its authorised envelope, or drop/hold an
illegal member and leave the gap. They may never add, restore, replace or
substitute a member. A role without the list keeps the older open contract, in
which the finalizer may still substitute a compliant same-role candidate.

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
11. **Closed membership is closed.** Once a role carries `selected_exercise_assignments`, no downstream layer — repair prompt, finalizer, card conversion — may add, restore, replace or substitute an exercise in it. An illegal member is dropped or held and the gap is left for deterministic planning.
12. **A deterministic hold is a planner bug, not a release decision.** The four holds in section 3.1 exist because the deterministic plan is unusable, and in production the plan still ships (persistence releases it with flags). The hold is therefore a signal to fix the planner — never a reason to add another model call, tweak the prompt, or relax a policy so the broken plan validates.
13. **The structured card cannot hold a plan.** Card conversion is downstream of release. A missing, invalid or rejected card degrades to the `plan_text` fallback and is recorded for admin audit.

## 8. New-code placement rules

Until the architecture is consolidated further:

- New normal-camp placement rules belong in `stage2_role_map.py` or a shared calendar-policy module called by it.
- New hard-vs-technical contact semantics belong in `sparring_dose_planner.py`.
- New late-fight placement rules belong in `stage2_payload_late_fight.py` (the live late-fight placement owner).
- New countdown dose-reduction rules belong in `late_camp_role_morph.py` / the canonical countdown dosage policy.
- New filler types belong in the filler library, but their placement must use the shared legality contract.
- New session-membership rules belong in `session_composition.py` (normal camp) or the late-fight assignment builder — never in the finalizer prompt.
- New effective-dose resolution belongs in `prescription_resolver.py`; new countdown bands stay in `late_camp_role_morph.py`.
- New goal-coverage rules belong in `goal_preservation.py`, inside its existing bounded-restore constraints.
- New rendering copy belongs in rendering/label modules and must describe existing state only.
- New finalizer rules may constrain wording, or compliant substitution for roles without `selected_exercise_assignments`, but must not compensate for deterministic calendar defects.
- New structured-card shape belongs in `api/structured_plan_models.py` + `api/structured_plan_generation.py`, and must stay non-blocking.

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
| Closed session membership | `session_composition.py`; late-fight assignment builder for D-13 inward |
| Effective render prescription | `prescription_resolver.py` |
| Goal coverage verdict + bounded restore | `goal_preservation.py` |
| Stage 1 draft rendering | `plan_pipeline_rendering.py` — read only |
| AI finalizer | wording / coaching detail; compliant substitution only for roles without closed membership |
| Validation | `stage2_validator.py` (+ postprocess), `plan_contract_validator.py` — never repairs architecture |
| Release policy | `stage2_policy.py` — publish / publish_with_flags only, never a hold |
| Deterministic holds | the four owners in section 3.1 |
| Structured-card conversion | `api/structured_plan_generation.py` — non-blocking |

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
8. **Duplicate role-budget engine (removed, Step 10).** `stage2_payload.py` carried stale
   forks of the `stage2_role_map` role-budget/compression engine. Eleven of them
   (`_lock_declared_hard_sparring_roles`, `_compressed_priority_for_role`,
   `_is_final_week_capped_sparring_entry`, `_role_anchor`, `_role_selection_rule`,
   `_recovery_role_key`, `_primary_limiter_key`, `_join_rule_parts`, `_normalize_text`,
   `_phrase_in_text`, `_slugify`) were outside the transitive closure of every real root —
   the four production entry points, module-level code, and every name any module or test
   imports from `stage2_payload` — and were deleted, along with three then-orphaned
   constants. The follow-up ownership closure also removed the payload-owned
   crowded-week *compression* path. Crowded-week policy, compression, suppression,
   and unused-day state now live only in `stage2_role_map.py`. What survives in
   `stage2_payload.py` is `_apply_boxing_crowded_week_post_processing`, which is
   decoration only: it discards its `athlete_model` argument, reads the role map's
   already-final `intentional_compression` verdict, and stamps day-identity
   governance onto the surviving roles. `_apply_high_fatigue_week_compression` in
   `stage2_payload.py` still contains a full non-boxing compression implementation
   but has no production caller (see 9.3.3); the live path delegates the boxing
   crowded-week case to `stage2_role_map._apply_boxing_crowded_week_compression`.

### 9.3 Remaining non-blocking debt

These are real but do not affect decision ownership, and are explicitly **not** scheduled
work (see the freeze rule in section 12).

Items 1-4 are structural shape. Items 5-7 were found in the September 2026 Stage 1 ->
Stage 2 -> cards audit: they are dead code, an unreachable branch, and stale comments that
had made their way into these docs as descriptions of live behaviour. They are recorded
here so the docs stop asserting them; none is scheduled work either, and each would be a
behaviour change to resolve.

1. `camp_week_fillers.py` / `camp_week_fillers_impl.py` remain a facade/implementation
   pair. The facade holds real orchestration (tail splicing, tactical-watch insertion), so
   it is not pure indirection and was not collapsed. Ownership is unambiguous: filler
   selection is the filler layer's, legality is `combat_load_policy`'s.
2. `stage2_finalizer_packet.py` / `_impl.py` are likewise a facade/implementation pair
   holding real packet-building logic. Same conclusion.
3. `stage2_payload.py` remains a compatibility/orchestration surface. Its dead placement
   policy (Step 9A) and its dead duplicate role-budget engine (Step 10) are gone; what
   remains is orchestration, re-exports, and four helpers live tests import as independent
   oracles. Two of those (`_apply_high_fatigue_week_compression`,
   `_compute_readiness_compression`) have **diverged** from their `stage2_role_map`
   counterparts, so they are not interchangeable; repointing those tests at the live owner
   would change what they assert and is deliberately left as separate work.
4. `weekly_schedule_view.py` normalises resolver `status` -> display `effective_load` for
   the API/validator view layer. This is presentation-side normalisation of resolver
   output, downstream of every planner decision; it is not a second contact authority.
5. **`weekly_plan_render.py` is not wired into the pipeline.** It renders a deterministic
   `## Week N — PHASE (D-x -> D-y)` week/day/session spine, and earlier revisions of this
   contract and of `STAGE2_PAYLOAD_SPEC.md` described it as the live Stage 1 renderer. It
   is not: `render_weekly_schedule_section` has no production caller anywhere in `api/` or
   `fightcamp/` — only tests import it. The live Stage 1 draft is still the phase-level
   render in `plan_pipeline_rendering.py` (`## GPP` / `### Strength & Power` /
   `### Conditioning`), with a deterministic countdown spine only on the late-fight path
   (`_render_late_fight_stage1_draft`). This is why `missing_week_session_role` and
   `late_camp_session_incomplete` are still in the Stage 1 parity baseline. Ownership is
   not ambiguous — nothing else claims that rendering — so this is dead code, not a second
   writer; wiring it in (or deleting it) is a behaviour change and needs its own argument
   under the freeze rule.
6. **`api/stage2_automation.py`'s "callers never upgrade HOLD to publication" comment is
   false.** The comment sits directly above the `_reviewed_result` call in `finalize`. It is
   true of Stage 2 itself, but the caller — `persist_plan_and_finalize` — does exactly that
   via `_release_held_plan_with_flags` (section 3.1). The same applies to the fail-closed
   language in `_apply_structural_source_repair_and_hold`'s docstring and to the
   `_CONTRACT_REVIEW_PLAN_STATUS` comment in `api/generation/persistence.py`, which
   describes a `review_required` routing the very next statement cancels. The behaviour is
   deliberate and test-locked; the comments are what is stale.
7. **`build_stage2_retry`'s hold guard is unreachable.** It early-returns
   `needs_retry: False` when `release_decision != "hold"` and there is no missing-closed-
   conditioning or goal-preservation finding — but its own call to
   `apply_stage2_release_policy` always rewrites `release_decision` to `publish` or
   `publish_with_flags` first, so the `"hold"` branch can never be taken. The practical
   consequence: `late_camp_effective_prescription_exceeded` and
   `goal_preservation_render_mismatch` on their own never produce a repair prompt, even
   though `api/stage2_automation.finalize` lists them as repair triggers and labels the
   attempt `effective_dose_repair`. Only the two conditioning codes actually reach a
   second model call. Documented here rather than silently changed: making the branch live
   would add a model call to a case that currently ships with flags, which is a release-
   behaviour change, not a refactor.


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
- Does closed membership (`selected_exercise_assignments`) stay closed everywhere downstream — prompt, repair prompt, card conversion?
- If it changes dose, does it change `effective_prescription` at its owner rather than reconciling doses downstream?
- Does it add, remove or change a deterministic hold (section 3.1)? If so, what is the deterministic repair, and why is a hold the right answer instead of releasing with flags?
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

session_composition.py + prescription_resolver.py
    close session membership and the effective dose on that verified calendar

goal_preservation.py
    judges coverage, and may only restore a planner-retained candidate back
    through the same morph/governor chain

render/finalizer/card conversion
    consume that calendar without rebuilding it
```

The architectural success condition is simple: for any athlete-facing session, a developer should be able to answer **why this role exists, why it survived, why it is on this day, what its effective load is, which exercises it contains, at what dose, and which file has authority for each answer** without tracing competing implementations.

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
| New session-membership rule | `session_composition.py` / the late-fight assignment builder |
| New effective-dose rule | `prescription_resolver.py` (bands stay in `late_camp_role_morph.py`) |
| New goal-coverage rule | `goal_preservation.py`, inside its bounded-restore constraints |
| New card field | `api/structured_plan_models.py` + `api/structured_plan_generation.py`, non-blocking |

### Specifically prohibited

- a second module that returns ALLOW / DEPRIORITIZE / FORBID;
- a second placement engine, or a generic "planner manager" / orchestrator over the
  existing owners;
- new `*_patch.py` / `*_integration.py` forwarding layers;
- another calendar abstraction or another role classifier;
- re-deriving effective contact from declared weekdays, role keys, or countdown
  thresholds when resolved sparring state is available;
- moving placement, contact, or role-survival authority into the renderer, the AI
  finalizer, the validator, or the structured-card converter;
- a second repair round, or any path that lets the model resolve a deterministic hold;
- granting the finalizer, the repair prompt, or the card converter permission to add,
  restore, replace or substitute an exercise inside a closed role.

The architecture regressions in `tests/test_step10_architecture_closure.py` and
`tests/test_placement_ownership.py` enforce this. A change that requires editing the
canonical legality matrix in those tests is, by definition, a change to training
collision doctrine and must be argued as such — not slipped in as a refactor.
