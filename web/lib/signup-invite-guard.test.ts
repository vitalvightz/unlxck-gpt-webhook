import test from "node:test";
import assert from "node:assert/strict";

import { NEW_ACCOUNT_WINDOW_MS, needsInviteCheck } from "./signup-invite-guard";

const now = Date.parse("2026-10-28T23:00:00Z");
const ago = (ms: number) => new Date(now - ms).toISOString();

test("a just-created account is checked for an invite", () => {
  assert.equal(needsInviteCheck({ created_at: ago(5_000) }, now), true);
  assert.equal(needsInviteCheck({ created_at: ago(NEW_ACCOUNT_WINDOW_MS - 1) }, now), true);
});

test("established accounts are not checked", () => {
  assert.equal(needsInviteCheck({ created_at: ago(NEW_ACCOUNT_WINDOW_MS + 1) }, now), false);
  assert.equal(needsInviteCheck({ created_at: "2025-01-01T00:00:00Z" }, now), false);
  assert.equal(needsInviteCheck({}, now), false);
  assert.equal(needsInviteCheck({ created_at: "not a date" }, now), false);
});

test("an account turned away before stays checked, however old", () => {
  assert.equal(needsInviteCheck({ created_at: "2025-01-01T00:00:00Z", invite_pending: true }, now), true);
});
