"use client";
import { useEffect, useState } from "react";
import { useAppSession } from "@/components/auth-provider";
import { getAnalyticsPreference, setAnalyticsPreference } from "@/lib/api";
export function AnalyticsPreference() {
  const { session, me } = useAppSession();
  const token = session?.access_token;
  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let current = true;
    if (token)
      getAnalyticsPreference(token)
        .then((p) => {
          if (current) setEnabled(p.enabled);
        })
        .catch(() => {
          if (current) setError("Unable to load analytics preference.");
        });
    return () => {
      current = false;
    };
  }, [token]);
  if (me?.profile.is_minor) return null;
  return (
    <div className="support-panel">
      <h3>Optional product analytics</h3>
      <p className="muted">
        Share feature interactions like timer starts and plan views to help improve Unlxck. No notes, nutrition or health details. Kept up to 180 days. Switch off any time. Saved training records stay available for service diagnostics.
      </p>
      <label>
        <input
          type="checkbox"
          checked={enabled === true}
          disabled={enabled === null || busy}
          onChange={async (e) => {
            if (!token) return;
            setBusy(true);
            setError(null);
            try {
              const result = await setAnalyticsPreference(
                token,
                e.target.checked,
              );
              setEnabled(result.enabled);
            } catch {
              setError("Unable to save preference. Try again.");
            } finally {
              setBusy(false);
            }
          }}
        />{" "}
        Allow optional feature analytics
      </label>
      {error ? <p role="alert">{error}</p> : null}
    </div>
  );
}
