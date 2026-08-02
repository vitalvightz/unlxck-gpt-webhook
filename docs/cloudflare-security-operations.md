# UNLXCK Cloudflare Security Operations

This document is the production baseline for `unlxck.com` and `api.unlxck.com`.

## Activation order

Do not enable Supabase CAPTCHA before the frontend is deployed with a valid Turnstile site key. Enabling the server-side requirement first would break signup, login, magic-link and password-recovery requests.

1. Merge and deploy the Turnstile frontend changes.
2. In Cloudflare, create a **Managed** Turnstile widget for the production frontend hostnames:
   - `unlxck.com`
   - `www.unlxck.com`
   - `app.unlxck.com`
3. Add the public site key to Vercel as `NEXT_PUBLIC_TURNSTILE_SITE_KEY` for Production.
4. Redeploy the frontend and verify that the security challenge appears on:
   - `/signup`
   - `/login`
   - `/forgot-password`
5. In Supabase Authentication > Bot and Abuse Protection, enable Cloudflare Turnstile using the widget secret key.
6. Verify password signup, password login, magic-link login and password recovery end to end.
7. Keep the database-level signup guard enabled as a second layer.

Use a separate Turnstile widget and site key for preview deployments. Do not allow every `vercel.app` hostname on the production widget.

## DNS and TLS

- Keep the apex, `www`, `app` and `api` records proxied through Cloudflare where applicable.
- SSL/TLS encryption mode: **Full (strict)**.
- Enable **Always Use HTTPS**.
- Minimum TLS version: **TLS 1.2**.
- Keep TLS 1.3 enabled.
- Keep HSTS at one year with `includeSubDomains`. Do not add `preload` until every present and future subdomain is confirmed HTTPS-only.

## WAF

Enable the Cloudflare Free Managed Ruleset. On a paid plan, also enable the Cloudflare Managed Ruleset and OWASP Core Ruleset, beginning with conservative sensitivity and reviewing Security Events before tightening it.

Recommended custom rule:

### Block unexpected API methods

Expression:

```text
(http.host eq "api.unlxck.com" and not http.request.method in {"GET" "HEAD" "POST" "PUT" "PATCH" "DELETE" "OPTIONS"})
```

Action: **Block**

Do not challenge all requests to `/api/*`. Browser API calls expect JSON and can fail when Cloudflare returns an interactive challenge page.

## Rate limiting

Protect the expensive plan-generation endpoint first. Cloudflare exposes different expression fields and time windows by plan, so use the matching version below.

### Free plan

Free rate-limit rules can match the request path but not host or method.

Expression:

```text
(http.request.uri.path eq "/api/plans/generate")
```

Threshold: **2 requests per 10 seconds per IP**.

Mitigation timeout: **10 seconds**. This is the only timeout available on Free.

### Pro plan

Pro rules can match host and path but not method.

Expression:

```text
(http.host eq "api.unlxck.com" and http.request.uri.path eq "/api/plans/generate")
```

Threshold: **5 requests per 60 seconds per IP**.

Mitigation timeout: **10 minutes**.

### Business or higher

Business rules can also match the HTTP method.

Expression:

```text
(http.host eq "api.unlxck.com" and http.request.method eq "POST" and http.request.uri.path eq "/api/plans/generate")
```

Threshold: **5 requests per 60 seconds per IP**.

Mitigation timeout: **10 minutes**.

Action for every plan: **Block** rather than interactive challenge because this is a JSON endpoint.

Application and database rate limits remain authoritative per account. Cloudflare's rule is an outer IP-based flood control and may allow a small excess burst before its distributed counters update.

Rule allowance by plan:

- Free: 1 rate-limit rule.
- Pro: 2 rate-limit rules.
- Business: 5 rate-limit rules.

If a second rule is available, protect large feedback uploads using the same plan-compatible expression pattern for `/api/feedback/global`. Suggested threshold: 5 requests per 60 seconds per IP on Pro or above.

## Bot controls

Do not blindly enable basic Bot Fight Mode for the whole zone. It can challenge legitimate API traffic, and its actions cannot be skipped with ordinary WAF custom rules. Prefer Turnstile on authentication and explicit rate limits on JSON API endpoints.

If Super Bot Fight Mode is available, start in a monitoring or conservative mode and review Security Events before blocking likely automated traffic.

## Origin protection

The public origin is the largest remaining Cloudflare bypass risk. Complete one of these approaches:

### Preferred: Cloudflare Tunnel

- Run `cloudflared` beside Caddy.
- Route `api.unlxck.com` through the tunnel.
- Remove public inbound TCP 80 and 443 from the Hetzner firewall after tunnel health is confirmed.
- Keep SSH independently restricted and tested.

### Alternative: Cloudflare-only firewall plus authenticated origin pulls

- Enable Authenticated Origin Pulls.
- Install and require the origin-pull certificate at Caddy.
- Prefer a zone-level or per-hostname client certificate over Cloudflare's shared global certificate.
- Restrict Hetzner TCP 80/443 sources to Cloudflare's published IPv4 and IPv6 ranges.
- Keep a tested local Caddy health check for deployments.
- Update Cloudflare IP ranges whenever Cloudflare changes them.

Do not apply the firewall restriction before the Cloudflare path and local deployment health check have both been verified. Otherwise the API can be locked out.

## Origin server baseline

The repository enforces:

- TCP 80 and 443 only; no direct UDP 443 exposure.
- HTTP early data disabled at Caddy.
- 32 KB maximum request-header size.
- 10-second header-read timeout.
- API responses marked `no-store`.
- Caddy `Server` header removed.
- API pages excluded from search indexing.
- Existing HSTS, clickjacking, MIME-sniffing, referrer and permissions protections preserved.

## Monitoring

Review Cloudflare Security Events after every rule change. Look for:

- Legitimate Vercel or browser requests being blocked.
- Repeated requests to plan generation, feedback, authentication or nonexistent routes.
- Large spikes from distributed IPs that pass simple per-IP thresholds.
- Unexpected traffic reaching the origin outside Cloudflare.

Retain Sentry and backend request IDs. Cloudflare is the edge layer; application authentication, Supabase RLS and database rate limits remain required.
