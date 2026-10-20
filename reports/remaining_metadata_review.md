# Remaining metadata findings: risk review

Reviewed Main `71e9d02e8f4035e1ec40bb8cafded5e08f5bbae3`. All **74** findings from PR #2853 are covered; the original audit and retirement review are unchanged.

One P2 defect is corrected: the missing `resistance_bands → bands` runtime alias. The authored fight-cutoff defect is reproduced but **deferred per the user’s instruction to ignore cutoff**. No source bank, historical identity, saved plan, clinical record, threshold, dose, cutoff or baseline is changed.

Classification counts: intentional distinction **22**, confirmed defect **2**, unresolved **35**, already resolved **2**, cosmetic inconsistency **13**.

The [machine-readable evidence](../tools/remaining_metadata_review.json) records field-specific active consumers, programming pathways, original affected-ID references, current source receipts, prior fixes and evidence required for every deferred finding. IDs always resolve through the immutable original register; its 74 findings overlap and must not be summed as distinct exercises. Receipts cover every affected row/group, not only the examples below.

## Verified correction and deferred safety defect

- **MI-e53d6bc86152 — P2, corrected here.** Existing aliases already accept singular and spaced plural resistance bands. The underscore plural affected four style rows and rejected ordinary `bands` access. Real Limb Collector candidate eligibility changes from absent to present. Full generator output matches the already-supported canonical source spelling after normalizing only the raw equipment representation; dose, scoring and safety logic are unchanged. Missing/irrelevant equipment still rejects it. Other three rows retain independent structure/phase/safety gates; alias repair is not a claim that every row becomes selectable.
- **MI-571670673453 — P0, deferred by user instruction.** On the reviewed Main, real source 5-10-15 Ladder and Squat-Clean/Burpee EMOM enter both the pool and selected work at D21/D18/D14 despite an authored 21-day cutoff, with SPP, conditioning/gas-tank priorities, no hard sparring and required equipment. D22/D35 allow them and D13 inward independently excludes them. Pad EMOM’s 10-day cutoff is already covered more conservatively by its D21–D14 opt-in. No cutoff implementation is included. Reopen as a bounded generation/scheduled-legality/editor change if requested.

## Prior work, preserved distinctions and scope

#2824 reviewed discovery equipment; #2825 fixed five actual apparatus sources and a strength fallback restriction. #2827 corrected seven bounded mechanical/cost rows. #2853 retired exactly 16 declarations. #2854 scoped editor contraindications; #2860 closed injury/microdose bypasses. #2882 later changed conditioning sources/selection, including neck-strength placement and controlled zone-3 rower metadata. #2897/#2898 repaired catalogue bindings. None of those edits is repeated here.

Clinical region keys, exposure validation, missing stage/dose/pain evidence, injury types, mat suitability, dumbbell quantities, all/alternative apparatus, cognitive reaction/rebound load and grip adaptation/hand demand remain separate. Broad mechanical findings with a few corrected rows remain unresolved as a whole. Sparse clinical declarations are not filled from exercise names. No audit-count target is used.

## All 74 dispositions

Consumer abbreviations: **M** injury/strength/conditioning mechanical gates and editor safety; **E** equipment normalization, generators, rehab and editor; **C** rehab lookup/selection, clinical policies and immutable exposure/progression; **G** library Goal facets and tag scoring; **T** movement/task, sport and discovery; **S** system normalization/quotas/dose; **R** raw source/hash retention versus computed scores. Exact paths and evidence are in the JSON.

