# Unlxck read audit and measurement baseline

Measured 2026-10-26. Base: `f59427a20de5960e1e247586d1e54f3bb80c01be`, Main's merge of #3043. This change adds diagnostics and synthetic measurement tools only. No application query, cache, safety check, permission, schema or training behaviour was optimised.

## Evidence and completion status

The connected Supabase project `unlxckpdf`, also referenced by existing rollout documents, supplied read-only aggregate observations. No production athlete records, SQL text, tokens, filter values or medical content were exported. The SQL in [read-audit.sql](read-audit.sql) reproduces the aggregate snapshots. These statistics do **not** establish current per-user latency or post-#3043 performance: the statistics reset on **2026-09-15 18:09:12 UTC**, before that merge, with zero statement deallocations.

Local fixture runs are separate evidence. [local-baseline.json](local-baseline.json) records endpoint probes and fixed-clock Today service calls across five personas. [local-mutation-baseline.json](local-mutation-baseline.json) records existing assertion-bearing mutation workflows. HTTP counts in those files are TestClient requests, **not observed browser request counts**. `store_method_calls` count logical in-memory methods, including nested calls; a method can contain zero, one or several database operations. All database and frontend latency fields unavailable from that environment are explicitly null.

This is a usable instrumentation and synthetic baseline, but **the full acceptance criteria remain open**: no authenticated browser journey timing or live per-workflow database-attempt capture was collected. Do not interpret fixture call counts as answers to production read budgets, or declare the performance audit complete on that basis.

## Measurement definitions

| Measurement | Boundary | What it excludes |
| --- | --- | --- |
| Frontend `headersMs` | Existing fetch invocation to response headers | Body transfer, JSON parsing and rendering |
| Frontend `bodyCompleteMs` | Fetch invocation to existing JSON/text consumption | Rendering and later asynchronous presentation work; null when consumption isn't observed |
| Frontend capture `durationMs` | Explicit begin to explicit end after requests settle | Work outside that labelled capture |
| `responseBytes` | HTTP Content-Length, or null | Not necessarily decoded JSON size; may be compressed or absent |
| TestClient `roundtrip_ms` / `decoded_body_bytes` | Local request through response consumption | Browser, real network, real database, compression |
| `backend_ms` | Existing middleware processing through response creation | Streaming response consumption and network delivery |
| `data_api_attempt_ms` | Supabase HTTP client send, including normal response read | Separate SQL server execution and subsequent PostgREST JSON decoding; streaming sends end earlier |
| Database `mean_exec_ms` / `total_exec_ms` | PostgreSQL cumulative statement execution | HTTP, auth gateway, backend work, browser work; no percentiles |

Concurrent operation durations can sum to more than wall time. Backend HTTP attempts are not SQL statement counts: one RPC can execute many statements. RPC read/write classification is deliberately unknown. Background work after response creation may fall outside the request snapshot. Transport-internal retries and SQL inside RPCs are not separately visible; application retries that call send again are counted, including exceptions and unsuccessful HTTP responses.

## Instrumentation and privacy

Backend: `api/read_diagnostics.py` extends the HTTP client already supplied by `SupabaseAppStore.from_env`. One ContextVar lookup is the disabled send path. `UNLXCK_READ_DIAGNOSTICS=1` enables request-local collection through the existing combined middleware in `api/app.py`; the default is off in every environment, including production. There are no public debug endpoints or response headers. Use controlled captures; do not leave this enabled globally on a busy production deployment.

Each JSON `[read-audit]` record contains the FastAPI route template, method, backend duration, all Data API attempt counts, GET/HEAD counts by allowlisted table category, exact repeated GET/HEAD counts and safe per-attempt durations/failure flags. Unmatched routes and unknown tables get fixed fallback labels. Failed attempts remain in counts; no exceptions are swallowed or retried by diagnostics. No extra queries run. ContextVar state is copied into request worker threads; the shared counters are locked. Nested/concurrent request scopes remain separate.

Exact GET equivalence uses a request-salted HMAC of the complete URL, retained only in that request; URLs, SQL, parameters, headers, bodies and exception messages are never exported. Equivalent attempts are **candidates**, not proof of waste: failed attempts, authoritative post-write reads and deliberately refreshed data can repeat. Different filter/order parameter encodings may escape exact matching. No read deduplication is performed.

