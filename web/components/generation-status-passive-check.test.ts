import test from "node:test";
import assert from "node:assert/strict";

import {
  PASSIVE_STATUS_RECHECK_MIN_INTERVAL_MS,
  shouldRunPassiveStatusCheck,
} from "./generation-status-provider";

const NOW = 1_000_000_000;

test("idle tab returns skip the generation re-check when the last one was recent", () => {
  assert.equal(
    shouldRunPassiveStatusCheck({
      trackedJobId: null,
      hasPendingRecord: false,
      adminHold: false,
      lastCheckedAtMs: NOW - 5_000,
      nowMs: NOW,
    }),
    false,
  );
  assert.equal(
    shouldRunPassiveStatusCheck({
      trackedJobId: null,
      hasPendingRecord: false,
      adminHold: false,
      lastCheckedAtMs: NOW - PASSIVE_STATUS_RECHECK_MIN_INTERVAL_MS,
      nowMs: NOW,
    }),
    true,
  );
});

test("a build in flight or held for review always re-checks on return", () => {
  const recent = { lastCheckedAtMs: NOW - 1_000, nowMs: NOW };
  assert.equal(
    shouldRunPassiveStatusCheck({ ...recent, trackedJobId: "job-1", hasPendingRecord: false, adminHold: false }),
    true,
  );
  assert.equal(
    shouldRunPassiveStatusCheck({ ...recent, trackedJobId: null, hasPendingRecord: true, adminHold: false }),
    true,
  );
  assert.equal(
    shouldRunPassiveStatusCheck({ ...recent, trackedJobId: null, hasPendingRecord: false, adminHold: true }),
    true,
  );
});
