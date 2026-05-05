import assert from "node:assert/strict";
import { describe, it } from "node:test";

import { buildBlockedWhy } from "@/lib/triage-block-reasons";

describe("buildBlockedWhy", () => {
  it("returns generic paused message when no signals exist", () => {
    const result = buildBlockedWhy({ red_flags: [], matched_high_risk_categories: [] });
    assert.equal(result.title, "Why this was paused");
    assert.match(result.body, /safety hold/);
  });

  it("returns coach wording with mapped clinical reason", () => {
    const result = buildBlockedWhy({ red_flags: ["breathing_pain"], matched_high_risk_categories: [] });
    assert.equal(result.title, "Why this was blocked");
    assert.match(result.body, /Breathing pain was reported/);
  });
});