Frontend: `web/lib/api-measurements.ts` observes the existing `api.ts` fetch call and body consumption. An explicit `beginApiMeasurement(workflow, trigger)` returns a finish function. Trigger is `navigation`, `mutation` or `refresh`; no new fetching/cache framework exists. Use fixed, source-defined workflow names. Await the action and all expected requests before finishing. Overlapping captures are rejected so request attribution is not silently mixed. Start/end markers are harness-controlled; navigation and refresh causes are not guessed from HTTP methods. Identical safe-read identities use salted SHA-256, with only allowlisted endpoint patterns exported. Mutation bodies are never compared, logged or marked as identical.

Example inside a local test harness importing the module:

```ts
const finish = beginApiMeasurement("today_refresh", "refresh");
await refresh();
// Also await expected presentation requests before finishing a full-screen capture.
const measurements = finish();
```

The collector is inactive until explicitly started. It does not send analytics, traces or logs. It records failures/cancellations and unknown response sizes as null. Downloads and raw `Response` consumers may have headers timing only. Supabase authentication calls and fetches outside `api.ts` are not covered. Capture those separately in browser tooling before claiming total startup traffic. Existing HTTP/API logs predate this PR and are not made safe to export by this collector; export only the new safe record fields, not unrestricted raw logs.

## Reproduction and fixtures

Install the existing `requirements-dev-fast.txt` and run `npm ci` in `web`. No new dependencies were added.

```sh
python scripts/measure_read_baseline.py --runs 20
python scripts/measure_mutation_baseline.py --runs 10
python scripts/measure_diagnostic_overhead.py
```

Run from the repository root. These commands use the existing FakeStore, app factory and fixtures, with no database client or remote writes. Each endpoint repetition has a fresh seeded store. The app is reused within a scenario; app construction is outside timing. There is no deliberate warm-up; the raw runs expose first-run effects. Today service and application service clocks are fixed to 2026-06-03; framework HTTP clock fields may still use wall time. The mutation fixtures derive their training day from the application and use relative-day inputs; they are not historical production replays.

| Persona | Seed |
| --- | --- |
| Active camp | Existing 12-week camp fixture, five training days/week, two sessions/day |
| Renewable | Existing four-week Open Plan rest-day fixture, no fight date |
| Tracking without plan | Compliant seeded athlete, no plan |
| Injury history | Existing camp/intake injury fixture; initial sync precedes measurement |
| Historical plans | Five additional plans, one saved completion per plan, saved snapshot titles; active pointer restored |

Injury response history is additionally exercised by the existing rehab completion fixture in the mutation recorder. It explicitly disables clinical policies to test the legacy capture path; this is **not** a measurement of the current live clinical pilot.

The pytest recorder (`tests/read_audit_recorder.py`) is opt-in. It records the test-call boundary, excluding pytest fixture setup/teardown but including assertions and any fixture construction inside the test body. It restores every wrapped method afterwards. TestClient requests, method counts, response statuses, bytes and timings are retained; request/response bodies and dynamic URL segments are not. A failed measurement test prevents the repeated runner from publishing a replacement baseline.

Quantiles use the median for p50 and nearest-rank p95. Twenty probe runs and ten mutation runs have limited tail confidence; ten-run p95 is the maximum. This shared host also ran verification work, so compare only like-for-like reruns under controlled load. These measurements provide reproducibility checks, not production SLOs.

## Workflow baseline

The generated tables below summarise recorded local runs; full per-run method counts and request measurements remain in the JSON artifacts. Missing-plan detail responses are deliberate negative probes and must not be ranked as successful detail loads. HTTP probes establish route-level measurements, not complete UI workflow boundaries. The camp fixtures do not carry production-sized generation blobs and are not payload stress tests.

