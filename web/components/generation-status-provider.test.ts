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
