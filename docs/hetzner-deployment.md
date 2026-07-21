# Hetzner backend deployment

This is the live production backend. It runs the FastAPI API, persistent generation worker, and Caddy on one Hetzner CX23 from `/opt/unlxck` on the `Main` branch.

## Architecture

- `api`: serves application traffic and queues generation jobs.
- `worker`: polls Supabase and processes one generation job at a time.
- `caddy`: exposes HTTPS and proxies requests to the API.

The API never generates plans in-process. spaCy is disabled only in the API container and remains enabled in the worker. Caddy certificate state is stored in named Docker volumes and is not removed during deployments.

## Production environment file

The server keeps its secrets in `/opt/unlxck/.env.production`. The file is ignored by Git and Docker build context, and the deployment script refuses to proceed if Git tracks it.

Required values include:

```env
API_DOMAIN=unlxck-staging.167.233.47.121.sslip.io
SUPABASE_URL=
SUPABASE_SERVICE_ROLE_KEY=
SUPABASE_ANON_KEY=
OPENAI_API_KEY=
UNLXCK_ADMIN_EMAILS=
APP_CORS_ORIGINS=https://unlxck-gpt-webhook.vercel.app
APP_ENV=production
UNLXCK_ENV=production
SENTRY_DSN=
```

Retain the production generation timeout, rate-limit, feedback, and Stage 2 values. Protect the file:

```bash
chmod 600 /opt/unlxck/.env.production
```

Never print this file in GitHub Actions or commit it.

## Existing server baseline

The current server uses Ubuntu 24.04, Docker Engine with the Compose plugin, a 2 GB swap file, and inbound TCP 22/80/443 plus UDP 443. Do not weaken the Hetzner firewall for deployment automation.

## One-time deploy user setup

Generate a dedicated key on a trusted workstation. Do not add a passphrase because GitHub Actions cannot unlock an interactive key:

```bash
ssh-keygen -t ed25519 -f ./unlxck_hetzner_deploy -C "github-actions-unlxck"
```

Keep `unlxck_hetzner_deploy` private. On the server, create the dedicated account and install only its public key:

```bash
adduser --disabled-password --gecos "" unlxck-deploy
install -d -m 700 -o unlxck-deploy -g unlxck-deploy /home/unlxck-deploy/.ssh
install -m 600 -o unlxck-deploy -g unlxck-deploy /dev/null /home/unlxck-deploy/.ssh/authorized_keys
printf '%s\n' 'PASTE_DEPLOY_PUBLIC_KEY_HERE' >> /home/unlxck-deploy/.ssh/authorized_keys
usermod -aG docker unlxck-deploy
chown -R unlxck-deploy:unlxck-deploy /opt/unlxck
chmod 600 /opt/unlxck/.env.production
```

Membership in the Docker group is effectively root-equivalent. The dedicated account isolates the deployment credential and audit trail, but it is not a security boundary against a malicious commit on `Main`. Do not grant the account general `sudo` access.

Open a fresh session so group membership applies, then verify:

```bash
su - unlxck-deploy
git -C /opt/unlxck status --short
cd /opt/unlxck
docker compose config --quiet
docker compose ps
```

Until the automation commit reaches the server, Git may show only `?? .env.production`; that is expected. Do not continue if any other server-side change appears. After the first deployment, `.env.production` is ignored and status should be clean.

## Verify the SSH host key

On the Hetzner server, obtain the authoritative Ed25519 fingerprint:

