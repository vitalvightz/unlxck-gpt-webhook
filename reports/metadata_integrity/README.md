# Unlxck metadata integrity — PR 1

Investigation only. Baseline: Main `a91b0be3593b6887162866c19712ab087392d459`, after #2816, #2818 and #2820. No catalogue identity, source bank, generator, search rule, injury rule, schema or environment is changed.

All **2,855 entries** are accounted for across 14 explicitly enumerated live sources. The zero-row coordination shim is retained in the source inventory. Extraction audits **104 row fields**, **114 field paths including group context/nested dose**, and **292 configuration field paths** in **1978 records**. Prose, identity and evidence are included, not treated as taxonomy tokens.

The policy trace additionally retains **774 code-definition records** and **3318 definition value paths**, plus typed model annotations and constraints. Those paths include definition names/keys and are not extra exercise fields. Training has 234 distinct raw tags; all catalogue content has 236.

| Finding | Count | Meaning |
| --- | ---: | --- |
| Confirmed synonym groups | 5 | High-confidence reviewed MERGE decisions; not approval to edit consumers |
| Confirmed format variants | 2 | High-confidence RENAME groups; clinical joins still need migration review |
| Repeated identical risk/list tokens | 14 | Affected entries; dose ranges are not deduplicated |
| Suspected duplicate groups | 70 | Similar spelling/order/plurality only; unresolved |
| Compound/separator values | 21 | Raw string retained; separators do not establish AND/OR |
| Questionable assignments | 202 | Unique flagged rows excluding missing clinical metadata; screens require review |
| Incomplete clinical declarations | 1491 | Unique rehab rows with at least one screened null clinical field |
| Confirmed unused values | 0 | No unsupported unused claim |
| Vocabulary without raw live occurrence | 119 | May be inferred/normalised/configured; requires review |
| Normaliser alias collisions | 1 | Equivalent-looking inputs map to different targets; semantics require review |
| Referenced obsolete/historical sources | 2 | Compatibility and historical identity still consumed |
| Safety-critical dependencies | 35 | Reviewed workflow/function boundaries, not number of token mentions |
| Register issues | 196 | {"CORRECT": 1, "MERGE": 5, "PARENT/SUBTYPE": 4, "PRESERVE": 5, "RECLASSIFY": 3, "RENAME": 2, "REVIEW": 153, "SPLIT": 23} |

## Live sources

| Source | Entries | SHA256 (LF-normalised) |
| --- | ---: | --- |
| exercise_bank.json | 339 | `e37b723160b37b60c7f401124d6f0f0b4a11649ec99bcc2bd7ee43078fcf2937` |
| conditioning_bank.json | 236 | `0545f27a588598a73988f9874dca85dad103ab83cdc69c05f6b28605eb8c2537` |
| style_conditioning_bank.json | 277 | `44c27a2b6d7fda6616945e44992842c795c3447c1039581c63e802ff57899911` |
| style_taper_conditioning.json | 75 | `5b9aa72f2da66ba02424f847f786bb2d758c16b47ae422f64a0a98ff9bd62a4c` |
| technical_footwork_bank.json | 25 | `ea8fdb6eebc9649bc63c3b03562023b43d1ffeb144be18bbcc9617a372d8cba3` |
| coordination_bank.json | 0 | `4305c5e437f187d7b499b50bbb7b3f635d9f1a2aa93abce02723a308b0825b27` |
| coordination/universal.json | 12 | `7dace5870c80d79d724cd4360eded38bdb03f6c42cd9994768ae3cdaa98afeb2` |
| coordination/striking.json | 18 | `f658fa3113edf4bbe3cfbdec9a50788c5c908b4225f9767e0d15daf809f3bbff` |
| coordination/kicks.json | 12 | `ab258da761323d7a08be1aabeab75692d16ff289df90d1db8c453d3c27196399` |
| coordination/mma_transitions.json | 9 | `3a8767a6083e1ae51f108dfaab85c4bcc798c9f090002a673746a2029a5e5edc` |
| coordination/grappling.json | 7 | `655bfeb697845a93a8aa51353bc121a6fc6d8a07154e452eb1478d669c44964c` |
| rehab_bank.json | 1603 | `163436f5df81320746fad53ab66d20712a44d8f0a764ad70ff9137f77e9c89bf` |
| tactical_watch_bank.json | 183 | `a8acad21e369f7ef9f0d5eb706e5c177e6e825287cf197d6f2f05d35fb714be6` |
| fight_visualization_bank.json | 59 | `74ab5307eb3fff7df4e4b00cc68a8a7477191e542badf5aaad44bc2983bbea64` |

