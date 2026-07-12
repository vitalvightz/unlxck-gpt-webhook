# Beta feedback operations

The beta feedback API uses the Supabase service role only. Do not grant browser access to `beta_feedback`, `beta_feedback_rate_limits`, or the private `feedback-screenshots` bucket.

## Environment

Configure these on the Render API and the Render Cron Job:

```env
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
FEEDBACK_REPORT_LIMIT_PER_HOUR=5
FEEDBACK_SCREENSHOT_LIMIT_PER_HOUR=2
FEEDBACK_SCREENSHOT_RETENTION_DAYS=90
FEEDBACK_NOTIFICATION_EMAIL=unlxckedmind@gmail.com
FEEDBACK_FROM_EMAIL=Unlxck Feedback <feedback@your-verified-domain.com>
FEEDBACK_ADMIN_URL=https://your-production-frontend-domain/admin
RESEND_API_KEY=...
```

`0` disables the report and screenshot-upload rate limits. Screenshot retention must remain a positive number; `0` falls back to 90 days. Invalid or negative values fall back to the defaults. Changing limits does not require a database migration.

Every saved feedback response is available to authenticated admins at `/admin` through the service-role backend; this feed is the authoritative delivery channel. The same save attempts one best-effort background Resend notification to `FEEDBACK_NOTIFICATION_EMAIL`, which defaults to `unlxckedmind@gmail.com`. Configure a verified sender in `FEEDBACK_FROM_EMAIL`. Email is skipped when the Resend key or sender is absent, and provider failures are logged without retry; neither case rolls back stored feedback.

The admin feed shows bounded server-derived submission context: page path, plan/check-in IDs, device/language, selected readiness values, and up to three open-injury summaries without injury descriptions. This context opens automatically when no written comment was supplied. The app never captures a page screenshot automatically; image attachments remain explicit user uploads with the existing privacy warning and sanitisation controls.

Athletes and admins may submit contextual feedback only for plans and Today recommendations owned by their own profile. Coaches and gym owners remain limited to global feedback.

Notification emails contain only priority, surface, category, response, reason, screenshot presence, authenticated role, and feedback ID. Comments, contact details, health snapshots, technical context, screenshots, and screenshot paths remain inside the authenticated admin/storage tools.

## Review recent feedback

Run this read-only query in the Supabase SQL editor. It deliberately exposes screenshot paths only to the operator running the query; paths are not public URLs.

```sql
select
  f.created_at,
  f.updated_at,
  f.priority,
  f.submitted_by_profile_id as submitter_profile_id,
  p.email as submitter_email,
  f.surface,
  f.category,
  f.response,
  f.reason,
  f.comment,
  f.contact_allowed,
  f.plan_id,
  f.today_checkin_id,
  f.camp_phase,
  f.app_version,
  f.screenshot_path,
  f.screenshot_expires_at,
  f.screenshot_deleted_at
from public.beta_feedback as f
join public.profiles as p on p.id = f.submitted_by_profile_id
order by (f.priority = 'safety') desc, f.created_at desc
limit 200;
```

Safety-only review:

```sql
select
  f.created_at,
  f.submitted_by_profile_id as submitter_profile_id,
  p.email as submitter_email,
  f.surface,
  f.category,
  f.response,
  f.reason,
  f.comment,
  f.plan_id,
  f.today_checkin_id,
  f.camp_phase,
  f.app_version,
  f.screenshot_path,
  f.screenshot_expires_at
from public.beta_feedback as f
join public.profiles as p on p.id = f.submitted_by_profile_id
where f.priority = 'safety'
order by f.created_at desc;
```

Authenticated admins can select **View private screenshot** in `/admin`. The backend resolves the stored path, rejects missing or expired objects, and returns a 60-second signed URL; the browser never supplies a path. Operators may also open the private `feedback-screenshots` bucket in the authenticated Supabase dashboard and locate the exact stored path. Never make the bucket public or put signed URLs in logs or tickets.

## Screenshot retention

Create a Render Cron Job from this repository with:

- Schedule: `30 3 * * *` (03:30 UTC daily)
- Runtime: the same Python 3.11.14 runtime and production dependencies as the API
- Command: `python -m api.feedback_retention`
- Environment: the Supabase service credentials and feedback retention setting above

Manual run:

```powershell
python -m api.feedback_retention
```

The command reads expired references in bounded batches, continuing until the backlog is empty, a deletion fails, or the default 1,000-object per-run safety cap is reached. Override the cap with `--max-per-run` during a managed backlog drain. It deletes each object through the Storage API and clears the database path only after Storage confirms the delete request. Failed rows remain unchanged and are retried by the next run. A non-zero exit means at least one object should be retried.

Verify the cron after deployment:

```sql
select count(*) as overdue_screenshots
from public.beta_feedback
where screenshot_path is not null
  and screenshot_deleted_at is null
  and screenshot_expires_at <= now();
```

Supabase Storage objects must be deleted through the Storage API. Direct SQL deletion from `storage.objects` can orphan the underlying file.

## Account deletion

The profile-delete guard rejects deletion while feedback screenshot paths remain. Before the existing profile/auth deletion operation, run:

```powershell
python tools/purge_feedback_screenshots.py --profile-id <profile-uuid> --confirm
```

Confirm `failed=0`, then run the existing account deletion. Feedback and rate-limit rows cascade from `submitted_by_profile_id`. Feedback rows otherwise remain until account deletion because the project has no broader feedback-row retention period. Safety rows use the same 90-day screenshot expiry; retaining them longer requires a documented policy change.

## Logging boundaries

Feedback route logs may contain only the request/feedback ID, server-derived surface/category/priority, screenshot presence, stable error code, and exception class. Cleanup logs contain feedback ID and operation only. Never add comments, health snapshots, raw headers, paths, filenames, multipart bodies, or image contents to logs, Sentry tags, or breadcrumbs.