```bash
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

On the trusted workstation, scan the public key and compare its fingerprint with the server output:

```bash
ssh-keyscan -p 22 -t ed25519 167.233.47.121 > hetzner_known_hosts
ssh-keygen -lf hetzner_known_hosts
```

Only after the fingerprints match should the complete `hetzner_known_hosts` line be stored in GitHub. This prevents the workflow from disabling host-key checking or trusting an unverified scan.

## GitHub configuration

Create a `production` GitHub environment and add these repository secrets:

| Secret | Value |
| --- | --- |
| `HETZNER_HOST` | `167.233.47.121` |
| `HETZNER_USER` | `unlxck-deploy` |
| `HETZNER_SSH_PORT` | `22` |
| `HETZNER_SSH_PRIVATE_KEY` | Complete contents of `unlxck_hetzner_deploy` |
| `HETZNER_SSH_KNOWN_HOSTS` | Verified line from `hetzner_known_hosts` |

Application secrets remain only in `/opt/unlxck/.env.production`; do not copy them into the deployment workflow.

Before merging the automation PR, confirm that no plan is actively generating. The currently running pre-automation worker still has the old 35-second shutdown grace; the first deployment installs the new ten-minute drain setting for every later deployment.

## Automatic deployment

`.github/workflows/deploy-hetzner.yml` runs on every push to `Main` and through **Actions → Deploy Hetzner → Run workflow**.

The workflow:

1. Checks out and records the exact commit to deploy.
2. Runs Ruff, the generation/runtime and deployment tests, bank validation, ShellCheck, Compose validation, and a production Docker build.
3. Opens a strictly verified SSH connection and takes a server-side deployment lock.
4. Verifies `.env.production`, fetches `Main`, and resets the checkout to the exact tested commit.
5. Builds both new images before replacing anything.
6. Recreates the API and waits for container health.
7. Recreates Caddy only when `Caddyfile` or `compose.yaml` changed.
8. Replaces the worker with one consumer only. SIGTERM stops new claims while the current job receives up to ten minutes to finish.
9. Requires the public `/health` endpoint to return HTTP 200 and verifies worker startup.
10. Prunes dangling images only after success and writes the deployment result to the Actions summary.

GitHub concurrency prevents two workflow deployments from running together. A second server-side `flock` also blocks overlap with manual deployment commands.

## Failure and automatic rollback

The script records the currently deployed commit before changing the checkout. A build, startup, container-health, worker-startup, or public-health failure restores that commit, rebuilds the previous images, recreates the affected services, and verifies `/health` again. The Actions job remains failed even when rollback succeeds.

The script never runs `docker compose down`, so Caddy certificate volumes and other named volumes remain intact. It also never starts a second worker alongside the first.

## Manual validation

```bash
cd /opt/unlxck
docker compose ps
curl -fsS https://unlxck-staging.167.233.47.121.sslip.io/health
docker stats --no-stream
docker compose logs --tail=100 api worker caddy
```

## Manual rollback

Use the previous commit shown in the GitHub deployment summary:

```bash
cd /opt/unlxck
git fetch origin Main
docker compose stop worker
git reset --hard PREVIOUS_COMMIT_SHA
docker compose config --quiet
docker compose build api worker
docker compose up -d --no-deps api
docker compose up -d --no-deps worker
docker compose up -d --no-deps --force-recreate caddy
docker compose ps
curl -fsS https://unlxck-staging.167.233.47.121.sslip.io/health
```

Do not re-enable the suspended Render worker. Only one production queue worker may run.

## Disable automatic deployment

Disable **Deploy Hetzner** from the repository's Actions page before server maintenance or deployment-key rotation. Existing containers keep running. Re-enable the workflow only after verifying the deploy user, Docker access, known-host entry, and repository secrets.

To revoke automation completely, disable the workflow, remove the five GitHub secrets, and delete the deployment public key line from `/home/unlxck-deploy/.ssh/authorized_keys`.

## Emergency Render fallback

Render is not part of the live system. Only resume its suspended web and worker services as a deliberate full rollback:

1. Stop the Hetzner worker.
2. Resume the Render worker and web service.
3. Change Vercel `NEXT_PUBLIC_API_BASE_URL` to the Render API URL.
4. Redeploy Vercel and verify the public flow.

Never run the Render and Hetzner workers against the production queue at the same time.