## Distinct raw values by field

Counts include explicit null/empty sentinels as values; `inventory.json` also separates nonempty counts and states. Group values count affected drills, not independent exercises. Configuration counts are separate, so policy arrays cannot inflate the 2,855 entry baseline.

| Field | Distinct raw values | Family |
| --- | ---: | --- |
| allowed_severities | 3 | safety |
| avoid_if | 5 | safety |
| ballistic_low_volume | 2 | programming/additional |
| block_if_fight_within_days | 2 | safety |
| body_region | 14 | classification |
| braking_demand | 3 | programming/additional |
| category | 28 | classification |
| cns_freshness | 2 | programming/additional |
| cns_load | 3 | programming/additional |
| combat_carryover | 1 | guidance/evidence |
| contact_level | 4 | safety |
| contraction_type | 4 | classification |
| contraindications | 14 | safety |
| cost_class | 3 | programming/additional |
| countdown_day | 5 | programming/additional |
| cue | 134 | guidance/evidence |
| cue_source | 4 | guidance/evidence |
| cut_buckets_allowed | 6 | safety |
| description | 75 | guidance/evidence |
| directionality | 6 | classification |
| dose | 2 | programming/additional |
| dose.duration_seconds | 2 | programming/additional |
| dose.reps | 2 | programming/additional |
| dose.sets | 2 | programming/additional |
| duration | 379 | guidance/evidence |
| duration_min | 9 | programming/additional |
| eccentric_cost | 3 | programming/additional |
| elastic_demand | 3 | programming/additional |
| equipment | 126 | equipment |
| equipment_note | 155 | equipment |
| evidence_notes | 83 | guidance/evidence |
| execution_intent | 4 | classification |
| footwork_pattern | 25 | classification |
| function | 7 | classification |
| goals | 10 | classification |
| group.location | 33 | safety |
| group.phase_progression | 7 | safety |
| group.type | 18 | classification |
| id | 1603 | identity |
| impact | 3 | safety |
| impact_cost | 4 | programming/additional |
| instructions | 811 | guidance/evidence |
| intensity | 15 | programming/additional |
| key | 300 | identity |
| lactate_load | 4 | programming/additional |
| landing_cost | 3 | programming/additional |
| late_fight_score | 20 | programming/additional |
| late_windows | 7 | safety |
| laterality_applicability | 4 | safety |
| load | 5 | safety |
| low_eccentric | 2 | programming/additional |
| low_impact | 2 | programming/additional |
| meaningful_stress | 2 | programming/additional |
| mechanical_risk_tags | 35 | safety |
| method | 8 | classification |
| mindset.anchor | 183 | guidance/evidence |
| mindset.context | 183 | guidance/evidence |
| mindset.focus | 183 | guidance/evidence |
| mindset.intent | 183 | guidance/evidence |
| mindset.reset | 183 | guidance/evidence |
| modality | 306 | classification |
| movement | 28 | classification |
| movement_cost | 3 | programming/additional |
| name | 2675 | identity |
| neural_primer | 2 | programming/additional |
| notes | 2051 | guidance/evidence |
| pain_ceiling | 3 | safety |
| phase_role | 1 | classification |
| phases | 3 | programming/additional |
| placement | 2 | programming/additional |
| pre_bout | 2 | programming/additional |
| primer_family | 4 | classification |
| priority_score | 20 | programming/additional |
| pro_tip | 1 | guidance/evidence |
| progress | 183 | guidance/evidence |
| progress_when | 4 | safety |
| qualities | 28 | classification |
| quality_stop_rule | 8 | safety |
| reactive_level | 3 | programming/additional |
| real_strength_maintenance | 1 | programming/additional |
| regress_when | 5 | safety |
| rehab_stage | 5 | safety |
| reps | 1 | programming/additional |
| reps_per_side | 2 | programming/additional |
| rest_sec | 27 | programming/additional |
| round_based | 1 | programming/additional |
| rounds | 10 | programming/additional |
| rpe | 7 | programming/additional |
| rpe_max | 3 | programming/additional |
| sets | 2 | programming/additional |
| side_rule | 2 | classification |
| soreness_risk | 3 | programming/additional |
| sport_specific | 2 | classification |
| sport_specificity | 3 | classification |
| sports | 8 | classification |
| stance_transition | 3 | classification |
| stop_when | 6 | safety |
| stress_class | 2 | programming/additional |
| styles | 8 | classification |
| subfamily | 20 | classification |
| support_only | 2 | programming/additional |
| system | 7 | classification |
| tactical_function | 15 | classification |
| tactical_styles | 12 | classification |
| tags | 236 | classification |
| target_regions | 34 | safety |
| target_tissues | 63 | safety |
| technical_complexity | 3 | programming/additional |
| total_minutes | 117 | programming/additional |
| type | 3 | classification |
| velocity | 4 | safety |
| weaknesses | 17 | classification |
| why | 293 | guidance/evidence |
| work_sec | 37 | programming/additional |

