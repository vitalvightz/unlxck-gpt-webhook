"use client";

import { useEffect, useState } from "react";

import { getPushSettings } from "@/lib/api";
import {
  DEFAULT_NOTIFICATION_PREFERENCES,
  parseNotificationPreferences,
  updateNotificationPreferences,
  type NotificationPreferences,
} from "@/lib/notification-preferences";
import {
  getPushOptInState,
  subscribeToPushNotifications,
  unsubscribeFromPushNotifications,
  type PushOptInState,
} from "@/lib/push";

type BooleanPreferenceKey = Exclude<
  keyof NotificationPreferences,
  "quiet_hours_start" | "quiet_hours_end"
>;

const PREFERENCE_ROWS: Array<{
  key: BooleanPreferenceKey;
  title: string;
  detail: string;
}> = [
  {
    key: "push_enabled",
    title: "Intelligent coaching notifications",
    detail: "Pause or resume every account-level coaching notification.",
  },
  {
    key: "session_reminders",
    title: "Session reminders",
    detail: "Training-session timing and actions.",
  },
  {
    key: "checkin_reminders",
    title: "Check-in reminders",
    detail: "Readiness prompts before the day's call is set.",
  },
  {
    key: "injury_followups",
    title: "Injury follow-ups",
    detail: "Updates needed to keep a restriction accurate.",
  },
  {
    key: "plan_update_alerts",
    title: "Plan update alerts",
    detail: "New plans, reviews and build outcomes.",
  },
  {
    key: "progress_milestones",
    title: "Progress milestones",
    detail: "Meaningful week, block and level achievements.",
  },
  {
    key: "coach_messages",
    title: "Coach messages",
    detail: "Direct coach or admin notes when connected.",
  },
];

/**
 * Device Web Push opt-in plus server-owned account preferences. The legacy
 * local-only toggle list rendered by Settings is hidden below; this component
 * is now the single preference authority the backend actually enforces.
 */
export function PushNotificationSettings({ token }: { token: string }) {
  const [state, setState] = useState<PushOptInState | "loading" | "working">("loading");
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [quietStart, setQuietStart] = useState(DEFAULT_NOTIFICATION_PREFERENCES.quiet_hours_start);
  const [quietEnd, setQuietEnd] = useState(DEFAULT_NOTIFICATION_PREFERENCES.quiet_hours_end);
  const [workingPreference, setWorkingPreference] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    Promise.all([getPushOptInState(token), getPushSettings(token)])
      .then(([resolvedState, settings]) => {
        if (cancelled) return;
        const resolvedPreferences = parseNotificationPreferences(
          (settings as typeof settings & { preferences?: unknown }).preferences,
        );
        setState(resolvedState);
        setPreferences(resolvedPreferences);
        setQuietStart(resolvedPreferences.quiet_hours_start);
        setQuietEnd(resolvedPreferences.quiet_hours_end);
      })
      .catch(() => {
        if (!cancelled) {
          setState("unsupported");
          setPreferences(DEFAULT_NOTIFICATION_PREFERENCES);
          setError("Unable to load notification settings right now.");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [token]);

  async function handleDeviceToggle(enable: boolean) {
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

  async function savePreference(key: BooleanPreferenceKey, checked: boolean) {
    if (!preferences || workingPreference) return;
    setWorkingPreference(key);
    setError(null);
    try {
      const updated = await updateNotificationPreferences(token, { [key]: checked });
      setPreferences(updated);
      setQuietStart(updated.quiet_hours_start);
      setQuietEnd(updated.quiet_hours_end);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update preferences.");
    } finally {
      setWorkingPreference(null);
    }
  }

  async function saveQuietHours() {
    if (!preferences || workingPreference) return;
    setWorkingPreference("quiet-hours");
    setError(null);
    try {
      const updated = await updateNotificationPreferences(token, {
        quiet_hours_start: quietStart,
        quiet_hours_end: quietEnd,
      });
      setPreferences(updated);
      setQuietStart(updated.quiet_hours_start);
      setQuietEnd(updated.quiet_hours_end);
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update quiet hours.");
    } finally {
      setWorkingPreference(null);
    }
  }

  const detail =
    state === "unsupported"
      ? "Not available in this browser. On iPhone, install UNLXCK to your home screen first."
      : state === "server-disabled"
        ? "Notifications aren't enabled on the server yet."
        : state === "denied"
          ? "Blocked in browser settings. Allow notifications for UNLXCK to turn these on."
          : "Coach-led check-ins, session actions and plan alerts on this device.";

  const canToggle = state === "subscribed" || state === "unsubscribed" || state === "working";

  return (
    <div className="settings-push-block">
      {/* Settings previously rendered a second localStorage-only list directly
          after this component. Hide that obsolete preview surface so athletes
          see only the preferences the server enforces. */}
      <style>{"#notifications > .settings-toggle-list { display: none; }"}</style>

      <div className="settings-toggle-row settings-push-row">
        <span>
          <span className="settings-toggle-title">Push notifications on this device</span>
          <span className="settings-toggle-detail">{detail}</span>
        </span>
        {canToggle ? (
          <button
            type="button"
            className={state === "subscribed" ? "ghost-button" : "cta"}
            onClick={() => handleDeviceToggle(state !== "subscribed")}
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

      {preferences ? (
        <div className="settings-toggle-list settings-server-notification-list">
          {PREFERENCE_ROWS.map((row) => (
            <label key={row.key} className="settings-toggle-row">
              <span>
                <span className="settings-toggle-title">{row.title}</span>
                <span className="settings-toggle-detail">{row.detail}</span>
              </span>
              <input
                type="checkbox"
                checked={preferences[row.key]}
                disabled={workingPreference !== null}
                onChange={(event) => void savePreference(row.key, event.target.checked)}
              />
            </label>
          ))}

          <div className="settings-toggle-row">
            <span>
              <span className="settings-toggle-title">Quiet hours</span>
              <span className="settings-toggle-detail">
                Routine coaching notifications wait outside this window.
              </span>
            </span>
            <input
              type="checkbox"
              checked={preferences.quiet_hours_enabled}
              disabled={workingPreference !== null}
              onChange={(event) => void savePreference("quiet_hours_enabled", event.target.checked)}
            />
          </div>

          <div className="settings-control-grid">
            <label className="field">
              <span>Quiet hours start</span>
              <input
                type="time"
                value={quietStart}
                disabled={!preferences.quiet_hours_enabled || workingPreference !== null}
                onChange={(event) => setQuietStart(event.target.value)}
              />
            </label>
            <label className="field">
              <span>Quiet hours end</span>
              <input
                type="time"
                value={quietEnd}
                disabled={!preferences.quiet_hours_enabled || workingPreference !== null}
                onChange={(event) => setQuietEnd(event.target.value)}
              />
            </label>
            <button
              type="button"
              className="secondary-button"
              disabled={
                !preferences.quiet_hours_enabled ||
                workingPreference !== null ||
                (quietStart === preferences.quiet_hours_start && quietEnd === preferences.quiet_hours_end)
              }
              onClick={() => void saveQuietHours()}
            >
              {workingPreference === "quiet-hours" ? "Saving…" : "Save quiet hours"}
            </button>
          </div>
        </div>
      ) : null}

      {error ? <p className="settings-push-error">{error}</p> : null}
    </div>
  );
}
