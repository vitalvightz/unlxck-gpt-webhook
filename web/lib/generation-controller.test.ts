import test from "node:test";
import assert from "node:assert/strict";

import { canRecoverPendingGenerationWithoutCreate } from "./generation-controller";

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
