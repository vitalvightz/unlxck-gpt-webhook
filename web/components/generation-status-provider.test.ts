import test from "node:test";
import assert from "node:assert/strict";

import { shouldUseLocalPendingForRecovery } from "./generation-status-provider";

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
