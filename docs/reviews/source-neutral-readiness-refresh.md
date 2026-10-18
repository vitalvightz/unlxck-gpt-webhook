# Source-neutral readiness refresh

Base audited: Main `005d069ad81772be4b8c8a3da327b7df252562a8` (merged #2921).

## Defect and refresh contract

Before: `GET /api/today` built a fresh command view, but generally copied the recommendation persisted at check-in. A source-specific probe reran readiness when recent manual rows (including deletion tombstones) existed. Prescribed completion did not satisfy that probe. Clearing the command cache or refreshing React could therefore return the same obsolete check-in-time recommendation.

After: whenever today's check-in exists, the live command view evaluates its original answers against current authoritative history through `_readiness_decision_with_failsafe`. The existing medical-hold path still works without a check-in. Both sources are read through `training_history`; empty history after deletion is also evaluated. No readiness or workload write is added to mutation endpoints.

The guarantee is a Today evaluation initiated after a successful mutation sees the committed history, on any device or backend worker. A read already in flight may have observed pre-commit history; the saving client starts a new refresh after acknowledgement and rejects older responses. This does not add live push updates to other devices or promise transactional isolation across different history tables.

Readiness is evaluated on demand. The persisted check-in recommendation remains the historical check-in-time snapshot; `/api/today/checkins` is historical data. It no longer supplies the live recommendation without reevaluation. Refresh never rewrites check-in inputs, completion provenance, execution snapshots, or plan content. No schema migration, revision table, queue, worker, formula, threshold, or policy change is required.

## Mutation and refresh paths

| Workload mutation | Persistence and identity | Existing refresh/invalidation | Authoritative read after this change |
| --- | --- | --- | --- |
| Prescribed completion / supported actuals correction | `POST /api/today/session-completion` → readiness boundary → `today_service.upsert_session_completion` → `AppStore.upsert_session_completion`; athlete/session/local-day identity | HTTP middleware drops athlete's command cache; completion UI awaits `refresh()` | Boundary → Today service → current check-in + `training_history` → existing readiness engine and context floor |
| Manual create / repeat | `POST /api/training/sessions` → `create_external_training` → store; athlete/client-request UUID identity | Same middleware; Log Training `onSaved` refreshes Today; repeat uses a new UUID | Same source-neutral read path |
| Manual edit | `PATCH /api/training/sessions/{id}` → `update_external_training` → owner-scoped update of the same row | Same middleware and save callback | Current row replaces old effort/duration; no appended workload |
| Manual delete | `DELETE /api/training/sessions/{id}` → `delete_external_training` → owner-scoped tombstone | Same middleware; existing history/UI reload patterns | Active history excludes tombstone; even completely empty history is evaluated |
| Duplicate manual create retry | Atomic `ON CONFLICT DO NOTHING`, then read original; fingerprint rejects changed request content | Same middleware; existing client UUID survives retry | Original occurrence only; a retry cannot undo an edit or resurrect a deletion |
| Duplicate prescribed completion retry | Existing unique occurrence upsert, stable completed timestamp and entered-completed-status handling | Same middleware; existing XP idempotency | One reported occurrence, with latest supported actuals |

History edits/deletes on the History screen do not stream changes into a mounted Today tab. Opening or explicitly refreshing Today performs a fresh authoritative read. Frontend `getToday` uses `cache: "no-store"`; the route now also returns `Cache-Control: private, no-store`.

`training_history` combines prescribed done/modified reports and active manual records, scopes them to the athlete, excludes `day_credit`, retains legacy unknown provenance for conservative availability handling, sorts by day/time, and deduplicates by source/occurrence/plan/day. `completed_workload` remains unchanged: five-day window, most recent three qualifying sessions, no invented RPE or contact exposure.

## Cache, snapshot, and failure audit

| Layer / failure | Behavior |
| --- | --- |
| Backend command cache | Only XP's derived read model reuses the short-lived command cache. Authoritative Today never reads it. Existing targeted athlete invalidation remains. If invalidation raises after persistence, middleware logs the failure and preserves the successful write response; the next Today read still rebuilds. The XP-only cache remains best-effort and process-local until invalidation, a newer Today publication, or its TTL. It is not used as readiness authority. |
| Stored readiness | Historical check-in-time recommendation is retained. Every checked-in live Today response reevaluates current history. There is no refresh write that can complete late and overwrite a newer snapshot. |
| In-process memoization | `_BuildReadCache` shares successful identical reads only within one command build, returns copies, and never caches failed reads. Structured-plan projection memoization remains per build. `reuse_today_command_views` is used only for the read-only morning-push sweep at an explicit instant, not the HTTP Today path or mutation handlers. |
| Unchanged workload | There is one inexpensive deterministic readiness evaluation per checked-in authoritative read. No program generation or readiness persistence is introduced. Identical successful history reads within that build are deduplicated; the separate manual/tombstone refresh probe is removed. No cross-request history cache is added. Regression tests verify identical repeated results and unique backing history reads per build. |
| Local-day rollover | Every build resolves the athlete-local training day through the existing 04:00 cutoff. Yesterday's check-in is not reused after rollover; workload retains the existing history window. Frontend presentation cache is keyed by day and does not cache readiness. |
| Multiple devices / workers | They all read the same persisted history through fresh Today builds; correctness does not rely on sharing cache invalidation, React state, or worker memory. A separate-worker regression retains an old command-cache entry while another worker writes, then verifies fresh returned workload and guidance. |
| Training write succeeds, immediate evaluation fails | Mutation does not include a post-write readiness evaluation. Its successful persistence remains acknowledged; a subsequent failed Today read uses the existing error/retry flow. An unexpected engine exception is an error, not green guidance. |
| One history source fails | The canonical tracking boundary records incomplete history and applies its existing conservative floor, confidence, and execution hold. Missing history cannot mean recovery. Failed reads are retried on the next build. |
| Today opened during pending mutation | It can legitimately see pre-commit data. After commit/acknowledgement, the next refresh sees the new record. Regression uses barriers rather than timing sleeps. |
| Close mutations / out-of-order evaluation | There are no asynchronously persisted refreshed recommendations to race. Each read uses its current inputs. Barrier regression lets the older evaluation finish last, then verifies the next read still uses both sessions and no check-in was overwritten. |
| Old frontend response | Existing sequence counter rejects it, including its error/finally updates. The pending state follows only the newest refresh. |
| Refresh pending / failed | Today shows “Updating Today…” instead of the recommendation while refreshing. On failure, its existing retry notice appears and the unsupported old decision/next-step recommendation is hidden. Forms and save acknowledgements stay mounted. |

## Provenance, safety, and evidence

#2921's implementation is unchanged. `reported` is eligible actual workload; `day_credit` is progress-only; unknown origin remains unverified and conservative. Fan-out credit cannot overwrite independent reports, and two independently reported workouts retain separate identities. Manual Boxing remains workload only: it does not create a sparring log, contact exposure, clinical clearance, or rehab exposure.

The existing engine, context fail-safe, medical holds, injury ceilings, neurological STOP rules, rehab progression and frozen-prescription reconciliation are unchanged. Live evaluation uses all stored check-in safety/pain answers. Regression tests remove workload under neurological symptoms, sharp pain, and severe injury and verify the hold remains. Existing XP/streak/week-progress and rehab completion regressions exercise their original persistence paths.

The exact same-day scenario is tested through real mutation services and the canonical Today boundary: Strength/RPE 8 produces one workload event; Boxing/90 minutes/Hard produces the second; Moderate replaces Hard; deletion leaves Strength. Tests capture the actual context delivered to the real engine and assert returned state/reason and workload counts, without forcing a downgrade beyond existing rules.

Validation commands and results are recorded below. Python uses the repository's fast-lane requirements (without spaCy), in an external virtual environment; no dependencies changed in the repository.

| Validation | Result |
| --- | --- |
| Main focused baseline: provenance, external training, Today service, safety matrix, readiness boundary/fail-safe | 289 passed; one pre-existing malformed-plan failure |
| Same focused branch suite plus first 15 new refresh cases | 304 passed; the identical pre-existing failure |
| New refresh suite (17 cases) + XP progress + rehab completion capture/API flow | 150 passed |
| API Today, readiness engine/fail-safe, clinician clearance, medical holds, multi-injury, rehab safety invariants, surface-injury readiness/safety | 859 passed |
| Changed Python lint/import compilation | Passed |
| Frontend hook + Today screen unit tests | 6 passed |
| Frontend production build / TypeScript and changed-file ESLint | Passed |
| Chromium save → pending Today → refreshed Today → second independent save → History | 2 passed (390px and 1280px; no app console errors or horizontal overflow) |

Four older readiness-boundary tests deliberately seeded recommendation labels inconsistent with the stored answers/current plan. Their assertions now verify live evaluation and current failure attribution instead of preserving obsolete labels. No safety floor was relaxed.

## Existing Main failures and limits

Main at the audited commit already has failed published workflows:

- [Python Quality](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39143471170): multiple existing full-suite failures, including the same `TestCommandView::test_malformed_structured_session_degrades_without_crashing` (`AttributeError` on malformed session text in exercise-instruction recovery).
- [Backend Checks](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39143471229): `test_saved_custom_plan_publish_view_activate_today_and_retries` expects `Strength / Rounds` but receives `Strength` (1 failed, 65 passed in that job).
- [Web Build](https://github.com/vitalvightz/unlxck-gpt-webhook/actions/runs/39143471223): exercise-coaching release gate (47 failed, 73 passed), predating this branch. This branch's local frontend production compilation succeeds.

The malformed-plan failure was reproduced on an isolated unchanged Main checkout and in the matching branch test command. It is outside the workload refresh path and is not changed here. The partial full-suite attempts also found the same existing ankle-sprain recovery failure; they were interrupted to run the relevant matched baseline and safety suites. An initial unmodified-Main `pytest -n 4` attempt could not collect because clinical-review/community tests generate random UUID parameter IDs across workers. The full 15,000+ non-spaCy suite was not completed locally, and no claim of a green full Main or full branch suite is made. Live Supabase/Postgres integration and real two-device browser sessions were not exercised locally; the cross-worker test uses two store facades over shared deterministic persistence.

Browser plugin was not available; rendered validation uses the repository's Playwright/Chromium workflow, with mocked API/auth traffic. It covers the loading state, save acknowledgement, retry-related hook behavior, independent repeat identities, console errors and mobile overflow. Screenshots are saved outside the repository. No redesign or extra logging input was added.