| Persona | Probe / service | HTTP calls | Logical store entries (first run) | Decoded response bytes (first run total) | p50 ms | p95 ms |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| active_camp | startup_home_probe | 1 | 3 | 1722 | 12.11 | 50.88 |
| active_camp | today_load_refresh_probe | 2 | 28 | 2808 | 86.72 | 101.14 |
| active_camp | plans_list_probe | 1 | 2 | 313 | 10.34 | 42.29 |
| active_camp | plan_detail_probe | 1 | 6 | 1198 | 49.71 | 75.99 |
| active_camp | history_page_probe | 1 | 4 | 38 | 6.75 | 38.66 |
| active_camp | history_pagination_probe | 1 | 4 | 38 | 8.81 | 41.67 |
| active_camp | xp_refresh_probe | 1 | 21 | 651 | 53.56 | 93.71 |
| active_camp | today_fixed_clock_service | 0 | 13 | 0 | 7.52 | 40.71 |
| renewable | startup_home_probe | 1 | 3 | 1705 | 13.19 | 46.85 |
| renewable | today_load_refresh_probe | 2 | 28 | 2738 | 38.57 | 75.97 |
| renewable | plans_list_probe | 1 | 2 | 296 | 7.86 | 41.01 |
| renewable | plan_detail_probe | 1 | 8 | 1185 | 19.42 | 51.44 |
| renewable | history_page_probe | 1 | 4 | 38 | 12.45 | 46.84 |
| renewable | history_pagination_probe | 1 | 4 | 38 | 7.43 | 35.92 |
| renewable | xp_refresh_probe | 1 | 21 | 651 | 22.27 | 55.6 |
| renewable | today_fixed_clock_service | 0 | 13 | 0 | 1.72 | 2.33 |
| tracking_without_plan | startup_home_probe | 1 | 4 | 1415 | 13.8 | 52.41 |
| tracking_without_plan | today_load_refresh_probe | 2 | 18 | 1612 | 39.13 | 68.07 |
| tracking_without_plan | plans_list_probe | 1 | 2 | 2 | 15.44 | 57.18 |
| tracking_without_plan | plan_detail_probe | 1 | 2 | 51 | 7.98 | 46.33 |
| tracking_without_plan | history_page_probe | 1 | 4 | 38 | 12.15 | 48.88 |
| tracking_without_plan | history_pagination_probe | 1 | 4 | 38 | 17.03 | 68.9 |
| tracking_without_plan | xp_refresh_probe | 1 | 15 | 651 | 13.16 | 50.46 |
| tracking_without_plan | today_fixed_clock_service | 0 | 8 | 0 | 0.18 | 1.71 |
| injury_history | startup_home_probe | 1 | 3 | 1750 | 11.67 | 40.11 |
| injury_history | today_load_refresh_probe | 2 | 46 | 11090 | 430.19 | 902.22 |
| injury_history | plans_list_probe | 1 | 2 | 313 | 9.08 | 46.21 |
| injury_history | plan_detail_probe | 1 | 6 | 2452 | 209.06 | 290.27 |
| injury_history | history_page_probe | 1 | 4 | 38 | 7.48 | 20.85 |
| injury_history | history_pagination_probe | 1 | 4 | 38 | 7.75 | 28.94 |
| injury_history | xp_refresh_probe | 1 | 30 | 654 | 96.23 | 107.8 |
| injury_history | today_fixed_clock_service | 0 | 22 | 0 | 76.91 | 85.77 |
| historical_plans | startup_home_probe | 1 | 3 | 1722 | 3.52 | 5.39 |
| historical_plans | today_load_refresh_probe | 2 | 28 | 2808 | 23.5 | 26.41 |
| historical_plans | plans_list_probe | 1 | 2 | 1873 | 3.31 | 4.71 |
| historical_plans | plan_detail_probe | 1 | 6 | 1198 | 12.81 | 17.72 |
| historical_plans | history_page_probe | 1 | 5 | 445 | 5.08 | 7.74 |
| historical_plans | history_pagination_probe | 1 | 5 | 445 | 5.82 | 8.28 |
| historical_plans | xp_refresh_probe | 1 | 21 | 651 | 25.44 | 42.95 |
| historical_plans | today_fixed_clock_service | 0 | 13 | 0 | 7.15 | 9.85 |

Mutation test workflows (10 repetitions, assertions inside boundary):

| Existing workflow | HTTP calls (first run) | p50 ms | p95 ms |
| --- | ---: | ---: | ---: |
| `test_successful_answer_removes_prompt_using_canonical_exposures` | 4 | 428.04 | 1119.58 |
| `test_added_exercise_can_be_edited_and_logged_with_its_updated_dose` | 8 | 2838.73 | 6683.42 |
| `test_retry_edit_delete_and_delayed_retry` | 11 | 772.24 | 2069.53 |
| `test_an_injury_reported_after_a_clean_check_in_refreshes_it` | 3 | 1032.34 | 2603.09 |

