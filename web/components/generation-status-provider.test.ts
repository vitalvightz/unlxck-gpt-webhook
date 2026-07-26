import test from "node:test";
import assert from "node:assert/strict";

import { shouldRetainLatestJob, shouldUseLocalPendingForRecovery } from "./generation-status-provider";

const baseJob = {
  job_id: "job-1",
  athlete_id: "athlete-1",
  client_request_id: "req-1",
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
} as const;

test("local pending without jobId is not used for recovery", () => {
  assert.equal(
    shouldUseLocalPendingForRecovery({
      clientRequestId: "req-1",
      createdAt: "2026-01-01T00:00:00Z",
    }),
    false,
  );
});

test("local pending with jobId can be used for exact-job recovery", () => {
  assert.equal(
    shouldUseLocalPendingForRecovery({
      clientRequestId: "req-2",
      jobId: "job-2",
      createdAt: "2026-01-01T00:00:00Z",
    }),
    true,
  );
});

test("null latest job is not retained", () => {
  assert.equal(shouldRetainLatestJob(null), false);
});

test("terminal latest job with neither plan id is not retained", () => {
  assert.equal(
    shouldRetainLatestJob({ ...baseJob, status: "completed", plan_id: null, latest_plan_id: null }),
    false,
  );
  assert.equal(
    shouldRetainLatestJob({ ...baseJob, status: "failed", plan_id: null, latest_plan_id: null }),
    false,
  );
});

test("recent retryable failure without a plan is retained so the failure stays visible", () => {
  // Without this the ribbon dropped the job and a failed build vanished the
  // moment the user left /generate — no notice, no retry.
  const nowMs = Date.parse("2026-01-01T01:00:00Z");
  assert.equal(
    shouldRetainLatestJob(
      {
        ...baseJob,
        status: "failed",
        plan_id: null,
        latest_plan_id: null,
        can_retry: true,
        completed_at: "2026-01-01T00:30:00Z",
      },
      nowMs,
    ),
    true,
  );
});

test("stale retryable failure is not resurfaced", () => {
  const nowMs = Date.parse("2026-01-05T00:00:00Z");
  assert.equal(
    shouldRetainLatestJob(
      {
        ...baseJob,
        status: "failed",
        plan_id: null,
        latest_plan_id: null,
        can_retry: true,
        completed_at: "2026-01-01T00:30:00Z",
      },
      nowMs,
    ),
    false,
  );
});

test("failure the backend cannot retry is still dropped", () => {
  const nowMs = Date.parse("2026-01-01T01:00:00Z");
  assert.equal(
    shouldRetainLatestJob(
      {
        ...baseJob,
        status: "failed",
        plan_id: null,
        latest_plan_id: null,
        can_retry: false,
        completed_at: "2026-01-01T00:30:00Z",
      },
      nowMs,
    ),
    false,
  );
});

test("completed latest job with only latest_plan_id is retained as openable", () => {
  assert.equal(
    shouldRetainLatestJob({ ...baseJob, status: "completed", plan_id: null, latest_plan_id: "plan_latest" }),
    true,
  );
});

test("terminal latest job with a plan id is retained", () => {
  assert.equal(
    shouldRetainLatestJob({ ...baseJob, status: "completed", plan_id: "plan_1" }),
    true,
  );
  assert.equal(
    shouldRetainLatestJob({ ...baseJob, status: "failed", plan_id: "plan_1" }),
    true,
  );
});

test("non-terminal latest job is retained", () => {
  assert.equal(shouldRetainLatestJob({ ...baseJob, status: "queued" }), true);
  assert.equal(shouldRetainLatestJob({ ...baseJob, status: "running" }), true);
});

test("triage-blocked terminal job without plan id is retained for admin-review ribbon", () => {
  // Protected triage outcomes live only on the job (no plan row). The
  // ribbon must keep showing "admin review required" so the user can
  // see it and an admin can act on it.
  assert.equal(
    shouldRetainLatestJob({
      ...baseJob,
      status: "review_required",
      plan_id: null,
      latest_plan_id: null,
      requires_admin_resume: true,
      stage2_status: "triage_blocked",
    }),
    true,
  );
});
