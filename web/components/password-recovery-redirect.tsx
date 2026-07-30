"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";

import { markPasswordRecovery } from "@/lib/password-recovery";
import { getSupabaseBrowserClient } from "@/lib/supabase";

const RESET_PASSWORD_ROUTE = "/reset-password";

/**
 * Carries a recovery sign-in to the set-a-new-password form, wherever it lands.
 *
 * Supabase picks the landing route, not us: it rewrites any `redirect_to` that
 * is not on its Redirect URLs allow list to the project Site URL. When that
 * happens the recovery tokens are consumed on the homepage, supabase-js signs
 * the athlete in, and the reset they asked for silently never happens — they
 * just find themselves logged in. Listening for the event app-wide means the
 * flow completes even when that configuration is wrong.
 *
 * PASSWORD_RECOVERY is the trustworthy signal here: supabase-js emits it only
 * after validating and storing a recovery session. Nothing in a URL can fake it,
 * which is what keeps the marker safe as proof on the other end.
 *
 * Renders nothing.
 */
export function PasswordRecoveryRedirect() {
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    let client;
    try {
      client = getSupabaseBrowserClient();
    } catch {
      // Missing public Supabase config; nothing to listen to.
      return;
    }

    let navigationId: number | undefined;

    const { data: { subscription } } = client.auth.onAuthStateChange((event, session) => {
      if (event !== "PASSWORD_RECOVERY" || !session?.user?.id) {
        return;
      }

      // Writing the marker is pure storage, so it is safe to do inline.
      markPasswordRecovery(session.user.id);

      // Already on the form (the link landed correctly) — it reads the event
      // itself, so leave the history entry alone.
      if (pathname === RESET_PASSWORD_ROUTE) {
        return;
      }

      // Navigating must NOT happen inline. supabase-js runs this callback while
      // holding its auth lock, and the reset page calls getSession() as it
      // mounts — that call would queue behind a lock this callback has not
      // released yet, and the page hangs on "Verifying your reset link...".
      // Deferring by a macrotask lets the lock go first.
      navigationId = window.setTimeout(() => router.replace(RESET_PASSWORD_ROUTE), 0);
    });

    return () => {
      window.clearTimeout(navigationId);
      subscription.unsubscribe();
    };
  }, [pathname, router]);

  return null;
}
