# Strength pool depth audit

Bank rows: 339 (73 late-window-only). Phase tags: {'GPP': 144, 'SPP': 149, 'TAPER': 6}. Rows tagged for neither GPP nor SPP: 2.

## Eligible pool per phase and equipment tier

| Cell | Eligible | Anchors | lower_body_loaded | upper_body_push_pull | unilateral |
|---|---|---|---|---|---|
| GPP/full | 111 | 38 | 18 | 16 | 6 |
| GPP/home | 63 | 14 | 7 | 5 | 4 |
| GPP/min | 38 | 4 | 3 | 0 | 1 |
| SPP/full | 111 | 90 | 26 | 23 | 9 |
| SPP/home | 53 | 42 | 5 | 7 | 8 |
| SPP/min | 39 | 35 | 2 | 3 | 6 |

## Thin required-category cells (≤2 eligible anchors)

### GPP/min/upper_body_push_pull
- Currently eligible: **none**
- Existing rows a coach could review for this phase tag:
  - Band-Resisted Push Press — tagged SPP, vertical_push, anchor_power, cost moderate, equipment bands
  - Banded Row (Speed Focus) — tagged SPP, pull, anchor_power, cost moderate, equipment bands
  - Judo Throw Simulation (Band-Resisted) — tagged SPP, rotation, anchor_power, cost moderate, equipment bands

### GPP/min/unilateral
- Currently eligible: Single-Leg Forward Hops
- Existing rows a coach could review for this phase tag:
  - Single-Leg 45° Bound — tagged SPP, horizontal_jump, anchor_power, cost moderate, equipment bodyweight
  - Single-Leg Box Jump — tagged SPP, vertical_jump, anchor_power, cost high, equipment bodyweight
  - Single-Leg Depth Drop (Stick Landing) — tagged SPP, vertical_jump, anchor_power, cost high, equipment bodyweight
  - Single-Leg Reactive Shuffle — tagged SPP, lateral_reactive, anchor_power, cost moderate, equipment bodyweight
  - Single-Leg Rotational Hop to Balance — tagged SPP, rotation, anchor_power, cost moderate, equipment bodyweight

### SPP/min/lower_body_loaded
- Currently eligible: Cossack Squat (Dynamic), Wrestler Shot Drill (Repetitive)
- Existing rows a coach could review for this phase tag:
  - Cossack Squat — tagged GPP, squat, anchor_loaded, cost moderate, equipment bodyweight
  - Wall Sit (Knee-Friendly) — tagged GPP, squat, anchor_force_isometric, cost moderate, equipment bodyweight

## Bodyweight rows counted as `lower_body_loaded`

- Cossack Squat (GPP, squat)
- Cossack Squat (Dynamic) (GPP/SPP, squat)
- Single-Leg Spanish Squat Hold (GPP, squat)
- Single-Leg Step-Up Hold (Mid-Range) (GPP, lunge)
- Single-Leg Wall Sit (60°) (GPP, squat)
- Sissy Squat (GPP, squat)
- Squat Hold (Parallel) (GPP, squat)
- Step-Up (Bodyweight) (GPP, squat)
- Wall Sit (Knee-Friendly) (GPP, squat)
- Wrestler Shot Drill (Repetitive) (SPP, squat)

## Rows reclassified by movement normalization

The bank `movement` value is rewritten on the shared cached row the first time a
generation touches it, so these rows classify differently before and after.

