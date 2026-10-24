# Injury readiness provenance and primary-goal suppression

Base: Main `315a469f` (merged #3033 and #3034). Production inspection was SELECT-only against project `leienvqynijrgghhzczt`. No records were changed.

## Observed evidence

Job `343486ba-dffd-4e79-814a-09ee278a1601`, source `admin_latest_intake`, was created on 2026-10-24 at 15:06 UTC. Plan `209ad015-8b1b-4fb4-b8a3-00684915e0b1` stores low-severity pain (`injury_type_default`), full-plan triage, no clearance requirement or movement restrictions, and both `injury_management` and `moderate_injury` flags. Its GPP pool contains 33 strength slots and five conditioning slots. Both strength roles have `two_hard_spar_days` / `injury_management` removal reasons every week.

The injury tracker contains an open, intake-derived row for the same symptom, created at 14:06 UTC, with `severity=moderate`, no `severity_source`, no `manual_severity`, and `latest_reported_status=ongoing`. There are no Today check-ins in the seven-day readiness window. The request also declares Tuesday/Friday light combat, in addition to Wednesday/Sunday hard sparring, and four total weekly appointments. The user explicitly confirmed that coached sessions consume that four-total-session contract.

The current plan row has subsequently been administratively rejected. This investigation does not assume that its current status is its original release status.

## Injury authority trace

1. `PlanInput.from_payload()` and `_attach_severity_provenance()` resolve the occasional symptom as low-severity pain. Medical triage permits a full plan.
2. Separately, `_legacy_intake_injury_candidate()` has historically assigned `moderate` to every free-text tracker entry. This is a tracking compatibility default, not independently confirmed medical severity. Intake sync retains that value in `injury_flags`.
3. Generation calls `annotate_payload_with_sparring_readiness()` server-side. It reads open/monitoring tracker rows and recent check-ins. Before this fix, its allowed-field projection discarded the row's source, severity provenance, manual severity, and latest reported status.
4. `sparring_readiness_flags()` introduces **`moderate_injury`**, through its active-injury severity branch. A separate branch can introduce it for a recent manageable/high-pain or worsening check-in. These flags originally describe hard-contact scheduling readiness, not a new medical diagnosis.
5. `_build_athlete_model()` concatenates those flags with intake-derived flags. `_derive_readiness_flags()` supplies `injury_management`; it does not produce `moderate_injury`.
6. `_boxing_crowded_week_injury_is_moderate_plus()` treated the flat `moderate_injury` flag as conclusive global injury evidence before inspecting current low/non-limiting intake. Both generic compression and crowded-week policy consume this predicate. Thus a tracker default, manageable contact-specific pain, or an opaque inherited flag could overrule current intake.

This is independent of injury location. Multiple simultaneous injuries must retain the independently restrictive injury rather than neutralizing the entire injury set.

### Corrected precedence

The same readiness producer now emits `readiness_evidence` diagnostics beside its existing flags. This is scope/provenance, not another injury severity or impact classification:

- Recent, latest check-in high pain or worsening can restrict global capacity. Stale/future check-ins do not count. Manageable pain alone retains contact caution.
- An unproven moderate tracker value retains conservative contact caution, with reason `unverified_tracker_severity`; it cannot independently remove a weekly appointment.
- Explicit manual/provenanced severity, high/severe evidence, and independent medical overrides remain restrictive. Manual high severity is evaluated before applying non-limiting awareness behavior.
- Current parsed severity, the shared `not_limiting` / `limiting` / `cant_train` contract, medical restrictions, red flags, and movement filters remain authoritative through their established owners.
- An opaque `moderate_injury` flag without global-capacity evidence is insufficient for global compression. Independent severe/red-flag flags remain protective.

The snapshot boundary retains the existing source/provenance fields so the producer can apply this precedence. The athlete snapshot retains only compact evidence diagnostics, not raw check-in history. The tracker itself is not rewritten or retrospectively cleared.

## Strength removal trace

The deterministic replay instruments `_apply_high_fatigue_week_compression()` at its entry/exit and captures reconciliation before Open Build projection:

- Before compression, all four weeks contain `primary_strength_day`, already assigned Friday, plus secondary strength, aerobic work and recovery. There are no hard-suppression reasons on the strength roles.
- The boxing crowded-week policy is **inactive**: six available days, no meaningful cut, no fatigue, and only one risk signal. Its anchor selector did not remove this plan's primary strength. `primary_strength_day` is correctly in `PRIMARY_STRENGTH_ROLE_KEYS`.
- The **generic** allocator removes both strength roles. The declared two sparring days consume two slots; the false global injury signal removes another. The phase's `must_keep` list is `rehab`, `aerobic`, `primary_strength`.
- `_non_spar_role_priority_rank()` recognized the literal aerobic system and gave it rank 100, but compared the semantic `primary_strength` requirement only to the literal `primary_strength_day` key. The actual anchor received rank 4. Thus it lost the final slot without any movement candidate being considered unsafe.
- `_restore_goal_roles()` and #3034's maintenance retry then see `injury_management` as an authority veto. No complete placement search is performed past that veto; no compatible strength host remains for recomposition/microdosing. Deferral constraints cite the false compression authority, so the existing validator regards the deferral as justified.

Both the normal and crowded rankers now recognize the existing semantic requirement through the canonical primary-strength role set. Existing goal-priority tie breaking remains in control; conditioning, power and speed are covered, without hardcoding this athlete or a new strength quota. No hard-suppressed candidate is revived.

## Actual appointment capacity

The generic allocator reserved hard sparring but did not reserve the light-combat appointments that `_lock_declared_light_combat_roles()` inserts later. The crowded-week owner had the same accounting gap. A discretionary physical filler could then create another standalone appointment even when the final calendar was full.

Both budget paths now reserve the existing declared light-combat appointments, counting actual calendar occurrences. The filler placement owner checks the existing appointment contract before creating an extra appointment; shared support may still accompany a lawful existing appointment. Rehab content and rendering are unchanged.

Suppression records use `coach_owned_appointment_capacity`, mapped to the existing `calendar_capacity` deferral reason. The week records its requested budget and light-combat reservation. The repair authority drops this reason when the final calendar no longer contains the coached work or has spare capacity, so a stale capacity ledger cannot permanently prevent recovery.

Reconciliation now opts into the existing appointment-cap enforcement for both its initial build/maintenance repair and #3034's fallback. A goal cannot manufacture a fifth appointment. A qualifying trial rejected for capacity records `weekly_appointment_capacity`; it can justify deferral only while the actual calendar is still full. Both repair and deferral also recheck injury-compression reasons against current parsed/provenanced injury authority, preventing an old injury ledger from perpetuating a disproven global restriction.

With the confirmed contract, the exact saved four-coach schedule has **no** capacity for separate app-owned strength. It must not be called a feasible strength week merely because unused weekdays and strength exercises exist.

| Representative replay | Before | After |
| --- | --- | --- |
| Exact four-coach intake, four-total target | No strength; false injury deferral; six standalone physical appointments per open week including a filler | Four protected coached appointments; no additional physical filler; explicit capacity deferral; no injury-compression reason |
| Same symptom and historical tracker row, two hard contacts and two genuinely available appointments | No strength; false injury deferral | Real primary strength in each open week; primary build evidence matches projected membership; four appointments |
| No injury, same feasible appointment budget | Primary work depends on existing role ranking | Primary adaptation preserved through the corrected semantic requirement; contact rules remain authoritative |

The fixture fixes the clock and seed and tests knee, shoulder and no-injury variants across Open Build and dated normal-camp weeks. It exercises the real server snapshot, intake, triage, role allocation, effective membership, goal reconciliation and projection. Removing causal constraints from a primary deferral remains a validator failure.

## Scope and limitations

No production writes, backfill, merge or deployment. No UI, medical intake enum, medical classification, strength exercise-count cap, conditioning dose/one-drill rule, rehab content, model, worker, timeout or publication-gate changes. #3033's advice/exercise separation and closed membership and #3034's maintenance recovery remain intact. Existing placement, safe candidate composition/substitution, contact legality and realised-load owners retain control.

The server-enriched readiness payload is ephemeral and is not stored in the original job request. The tracker row was updated after generation when the resulting plan was synchronized. Therefore the saved request and current tracker evidence support the source trace and deterministic reproduction, but are not a byte-for-byte archive of the original server enrichment or random candidate selection. The test seed is fixed at 7; the production request did not fix a seed.

The dated replay asserts normal weeks clear of the finished late-fight ownership window; this PR does not redesign the D-13 tail. Other unmet power/conditioning/footwork obligations remain visible; a strength fix is not a promise to satisfy every secondary goal. Contradictory declarations with more protected coached appointments than the requested target cannot be repaired by deleting coach-owned sessions.

## Athlete-facing goal notes

A supplied screenshot exposed the internal validator sentence about “deterministic repair” in Active notes. The Open Build goal projection carried `contract_errors` into the finalizer's render material; the finalizer could paraphrase that diagnostic into the athlete plan. Its fallback goal classification could also precede the actual open-block verdict.

Reduced-week copy now cites actual suppression reasons rather than inferring injury compression from any active symptom. The finalizer now receives the final open goal verdict and a plain `athlete_explanation`, with workflow diagnostics omitted from its goal render context. The source brief, validator report, evidence and constraints remain intact for admin review. Structured conversion replaces goal-gap/deferral notes with the same authoritative explanation. It does not edit injury context or red-flag rules, hide unmet goals, alter session membership, or add a release gate.

Examples:

- Capacity: “Your current training schedule leaves no room for separate strength work this block.”
- Missing work without a justified deferral: “This plan does not yet include work for your footwork goal.”

Existing saved plan text/notes are not backfilled. The source prompt and backend conversion changes apply to newly generated/converted plans after deployment. No model call was made to evaluate prose generation in this investigation; note correction itself is deterministic and covered by tests reproducing the screenshot.
