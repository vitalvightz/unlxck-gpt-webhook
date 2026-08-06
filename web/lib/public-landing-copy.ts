// Public landing (logged-out homepage) marketing copy.
//
// Kept in one pure module so the copy is unit-testable and so the outcome-led
// voice stays consistent instead of drifting per-section. The homepage used to
// repeat the same "Intake / Readiness / Camp Plan / Saved History" feature list
// across four sections; the pipeline taxonomy now lives in exactly one place,
// the workspace-preview mock (LANDING_WORKSPACE_ROWS), while every prose
// section is written around what the athlete achieves.
//
// Copy rules (see also lib/safety-copy.ts):
// - Lead with outcomes, not stored features.
// - Direct, athlete-focused, brand voice intact. Not every heading is a shout.
// - No medical overpromise: never imply diagnosis, injury prevention, medical
//   clearance, or guaranteed performance. "adapts / bends to how you recover",
//   not "keeps you safe / injury-free".
// - Don't repeat the same benefit across sections.

// First-viewport lead under the hero title. Names the product category in one
// read (what it is, who it's for), so a new visitor isn't left inferring it.
export const PUBLIC_HERO_LEAD =
  "Personalised fight camps that adapt to your readiness, recovery and injuries.";

// Supporting value line beneath the lead. Outcome-led, not a feature list.
export const PUBLIC_HERO_SUMMARY =
  "Know what to train today, and adjust before fatigue becomes failure.";

// Featured "Today" state for the top of the workspace preview. A concrete, live
// adaptation (not a static workflow list) so a visitor grasps what the product
// actually does in a couple of seconds. Mock data — makes no medical claim.
export const LANDING_TODAY_PREVIEW = {
  eyebrow: "Today",
  status: "Modified session",
  changes: [
    { direction: "down" as const, text: "Heavy bag rounds reduced" },
    { direction: "up" as const, text: "Reaction drills increased" },
  ],
  reasonLabel: "Reason",
  reason: "High fatigue reported",
} as const;

// Hero proof strip. Three short outcome pills (was four feature nouns).
export const LANDING_OUTCOME_POINTS = [
  { label: "Today", value: "Know what to train" },
  { label: "Readiness", value: "Adjust before fatigue" },
  { label: "Every session", value: "Decisions, not guesses" },
] as const;

// Workspace-preview mock rows. This is the single place the product pipeline is
// enumerated, because it stands in for a screenshot of the real sidebar/stages.
export const LANDING_WORKSPACE_ROWS = [
  {
    step: "01",
    label: "Intake",
    status: "Complete",
    title: "Intake",
    body: "Fight date, schedule, style, goals, and restrictions.",
  },
  {
    step: "02",
    label: "Readiness",
    status: "Checked",
    title: "Readiness",
    body: "Load, recovery, nutrition, and injury limits.",
  },
  {
    step: "03",
    label: "Camp plan",
    status: "Ready",
    title: "Camp plan",
    body: "Phases, sessions, targets, and recovery.",
  },
  {
    step: "04",
    label: "Today",
    status: "Live",
    title: "Today",
    body: "The next session, adapted to how you checked in.",
  },
] as const;

// Proof grid. Three distinct benefit cards (was four, plus a separate
// "Decisions" card that repeated the readiness/full-camp promise). Each headline
// says something the others don't, so no section re-lists the pipeline.
export const LANDING_PRODUCT_PROOF_POINTS = [
  {
    label: "Today",
    title: "Know today's session.",
    body: "See the work that fits your fight date, schedule, and current condition.",
  },
  {
    label: "Readiness",
    title: "Adapt before you break down.",
    body: "Readiness and injury check-ins adjust the session when needed.",
  },
  {
    label: "Full camp",
    title: "Keep the camp aligned.",
    body: "Changes to today's work stay connected to the full camp.",
  },
] as const;

// "How it works" steps. Legitimately process-framed (setup flow), kept distinct
// from the benefit sections and anchored to outcomes at each step.
export const LANDING_WORKFLOW_STEPS = [
  {
    label: "Step 1",
    title: "Complete your intake",
    body: "Add your fight date, weekly schedule, training history, and restrictions.",
  },
  {
    label: "Step 2",
    title: "Check in before training",
    body: "Report your recovery, fatigue, soreness, and active injuries.",
  },
  {
    label: "Step 3",
    title: "Receive your camp",
    body: "Get phases, weekly targets, and sessions built around your fight date.",
  },
  {
    label: "Step 4",
    title: "Adapt session by session",
    body: "Unlxck modifies today's work while keeping the wider camp aligned.",
  },
] as const;
