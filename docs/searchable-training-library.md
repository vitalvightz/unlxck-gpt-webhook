# Searchable training library

Plan → **Find a Drill** opens `/plans/library`, including when the athlete has no active plan. Discovery is authenticated and read-only. The existing catalogue remains the only inventory; no exercise banks, planner logic, injury policies, rehab stages or database tables are changed.

## API and coverage

`GET /api/training/library` accepts `q`, `category` (`training` by default, `rehab`, `learn`), `type`, `goal`, `sport`, `equipment`, `body_focus`, `offset`, `limit` (1–50) and optional `revision`. `GET /api/training/library/entry?catalogue_id=...` returns current source coaching and existing curated media.

All 2,855 entries are accounted for: 1,010 Training, 1,499 Rehab, 346 Learn (104 care, 183 tactical, 59 visualisation). Duplicate names keep separate IDs and source/sport/style/pathway context. Four repeated pathway contexts also display their different original notes.

Names, descriptions, cues, notes, instructions, qualities, tags, movement, equipment and reviewed aliases are searched together. Every query term must match, with word prefixes and bounded spelling tolerance. Exact names rank first, then name phrases/partials, existing reviewed aliases, directly supported discovery concepts, technical metadata, literal descriptions and clearly labelled related work; ties sort by normalised name and stable ID. Recognised fighter phrases require a complete supported concept or strong literal match, so unrelated words scattered across risk tags cannot manufacture an intent. Search does not create metadata.

The process-local cache checks source, manifest and alias file stats and the reviewed discovery vocabulary on each request. A lock allows one rebuild per cache signature. The public pagination revision hashes source, manifest and alias contents plus the reviewed vocabulary; timestamps and deployment paths are excluded, and checkout line endings are normalised. Identical contents across server instances therefore accept the same pagination revision. Invalid identities or changes while loading return 503 without serving stale records. Pagination passes the returned revision; a changed revision returns 409 and the UI refreshes instead of mixing pages. Media uses the existing independent media cache, exact exercise keys, or canonical rehab drill IDs; Learn entries never acquire exercise demonstrations.

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

Foundation aliases remain unchanged. The two existing source-backed Goal context rules remain unchanged: **Explosive legs** requires both explicit `lower_body` anatomy and `explosive` tags; **Defensive movement** requires an explicit `defensive_exit` or `takedown_defense` tactical function. Broad rotation, sprinting or reactive mechanics do not acquire Goal labels. `Legs` is a display synonym for explicit `lower_body`, not an inferred quality.

## Reviewed discovery taxonomy

A separate taxonomy has 57 reviewed concepts and 172 distinct everyday phrases, each with explicit field/token evidence, conjunctions where needed, and a rationale. It includes energy systems, cue response, technical timing, footwork/range functions, mobility regions, strength/power and equipment language. Related rotational/upper-body power is discoverable for punching intent without receiving the Punching power Goal label. Search synonyms do not modify banks or foundation aliases.

The reproducible [30-query review](training-library-search-review.md) records 67/67 relevant anchors found (34/67 before) and 0/36 exclusions returned (1/36 before), along with rankings, misses and gaps. This finite review is not exhaustive ground truth. Full token frequencies and unmapped values are in [the audit data](training-library-search-audit.json).

## Example Training queries

These are search matches across original evidence and aliases, not counts of approved aliases or recommended prescriptions.

| Query | Matches | Examples |
| --- | ---: | --- |
| Punching power | 37 | Medicine Ball Hook Throw; Standing Cable Punch Simulation (reviewed aliases rank first) |
| Reaction speed | 50 | Cage Cut-to-Entry Choice; Call-and-Response Direction Change |
| Stamina | 206 | 3-Min Round Intervals (Bag/Pads); Aerobic power circuits |
| Core stability | 46 | Ab Wheel Rollout (Kneeling); Anti-Rotation Med Ball Slam |
| Shoulder control | 5 | Standing scapular CARs; Scapular Pull-Up Hold |
| Footwork | 139 | Cage Cutting Footwork; Footwork Ladder (Continuous Flow) |
| Explosive legs | 33 | Back Squat → Box Jump; Box Jump |
| Medicine ball | 34 | Half-Kneeling Medicine-Ball Punch Throw; Kneeling Single-Arm Medicine Ball Slam |
| Defensive movement | 17 | Defensive Movement Drill; Defensive Movement Flow |

`medicne ball` and `punchng power` also find results. Search handles punctuation such as the arrows in Learn names. The revised local 15-query samples had medians of 32-35 ms for punching power, hand speed and gas tank; this is not a production latency guarantee.

## UI and limitations

The mobile-first screen follows Today's grouped exercise rows, shared type icons, verified demo thumbnails, chevrons, typography tokens and white sheet CTA. Training, Rehab and Learn each occupy one third of the available width on desktop and mobile. `ExerciseGlyphIcon` is extracted unchanged from the structured renderer; its existing name/type selection logic stays in that renderer. The library chooses icons only from catalogue classifications.

Find a Drill and Log Training sit in equal-width horizontal tiles above the current camp and on plan detail. They remain independent of the training-history component. Plan uses Today's actual shared typography, surface, spacing and CTA tokens; the supplied mockup guides the arrangement rather than replacing the app's design system. View History opens the existing History route. The empty camp offers Quick Build Plan and Complete Intake without changing active-plan or saved-intake logic.

