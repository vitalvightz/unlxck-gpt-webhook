# Training library search review

30 Training queries with source-reviewed positive anchors and exclusion controls; not exhaustive relevance ground truth or scientific effect validation.

The audit covers **1010 Training entries**, **57 reviewed concepts** and **172 distinct phrases**. 1006 entries satisfy at least one rule; 1003 satisfy a non-equipment rule. These are vocabulary reach counts, not proof of relevant effects or complete intent coverage.

Goal-filter coverage remains **222/1,010**. Discovery synonyms do not add Goal values, change original tags, or grant prescription permission.

## Source vocabulary

Full token frequencies and unmapped tokens are in `training-library-search-audit.json`.

| Field | Entries | Distinct values | Values mentioned by rules |
| --- | ---: | ---: | ---: |
| tags | 1010 | 234 | 59 |
| qualities | 58 | 28 | 28 |
| goals | 55 | 10 | 7 |
| movement | 339 | 28 | 16 |
| method | 339 | 8 | 6 |
| system | 613 | 7 | 5 |
| modality | 504 | 306 | 14 |
| tactical_function | 25 | 15 | 12 |
| body_region | 37 | 14 | 7 |
| weaknesses | 55 | 17 | 7 |
| category | 339 | 28 | 10 |

A token being mentioned is not enough when its rule requires combined evidence. Risk/loading tokens, sport/style identifiers, phase restrictions and injury-prevention promises are not converted wholesale into fighter goals. Free-text modality values remain directly searchable; selected exact values and source names support the taxonomy.

## Query checks

**67/67 reviewed positive anchors found; 0/36 exclusion controls returned.** The initial PR implementation found 34/67 anchors and returned 1/36 exclusions against the same current sources. Anchor recall measures this finite review set, not exhaustive recall or precision across every result. Anchor ranks and the first five actual results are recorded in the JSON for review.

