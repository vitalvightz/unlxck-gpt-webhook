# Session hierarchy design QA

source visual truth path: `C:/Users/Micha/AppData/Local/Temp/codex-clipboard-a262bbe1-b611-443d-8cf8-ebb924d898e0.png`

implementation screenshot path: `output/playwright/session-essential-collapsed.png`

expanded implementation screenshot path: `output/playwright/session-essential-expanded.png`

mobile implementation screenshot path: `output/playwright/session-essential-mobile.png`

mobile expanded implementation screenshot path: `output/playwright/session-essential-mobile-expanded.png`

full-view comparison path: `output/playwright/session-essential-comparison.png`

viewport: desktop `1522 x 846` CSS px, mobile `390 x 844` CSS px

pixel dimensions and normalization:
- Source: `1522 x 846` px.
- Desktop implementation: `1522 x 846` px at device scale factor 1.
- Expanded desktop element: `1120 x 1233` px at device scale factor 1.
- Mobile viewport: `390 x 844` px at device scale factor 1.
- Expanded mobile element: `358 x 1470` px at device scale factor 1.
- The comparison image uses equal `1120 x 674` content canvases separated by a red divider. Browser chrome and the mockup-only concept switcher are excluded.

state: dark theme; workout expanded; coaching notes collapsed for the primary comparison. Expanded coaching and Coming soon video states were checked separately.

browser verification:
- The Codex in-app browser failed to attach reliably to the local Next.js preview, so the repository browser verification used the Playwright CLI with Microsoft Edge as a documented fallback.
- Desktop collapsed, desktop expanded, mobile collapsed, and mobile expanded states were rendered.
- Browser console check returned 0 errors and 0 warnings.
- The real React click path was also exercised in `structured-plan-interaction.test.tsx`: opening coaching notes updates `aria-expanded`, reveals block notes, reveals mindset detail, and exposes the video placeholder.

## Full-view comparison evidence

- Essential 01's title, Why line, single session tag, numbered exercise rows, metric columns, dividers, and one coaching disclosure remain recognizable in the implementation.
- The selected black panel, white typography, muted secondary text, fine borders, and disciplined red accent map directly to the existing Unlxck tokens.
- The approved Coach split influence replaces the generic focus strip with a stronger In your corner lead and support line.
- The collapsed state is shorter than the source's open coaching state by design; the user explicitly confirmed that clicking should open the session larger.

## Focused region comparison evidence

- Typography: the desktop session title was increased after the first render to restore the source's display hierarchy; UI labels stay in the existing mono treatment.
- Spacing and layout rhythm: the workout expansion control moved below the exercises so it no longer interrupts the In your corner-to-workout reading sequence.
- Colors and tokens: no new palette was introduced. Brand red is reserved for Why, In your corner, coaching/video labels, and disclosure direction.
- Image quality and asset fidelity: the selected screen contains no raster or illustrative assets. The reserved YouTube region is intentionally an empty semantic placeholder and does not fake a thumbnail or play control.
- Copy and content: deterministic session, metric, adjustment, and safety fields remain unchanged. Approved additions are `In your corner`, `Video coaching`, `Movement demos are coming soon.`, and `Coming soon`.
- Mobile: the exercise prescription becomes a two-column row with a three-column metric strip; expanded coaching and the 16:9 video reservation stack without horizontal overflow.

## Findings

- No remaining P0/P1/P2 findings.

## Comparison history

1. First comparison
   - P2: the existing Show less pill appeared between In your corner and the exercise rows, interrupting the selected hierarchy.
   - Fix: moved the workout collapse control to the bottom of the expanded session.
   - Post-fix evidence: `output/playwright/session-essential-collapsed.png`.
2. Second comparison
   - P2: the live session title was materially smaller than Essential 01's title.
   - Fix: increased the responsive session-title scale while preserving mobile wrapping.
   - Post-fix evidence: `output/playwright/session-essential-comparison.png` and `output/playwright/session-essential-mobile.png`.

## Intentional deviations

- The mockup-only Unlxck top bar and concept tabs are not part of `SessionCard`; they belong to the surrounding app/prototype shell.
- The source image shows coaching detail open. Production defaults it closed because the selected product behavior is progressive disclosure.
- The existing Show less session control remains at the bottom so athletes can collapse the workout without collapsing the parent day.
- The video region says Coming soon and has no inert play button; a future YouTube iframe can replace the reserved 16:9 region.

## Implementation checklist

- [x] Essential 01 information hierarchy.
- [x] In your corner lead and support language.
- [x] One coaching disclosure controlling mindset, adjustments, swaps, and safety detail.
- [x] Reserved responsive YouTube/video region with Coming soon state.
- [x] Keyboard and screen-reader disclosure state through `button`, `aria-expanded`, `aria-controls`, and `hidden`.
- [x] Desktop and mobile responsive checks.
- [x] Reduced-motion fallback.

## Follow-up polish

- P3: replace the Coming soon state with the real YouTube iframe only when a final video URL, consent/cookie behavior, and thumbnail treatment are available.

final result: passed
