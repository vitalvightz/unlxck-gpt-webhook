# UNLXCK Cookies & Local Storage (PECR Position)

**Regulation:** Regulation 6, Privacy and Electronic Communications (EC Directive) Regulations 2003
**Status:** One open item — see "Sentry Session Replay" below.

## The rule

PECR reg. 6 requires consent before storing information on, or reading information from, a user's device — cookies, `localStorage`, `sessionStorage` alike. The technology does not matter; the storage does.

There is one exemption, at reg. 6(4): storage that is **strictly necessary** for a service the user has explicitly requested. The ICO reads this narrowly. "Necessary for us to run the business" is not the test; "the requested feature cannot work without it" is. Analytics, product measurement and session recording are outside it.

UNLXCK uses **no cookie banner**, which is only correct while every item of storage is either strictly necessary or consented to.

## Register

| What | Purpose | PECR position |
|---|---|---|
| Supabase auth session (`localStorage`) | Keeps the athlete signed in between page loads | **Strictly necessary.** Authentication is the requested service; without it every navigation would sign the athlete out. |
| Cloudflare Turnstile (`__cf_bm` and related) | Bot and abuse prevention at signup and login | **Strictly necessary.** Reg. 6(4) covers security measures protecting the requested service. The ICO accepts security storage on this footing, and the data at risk here is children's health data. Turnstile must never receive athlete health data — see `docs/processor-dpa-international-transfer-verification.md`. |
| Appearance mode (`auth-provider.tsx:55`) | Remembers the athlete's light/dark preference | **Strictly necessary.** A user-preference store set in direct response to a user action is the textbook reg. 6(4) example. |
| Generation status / dismissed-ribbon keys (`generation-status-provider.tsx`, `global-generation-status.tsx`) | Tracks an in-flight plan generation across tabs and remembers a dismissed notice | **Strictly necessary.** Purely functional state for a feature the athlete started. Contains no health information beyond a job identifier. |
| **Sentry Session Replay** (`instrumentation-client.ts`) | Records session video-reconstructions at 10% of sessions and 100% of error sessions | **NOT strictly necessary — consent required, and not currently obtained.** See below. |

## Sentry Session Replay — open item

`web/instrumentation-client.ts` initialises `Sentry.replayIntegration()` with `replaysSessionSampleRate: 0.1` and `replaysOnErrorSampleRate: 1.0`. Replay writes a session identifier to browser storage, which engages reg. 6, and session recording does not qualify as strictly necessary under reg. 6(4).

Two things follow, and they are independent:

1. **PECR** — consent is required before replay initialises. There is no consent mechanism in the product today.
2. **UK GDPR** — Sentry is a processor receiving personal data. It is absent from `docs/data-map-processor-register.md` and `docs/processor-dpa-international-transfer-verification.md`, both of which currently state it is not used. That is an Article 30 and Article 13(1)(e) problem, and a Chapter V one if the data leaves the UK, and it is not cured by fixing PECR.

The replay configuration is otherwise conservative — `maskAllText`, `maskAllInputs` and `blockAllMedia` are all set — which materially reduces what a recording contains. It does not remove the consent requirement, and URL paths, breadcrumbs, tags and client log capture (`enableLogs: true`) sit outside the masking.

**Resolution options, in order of preference:**

1. **Remove replay, keep error monitoring.** Deleting `replayIntegration` takes UNLXCK out of reg. 6 for this item entirely and leaves no PECR obligation to satisfy. Error events themselves do not require storage consent. The UK GDPR processor work at (2) above still has to be done.
2. **Keep replay behind consent.** Build a PECR-compliant consent mechanism, default off, and initialise replay only on an affirmative choice. Note that a 13-year-old is the one being asked, so the request has to meet the Age Appropriate Design Code's transparency standard, and refusing must be as easy as accepting.

Until one of these is done, this document records a known unremediated gap rather than a compliant position.

## Rules

- No new cookie, `localStorage` or `sessionStorage` write ships without an entry in the table above and a reg. 6 assessment.
- Anything that is not strictly necessary requires a consent mechanism first — the absence of a banner is a consequence of the current storage set, not a standing decision.
- Analytics, advertising, A/B testing and heatmap tooling are all outside reg. 6(4). Treat any proposal to add them as requiring consent infrastructure as a precondition, not a follow-up.

## Review

Re-check when storage is added or removed, when a third-party script is introduced, when the Sentry replay decision is made, or when the ICO updates its guidance on the strictly-necessary exemption.

This is an internal compliance assessment, not legal advice.
