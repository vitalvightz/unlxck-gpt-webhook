// Shell-surface contract shared by the root layout (server) and AppNav (client).
//
// The app has two chromes:
//   - "brand":     the public entry shell (marketing homepage + auth routes).
//                  No signed-in workspace sidebar, no floating workspace Menu.
//   - "workspace": the signed-in app shell with the full sidebar navigation.
//
// Keeping the route lists and the resolution rules in one pure module means the
// server and client agree on the surface without duplicating per-page checks,
// and the logic stays unit-testable without a DOM or a Supabase session.

export type ShellSurface = "brand" | "workspace";

// Fully public authentication routes. These render only the brand/auth shell:
// the auth form owns all navigation on them, so they resolve to the brand
// surface regardless of session. Note that only /login and /signup send a
// signed-in visitor away (AuthForm does it); /reset-password and
// /forgot-password stay reachable while signed in, because a recovery session
// is itself a signed-in session.
export const AUTH_SURFACE_ROUTES: ReadonlySet<string> = new Set([
  "/login",
  "/signup",
  "/forgot-password",
  "/reset-password",
]);

// Brand surface = the public marketing homepage plus every auth route.
export const BRAND_SURFACE_ROUTES: ReadonlySet<string> = new Set([
  "/",
  ...AUTH_SURFACE_ROUTES,
]);

// True on the public auth routes, where the signed-in workspace navigation must
// never render (not even the loading/"checking your session" state), because
// the auth form is the whole experience.
export function isAuthSurfaceRoute(pathname: string): boolean {
  return AUTH_SURFACE_ROUTES.has(pathname);
}

export function getShellSurface(pathname: string, hasSession: boolean): ShellSurface {
  // Auth routes always use the brand shell. Signed-in users are redirected off
  // them, so we never want workspace chrome to flash in behind the form.
  if (isAuthSurfaceRoute(pathname)) {
    return "brand";
  }
  if (hasSession) {
    return "workspace";
  }
  return BRAND_SURFACE_ROUTES.has(pathname) ? "brand" : "workspace";
}

// Surface the server can commit to before the client session is known. Only the
// auth routes are certain server-side (they ignore session), so setting
// data-app-surface for them on the SSR <html> removes the workspace-shell flash
// on first paint. Every other route defers to the client effect (returns null),
// because whether it is brand or workspace depends on the session.
export function getServerShellSurface(pathname: string | null | undefined): ShellSurface | null {
  if (pathname && isAuthSurfaceRoute(pathname)) {
    return "brand";
  }
  return null;
}
