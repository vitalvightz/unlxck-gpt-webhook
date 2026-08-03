"use client";

import { useCallback, useEffect, useMemo, useState, type ReactNode } from "react";

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

  useEffect(() => {
    setSettingsMe((current) => reconcileSettingsMe(current, parentSession.me));
  }, [parentSession.me]);

  const replaceMe = useCallback(
    (nextMe: MeResponse | null) => {
      parentSession.replaceMe(nextMe);
      setSettingsMe((current) => reconcileSettingsMe(current, nextMe));
    },
    [parentSession.replaceMe],
  );

  const settingsSession = useMemo(
    () => ({ ...parentSession, me: settingsMe, replaceMe }),
    [parentSession, replaceMe, settingsMe],
  );

  return <AppSessionContext.Provider value={settingsSession}>{children}</AppSessionContext.Provider>;
}
