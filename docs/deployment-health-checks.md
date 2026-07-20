# Deployment health checks

## The failure mode this guards against

When the runtime app fails during import, `api/app.py` serves a startup-failure application instead of disappearing into a crash loop. Normal endpoints return `503`, while `/health` also returns `503` so infrastructure and operators can detect that the service is not usable.

## Hetzner production checks

The production backend runs on Hetzner through Docker Compose:

- `api` has a container health check against `http://127.0.0.1:8000/health`.
- `caddy` waits for the API container to become healthy, then exposes the public HTTPS endpoint.
- `worker` is a separate persistent queue consumer and must be running alongside the API.

After every deployment, run:

```bash
cd /opt/unlxck
docker compose config --quiet
docker compose ps
curl -fsS https://$API_DOMAIN/health
docker compose logs --tail=100 api worker caddy
```

Expected state:

- `api` is `healthy`.
- `worker` and `caddy` are running.
- the public health endpoint returns HTTP `200` with `ok: true`.
- no restart loop, OOM kill, schema-readiness error, or repeated worker exception appears in the logs.

Do not treat a successful image build as a successful deployment. The container and public endpoint checks must both pass.

## Vercel frontend

The Next.js frontend runs on Vercel and has no equivalent long-running process-health probe. It depends on:

- the latest production deployment being `READY`;
- `NEXT_PUBLIC_API_BASE_URL` pointing to the current Hetzner HTTPS API URL;
- the same-origin `/api/*` rewrite reaching the healthy backend.

## Alerting

- Alert on any public `/health` `503` or connection failure.
- Alert on repeated API/container restarts.
- Monitor Sentry for startup failures, schema-readiness failures, and elevated 5xx responses.
- Monitor the generation queue for stale jobs and abnormal generation duration.

## Decision: fail soft vs. fail hard

The application fails soft by serving `503` from the startup-failure app. This preserves diagnostics while still allowing the Docker health check and public monitoring to reject the deployment.

## Legacy Render fallback

Render is not part of the live production path. Its services remain suspended only as an emergency rollback option. Never run the Render and Hetzner workers against the production queue at the same time.
