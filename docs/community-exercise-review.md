# Community exercise review — issue #2833, Stage B

Built on merged Stage A PR #2835 (189ef89f); no new uploader/player or catalogue identity system.

Athletes use the manual exercise sheet to opt into review with sharing rights and public-profile consent. Private saving never submits an exercise. The same sheet shows Private, In review, Changes requested, Rejected or Published and allows withdrawal. Rejected submissions stay usable privately.

Admins open **Exercise reviews** in the existing dashboard. Its compact queue uses AdminQueue/AdminQueueList; details use InjuryDetailSheet with two columns on desktop. Existing cta, secondary-button, ghost-button, Find a Drill results and private-video/YouTube player styling are reused. Editing details or replacing a clip creates an immutable revision and clears verification/confirmation. Publication requires server verification, an explicit final-revision confirmation and a separate approval. Changes requested, rejection and removal require reasons. Audit history records each meaningful action, actor, time and edited content.

Only approved, consenting contributions appear in the Community exercises disclosure inside Find a Drill. Attribution reads the contributor's current authenticated profile; request-supplied names/photos are rejected. Reports return to moderation. Withdrawal/removal hides discovery immediately; account deletion removes credit. Previously saved self-directed plans keep immutable content snapshots and retained media where available. A deleted account's media can become unavailable; its saved exercise text is preserved.

Community UUIDs and revision UUIDs remain separate from catalogue IDs. Imported exercises are manual self-directed snapshots, with prescription_allowed=false. No community data is added to frozen banks, verified Goals, clinical clearance, rehab prescription or fight-camp generation.

## Deployment

Apply `20261011212949_community_exercise_review.sql` after the two Stage A migrations, then deploy the API and web together. It was applied to linked project unlxckpdf on 2026-10-11; live introspection satisfies the runtime schema gate. Four new tables deny anon/authenticated direct access with RLS and revoked grants. Service-only functions also recheck current profile access, ownership/admin role, consent, exact revision and transitions. No environment values changed.

Stage A upload prerequisites remain in [private-exercise-video.md](private-exercise-video.md): dedicated isolated Docker worker, immutable processor image, fresh ClamAV signatures and healthy heartbeat. Uploads remain unavailable unless its explicit server gate is enabled. YouTube reuses the server-only Data API key and privacy-enhanced player. Approval rechecks YouTube availability/embedding/classification; uploaded videos require the verified isolated processor version and matching SHA256. Uploaded storage stays private even after publication; authorized community previews receive 60-second rendition URLs. Raw files and service-role credentials are never sent to clients.

Cleanup now retains media referenced by pending reviews, current publications and previously saved approved revisions. Unused YouTube previews still expire after Stage A's 24-hour grace period and retain the 200-record quota. Rejected/abandoned upload retention uses Stage A's existing policy. Stage A's retry-safe finalisation/cleanup is reused unchanged.

## Verification

- Critical API tests: consent, authentication/admin denial, strict actor/profile inputs, trusted media verification, short-lived previews, separate saved revision identities and legacy-client preservation.
- `node tools/test_community_exercise_migration.mjs <isolated-pglite-install>`: 12 actual PostgreSQL groups covering RLS, transitions, immutable edits, verification, attribution, reports, withdrawal, cleanup and account deletion. Existing Stage A SQL/processor CI remains in place.
- Playwright: six new consent/discovery/admin journeys at 320/390/1280px; existing custom-plan/video/clipping/calendar-order journeys preserved. Mock APIs exercise UI; database/security tests exercise real SQL separately.
- Frontend build, typecheck, lint (existing warnings), 1,865 unit tests and frozen catalogue/planner audit pass.
- No physical iPhone/Safari or production athlete upload was performed. No production contributions were seeded or approved.

## Corrective retention and report dismissal

Apply the new `20261011214749_community_review_retention_reports.sql` after Stage B; do not modify the applied migration. The corrective migration was applied to unlxckpdf on 2026-10-11. Changes requested retain the current revision's video for **30 days from the admin request**, including private correction drafts saved during that window. Editing a draft does not extend the deadline; resubmitting protects media throughout review, and a subsequent admin change request starts a fresh window. Existing requests receive 30 days from corrective rollout. After expiry, unreferenced media becomes eligible for the existing YouTube/asset cleanup worker; published and saved-plan references remain protected. Rejection or withdrawal ends correction-specific protection.

Within Reports in the existing review sheet, admins can dismiss an individual false/outdated report with a mandatory reason. Dismissal resolves only that report, records report ID/reason/admin/time in audit history, leaves publication and verification unchanged and is safe to retry. Direct client RPC calls and non-admin API calls are denied.
