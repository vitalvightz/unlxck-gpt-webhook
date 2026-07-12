import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  ADMIN_REVIEW_BLOCKING_CODES,
  ATHLETE_RELEASE_WITH_FLAGS_CODES,
  HARD_STAGE2_BLOCKER_CODES,
} from "./stage2-policy.ts";

type Stage2Policy = {
  hard_stage2_blocker_codes: string[];
  athlete_release_with_flags_codes: string[];
  admin_review_blocking_codes: string[];
};

test("frontend hard blocker codes stay in sync with shared policy JSON", () => {
  const policy = JSON.parse(
    readFileSync(resolve(import.meta.dirname, "../../shared/stage2-policy.json"), "utf8"),
  ) as Stage2Policy;

  assert.deepEqual(HARD_STAGE2_BLOCKER_CODES, policy.hard_stage2_blocker_codes);
  assert.deepEqual(
    ATHLETE_RELEASE_WITH_FLAGS_CODES,
    policy.athlete_release_with_flags_codes,
  );
  assert.deepEqual(ADMIN_REVIEW_BLOCKING_CODES, policy.admin_review_blocking_codes);
});
