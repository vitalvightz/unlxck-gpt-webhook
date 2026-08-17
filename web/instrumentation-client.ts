import * as Sentry from "@sentry/nextjs";

// Error monitoring only. Session Replay is deliberately absent and must not be
// reintroduced without the compliance work that goes with it.
//
// Replay recorded 10% of all sessions and 100% of error sessions on a service
// whose users are athletes from age 13 up, entering injuries, pain, readiness
// and bodyweight. Two problems came with it, and neither was solved by the
// masking options it was configured with:
//
//   * it writes a session identifier to browser storage, which needs consent
//     under PECR reg. 6 — session recording is not "strictly necessary" for a
//     service the user requested, and UNLXCK has no consent mechanism; and
//   * it disclosed children's session data to a processor that the Privacy
//     Notice did not name and the processor register recorded as unused.
//
// Removing it takes UNLXCK out of PECR reg. 6 for this path entirely: error
// events themselves need no storage consent. See docs/cookies-and-local-storage.md.
//
// Adding replay back means, first: a consent mechanism defaulting to off, a
// DPIA covering recording of child sessions, and the Age Appropriate Design
// Code position on asking a 13-year-old for that consent.
Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  tracesSampleRate: process.env.NODE_ENV === "development" ? 1.0 : 0.1,
  enableLogs: true,
});

document.addEventListener("click", (event) => {
  const target = event.target;
  if (!(target instanceof Element)) {
    return;
  }

  const actionButton = target.closest<HTMLButtonElement>(".plan-action-menu-popover button");
  const details = actionButton?.closest<HTMLDetailsElement>("details.plan-action-menu");
  if (details) {
    details.open = false;
  }
});

export const onRouterTransitionStart = Sentry.captureRouterTransitionStart;