| Row | Movement (bank → normalized) | Class | Gains | Loses |
|---|---|---|---|---|
| Atlas Stone Lift | compound → carry | anchor_power → support_accessory | — | — |
| Atlas Stone Load Isometric (120% max stone @ lap) | isometric → hinge | anchor_force_isometric | lower_body_loaded | — |
| Band-Resisted Clinch Knee Strike | unilateral → hinge | anchor_power | — | unilateral |
| Barbell Thruster | squat_to_press → squat | anchor_power | — | upper_body_push_pull |
| Cable Fly (High to Low) | dynamic → horizontal_push | support_accessory | upper_body_push_pull | — |
| Chin tuck nod | mobility → pull | rehab_support | upper_body_push_pull | — |
| Clinch Knee Strike (Band-Resisted) | unilateral → hinge | anchor_power | — | unilateral |
| Copenhagen Adduction | isometric → core | support_isometric → support_accessory | — | — |
| Couch Stretch | mobility → squat | rehab_support | lower_body_loaded | — |
| Defensive Level Change (Weighted Vest) | compound → squat | anchor_power | lower_body_loaded | — |
| Dumbbell Chest Fly | dynamic → horizontal_push | support_accessory | upper_body_push_pull | — |
| Glute Bridge Hold (Heavy Load) | isometric → hinge | anchor_force_isometric | lower_body_loaded | — |
| Grappler’s Bridge (Weighted) | isometric → hinge | support_isometric → support_accessory | lower_body_loaded | — |
| Lateral Resisted Band Walk | lateral → lateral_reactive | rehab_support | lower_body_ballistic, lower_body_explosive_anchor, lower_body_jump, lower_body_power | — |
| Lateral Shuffle Sprint | lateral → lateral_reactive | support_accessory → anchor_power | lower_body_ballistic, lower_body_explosive_anchor, lower_body_jump, lower_body_power | — |
| Single-Leg Wall Sit (60°) | isometric → squat | support_isometric | lower_body_loaded | — |
| Sled Push | compound → push | anchor_loaded → support_accessory | — | lower_body_loaded |
| Sled Push Isometric Hold | isometric → push | support_isometric → anchor_force_isometric | — | — |
| Slip Rope Drill (Band-Resisted) | unilateral → rotation | support_accessory | — | unilateral |
| Thai Pad Round Kick | unilateral → hinge | anchor_power | — | unilateral |
| Towel Hang | isometric → neck | support_isometric → support_accessory | — | — |
| Wall Sit (Knee-Friendly) | isometric → squat | anchor_force_isometric | lower_body_loaded | — |
| Wrestler Shot Drill (Repetitive) | compound → squat | anchor_power | lower_body_loaded | — |

## Generated camps

| Cell | Camps | Distinct selected | Picked in ≥80% | Blocks missing a category |
|---|---|---|---|---|
| GPP/full | 168 | 46 | 7 | {'unilateral': 1} |
| GPP/home | 168 | 27 | 6 | — |
| GPP/min | 168 | 18 | 4 | {'upper_body_push_pull': 168} |
| SPP/full | 168 | 40 | 6 | {'unilateral': 109} |
| SPP/home | 168 | 30 | 5 | {'lower_body_loaded': 36} |
| SPP/min | 168 | 23 | 3 | {'unilateral': 5, 'lower_body_loaded': 52} |

- **GPP/full** top: Z Press 100%, Cossack Squat 98%, Hang Power Clean 98%, Single-Leg Forward Hops 95%, Landmine Press 89%, Lat Pulldown 86%, Sled Push (Board) 85%, Single-Leg Lateral Squat Hold 79%
- **GPP/home** top: DB Alternating Incline Press (30-45°) 100%, Slow-Lowered Pull-Up 100%, Cossack Squat 100%, Cossack Squat (Dynamic) 100%, Single-Leg Forward Hops 100%, Kettlebell Swing 96%, Single-Leg Farmer Carry Hold 79%, DB Plyometric Push-Up (Hands on Dumbbells) 71%
- **GPP/min** top: Cossack Squat 100%, Cossack Squat (Dynamic) 100%, Single-Leg Forward Hops 100%, Brettzel Stretch 83%, Plank 80%, Psoas March (Banded) 79%, Plate Russian Twists 62%, Staggered Stance Hold 58%
- **SPP/full** top: Landmine Push Press 99%, Heavy RDL → Broad Jump 96%, Trap Bar Jump 89%, High Pull 87%, Barbell Thruster 83%, Woodchopper (Cable) 81%, Banded Row (Speed Focus) 78%, Med-Ball Rotational Slam 77%
- **SPP/home** top: Sprawl-to-Burpee 99%, Banded Row (Speed Focus) 98%, Jump Lunge (Alternating) 95%, Lateral Bound-to-Slip 93%, Ballistic Box Jump (Min Ground Contact) 83%, Band-Resisted Sprawl to Sprint 67%, Band-Resisted Push Press 65%, Tempo Split Squat (4-0-1) 57%
- **SPP/min** top: Banded Row (Speed Focus) 100%, Sprawl-to-Burpee 100%, Ballistic Box Jump (Min Ground Contact) 89%, Lateral Bound-to-Slip 75%, Jump Lunge (Alternating) 74%, Band-Resisted Sprawl to Sprint 74%, Band-Resisted Push Press 65%, Wrestler Shot Drill (Repetitive) 64%
