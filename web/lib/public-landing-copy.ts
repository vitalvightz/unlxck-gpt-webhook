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

// First-viewport value line under the hero title. Outcome-led, not a feature
// list. This is the sentence that has to land the product in one read.
export const PUBLIC_HERO_SUMMARY =
  "Know what to train today, and adjust before fatigue becomes failure.";

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

// Proof grid. Outcome-led headlines that each say something distinct, so no
// section just re-lists the pipeline.
export const LANDING_PRODUCT_PROOF_POINTS = [
  {
    label: "Today",
    title: "Know what to train today.",
    body: "Open the app and see the session that fits your fight date, current load, and availability, not a generic block.",
  },
  {
    label: "Readiness",
    title: "Adjust before fatigue becomes failure.",
    body: "Check-ins keep load, recovery, and injury limits in view, so today's work bends to how you're actually recovering.",
  },
  {
    label: "Decisions",
    title: "Turn check-ins into clear training decisions.",
    body: "Daily inputs resolve into a straight answer: train hard, modify, or pull back. It's a decision, not another dashboard to read.",
  },
  {
    label: "Full camp",
    title: "Keep the camp moving without guessing.",
    body: "Every session stays tied to your fight date, so today's work can adapt while the rest of the camp stays aligned.",
  },
] as const;

// "How it works" steps. Legitimately process-framed (setup flow), kept distinct
// from the benefit sections and anchored to outcomes at each step.
export const LANDING_WORKFLOW_STEPS = [
  {
    label: "Step 1",
    title: "Complete intake",
    body: "Add your fight date, schedule, style, history, and restrictions.",
  },
  {
    label: "Step 2",
    title: "Check in on readiness",
    body: "Log load, recovery, and any injury limits before each block.",
  },
  {
    label: "Step 3",
    title: "Generate the camp",
    body: "Get phases, sessions, and targets built around your fight date.",
  },
  {
    label: "Step 4",
    title: "Adapt as you go",
    body: "Return between sessions and let today's work adjust to where you are.",
  },
] as const;
