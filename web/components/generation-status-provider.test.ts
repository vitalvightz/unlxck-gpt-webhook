import test from "node:test";
import assert from "node:assert/strict";

import { shouldShowLatestGenerationJob, shouldUseLocalPendingForRecovery } from "./generation-status-provider";

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

test("hides terminal latest job when it has no plan ids", () => {
  assert.equal(
    shouldShowLatestGenerationJob({
      job_id: "job-1",
      athlete_id: "athlete-1",
      status: "completed",
      source: "dashboard",
      client_request_id: "req-1",
      created_at: "2026-01-01T00:00:00Z",
      started_at: null,
      completed_at: "2026-01-01T00:01:00Z",
      plan_id: null,
      latest_plan_id: null,
      error: null,
      updated_at: "2026-01-01T00:01:00Z",
    }),
    false,
  );
});

test("keeps completed latest job when latest_plan_id exists", () => {
  assert.equal(
    shouldShowLatestGenerationJob({
      job_id: "job-2",
      athlete_id: "athlete-1",
      status: "completed",
      source: "dashboard",
      client_request_id: "req-2",
      created_at: "2026-01-01T00:00:00Z",
      started_at: null,
      completed_at: "2026-01-01T00:01:00Z",
      plan_id: null,
      latest_plan_id: "plan-2",
      error: null,
      updated_at: "2026-01-01T00:01:00Z",
    }),
    true,
  );
});