## Goal coverage

Existing usable Goal facets are **222/1,010**. Only **55 entries** declare `goals`. The remainder of current facets come from reviewed source aliases and the lower-body/explosive and defensive-function conjunctions in `training_library._prepare`. The 57 discovery concepts are separate and do not create goals.

| Bank | Training rows | Explicit goals | Current Goal facets |
| --- | ---: | ---: | ---: |
| exercise_bank.json | 339 | 55 | 102 |
| conditioning_bank.json | 236 | 0 | 64 |
| style_conditioning_bank.json | 277 | 0 | 0 |
| style_taper_conditioning.json | 75 | 0 | 18 |
| technical_footwork_bank.json | 25 | 0 | 11 |
| coordination/universal.json | 12 | 0 | 9 |
| coordination/striking.json | 18 | 0 | 6 |
| coordination/kicks.json | 12 | 0 | 3 |
| coordination/mma_transitions.json | 9 | 0 | 5 |
| coordination/grappling.json | 7 | 0 | 4 |

Existing explicit goals: `balance` (36), `coordination` (11), `injury_prevention` (4), `maximal_strength_maintenance` (6), `mobility` (37), `posture` (1), `power` (11), `readiness` (41), `skill_refinement` (8), `speed` (11).

`method` can support strength/power candidates, `system` endurance emphasis, `qualities` cue-response/control candidates, and `tactical_function` specific movement intent. These need exercise instructions and dose/context review. A keyword, equipment requirement, mechanical risk, broad sport tag or synonym alone cannot verify a goal. `injury_prevention` needs qualified review. Unknown is preferable to unsupported completeness.

## Confirmed decisions and safeguards

- `MI-5650eecead89` **RECLASSIFY** `body_region` ["full_body_stance"]: Combines whole-body anatomy and stance task in one region token. It is not a synonym for every full_body exercise. (1 rows).
- `MI-dee4a99b1939` **PARENT/SUBTYPE** `body_region` ["neck", "neck_vestibular"]: Neck anatomy and vestibular sensorimotor focus must not be merged into one adaptation or loading claim. (5 rows).
- `MI-059f2c702dee` **PARENT/SUBTYPE** `equipment` ["echo_bike", "assault_bike", "bike_erg", "air_dyne_bike", "stationary_bike", "recumbent_bike"]: Shared cycling family with different apparatus and loading. Existing echo/bike_erg aliases reflect broad athlete capability, not identical mechanics. (14 rows).
- `MI-1d52007d31ef` **RENAME** `equipment` ["double-end_bag", "double_end_bag"]: Separator variants of the same double-end boxing bag; distinct from heavy bag. Current equipment normalisation does not collapse this hyphen. (4 rows).
- `MI-265b3eee8385` **PARENT/SUBTYPE** `equipment` ["thai_pad", "thai_pads", "focus_mitts", "partner_mitts", "pads"]: Existing shared contract defines one handheld striking-pad capability. Exact implements remain distinct for exercise execution; foam pad and generic pad must not acquire striking-pad semantics. (106 rows).
- `MI-35204cfd5cf6` **MERGE** `equipment` ["weight_vest", "weighted_vest"]: Two names for a wearable weight vest; preserve loading instructions. (6 rows).
- `MI-45e540176268` **MERGE** `equipment` ["kettlebell", "kettlebells"]: Same apparatus identity with inconsistent plurality. A single/pair prescription must remain in instructions or a future explicit quantity, not be inferred from plurality. (26 rows).
- `MI-61c4e4c2bb3a` **PARENT/SUBTYPE** `equipment` ["bands", "resistance_band", "resistance_bands", "mini_band"]: Bands share a resistance-equipment family, but mini-loop and long resistance bands are not automatically interchangeable. Runtime broad aliases describe capability, not identical exercise setup. (61 rows).
- `MI-c8c1f7bc7749` **MERGE** `equipment` ["rower", "rowing_machine"]: Apparatus identity is the rowing ergometer; this does not make different session doses interchangeable. (8 rows).
- `MI-f400cf810ade` **MERGE** `equipment` ["battle_rope", "battle_ropes"]: Singular/plural equipment name for battle-rope apparatus. Rope Climb Sprints also carries battle_rope alongside climbing_rope: that association needs separate correction review; never equate climbing rope and battle ropes. (9 rows).
- `MI-59f362158821` **PRESERVE** `goals` ["power"]: A training objective, chosen execution method and force/loading mechanics cannot share evidentiary authority merely because they overlap. (11 rows).
- `MI-80e2ba230ae6` **PRESERVE** `source_file` ["rehab_archive/exact_duplicates.json"]: Historical completion identity recovery still reads archived drills. Exclude archive rows from the live inventory while preserving their original IDs and evidence. (0 rows).
- `MI-ebb9bb103dab` **PRESERVE** `source_file` ["coordination_bank.json"]: Empty compatibility shim is still referenced by conditioning, injury-bank collection and Stage 2 identity lookup. Preserve it until every reader has a tested replacement. (0 rows).
- `MI-b51b84fc851f` **RECLASSIFY** `system` ["cognitive", "hypertrophy"]: This system describes an adaptation or activity domain, not an energy system; runtime support-alias rules must be preserved. (2 rows).
- `MI-569d5639084c` **PRESERVE** `tags` ["reaction", "reactive", "mech_reactive"]: Cognitive cue-response and stretch/rebound loading are distinct. Existing broad TAG_SYNONYMS mapping reactive decision to reactive must be reviewed separately, not propagated into Goal verification. (308 rows).
- `MI-a793c6f54e62` **MERGE** `tags` ["adductor", "adductors"]: Both denote the hip-adductor muscle group in these source associations. Mobility and loaded adduction remain different exercises and doses. (7 rows).
- `MI-c53ebeb0917a` **RECLASSIFY** `tags` ["mech_ballistic", "mech_reactive", "mech_landing_impact", "mech_grip_support", "mech_systemic_fatigue"]: Mechanical mechanisms are duplicated in mixed tags and the risk array. Injury and planner consumers still read tags, so deleting copies would change safety behaviour. (692 rows).
- `MI-da9b41462c21` **PRESERVE** `tags` ["grip", "mech_grip_support", "mech_grip_intensive", "mech_grip_crush"]: Grip development, required hand support and intense/crush loading are different claims; source grip associations need per-row intent review. (228 rows).
- `MI-1af3d6723e44` **RENAME** `target_regions` ["upper back", "upper_back"]: Whitespace variant of the same region, with safety-sensitive exact regional comparisons and historical evidence validation. (52 rows).

