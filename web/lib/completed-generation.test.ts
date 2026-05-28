import test from "node:test";
import assert from "node:assert/strict";

import {
  parseCompletedGeneration,
  shouldClearCompletedGenerationForDeletedPlan,
} from "./completed-generation";

test("delete clears completed-generation cache only when it points to the deleted plan", () => {
  const raw = JSON.stringify({ planId: "plan_123", payloadHash: "hash_a" });
  assert.equal(shouldClearCompletedGenerationForDeletedPlan(raw, "plan_123"), true);
});

test("delete keeps completed-generation cache that points to a different plan", () => {
  const raw = JSON.stringify({ planId: "plan_other", payloadHash: "hash_a" });
  assert.equal(shouldClearCompletedGenerationForDeletedPlan(raw, "plan_123"), false);
});

test("delete does not clear when cache is empty or malformed", () => {
  assert.equal(shouldClearCompletedGenerationForDeletedPlan(null, "plan_123"), false);
  assert.equal(shouldClearCompletedGenerationForDeletedPlan("not-json", "plan_123"), false);
  assert.equal(shouldClearCompletedGenerationForDeletedPlan(JSON.stringify({ payloadHash: "hash_a" }), "plan_123"), false);
});

test("completed-generation cache parses a valid planId and payload hash", () => {
  assert.deepEqual(
    parseCompletedGeneration(JSON.stringify({ planId: "plan_123", payloadHash: "hash_a" })),
    { planId: "plan_123", payloadHash: "hash_a" },
  );
});

test("completed-generation cache reports a null planId when it is missing", () => {
  assert.deepEqual(
    parseCompletedGeneration(JSON.stringify({ payloadHash: "hash_a" })),
    { planId: null, payloadHash: "hash_a" },
  );
  assert.equal(parseCompletedGeneration(null), null);
});
