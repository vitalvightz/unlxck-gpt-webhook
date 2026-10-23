# Generation timeout and recovery investigation

Investigated on 2026-10-23 against the selected `Main` checkout. Changes here are local; no production deployment or database writes were performed.

## Confirmed code paths

- `api/generation/timeouts.py` defaults Stage 2 finalization to 1500 seconds. Individual provider timeouts and the overall generation runtime are separate limits.
- `api/store.py` defines a 900-second default job runtime ceiling, with a minimum configurable value of 300 seconds. It measures `started_at`, independently of the 15-second heartbeat.
- The worker recovery classifier previously used heartbeat staleness without that ceiling. Its sweep also skipped its own active tasks, including an active task stuck awaiting the provider.
- Stage 2 handoff milestones were subject to the cumulative milestone recorder's write throttle. A job could remain durably at `stage1_result_persisted` while finalization was already awaiting the provider. The 40-entry milestone limit is a rolling cap: it removes old entries rather than stopping new milestones.
- The pre-release structured-card retry previously received a new full Stage 2 timeout budget.
- Technical Stage 2 failures currently fail the job without publishing the Stage 1 draft. Existing tests enforce this. The README's statement that a technical Stage 2 failure releases Stage 1 does not describe this implementation.

These defects explain how an over-age job could remain running. They do not establish the exact operation blocking a particular production job. No production worker logs or live job records were available in this environment.

## Changes

The worker now checks the absolute runtime even for local active jobs and fresh heartbeats. Expired attempts bypass startup requeue logic. Already persisted output uses the existing completion/review recovery path. Recovery re-reads the job before resolution, and the terminal RPC retains its expected running status and attempt-count checks. Recovery never updates a plan row.

The orchestrator calculates one remaining runtime budget after claim and tracks it with a monotonic clock. Finalization and the card retry share that budget, even if the standalone Stage 2 timeout is disabled. This preserves the configured runtime ceiling rather than increasing it to accommodate a slow request. It bounds waiting; it does not make provider generation faster. The worker recovery sweep is periodic, and storage operations still have their own latency.

The Stage 2 handoff now flushes before awaiting finalization. Its milestone includes the claim attempt and remaining budget. Persistence errors remain logged and fail-soft, so an unavailable database can still prevent the handoff from becoming durable.

## Reading the new logs

Filter worker application logs by the affected `job_id`. New records avoid prompts, generated text, credentials, and athlete health details.

| Last observed record | Meaning |
| --- | --- |
| `stage2_finalize_started` | Finalizer entered; effective timeout and remaining job budget are recorded. |
| `model_request_started` | Provider request about to open; includes model, attempt label, source, and job ID. |
| `model_request_waiting phase=opening_stream` | Still waiting for the stream context to open. |
| `model_stream_opened` | Stream opened; now awaiting the final response. |
| `model_request_waiting phase=awaiting_final_response` | Still draining/waiting for the response. Logged every 30 seconds; this does **not** prove model progress. |
| Existing `received ... response` | Response ID, token usage, cost, and elapsed time are available. |
| `model_request_cancelled` / `model_request_failed` | Request stopped; correlates attempt, model, elapsed time, and exception type without dumping provider errors. |
| `stage2_finalize_stopped` / `stage2_finalize_finished` | Overall finalization outcome and elapsed time. |
| `generation_recovery_candidate` | Recovery classification, claim attempt, local task presence, start/heartbeat times, and last durable milestone. |

For example, on the deployment host, use `docker compose logs --since 30m worker` and filter for the affected job UUID. Compare the effective timeout with the deployed environment settings. A missing event from an older worker image is not evidence that the operation never ran. Local cancellation closes the request stream; it does not establish that a background response has stopped computing at the provider.

## Validation and remaining work

Regression coverage exercises fresh-heartbeat expiry, local hanging tasks, expired startup attempts, persisted output, concurrent completion, shared finalizer/card deadlines, durable handoff, and request-log redaction/cancellation. Existing ownership tests verify that completed jobs and stale attempts reject terminal writes.

Final checks passed: 316 tests across API generation, stale recovery, worker ownership/shutdown, and Stage 2 automation; 154 tests across generation runtime, recovery routing, heartbeat, and provider failure/logging. These suites overlap. The final recovery/ownership check passed 18 tests. Ruff and `git diff --check` also passed.

The selected browser smoke/accessibility/security-header suite passed 11 tests. Baseline frontend unit tests had 2198 passes and three pre-existing exercise-row summary assertion failures. Baseline injury tests had 116 passes and five failures (four stale `training_context` fixtures and one missing swelling label). These unrelated files were not changed.

Live authentication, schema readiness, provider behavior, and a real end-to-end generation remain unverified. The supplied Supabase project's development/production status is unknown, and its keys are not injected. Before production rollout, review this patch and correlate logs from an affected job. Use a confirmed development project for any generation test that writes data. No worker was started against the supplied project.
