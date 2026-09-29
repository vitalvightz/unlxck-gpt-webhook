import type { ResolvedTodayDecision } from "./today-authoritative";
import type { TodayCommandView } from "./types";

export type TodayNextStep = {
  title: string;
  detail: string;
  action: string;
  href: string;
};

/** A navigation prompt after a modified or skipped log, never a new prescription. */
export function getTodayNextStep(
  state: TodayCommandView,
  decision: ResolvedTodayDecision,
): TodayNextStep | null {
  const status = state.today.completion_status;
  if (status !== "modified" && status !== "skipped") return null;

  const title = status === "modified" ? "Adjustment logged" : "Skip logged";
  if (
    decision.authoritativeTier === "stop" ||
    decision.authoritativeTier === "pull_back" ||
    state.today.primary_safety_notice
  ) {
    const guidanceVisible = decision.primaryMessageKind === "decision" ||
      decision.primaryMessageKind === "safety_notice";
    return {
      title,
      detail: "Today's safety decision still applies. Check in again before your next session.",
      action: guidanceVisible ? "Review guidance" : "View session log",
      href: guidanceVisible ? "#today-decision" : "/history",
    };
  }

  if (state.today.session_scope === "next" && state.today.next_session.session_id) {
    const nextTitle = state.today.next_session.title?.trim() ||
      state.today.next_session.label?.trim() || "Your next session";
    return {
      title,
      detail: `${nextTitle} is planned next. Check in on that training day before starting.`,
      action: "Preview next session",
      href: "#today-session",
    };
  }

  return {
    title,
    detail: "Your camp plan stays as scheduled. Check in again before your next session.",
    action: "Open camp plan",
    href: `/plans/${state.active_plan.id}`,
  };
}
