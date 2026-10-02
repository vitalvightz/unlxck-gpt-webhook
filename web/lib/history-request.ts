import { ApiError } from "@/lib/api";
import { getSupabaseBrowserClient } from "@/lib/supabase";

/** Recover a stale History token once, without crossing account boundaries. */
export async function loadHistoryWithAuthRecovery<T>(
  session: { access_token: string; user_id?: string | null },
  request: (token: string) => Promise<T>,
  isCancelled: () => boolean = () => false,
): Promise<T> {
  try {
    return await request(session.access_token);
  } catch (error) {
    if (!(error instanceof ApiError) || error.status !== 401 || !session.user_id || isCancelled()) {
      throw error;
    }

    const auth = getSupabaseBrowserClient().auth;
    const current = await auth.getSession();
    if (current.error || current.data.session?.user.id !== session.user_id || isCancelled()) {
      throw error;
    }

    // Auto-refresh may already have replaced the token while the request ran.
    let live = current.data.session;
    if (live.access_token === session.access_token) {
      const refreshed = await auth.refreshSession();
      if (refreshed.error || refreshed.data.session?.user.id !== session.user_id || isCancelled()) {
        throw error;
      }
      live = refreshed.data.session;
    }

    // Retry only once: a second 401 must surface, not loop.
    return request(live.access_token);
  }
}
