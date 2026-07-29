# UNLXCK System Regression Checklist

Use this checklist for beta-readiness verification against the production frontend, Render API, Supabase project, and current `Main` deployment. Do not paste secrets into the checklist or test logs.

## Environment

### Render Environment Variables

- [ ] `UNLXCK_ENV=production`
- [ ] `UNLXCK_ADMIN_EMAILS` is set to the intended comma-separated admin email list.
- [ ] `APP_PLAN_GENERATE_DAILY_LIMIT_PER_USER` is set to the intended beta cap.
- [ ] `APP_GENERATION_JOB_STALE_AFTER_SECONDS` is set to the intended stale-job timeout.
- [ ] Supabase service credentials are configured in Render only.
- [ ] OpenAI credentials are configured in Render only.

### Vercel Environment Variables

- [ ] `NEXT_PUBLIC_SITE_URL` is set to the production frontend URL for **every**
      environment (Production, Preview, Development). Unset on Preview means auth
      emails link to a `*.vercel.app` deployment host — see
      [`docs/supabase-auth-emails.md`](../supabase-auth-emails.md).
- [ ] `NEXT_PUBLIC_API_BASE_URL` points to the production Render API.
- [ ] `NEXT_PUBLIC_SUPABASE_URL` points to the production Supabase project.
- [ ] `NEXT_PUBLIC_SUPABASE_ANON_KEY` is present and scoped as anon/public.

### Supabase Auth URLs

- [ ] Site URL is the production frontend URL.
- [ ] Redirect URLs include the production `/login` route.
- [ ] Redirect URLs include the production `/reset-password` route.
- [ ] Email confirmation links open the production app, not localhost or a preview domain.
- [ ] Password reset links open the production app, not localhost or a preview domain.
- [ ] Branded email templates from `supabase/templates/` are pasted into
      Authentication -> Emails -> Templates.
- [ ] Re-opening an already-used reset link shows the UNLXCK "expired or already
      used" state, not a blank form.

### Supabase DB Migrations

- [ ] Profile role escalation trigger is applied.
- [ ] Plans direct insert/update/delete RLS policies are absent.
- [ ] Athlete intake direct insert/update/delete RLS policies are absent.
- [ ] Generation job direct insert/update/delete RLS policies are absent.
- [ ] Profile username columns and constraints are applied.
- [ ] Username bypass trigger is applied.

## Manual Flows

### Auth

- [ ] Sign up as a new user.
- [ ] Confirm email link opens the production app.
- [ ] Log in with email/password.
- [ ] Log out, then log in again.
- [ ] Forgot password sends a reset email.
- [ ] Valid reset link allows password update.
- [ ] Reused or expired reset link shows a clear expired/invalid message.
- [ ] Expired reset screen includes a `/forgot-password` action.

### Admin Access

- [ ] Email listed in `UNLXCK_ADMIN_EMAILS` logs in and is promoted to admin.
- [ ] Admin user can open `/admin`.
- [ ] Normal athlete cannot access admin views.
- [ ] Removing an email from `UNLXCK_ADMIN_EMAILS` does not unexpectedly mutate existing production data without an explicit admin process.

### Admin Reliability

- [ ] Admin dashboard (`/admin`) loads athlete and plan lists without raw error output.
- [ ] Admin athlete detail (`/admin/athletes/<id>`) loads the profile and nutrition workspace.
- [ ] During a temporary backend blip (502/503/504 or network error) the admin pages show a clean error banner instead of a stack trace.
- [ ] The error banner exposes a `Try again` button that re-runs the failed load when clicked.
- [ ] After the backend recovers, `Try again` restores the dashboard / athlete profile contents.
- [ ] Admin-triggered generation from latest intake still completes successfully after a load retry.
- [ ] An unauthorized athlete attempting to hit `/admin` or `/admin/athletes/<id>` is rejected with a 401/403 and is **not** silently retried.

### Settings / Account

- [ ] Settings page loads.
- [ ] Change username succeeds with a valid available username.
- [ ] Duplicate username is rejected.
- [ ] Invalid username is rejected.
- [ ] Username rate limit blocks after the configured 30-day change window is exhausted.
- [ ] Change password succeeds with the correct current password.
- [ ] Wrong current password is rejected.

### Plan Generation

- [ ] Quick Build can save intake and start generation.
- [ ] Advanced Intake can save intake and start generation.
- [ ] Advanced Intake Review step does not show the "Generate Stage 1 only" button for an athlete account.
- [ ] Advanced Intake Review step still shows the "Generate Stage 1 only" button for an admin account.
- [ ] Generate plan succeeds and opens a completed plan.
- [ ] Daily generation limit blocks after the configured cap.
- [ ] Same request retry/idempotency does not create duplicate jobs.
- [ ] Admin-triggered generation from latest intake works.
- [ ] Admin-triggered generation behavior is not counted against the athlete self-serve daily cap.

### Failed / Stale Generation Recovery

- [ ] Force or identify a failed generation and verify `Try again` appears.
- [ ] Retry failed generation and confirm a new job starts.
- [ ] Original failed job remains failed after retry.
- [ ] Force or identify a stale running job and verify polling marks it failed.
- [ ] Retry stale-failed job and confirm a new job starts.
- [ ] Non-owner cannot view or retry another athlete's failed/stale job.
- [ ] Admin can view athlete generation jobs in the Generation diagnostics section.
- [ ] Failed job shows error details and Retry action in Generation diagnostics.
- [ ] Stale running job shows a stale warning in Generation diagnostics.
- [ ] Completed job includes a plan link/open action in Generation diagnostics.
- [ ] Payload summary is useful and does not expose sensitive secrets.

### Plans / Refinement

- [ ] Plan dashboard loads with latest plan card.
- [ ] Completed plan opens correctly.
- [ ] Older plans remain accessible from the archive.
- [ ] Rename plan still works.
- [ ] Delete plan still works.
- [ ] Saved plan opens in-app without requiring a download/export action.
- [ ] Quick Build plan shows the refinement banner.
- [ ] Non-Quick-Build plan does not show the Quick Build refinement banner.
- [ ] Refinement CTA opens Advanced Intake.

### Mobile

- [ ] Login/signup forms fit on iPhone-width viewport.
- [ ] Quick Build chips wrap cleanly.
- [ ] Quick Build submit actions are easy to tap.
- [ ] Advanced Intake mobile step controls remain usable.
- [ ] Generate/loading screen fits without overlapping primary controls.
- [ ] Plans dashboard cards stack cleanly.
- [ ] Global generation status does not block bottom navigation actions.
