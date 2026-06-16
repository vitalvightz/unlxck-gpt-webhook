import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import test from "node:test";

import {
  HARD_STAGE2_BLOCKER_CODES,
  PUBLISH_BLOCKING_REVIEW_FLAG_CODES,
} from "./stage2-policy.ts";

type Stage2Policy = {
  hard_stage2_blocker_codes: string[];
  publish_blocking_review_flag_codes: string[];
};

test("frontend hard blocker codes stay in sync with shared policy JSON", () => {
  const policy = JSON.parse(
    readFileSync(resolve(import.meta.dirname, "../../shared/stage2-policy.json"), "utf8"),
  ) as Stage2Policy;

  assert.deepEqual(HARD_STAGE2_BLOCKER_CODES, policy.hard_stage2_blocker_codes);
  assert.deepEqual(
    PUBLISH_BLOCKING_REVIEW_FLAG_CODES,
    policy.publish_blocking_review_flag_codes,
  );
});
