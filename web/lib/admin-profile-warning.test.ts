import test from "node:test";
import assert from "node:assert/strict";

import {
  extractRequestId,
  isProfileServiceUnavailableMessage,
  nonProfileSectionError,
  summarizeProfileWarning,
} from "./admin-profile-warning";

test("detects profile-service unavailable messages", () => {
  assert.equal(
    isProfileServiceUnavailableMessage("profile service temporarily unavailable (request id: abc)"),
    true,
  );
  assert.equal(isProfileServiceUnavailableMessage("Store service temporarily unavailable"), true);
  assert.equal(isProfileServiceUnavailableMessage("Unable to load active generation jobs."), false);
  assert.equal(isProfileServiceUnavailableMessage(null), false);
});

test("extracts the latest request id from a message", () => {
  assert.equal(
    extractRequestId("profile service temporarily unavailable (request id: req-123)"),
    "req-123",
  );
  assert.equal(
    extractRequestId("first (request id: old) then (request id: new)"),
    "new",
  );
  assert.equal(extractRequestId("no id here"), null);
});

test("shows one banner when profile-service section errors are present", () => {
  const summary = summarizeProfileWarning({
    sectionErrors: [
      "profile service temporarily unavailable (request id: req-9)",
      "profile service temporarily unavailable (request id: req-9)",
      null,
    ],
  });
  assert.equal(summary.show, true);
  assert.equal(summary.requestId, "req-9");
});

test("shows banner when rows are degraded even without a section error", () => {
  const summary = summarizeProfileWarning({ sectionErrors: [], rowsDegraded: true });
  assert.equal(summary.show, true);
  assert.equal(summary.requestId, null);
});

test("does not show banner for unrelated section failures", () => {
  const summary = summarizeProfileWarning({
    sectionErrors: ["Unable to load active generation jobs."],
    rowsDegraded: false,
  });
  assert.equal(summary.show, false);
});

test("prefers an explicit request id over parsed section ids", () => {
  const summary = summarizeProfileWarning({
    sectionErrors: ["profile service temporarily unavailable (request id: parsed)"],
    requestId: "explicit",
    rowsDegraded: true,
  });
  assert.equal(summary.requestId, "explicit");
});

test("nonProfileSectionError keeps genuine queue failures but drops profile noise", () => {
  assert.equal(
    nonProfileSectionError("profile service temporarily unavailable (request id: x)"),
    null,
  );
  assert.equal(
    nonProfileSectionError("Unable to load active generation jobs."),
    "Unable to load active generation jobs.",
  );
});
