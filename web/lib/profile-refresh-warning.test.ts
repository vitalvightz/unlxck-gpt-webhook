import test from "node:test";
import assert from "node:assert/strict";

import {
  PROFILE_REFRESH_FAILED_BANNER_BODY,
  PROFILE_REFRESH_FAILED_BANNER_TITLE,
  PROFILE_REFRESH_FAILED_WARNING_CODE,
  PROFILE_REFRESH_FAILED_WARNING,
  hasProfileRefreshFailedWarning,
} from "./profile-refresh-warning";

test("detects profile refresh failure warnings from generation jobs", () => {
  assert.equal(
    hasProfileRefreshFailedWarning({ warnings: [PROFILE_REFRESH_FAILED_WARNING] }),
    true,
  );
});

test("does not show profile refresh banner for unrelated or missing warnings", () => {
  assert.equal(hasProfileRefreshFailedWarning({ warnings: ["Some other warning"] }), false);
  assert.equal(hasProfileRefreshFailedWarning({ warnings: [] }), false);
  assert.equal(hasProfileRefreshFailedWarning(null), false);
});

test("detects profile refresh failure warning milestones", () => {
  assert.equal(
    hasProfileRefreshFailedWarning({
      warnings: [],
      progress_milestones: [{ code: PROFILE_REFRESH_FAILED_WARNING_CODE }],
    }),
    true,
  );
});

test("uses the admin-facing profile refresh warning copy", () => {
  assert.equal(PROFILE_REFRESH_FAILED_BANNER_TITLE, "Profile refresh failed during generation.");
  assert.match(PROFILE_REFRESH_FAILED_BANNER_BODY, /Review the latest intake before approving or editing this plan/);
});

