# Combat training allocation and boxing conditioning audit

## Saved-plan findings

Read-only inspection of the earlier and newer saved plans confirmed the same Tuesday/Saturday hard sparring, Thursday/Friday Light Combat appointments and six available training days. Both saved intakes supplied structured frequency **6**, recorded as `user_supplied`. Only the newer intake included the current “8/9 sessions a week” and double-day note. Both failed power preservation in **D-2 through D-15** despite retaining earlier power witnesses. The defect therefore predates the note; it was not an absence of power throughout camp. Conditioning goal coverage already passed in both saved plans.

The UI explained the possible six-day/six-session confusion: Quick Build automatically followed availability with frequency and prevented counts above available days; full intake capped frequency at six. Backend parsing also rejected doubles. Saved provenance cannot establish whether the athlete deliberately chose six or the UI supplied it, so the fix preserves the structured answer and records the conflicting note separately.

## Corrections and authority

- Availability and session count are independent. Existing frequency inputs accept doubles, up to two sessions per selected day, without raising app role budgets or authorising that many hard workouts. Quick Build no longer silently changes frequency when days change.
- Intake parsing recognises explicit current weekly ranges and positive double-day statements. Missing structured frequency uses the range's lower bound; an explicit structured answer wins, and discrepancies remain in `training_workload_context`. Availability-only fallback is explicitly system-inferred. No day, duration or intensity is inferred from free text.
- Shared calendar policy permits hard S&C alongside the specifically declared Light Combat / S&C-compatible appointment. Generic or downgraded technical contact retains its stricter ownership; explicit technical stress overrides the light appointment's intent. The same shared policy checks combined daily stress and recovery spacing. Ordinal stress grades are compared, not added as fictitious workload units. Two hard S&C sessions do not acquire permission merely because boxing is light.
- Crowded-week decisions use resolved effective hard days, including an authoritative empty list. Routine inactive trimming codes no longer veto all goal repair. Genuine fatigue, injury, cut, intentional compression, contact locks and finished-tail ownership still take precedence.
- Placement reserves a suitable conditioning day when it is the higher selected priority, while preserving a primary strength weakness. Converting recovery to aerobic support retains its original category budget ownership.
- Day occupancy is separate from the total session ceiling. Each standalone coach or S&C appointment consumes a session, including two on the same day; movement inserts embedded in a session consume no additional appointment. The normal allocator and goal repair enforce the total in seven-day buckets, including across phase boundaries. An impossible normal coach schedule is preserved and explicitly blocked by validation. Goal repair can relocate an existing role, exchange approved roles or use authorised embedded members; it cannot exceed the requested total. Further direct-countdown frequency work was stopped at the user's request; its separate occupancy owner is unchanged.
- For maintenance repair, the prescription resolver reuses the existing reduced maintenance envelope. The bank identity and base dose remain intact; countdown and readiness can tighten the result. Unit-preserving support prescriptions now display their actual RPE ceiling.
- Realised stress distinguishes authored easy aerobic effort from an unconditional fatigue tag, uses resolver effort for capped strength work, and counts ballistic/mechanical reps separately from ordinary lifting reps. Unknown effort stays conservative. Normal forbidden doses surviving the two-round revalidation bound use canonical suppression; legal graded conflicts remain inspectable. Revalidation handles forbidden doses through the canonical mover and rechecks each conflict after a preceding mutation, avoiding suppression of both sessions from a stale same-day verdict. Affected neighbouring strength roles are recomposed after moves/removals, and all goal evidence is refreshed against the final calendar.

## Boxing conditioning

Both base and style scoring now carry an inspectable heavy-bag preference within the already-authorised energy system. SPP favours boxing fight-pace/repeat-effort work more strongly than GPP; alactic bag bursts remain competitive. The aerobic bonus is smaller so machines, shadowboxing and recovery work remain viable. The bonus yields to missing equipment, upper-limb sensitivity, high fatigue, three effective hard-contact days and taper/fight-week proximity. Eligibility, injury filtering, dose and scheduling remain with their existing owners.

Pressure Combination Rounds now explicitly follow the athlete's fight-round length, retaining the authored round count and rest. Catalogue identity is preserved through its updated content-hash binding. Alactic workload targets use short burst work (30 seconds GPP, 40 seconds SPP), rather than inheriting multi-minute aerobic/glycolytic targets. A final complete authored round may cross the active-work floor, while bank round counts and elapsed-time caps still constrain partitioning.

In the controlled real-bank SPP comparison, selected bag exercises increased from **zero to three**: Entry-and-Score Burst, Heavy Bag Power Rounds and Max-Power Bag Burst. Tempo Shadowboxing remains as aerobic work. Regression coverage checks sustained rounds, burst/repeat-effort variety, equipment exclusion, phase progression, readiness and actual resolved prescriptions.

## Before/after verification

The anonymised fixtures pin 13 October, the actual fight date and relevant intake constraints, with neutral identifying fields and seed 1. Baseline is pulled Main at `eadb97d2`. This compares deterministic output under identical controlled inputs; it does not claim to reproduce an unknown historical random seed. The committed `combat_allocation_comparison.json` records all nine cases. Witness days are not appointment counts or measures of total workload.

