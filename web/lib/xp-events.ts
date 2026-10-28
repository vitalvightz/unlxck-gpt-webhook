import type { XpAction } from "@/lib/xp";

export const XP_REFRESH_EVENT = "unlxck:xp-refresh";

export function requestXpRefresh(): void {
  if (typeof window !== "undefined") {
    window.dispatchEvent(new Event(XP_REFRESH_EVENT));
  }
}

/**
 * XP actions each kind of confirmation toast can earn. A confirmation passes one
 * of these as `mergeKeys` so the reward it triggers folds into it, and only it.
 */
export const XP_TOAST_KEYS = {
  session: [
    "training_logged",
    "planned_session_completed",
    "manual_training_logged",
    "first_session_logged",
    "first_exercise_logged",
    "stop_decision_followed",
    "full_training_week_completed",
    "phase_completed",
    "first_plan_completed",
    "camp_completed",
    "training_days_10",
    "training_days_25",
    "training_days_50",
    "training_days_100",
  ],
  checkin: ["first_checkin_completed", "readiness_checkin_completed"],
  injury: ["injury_update_completed"],
} as const satisfies Record<string, readonly XpAction[]>;
