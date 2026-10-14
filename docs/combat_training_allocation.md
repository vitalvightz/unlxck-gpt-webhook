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
- Goal repair counts the canonical occupied-day footprint instead of every support/coach row. It can re-place a retained dayless role or exchange two existing normal S&C sessions inside their original week/category budgets. Trials rerun composition, morph, prescription resolution and realised-load revalidation; accepted trials must improve the missing cadence window and preserve other selected coverage. It does not force a new high-stress repair into a deprioritised slot or reopen D-13 inward.
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
| Earlier saved constraints | Power missing D-2..D-15 | Power and speed maintenance covered; D-15 resolved power witness |
| Newer saved constraints | Power missing D-2..D-15 | Speed build, power maintenance and conditioning covered |
| Explicit 8 / 9 sessions | Input rejected against six available days | Accepted; selected speed/power/conditioning covered with legal technical doubles |
| High fatigue | Strength/power roles heavily suppressed | Reduced-dose maintenance retained where legal; fatigue remains active |
| Knee restriction, no jumping | Power absent | Injury-filtered strength/conditioning retained; speed/power explicitly deferred |
| Three hard contacts | Heavy compression | Effective contact compression retained; bounded legal exposures survive |
| Professional, no hard contact, nine sessions | Frequency rejected | Input accepted; speed build, power maintenance and conditioning covered with compatible S&C |
| Fight week | No development work | No development work; finished-tail safeguards retained |

Exact calendar baselines were refreshed for the intentional allocation and resolved-contact suppression changes. The direct D-13 semantic baseline is unchanged. Tests inspect scheduled bank identities, effective doses, coach-owned technical locks and shared legality, including a week where coverage must genuinely defer.

## Remaining limits

This does not remove publishing gates or claim all validation flags were programming defects. Underfill findings in the controlled earlier/newer replays fall from 4/7 to 2/1; explicit eight/nine cases retain three underfills. Some selected rep-based conditioning lacks enough canonical timed work to meet its phase workload floor. Increasing or inventing work to clear that flag would violate prescription authority.

The professional comparison also covers all selected goals after affected neighbours are recomposed, while retaining seven workload underfill findings. Further work belongs in authorised selection/composition and dose evidence, not another frequency restriction or a change to publishing gates.

Saved plans also carried `ambiguous_working_dose` and rendering/contact findings. Publishing policy and AI rendering were not changed. Live database records were read only; no plans were regenerated, deployed or modified.

Frontend QA: production build, TypeScript and lint passed (lint retains existing warnings). React DOM interaction verifies selecting nine sessions across six days and preserving it when availability changes; validation/round-trip tests cover both inputs. Starting the local server was rejected by automatic tool policy, so browser screenshots, layout and browser console checks are unverified.

Validation evidence: the 80-file sweep recorded 2,186 passes and three findings. All three were corrected (reviewed bank metadata, stale witness dates, and stale neighbour pruning); affected suites were rerun. Final runs include 119 goal-delivery/allocation tests, 49 calendar/goal-contract tests, 245 dose/calendar/repair tests, 83 conditioning/composition tests and 41 frontend tests. These suites overlap and their counts are not additive. Python imports, compileall, Ruff, diff checks, production frontend build, TypeScript and lint also passed.
