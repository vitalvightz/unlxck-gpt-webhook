// Central source of athlete-facing copy explaining HOW Unlxck decides.
//
// Rules for anything added here:
// - Name the inputs plainly. An athlete who can see what was used can argue
//   with the output; one who cannot has to take it on faith.
// - Say what the athlete controls. A recommendation the athlete cannot refuse
//   is a rule, and this product does not make rules.
// - Never anthropomorphise. It is "your session changed", never "the AI thinks"
//   or "our AI decided" — the athlete is reading their own plan.
// - Describe signals as CONTRIBUTORS, never causes. The engine records which
//   signals were present when it decided, not that any one of them caused the
//   change, and the copy must not claim more than the engine knows.
// - Nothing here is a safety claim. Medical wording belongs in safety-copy.ts.

export const TRUST_INTRO_HEADING = "How Unlxck builds your camp";

export const TRUST_INTRO_BODY =
  "Your answers here shape the whole camp: your sport, fight date, schedule, equipment, goals, " +
  "and anything you are carrying. Nothing is generated until you review it.";

// Shown during intake, before the athlete has ever seen a daily recommendation,
// so the daily flow is not a surprise later.
export const TRUST_POINTS: readonly { title: string; body: string }[] = [
  {
    title: "Your plan stays your plan",
    body:
      "Daily check-ins never rewrite your saved camp. They adjust the session in front of you, and " +
      "every adjustment is recorded so you can see what changed and when.",
  },
  {
    title: "Changed sessions show their reasons",
    body:
      "When a session changes, you see the signals behind it and what it was based on: today's " +
      "check-in, your recent check-ins and sessions, and any injuries you are tracking.",
  },
  {
    title: "You stay in control",
    body:
      "You can follow the adjusted session, log what you actually did instead, or flag an injury " +
      "for review. Your coach's call always beats the app's.",
  },
];