| Case | Before | After |
| --- | --- | --- |
| Earlier saved constraints, six total | Power missing D-2..D-15 | Power maintenance covered at D-15; speed explicitly deferred within six appointments |
| Newer saved constraints, six total | Power missing D-2..D-15 | Power maintenance covered; speed/conditioning explicitly deferred within six appointments |
| Explicit 8 / 9 sessions | Input rejected against six available days | Accepted; selected speed/power/conditioning covered with legal technical doubles |
| High fatigue | Strength/power roles heavily suppressed | Reduced-dose maintenance retained where legal; fatigue remains active |
| Knee restriction, no jumping | Power absent | Injury-filtered strength/conditioning retained; speed/power explicitly deferred |
| Three hard contacts | Heavy compression | Effective contact compression retained; bounded legal exposures survive |
| Professional, no hard contact, nine sessions | Frequency rejected | Input accepted; speed build, power maintenance and conditioning covered with compatible S&C |
| Fight week | No development work | No development work; finished-tail safeguards retained |

Exact calendar baselines were refreshed for the intentional allocation and resolved-contact suppression changes. The direct D-13 semantic baseline is unchanged. Tests inspect scheduled bank identities, effective doses, coach-owned technical locks and shared legality, including a week where coverage must genuinely defer.

## Remaining limits

This does not remove publishing gates or claim all validation flags were programming defects. The six-session schedules include four coach appointments, leaving two standalone S&C appointments. They preserve power but do not claim complete speed/conditioning coverage. Their remaining conditioning-underfill count is zero because over-budget sessions were removed, not because additional work was invented. Explicit eight/nine cases retain three underfills. Some selected rep-based conditioning lacks enough canonical timed work to meet its phase workload floor.

The professional comparison also covers all selected goals after affected neighbours are recomposed, while retaining seven workload underfill findings. Further work belongs in authorised selection/composition and dose evidence, not another frequency restriction or a change to publishing gates.

Saved plans also carried `ambiguous_working_dose` and rendering/contact findings. Publishing policy and AI rendering were not changed. Live database records were read only; no plans were regenerated, deployed or modified.

Frontend QA: production build, TypeScript and lint passed (lint retains existing warnings). React DOM interaction verifies selecting nine sessions across six days and preserving it when availability changes; validation/round-trip tests cover both inputs. Starting the local server was rejected by automatic tool policy, so browser screenshots, layout and browser console checks are unverified.

Validation evidence: the 80-file sweep recorded 2,186 passes and three findings. All three were corrected (reviewed bank metadata, stale witness dates, and stale neighbour pruning); affected suites were rerun. Final runs include 119 goal-delivery/allocation tests, 49 calendar/goal-contract tests, 245 dose/calendar/repair tests, 83 conditioning/composition tests and 41 frontend tests. These suites overlap and their counts are not additive. Python imports, compileall, Ruff, diff checks, production frontend build, TypeScript and lint also passed.

## PR failure investigation

The follow-up found a real session-count defect: a six-session final schedule held nine standalone appointments in its opening week because goal repair counted days. The added end-to-end counter independently counts standalone cards, verifies six/eight/nine ceilings across complete calendar weeks and phase boundaries, and checks final prescriptions and shared legality. Impossible normal coach schedules are explicitly blocked. The separate direct-countdown frequency audit is deferred at the user's request.

The crowded-week fixtures previously projected a lone seven-day SPP phase onto D-6..D-0 without a fight weekday. Every declared hard session was therefore converted under the unresolved D-14 cutoff, while the tests expected three effective hard sessions. The corrected restrictive fixtures provide a normal four-week calendar and a genuinely meaningful 8% cut: resolved contacts remain two, the three declared coach rows remain, and the original maximum of two standalone S&C roles stays intact. Separate resolved-contact policy cases prove that moderate fatigue with two effective hard contacts does not inherit the declared three-contact restriction. Support inserts are tested separately from standalone S&C roles.

The relocation fixture still records actual moves and checks destination membership, effective doses and no residual conflicts; the relocated role is now secondary strength. The D-7 primer fixture checks a legal bounded primer alongside immutable light combat, with unchanged pool/dose and hard-contact safeguards. Calendar snapshots are reviewed against unchanged contact rows, actual appointment ceilings, resolved prescriptions and shared legality before being refreshed; their added suppressions explicitly carry `total_session_budget`. Direct D-13 remains unchanged.

The conditioning plan's additional selection change is Entry-Score-Exit Bursts (6s × 8, 60s rest) to Max-Power Bag Burst (5s × 8, 60s rest). Both use the authored alactic burst doses; the new selection gives boxing bag specificity. Existing real-bank tests verify greater bag diversity, retained aerobic selection, equipment/readiness/taper exclusions and bounded work. Historical bank digests are not refreshed: offline audit replay reverses only the exactly hashed Pressure Combination Rounds flag and corresponding identity binding, rejecting any other edit to that row.

API contract omissions, missing-context rehab fixtures, metadata replay drift in `api/services/xp_progress.py`, and the frozen pre-retirement complete-plan comparison reproduce on pulled Main `eadb97d2`. Their historical snapshots remain unchanged. Frontend navigation failures were observed in CI but not independently reproduced in this follow-up.
