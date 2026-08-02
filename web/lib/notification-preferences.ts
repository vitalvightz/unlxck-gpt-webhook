"use client";

export type NotificationPreferences = {
  push_enabled: boolean;
  session_reminders: boolean;
  checkin_reminders: boolean;
  injury_followups: boolean;
  plan_update_alerts: boolean;
  progress_milestones: boolean;
  coach_messages: boolean;
  quiet_hours_enabled: boolean;
  quiet_hours_start: string;
  quiet_hours_end: string;
};

export type NotificationPreferencesPatch = Partial<NotificationPreferences>;

export const DEFAULT_NOTIFICATION_PREFERENCES: NotificationPreferences = {
  push_enabled: true,
  session_reminders: true,
  checkin_reminders: true,
  injury_followups: true,
  plan_update_alerts: true,
  progress_milestones: true,
  coach_messages: true,
  quiet_hours_enabled: true,
  quiet_hours_start: "22:00",
  quiet_hours_end: "07:00",
};

function normalizePreferences(value: unknown): NotificationPreferences {
  const candidate = value && typeof value === "object" ? value as Record<string, unknown> : {};
  return {
    push_enabled: candidate.push_enabled !== false,
    session_reminders: candidate.session_reminders !== false,
    checkin_reminders: candidate.checkin_reminders !== false,
    injury_followups: candidate.injury_followups !== false,
    plan_update_alerts: candidate.plan_update_alerts !== false,
    progress_milestones: candidate.progress_milestones !== false,
    coach_messages: candidate.coach_messages !== false,
    quiet_hours_enabled: candidate.quiet_hours_enabled !== false,
    quiet_hours_start:
      typeof candidate.quiet_hours_start === "string"
        ? candidate.quiet_hours_start.slice(0, 5)
        : DEFAULT_NOTIFICATION_PREFERENCES.quiet_hours_start,
    quiet_hours_end:
      typeof candidate.quiet_hours_end === "string"
        ? candidate.quiet_hours_end.slice(0, 5)
        : DEFAULT_NOTIFICATION_PREFERENCES.quiet_hours_end,
  };
}

export async function updateNotificationPreferences(
  token: string,
  patch: NotificationPreferencesPatch,
): Promise<NotificationPreferences> {
  const response = await fetch("/api/push/preferences", {
    method: "PUT",
    headers: {
      Authorization: `Bearer ${token}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(patch),
  });
  const raw = await response.text();
  if (!response.ok) {
    let message = "Unable to update notification preferences.";
    try {
      const decoded = raw ? JSON.parse(raw) as { detail?: string } : null;
      if (decoded?.detail) message = decoded.detail;
    } catch {
      // Keep the safe generic message for non-JSON proxy responses.
    }
    throw new Error(message);
  }
  try {
    return normalizePreferences(raw ? JSON.parse(raw) : null);
  } catch {
    throw new Error("Server returned invalid notification preferences.");
  }
}

export function parseNotificationPreferences(value: unknown): NotificationPreferences {
  return normalizePreferences(value);
}
