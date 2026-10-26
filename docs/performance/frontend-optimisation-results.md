# Frontend request reduction — PR 3

Base: `9da897b60a1dc5852e32df0a76267639fa0ca845`, Main containing #3044 (instrumentation) and #3045 (backend read reduction). No stacking was needed. Frontend only: no migration, RLS, backend projection, prescription, clinical/injury or XP-rule change.

## What changed

### 1. Shared reads in the API client (`web/lib/shared-reads.ts`)

Six read helpers now go through one small module instead of each screen issuing its own request:

| Helper | Concurrent identical calls share one request | A resolved result may be reused | Who may reuse it |
| --- | --- | --- | --- |
| `getToday` | yes | yes, ≤30 s, opt-in | Plans (phase label), Plan Viewer ("Open Today" link, active badge). **Home and Today always read fresh.** |
| `getPlan` | yes | yes, ≤30 s, opt-in | Home countdown calendar, Today block presentation (first load only), Plan Detail initial load. Background upgrade polls, triage-resume polls and post-change refreshes read fresh. |
| `getActivePlan` | yes | yes, ≤30 s, opt-in | Plan Viewer. Plans (where activation happens) reads fresh. |
| `listPlans` | yes | no | — |
| `getPlanCompletions` | yes | no | Completion rows and exercise-change locks are read on every Viewer visit. |
| `getTrainingHistory` | yes | no | History edits must show on the next read. |

Rules, all enforced in one place:

- **Identity.** The key is the bearer token plus the full path and query string (plan ID, `include_skipped`, `limit`, `before_day`). Two accounts, an admin and an athlete, or a refreshed token never share a request or a result. Results are dropped at sign-out and whenever the auth token changes.
- **Writes end sharing.** Every non-GET request through `api.ts` (analytics events excepted) starts a new write epoch: held results are discarded, later callers cannot join reads that began earlier, and nothing is shared while the write is in flight. A read that started before a write and finished after it is never held. This covers plan creation, activation/replacement, rename, archive/delete, custom-plan save/publish, exercise changes, session completion/edit/deletion, exercise logging, check-ins, injury updates, delayed rehab answers, profile/timezone changes and consent withdrawal, because they all go through `api.ts`. A missing classification can only cost a read, never serve a stale one.
- **Freshness.** Reuse is opt-in per call and capped at 30 s on a monotonic clock. Held results are memory-only (never browser storage), at most 12, and pruned on access.
- **Failures.** Failed, timed-out and cancelled reads are never held; the next caller starts a new request. Callers that join a read already retrying a gateway error share that retry instead of adding a parallel request.
- **Cancellation.** Each caller's `AbortSignal` cancels only its own wait. The network request is aborted only when every caller has left, and is then forgotten so the next caller starts again.
- **Response protections unchanged.** Every request still uses `cache: "no-store"`; the server's `private, no-store` headers are untouched. The client never caches across page loads.

Safety boundary: a reused Today view only labels the active plan and links to `/today`. Readiness, training permission, injury holds, rehab gating and save confirmation always come from the Today screen's own fresh read, and the server stays authoritative for every action.

### 2. Today no longer triggers an XP read on open

`useTodayCommand` dispatched `requestXpRefresh()` after every successful Today load, including the first load when the screen opens. `XpProvider` treats that event as an explicit refresh and bypasses its 30 s passive guard, so every visit to Today cost a `GET /api/xp/progress`. `GET /api/today` awards nothing (`api/routes/today.py:get_today_state` only builds and caches the view). The first load now skips the event. Every refresh the screen requests (after check-in, completion, injury update, exercise change, retry or reconnect) still dispatches it, and each write that already dispatched its own XP refresh is unchanged.

### 3. Screen changes

- **Home → Today / Plan Detail.** The plan detail Home reads for its countdown is reused by Today's block presentation and by Plan Detail.
- **Today.** Once the screen has shown blocks, a change of plan, training day or injuries, an expired presentation, or an exercise change reads the plan fresh, as before. An exercise change also marks the next read as fresh explicitly.
- **Plans.** The phase label reuses a Today view from the last 30 s instead of rebuilding it.
- **Plan Viewer.** Active-plan state and the next-session link reuse recent reads. Completion rows are always read fresh.

### Considered and left unchanged

- **Home's 200-row History read (tracking-first athletes).** Home feeds every loaded row to habit inference over the last 42 days (`learnTrainingHabits`) and to the 7-day summary with its existing "load more" cursor. Home does not mark a page as truncated, so a smaller row limit would silently change habit suggestions for athletes who log a lot. Bounding by days needs a backend contract, which is out of scope here. The cursor pagination is unchanged.
- **History list reuse across screens.** Home and History request the same page, but History is where athletes check what they logged, possibly from another device. Only in-flight sharing applies.
- **Startup reads** (`/api/me`, XP activity/progress, analytics preference, generation-job checks). These are already coalesced or deliberately deferred, and each serves a different purpose.
- **Combining endpoints.** Not done: Today, plan detail, active plan and completions return genuinely different data.

