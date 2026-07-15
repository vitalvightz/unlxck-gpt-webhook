# Hetzner backend deployment

This deployment runs the FastAPI API, persistent generation worker, and Caddy on one Hetzner CX23.

## Architecture

- `api`: serves normal application traffic and only creates generation jobs.
- `worker`: polls Supabase and processes one generation job at a time.
- `caddy`: exposes HTTPS and proxies requests to the API.

The API must not run plan generation in-process. spaCy is disabled only in the API container and remains enabled in the worker.

## Required files on the server

Create `.env.production` in the repository root. Do not commit it.

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
```

Retain the generation timeout, rate-limit, feedback, and Stage 2 variables from `.env.example` that are used in production.

Protect the file:

```bash
chmod 600 .env.production
```

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

```bash
git clone https://github.com/vitalvightz/unlxck-gpt-webhook.git
cd unlxck-gpt-webhook
git checkout codex/hetzner-migration
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

## Updates

```bash
git pull --ff-only
sudo docker compose build
sudo docker compose up -d
sudo docker compose ps
```

## Rollback

1. Stop the Hetzner worker first:

```bash
sudo docker compose stop worker
```

2. Restore the previous API DNS or frontend API base URL.
3. Re-enable the Render services.
4. Preserve Hetzner logs for diagnosis.

Do not run Render and Hetzner workers against the production queue simultaneously unless multi-worker job claiming has been explicitly tested.