## Production statement and payload observations

[production-statements.json](production-statements.json) contains the top 15 matching profile/plan statement fingerprints by cumulative execution time. The safe category is a SQL-text substring classifier; a query referencing both tables can be classified as profiles. `wildcard_projection` is a pattern flag, not a full SQL parser. Neither flag proves caller attribution. Statement IDs are database query fingerprints, not user identifiers.

| Statement fingerprint | Category | Calls | Total execution ms | Mean execution ms |
| --- | --- | ---: | ---: | ---: |
| 8913771770534056826 | profiles, wildcard | 19,681 | 3,123,086.01 | 158.69 |
| -3259626848228504006 | plans, owner-scoped wildcard | 28,620 | 1,145,454.56 | 40.02 |
| 4198156773070080836 | profiles, wildcard | 4,793 | 446,311.05 | 93.12 |
| -8693842595633383058 | plans, owner-scoped wildcard | 8,094 | 435,892.90 | 53.85 |
| -6856317647541300064 | profiles, wildcard | 557 | 330,761.21 | 593.83 |
| 4874336862738510789 | plans, non-wildcard | 5,456 | 214,711.52 | 39.35 |

The first two historical counts are exactly unchanged in the current snapshot. This verifies that the statistics still exist, not that this traffic rate or latency persists after #3043. A follow-up snapshot/delta over a known observation window is required. This table ranks execution cost; within the captured subset, the highest-frequency entries are 28,620 owner-plan calls, 19,681 profile calls and 8,094 additional owner-plan calls. Other database activity is outside this profile/plan-focused ranking.

[production-sizes.json](production-sizes.json) measures a deterministic **first 50 plans by ID**, not a random sample or a full-population average. Mean row JSON: **1,344,546 bytes**, maximum **2,126,535 bytes**. Mean `planning_brief`: **577,539 bytes**; mean `stage2_payload`: **424,314 bytes**. Together those fields average roughly 75% of sampled row JSON. JSON representation/escaping can change exact shares. These are uncompressed database JSON materialisation sizes, **not API response transfer sizes**; the API may project/transform them. The observation supports the historical ~1.35 MB concern without claiming every detail endpoint returns that amount.

## Read and caller audit

[select-inventory.json](select-inventory.json) inventories select expressions in the main store and its compact/community/media mixins, with caller and line references. It includes explicit projections and wildcard reads. Queries and fields are unchanged in this PR.

