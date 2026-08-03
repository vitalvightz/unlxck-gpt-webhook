import type { MeResponse } from "@/lib/types";

function withoutTimezoneRefreshFields(me: MeResponse): string {
  const profile: Partial<MeResponse["profile"]> = { ...me.profile };
  delete profile.athlete_timezone;
  delete profile.updated_at;
  return JSON.stringify({ ...me, profile });
}

/**
 * Keep the Settings route's existing `me` object when the server response only
 * acknowledges an automatic device-timezone sync. The Settings page hydrates
 * its account draft from `me` identity, so replacing that object while a name
 * or photo edit is in progress would silently erase the edit.
 *
 * The parent auth provider still receives the fresh response. This function
 * only controls the route-local snapshot consumed by Settings.
 */
export function reconcileSettingsMe(
  current: MeResponse | null,
  next: MeResponse | null,
): MeResponse | null {
  if (!current || !next || current.profile.athlete_id !== next.profile.athlete_id) {
    return next;
  }

  return withoutTimezoneRefreshFields(current) === withoutTimezoneRefreshFields(next)
    ? current
    : next;
}