`accuracy.json` retains every screened association with a stable identity, raw row hash and source pointer. Read it alongside the full raw row/group in `inventory.json`; no screen repairs a tag. Reaction cue omissions, grip demand, low-cost eccentric work and mixed energy emphasis may be legitimate. Landing/reactive risk on stationary rope drills and no-equipment pull-ups need priority review because they can affect eligibility and restrictions.

## Consumer evidence

`consumers.json` provides file/function/line receipts, reviewed workflow semantics, exact raw literal occurrences, dynamic getters, policy constants, source references and production import receipts. Register issues refer to those arrays by index. A literal mention is not automatically an exact comparison, and a missing literal is not unused: catalogue retention, generic ranking and dynamic getters still consume values.

The legacy coordination shim remains referenced by conditioning, injury-bank collection and Stage 2 identity lookup. The historical rehab archive is used by completion evidence recovery; removal would break historical identities. Old footwork-conditioning sources are excluded; current source-reference receipts show whether any active code still names them.

Source `avoid_if`, `contraindications`, `block_if_fight_within_days`, `priority_score` and `late_fight_score` have no named semantic reader in the scanned baseline. Generic raw retention/hash consumers remain. The register flags enforcement/ranking as unestablished rather than declaring these values unused. Case-sensitive GOAL_NORMALIZER lookup also maps `Speed` and `speed` differently before lowercasing the result; any canonicalisation must explicitly review that existing programming distinction.

## Reproduce and verify

```powershell
python tools/audit_metadata_integrity.py
python tools/audit_metadata_integrity.py --check
python -m pytest tests/test_metadata_integrity_audit.py tests/test_training_catalogue.py -q
```

Reports contain no timestamps or absolute paths. Extraction preserves original types, strings, list order and compound values. Source hashes normalise only checkout CRLF; tests independently check raw-byte immutability around execution. Frozen source, production-file, identity and media-key baselines prevent this investigation from changing runtime behaviour. The generator comparison exercises deterministic plan text and Stage 2 before/after audit use.

See [roadmap](roadmap.md) for ordered remediation and required before/after gates. See [verification](verification.md) for executed checks and limitations. The static scan and evidence screens do not certify every exercise scientifically or clinically; unresolved entries are explicit REVIEW decisions.
