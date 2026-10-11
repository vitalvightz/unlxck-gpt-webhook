# Private exercise demonstrations — issue #2833, PR A

Based on merged PR #2834 (`ed333b5f`), extending its manual exercise fields.
Athletes can attach an optional verified YouTube clip or sanitized short upload,
replace/remove it, and reopen it from a saved custom plan. Nothing is submitted or
published. Admin moderation, attribution consent, reporting and discovery are PR B.
The catalogue, frozen banks, generator and clinical prescription system are unchanged.

## Deployment gate

1. Apply `20261011203627_private_exercise_media.sql` and
   `20261011203631_private_media_retry_cleanup.sql` before deploying the API.
   Both were applied to the linked `unlxckpdf` project on 2026-10-11 at the user's request.
   The existing runtime schema gate requires its tables, functions, indexes and RLS.
2. YouTube uses the existing server-only `YOUTUBE_DATA_API_KEY`. No new client key.
3. Deploy `tools/private_media_worker.py` on a **dedicated Linux Docker host**.
   Build `media_processor/Dockerfile`, run the real-media smoke gate, and configure
   `PRIVATE_VIDEO_PROCESSOR_IMAGE` with the resulting immutable image SHA256 or
   repository digest. Mutable tags are rejected. The host needs Docker, the backend
   Python dependencies and server-only Supabase credentials; containers receive none.
4. Keep `PRIVATE_VIDEO_UPLOADS_ENABLED` unset until processing CI and a staging upload
   succeed. Then set it to `true` on the API. The worker must continuously succeed at
   offline scanner/decoder health, retention cleanup and processing; a heartbeat older
   than two minutes closes new upload permissions. Restart failures clear the heartbeat.
5. Refresh ClamAV signatures and rebuild/review the pinned image at least daily.
   A daily signature file older than 48 hours fails health and processing. Patch the
   decoder/scanner and base image regularly. The worker must have no privileged Docker
   options beyond those in its fixed runner command. Run separate from application,
   database and generation infrastructure, with restricted host credentials/network.

```sh
docker build --pull -t unlxck-private-media ./media_processor
python tools/test_private_media_processor.py --image "$(docker image inspect unlxck-private-media --format '{{.Id}}')"
# Set PRIVATE_VIDEO_PROCESSOR_IMAGE to this immutable digest in worker configuration.
python tools/private_media_worker.py
```

Do not run processing inside the web API, Vercel request handlers or generation worker.
The authorized migrations created private storage buckets and database safeguards.
No environment values or upload/publication switches were changed. Upload controls show unavailable until the server gate is healthy.

## Security and retention

- A server-generated asset UUID reserves one owner/path for **five minutes**. Upload
  uses the athlete's existing authenticated Supabase client and an INSERT-only RLS
  lease. There is no reusable signed upload URL, overwrite permission or client read
  access to raw objects. Storage caps files at **20 MiB** and accepted transport MIME
  types (MP4/MOV/WebM). Declared size/MIME alone never verify a video.
- Durable advisory locks enforce 30 video attempts/hour, 6 uploads/hour, 20 uploads/day,
  at most 50 active assets and a 1,000 MiB reserved-byte quota per owner. YouTube revisions
  are capped at 200 per owner. Retries and invalid attempts consume the rate budget.
- Offline processing scans raw bytes with ClamAV, checks magic, container, codecs,
  streams, dimensions and actual duration, fully decodes with FFmpeg and rejects source
  or output longer than 30 seconds. Input video codecs: H.264/HEVC/VP8/VP9/AV1; limited
  audio codecs may be present. Extra streams/attachments are rejected. Output is H.264
  MP4, no audio or metadata, with a maximum 1920-pixel side, scanned again and hashed.
- Docker runs without network, as UID 10001, with a read-only root/input, no capabilities,
  no privilege escalation and CPU/memory/process/file/output limits. Output lives in a
  bounded container tmpfs, never a writable host mount. Host output reads are bounded;
  timeout/error forcibly removes the container. No parser runs on the API or worker host.
- The worker atomically records verification and a distinct immutable media revision.
  APIs check the authenticated owner and verified state before attachment or preview.
  Database checks also prevent cross-owner JSON references and serialize saves with
  cleanup. Only processed renditions receive a **60-second** read URL; these are bearer
  URLs once issued, so copying one permits access until expiry. Raw bytes never do.
- Finalisation is idempotent for the same rendition proof and rejects mismatched
  revisions. Proof persists before an immutable upload; stale processing leases can
  be reclaimed after ten minutes. Network errors preserve raw and ready objects.
  Retries reuse the hashed rendition. Raw cleanup runs only after confirmed verification,
  with a sweep reclaiming verified raw leftovers after one hour.
- Raw sources are removed after confirmed processing. Stalled/abandoned/rejected
  assets are removed after 24 hours. Unreferenced verified renditions expire after seven
  days; saved-plan references retain them. Orphan objects from account deletion become
  eligible after one hour. Each worker sweep is bounded to 100 candidates; alert on backlog
  and heartbeat loss. Cleanup retries until storage removals succeed. Quota attempt records
  expire after 24 hours on the owner's next attempt. Unused YouTube preview records
  expire after 24 hours, bounded to 200 per sweep; saved-plan references retain them.
  Cleanup runs before quota checks, even without an upload worker, and during worker
  sweeps. Row locks serialize cleanup with plan saves. The 200-record limit remains.
- YouTube input accepts HTTPS provider URLs only, reusing the existing ID parser and
  Data API availability, embedding and classification checks. End time must fall within
  the reported duration; the selected segment is 1–30 seconds. No arbitrary URL fetching
  or client HTML/iframe markup. Replacing any demo creates a new media revision UUID.

## UI and verification

Uses `InjuryDetailSheet`, the custom builder's fields, global `cta`, `secondary-button`
and `ghost-button`, plus `ExerciseDemo` and its established `ex-demo-*` controls.
Only spacing, grid layout and media sizing are new CSS. Clip fields collapse after
verification; alternate source selection sits in a disclosure. Athlete UI contains no
storage paths, processing internals or validation metadata. Desktop sessions use
Today's two-column rhythm; the existing sheet places settings beside the preview
on desktop while retaining the compact mobile stack. Sessions always appear
Monday through Sunday, with unassigned sessions last. Same-day session order and
exercise order are preserved. API reads also order older saved plans without an
identity rewrite; saves persist calendar order.

Relevant checks:

```sh
python -m pytest tests/test_private_media.py tests/test_custom_plans.py tests/test_exercise_media.py tests/test_api_types_generated.py -q
python -m pytest tests/test_metadata_integrity_audit.py tests/test_canonical_metadata.py tests/test_supabase_runtime_schema_checker.py -q
npm install --prefix /tmp/media-sql @electric-sql/pglite@0.5.8
node tools/test_private_media_migration.mjs /tmp/media-sql
# In web: npm run typecheck; npm run lint; npm run test:unit; npm run build
# In web: npx playwright test e2e/custom-plans.spec.ts --workers=1
```

PostgreSQL checks run against an isolated WASM database, never the linked project.
Browser tests at 320/390/1280px exercise mocked YouTube API playback settings, replay,
segment looping, validation, saved-plan reopening and removal. These checks do not
claim live YouTube playback, hosted decoding, actual Safari or physical iPhone testing.
The separate Linux processing CI runs real MP4/WebM, >30-second, disguised HTML and
EICAR fixtures. Staging Storage, signed URL expiry/range playback and real Safari must
still be verified before the operator opens uploads or proceeds to public PR B.
