import stage2Policy from "../../shared/stage2-policy.json" with { type: "json" };

type Stage2Policy = {
  hard_stage2_blocker_codes: string[];
  athlete_release_with_flags_codes: string[];
  admin_review_blocking_codes: string[];
  card_rescuable_soft_codes: string[];
};

const policy = stage2Policy as Stage2Policy;

export const HARD_STAGE2_BLOCKER_CODES = policy.hard_stage2_blocker_codes;
export const STAGE2_HARD_BLOCKER_CODE_SET = new Set(HARD_STAGE2_BLOCKER_CODES);
export const ATHLETE_RELEASE_WITH_FLAGS_CODES = policy.athlete_release_with_flags_codes;
export const ADMIN_REVIEW_BLOCKING_CODES = policy.admin_review_blocking_codes;
