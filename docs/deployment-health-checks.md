# Deployment health checks

## The failure mode this guards against

When the runtime app fails to build at import time, `api/app.py` does not crash —
it serves a minimal **startup-failure app** whose `/health` returns
`503 Service Unavailable` (`_build_startup_failure_app`). That is the correct
behaviour **only if the deploy platform treats a failing `/health` as an unhealthy
deploy**. If the platform never probes `/health`, a "successfully deployed"
service can in fact be dead — every request returns 503 — and nobody is paged.

## Required platform configuration

### Render (backend)

Set the service **Health Check Path** to `/health`.

- A healthy runtime returns `200` with a JSON body including the mode label.
- The startup-failure app returns `503` from `/health`, so Render marks the
  deploy unhealthy and does not route traffic to a dead instance.

If/when the backend is managed via a Render Blueprint (`render.yaml`), encode it:

```yaml
services:
  - type: web
    name: unlxck-api
    healthCheckPath: /health
```

> Not committed today because the service is dashboard-managed. Configure the
> Health Check Path in the Render dashboard until a Blueprint is adopted.

### Vercel (frontend)

The frontend is static/SSR on Vercel and has no equivalent process-health probe;
it depends on the backend `/health` gate above.

## Alerting

- Alert on **any `503` from `/health`** (synthetic uptime check or log-based
  alert). A sustained 503 means the startup-failure app is being served.
- Alert on the startup log line `[admin] startup_admin_count=0`.
- Consider alerting on Stage 2 failure rate, generation queue depth, and
  generation duration (see `docs/generation-reliability-checklist.md`).

## Decision: fail soft vs. fail hard

The current design **fails soft** (serve 503) rather than crash-looping. This is
fine when the health check is wired and alerting fires. If the deploy platform is
configured to restart cleanly on process exit and you would rather a bad build
never accept connections at all, switch `_build_startup_failure_app` to re-raise
in production. Until then, the health check + alert above are mandatory.
