# Core Athlete Flow UI/UX Plan

## Scope

This plan covers the four surfaces an athlete touches every camp, in order:

1. **Intake** — `app/onboarding/page.tsx` → `components/plan-intake-form.tsx`
   (multi-step wizard; `/intake` redirects here).
2. **Generate** — `app/generate/page.tsx` → `components/premium-loading-screen.tsx`
   (phased build/loading screen).
3. **Today** — `app/today/page.tsx` → `components/today-screen.tsx`
   (daily decision + execution surface).
4. **Plan Viewer** — `app/plans/[planId]/page.tsx` →
   `components/plan-detail-screen.tsx` → `components/plan-viewer.tsx`
   (full camp map).

The landing page is out of scope — it has a shipped plan in
`docs/landing-page-ui-ux-plan.md`. The navigation hierarchy contract in
`docs/block-4-ux-hierarchy-addendum.md` is treated as locked; nothing here
changes tab roles or the landing resolver.

This is a plan only. No component code is changed by this document. Every
proposed change is designed to be small, reviewable, and shipped one surface
at a time.

## Guiding Constraints

- Keep the UNLXCK aesthetic from `agents.md`: black premium base, white bold
  typography, red accents for emphasis only. No new gradients, no soft
  wellness styling, no generic SaaS chrome, no animation that does not improve
  clarity.
- Reuse the existing design tokens in `app/globals.css` (`--brand-red`,
  `--radius-*`, `--space-*`, `--text-*`). Do not introduce parallel scales.
- Preserve all current behaviour: generation recovery/reconnect, injury
  triage gating, admin-review pauses, step validation, and reduced-motion
  fallbacks. UI changes must not touch the deterministic generation contract.
- Mobile-first. Every change is verified at 390×844 before desktop.

## Priority Legend

- **P0** — friction or clarity defect on the critical path; do first.
- **P1** — meaningful polish or hierarchy win.
- **P2** — refinement, nice-to-have.

---

## 1. Intake (`plan-intake-form.tsx`)

### Current state

- Multi-step wizard: Athlete → Fight → Training → Performance → Review.
- Desktop uses `step-pill-*` states (complete / active / upcoming); mobile
  uses `mobile-step-rail-item-*` with auto-scroll to the active item.
- Validation is centralised and maps each error to a `{ message, step,
  fieldId }` so the form can jump the user to the offending field.
- Body map drives injury capture.
- The file is ~3,300 lines — the single largest component in the app.

### Proposed updates

- **P0 — Error-to-field focus proof.** Validation already resolves a
  `fieldId` and target `step`. Confirm every returned `fieldId` actually
  receives focus and an `aria-describedby` error association after a jump, and
  that the mobile step rail scrolls the target into view. A validation map is
  only useful if the field visibly takes focus.
- **P0 — Persistent progress affordance on mobile.** The step rail scrolls;
  make sure "Step X of N" and remaining-count copy (already computed as
  `stepNumber` / `remainingSteps`) stay visible without horizontal scrolling,
  so the athlete always knows how much intake is left.
- **P1 — Review step scannability.** The Review step uses
  `ReviewDetailList` (label/value pairs). Group it under the same section
  headings as the steps (Athlete / Fight / Training / Performance) with an
  inline "Edit" link per group that deep-links back to that step, instead of
  one flat list. Lowers the cost of a last-minute correction.
- **P1 — `OptionalDetails` consistency.** Standardise the collapsed
  optional-detail disclosure (title + hint) so every step's optional inputs
  use the same pattern and the same expand/collapse affordance.
- **P2 — Sticky primary action on mobile.** Keep the "Continue / Review"
  primary button pinned above the mobile tab bar so long steps never bury the
  advance action below the fold. Respect `--mobile-tab-bar-clearance`.
- **P2 — File decomposition (non-visual).** Split the 3,300-line component
  into per-step subcomponents behind the existing form state. Pure
  maintainability; zero behaviour change. Sequence this after the visual work
  so review diffs stay legible.

---

## 2. Generate (`premium-loading-screen.tsx`)

### Current state

- Phased screen: `submitting → queued → running → reconnecting → finalizing`,
  plus `already_generated`, `review_paused`, `failed`.
