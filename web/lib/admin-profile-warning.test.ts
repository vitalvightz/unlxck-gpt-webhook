import test from "node:test";
import assert from "node:assert/strict";

import {
  extractRequestId,
  ADMIN_SERVICE_WARNING_TITLE,
  PROFILE_SERVICE_WARNING_TITLE,
  isAdminServiceUnavailableMessage,
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

test("nonProfileSectionError suppresses a pure profile-service error", () => {
  assert.equal(
    nonProfileSectionError("profile service temporarily unavailable (request id: x)"),
    null,
  );
  assert.equal(nonProfileSectionError("Store service temporarily unavailable"), null);
  assert.equal(
    nonProfileSectionError(
      "profile service temporarily unavailable (request id: a) profile service temporarily unavailable (request id: b)",
    ),
    null,
  );
});

test("nonProfileSectionError does not suppress an unrelated error", () => {
  assert.equal(
    nonProfileSectionError("Unable to load active generation jobs."),
    "Unable to load active generation jobs.",
  );
  assert.equal(
    nonProfileSectionError("failed to load athlete directory"),
    "failed to load athlete directory",
  );
});

test("nonProfileSectionError preserves the unrelated part of a mixed error", () => {
  assert.equal(
    nonProfileSectionError("profile service temporarily unavailable; failed to load review queue"),
    "failed to load review queue",
  );
  assert.equal(
    nonProfileSectionError(
      "Unable to load athlete accounts. profile service temporarily unavailable (request id: x)",
    ),
    "Unable to load athlete accounts.",
  );
  assert.equal(
    nonProfileSectionError(
      "profile service temporarily unavailable (request id: x) failed to load plan history",
    ),
    "failed to load plan history",
  );
});

test("nonProfileSectionError keeps internal hyphenation intact", () => {
  assert.equal(
    nonProfileSectionError("profile service temporarily unavailable; non-blocking validation failed"),
    "non-blocking validation failed",
  );
});

test("profile banner still shows for mixed errors and keeps the request id", () => {
  const summary = summarizeProfileWarning({
    sectionErrors: [
      "profile service temporarily unavailable (request id: req-7); failed to load review queue",
    ],
  });
  assert.equal(summary.show, true);
  assert.equal(summary.requestId, "req-7");
});

test("detects admin-service unavailable messages", () => {
  assert.equal(
    isAdminServiceUnavailableMessage("authentication service temporarily unavailable (request id: abc)"),
    true,
  );
  assert.equal(isAdminServiceUnavailableMessage("Request failed: 502 Request failed: 502"), true);
  assert.equal(isAdminServiceUnavailableMessage("Unable to load active generation jobs."), false);
});

test("shows support-data banner for authentication and gateway failures", () => {
  const summary = summarizeProfileWarning({
    sectionErrors: [
      "authentication service temporarily unavailable (request id: old)",
      "authentication service temporarily unavailable (request id: latest)",
    ],
  });
  assert.equal(summary.show, true);
  assert.equal(summary.title, ADMIN_SERVICE_WARNING_TITLE);
  assert.equal(summary.requestId, "latest");
});

test("keeps profile banner title for profile-service failures", () => {
  const summary = summarizeProfileWarning({
    sectionErrors: ["profile service temporarily unavailable (request id: req-1)"],
  });
  assert.equal(summary.title, PROFILE_SERVICE_WARNING_TITLE);
});

test("nonProfileSectionError suppresses pure admin-service failures", () => {
  assert.equal(
    nonProfileSectionError(
      "authentication service temporarily unavailable (request id: a) authentication service temporarily unavailable (request id: b)",
    ),
    null,
  );
  assert.equal(nonProfileSectionError("Request failed: 502 Request failed: 502"), null);
});
