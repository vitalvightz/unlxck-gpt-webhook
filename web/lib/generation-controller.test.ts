import test from "node:test";
import assert from "node:assert/strict";

import {
  canRecoverPendingGenerationWithoutCreate,
  resolveCompletedTerminalJobOutcome,
  resolveFailedJobWithSavedPlan,
  resolveTerminalJobPlanId,
} from "./generation-controller";
import type { GenerationJobResponse } from "@/lib/types";

function buildTerminalJob(partial: Partial<GenerationJobResponse>): GenerationJobResponse {
  return {
    job_id: "job-terminal",
    athlete_id: "athlete-1",
    client_request_id: "request-1",
    status: "completed",
    created_at: "2026-05-22T23:00:00.000Z",
    updated_at: "2026-05-22T23:30:00.000Z",
    ...partial,
  };
}

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

test("completed job with missing plan ids does not recover from milestone meta plan_id", () => {
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
    null,
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

test("completed terminal job with plan_id opens that plan", () => {
  assert.deepEqual(
    resolveCompletedTerminalJobOutcome(buildTerminalJob({ plan_id: "plan_direct" })),
    { type: "open", planId: "plan_direct" },
  );
});

test("completed terminal job with only latest_plan_id opens that plan", () => {
  assert.deepEqual(
    resolveCompletedTerminalJobOutcome(buildTerminalJob({ plan_id: null, latest_plan_id: "plan_latest" })),
    { type: "open", planId: "plan_latest" },
  );
});

test("completed terminal job with no openable plan is already-generated, not a failure", () => {
  assert.deepEqual(
    resolveCompletedTerminalJobOutcome(buildTerminalJob({ plan_id: null, latest_plan_id: null })),
    { type: "already_generated" }
  );
  assert.deepEqual(
    resolveCompletedTerminalJobOutcome(buildTerminalJob({ plan_id: "   ", latest_plan_id: "" })),
    { type: "already_generated" }
  );
});

test("completed terminal job with no plan but requires_admin_resume is review_paused", () => {
  // Triage-blocked outcomes live only on the job. The controller must
  // surface "review_paused" instead of "already_generated" so the UI
  // routes to admin review (and the elapsed timer halts).
  assert.deepEqual(
    resolveCompletedTerminalJobOutcome(
      buildTerminalJob({
        plan_id: null,
        latest_plan_id: null,
        requires_admin_resume: true,
        stage2_status: "triage_blocked",
      }),
    ),
    { type: "review_paused" },
  );
});
