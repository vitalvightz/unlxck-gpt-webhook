export const ATHLETE_FULL_NAME_MAX = 120;
export const RECORD_MAX = 40;
export const INJURIES_MAX = 2000;
export const TRAINING_PREFERENCE_MAX = 1000;
export const MENTAL_BLOCKERS_MAX = 1500;
export const PREVIOUS_PLAN_FEEDBACK_MAX = 1500;
export const GUIDED_INJURY_AREA_MAX = 200;
export const GUIDED_INJURY_NOTES_MAX = 4000;
// Free-text entries on the Today (daily) injury check-in — the injury entry and
// the optional "anything else?" detail. Both are kept short on purpose: Today
// prioritises a fast, consistent report (body map + type tap), so the free text
// is a brief phrase (max 4 words / 40 chars), never a notes box. 4 words leaves
// room for real locations like "back of left knee" / "outside of right ankle".
export const TODAY_INJURY_TEXT_MAX = 40;
export const TODAY_INJURY_MAX_WORDS = 4;
export const AVATAR_URL_MAX = 2048;
