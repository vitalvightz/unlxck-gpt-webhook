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

// The public top bar is useful on the marketing homepage, but auth forms
// already provide their own account switch link. Keeping the bar off auth
// routes avoids duplicate calls to action and, on narrow screens, leaves the
// form heading clear of fixed navigation.
export function shouldShowBrandTopbar(pathname: string, hasSession: boolean): boolean {
  return getShellSurface(pathname, hasSession) === "brand" && !hasSession && !isAuthSurfaceRoute(pathname);
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

// Surface the server can safely commit before the client session is known.
// Every public entry route starts with the brand shell so workspace navigation
// cannot flash while authentication resolves. On `/`, a confirmed session
// switches the client to the workspace surface after hydration; the final
// signed-in workspace is unchanged. Other routes still defer to the client.
export function getServerShellSurface(pathname: string | null | undefined): ShellSurface | null {
  if (pathname && BRAND_SURFACE_ROUTES.has(pathname)) {
    return "brand";
  }
  return null;
}
