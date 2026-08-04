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
  "quiet_hours_start" | "quiet_hours_end" | "preferred_training_time"
>;

const MASTER_ROW: { key: BooleanPreferenceKey; title: string; detail: string } = {
  key: "push_enabled",
  title: "Intelligent coaching notifications",
  detail: "Pause or resume every account-level coaching notification.",
};

const PREFERENCE_ROWS: Array<{
  key: BooleanPreferenceKey;
  title: string;
  detail: string;
}> = [
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

export function PushNotificationSettings({ token }: { token: string }) {
  const [state, setState] = useState<PushOptInState | "loading" | "working">("loading");
  const [preferences, setPreferences] = useState<NotificationPreferences | null>(null);
  const [quietStart, setQuietStart] = useState(DEFAULT_NOTIFICATION_PREFERENCES.quiet_hours_start);
  const [quietEnd, setQuietEnd] = useState(DEFAULT_NOTIFICATION_PREFERENCES.quiet_hours_end);
  const [trainingTime, setTrainingTime] = useState("");
  const [workingPreference, setWorkingPreference] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function syncPreferences(updated: NotificationPreferences) {
    setPreferences(updated);
    setQuietStart(updated.quiet_hours_start);
    setQuietEnd(updated.quiet_hours_end);
    setTrainingTime(updated.preferred_training_time ?? "");
  }

  useEffect(() => {
    let cancelled = false;
    Promise.all([getPushOptInState(token), getPushSettings(token)])
      .then(([resolvedState, settings]) => {
        if (cancelled) return;
        const resolvedPreferences = parseNotificationPreferences(
          (settings as typeof settings & { preferences?: unknown }).preferences,
        );
        setState(resolvedState);
        syncPreferences(resolvedPreferences);
      })
      .catch(() => {
        if (!cancelled) {
          setState("unsupported");
          syncPreferences(DEFAULT_NOTIFICATION_PREFERENCES);
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
    const previous = preferences;
    // Flip on screen straight away; the row is what the athlete just touched.
    setPreferences({ ...previous, [key]: checked });
    setWorkingPreference(key);
    setError(null);
    try {
      syncPreferences(await updateNotificationPreferences(token, { [key]: checked }));
    } catch (caught) {
      setPreferences(previous);
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
      syncPreferences(
        await updateNotificationPreferences(token, {
          quiet_hours_start: quietStart,
          quiet_hours_end: quietEnd,
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update quiet hours.");
    } finally {
      setWorkingPreference(null);
    }
  }

  async function saveTrainingTime() {
    if (!preferences || workingPreference) return;
    setWorkingPreference("training-time");
    setError(null);
    try {
      syncPreferences(
        await updateNotificationPreferences(token, {
          preferred_training_time: trainingTime || null,
        }),
      );
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : "Unable to update training time.");
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

  // The master switch gates delivery rather than rewriting the stored choices,
  // so a paused account reads as every category off and resuming brings back
  // exactly the rows the athlete had before.
  const paused = preferences ? !preferences.push_enabled : false;

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
          <label className="settings-toggle-row">
            <span>
              <span className="settings-toggle-title">{MASTER_ROW.title}</span>
              <span className="settings-toggle-detail">{MASTER_ROW.detail}</span>
            </span>
            <input
              type="checkbox"
              checked={preferences.push_enabled}
              disabled={workingPreference !== null}
              onChange={(event) => void savePreference(MASTER_ROW.key, event.target.checked)}
            />
          </label>

          {PREFERENCE_ROWS.map((row) => (
            <label key={row.key} className="settings-toggle-row">
              <span>
                <span className="settings-toggle-title">{row.title}</span>
                <span className="settings-toggle-detail">{row.detail}</span>
              </span>
              <input
                type="checkbox"
                checked={!paused && preferences[row.key]}
                disabled={paused || workingPreference !== null}
                onChange={(event) => void savePreference(row.key, event.target.checked)}
              />
            </label>
          ))}

          <div className="settings-subsection">
            <div className="settings-subsection-header">
              <h3 className="settings-subsection-title">Session timing</h3>
            </div>
            <div className="settings-control-grid">
              <label className="field">
                <span>Usual training time</span>
                <input
                  type="time"
                  value={trainingTime}
                  disabled={paused || !preferences.session_reminders || workingPreference !== null}
                  onChange={(event) => setTrainingTime(event.target.value)}
                />
                <small>Optional. Without a time, UNLXCK will not guess when you train.</small>
              </label>
            </div>
            <div className="form-actions settings-subsection-actions">
              <button
                type="button"
                className="secondary-button"
                disabled={
                  paused ||
                  !preferences.session_reminders ||
                  workingPreference !== null ||
                  trainingTime === (preferences.preferred_training_time ?? "")
                }
                onClick={() => void saveTrainingTime()}
              >
                {workingPreference === "training-time" ? "Saving…" : "Save training time"}
              </button>
            </div>
          </div>

          <div className="settings-subsection">
            <div className="settings-subsection-header">
              <h3 className="settings-subsection-title">Quiet hours</h3>
            </div>
            <label className="settings-toggle-row">
              <span>
                <span className="settings-toggle-title">Hold routine notifications</span>
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
            </label>
            <div className="settings-control-grid">
              <label className="field">
                <span>Start</span>
                <input
                  type="time"
                  value={quietStart}
                  disabled={!preferences.quiet_hours_enabled || workingPreference !== null}
                  onChange={(event) => setQuietStart(event.target.value)}
                />
              </label>
              <label className="field">
                <span>End</span>
                <input
                  type="time"
                  value={quietEnd}
                  disabled={!preferences.quiet_hours_enabled || workingPreference !== null}
                  onChange={(event) => setQuietEnd(event.target.value)}
                />
              </label>
            </div>
            <div className="form-actions settings-subsection-actions">
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
        </div>
      ) : null}

      {error ? <p className="settings-push-error">{error}</p> : null}
    </div>
  );
}
