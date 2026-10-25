# UNLXCK — design direction for review

Three independent high-resolution mobile concepts. Design exploration only; no application files were changed during this pass. These are static mockups, not an implemented or tested interface.

## Shared language

Near-black canvas, charcoal content surfaces, confident grotesk headings, readable secondary text, moderate corners, consistent outline icons and an 8-point spacing rhythm. Deep red identifies the primary action, selection and critical safety signals. Surfaces establish grouping; dividers separate content within groups. Detail screens retain their own back navigation rather than duplicating the bottom tab bar.

## Plan

Camp identity, phase, selected week and completion share one surface. The next session has the highest action emphasis. Upcoming work is quieter; recovery is a compact, non-actionable row. Notes are secondary. Important global stop guidance stays visible.

Review: hierarchy leads from camp to next session; density accommodates overview and scheduled training in one phone-shaped composition; the next-session CTA is explicit; selected weeks and primary actions share the brand accent; labels remain readable; duplicated percentages and repeated session-type copy were removed in refinement. This is a sample week, not a live account screenshot.

## Session

Session title and concise activity-derived description establish purpose. Three ordered activities share a single surface with dividers. Demonstration thumbnails, exact dose and rest support scanning; exercise menus expose existing edit/replace/remove actions. Add exercise remains discoverable. Open Today points to the existing start/logging surface rather than inventing a new workout execution flow.

Review: title, purpose, exercise group and primary action have distinct weights; thumbnails give the list visual substance; individual exercise rows retain separate navigation and management affordances; stop guidance stays ahead of the training action; the main prescription is not expanded into repeated panels. The menu-explanation helper is secondary and can be omitted if discovery tests show it is unnecessary.

## Exercise

Demonstration leads, followed by one prescription band, technique, local stop criteria, global stop guidance, an existing easier option and supported management actions. Missing values would be omitted. The easier option is explicitly labelled as an alternative, not a repeated main prescription.

Review: media is the focal point; main dosage appears only once; instructional text has a clear heading and comfortable measure; local amber and global red safety semantics remain distinct; edit and replace are separated from workout execution; bottom controls respect a visible safe area. The illustrated demo frames do not verify that a particular account has a playable video. Implementation must use only resolved valid media and omit unavailable demonstrations.

## Source and limits

Exercise names, doses, rest intervals, cues, stop rules and regression come from `tests/fixtures/concise_coaching/october_11_15.json`, first recorded Strength session: Reactive Start Burst (3 × 4 sec, 180 sec rest); Jump Squat (4 × 3 reps, 90 sec rest, bodyweight); Punch-Specific Max Isometric Hold (3 × 12 sec, 180 sec rest). Jump Squat cue: drive with hips, extend through the toes and land quietly. Stops: big drop in jump height; painful landing. Existing regression: bodyweight squat jumps 3 × 3. The sample camp date comes from the supplied reference; week context and states are illustrative. Demonstration imagery is generated for visual review, not production exercise instruction.

These concepts establish the primary screens, not final variants for every plan type, state or permission. Editing affordances must remain permission- and date-dependent. No training calculation, severity classification, completion state or video availability may be inferred from the mockup. Production implementation waits for review.
