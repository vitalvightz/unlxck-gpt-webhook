# Hetzner backend deployment

This is the live production backend. It runs the FastAPI API, persistent generation worker, and Caddy on one Hetzner CX23 from `/opt/unlxck` on the `Main` branch.

## Architecture

- `api`: serves normal application traffic and only creates generation jobs.
- `worker`: polls Supabase and processes one generation job at a time.
- `caddy`: exposes HTTPS and proxies requests to the API.

The API must not run plan generation in-process. spaCy is disabled only in the API container and remains enabled in the worker.

## Required files on the server

Production uses `/opt/unlxck/.env.production`. Create it during first setup, protect it with `chmod 600`, and never commit it.

Required values include:

```env
API_DOMAIN=api.example.com
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=
OPENAI_API_KEY=
UNLXCK_ADMIN_EMAILS=
APP_CORS_ORIGINS=https://your-frontend.example.com
APP_ENV=production
UNLXCK_ENV=production
SENTRY_DSN=

# Web Push notifications. Both keys must come from the same VAPID key pair.
UNLXCK_VAPID_PRIVATE_KEY=
UNLXCK_VAPID_PUBLIC_KEY=
UNLXCK_VAPID_SUBJECT=mailto:ops@example.com
UNLXCK_PUSH_SITE_URL=https://your-frontend.example.com
UNLXCK_MORNING_PUSH_ENABLED=1
UNLXCK_MORNING_PUSH_LOCAL_HOUR=7
UNLXCK_MORNING_PUSH_CUTOFF_LOCAL_HOUR=11
UNLXCK_MORNING_PUSH_SWEEP_INTERVAL_SECONDS=600
```

Retain the generation timeout, rate-limit, feedback, and Stage 2 variables from `.env.example` that are used in production.

Protect the file:

```bash
chmod 600 .env.production
```

## Activate Web Push notifications

The Web Push implementation is already part of the API, worker, PWA service worker, and Supabase schema. It remains silently disabled until both VAPID keys are present in `.env.production`.

Generate one VAPID key pair on a trusted machine or directly on the server:

```bash
npx web-push generate-vapid-keys
```

Copy the matching public and private keys into `.env.production`:

```env
UNLXCK_VAPID_PRIVATE_KEY=<private-key>
UNLXCK_VAPID_PUBLIC_KEY=<public-key>
UNLXCK_VAPID_SUBJECT=mailto:ops@example.com
UNLXCK_PUSH_SITE_URL=https://your-production-pwa-origin.example.com
```

Rules:

- Keep the private key server-only. Never commit it, expose it through a `NEXT_PUBLIC_*` variable, or place it in the frontend deployment.
- Keep the same key pair across deployments. Replacing the pair invalidates existing browser subscriptions and requires users to opt in again.
- Set `UNLXCK_PUSH_SITE_URL` to the canonical origin from which users install the PWA.
- The current deployment workflow preserves `.env.production`; with the present architecture the VAPID keys belong on Hetzner, not in the repository.

Recreate the API and worker containers so they read the new environment values:

```bash
cd /opt/unlxck
docker compose up -d --force-recreate api worker
docker compose ps
```

Verify the backend sees a complete key pair without printing either key:

```bash
docker compose exec api python -c "from api.services.push_notifications import push_notifications_configured; assert push_notifications_configured(); print('web push configured')"
docker compose exec worker python -c "from api.services.push_notifications import push_notifications_configured; assert push_notifications_configured(); print('web push configured')"
```

Then validate the full flow:

1. Sign in to the production PWA and open **Settings → Notifications**. The control must no longer say that notifications are disabled on the server.
2. Install the PWA first on iPhone, then turn notifications on and grant browser permission.
3. Confirm a row appears in Supabase `push_subscriptions` for that device.
4. Complete a real plan-ready flow and confirm the notification opens the correct plan.
5. Confirm the morning check-in nudge arrives once during the device-local configured window and does not repeat that day.

There is currently no dedicated admin test-send endpoint, so production validation uses an opted-in device and the real plan-ready or morning flow.

## Server preparation

1. Create a Hetzner CX23 using Ubuntu 24.04 and an SSH key.
2. Allow inbound TCP 22, 80, and 443 only. Restrict SSH by source IP where practical.
3. Install Docker Engine and the Compose plugin from Docker's official Ubuntu repository.
4. Enable unattended security updates.
5. Add 2 GB swap as emergency protection; swap is not a substitute for sufficient RAM.

Example swap setup:

```bash
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## First deployment

1. Clone the repository and check out the deployment branch:

```bash
git clone https://github.com/vitalvightz/unlxck-gpt-webhook.git
cd unlxck-gpt-webhook
git checkout Main
```

2. Create and populate `.env.production` in the repository root before starting the containers (see **Required files on the server** above). The API, worker, and Caddy services all read this file, so `docker compose` fails to start without it.

3. Build and start the services:

```bash
sudo docker compose build
sudo docker compose up -d
sudo docker compose ps
sudo docker compose logs -f api worker caddy
```

Point the API domain's A record to the server IPv4 address before starting Caddy.

## Validation

```bash
curl -fsS https://$API_DOMAIN/health
sudo docker stats
sudo docker compose logs --tail=200 api worker
```

Before production cutover:

1. Test at least 15 users navigating concurrently.
2. Submit three generation jobs close together.
3. Confirm exactly one job runs while the others remain queued.
4. Confirm navigation remains responsive during generation.
5. Record API, worker, child-process, total RAM, and swap peaks.
6. Reject the cutover if an OOM kill or unexplained restart occurs.

## Automated deployment (GitHub Actions)

`.github/workflows/deploy-hetzner.yml` deploys automatically on every push to
`Main` (including merged pull requests) and can be run on demand with
**workflow_dispatch**. Concurrent runs are serialised so two deployments can
never touch `/opt/unlxck` at the same time.

### How the exact commit reaches the server

The server does **not** fetch from GitHub. Instead:

1. The runner checks out the exact `github.sha` with full history.
2. It packages that commit as a self-contained **git bundle**.
3. The bundle is streamed to the server over the existing SSH connection.
4. The server imports the commit from the local bundle and `git reset --hard`
   to it, then verifies `HEAD == github.sha`.

This means deployment does not depend on the server's git URL/credential
configuration and needs no GitHub token or deploy key on the server. If GitHub
is unreachable, the runner's checkout fails before anything on the server
changes, so a failed deploy is always fail-safe.

### Required GitHub Actions secrets

| Secret | Purpose |
| --- | --- |
| `HETZNER_HOST` | Server hostname or IP for SSH. |
| `HETZNER_USER` | SSH user (must be able to run `docker compose`). |
| `HETZNER_SSH_PRIVATE_KEY` | Private key for that user. |
| `HETZNER_KNOWN_HOSTS` | `ssh-keyscan` output pinning the server host key (strict host-key checking is enforced). |

### One-time server requirements

- `/opt/unlxck` is a git checkout of this repository on `Main`.
- `/opt/unlxck/.env.production` exists and is `chmod 600`. It is untracked, so
  `git reset --hard` never overwrites or deletes it; the workflow aborts if it
  is missing.
- The SSH user is in the `docker` group (the workflow calls `docker compose`
  without `sudo`).
- Docker Engine and the Compose plugin are installed.

### Deploy, validation, and rollback behaviour

Each run validates `docker compose config --quiet`, rebuilds and restarts
`api`, `worker`, and `caddy` with `docker compose up -d --build` (never
`docker compose down`, and volumes are preserved), then requires **both** the
public API health endpoint and a running `worker` container before declaring
success. On any failure it saves diagnostics to
`/opt/unlxck/deployment-logs/`, restores the previous commit, rebuilds, and
re-verifies the API and worker. A run that had to roll back still reports
failure.

## Manual update (fallback)

Use this only for a hands-on update from a shell on the server:

```bash
git fetch origin
git reset --hard origin/Main
sudo docker compose config --quiet
sudo docker compose up -d --build
sudo docker compose ps
curl -fsS https://$API_DOMAIN/health
```

## Rollback

### Roll back to a previous Hetzner commit

Stop the worker first so only one queue consumer can run:

```bash
cd /opt/unlxck
docker compose stop worker
git fetch origin Main
git reset --hard PREVIOUS_COMMIT_SHA
docker compose config --quiet
docker compose up -d --build
docker compose ps
curl -fsS https://$API_DOMAIN/health
```

Preserve the failed deployment logs for diagnosis.

### Emergency Render fallback

Render is not part of the live system. Only resume its suspended web and worker services as a deliberate full rollback:

1. Stop the Hetzner worker.
2. Resume the Render worker and web service.
3. Change Vercel `NEXT_PUBLIC_API_BASE_URL` to the Render API URL.
4. Redeploy Vercel and verify the public flow.

Never run the Render and Hetzner workers against the production queue at the same time.