- Each phase has full `PHASE_CONTENT` copy (eyebrow, title, copy, chip,
  reassurance) and an ordered `WORKFLOW_STEPS` list.
- Shows `StageOnePreviewCard` and `GenerationProgressMilestones`.
- Strong reassurance messaging ("safe to leave and return; reconnects to the
  same build").

### Proposed updates

- **P1 — Single source of truth for phase → step mapping.** `PHASE_ORDER`,
  `WORKFLOW_STEPS`, and `PHASE_CONTENT` are three parallel structures keyed by
  phase. Derive the active/complete step state from one map so a future phase
  edit can't desync the visual stepper from the copy.
- **P1 — Elapsed-time legibility.** Confirm the elapsed timer (driven by
  `startedAtMs`) reads calmly — monospace via `--font-mono`, no layout shift
  as digits change — and that it stops on terminal phases
  (`review_paused`, `failed`, `already_generated`).
- **P1 — Terminal-state action clarity.** `failed`, `review_paused`, and
  `already_generated` each already surface distinct actions (retry, open plan
  history, refine intake, return to workspace). Ensure exactly one visually
  dominant action per terminal state and that the others read as secondary —
  no competing primary CTAs on a dead-end screen.
- **P2 — Milestone motion restraint.** Audit `GenerationProgressMilestones`
  for any pulse/spin that runs indefinitely; cap or calm it, and verify the
  `prefers-reduced-motion` path renders a static completed/active state.
- **P2 — Stage-one preview framing.** Frame `StageOnePreviewCard` as a
  concrete "here's what we already locked in" proof point during the wait,
  reinforcing that leaving is safe, rather than reading as decorative filler.

---

## 3. Today (`today-screen.tsx`)

### Current state

- `today-shell` hero with kicker/title/meta and a hero action row.
- `today-readiness-strip` status cells (Check-in / Injury / Session) with
  `data-tone` dots: pending (amber, pulsing), clear (green), risk (red).
- Composes `CampProgressBar`, `TodayReadinessForm`, `TodayInjuryManager`,
  `TodayRiskWatch`, `TodaySessionPanel`.
- Distinct empty (`NoActivePlanState`) and error states.

### Proposed updates

- **P0 — Fix the empty-state redirect hop.** `NoActivePlanState` links to
  `/intake`, which server-redirects to `/onboarding` (`app/intake/page.tsx` is
  a `redirect`). Point the CTA straight at `/onboarding` to remove the extra
  hop and the flash. One-line change.
- **P0 — One dominant CTA in the no-check-in state.** The hierarchy contract
  (`block-4-ux-hierarchy-addendum.md` §1, row 6) requires exactly one dominant
  "Check in / Open Today" action when a returning athlete has not checked in.
  Verify the Today hero enforces this — the readiness form's start action
  should be the single primary; "View plan / History / Home" must read as
  secondary/ghost, which the current markup (`secondary-button`,
  `ghost-button`) already implies but should be visually confirmed.
- **P1 — Readiness strip → decision, not just status.** The strip currently
  reports state (Due / Logged, injuries, session). Make each pending cell
  tappable to its action (Check-in cell → readiness form, Injury cell →
  injury manager, Session cell → session panel) so status doubles as
  navigation on the decision surface.
- **P1 — Injury tone accessibility.** The red "risk" and amber "pending"
  tones must not be the only signal. Confirm each `data-tone` cell pairs the
  colour with its text label (it does today) and add a shape/icon cue so the
  distinction survives colour-blindness and the pulsing animation respects
  reduced motion.
- **P2 — Hero meta density.** The hero action row carries three ghost links
  (View plan / History / Home). On mobile, collapse History/Home into the
  existing tab bar reliance and keep only the plan link in the hero to reduce
  competing targets.

---

## 4. Plan Viewer (`plan-viewer.tsx` / `plan-detail-screen.tsx`)

### Current state

- `plan-detail-screen` handles the read-after-write 404 window with retry
  (`PLAN_LOAD_MAX_ATTEMPTS`) before showing a failure card.
- `plan-viewer` (~3,000 lines) renders `panel` / `support-panel` /
  `plan-text-panel` sections, a `plan-next-session` region, injury-risk
  badges, accordions, structured plan cards
  (`structured-plan-renderer.tsx`), retry banners, and admin-only sections.

### Proposed updates

- **P0 — "Next session" as the anchor.** The `plan-next-session` region is
  the athlete's most-wanted answer ("what do I do next"). Confirm it sits
  above the full-camp map on first load and is the visual focal point, not one
  card among many. This is the bridge from Today into the plan.
- **P1 — Section wayfinding for a long plan.** A full camp is long. Add a
  lightweight sticky in-page section index (Overview / Next session / Weeks /
  Injuries / Notes) so the athlete can jump without scrolling the whole map.
  Reuse existing section headings; no new taxonomy.
- **P1 — Status-badge vocabulary.** `STRUCTURED_CARD_STATUS_LABELS` and the
  injury-risk band labels drive several badges. Audit that the badge palette
  maps consistently to tokens (ready/publishable = calm, flagged = gold
  `--progress-gold`, blocked/triage = red `--brand-red`) and that the same
  state never renders two different colours across panels.
- **P1 — Retry/paused banners hierarchy.** Stage-2 retry and
  triage/admin-review banners (`support-panel-alert`,
  `stage2-retry-banner`) should read as clearly subordinate to the plan body
  when the plan is publishable-with-flags, and clearly dominant when the plan
  is non-publishable. Tie banner prominence to plan status, not fixed styling.
- **P2 — Plan header actions.** Consolidate export/copy/download actions
  (there is a text `Blob` download path today) into one consistent action
  cluster in the plan header rather than scattered inline buttons.
- **P2 — Structured-card density on mobile.** Verify structured plan cards
  collapse cleanly at 390px with no horizontal overflow and readable
  round/exercise rows.

---

## Cross-Cutting

- **Empty / loading / error parity.** Each surface has its own skeleton and
  empty/error states (`Skeleton`, `today-*-state`, `PlanDetailStateCard`,
  loading phases). Align their tone, spacing, and CTA patterns so the flow
  feels like one product across states.
- **Reduced motion.** The nav already gates animation on
  `prefers-reduced-motion`. Apply the same gate to any pulsing readiness dot,
  milestone animation, or CTA sweep introduced or touched here.
- **Focus management.** On step jumps (Intake), phase transitions (Generate),
  and route entry (Today/Plan), move focus to the new primary heading/region
  so keyboard and screen-reader users track the change.
- **Token discipline.** No hard-coded hex or spacing values in touched code —
  route everything through `app/globals.css` variables.

## Responsive Plan

- **Mobile (390×844)** is the reference viewport. Sticky primary actions
  respect `--mobile-tab-bar-clearance`; no surface may scroll horizontally.
- **Tablet** stacks two-column heroes (Today, Plan) to avoid cramped reading,
  consistent with the landing-page plan's tablet rule.
- **Desktop** may use two-column layouts (plan body + rail, today hero +
  actions) but the mobile single-column order stays the source of truth for
  content priority.

## Rollout Sequencing

1. **Today P0s** — empty-state redirect fix and single-dominant-CTA check.
   Smallest, highest-frequency surface; ships first as a confidence-builder.
2. **Intake P0s** — error-to-field focus proof and mobile progress
   visibility. Fixes the highest-friction entry point.
3. **Plan Viewer P0/P1** — next-session anchor and section wayfinding.
4. **Generate P1s** — phase-map unification and terminal-state clarity.
5. **P2s and the Intake file decomposition** last, once the visible flow is
   settled.

Each numbered item is its own PR with before/after screenshots at 390×844 and
1440×1000.

## Verification Checklist (per PR)

- `npm run typecheck`, `npm run lint`, and `npm run test:unit` pass in `web/`.
- Relevant Playwright e2e specs in `web/e2e` still pass.
- Manual DOM/browser check at 390×844 and 1440×1000, with a
  reduced-motion pass.
- No new fake metrics, no AI-generated fighter imagery, no new gradients.
- Generation recovery, injury triage gating, and admin-review pauses behave
  exactly as before (no change to the deterministic generation contract).

## Out of Scope

- Landing / marketing page (already planned and shipped).
- Nutrition, history, onboarding-auth, settings, admin, coach, and gym-owner
  surfaces.
- Navigation hierarchy and the landing-state resolver (locked contract).
- Any backend, Supabase, or generation-pipeline logic change.
