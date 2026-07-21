"use client";

import { useEffect, useState } from "react";

import {
  getPushOptInState,
  subscribeToPushNotifications,
  unsubscribeFromPushNotifications,
  type PushOptInState,
} from "@/lib/push";

/**
 * Device-level web push control for the Settings notifications card. One
 * subscription powers every push the backend sends to this browser install:
 * the plan-ready "camp is lxcked in" alert and the daily morning check-in.
 */
export function PushNotificationSettings({ token }: { token: string }) {
  const [state, setState] = useState<PushOptInState | "loading" | "working">("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getPushOptInState(token)
      .then((resolved) => {
        if (!cancelled) {
          setState(resolved);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setState("unsupported");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function handleToggle(enable: boolean) {
    setState("working");
    setError(null);
    try {
      if (enable) {
        await subscribeToPushNotifications(token);
        setState("subscribed");
      } else {
        await unsubscribeFromPushNotifications(token);
        setState("unsubscribed");
      }
    } catch (caught) {
      setError(
        caught instanceof Error ? caught.message : "Unable to update notifications right now.",
      );
      setState(await getPushOptInState(token));
    }
  }

  const detail =
    state === "unsupported"
      ? "Not available in this browser. On iPhone, install UNLXCK to your home screen first."
      : state === "server-disabled"
        ? "Notifications aren't enabled on the server yet."
        : state === "denied"
          ? "Blocked in browser settings. Allow notifications for UNLXCK to turn these on."
          : "Plan-ready alerts and the daily morning check-in nudge on this device.";

  const canToggle = state === "subscribed" || state === "unsubscribed" || state === "working";

  return (
    <div className="settings-push-block">
      <div className="settings-toggle-row settings-push-row">
        <span>
          <span className="settings-toggle-title">Push notifications on this device</span>
          <span className="settings-toggle-detail">{detail}</span>
        </span>
        {canToggle ? (
          <button
            type="button"
            className={state === "subscribed" ? "ghost-button" : "cta"}
            onClick={() => handleToggle(state !== "subscribed")}
            disabled={state === "working"}
          >
            {state === "working"
              ? "Updating…"
              : state === "subscribed"
                ? "Turn off"
                : "Turn on"}
          </button>
        ) : null}
      </div>
      {error ? <p className="settings-push-error">{error}</p> : null}
    </div>
  );
}