| Caller/reference | Current read / required consumer data | Opportunity and evidence |
| --- | --- | --- |
| `api/store.py:_get_profile_by_id` (1191 before this PR), `get_profile`, `ensure_profile` | Full profile. Authenticated requests need profile/consent/role/timezone fields; workers have different requirements | Audit required fields per consumer before a dedicated projection. Aggregate profile cost is high, but the 10s cache means cumulative calls cannot be translated to reads per screen |
| `api/store.py:list_user_plans` (2041) | `PLAN_SUMMARY_SELECT`, including validator report | Already compact; measure validator-report size before assuming this is a full-plan problem |
| `api/store.py:get_plan_for_athlete` (2074) | Full owner-scoped plan | Required for some detail/admin consumers. Separate display/title/identity/training consumers later; retain ownership predicates and all authoritative safety inputs |
| `api/store.py:get_training_plan_for_athlete` (2120), `TRAINING_PLAN_SELECT` | Explicit training projection still includes `planning_brief`, plan text and structured plan | Audit which brief subfields drive deterministic fallback, rehab and schedule logic. Large aggregate brief size gives high potential impact, but removal without a contract is high risk |
| `api/routes/today.py:list_training_history` (261–288) | Full owned plan and structured-plan resolution per distinct plan in page, before checking frozen title | **Confirmed avoidable load/parse candidate**: the frozen snapshot title is preferred only after the read. Historical fixture includes five saved titles. Preserve ownership and fallback handling; do not bypass safety checks based on a snapshot |
| `api/services/training_history.py:training_history_page`, `_whole_day` | Two sources; may repeat reads with wider limits for a dense whole day | Intentional pagination correctness, not established waste. Measure dense-day histories separately before changing limits |
| `api/services/session_details.py` | Historical evidence projection explicitly avoids current-plan reads | Preserve this existing behaviour; history detail is not interchangeable with history list |
| `api/services/active_plan.py` | Active pointer plus owner-scoped plan resolution | Owner lookup is an authoritative boundary. Existing shared resolution prevents repeats in Today; do not remove checks to meet budgets |
| `api/services/today_service.py:_structured_plan_weeks`, `today_readiness_boundary.py`, `completion_reads.py` | Several callers of structured-plan resolution; build/mutation scopes already share successful results | #3043 tests confirm completion plan/history reuse and one structured-card validation per build. Counts of source call sites alone do not prove duplicate parsing at runtime |
| `web/app/page.tsx` (303, 350, 380); `web/app/plans/page.tsx` (225); `web/components/today/use-today-command.ts` (107 onward) | Independent Home/Plans/Today command requests, plus calendar detail reads | Cross-navigation repeated data **confirmed by source**, but unnecessary refresh frequency is not measured in a browser. Reconnect/error retry is intentional; classify trigger and freshness before consolidating |
| `web/components/history-screen.tsx` (671, 701, 718) | First page, cursor pages, corrected-row update then totals refresh | Mutation refresh has a user-visible purpose. Measure request overlap before changing it |
| `web/components/today/use-today-command.ts` | Every successful Today refresh dispatches an XP refresh before presentation reuse check | Confirmed trigger location; downstream debounce/cache may coalesce it. Browser capture is required to quantify unnecessary XP HTTP requests |

Repeated reads after a mutation can be required to observe authoritative saved state. Failure retries are also not optimisation targets by themselves. The injury fixture's multiple `list_injury_flags` calls include different filters and post-write reads: they must not be conflated into one equivalent read.

## Existing cache and invalidation boundaries

- `api/store.py:_ProfileRowCache`: per-process, 10-second default profile cache behind `ensure_profile`, bounded; write decorators invalidate affected profile rows. `get_profile` itself remains a full direct read. Zero TTL disables it.
- `api/services/today_command_cache.py`: 30-second default per-store/athlete/timezone view reuse for XP. GET Today rebuilds authoritatively. Existing middleware invalidates after non-neutral writes, including partial failures.
- `api/services/today_readiness_boundary.py` and `completion_reads.py`: request/build-local successful-read and structured-plan reuse; failure retries and write invalidation remain intact from #3043. Reward/XP state is not made cacheable by these scopes.
- `web/lib/api.ts`: per-token in-flight Me reads/updates, plus existing analytics-preference TTL. The existing fetch policy is `no-store`.
- `web/components/today/use-today-command.ts`: 60-second presentation cache keyed to token/plan/day/injury context; in-flight plan reuse and sequence guards discard stale presentation work. It does not replace authoritative readiness/save validation.

## Prioritised PR 2 / PR 3 plan and proposed budgets

| Priority / phase | Work | Expected impact | Risk | Confidence |
| --- | --- | --- | --- | --- |
| 1, PR 2 | History title/snapshot fast path with a compact ownership/identity contract and existing fallback | Avoid large rows and parsing per distinct historical plan | Medium: ownership and legacy evidence | High source evidence; fixture method counts, no live savings estimate |
| 2, PR 2 | Separate plan metadata/display projection from large generation/admin fields | Potentially large payload/TOAST reduction; measured sampled fields dominate row size | Medium | High field-size evidence; endpoint savings unmeasured |
| 3, PR 2 | Profile consumer/field audit and compact reads outside existing cache | High cumulative query-cost target | Medium/high: consent and auth consumers | High cumulative cost; current incremental traffic unknown |
| 4, PR 2 investigation | Identify minimal deterministic brief input contract for training-plan reads | Potentially remove hundreds of KB per row | High: readiness, fallback, rehab | High size evidence; low confidence that entire brief is removable |
| 5, PR 3 | Capture Home → Today → Plans → Viewer and XP triggers, then consolidate proven redundant presentation requests | Potential navigation and response-byte reduction | Medium: stale state/account isolation | Medium source evidence; browser frequency unmeasured |
| 6, PR 3 | Revisit dense-day pagination, history parsing, response compression/caching after measured traces | Workload-dependent | Medium/high | Low until dense histories and real payload transfer are captured |

