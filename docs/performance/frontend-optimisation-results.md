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

<!-- RESULTS -->
