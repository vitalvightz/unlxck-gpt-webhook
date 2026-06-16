import stage2Policy from "../../shared/stage2-policy.json" with { type: "json" };

type Stage2Policy = {
  hard_stage2_blocker_codes: string[];
  publish_blocking_review_flag_codes: string[];
  card_rescuable_soft_codes: string[];
};

const policy = stage2Policy as Stage2Policy;

export const HARD_STAGE2_BLOCKER_CODES = policy.hard_stage2_blocker_codes;
export const STAGE2_HARD_BLOCKER_CODE_SET = new Set(HARD_STAGE2_BLOCKER_CODES);
export const PUBLISH_BLOCKING_REVIEW_FLAG_CODES = policy.publish_blocking_review_flag_codes;
