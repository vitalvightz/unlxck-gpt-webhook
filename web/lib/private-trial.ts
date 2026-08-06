// The private trial briefing shown once between account creation and
// onboarding, and kept permanently readable in Settings.
//
// Testers were completing onboarding without ever being told what the trial
// asks of them, so the copy lives here as data: one source for the gate screen
// and the Settings guide, and it stays unit-testable without a DOM.

import type { MeResponse } from "@/lib/types";

export const PRIVATE_TRIAL_TITLE = "UNLXCK PRIVATE TRIAL";

export const PRIVATE_TRIAL_INTRO =
  "You are testing an early version of UNLXCK. Use the app normally and report anything confusing, incorrect or broken.";

export const PRIVATE_TRIAL_DUTIES: readonly string[] = [
  "Complete onboarding honestly.",
  "Create and review your training plan.",
  "Complete any sessions you are able to do.",
  "Submit feedback after completed sessions.",
  "Report bugs with screenshots where possible.",
];

export const PRIVATE_TRIAL_CHECKS: readonly string[] = [
  "Does the plan match your sport, experience and schedule?",
  "Are the exercises and instructions clear?",
  "Is the session difficulty appropriate?",
  "Do injuries and recovery information change the plan correctly?",
  "Is the app easy to understand and use?",
];

export const PRIVATE_TRIAL_CLOSING =
  "Some features may be incomplete, slow or incorrect. Finding these problems is the purpose of the trial.";

export const PRIVATE_TRIAL_ACKNOWLEDGE_LABEL = "I UNDERSTAND — CONTINUE";

/**
 * True while the athlete still owes an acknowledgement.
 *
 * Only athletes are gated: admins, coaches and gym owners land on their own
 * workspaces and never pass through athlete onboarding. An unresolved profile
 * is never gated either — the auth guard handles that case, and blocking on a
 * null profile would strand the loading state behind this screen.
 */
export function requiresPrivateTrialAcknowledgement(me: MeResponse | null): boolean {
  if (!me || me.profile.role !== "athlete") {
    return false;
  }
  return !me.profile.private_trial_ack_at;
}
