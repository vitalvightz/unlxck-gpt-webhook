# Searchable training library

Plan → **Find a Drill** opens `/plans/library`, including when the athlete has no active plan. Discovery is authenticated and read-only. The existing catalogue remains the only inventory; no exercise banks, planner logic, injury policies, rehab stages or database tables are changed.

## API and coverage

`GET /api/training/library` accepts `q`, `category` (`training` by default, `rehab`, `learn`), `type`, `goal`, `sport`, `equipment`, `body_focus`, `offset`, `limit` (1–50) and optional `revision`. `GET /api/training/library/entry?catalogue_id=...` returns current source coaching and existing curated media.

All 2,855 entries are accounted for: 1,010 Training, 1,499 Rehab, 346 Learn (104 care, 183 tactical, 59 visualisation). Duplicate names keep separate IDs and source/sport/style/pathway context. Four repeated pathway contexts also display their different original notes.

Names, descriptions, cues, notes, instructions, qualities, tags, movement, equipment and reviewed aliases are searched together. Every query term must match, with word prefixes and bounded spelling tolerance. Exact names rank first, then name phrases/partials, reviewed alias phrases, technical metadata and descriptions; ties sort by normalised name and stable ID. Search does not create metadata.

The process-local cache checks source, manifest and alias file stats on each request. A lock allows one rebuild per revision. Invalid identities or changes while loading return 503 without serving stale records. Pagination passes the returned revision; a changed revision returns 409 and the UI refreshes instead of mixing pages. Media uses the existing independent media cache, exact exercise keys, or canonical rehab drill IDs; Learn entries never acquire exercise demonstrations.

## Verified filters

Only values with source evidence appear; combined filters use AND. Facets reflect the query and other selected filters. No sport is selected automatically. An explicit sport filter includes explicit `universal` entries; missing sport remains searchable by name without that filter.

| Filter | Evidence | Training coverage | Rehab coverage | Learn coverage |
| --- | --- | ---: | ---: | ---: |
| Training type | Catalogue source classification | 1,010 | 1,499 | 346 |
| Goal | Original `goals`, foundation aliases, two narrow context rules below | 222 | 0 | 0 |
| Sport | Foundation's explicit `sports` / approved sport tokens in `tags` | 450 | 0 | 219 |
| Equipment | Known raw equipment only | 1,010 | 166 | 0 |
| Body focus | Known `body_region`, `target_regions`, anatomical `category` | 229 | 1,451 | 0 |

Coverage counts entries with at least one supported value, not permissions to use those entries. Unknown/null/absent equipment never earns **No equipment**. That value requires explicit empty equipment or only `none`/`bodyweight`. Difficulty is omitted.

Foundation aliases remain unchanged. Two discovery context rules extend the search vocabulary: **Explosive legs** requires both explicit `lower_body` anatomy and `explosive` tags; **Defensive movement** requires an explicit `defensive_exit` or `takedown_defense` tactical function. Broad rotation, sprinting or reactive-mechanics mappings are not added. `Legs` is a display synonym for explicit `lower_body`, not an inferred quality.

## Example Training queries

These are search matches across original evidence and aliases, not counts of approved aliases or recommended prescriptions.

| Query | Matches | Examples |
| --- | ---: | --- |
| Punching power | 4 | Medicine Ball Hook Throw; Standing Cable Punch Simulation (reviewed aliases rank first) |
| Reaction speed | 59 | Cage Cut-to-Entry Choice; Call-and-Response Direction Change |
| Stamina | 61 | 3-Min Round Intervals (Bag/Pads); Aerobic power circuits |
| Core stability | 126 | Ab Wheel Rollout (Kneeling); Anti-Rotation Med Ball Slam |
| Shoulder control | 9 | Standing scapular CARs; Ground-N-Pound Intervals |
| Footwork | 139 | Cage Cutting Footwork; Footwork Ladder (Continuous Flow) |
| Explosive legs | 17 | Back Squat → Box Jump; Box Jump |
| Medicine ball | 34 | Half-Kneeling Medicine-Ball Punch Throw; Kneeling Single-Arm Medicine Ball Slam |
| Defensive movement | 17 | Defensive Movement Drill; Defensive Movement Flow |

`medicne ball` and `punchng power` also find results. Search handles punctuation such as the arrows in Learn names. A local warm-query sample took approximately 17–32 ms; this is an observation, not a production latency guarantee.

## UI and limitations

The mobile-first screen follows Today's grouped exercise rows, shared type icons, verified demo thumbnails, chevrons, typography tokens and white sheet CTA. `ExerciseGlyphIcon` is extracted unchanged from the structured renderer; its existing name/type selection logic stays in that renderer. The library chooses icons only from catalogue classifications.

One Filters sheet, category controls, reset/empty states and revision-aware pagination keep discovery compact. Search is debounced and aborted requests cannot overwrite newer results. Preview reuses `InjuryDetailSheet`, `ExerciseDemo` and Today's coaching disclosure styling; existing Instructions/Cues stay visible, additional Why/Progress/Regress/Stop coaching is collapsed. No missing videos or explanations are generated.

2,580 entries have some existing coaching guidance; 275 do not. Equipment, sport and goal coverage is sparse in Rehab/Learn. Available search text can still match those records, while choosing an explicit filter intentionally restricts results to supported evidence. Name matches cannot bypass a user-selected equipment/sport filter. Several source tags are technical; the UI humanises separators but does not reinterpret their meaning.

## Boundary for Add Session

The next PR can reuse stable `catalogue_id`, current source/row revisions, search results, facets, preview, category and `selection_boundary`. These are discovery inputs. Every response has `prescription_allowed: false`.

A future server-side write must resolve the current ID again and evaluate current athlete, injury, phase, equipment and programming rules. Rehab requires the active pathway/stage and clearance. Learn/care is excluded from normal workout selection. The current search result, media availability, goal labels and a previously loaded preview grant no training permission.

## Verification

Backend tests cover inventory, ranking, aliases/false positives, missing metadata, filters, duplicate contexts, pagination, cached rebuilds, changes during loading, invalid identity failure, authentication, coaching and exact curated-media resolution. React tests cover debounce/abort races, stale-result removal and revision conflicts. Playwright covers no-active-plan entry, mobile/desktop layout, search/filter/preview, focus restoration, keyboard use, category boundaries, collapsed coaching, empty reset, recovery and axe accessibility.

The browser spec supports `LIBRARY_TEST_API` for live local integration against the same authenticated routes and real banks with a test auth/store. Default web CI uses isolated fixtures and blocks external services. Screenshot evidence is saved outside the repository. Real Supabase credentials, live YouTube playback, Safari and production latency are not exercised by those fixtures.