## Measurement

### Method and evidence boundaries

All numbers below come from **mocked browser runs**. They are not from controlled staging or production, and I am not claiming any production speed change from them.

- **Harness:** `web/e2e/frontend-requests.spec.ts` with `web/e2e/request-journeys.ts`, running production `next build` / `next start` builds in Chromium (Playwright 1.60).
- **Data:** every `/api/*` response comes from synthetic fixtures (the existing `rehab-today.json` athlete) after a fixed delay. Request counts are **actual browser network calls** seen at the route handler, not API-helper invocations. API-helper sharing is covered separately by unit tests (`web/lib/shared-reads.test.ts`).
- **Not covered:** Supabase auth and other cross-origin traffic is blocked and not counted. The XP calls in `lib/xp-api.ts` bypass `api.ts` but are counted, because they hit `/api/*`.
- **Builds:** *Before* is an untouched worktree at `9da897b`. *After* is this branch. Both use the same host, Node 22, fixtures and harness, and run sequentially with one worker and reduced motion. The *after* benchmark build predates two later commits: the cancelled-caller guard in `shared-reads.ts` (no journey passes a pre-cancelled signal) and the measurement-only harness changes.
- **Runs:** 15 runs per configuration, each in a fresh browser context, so every run starts with a cold browser cache and a cold module state.
- **Journey:** one continuous client-side journey per run through the real app navigation, in the order of the table. Each step ends once its destination URL has loaded and no API request has been in flight for 400 ms (1.5 s for startup, so its deliberately deferred generation-job checks stay attributed to startup).
- **Cold and warm:** "Login → Home" is a cold authenticated start (session restored from storage; an interactive Supabase sign-in cannot run offline). All other steps are warm client-side navigations a few seconds apart, inside the 30 s reuse window. After 30 s on a screen, reuse no longer applies and the next screen issues the same reads as before, apart from the XP read.
- **Timing:** measured from the click or `goto` until the step's *useful* element is visible (Home hero, Today's session block, the plan title, the Plans camp link, a History row, the details dialog). *Ready* means its primary action is visible: Home's hero action, the Viewer's "Open Today" link (which needs the active-plan state). p50 is the median; p95 is nearest-rank, which over 15 runs is the second-highest value.
- **Bytes:** JSON bytes served by the mock. Fixture plans are small (about 3.5 KB), so production plan reads are likely to save more, but this run did not measure that.

Reproduce (from `web/`, with both builds running):

```sh
# Before: git worktree add --detach <dir> 9da897b; build and `next start --port 3101` there.
# After: this branch, `next start --port 3100`. Build env as in .github/workflows/web-build.yml.
for latency in 150 600; do
  E2E_PORT=3101 FRONTEND_BENCH_OUT=before-$latency.json FRONTEND_BENCH_RUNS=15 FRONTEND_BENCH_LATENCY_MS=$latency \
    npx playwright test e2e/frontend-requests.spec.ts -g "record repeated" --workers=1
  E2E_PORT=3100 FRONTEND_BENCH_OUT=after-$latency.json FRONTEND_BENCH_RUNS=15 FRONTEND_BENCH_LATENCY_MS=$latency \
    npx playwright test e2e/frontend-requests.spec.ts -g "record repeated" --workers=1
done
node scripts/summarise-request-benchmark.mjs --pair "150 ms" before-150.json after-150.json \
  --pair "600 ms" before-600.json after-600.json --output ../docs/performance/frontend-comparison.json
```

Raw per-run files stay local. [frontend-comparison.json](frontend-comparison.json) keeps every journey's counts, bytes, p50/p95 and mean per-endpoint calls. Counts were identical in all 15 runs of every configuration.

### Requests per journey

The counts are the same at both latencies.

| Journey | Before requests | After requests | Backend requests avoided per run | Response bytes before → after |
| --- | ---: | ---: | --- | ---: |
| Login → Home (cold) | 8 | 8 | — | 19,656 → 19,656 |
| Home → Today | 6 | 4 | plan detail, XP progress | 21,708 → 18,126 |
| Today → Viewer | 5 | 3 | plan detail, Today | 18,096 → 424 |
| Viewer → Today | 6 | 4 | plan detail, XP progress | 21,708 → 18,126 |
| Today → Home | 2 | 1 | plan detail | 17,672 → 14,147 |
| Home → Plans | 5 | 4 | Today | 14,786 → 639 |
| Plans → Viewer | 5 | 2 | plan detail, active plan, Today | 18,096 → 125 |
| Viewer → History | 1 | 1 | — | 1,971 → 1,971 |
| History → Details | 1 | 1 | — | 230 → 230 |
| History → Home (return) | 2 | 1 | plan detail | 17,672 → 14,147 |
| **Whole journey** | **41** | **29** | **12 (−29%)**: 6 plan detail, 3 Today, 2 XP, 1 active plan | **151,595 → 87,591** |