Budgets are proposals, not enforced thresholds. Existing successful fixture invariants provide useful initial constraints: one active pointer and one owned plan resolution per ordinary Today build; one completion plan read and one post-save plan history read in the #3043 controlled completion test; no per-future-session completion reads; one Today refresh for injury plus delayed answer. A history list could target zero full-plan reads when usable frozen titles exist, while retaining required ownership verification and legacy fallback. No numeric production total-read budget is justified yet. Establish it from warm/cold, success/retry and persona-specific captures before PR 2 changes it.

For PR 2/3 validation, rerun exactly the same scenarios, compare counts/bytes first, then compare latency under the same host/load/cache conditions. Add a regression assertion only for a justified invariant. Keep authoritative safety inputs fresh and all ownership checks intact.

## Overhead, verification and remaining measurements

[diagnostic-overhead.json](diagnostic-overhead.json) contains seven rounds of 2,000 synthetic HTTP attempts per mode. Recorded medians were approximately 82.2 µs plain HTTPX, 70.7 µs disabled diagnostics, and 94.4 µs enabled. Noise is substantial; these differences are not a production overhead guarantee. Enabled collection adds HMACs, timing, locking and record allocation, plus one JSON log per request. This microbenchmark excludes middleware logging and SQL; production overhead is not established. The disabled frontend path forwards the existing fetch; enabled capture adds local hashing and timing without copying response bodies. Its overhead has not been separately benchmarked.

Verification results are recorded below after checks complete.

- 150 focused backend tests passed: diagnostics, completion/read amplification, store performance, rehab completion flows and external training. After final diagnostic changes, 53 PR #3043/request/diagnostic regression tests passed; seven diagnostic tests passed after the final equivalence/logging changes.
- Frontend full unit suite: 2,224 passed. Final collector tests: three passed, including failure/retry counts, redaction, disabled behaviour, overlap rejection, body timing and mutation distinction.
- TypeScript passed. Targeted ESLint passed; full ESLint had zero errors and 52 existing warnings.
- Production Next.js build passed using CI-safe local API and stub Supabase public values. An unconfigured build correctly refused missing `NEXT_PUBLIC_API_BASE_URL`; no environment files changed.
- Ruff, Python compilation and `git diff --check` passed for changed code.
- Existing Chromium browser regressions: 52 passed and 18 skipped without the seeded API. An isolated 390px Home run with screenshots passed. The seeded-API exercise suite passed three tests, then failed its hill-run edit assertion at `web/e2e/exercise-customisation.spec.ts:191` (expected closed details, observed open); its serial group left 14 tests unrun. The same assertion failed on a separately installed and built untouched Main worktree at `f59427a2`, confirming it predates this PR. Eight focused timer/session-final browser tests then passed against the seeded local API. Browser plugin unavailable; used repository Playwright against `http://127.0.0.1:3100`, synthetic API/auth responses, then the seeded in-memory API on localhost for exercise checks; no production writes. These checks verify behaviour, not live performance.
- Live PostgreSQL concurrency, schema credential gates, the complete backend/spaCy suite and deployment CI were not run. No schema changes need verification in this PR.

Still required before claiming full acceptance:

1. Browser scenarios with fixed fixtures, explicit UI-ready start/end markers, cold/warm caches and repeated runs for startup/auth/Home, Today, Plans/Viewer, History pagination and every mutation. Include Supabase auth traffic outside `api.ts`, render completion and slow/offline/retry paths.
2. Controlled staging captures of request-local Data API counts for the same personas. This checkout has no configured staging database/API credentials. No benchmark writes were made against the connected live project.
3. Before/after aggregate statistic snapshots over a known time window; correlate safe route categories to statement categories without raw user data. Collect server-side execution traces if per-request SQL p50/p95 is needed; cumulative means cannot supply them.
4. A representative large-response endpoint measurement with encoded and decoded bytes and compression noted. Current production numbers measure database materialisation only.
5. Dense same-day histories, current clinical-pilot injury/rehab paths, authentication refresh, real remote failures/retries, and separate frontend/middleware overhead measurements.

No faster-app claim is made by this PR.