| Fighter query | Before → now | Reviewed relevant examples | Missed anchors |
| --- | ---: | --- | --- |
| punching power | 4 → 37 | Medicine Ball Hook Throw (#1); Standing Cable Punch Simulation (#2); Half-Kneeling Medicine-Ball Punch Throw (#7); Landmine Split-Stance Punch Press (#8); Max-Power Bag Burst (#9); Med Ball Chest Pass (Reactive) (#27) | None |
| hit harder | 0 → 37 | Medicine Ball Hook Throw (#1); Band-Resisted Straight Punch (#5); Landmine Split-Stance Punch Press (#8) | None |
| hand speed | 72 → 15 | Band-Resisted Jab-Cross Primer (#5); Explosive Boxing Burst Intervals (#2) | None |
| reaction speed | 59 → 50 | Call-and-Response Direction Change (#2); Cage Cut-to-Entry Choice (#1) | None |
| faster reactions | 0 → 48 | Call-and-Response Direction Change (#2); Cage Cut-to-Entry Choice (#1) | None |
| gas tank | 9 → 401 | Assault Bike Easy Gas Tank Ride (#1); 3-Min Round Intervals (Bag/Pads) (#4) | None |
| lasting rounds | 0 → 401 | 3-Min Round Intervals (Bag/Pads) (#60); Assault Bike Zone 2 Steady (#4) | None |
| round fitness | 0 → 218 | 3-Min Round Intervals (Bag/Pads) (#1); Heavy Bag Power Intervals (#65) | None |
| short bursts | 23 → 232 | Max-Power Bag Burst (#192); Assault Bike Sprint Intervals (#5) | None |
| foot work | 10 → 130 | Cage Cutting Footwork (#24); 45-Degree Angle Step to Jab Reset (#14) | None |
| change direction | 153 → 30 | Call-and-Response Direction Change (#1); Shot-Reshot Direction Change (#2) | None |
| create angles | 3 → 26 | 45-Degree Angle Step to Jab Reset (#1); Level-Change Feint to Angle (#5) | None |
| defensive movement | 17 → 17 | Defensive Movement Drill (#1); Defensive Movement Flow (#2); Sprawl Exit to Ring Angle (#11) | None |
| manage range | 14 → 15 | Intercepting Jab on Cue (#1); Teep Retreat and Re-Stance (#5) | None |
| cut off ring | 4 → 18 | Ring Cut-Off Walkdown (#1); Cage Cutting Footwork (#13) | None |
| stop takedowns | 4 → 23 | Defensive Sprawl Intervals (#2); Sprawl Exit to Ring Angle (#21) | None |
| recover stance | 96 → 54 | Switch-Step Stance Recovery (#2); Sprawl-to-Stance-Recover (#1) | None |
| kick balance | 46 → 16 | Kick-Catch Balance Reset (#1); Kick-and-Stick (#5) | None |
| single leg balance | 12 → 11 | Single-Leg Balance (Eyes Closed) (#1); Single-Leg Rotational Hop to Balance (#2) | None |
| core stability | 126 → 46 | Cable Pallof Press (#5); Anti-Rotation Press (#3) | None |
| shoulder stability | 62 → 6 | Standing scapular CARs (#1); Scapular Pull-Up Hold (#3) | None |
| grip endurance | 12 → 12 | Farmer Walk Hold (Static) (#2); Towel/Gi Row Isometric Hold (#7) | None |
| neck strength | 7 → 5 | Band-Resisted Neck Extension (#1); Neck Harness Flexion (#3) | None |
| loosen up | 0 → 50 | 90/90 hip switches (#1); Banded Hip Flexor Stretch (#38) | None |
| hip mobility | 12 → 10 | 90/90 hip switches (#1); Banded Hip Flexor Stretch (#2) | None |
| ankle mobility | 8 → 8 | Knee-to-wall dorsiflexion pulse (#2); Bent-knee soleus pulse at wall (#1) | None |
| hand foot coordination | 59 → 14 | Catch-Return-Step Out (#1); Double Jab to Exit Angle (#3) | None |
| get stronger | 0 → 148 | Isometric Mid-Thigh Pull (#2); Anti-Rotation Press (#9) | None |
| explosive legs | 17 → 33 | Box Jump (#2); Jump Squat (#5); Trap Bar Jump (#10) | None |
| low impact cardio | 0 → 94 | Assault Bike Easy Gas Tank Ride (#2); Air Dyne Bike Aerobic Base (#1) | None |

## Gaps and decisions

- The initial library returned four `punching power` matches. The revised results retain the two reviewed Goal aliases first, then punch-specific power, then labelled related rotational/upper-body power. Generic rotation, leg power and rebound risk alone do not qualify.
- Review exposed false positives from combining words across aliases, row/foot speed appearing for hand speed, neck work appearing for grip endurance, and mobility work appearing for neck strength. Intent phrases are now evaluated as complete evidence groups, with explicit exclusion controls.
- Some searches intentionally became smaller: `core stability` and `reaction speed` no longer accept unrelated mechanical-risk words scattered across source fields. Higher counts are not the acceptance target.
- Broad conditioning intents such as gas tank still span several modalities and energy systems. Filters narrow discovery; these results are not equivalent doses or interchangeable prescriptions.
- Source-body mobility records can cover several regions at once. Hip/ankle searches require both mobility and explicit regional evidence, but the source may still describe a combined support drill.
- Goal labels are source-backed discovery metadata, not scientific effect certification. Expanded search phrases are deliberately separate. No missing goal/anatomy/sport is inferred.
- Pain, injury clearance, concussion prevention and guaranteed performance outcomes are not assigned synonyms. Rehab remains a separate category requiring its pathway/stage and clinical rules.
- The review set does not establish complete relevance across all 1,010 records. Remaining unmatched tokens and unmapped entries are listed in the JSON for future reviewed additions.

## Reproduce

`python tools/audit_training_library_search.py`

`python -m pytest tests/test_training_library.py -q`
