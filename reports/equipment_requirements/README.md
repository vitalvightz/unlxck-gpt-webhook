# Equipment accuracy and requirements cleanup

Base: Main `b074e8a1` (#2823). Reviewed 25 affected source records across 20 overlapping audit findings: 14 corrected requirement projections; 11 explicitly unresolved.

The small shared review contract is the source-bound correction layer for library metadata. Two rope-climbing associations now return climbing rope only; three apparatus-dependent entries no longer qualify as No Equipment. Nine other compound records have evidenced simultaneous or single requirements. Original bank rows, hashes, permanent IDs, media keys and historical records remain unchanged (zero bank rows edited). Original values remain in `equipment_source` and requirement provenance.

SINGLE, ALL, ANY, OPTIONAL and UNKNOWN are supported as explicit groups. Multiple mandatory groups combine with AND. Current evidence supports only SINGLE, ALL and UNKNOWN; no row gains ANY/OPTIONAL or a quantity from punctuation, plurality or presumed substitutions. Partner requirements have a separate item kind. Unknown compounds remain whole legacy filters and display Equipment setup needs review.

Library apparatus filters describe discovery, including additional mandatory equipment shown on the result and preview. They do not certify complete athlete availability. Legacy compound filters resolve only their reviewed identities. Independent Sport/Goal/Type/Equipment filters retain AND and distinct exercise counts.

## Reviewed records

| Exercise | Decision | Relationship |
| --- | --- | --- |
| Towel Pull-Up Sprints | CORRECT | ALL |
| Rope Climb + Short Sprint | CORRECT | SINGLE |
| Rope Climb Sprints | CORRECT | SINGLE |
| Landmine Press → Med Ball Chest Pass | CORRECT | ALL |
| Trap-Bar Pin Pull Isometric | CORRECT | ALL |
| Towel/Gi Row Isometric Hold | REVIEW | UNKNOWN |
| Tabata Sprints (Treadmill/Row) | REVIEW | UNKNOWN |
| Counter-Striker Split-Line Punch Isometric Hold | REVIEW | UNKNOWN |
| Landmine Split-Stance Punch Press | CORRECT | ALL |
| Tandem Gait Walk (Heel-to-Toe) | REVIEW | UNKNOWN |
| Side Hop-to-Stabilize | REVIEW | UNKNOWN |
| 3-Minute Round (Striking + Takedowns) | REVIEW | UNKNOWN |
| Overcoming Split-Squat Isometric | CORRECT | SINGLE |
| Slow-Lowered Pull-Up | CORRECT | SINGLE |
| Slip Rope Drill (Band-Resisted) | CORRECT | ALL |
| Isometric Mid-Thigh Pull | CORRECT | ALL |
| Takedown Defense Drill | REVIEW | UNKNOWN |
| Rotational Sledgehammer Strike | CORRECT | ALL |
| Towel Hang | REVIEW | UNKNOWN |
| Reactive Band Taps (Partner) | CORRECT | ALL |
| Jump Rope (Weighted Vest) | CORRECT | ALL |
| Death by Carry (Sandbag/Sled) | REVIEW | UNKNOWN |
| Punch-Specific Max Isometric Hold | REVIEW | UNKNOWN |
| Towel-assisted lateral neck isometric | CORRECT | SINGLE |
| Adductor Squeeze Isometric | REVIEW | UNKNOWN |

Exact identities, row hashes, raw equipment, original audit references and decision evidence live once in `shared/equipment-requirements.json`.

## Distinct Training filter counts

| Value | Before | After |
| --- | ---: | ---: |
| `bands` | 36 | 39 |
| `bands/partner` | 1 | 0 |
| `bands/rope` | 1 | 0 |
| `barbell` | 38 | 39 |
| `barbell,landmine` | 1 | 0 |
| `bodyweight,bands` | 1 | 0 |
| `jump_rope` | 4 | 5 |
| `landmine` | 4 | 6 |
| `landmine,medicine_ball` | 1 | 0 |
| `medicine_ball` | 33 | 34 |
| `no_equipment` | 266 | 263 |
| `partner` | 225 | 226 |
| `pins` | 0 | 2 |
| `pullup_bar` | 7 | 9 |
| `rope` | 0 | 1 |
| `sledgehammer` | 4 | 5 |
| `sledgehammer/tire` | 1 | 0 |
| `tire` | 5 | 6 |
| `towel` | 1 | 3 |
| `trap_bar` | 7 | 9 |
| `trap_bar,pins` | 2 | 0 |
| `weight_vest` | 6 | 7 |
| `weighted_vest/jump_rope` | 1 | 0 |

Battle ropes stays at 7 and climbing rope at 2. All 30 reviewed fighter-query totals, ordered IDs and match labels are unchanged. All non-equipment facets are unchanged, including verified Goal coverage of 222/1,010.

## Consumer and programming boundaries

The library adapter consumes reviewed requirements. The planner continues consuming original banks through its existing normalizers and exact capability gates. `equipment_setup_available` is a conservative setup-only checker, tested for complete, partial and absent equipment; no prescription engine imports or calls it. It cannot grant clinical clearance. No planner eligibility correction is introduced in this PR. The original inaccurate bank associations remain visible as evidence and require a separately tested planner/source migration before this layer can change prescription eligibility.

- `fightcamp/equipment_requirements.py:45` — `project_requirements`
- `fightcamp/equipment_requirements.py:67` — `equipment_setup_available`
- `api/services/training_library.py:60` — `_prepare`
- `api/services/training_library.py:315` — `search`
- `api/services/training_library.py:370` — `preview`
- `api/services/training_library.py:171` — `get`
- `fightcamp/training_context.py:108` — `normalize_equipment_list`
- `fightcamp/training_context.py:136` — `normalize_athlete_equipment_list`
- `fightcamp/strength.py:1910` — `generate_strength_block`
- `fightcamp/conditioning.py:2999` — `generate_conditioning_block`
- `fightcamp/conditioning.py:1650` — `_conditioning_required_equipment`

## Verification

```powershell
python tools/audit_equipment_requirements.py --check
python -m pytest tests/test_equipment_requirements.py tests/test_canonical_metadata.py tests/test_training_catalogue.py tests/test_training_library.py tests/test_api_types_generated.py -q
```

The new baseline contains compact pre-change digests and filter counts, not per-exercise snapshots. PR #2822/#2823 reports are retained unchanged. The canonical audit replays its original projection without the later requirement layer; its consumer line references remain historical. One additive original UI receipt keeps the pre-change replay hash-exact. Full fixed-seed plan text/Stage 2 comparisons use the existing temporary-output harness. Executed checks and limitations are recorded in verification.md.
