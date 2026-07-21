---
name: verify
description: Build, launch, and drive the UNLXCK web app for runtime verification of web/ changes.
---

# Verifying web/ changes

## Build & launch

```bash
cd web
npm ci --no-audit --no-fund
cp .env.local.example .env.local   # fill NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY with dummy values
npm run dev                        # serves http://localhost:3000
```

Public routes (`/`, `/login`, `/signup`) render without real Supabase
credentials — dummy env values are enough. Authenticated routes
(`/settings`, `/today`, …) need a real Supabase session and can't be
driven cold.

## Driving with Playwright

Chromium is pre-installed at `/opt/pw-browsers/chromium`; launch with
`chromium.launch({ executablePath: "/opt/pw-browsers/chromium" })`.
Bare-import scripts must live inside `web/` so `@playwright/test`
resolves (ESM ignores cwd/NODE_PATH).

To exercise iOS-only UI (e.g. the PWA "View iPhone steps" flow), pass an
iPhone user agent in `newContext` — capability detection reads
`navigator.userAgent`, not the viewport.

## Gotchas

- The service worker only registers when `NODE_ENV === "production"`;
  `npm run dev` never registers it, which is fine for UI verification.
- Entrance-animated sections (`athlete-motion-slot`, `overview-reveal`)
  fill forwards; keyframes must end at `transform: none` or they become
  the containing block for fixed-position descendants (modals).