The profile row uses the athlete's existing safe `avatar_url`, falls back to initials on missing/failed images and links to the existing profile/photo editor. No fighter imagery or invented athlete photos are included.

Authenticated `GET /api/training/library/featured` selects one editorial Training entry with a currently served curated YouTube demo, preferring Medicine Ball Hook Throw, Check-Hook Pivot Burst, then Standing Cable Punch Simulation; a deterministic Training-only fallback handles unavailable preferred demos. It returns `entry: null` when no eligible media exists. The UI reuses Today's `ExerciseDemo` and the existing source-backed drill preview. This is an editor's pick, not measured popularity, athlete-specific advice or a new verified goal. Demo metadata is resolved at read time through the existing media cache; no database or source-bank writes are introduced.

One Filters sheet, category controls, reset/empty states and revision-aware pagination keep discovery compact. Match reasons distinguish expanded discovery from source Goal labels; related matches are labelled in the result rows, and the Filters sheet explains the distinction. Search is debounced and aborted requests cannot overwrite newer results. Preview reuses `InjuryDetailSheet`, `ExerciseDemo` and Today's coaching disclosure styling; existing Instructions/Cues stay visible, additional Why/Progress/Regress/Stop coaching is collapsed. No missing videos or explanations are generated.

2,580 entries have some existing coaching guidance; 275 do not. Equipment, sport and goal coverage is sparse in Rehab/Learn. Available search text can still match those records, while choosing an explicit filter intentionally restricts results to supported evidence. Name matches cannot bypass a user-selected equipment/sport filter. Several source tags are technical; the UI humanises separators but does not reinterpret their meaning.

## Boundary for Add Session

The next PR can reuse stable `catalogue_id`, current source/row revisions, search results, facets, preview, category and `selection_boundary`. These are discovery inputs. Every response has `prescription_allowed: false`.

A future server-side write must resolve the current ID again and evaluate current athlete, injury, phase, equipment and programming rules. Rehab requires the active pathway/stage and clearance. Learn/care is excluded from normal workout selection. The current search result, media availability, goal labels and a previously loaded preview grant no training permission.

## Verification

Backend tests cover inventory, ranking, aliases/false positives, missing metadata, filters, duplicate contexts, pagination, cached rebuilds, changes during loading, invalid identity failure, authentication, coaching and exact curated-media resolution. React tests cover debounce/abort races, stale-result removal and revision conflicts. Playwright covers no-active-plan entry, mobile/desktop layout, search/filter/preview, focus restoration, keyboard use, category boundaries, collapsed coaching, empty reset, recovery and axe accessibility.

The browser spec supports `LIBRARY_TEST_API` for live local integration against the same authenticated routes and real banks with a test auth/store. Default web CI uses isolated fixtures and blocks external services. Screenshot evidence is saved outside the repository. The isolated CI fixtures do not exercise Supabase credentials or YouTube. Separate local browser QA used the real source catalogue with test auth/store and public demo metadata read from the existing Supabase media table (read-only): the real YouTube thumbnail loaded, and Medicine Ball Hook Throw played and paused at its curated segment. Safari and production latency remain unverified.


### Final Plan UX verification

- Shared source: `today-screen.module.css`, `globals.css`, `ExerciseDemo`, the existing profile URL policy and native drill detail sheet. No new image assets or fighter artwork.
- Responsive checks: 320, 390, 589 and 1280px; the 589 × 1278 viewport matches the supplied mockup's native dimensions. Library category tabs also pass at 1440px, each filling one third of the available width.
- Visual comparison: checked the actual Today screen, supplied mockup and final browser renders for hierarchy, copy, surface colours, typography, icon geometry, horizontal alignment, spacing and video framing. The mockup is inspiration, not a pixel-copy of the app. Intentional differences follow the user's final instructions: no fighter image, one genuine curated video centred on desktop, concise action copy and profile details on one compact line. No popularity claim or invented athlete photo.
- Interactions: Log Training opens its existing form and restores focus; History still saves/edits/deletes training; profile opens its sheet and the existing photo editor; featured video plays/pauses and opens its source-backed preview; library supports search/filter/category/empty/retry flows. No horizontal overflow or axe violations in the checked Plan/library states.
- Local gates: 170 library/catalogue/media/schema tests, 10 web deployment tests (Python UTF-8 mode on Windows), 1,855 full frontend unit tests plus the final 5 Plan unit tests, 55 complete isolated browser tests, Ruff, generated schema, reproducible vocabulary audit, typecheck, lint and production build pass. Lint retains 47 existing warnings and no errors. Earlier full backend CI shards passed on the preceding PR head; updated-head CI is checked separately.
- The browser suite caught and reproduced the navigation/font stylesheet error; the CSP now permits the already-used Google Fonts stylesheet fetch on route transitions, scoped to `fonts.googleapis.com`. Nonce and frame restrictions are retained.
- Playwright Chromium supplied authenticated local fixture QA. The attempted IAB inspection reached the offline shell, so it could not verify this local authenticated test session. Evidence is retained outside the repository for the user's mobile/desktop review.
