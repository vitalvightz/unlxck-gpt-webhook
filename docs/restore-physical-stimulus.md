# Restore physical stimulus without another scheduling governor

## Exact intake and comparison method

The source is saved plan `da5b9dc9-ca7d-4866-a84b-b82fefede4d3`, inspected read-only, including its generation job's request and saved calendar context. The job started on 15 October 2026 at 12:36:40 UTC. The committed [intake fixture](../tests/fixtures/physical_stimulus/saved_intake.json) changes only the athlete's name. Programming inputs, equipment, injury description, primary selections, four-session answer, available days, contact request and fight date are preserved.

The production planner also received **`include_generation_day: true`** from the existing account workflow. Replaying just `PlanRequest` without this setting gives a different 17-date calendar. This comparison includes it: **18 calendar dates, D-17 through D-0**, matching the saved plan. The source requests four sessions, six available weekdays, Tuesday/Thursday hard sparring, Monday light combat, primary speed, secondary power and primary footwork weakness. Fatigue is low; weight is 75 kg, target 73 kg. The surface injury is approved as non-limiting, with no active exercise restrictions. The resolved contact cutoff remains D-17.

Three controlled Stage 1 replays use the same saved request, runtime setting, clock and seed **1**:

* Main: `a76fd0ef` (includes #2871, #2875, #2876 and subsequent Main fixes).
* Pre-#2875: `eadb97d2`, the parent of merged #2875; it still includes #2871.
* Proposed: this branch.

Production did not persist a random seed. These are controlled version comparisons, not a claim to reproduce an unknown stochastic production run. The stored production brief independently reports 10 physical appointments, three S&C sessions and unsatisfied speed/footwork build obligations, matching the controlled Main's counts and diagnosis. No saved programme was overwritten, deployed or regenerated in production. No provider was called.

The [comparison evidence](physical-stimulus-comparison.json) contains all five camps' selected exercise names, prescriptions, dated physical roles, exact cadence counts, contact classifications, goal witnesses, suppression codes and post-allocation deletions for all three versions. Its `revision` for proposed identifies the starting checkout; the proposed code is the PR diff, not that unchanged base SHA.

## Removed rules and their origins

| Rule / origin | Before | Proposed |
| --- | --- | --- |
| `enforce_total_session_budget`, **#2875** `792a1670`; goal-loss removal ranking added by **#2876** `6358dc3e` | Deletes already-selected physical appointments after composition, including across phase boundaries. | Deletes none. A single final reporting pass records actual over-target counts. #2876's removal-ranking branch disappears with the deletion mechanism; its membership/dose fidelity remains. |
| Whole-calendar goal-repair appointment rejection, **#2875**, retained by **#2876** | A compatible trial that delivers a goal is rejected for exceeding frequency. #2876 removed an earlier preliminary count check but retained the final veto. | Existing category allocation, eligibility, calendar and dose owners decide the trial. Existing sessions, selected complementary members, technical days and legal doubles can provide coverage; totals are reported separately. |
| `DEPRIORITIZE` plus high realised stress promoted to a hard goal-repair veto, **#2875** | A legal shared-calendar preference becomes a second categorical prohibition. | The shared calendar's actual `FORBID` remains binding; its legal graded verdict remains legal. |
| `combined_daily_stress_exceeded`, **#2875** | Counts ordinal hard/moderate stamps and rejects a daily combination independently of existing occupancy/contact rules. | Additional aggregate veto deleted. Existing exclusive S&C ownership, effective hard/reduced contact conflicts, actual contraindications and explicit technical stress remain authoritative. |
| `_apply_goal_maintenance_cap` / `goal_preservation_reduced_maintenance`, **#2875** | Applies the D-10 maintenance envelope to repair work at D-14 and earlier, on top of its actual countdown/readiness prescription. | Deleted. Repair mode does not impose another dose band; the canonical scheduled-day/readiness resolver prices the exercise. |
| `_late_primer_member_limit`, **#2871** `77d655c2` | Reapplies fatigue/cut/injury reduction as a member-count penalty after per-exercise dose control. | Duplicate count penalty deleted. Existing maximum three members, effective per-exercise doses, one-effort complements and measured calendar compatibility remain. |
| Support/fallback precedence in late primer composition, **#2871** | A non-fulfilling generic fallback or short-rest support accessory can lead, reducing the actual full-rest speed drill to one complementary effort. | Eligible physical bank work leads the alactic appointment by its existing structured dose classification. Generic fallback precedence is removed. No exercise or dose is invented. |
| Converted-hard provenance exclusion in `allows_light_combat_stack`, **#2436** `e6b53c7c`; stress-compatible extension in **#2875** | Declared light combat can share S&C, but the same resolved technical load from a hard declaration cannot. | `TECHNICAL_CONTACT` receives the same existing compatibility path regardless of declaration. Explicit high technical stress still rejects meaningful S&C; unstated stress uses the existing light technical intent. |
| Raw declared-weekday label exclusion, **#1973** `97cd44aa`; composite penalty **#855** `93b44ff4`; later penalty **#2405** `ec772b74`; freshness-day exclusion **#1991** `f0c09015` | Separately filters/penalises a weekday even after the resolved calendar permits that particular technical-only occurrence. | Duplicative declaration-based filters/penalties removed. Existing per-occurrence resolved calendar scoring remains. These older rules were changed because otherwise the requested converted-day behaviour remains unreachable. |
| Silent deletion in `ensure_declared_coach_combat_spine`, **#2231** `e17bb5c1` | Removes an app session on a declared hard weekday after compatible placement, even when that occurrence resolved to technical. | Technical conversion no longer triggers deletion. Effective hard/reduced contact and medical contact holds retain their existing protection. This is verified by the independent low-risk short camp. |

Focused review of **#2865** `78c5c001` retains final-calendar recomposition and authoritative loaded-work permission. **#2868** `e7806e7c` and **#2869** `a1878d0b` introduced adaptation-backed composition, effective evidence and repair; these owners are reused. Their selected-only strength composition could not use an eligible speed alternate, and their strength-only repair path could not accommodate the already-selected moving-footwork bank. The existing composer now substitutes an eligible alternate and fits the selected physical footwork drill inside the existing exercise cap. Footwork keeps the conditioning assignment/dose builder and ordinary evidence path, including when hosted by strength.

No new scheduler, configuration layer, schema, athlete questions or AI calls were added. Exercise banks, cards, UI and media are unchanged. Explicit technical stress stamps survive composition; only stale stamps written by the realised-composition owner are cleared.

## Saved programme: actual selected work

| Version | Physical appointments | Bank-composed strength/conditioning sessions | Cadence appointments / requested four |
| --- | ---: | ---: | --- |
| Pre-#2875 | 14 | 3 | 6, 6, 2 |
| Main | 10 | 3 | 4, 4, 2 |
| Proposed | 14 | 4 | **6, 6, 2 — exceeds the request in both full windows** |

The count includes coach technical appointments, standalone movement support and separate same-day sessions. Breathing, visualisation and tactical instructions count zero. Embedded movement support is not another appointment. The final cadence window is partial. S&C counts mean strength/conditioning roles with selected bank exercises; recovery appointments are counted in the physical total separately.

Main's selected S&C work is:

| Day | Exercise and effective prescription |
| --- | --- |
| D-13 | Jump Squat — **2 × 2 at max speed; rest 120 s**. Punch-Specific Max Isometric Hold — **1 hold × 10 s at 7/10 effort; full rest**. Range Gate-Score-Exit — **1 × 6 s; rest 120 s**. |
| D-6 | Explosive First-Step Cue — **2 × 5 s; rest 120 s**. Range Gate-Score-Exit — **1 × 6 s; rest 120 s**. Pendulum Jab-Cross Reset — **1 × 5 s; rest 120 s**. |
| D-1 | Shuffle-Angle-Set Cue — **2 × 4 s; rest 120 s**. This does not earn developmental goal credit. |

Proposed retains that work and adds:

| Day | Exercise and effective prescription | What it replaces / restores |
| --- | --- | --- |
| D-16 | **Jump-in-Place (Max Frequency) — 3 × 2 at max speed; rest 120 s** | Eligible alternate of the existing SPP Jump Squat slot; selected/dosed by the composer/resolver. |
| D-16, same strength session | **Step-Back Pivot Reset — 2 × 75 s moving technical sets, 60 s reset between sets; low effort** | The already-selected physical footwork bank drill, not an invented instruction or mental exercise. |
| D-4, recovery appointment | **Light Heavy-Bag Technical Tempo — 1 × 6 at RPE 5 maximum** | The post-allocation deletion is removed. The existing countdown/readiness resolver now prices this retained bank support member, avoiding an unresolved dose. |

Pre-#2875 had Jump Squat/isometric/Range Gate at D-12 rather than D-13; its isometric instruction was the authorised range **1 hold × 10–20 s at 7–9/10 effort**. Its D-6 selection was **Explosive Boxing Burst Intervals — 4–6 × 6–10 s, 75–120 s complete rest, RPE 8–9**. Its D-4 recovery member had no persisted effective prescription. Proposed keeps #2876's concrete authoritative doses instead of reverting to those ranges or letting the finaliser select exercises.

### Which filter caused each loss

* The retained candidate `neural_plus_strength_day` initially loses to the existing spar-first allocation. Main's speed repair then records appointment/category-cap refusals; the already-selected speed alternate is never composed into a scheduled development session. Proposed uses the retained candidate and existing composition/dose owners at D-16.
* `Step-Back Pivot Reset` was already in the eligible conditioning pool but had no matching standalone role in the build window. The strength-only fallback recorded `no_phase_pool_candidate_for_goal`. Proposed composes that exact bank drill alongside speed, with its own timed dose. It does not relabel a static stance hold as footwork development.
* Instrumented Main budget passes remove **Joint Prep at D-16**, **Footwork Walkthrough at D-11**, **Technical Shadow Rhythm at D-9**, and **Fight-week Freshness at D-4**, including the selected Light Heavy-Bag Technical Tempo member. These exact deletions and any available prescriptions are in the comparison evidence.
* Proposed does **not** restore Joint Prep as another appointment. The D-16 goal session **replaces that optional occupancy filler**, using the existing late-primer displacement definition in normal goal repair. Prescribed recovery and medical holds are not displacement candidates. The D-11/D-9 movement support and D-4 recovery survive; none is credited as new build stimulus.
* Main already had late neural/technical touches, including Explosive First-Step Cue at D-6. The regression was missing real **build-window** delivery, not an absence of every speed-related word throughout the programme. Both primary build obligations now have real D-16 witnesses; power maintenance remains satisfied.

### Technical dates and real restrictions

The saved programme's converted appointments at **D-17 (15 October), D-12 (20 October), D-10 (22 October), D-5 (27 October) and D-3 (29 October)** now admit compatible S&C through the existing policy. They remain technical appointments and count as **zero effective hard-sparring appointments**. The saved risk resolution still uses **D-17**, including its reduced-contact request and existing readiness evidence. The separate low-risk case uses **D-14**. Nothing moves or recreates hard contact inside either cutoff.

The non-limiting surface injury does not impose an active exercise prohibition in this replay. Contact medical holds, real exercise contraindications, explicit high-stress technical work, available training weekdays and existing scheduled-day/readiness doses remain binding. D-13 inward remains the existing finished tail; the planner does not invent new development there. Breathing/mental support cannot satisfy a physical development goal or prevent an approved goal session from taking an optional filler slot.

## Independent camp checks

| Camp | Physical appointments: pre / Main / proposed | S&C: pre / Main / proposed | Proposed cadence counts |
| --- | --- | --- | --- |
| Exact saved calendar, four requested | 14 / 10 / **14** | 3 / 3 / **4** | **6, 6, 2** |
| 28-day boxing variant, four requested | 18 / 16 / **20** | 6 / 5 / **8** | **6, 5, 4, 5** |
| 56-day boxing variant, four requested | 38 / 32 / **42** | 14 / 9 / **18** | **6, 6, 6, 5, 5, 5, 4, 5** |
| Independent recorded 52-day boxing intake from #2876, six requested | 51 / 44 / **55** | 20 / 13 / **24** | **7, 8, 6, 8, 8, 9, 6, 3** |
| Low-risk 10-day camp, four requested | 9 / 9 / **9** | 3 / 3 / **3** | **6, 3** |

**These proposed schedules are not compliant with their requested weekly totals wherever the listed count exceeds four or six.** The excess is deliberate and reported as a count advisory, not concealed by deleting work or rejecting the entire valid programme. This also exposes the pre-existing direct short-camp overrun.

All proposed selected goals pass their actual effective-dose contracts in these five camps. The 28-/56-day boxing variants restore both speed and footwork build delivery; the independent 52-day intake preserves speed build, power maintenance and conditioning maintenance. The short camp preserves maintenance instead of claiming new development. Its strength appointment moves from D-9 to **D-10**, now alongside the converted technical appointment, with its existing authorised prescription; the coach-spine regression would previously have silently deleted it. Effective hard-contact counts stay **0, 2, 10, 10, 0** respectively. Seed 7 additionally retains all selected goals in the saved and low-risk short cases.

## Reproduction and verification

From each checkout, run the same proposed tool file, so the importer uses that checkout's planner and the same intake fixtures:

```bash
python /path/to/proposed/tools/replay_physical_stimulus.py --output /tmp/comparison.json
python /path/to/proposed/tools/replay_physical_stimulus.py --seed 7 --case saved_plan --case low_risk_10_day --output /tmp/seed7.json
```

Regression coverage checks more real scheduled stimulus, bank/alternate provenance, unchanged effective exercise doses, concrete physical footwork, filler displacement, converted D-14/D-17 compatibility, explicit technical stress, medical contact blocks, and deterministic programme/card fidelity. Existing tests that assumed mandatory trimming now verify visible count discrepancies; tests of genuine prohibition and contraindication remain.

The repository's reviewed-bank identity test independently fails on unchanged Main with `Missing stable identity: conditioning_bank.json/61`; banks/manifests are outside this change and remain untouched. The fast dependency set lacks spaCy/NegEx, so no claim of full clinical NLP or full-suite CI verification is made. Final scoped results are recorded in the PR.

Final local verification: **810 planner/calendar/goal/fidelity tests passed** across 25 modules, plus **113 prescription/composition/injury-exclusion tests passed** across six additional modules (**923 scoped tests passed**). The single unrelated bank-identity test described above was explicitly deselected. Ruff and `git diff --check` passed. All three-version replays and the two seed-7 replays completed offline. No full-suite or hosted-CI result is implied.

The eight refreshed semantic calendar fixtures were checked against live Main: all contact projections are identical. Normal scheduled physical rows pass the shared calendar and their selected S&C members have effective prescriptions. See the [fixture review note](../tests/fixtures/calendar_integrity/README.md#physical-stimulus-restoration-review), which also separates pre-existing Main mental/support cadence drift from this change.
