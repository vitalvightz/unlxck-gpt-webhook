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

export const TRUST_INTRO_HEADING = "How Unlxck works";

// Four cards, not four paragraphs. Nobody reads prose on an intake screen, and
// an explanation that goes unread builds no trust at all. Every body line is one
// or two short sentences so the whole block can be scanned in a few seconds.
export const TRUST_POINTS: readonly { title: string; body: string }[] = [
  {
    title: "Your answers build your camp",
    body: "Everything starts with your sport, fight date, schedule, equipment and goals.",
  },
  {
    title: "Daily check-ins adjust today",
    body: "Your camp stays the same. Today's session changes only when it needs to.",
  },
  {
    title: "Every change has a reason",
    body: "You always see the signals behind a change, and what it was based on.",
  },
  {
    title: "You're always in control",
    body: "Follow the change, log what you actually did, or take your coach's call instead.",
  },
];
