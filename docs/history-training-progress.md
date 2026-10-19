# History: Training Rhythm and Exercise Progress

Training Rhythm extends History's existing training summary. Home keeps the original summary. History retains its five tabs and the existing session/exercise detail views.

## Recorded training

- Weeks are Monday–Sunday, calculated from stored athlete-local training dates with UTC date-only arithmetic. The current week is explicitly partial. Comparisons use the last two completed weeks.
- The summary and weekly chart share eligibility and discipline classification. External sessions and reported UNLXCK completions count; skipped work, automatic day credits, unverified completions, and future dates do not.
- Occurrence identity is source plus ID. Distinct same-day sessions remain distinct. Plan discipline is never guessed from titles.
- The existing whole-day cursor must cover the complete requested window before trends appear. Failures offer retry without showing partial totals as complete.
- Minutes mean recorded minutes. Missing durations remain visible in the selected week and in both sides of any minute comparison. Sessions with no timed measurements show unavailable time instead of zero.
- The preview covers eight weeks. Trends offers four/twelve weeks, session/minute views, and recorded discipline filters. Leading empty weeks are trimmed; internal empty weeks remain.

## Exercise evidence

The existing performance endpoint adds nullable `performed_values`, resolved with the same `_actual`, `_performed`, and `performed_values` functions as the library index. The original reported/prescribed projection remains separate. No new database reads, endpoint, schema, logging, or best-load rules are introduced.

The browser plots only this projection. Metrics and units stay separate; there is no parsing of display strings, merging of exercise variants, estimation of unreported values, individual-set reconstruction, or 1RM calculation. Modified performances cannot inherit missing prescribed values. Zero-work, skipped, malformed, and otherwise ineligible records cannot create chart points.

Charts describe loaded records, with the existing action to load earlier performances. One measured result uses a factual readout, two use a comparison, and three or more use a chart. Missing measurements split the line; dates without logs do not invent measurements. Same-day entries remain separately selectable using the scrubber and previous/next controls. Selecting a record exposes its values and focuses its original timeline entry on request.

## Modal handoff and accessibility

Training Rhythm's controller retains the selected week, filters, scroll position, and originating session control. It closes/suspends its native dialog before mounting Session Details. Session Details delegates focus restoration to that controller; dismissing it reopens trends and focuses the original session control. Only one modal occupies the top layer at a time. The existing shared scroll lock remains authoritative.

SVGs provide visual marks; semantic weekly buttons and a labelled exercise range input expose the same values to keyboards and assistive technology. Touch controls are at least 44px. Chart scrolling is contained within the chart; selection is brought into view. Transitions respect reduced motion.

## Verification

- Python: exercise-library, session-details, training-history paging, exercise-log, store-protocol, and generated-contract regressions.
- Frontend: unit tests, typecheck, changed-file ESLint, and production build.
- Browser regressions: `training-progress.spec.ts`, `exercise-library.spec.ts`, and `history-session-details.spec.ts` at 390×844 and 1280×844. Include original record selection, missing-minute comparisons, modal focus handoff, sparse states, pagination, and axe checks.
- `PROGRESS_QA_DIR` optionally saves screenshots outside the repository. Browser visual inspection uses only synthetic fixture data from `web/e2e/fixtures/training-progress.ts`.

No migrations, RLS, environment-file changes, generation/readiness changes, or deployment are part of this feature. Production scale, Safari, and deployed full-stack behavior require separate verification.
