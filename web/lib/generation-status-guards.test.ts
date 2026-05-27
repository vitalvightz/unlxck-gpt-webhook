import test from "node:test";
import assert from "node:assert/strict";

import {
  isExpiredPendingGeneration,
  isStaleVisibleGenerationJob,
  normalizeLegacyGenerationJobStatus,
  resolveMatchingPayloadGenerationAction,
  shouldBlockGenerateAutoStartForMatchingPayload,
} from "@/lib/generation-status-guards";
import type { GenerationJobResponse } from "@/lib/types";

const NOW_MS = Date.parse("2026-05-23T00:00:00.000Z");

function buildJob(partial: Partial<GenerationJobResponse>): GenerationJobResponse {
  return {
    job_id: "job-1",
    athlete_id: "athlete-1",
    client_request_id: "request-1",
    status: "running",
    created_at: "2026-05-22T23:00:00.000Z",
    updated_at: "2026-05-22T23:30:00.000Z",
    started_at: "2026-05-22T23:00:00.000Z",
    heartbeat_at: "2026-05-22T23:30:00.000Z",
    ...partial,
  };
}

test("pending generation created 25 days ago is expired", () => {
  const oldPending = "2026-04-28T00:00:00.000Z";
  assert.equal(isExpiredPendingGeneration(oldPending, NOW_MS), true);
});

test("running job older than stale window is treated as stale and not active", () => {
  const staleJob = buildJob({
    status: "running",
    created_at: "2026-04-28T00:00:00.000Z",
    started_at: "2026-04-28T00:00:00.000Z",
    heartbeat_at: "2026-04-28T00:00:00.000Z",
  });
  assert.equal(isStaleVisibleGenerationJob(staleJob, NOW_MS), true);
});

test("fresh running job remains active", () => {
  const freshJob = buildJob({
    status: "running",
    created_at: "2026-05-22T23:00:00.000Z",
    updated_at: "2026-05-22T23:30:00.000Z",
    started_at: "2026-05-22T23:00:00.000Z",
    heartbeat_at: "2026-05-22T23:30:00.000Z",
  });
  assert.equal(isStaleVisibleGenerationJob(freshJob, NOW_MS), false);
});

test("generate auto-start is blocked only when payload hash matches completed marker", () => {
  assert.equal(shouldBlockGenerateAutoStartForMatchingPayload("hash_a", "hash_a"), true);
  assert.equal(shouldBlockGenerateAutoStartForMatchingPayload("hash_a", "hash_b"), false);
  assert.equal(shouldBlockGenerateAutoStartForMatchingPayload("hash_a", null), false);
});

test("legacy generation statuses normalize to supported generation lifecycle values", () => {
  assert.equal(normalizeLegacyGenerationJobStatus("held_for_review"), "review_required");
  assert.equal(normalizeLegacyGenerationJobStatus("publishable_with_flags"), "completed");
});

test("matching payload with completed local generation redirects to existing plan", () => {
  assert.deepEqual(
    resolveMatchingPayloadGenerationAction("hash_a", { planId: "plan_123", payloadHash: "hash_a" }),
    { type: "redirect", planId: "plan_123" },
  );
});

test("matching payload without an openable plan id shows already-generated state", () => {
  assert.deepEqual(
    resolveMatchingPayloadGenerationAction("hash_a", { planId: null, payloadHash: "hash_a" }),
    { type: "already_generated" },
  );
  assert.deepEqual(
    resolveMatchingPayloadGenerationAction("hash_a", { planId: "   ", payloadHash: "hash_a" }),
    { type: "already_generated" },
  );
});

test("non-matching payload proceeds with a fresh generation", () => {
  assert.deepEqual(
    resolveMatchingPayloadGenerationAction("hash_a", { planId: "plan_123", payloadHash: "hash_b" }),
    { type: "proceed" },
  );
  assert.deepEqual(resolveMatchingPayloadGenerationAction("hash_a", null), { type: "proceed" });
});