| Finding | Risk / path | Classification | Evidence and disposition |
| --- | --- | --- | --- |
| `MI-1a6aaa4a34c4` · avoid_if | P0 / M | intentional distinction | Both real rows reject Achilles, ankle, calf and foot injuries through injury_match_details; recovery rope also rejects shin symptoms. |
| `MI-571670673453` · block_if_fight_within_days | P0 / M | confirmed defect | No production cutoff reader exists. |
| `MI-dae5ec15f5f9` · contraindications | P0 / M | unresolved | All 13 source rows retained. |
| `MI-ed7b3bb9bdca` · dose | P0 / C | unresolved | Legacy textual prescriptions and policy-owned bounded clinical doses are separate authorities; absent structured dose is not zero dose. |
| `MI-8a323c275807` · function | P0 / C | unresolved | resolve_drill_function preserves a legacy fallback; explicit functions rank session fit. |
| `MI-b30c402ba17a` · low_eccentric | P0 / M | already resolved | Slow-Lowered Pull-Up now has low_eccentric=false and unknown eccentric_cost. |
| `MI-d857b5615775` · mechanical_risk_tags | P0 / M | unresolved | Three stationary rope rows lost disproven landing/rebound risks and high impact in #2827. |
| `MI-f6ac4b3a763c` · mechanical_risk_tags | P0 / M | unresolved | #2827 corrected three stationary rope rows and Defensive Rhythm Flow. |
| `MI-3904a77f1745` · pain_ceiling | P0 / C | unresolved | Null is not an unrestricted pain ceiling. |
| `MI-2d2d6befa98b` · rehab_stage | P0 / C | unresolved | Missing stages retain legacy eligibility with no stage-specificity credit; stated unknown or higher-than-live stages are rejected, and only activated stages are live. |
| `MI-c53ebeb0917a` · tags | P0 / M | intentional distinction | Mixed tags and mechanical_risk_tags are compatibility copies, not an approved consolidation. |
| `MI-61ca7482f884` · target_regions | P0 / C | unresolved | hamstring/hamstrings lookup aliases are supplied by rehab_protocols, but target_regions is also a strict clinical exposure identity. |
| `MI-7e256062a1ab` · target_regions | P0 / C | unresolved | bicep/biceps lookup aliases are supplied by rehab_protocols, but target_regions is also a strict clinical exposure identity. |
| `MI-5650eecead89` · body_region | P1 / T | intentional distinction | Boxer stance weight-shift hold is balance/stance micro-support, not a full-body loaded lift. |
| `MI-ec3d257049b6` · body_region | P1 / T | intentional distinction | Lead/rear single-leg stance and lead-foot pivot use the same regional words but different stance/pivot mechanics and D1 eligibility. |
| `MI-0652eadb8203` · equipment | P1 / E | intentional distinction | Overcoming Split-Squat Isometric explicitly requires bands; bodyweight describes loading, not absence of apparatus. |
| `MI-2feb680cf7c6` · equipment | P1 / E | intentional distinction | Landmine press followed by medicine-ball chest pass requires both stations; reviewed ALL, not an alternative. |
| `MI-55bca90d64d1` · equipment | P1 / E | intentional distinction | Weighted-vest jump rope uses vest AND jump rope; reviewed ALL and both tokens survive runtime normalization. |
| `MI-5a11f50b939f` · equipment | P1 / E | intentional distinction | Partner gently tugs a band during single-leg stance; reviewed ALL bands plus partner, not interchangeable equipment. |
| `MI-71931d8b6978` · equipment | P1 / E | intentional distinction | Rotational sledgehammer strike requires hammer AND tire; reviewed ALL and runtime requires both. |
| `MI-7b3671fc562e` · equipment | P1 / E | intentional distinction | Both pin-pull isometrics require trap bar AND pins; reviews and contraindication notes agree. |
| `MI-a94cd8760e27` · equipment | P1 / E | intentional distinction | Band-resisted slip-rope drill requires bands AND rope in the reviewed setup; split tokens already enforce both. |
| `MI-ac585612eeee` · equipment | P1 / E | intentional distinction | Split-stance landmine press retains reviewed ALL barbell plus landmine. |
| `MI-f1ed6d5c05f8` · equipment | P1 / E | already resolved | All three actual source rows now declare towel+pullup_bar, pullup_bar, and towel respectively. |
| `MI-15596c12f262` · modality | P1 / T | intentional distinction | Gogoplata Grinder practices a flexibility-plus-submission setup, 10 shin-to-throat setups across five rounds. |
| `MI-1fbb489fff4b` · modality | P1 / T | intentional distinction | Range Reset Flow is controlled partner-cued aerobic restoration (120s/60s); Range Recovery Intervals repeats compressed-distance score/reposition at demanding glycolytic pace (60s/45s). |
| `MI-947031a5e18e` · modality | P1 / T | intentional distinction | Random Attack Counter Rounds uses unpredictable strikes/entries, glycolytic 4x120s; Reactive Clinch Position Rounds uses grips/frames/posture and controlled knee decisions, aerobic 4x120s. |
| `MI-9fca9706fdf6` · modality | P1 / T | intentional distinction | Movement Economy Rounds scores/repositions every 6-10s; Range Movement Flow scores every 10-15s at low pace. |
| `MI-e2c12769df3e` · modality | P1 / T | intentional distinction | Reactive Long-Weapon Burst permits jab/teep/long-kick choice, 7s/75s x6; Teep Intercept Burst is teep on unpredictable entry, 5s/60s x8. |
| `MI-f5af987cac2e` · modality | P1 / T | intentional distinction | Inside Decision Rounds (kickboxing/Muay Thai) includes checks/catches/kicks and controlled pad knee. |
| `MI-b51b84fc851f` · system | P1 / S | intentional distinction | Neck Harness Flexion/Extension now explicitly has placement=strength and structural-support notes (#2882). |
| `MI-cc45611f69c2` · system | P1 / S | unresolved | Mixed aerobic/glycolytic tags can describe threshold or mixed hard/easy work; system owns allocation while tags affect ranking. |
| `MI-001c17155974` · equipment | P2 / E | unresolved | Death by Carry (Sandbag/Sled) does not specify whether sled/carry is a substitution or combined station. |
| `MI-1277d8b6d1a1` · equipment | P2 / E | unresolved | Tabata Sprints (Treadmill/Row) lacks per-modality setup and dose evidence; runtime currently requires both tokens. |
| `MI-19c8f76c5408` · equipment | P2 / E | unresolved | Six slash rows mix proven ALL setups (hammer/tire, bands/partner, vest/rope) and UNKNOWN treadmill/rower plus partner/dummy. |
| `MI-25efc74f546c` · equipment | P2 / E | unresolved | Both bag isometric holds have bands,heavy_bag. |
| `MI-2a5bb39b6422` · equipment | P2 / E | unresolved | Towel Hang uses towel/bar but bar is not an explicit supported pull-up-bar identity. |
| `MI-487facf8df61` · equipment | P2 / E | unresolved | Towel/Gi Row Isometric Hold may require a particular anchor; source instructions do not establish the exact anchor/substitution. |
| `MI-58ae8898fd59` · equipment | P2 / E | unresolved | Seven comma rows mix reviewed ALL landmine/ball, trap-bar/pins and barbell/landmine with UNKNOWN towel/anchor and the two bag-isometric setups. |
| `MI-770609066613` · equipment | P2 / E | unresolved | mat and mats remain separate capabilities. |
| `MI-85d8031a7c6b` · equipment | P2 / E | unresolved | Heel-to-toe gait and side-hop stabilization list line/tape; instructions do not establish apparatus necessity and substitution for both tasks. |
| `MI-8c1eb5c925d8` · equipment | P2 / E | intentional distinction | Nineteen plural strength/conditioning rows include paired dumbbells; four singular clinical rows explicitly use one fixed clinician-selected implement. |
| `MI-a22b542d2011` · equipment | P2 / E | unresolved | Partner/dummy takedown drills lack evidence that inert dummy and reactive partner variants have equivalent feedback, safety and dose. |
| `MI-b4fe8a71fda0` · equipment | P2 / E | unresolved | Adductor Squeeze Isometric requires pad in the current runtime tokens; pad subtype/necessity/substitutions remain unreviewed. |
| `MI-e53d6bc86152` · equipment | P2 / E | confirmed defect | Four style rows require resistance_bands, while singular and spaced plural already normalize to bands. |
| `MI-0b14c481ac7e` · goals | P2 / G | unresolved | Missing explicit goals is not missing planner stimulus: active strength/conditioning score normalized tags, method/system and priority maps. |
| `MI-1489316c995a` · goals | P2 / G | unresolved | Missing explicit goals is not missing planner stimulus: active strength/conditioning score normalized tags, method/system and priority maps. |
| `MI-3f6518c161c8` · goals | P2 / G | unresolved | Missing explicit goals is not missing planner stimulus: active strength/conditioning score normalized tags, method/system and priority maps. |
| `MI-5b99d6aabf49` · goals | P2 / G | unresolved | The four source injury_prevention goals express broad intent. |
| `MI-5e032cc4ef78` · goals | P2 / G | unresolved | Missing explicit goals is not missing planner stimulus: active strength/conditioning score normalized tags, method/system and priority maps. |
| `MI-6d9fbdada3aa` · goals | P2 / G | unresolved | Missing explicit goals is not missing planner stimulus: active strength/conditioning score normalized tags, method/system and priority maps. |
| `MI-8220764db0f1` · goals | P2 / G | unresolved | Missing explicit goals is not missing planner stimulus: active strength/conditioning score normalized tags, method/system and priority maps. |
| `MI-8d61209ed2d8` · goals | P2 / G | unresolved | Missing explicit goals is not missing planner stimulus: active strength/conditioning score normalized tags, method/system and priority maps. |
| `MI-a95e6cf828d5` · goals | P2 / G | unresolved | Missing explicit goals is not missing planner stimulus: active strength/conditioning score normalized tags, method/system and priority maps. |
| `MI-dbebbb9b0c3e` · goals | P2 / G | unresolved | Missing explicit goals is not missing planner stimulus: active strength/conditioning score normalized tags, method/system and priority maps. |
| `MI-e85f5cef1705` · goals | P2 / G | unresolved | GOAL_NORMALIZER still maps Speed=>reactive and speed=>speed, while Speed / Reaction=>reactive. |
| `MI-ef4274109cb7` · goals | P2 / G | unresolved | Missing explicit goals is not missing planner stimulus: active strength/conditioning score normalized tags, method/system and priority maps. |
| `MI-a290d57c801b` · qualities | P2 / T | intentional distinction | Hand-Fight to Snapdown wins hand contact then steps/snaps; striking and transition rows prescribe specific foot/hand ordering (e.g. |
| `MI-16607bd82e68` · tags | P2 / T | unresolved | The 13 reaction-label rows include rhythmic bag work and sequences with sparse cue descriptions. |
| `MI-cd90e68e84e3` · tags | P2 / M | intentional distinction | Nineteen grips include carries, pulls, KB/snatch, stones, hammer and hand-fight tasks. |
| `MI-61102b0d5acd` · config.proposed.target_regions | P3 / C | cosmetic inconsistency | upper back/upper_back occurs in the review ledger proposed.target_regions. |
| `MI-76e10c33535c` · config.proposed.target_regions | P3 / C | cosmetic inconsistency | bicep/biceps occurs in the review ledger proposed.target_regions. |
| `MI-b984154148db` · config.proposed.target_regions | P3 / C | cosmetic inconsistency | hamstring/hamstrings occurs in the review ledger proposed.target_regions. |
| `MI-22246d2e47eb` · equipment | P3 / E | cosmetic inconsistency | thai_pad and thai_pads both resolve to the shared pads capability on athlete and exercise sides; foam pad remains separate. |
| `MI-5105da333463` · equipment | P3 / E | cosmetic inconsistency | plate and plates both normalize to plate; single fixed clinical plate dose/weight is still individually specified. |
| `MI-c2cd6e809977` · equipment | P3 / E | cosmetic inconsistency | All 15 entries describe a cable-station exercise, including cable-machine rehab curl/adduction. |
| `MI-7c48a23da18a` · group.location | P3 / C | cosmetic inconsistency | hamstring/hamstrings groups are reachable via normalize_rehab_location alias candidates. |
| `MI-dcb55fcc63b4` · group.location | P3 / C | cosmetic inconsistency | upper back/upper_back groups are reachable via normalize_rehab_location alias candidates. |
| `MI-7f4a8e3e3383` · late_fight_score | P3 / R | cosmetic inconsistency | late_fight_score has no named bank-field reader in current strength/conditioning scoring. |
| `MI-184cb43cf191` · modality | P3 / T | cosmetic inconsistency | rope/ropes describes battle-rope modalities on three named rows; the modality reader special cases run/sled/technical_footwork, not rope plurality. |
| `MI-8923cf7a861a` · movement | P3 / T | cosmetic inconsistency | The shared rotation discovery pattern explicitly accepts both rotation and rotational. |
| `MI-2810482d4d33` · priority_score | P3 / R | cosmetic inconsistency | priority_score has no named bank-field reader in current strength/conditioning scoring. |
| `MI-2c0f544f8bdb` · system | P3 / S | cosmetic inconsistency | normalize_system maps ATP-PCr, alactic and anaerobic_alactic to alactic. |
| `MI-9e5b23ccad9d` · tags | P3 / R | unresolved | The 119 original absent-live-row vocabulary candidates are not all unused. |

## Verification

All **44 focused regressions pass**, including the complete-programme comparison. Seven complete-programme controls (six in the regression fixture, plus a targeted BJJ/bands profile) cover GPP, SPP, taper, final day, shoulder injury, no equipment, sport/style and performance priorities. Both full plan text and complete Stage 2 payloads equal unchanged Main; per-case before/after digests are in the JSON. The four affected band rows also match existing canonical-input generator output across phases, fatigue and fight proximity. An isolated Limb Collector profile changes candidate eligibility from absent to present while retaining its selected fallback and source dose.

An existing targeted conditioning/equipment/restriction/rehab/generation-safety run passed **120 tests**. Bank audit, tag registry audit/migration/authority, rehab schema/migration/review/clinical checks and injury vocabulary checks pass (nine validator commands). Strict bank validation retains **860 errors, 276 warnings and 3 informational findings**, matching Main after checkout-path normalization. The retirement checker reports the same five stale protected-source receipts on both branches. They are not refreshed.

The historical metadata/canonical audit run has **6 failures, 39 passes and 13 setup errors**; every non-passing node reproduces on unchanged Main. Main's run including tag-retirement tests has **8 failures, 48 passes and 13 setup errors**. The setup root is historical replay drift at `api/contracts/external_training.py`; remaining failures include retained library/source contracts and original plan receipts. Ruff, compilation and whitespace checks pass.

The historical replay adapter gains only the original `training_context.py` bytes recovered from the frozen baseline's source revision and verified against its existing digest. All previous receipts remain exact. No expected-output fixture or baseline hash is refreshed.

The broad run covered **165 modules**: **5,874 passed, 22 skipped**, with 39 initial failures and 13 errors. One new coverage test started before the evidence file was written; it now passes. Replaying all non-passing nodes after completing the files gives **38 failures, 13 errors and 1 pass**. Every one of the **51 outstanding nodes** reproduces on unchanged Main (21 audit/tag nodes plus 30 additional exact cases). The JSON lists every node; they include historical equipment/mechanical receipts, conditioning dose/golden contracts, injury wrappers and fight-week/scheduling expectations. These remain outstanding; no safety restriction or baseline was changed to hide them.

All four affected style rows also pass the editor's real equipment gate after the alias repair, while no/battle-rope-only equipment still rejects them.

The separate editor/API suite has **59 passes and 1 failure**: `test_library_dose_fields_follow_the_drill[Tempo Hill Runs-intervals]` expects `dose_required=False`, but receives `True`. The same assertion fails on unchanged Main. Across both runs, **52 distinct outstanding failure/error nodes reproduce on Main**.
