"use client";

import { useCallback, useMemo, useState, type ReactNode } from "react";

import { AppSessionContext, useAppSession } from "@/components/auth-provider";
import { reconcileSettingsMe } from "@/lib/settings-session-shield";
import type { MeResponse } from "@/lib/types";

/**
 * Settings owns editable name/photo drafts. An automatic timezone update still
 * belongs in the parent session, but its response must not replace the route's
 * `me` identity and retrigger account hydration while a draft is in progress.
 */
export default function SettingsLayout({ children }: Readonly<{ children: ReactNode }>) {
  const parentSession = useAppSession();
  const [settingsMe, setSettingsMe] = useState<MeResponse | null>(parentSession.me);

  // Reconcile during render, not in an effect. An effect leaves one committed
  // frame where the parent session is hydrated but this snapshot is still null;
  // RequireAuth reads that frame as "signed in with no profile" and bounces a
  // cold load of /settings to /login (and on to the landing route).
  const reconciledMe = reconcileSettingsMe(settingsMe, parentSession.me);
  if (reconciledMe !== settingsMe) {
    setSettingsMe(reconciledMe);
  }

  const replaceMe = useCallback(
    (nextMe: MeResponse | null) => {
      parentSession.replaceMe(nextMe);
      setSettingsMe((current) => reconcileSettingsMe(current, nextMe));
    },
    [parentSession.replaceMe],
  );

  const settingsSession = useMemo(
    () => ({ ...parentSession, me: reconciledMe, replaceMe }),
    [parentSession, reconciledMe, replaceMe],
  );

  return <AppSessionContext.Provider value={settingsSession}>{children}</AppSessionContext.Provider>;
}
