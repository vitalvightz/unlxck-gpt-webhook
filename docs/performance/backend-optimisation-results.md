# Backend read reduction — PR 2

This PR is explicitly **stacked on `perf/read-audit-baseline` (#3044), commit `efa2deceb3304381a78c7aa8418cdcb90319b5b6`**. #3044 was still open when work began; Main remained at #3043's merge. No measurement infrastructure was omitted. Retarget this PR to Main after #3044 merges.

## Changes and evidence

### History: use saved evidence before current plans

`api/routes/today.py` now shares a small title resolver between `list_training_history` and `list_session_completion_history`:

1. Read a nonblank string title from the saved snapshot's session. Older title-only snapshots remain supported. When snapshot plan/session/day identities are present, they must match the completion; inconsistent evidence falls back.
2. For sufficient saved evidence, return the historical title with **no plan query or structured-plan resolution**. A deleted, archived or subsequently inaccessible current plan does not prevent access to the athlete's own saved history.
3. For legacy, incomplete or malformed snapshots, use the existing **owner-scoped training projection**. Resolve each distinct needed plan once per request. Keep the existing renewable calendar projection and generic/null fallback titles.

The history store reads remain scoped by authenticated athlete. Combined history also retains its explicit athlete filter. Previously the current-plan lookup was **not an authorisation gate for saved titles**: even if it returned None, the owned completion's saved title was returned. Removing that lookup does not authorise access to any current plan or another athlete's completion. Legacy fallback still queries by both plan ID and athlete ID; no unrestricted lookup replaces it. Snapshots and historical prescriptions are never rewritten. `session_details.py` is unchanged.

The completion-history route now also honours the saved title rather than looking up the present calendar first, as requested. Its title can therefore correctly differ from a renamed current prescription. All response models are unchanged. Non-dict snapshot containers still cannot be serialised by the completion-history response's existing dict contract; this PR does not silently delete persisted fields to make invalid records fit. The combined-history endpoint safely falls back for those containers.

Tests cover sufficient snapshots, matching/mismatched identities, invalid title types, empty/whitespace titles, deleted/archived/foreign plans, multiple plans, mixed manual/prescribed history, cross-athlete isolation, unchanged saved evidence, parse/read reuse, and retry on the next request after a failed legacy read.

### Purpose-specific reads

| Consumer | Previous read | New read | Required contract |
| --- | --- | --- | --- |
| History legacy title fallback | `get_plan_for_athlete`, `select("*")` | Existing `get_training_plan_for_athlete` | Full training calendar, IDs, plan text, brief, creation/fight dates and renewable fallback inputs remain present |
| Today landing interaction check | `get_latest_plan` | Existing `get_latest_plan_status` | Existence only; same athlete filter and newest-first order |
| XP `_safe_latest_plan` | `get_latest_plan` | Existing `get_latest_plan_status` | Found / not-found / unavailable only; returned plan contents are not read by this decision |
| Today `check_in_possible` | `get_profile` | `get_profile_compliance` | All seven inputs to `evaluate_profile_compliance`; fresh on each read |

The existing compact latest-plan implementation keeps its retry/full-row rolling-deploy fallback. Tests demonstrate transient compact failures are counted and retried, followed by the existing full fallback; no exception or unavailable state is reinterpreted as "no plan". This failure path is intentionally not a read-count improvement: the forced-timeout test records three failed compact attempts followed by one full fallback attempt.

`get_plan`, `get_plan_for_athlete`, `get_latest_plan`, full viewer/admin/generation consumers, `PLAN_SUMMARY_SELECT`, identity reads and shared `TRAINING_PLAN_SELECT` remain intact. The updated [select inventory](select-inventory.json) includes the new compliance projection and current source locations. The caller table above documents changed use sites not visible from select expressions alone.

### Remove the duplicate overlap read

`api/services/active_plan.py:_active_plan_overlap` previously called `resolve_active_plan`, which reads the active pointer and owned plan, then fetched that same owned plan again based on an obsolete summary-projection comment. The resolver actually returns the owner-scoped row with both `structured_plan` and `planning_brief`. There are no intervening writes. Overlap evaluation now uses that row directly.

Both eligibility checks, ownership predicates, date-range/renewable checks, pause/replace choices, pointer writes and rollback behaviour remain unchanged. No result is shared across requests or across a mutation. This removes one full-plan Data API attempt and one equivalent repeated read per ordinary two-plan overlap check.

## Profile contract and caching

The primary `require_profile → ensure_profile → _map_profile_row` path is unchanged, including bootstrap and the existing 10-second profile cache and write invalidation. It produces the application's broad `ProfileRecord`, not just an authentication boolean. Narrowing it without separating its response/bootstrap consumers would create unnecessary compatibility risk.

| Purpose | Existing required profile fields | Change |
| --- | --- | --- |
| Authentication identity and authorisation | `id`, `email`, `role`, `access_status`; effective-admin check uses role and email | None |
| Compliance | `date_of_birth`, `terms_version`, `terms_accepted_at`, `health_data_consent`, `health_consent_at`, `health_consent_withdrawn_at`, `health_consent_version` | New exact projection for the isolated Today compliance consumer |
| Timezone and presentation | `athlete_timezone`, `athlete_locale`, `appearance_mode` | None |
| Public profile/bootstrap response | Names, username/history, styles, stance, professional status/record, onboarding draft, avatar, nutrition, starting path/habits/revision, trial acknowledgement and creation/update timestamps | None |
| Generation worker helpers | DOB-derived age/minor policy, saved timezone and generation-day override information from stored profile | None; these helpers remain separate future work |

`PROFILE_COMPLIANCE_SELECT` contains **all** evaluator inputs, even those not used by the final health-consent boolean. It is scoped by profile ID and deliberately has no new cache. Tests compare the entire compliance verdict against a full row for grants, withdrawal, explicit refusal, superseded consent versions, missing DOB and invalid timestamps. A subsequent withdrawal is observed immediately. Existing missing-row/read-error behaviour is preserved; these optimisations do not grant clearance when a read fails. Auth bootstrap is not routed through the compact method.

## Why the training brief remains

The History fallback now excludes generation/admin fields such as `stage2_payload`, using an already-established projection. It retains `planning_brief` and the shared training projection is not narrowed further:

- `effective_structured_plan.py` rebuilds absent/malformed cards from deterministic planner truth and recovers source doses/coaching. It reconciles calendar spines, coach-led contact and custom/generated provenance using the brief.
- `open_plan_timeline.py` uses `open_plan_spec`, athlete timezone/creation context and weekly templates to project renewable schedules.
- `today_service.py` and `exercise_overrides.py` inspect custom-plan metadata; readiness, rehab and exercise execution consume the resulting authoritative prescription and intake inputs.
- Completion, streak and XP paths depend on the same schedule/session identity and deterministic fallback. #3043's build/mutation scopes still share successful results and invalidate around writes.

A small shared brief projection is **not established** by these contracts. Removing the whole field would be unsafe; passing selected nested pieces without proving their transitive consumers would be a risky partial redesign. Tests verify full versus training-row equivalence for dated/renewable calendars and real deterministic reconstruction from missing/malformed cards. All training/safety fields remain unchanged.

## Reproduction and measurement boundaries

Artifacts:

- [Before](backend-before/local-baseline.json) and [after](backend-after/local-baseline.json): #3044's same 40 probes, all five personas, 20 repetitions.
- [Before mutation workflows](backend-before/local-mutation-baseline.json) and [after](backend-after/local-mutation-baseline.json): #3044's four workflows, 10 repetitions, including completion/delayed rehab and exercise editing/logging.
- [Before Data API measurements](backend-before/data-api.json) and [after](backend-after/data-api.json): 20 repetitions through real Supabase query builders with `httpx.MockTransport`, using #3044's request diagnostics.
- [Comparison data](backend-comparison.json): complete counts, data sizes, logical method entries, and p50/p95. No SQL counts are inferred from FakeStore calls.

The before source is an untouched worktree at `efa2dece`, with only the new measurement script/transport fixture copied in. The after source is this backend change. Both use the same host, Python environment, fixture sizes and cache setup. The final before/after runs were sequential, after verification jobs finished, rather than competing with those test jobs. Fresh stores are seeded for each repetition; application setup is outside probe timing. The original scripts' embedded `base_commit` describes their historical audit baseline; this comparison's before source is explicitly `efa2dece`.

The Data API fixture gives two plans synthetic padding of 578 KiB in the brief and 424 KiB in the Stage 2 payload and a profile a 64 KiB draft. These are **controlled test inputs, not production measurements or estimates of every plan**. The transport applies the production query's projection, owner filters and limit and records actual JSON bytes returned to the client. It refuses writes. No real database, network latency, query planner, RLS, compression or server-side RPC work is modelled.

Only the selected Data API methods are real in this harness: plan reads, profile reads and history source reads. Auth/bootstrap and unrelated methods remain in-memory. The quoted attempt counts describe that instrumented subset, **not the entire production route budget**. The production History reduction is specifically the two removed owner-plan requests for this two-plan fixture. Tests additionally check the owner predicates independently.

Backend time is captured from #3044's request middleware for endpoint scenarios; outer request duration includes TestClient response handling. Direct overlap/consent probes have service duration and Data API attempt duration but no HTTP/backend duration. These durations are separate from SQL execution time, which is unmeasured. p50 is the median and p95 uses nearest rank. No warm-up is discarded. Ten-run p95 is the maximum, with limited tail confidence.

Example commands from each checkout (run before and after sequentially under the same conditions):

```sh
python scripts/measure_read_baseline.py --runs 20 --output /absolute/output/local-baseline.json
python scripts/measure_mutation_baseline.py --runs 10
# Copy its generated local-mutation-baseline.json to the appropriate before/after directory.
python scripts/measure_backend_reads.py --runs 20 --output /absolute/output/data-api.json
python scripts/compare_backend_baselines.py
```

## Before/after results

| Scenario | Data API reads before → after | Full plan reads | Compact plan reads | Equivalent repeated reads | Retrieved bytes before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| history_frozen | 4 → 2 | 2 → 0 | 0 → 0 | 0 → 0 | 2,109,341 → 1,867 |
| history_legacy | 4 → 4 | 2 → 0 | 0 → 2 | 0 → 0 | 2,109,217 → 1,241,237 |
| completion_history_frozen | 3 → 1 | 2 → 0 | 0 → 0 | 0 → 0 | 2,109,339 → 1,865 |
| landing | 1 → 1 | 1 → 0 | 0 → 1 | 0 → 0 | 1,053,737 → 102 |
| overlap | 3 → 2 | 2 → 1 | 0 → 0 | 1 → 0 | 2,107,533 → 1,053,796 |
| consent | 1 → 1 | 0 → 0 | 0 → 0 | 0 → 0 | 66,347 → 268 |

All 20 repetitions have the same read/byte counts per scenario. The four-row, two-plan frozen History fixture removes both plan reads. Legacy History still reads two plans, using the existing training projection; no fallback validation was skipped.

| Scenario | Outer/service p50/p95 ms before | Outer/service p50/p95 ms after | Backend p50/p95 ms before | Backend p50/p95 ms after | Endpoint bytes before → after |
| --- | ---: | ---: | ---: | ---: | ---: |
| history_frozen | 52.82 / 79.78 | 5.43 / 6.69 | 49.21 / 70.44 | 3.21 / 4.14 | 1637 → 1637 |
| history_legacy | 53.63 / 77.82 | 48.04 / 61.78 | 49.80 / 72.56 | 44.74 / 58.28 | 1654 → 1654 |
| completion_history_frozen | 49.22 / 55.88 | 5.49 / 8.16 | 46.19 / 53.08 | 3.03 / 3.73 | 2066 → 2085 |
| landing | 27.22 / 37.65 | 5.94 / 7.42 | 23.08 / 33.82 | 3.45 / 4.73 | 58 → 58 |
| overlap | 30.34 / 39.52 | 20.14 / 36.16 | not HTTP | not HTTP | not HTTP → not HTTP |
| consent | 1.32 / 3.30 | 0.55 / 0.74 | not HTTP | not HTTP | not HTTP → not HTTP |

The comparison JSON additionally retains p50/p95 for Data API attempt duration separately. SQL execution time is not measured.

The saved-title combined History response bytes are unchanged. Completion-history response size can increase slightly because previously missing/current titles are now correctly supplied from saved evidence. Legacy History endpoint bytes remain unchanged: the reduction is in database-to-backend transfer, not the API response.

The original FakeStore probes do not model Supabase transfer costs. Their compact methods can delegate to a full in-memory method and the new compliance method copies seven dictionary fields. Consequently logical call entries can increase by one despite unchanged database attempt counts and reduced actual projection bytes. They must not be advertised as extra SQL operations or real-world speedups. All neutral/negative timing results are retained below and in the comparison JSON.

| Persona | Original probe | Logical entries before → after (first run) | Endpoint bytes before → after (first run total) | p50 ms before → after | p95 ms before → after |
| --- | --- | ---: | ---: | ---: | ---: |
| active_camp | startup_home_probe | 3 → 3 | 1722 → 1722 | 3.44 → 4.04 | 4.30 → 6.35 |
| active_camp | today_load_refresh_probe | 28 → 30 | 2808 → 2808 | 23.74 → 25.19 | 52.10 → 41.44 |
| active_camp | plans_list_probe | 2 → 2 | 313 → 313 | 3.36 → 3.96 | 4.89 → 7.81 |
| active_camp | plan_detail_probe | 6 → 6 | 1198 → 1198 | 12.96 → 13.69 | 19.22 → 17.61 |
| active_camp | history_page_probe | 4 → 4 | 38 → 38 | 3.67 → 3.95 | 4.75 → 6.67 |
| active_camp | history_pagination_probe | 4 → 4 | 38 → 38 | 3.53 → 3.43 | 5.80 → 5.24 |
| active_camp | xp_refresh_probe | 21 → 23 | 651 → 651 | 25.86 → 25.29 | 33.72 → 33.35 |
| active_camp | today_fixed_clock_service | 13 → 14 | 0 → 0 | 8.37 → 8.33 | 12.99 → 15.20 |
| renewable | startup_home_probe | 3 → 3 | 1705 → 1705 | 4.82 → 4.19 | 6.08 → 6.74 |
| renewable | today_load_refresh_probe | 28 → 30 | 2738 → 2738 | 18.19 → 12.56 | 23.30 → 28.41 |
| renewable | plans_list_probe | 2 → 2 | 296 → 296 | 4.13 → 3.49 | 5.56 → 5.08 |
| renewable | plan_detail_probe | 8 → 8 | 1185 → 1185 | 8.53 → 6.16 | 11.13 → 8.76 |
| renewable | history_page_probe | 4 → 4 | 38 → 38 | 3.94 → 4.07 | 6.26 → 6.84 |
| renewable | history_pagination_probe | 4 → 4 | 38 → 38 | 4.54 → 4.98 | 6.97 → 8.91 |
| renewable | xp_refresh_probe | 21 → 23 | 651 → 651 | 9.29 → 9.08 | 16.53 → 14.66 |
| renewable | today_fixed_clock_service | 13 → 14 | 0 → 0 | 2.23 → 1.66 | 3.76 → 2.13 |
| tracking_without_plan | startup_home_probe | 4 → 4 | 1415 → 1415 | 4.12 → 3.50 | 5.90 → 4.60 |
| tracking_without_plan | today_load_refresh_probe | 18 → 18 | 1612 → 1612 | 8.92 → 7.68 | 11.40 → 9.40 |
| tracking_without_plan | plans_list_probe | 2 → 2 | 2 → 2 | 3.93 → 3.64 | 4.86 → 4.56 |
| tracking_without_plan | plan_detail_probe | 2 → 2 | 51 → 51 | 4.15 → 3.51 | 5.73 → 5.01 |
| tracking_without_plan | history_page_probe | 4 → 4 | 38 → 38 | 4.44 → 3.47 | 6.78 → 5.83 |
| tracking_without_plan | history_pagination_probe | 4 → 4 | 38 → 38 | 3.90 → 3.72 | 6.53 → 4.89 |
| tracking_without_plan | xp_refresh_probe | 15 → 16 | 651 → 651 | 4.73 → 4.85 | 7.19 → 7.95 |
| tracking_without_plan | today_fixed_clock_service | 8 → 8 | 0 → 0 | 0.11 → 0.10 | 0.33 → 0.34 |
| injury_history | startup_home_probe | 3 → 3 | 1750 → 1750 | 5.75 → 5.59 | 10.01 → 8.76 |
| injury_history | today_load_refresh_probe | 46 → 48 | 11090 → 11090 | 211.03 → 185.75 | 391.41 → 486.70 |
| injury_history | plans_list_probe | 2 → 2 | 313 → 313 | 5.68 → 5.46 | 7.02 → 7.22 |
| injury_history | plan_detail_probe | 6 → 6 | 2452 → 2452 | 146.27 → 142.94 | 162.34 → 160.48 |
| injury_history | history_page_probe | 4 → 4 | 38 → 38 | 5.62 → 5.51 | 6.77 → 6.36 |
| injury_history | history_pagination_probe | 4 → 4 | 38 → 38 | 5.60 → 5.19 | 7.56 → 5.89 |
| injury_history | xp_refresh_probe | 30 → 32 | 654 → 654 | 107.32 → 109.47 | 137.21 → 415.27 |
| injury_history | today_fixed_clock_service | 22 → 23 | 0 → 0 | 81.99 → 92.44 | 92.05 → 109.41 |
| historical_plans | startup_home_probe | 3 → 3 | 1722 → 1722 | 5.24 → 4.36 | 7.20 → 6.20 |
| historical_plans | today_load_refresh_probe | 28 → 30 | 2808 → 2808 | 31.08 → 29.49 | 38.24 → 35.89 |
| historical_plans | plans_list_probe | 2 → 2 | 1873 → 1873 | 4.59 → 4.67 | 9.27 → 5.98 |
| historical_plans | plan_detail_probe | 6 → 6 | 1198 → 1198 | 15.63 → 23.66 | 20.55 → 30.36 |
| historical_plans | history_page_probe | 5 → 4 | 445 → 445 | 5.02 → 4.11 | 6.33 → 5.74 |
| historical_plans | history_pagination_probe | 5 → 4 | 445 → 445 | 6.10 → 5.06 | 7.40 → 6.41 |
| historical_plans | xp_refresh_probe | 21 → 23 | 651 → 651 | 25.75 → 28.47 | 34.88 → 46.70 |
| historical_plans | today_fixed_clock_service | 13 → 14 | 0 → 0 | 7.52 → 9.05 | 8.91 → 10.92 |

| Existing mutation test workflow | Logical entries before → after (first run) | HTTP calls before → after (first run) | p50 ms before → after | p95 ms before → after |
| --- | ---: | ---: | ---: | ---: |
| `test_successful_answer_removes_prompt_using_canonical_exposures` | 60 → 61 | 4 → 4 | 236.73 → 244.17 | 273.25 → 295.27 |
| `test_added_exercise_can_be_edited_and_logged_with_its_updated_dose` | 86 → 87 | 8 → 8 | 1716.48 → 1918.89 | 1890.67 → 2329.96 |
| `test_retry_edit_delete_and_delayed_retry` | 17 → 17 | 11 → 11 | 486.49 → 538.90 | 527.72 → 634.29 |
| `test_an_injury_reported_after_a_clean_check_in_refreshes_it` | 44 → 44 | 3 → 3 | 553.04 → 623.68 | 581.28 → 738.56 |

The final sequential FakeStore run shows slower p50 values for all four mutation test workflows. Injury Today service and some unchanged plan-detail probes are also slower. These measurements do not establish that completion, exercise editing or the whole app became faster. The fixtures have no database transfer cost, and small dictionary/proxy overhead and runtime variability remain in their timings. No causal attribution is made from one synthetic timing batch; the supported improvements are the removed Data API attempts and reduced transferred projection bytes. Every negative/neutral result is retained above.

## Verification

- Broad relevant backend run: **727 passed, 2 skipped, 5 failed** across History, active plans, projections, Today/readiness/safety, renewable/custom plans, exercise customisation, session details, rehab, XP, timezone and compliance coverage.
- Every failure also reproduces on untouched `efa2dece` in the separate before worktree:
  - `test_today_service.py::TestCommandView::test_malformed_structured_session_degrades_without_crashing` — existing malformed-session crash.
  - `test_exercise_customisation.py::test_library_dose_fields_follow_the_drill[Tempo Hill Runs-intervals]` — existing interval-dose expectation.
  - `test_week_progress_route_resilience.py::test_week_plan_lookup_failure_does_not_break_saved_completion` — existing fixture expects 201 but receives 409.
  - Two `test_xp_active_plan_route.py` cases (`test_xp_rejection_does_not_prevent_adherence_reconciliation`, `test_adherence_reconciliation_failure_does_not_rollback_completion`) — existing fixtures expect 201 but receive 409.
- Final focused new History/projection, effective-fallback and preserved diagnostic tests: **71 passed**. No existing assertions were weakened.
- Additional plan access, generation-response and minor weight-cut safety tests: **86 passed**.
- Repository-wide Ruff, changed-file Python compilation and diff whitespace checks passed. All comparison JSON parses, and all 20 Data API repetitions agree on attempt/projection/byte counts.
- Frontend, dependency, schema, RLS and deployment changes are absent. No frontend verification rerun was required for this backend-only change. Real PostgreSQL tests requiring a disposable database skipped; the full spaCy-dependent suite was not run locally.
- GitHub CI status is reported in the PR. The PR remains draft while its #3044 dependency is unmerged and baseline test failures remain unresolved; this report does not claim a fully green repository.

No frontend files, migrations, RLS/auth policies, prescriptions, clinical decisions or readiness gates changed. No production benchmarking writes occurred. #3044 diagnostics and #3043 request caches are preserved.

## Remaining backend work

1. Establish a versioned deterministic brief-input contract before reducing the remaining large training brief. Include renewable, fallback, coaching, injury and rehab consumers.
2. Profile generation-worker reads and consolidate only where no intervening writes require freshness; do not share stale compliance decisions.
3. Investigate full plan reads in XP/week-progress/streak consumers, proving all safety/fallback branches before substituting a projection. Active-plan resolver callers generally need a training/full row, so it was not globally reduced to metadata.
4. Dense same-day history pagination can widen its source queries for correctness. It was not altered.
5. Capture staging/live per-workflow read deltas and encoded transfer sizes. No real-world latency improvement is claimed from synthetic fixtures. Backend counts/bytes improved in the measured paths; absolute production latency and query execution percentiles remain unmeasured.
6. Resolve the baseline test failures separately without weakening their assertions. Frontend request consolidation remains PR 3 work.
