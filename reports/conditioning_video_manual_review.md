# Conditioning video review — no approvals or replacements

Read-only snapshot: 2026-10-15, `public.exercise_media`, 732 rows. Existing
`api/services/exercise_media.py` and the YouTube player remain unchanged.
No model calls, media imports, status changes or keyword-based approvals occurred.

Exact key/alias matching finds 368 of the 591 current conditioning bank records
(366 distinct media rows). This is a diagnostic join, not the application's full
legacy-name resolution and not proof that every unmatched record lacks a demo.
One matched row, `sled-push-sprints` (`bVIdYDjw184`), is marked unavailable/not
found or private. Keep the existing cues-only fallback; investigate separately.

## Existing matches requiring visual review

Stored titles, sources and selected segments raise the following specific
questions. These are **review flags**, not claimed visual findings: the execution
environment's proxy denied YouTube access (HTTP 403) when a segment was requested.
Do not approve or replace any video from this table without watching it.

| Exercise/media key | Existing stored video and segment | Check against the actual bank drill |
| --- | --- | --- |
| `blast-double-sprints` | [Combine Pro-agility (5-10-5)](https://www.youtube.com/watch?v=U8aiqJ7O0dk&t=7s), 7–13s, EARTHSTRONG TRAINING | A field shuttle is not evidence of a wrestling blast-double entry/drive. Verify whether the selected segment contains the required movement at all |
| `reactive-mma-clinch-rounds` | [Muay Thai Clinch Inner Thigh Bump](https://www.youtube.com/watch?v=p6sbTMRCy-0&t=65s), 65–74s, Coach Vic | A single Muay Thai clinch action may not demonstrate the MMA reactive round's decisions/transitions |
| `strike-or-shot-counter-intervals` | [10 Count Boxing Pad Work Combo 44](https://www.youtube.com/watch?v=Dc60jmElaow&t=75s), 75–87s, Alpha Boxing Coach Academy | Verify the shot/takedown decision and counter, rather than just a pre-arranged boxing mitt combination |
| `clinch-position-flow` | [Rear Naked Choke From The Clinch](https://www.youtube.com/watch?v=A4wPZ8fARY4&t=40s), 40–52s, Bam Bam Martial Arts | Confirm the permitted position flow; a choke finish can introduce an unprescribed submission/contact element |
| `3-min-round-intervals-bag-pads` | [Saenchai and Singdam on heavy bags](https://www.youtube.com/watch?v=o3VgyUqPzko&t=3s), 3–13s, YOKKAO | Shared exercise key must not show kicks/knees to a boxer prescribed punching-only rounds. Neither a short bag clip nor its title proves the three-minute protocol |
| `range-recovery-intervals` | Two style-bank names normalise to this key | Boxing distance restoration and kickboxing/Muay Thai kicking-range restoration differ. Check both consumers before changing aliases/media |

The hill sprint match is titled “8 Second Hill Sprints” (`t62tRpLCBaA`, 105–112s,
Run Elite), consistent with the work duration on metadata review; actual technique
and terrain remain unverified. The rower match is Concept2's technique video
(`4zWu1yuJ0_g`, 94–103s), appropriate to review as **rowing technique**, not proof
that the athlete is following zone 3 or the 4/2 recovery structure. Reclassification
does not require changing either identity/media key.

## Small manual list for genuinely missing protocol demonstrations

The three new complete protocol keys have no existing exact/alias media rows in
the snapshot. Existing air-bike technique footage may be reusable after a person
checks setup, safe mounting/stopping, posture and arm/leg action. A protocol
explanation is supplementary; it is not automatically an exercise-technique demo.

| New bank entry | Reference/candidate to inspect | Manual acceptance requirement |
| --- | --- | --- |
| Air Bike Aerobic HIIT | [Boxing Science: Boxing Fitness](https://boxingscience.co.uk/boxing-fitness/), including its HIIT examples; [existing air-bike technique candidate](https://www.youtube.com/watch?v=PHReR7tC_tw&t=18s) (Live Lean TV, stored 18–29s) | Confirm technique is a compatible air bike, distinguish controlled four-minute output from maximal sprinting, and display 240s work / 120s recovery in the prescription |
| Air Bike Sprint Interval Training | [Boxing Science 30s sprint example embedded in the method article](https://www.youtube.com/watch?v=Njujebd3LQg&t=8s); [method/source context](https://boxingscience.co.uk/conditioning-for-boxing-the-boxing-science-method/) | A running/curve-treadmill example explains the protocol but cannot silently become the air-bike technique clip. Verify 30s maximal intent and 180s recovery independently |
| Air Bike Muscle Buffer Intervals | [Boxing Science buffering explanation](https://boxingscience.co.uk/boxing-fitness/); [method article's 2min/3min example](https://boxingscience.co.uk/conditioning-for-boxing-the-boxing-science-method/) | Find or record a reputable air-bike demonstration of the prescribed technique and pacing. Do not present a generic circuit or a short technique loop as a demonstration of the full buffering protocol |

Use the existing media review/import workflow for any eventual human-approved
row. Large-scale curation, identity collisions and unavailable-video repair are
separate work; this PR deliberately contains no media writes.
