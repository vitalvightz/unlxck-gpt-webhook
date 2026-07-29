# Supabase auth emails and redirect URLs

Password reset, email sign-in links, and signup confirmations are all sent by
Supabase Auth. Two things decide whether an athlete lands in UNLXCK or on a
stranger's error page: the **origin baked into the link** and the **Supabase URL
configuration**. Both must be right — fixing one without the other still breaks.

## Why reset links used to open a Vercel page

The frontend builds the `redirect_to` for every auth email from
`web/lib/site-url.ts`. It used to fall back to `window.location.origin` whenever
`NEXT_PUBLIC_SITE_URL` was unset, so a reset requested from a
`unlxck-<hash>-<team>.vercel.app` deployment host emailed that host back to the
athlete. Those hostnames are per-deployment and sit behind Vercel's deployment
protection, so the athlete opened the link and got Vercel's own branded gate
instead of UNLXCK.

`buildAuthRedirectUrl()` now resolves the origin in this order:

1. `NEXT_PUBLIC_SITE_URL`
2. `NEXT_PUBLIC_VERCEL_PROJECT_PRODUCTION_URL` — Vercel's stable production
   domain, never a preview host
3. `window.location.origin` — local development only

If none resolves it returns `undefined`, which makes supabase-js fall back to
the project's Site URL rather than emailing a malformed link.

There is a second, independent cause with the same symptom: **Supabase silently
rewrites any `redirect_to` that is not on the Redirect URLs allow list to the
project Site URL.** If Site URL is still a `*.vercel.app` value, every link lands
there no matter what the frontend sends. Check both.

## Required configuration

### Vercel project environment variables

| Variable | Value |
| --- | --- |
| `NEXT_PUBLIC_SITE_URL` | The production frontend origin, no trailing slash |

Set it for **Production, Preview, and Development**. Leaving it unset on Preview
is what puts a deployment host into a link that was requested from a preview
build.

### Supabase dashboard — Authentication → URL Configuration

- **Site URL**: the production frontend origin.
- **Redirect URLs** must include every path the app passes to `redirectTo`:
  - `<origin>/login` — magic link and signup confirmation
  - `<origin>/reset-password` — password recovery
  - `http://localhost:3000/**` for local development

Adding a new `buildAuthRedirectUrl()` path in the frontend without adding it here
reintroduces the bug, because the unlisted path falls back to Site URL.

## Applying the branded email templates

`supabase/templates/` holds the UNLXCK-branded HTML. They replace Supabase's
unstyled defaults.

| File | Dashboard template |
| --- | --- |
| `confirm-signup.html` | Confirm signup |
| `magic-link.html` | Magic Link |
| `recovery.html` | Reset Password |
| `email-change.html` | Change Email Address |
| `invite.html` | Invite user |

To apply: **Authentication → Emails → Templates**, pick the template, paste the
file contents into the message body, and save. Re-paste after editing a file
here — the dashboard holds the live copy, so the repo is the source of truth
only if it is kept in sync.

Suggested subject lines:

| Template | Subject |
| --- | --- |
| Confirm signup | Confirm your UNLXCK account |
| Magic Link | Your UNLXCK sign-in link |
| Reset Password | Reset your UNLXCK password |
| Change Email Address | Confirm your new UNLXCK email |
| Invite user | You have been invited to UNLXCK |

### Template constraints

- **No remote images.** The wordmark is letter-spaced text so it renders even
  when a client blocks remote content. Do not swap in a hosted logo.
- **Inline styles only.** Gmail strips `<style>` blocks in several clients.
- **Table layout.** `flex` and `grid` are unreliable across email clients.
- Every template links `{{ .ConfirmationURL }}` twice — once as the button and
  once as visible copy-paste text — so a client that mangles the button still
  leaves a usable link.

## Verifying a change

1. Request a reset from production and confirm the link host is the production
   domain, not `*.vercel.app`.
2. Open the link and confirm the UNLXCK reset form renders.
3. Open the same link a second time. It must show "This link has expired or has
   already been used" on the UNLXCK page rather than a blank form.
4. Repeat 1–3 for the email sign-in link, which lands on `/login`.
