import test from "node:test";
import assert from "node:assert/strict";

import {
  canRecoverPendingGenerationWithoutCreate,
  resolveFailedJobWithSavedPlan,
  resolveTerminalJobPlanId,
} from "./generation-controller";

test("controller recovery does not create from localStorage-only pending state", () => {
  assert.equal(
    canRecoverPendingGenerationWithoutCreate({
      clientRequestId: "req-1",
      createdAt: "2026-01-01T00:00:00Z",
    }),
    false,
  );
});

test("controller recovery requires an exact pending job id", () => {
  assert.equal(
    canRecoverPendingGenerationWithoutCreate({
      clientRequestId: "req-2",
      jobId: "job-2",
      createdAt: "2026-01-01T00:00:00Z",
    }),
    true,
  );
});

test("failed job with plan id is recovered to open saved plan", () => {
  assert.equal(
    resolveFailedJobWithSavedPlan({
      job_id: "job-1",
      athlete_id: "athlete-1",
      client_request_id: "request-1",
      status: "failed",
      created_at: "2026-05-22T23:00:00.000Z",
      updated_at: "2026-05-22T23:30:00.000Z",
      plan_id: "plan_123",
    }),
    "plan_123",
  );
});

test("completed job with plan id resolves directly", () => {
  assert.equal(
    resolveTerminalJobPlanId({
      job_id: "job-2",
      athlete_id: "athlete-1",
      client_request_id: "request-1",
      status: "completed",
      created_at: "2026-05-22T23:00:00.000Z",
      updated_at: "2026-05-22T23:30:00.000Z",
      plan_id: "plan_direct",
    }),
    "plan_direct",
  );
});

test("completed job with missing plan id recovers from milestone meta plan_id", () => {
  assert.equal(
    resolveTerminalJobPlanId({
      job_id: "job-3",
      athlete_id: "athlete-1",
      client_request_id: "request-1",
      status: "completed",
      created_at: "2026-05-22T23:00:00.000Z",
      updated_at: "2026-05-22T23:30:00.000Z",
      plan_id: null,
      latest_plan_id: null,
      progress_milestones: [
        { code: "plan_persisted", label: "Plan row persisted", detail: "", at: "", meta: { plan_id: "plan_from_meta" } },
      ],
    }),
    "plan_from_meta",
  );
});

test("terminal plan resolution prefers saved plan_id over stale milestone plan_id", () => {
  assert.equal(
    resolveTerminalJobPlanId({
      job_id: "job-4",
      athlete_id: "athlete-1",
      client_request_id: "request-1",
      status: "completed",
      created_at: "2026-05-22T23:00:00.000Z",
      updated_at: "2026-05-22T23:30:00.000Z",
      plan_id: "real_saved_plan_id",
      latest_plan_id: "latest_saved_plan_id",
      progress_milestones: [
        { code: "plan_saved", label: "Plan saved", detail: "", at: "", meta: { plan_id: "stale_fake_plan_id" } },
      ],
    }),
    "real_saved_plan_id",
  );
});