Authenticated application GETs dropped from 40 to 28. Neither build repeated an identical GET within a single step. The waste was entirely *across* screens: the same plan detail, Today view and active plan fetched again by the next screen. Every remaining Today read in Home → Today, Viewer → Today, Today → Home and the return to Home is the authoritative fresh read, which is kept on purpose. Completion rows are still read on every Viewer visit.

### Timing (mocked latency per API response)

| Journey | 150 ms before useful p50/p95 | 150 ms after | 150 ms before ready p50/p95 | 150 ms after | 600 ms before useful p50/p95 | 600 ms after | 600 ms before ready p50/p95 | 600 ms after |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| Login → Home | 367 / 470 | 349 / 394 | 537 / 644 | 544 / 690 | 345 / 456 | 360 / 392 | 1172 / 1326 | 1232 / 1269 |
| Home → Today | 350 / 384 | 366 / 386 | 361 / 390 | 378 / 392 | 950 / 980 | 961 / 1050 | 956 / 985 | 965 / 1055 |
| Today → Viewer | 304 / 324 | **170 / 207** | 498 / 622 | **386 / 519** | 914 / 937 | **175 / 225** | 1705 / 1731 | **972 / 1018** |
| Viewer → Today | 253 / 287 | 257 / 292 | 262 / 299 | 264 / 296 | 856 / 871 | 855 / 890 | 860 / 877 | 861 / 895 |
| Today → Home | 74 / 100 | 78 / 111 | 272 / 298 | 269 / 301 | 84 / 113 | 82 / 106 | 880 / 904 | 884 / 894 |
| Home → Plans | 290 / 320 | 301 / 348 | 293 / 324 | 305 / 351 | 915 / 929 | 909 / 922 | 919 / 933 | 914 / 927 |
| Plans → Viewer | 232 / 278 | **67 / 106** | 433 / 571 | **264 / 379** | 841 / 856 | **65 / 84** | 1634 / 1649 | **860 / 889** |
| Viewer → History | 518 / 557 | 529 / 576 | 522 / 564 | 537 / 582 | 889 / 944 | 888 / 947 | 898 / 958 | 896 / 957 |
| History → Details | 43 / 55 | 47 / 56 | 47 / 64 | 52 / 61 | 47 / 68 | 42 / 65 | 52 / 72 | 47 / 70 |
| History → Home (return) | 314 / 343 | 313 / 356 | 505 / 538 | 500 / 543 | 305 / 354 | 315 / 377 | 1095 / 1143 | 1107 / 1172 |

All times are in ms.

What these show, within this mocked setup:

- **Plan Viewer is the only measurable speed change.** Arriving from Today or Plans, the plan shows without waiting on its own detail read. It is ready about one round trip sooner, because the Viewer previously waited for the plan, *then* for active plan + Today + completions (two serial round trips) and now waits only for completions. At 600 ms, Plans → Viewer ready went from 1634 to 860 ms p50.
- **Every other journey is unchanged within run-to-run noise.** Those screens were already bound by a request that is still made (the authoritative Today read, plans list, History). Removing a parallel duplicate does not shorten them. Home → Plans and Home → Today send fewer requests but show content no sooner.
- **Slow network:** at 600 ms the Viewer saving scales with latency (about 750–770 ms at p50); the other journeys scale identically before and after.

**Not established:** production or staging latency, effects on real plan payload sizes, CPU/render time, or overall app speed. No overall speed improvement is claimed.

## Verification

- **Shared-read unit tests** (`web/lib/shared-reads.test.ts`, 22 tests):
  - same-user concurrent deduplication;
  - different plan IDs, cursors and query parameters;
  - different athletes, admins and refreshed tokens;
  - opt-in and expiring reuse;
  - writes for: plan rename, activation, archive, session completion, check-in, injury update, delayed rehab answer, profile/timezone change, consent;
  - analytics events as neutral writes;
  - reads straddling a write;
  - failures and timeouts not held;
  - one-of-two and last-consumer cancellation;
  - an already-cancelled caller never starting a cold read;
  - sign-out clearing;
  - the bound on held results.
- **Today hook** (`use-today-command.test.tsx`): the existing out-of-order and presentation-cache tests pass. The first test now makes its injury update through the API, as production does. A new test covers plan reuse on open, no XP refresh on open, XP refresh on explicit refresh, and a fresh plan read after an exercise change.
- **Browser request budget** (`frontend-requests.spec.ts`, runs in CI's existing `test:e2e`):
  - central-journey budgets: no duplicate GET per step; fresh Today on Home/Today; no repeated plan read; no XP read on opening Today; fresh completions in the Viewer;
  - a rename followed by Viewer navigation must re-read plan, Today and active plan and show the new name;
  - a failed plan read must be retried, not reused.
  
  The budget test fails on the *before* build. Under stress (10 repeats, 4 workers) it exposed an existing double `/api/me` at startup: the auth-change and `getSession` paths both load the profile, and the later one could miss the first result before React committed it. `auth-provider.tsx` now records the loaded profile with the state.

Areas still covered only by the existing suites (not re-measured here): exercise logging and editing UI flows, date rollover across midnight, and dense History pagination.
