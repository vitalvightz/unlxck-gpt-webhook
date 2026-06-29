"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { PasswordStrengthMeter } from "@/components/password-strength-meter";
import { ApiError, changeUsername, updateMe } from "@/lib/api";
import { isSafeAvatarImageUrl } from "@/lib/avatar-image-url";
import { formatAppDate, formatAppDateTime } from "@/lib/date-format";
import {
  EQUIPMENT_ACCESS_OPTIONS,
  KEY_GOAL_OPTIONS,
  TRAINING_AVAILABILITY_OPTIONS,
  detectDeviceTimeZone,
  getOptionLabel,
  getOptionLabels,
  PROFESSIONAL_STATUS_OPTIONS,
  STANCE_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";
import { hydratePlanRequest } from "@/lib/onboarding";
import { evaluatePasswordStrength } from "@/lib/password-strength";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import { ATHLETE_FULL_NAME_MAX, AVATAR_URL_MAX } from "@/lib/input-limits";
import type { AppearanceMode, GuidedInjuryInput, PlanRequest } from "@/lib/types";

type SettingsSection = {
  id: string;
  label: string;
};

type NotificationKey = "sessionReminders" | "checkInReminders" | "planUpdateAlerts" | "coachMessages";

type NotificationSettings = Record<NotificationKey, boolean>;

type ProgrammeControls = {
  injuryFiltering: "light" | "strict";
  fatigueAdjustment: "light" | "strict";
  requireCoachReview: boolean;
  autoGeneratePlans: boolean;
};

type AdminTemplateDraft = {
  welcomeMessage: string;
  planEmail: string;
  coachNotes: string;
};

const MAX_AVATAR_FILE_BYTES = 5 * 1024 * 1024;
const USERNAME_PATTERN = /^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$/;
const USERNAME_MIN = 3;
const USERNAME_MAX = 24;
const NOTIFICATION_STORAGE_KEY = "unlxck.notificationSettings";
const PROGRAMME_CONTROLS_STORAGE_KEY = "unlxck.adminProgrammeControls";
const ADMIN_TEMPLATES_STORAGE_KEY = "unlxck.adminTemplateDrafts";

const ATHLETE_SETTINGS_SECTIONS: SettingsSection[] = [
  { id: "account", label: "Account" },
  { id: "training-profile", label: "Training Profile" },
  { id: "notifications", label: "Notifications" },
  { id: "subscription", label: "Subscription" },
  { id: "privacy", label: "Privacy" },
];

const ADMIN_SETTINGS_SECTIONS: SettingsSection[] = [
  { id: "admin-account", label: "Admin Account" },
  { id: "organisation", label: "Organisation" },
  { id: "coaches-roles", label: "Coaches & Roles" },
  { id: "programme-controls", label: "Programme Controls" },
  { id: "templates-billing", label: "Templates & Billing" },
];

const APPEARANCE_OPTIONS: Array<{
  value: AppearanceMode;
  label: string;
  description: string;
}> = [
  {
    value: "dark",
    label: "Dark",
    description: "Higher contrast workspace.",
  },
  {
    value: "light",
    label: "Light",
    description: "Brighter workspace.",
  },
];

const DEFAULT_NOTIFICATIONS: NotificationSettings = {
  sessionReminders: true,
  checkInReminders: true,
  planUpdateAlerts: true,
  coachMessages: true,
};

const NOTIFICATION_ROWS: Array<{
  key: NotificationKey;
  title: string;
  detail: string;
}> = [
  { key: "sessionReminders", title: "Session reminders", detail: "Training-session timing" },
  { key: "checkInReminders", title: "Check-in reminders", detail: "Fatigue, soreness, and readiness prompts" },
  { key: "planUpdateAlerts", title: "Plan update alerts", detail: "New plan versions and releases" },
  { key: "coachMessages", title: "Coach messages", detail: "Direct admin or coach notes" },
];

const DEFAULT_PROGRAMME_CONTROLS: ProgrammeControls = {
  injuryFiltering: "strict",
  fatigueAdjustment: "light",
  requireCoachReview: true,
  autoGeneratePlans: true,
};

const DEFAULT_ADMIN_TEMPLATES: AdminTemplateDraft = {
  welcomeMessage: "Welcome to camp. Complete Advanced Intake so your plan starts with the right context.",
  planEmail: "Your updated training plan is ready.",
  coachNotes: "Keep review notes short, specific, and tied to athlete risk.",
};

function getInitials(name: string): string {
  const result = name
    .trim()
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((word) => word[0]?.toUpperCase() ?? "")
    .join("");
  return result || "A";
}

function isDataAvatarImageUrl(url: string): boolean {
  return url.startsWith("data:image/");
}

function validateUsernameClient(value: string): string | null {
  const trimmed = value.trim().toLowerCase();
  if (!trimmed) {
    return "Enter a username.";
  }
  if (trimmed.length < USERNAME_MIN || trimmed.length > USERNAME_MAX) {
    return `Username must be ${USERNAME_MIN}-${USERNAME_MAX} characters.`;
  }
  if (!USERNAME_PATTERN.test(trimmed)) {
    return "Use lowercase letters, digits, dots, dashes, or underscores. Must start and end with a letter or number.";
  }
  return null;
}

function formatNextAvailable(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return formatAppDate(iso);
}

function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "Not saved yet";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "Not saved yet";
  return formatAppDateTime(iso);
}

function formatList(values: string[], fallback = "Not set", maxItems = 3): string {
  if (!values.length) {
    return fallback;
  }
  const visible = values.slice(0, maxItems);
  const extraCount = values.length - visible.length;
  return extraCount > 0 ? `${visible.join(", ")} +${extraCount}` : visible.join(", ");
}

function summarizeStyle(request: PlanRequest): string {
  const technical = getOptionLabels(TECHNICAL_STYLE_OPTIONS, request.athlete.technical_style);
  const tactical = getOptionLabels(TACTICAL_STYLE_OPTIONS, request.athlete.tactical_style);
  const stance = request.athlete.stance ? getOptionLabel(STANCE_OPTIONS, request.athlete.stance) : "";
  const parts = [...technical, ...tactical, stance].filter(Boolean);
  return formatList(parts, "Not set", 3);
}

function summarizeGoal(request: PlanRequest): string {
  const primaryValue = request.primary_goal || request.key_goals[0] || "";
  const primary = primaryValue ? getOptionLabel(KEY_GOAL_OPTIONS, primaryValue) : "";
  if (!primary) {
    return "Not set";
  }
  const secondaryCount = request.key_goals.filter((goal) => goal !== primaryValue).length;
  return secondaryCount > 0 ? `${primary} +${secondaryCount}` : primary;
}

function summarizeTrainingDays(request: PlanRequest): string {
  const labels = getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, request.training_availability);
  const sessions = request.weekly_training_frequency ? `${request.weekly_training_frequency}/week` : "";
  const days = formatList(labels, "No days set", 4);
  return sessions ? `${sessions} - ${days}` : days;
}

function summarizeGuidedInjury(injury: GuidedInjuryInput | null | undefined): string | null {
  if (!injury) {
    return null;
  }
  const parts = [injury.area, injury.severity, injury.trend]
    .map((part) => String(part || "").trim())
    .filter(Boolean);
  return parts.length ? parts.join(" / ") : null;
}

function summarizeInjuries(request: PlanRequest): string {
  const guided =
    (request.guided_injuries ?? [])
      .map((injury) => summarizeGuidedInjury(injury))
      .find(Boolean) ?? summarizeGuidedInjury(request.guided_injury);
  if (guided) {
    const additionalCount = Math.max(0, (request.guided_injuries?.length ?? 0) - 1);
    return additionalCount > 0 ? `${guided} +${additionalCount}` : guided;
  }
  return request.injuries?.trim() || "None recorded";
}

function readLocalJson<T>(key: string, fallback: T): T {
  if (typeof window === "undefined") {
    return fallback;
  }
  try {
    const raw = window.localStorage.getItem(key);
    return raw ? { ...fallback, ...JSON.parse(raw) } : fallback;
  } catch {
    return fallback;
  }
}

function writeLocalJson(key: string, value: unknown) {
  if (typeof window === "undefined") {
    return;
  }
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // Non-critical preference persistence.
  }
}

function SettingsNav({
  isSaving,
  onSave,
  sections,
}: Readonly<{
  isSaving: boolean;
  onSave: () => void;
  sections: SettingsSection[];
}>) {
  return (
    <nav className="settings-section-nav" aria-label="Settings sections">
      {sections.map((section) => (
        <a key={section.id} href={`#${section.id}`} className="settings-section-nav-link">
          {section.label}
        </a>
      ))}
      <button type="button" className="settings-section-save" onClick={onSave} disabled={isSaving}>
        {isSaving ? "Saving..." : "Save"}
      </button>
    </nav>
  );
}

function SettingsSummaryItem({ label, value }: Readonly<{ label: string; value: string }>) {
  return (
    <article className="plan-meta-item">
      <p className="plan-meta-label">{label}</p>
      <p className="plan-meta-value">{value}</p>
    </article>
  );
}

export default function SettingsPage() {
  const { isMeHydrated, me, previewAppearanceMode, replaceMe, session, signOut } = useAppSession();

  const [fullName, setFullName] = useState("");
  const [appearanceMode, setAppearanceMode] = useState<AppearanceMode>("dark");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [urlInputValue, setUrlInputValue] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const fileInputRef = useRef<HTMLInputElement>(null);

  const [usernameDraft, setUsernameDraft] = useState("");
  const [usernameError, setUsernameError] = useState<string | null>(null);
  const [usernameMessage, setUsernameMessage] = useState<string | null>(null);
  const [isUsernamePending, startUsernameTransition] = useTransition();

  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPasswords, setShowPasswords] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [isPasswordPending, startPasswordTransition] = useTransition();

  const [notifications, setNotifications] = useState<NotificationSettings>(DEFAULT_NOTIFICATIONS);
  const [programmeControls, setProgrammeControls] = useState<ProgrammeControls>(DEFAULT_PROGRAMME_CONTROLS);
  const [adminTemplates, setAdminTemplates] = useState<AdminTemplateDraft>(DEFAULT_ADMIN_TEMPLATES);

  const isAdmin = me?.profile.role === "admin";
  const sections = isAdmin ? ADMIN_SETTINGS_SECTIONS : ATHLETE_SETTINGS_SECTIONS;
  const hydratedProfile = useMemo(() => hydratePlanRequest(me), [me]);
  const currentUsername = (me?.profile.username ?? "").trim();
  const detectedTimeZone = detectDeviceTimeZone() || me?.profile.athlete_timezone || "Automatic";
  const lastUpdatedLabel = formatDateTime(me?.profile.updated_at);
  const initials = getInitials(fullName || "Athlete");
  const professionalStatusLabel =
    getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, hydratedProfile.athlete.professional_status ?? "") || "Not set";

  const rateLimit = me?.username_rate_limit;
  const usernameRemaining = rateLimit?.remaining ?? 4;
  const usernameMax = rateLimit?.max_changes_per_window ?? 4;
  const usernameWindowDays = rateLimit?.window_days ?? 30;
  const nextAvailableLabel = formatNextAvailable(rateLimit?.next_available_at);

  const passwordStrength = useMemo(
    () => evaluatePasswordStrength(newPassword, { fullName, email: me?.profile.email ?? "" }),
    [newPassword, fullName, me?.profile.email],
  );

  const trainingProfileSummary = useMemo(
    () => [
      { label: "Current sport/style", value: summarizeStyle(hydratedProfile) },
      { label: "Current focus", value: summarizeGoal(hydratedProfile) },
      {
        label: "Equipment access",
        value: formatList(getOptionLabels(EQUIPMENT_ACCESS_OPTIONS, hydratedProfile.equipment_access), "Not set", 4),
      },
      { label: "Training days", value: summarizeTrainingDays(hydratedProfile) },
      { label: "Injuries/limitations", value: summarizeInjuries(hydratedProfile) },
    ],
    [hydratedProfile],
  );

  useEffect(() => {
    if (!me) {
      return;
    }
    setFullName(me.profile.full_name);
    setAppearanceMode(me.profile.appearance_mode ?? "dark");
    const storedAvatar = me.profile.avatar_url ?? "";
    setAvatarUrl(storedAvatar);
    if (!isDataAvatarImageUrl(storedAvatar)) {
      setUrlInputValue(storedAvatar);
    }
    setUsernameDraft(currentUsername);
  }, [currentUsername, me]);

  useEffect(() => {
    setNotifications(readLocalJson(NOTIFICATION_STORAGE_KEY, DEFAULT_NOTIFICATIONS));
    setProgrammeControls(readLocalJson(PROGRAMME_CONTROLS_STORAGE_KEY, DEFAULT_PROGRAMME_CONTROLS));
    setAdminTemplates(readLocalJson(ADMIN_TEMPLATES_STORAGE_KEY, DEFAULT_ADMIN_TEMPLATES));
  }, []);

  useEffect(() => {
    return () => {
      previewAppearanceMode(null);
    };
  }, [previewAppearanceMode]);

  async function saveAppearanceMode(nextMode: AppearanceMode) {
    if (!session?.access_token) {
      return;
    }

    startTransition(async () => {
      try {
        const updatedMe = await updateMe(session.access_token, {
          appearance_mode: nextMode,
        });
        replaceMe(updatedMe);
        setMessage("Theme updated.");
      } catch (saveError) {
        setAppearanceMode(me?.profile.appearance_mode ?? "dark");
        setError(saveError instanceof Error ? saveError.message : "Unable to update settings.");
      }
    });
  }

  function handleSaveAccount() {
    if (!session?.access_token) {
      return;
    }
    setMessage(null);
    setError(null);

    startTransition(async () => {
      try {
        const updatedMe = await updateMe(session.access_token, {
          full_name: fullName,
          athlete_timezone: detectDeviceTimeZone() || me?.profile.athlete_timezone || "",
          appearance_mode: appearanceMode,
          avatar_url: isSafeAvatarImageUrl(avatarUrl) ? avatarUrl.trim() : null,
        });
        replaceMe(updatedMe);
        setMessage("Account settings updated.");
      } catch (saveError) {
        setError(saveError instanceof Error ? saveError.message : "Unable to update settings.");
      }
    });
  }

  function handleUsernameSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!session?.access_token) return;

    setUsernameError(null);
    setUsernameMessage(null);

    const next = usernameDraft.trim().toLowerCase();
    if (next === currentUsername.toLowerCase()) {
      setUsernameError("That is already your username.");
      return;
    }
    const validationError = validateUsernameClient(next);
    if (validationError) {
      setUsernameError(validationError);
      return;
    }
    if (usernameRemaining <= 0) {
      setUsernameError(
        nextAvailableLabel
          ? `Limit reached. You can change again on ${nextAvailableLabel}.`
          : `Limit reached. You can change your username up to ${usernameMax} times every ${usernameWindowDays} days.`,
      );
      return;
    }

    startUsernameTransition(async () => {
      try {
        const updated = await changeUsername(session.access_token, { username: next });
        replaceMe(updated);
        setUsernameMessage(currentUsername ? "Username updated." : "Username set.");
      } catch (err) {
        if (err instanceof ApiError) {
          setUsernameError(err.message);
        } else {
          setUsernameError(err instanceof Error ? err.message : "Unable to update username.");
        }
      }
    });
  }

  function handlePasswordSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setPasswordError(null);
    setPasswordMessage(null);

    if (!currentPassword) {
      setPasswordError("Enter your current password.");
      return;
    }
    if (!newPassword || newPassword.length < 8) {
      setPasswordError("New password must be at least 8 characters.");
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordError("New password and confirmation do not match.");
      return;
    }
    if (!passwordStrength.isAcceptable) {
      setPasswordError(passwordStrength.feedback || "Pick a stronger password.");
      return;
    }
    if (newPassword === currentPassword) {
      setPasswordError("New password must be different from your current password.");
      return;
    }
    const email = me?.profile.email;
    if (!email) {
      setPasswordError("Your account email is unavailable. Reload and try again.");
      return;
    }

    startPasswordTransition(async () => {
      let client;
      try {
        client = getSupabaseBrowserClient();
      } catch (clientError) {
        setPasswordError(clientError instanceof Error ? clientError.message : "Auth client unavailable.");
        return;
      }

      const { error: reauthError } = await client.auth.signInWithPassword({
        email,
        password: currentPassword,
      });
      if (reauthError) {
        setPasswordError("Current password is incorrect.");
        return;
      }

      const { error: updateError } = await client.auth.updateUser({ password: newPassword });
      if (updateError) {
        setPasswordError(updateError.message);
        return;
      }

      setCurrentPassword("");
      setNewPassword("");
      setConfirmPassword("");
      setPasswordMessage("Password updated.");
    });
  }

  function handleFileChange(event: React.ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file) return;
    if (file.size > MAX_AVATAR_FILE_BYTES) {
      setError("Image must be smaller than 5 MB. Please choose a smaller file.");
      if (fileInputRef.current) fileInputRef.current.value = "";
      return;
    }
    const reader = new FileReader();
    reader.onload = (e) => {
      const dataUrl = e.target?.result;
      if (typeof dataUrl === "string") {
        setAvatarUrl(dataUrl);
        setUrlInputValue("");
        setError(null);
      }
    };
    reader.onerror = () => {
      setError("Failed to load image. Please try a different file.");
      if (fileInputRef.current) fileInputRef.current.value = "";
    };
    reader.readAsDataURL(file);
  }

  function handleRemoveAvatar() {
    setAvatarUrl("");
    setUrlInputValue("");
    if (fileInputRef.current) {
      fileInputRef.current.value = "";
    }
  }

  function updateNotification(key: NotificationKey, checked: boolean) {
    setNotifications((current) => {
      const next = { ...current, [key]: checked };
      writeLocalJson(NOTIFICATION_STORAGE_KEY, next);
      return next;
    });
  }

  function updateProgrammeControls(next: ProgrammeControls) {
    setProgrammeControls(next);
    writeLocalJson(PROGRAMME_CONTROLS_STORAGE_KEY, next);
  }

  function updateAdminTemplate(key: keyof AdminTemplateDraft, value: string) {
    setAdminTemplates((current) => {
      const next = { ...current, [key]: value };
      writeLocalJson(ADMIN_TEMPLATES_STORAGE_KEY, next);
      return next;
    });
  }

  const usernameChangedFromCurrent =
    usernameDraft.trim().toLowerCase() !== currentUsername.toLowerCase() && usernameDraft.trim().length > 0;
  const usernameSubmitDisabled = isUsernamePending || !usernameChangedFromCurrent || usernameRemaining <= 0;

  function renderAvatarEditor() {
    return (
      <>
        <input
          ref={fileInputRef}
          type="file"
          accept="image/*"
          className="avatar-file-input"
          aria-label="Upload profile photo"
          onChange={handleFileChange}
        />

        <div className="avatar-editor-row">
          <button
            type="button"
            className="avatar-upload-trigger"
            aria-label="Choose profile photo"
            onClick={() => fileInputRef.current?.click()}
          >
            <div className="avatar-upload-circle">
              {isSafeAvatarImageUrl(avatarUrl) ? (
                <img src={avatarUrl.trim()} alt="Profile" className="avatar-preview-img" />
              ) : (
                <span className="avatar-preview-initials">{initials}</span>
              )}
              <div className="avatar-upload-overlay" aria-hidden="true">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                  <path
                    d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                  <circle
                    cx="12"
                    cy="13"
                    r="4"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                  />
                </svg>
              </div>
            </div>
          </button>

          <div className="avatar-editor-actions">
            <button type="button" className="secondary-button avatar-upload-btn" onClick={() => fileInputRef.current?.click()}>
              {avatarUrl.trim() && isSafeAvatarImageUrl(avatarUrl.trim()) ? "Change photo" : "Upload photo"}
            </button>

            {avatarUrl.trim() && isSafeAvatarImageUrl(avatarUrl.trim()) ? (
              <button type="button" className="ghost-button danger-button" onClick={handleRemoveAvatar}>
                Remove
              </button>
            ) : null}

            <div className="field avatar-url-field">
              <label htmlFor="settingsAvatarUrl">Or paste image URL</label>
              <input
                id="settingsAvatarUrl"
                type="url"
                value={urlInputValue}
                onChange={(event) => {
                  setUrlInputValue(event.target.value);
                  setAvatarUrl(event.target.value);
                }}
                maxLength={AVATAR_URL_MAX}
                placeholder="https://example.com/photo.jpg"
              />
            </div>
          </div>
        </div>
      </>
    );
  }

  function renderAccountControls() {
    return (
      <>
        <div className="form-grid settings-identity-grid">
          <div className="field">
            <label htmlFor="settingsFullName">Name</label>
            <input
              id="settingsFullName"
              name="name"
              autoComplete="name"
              value={fullName}
              onChange={(event) => setFullName(event.target.value)}
              maxLength={ATHLETE_FULL_NAME_MAX}
            />
          </div>
          <div className="field">
            <label>Email</label>
            <div className="readonly-field">{me?.profile.email || "Unavailable"}</div>
          </div>
        </div>

        <form className="settings-subsection" onSubmit={handleUsernameSubmit}>
          <div className="settings-subsection-header">
            <h3 className="settings-subsection-title">Username</h3>
            <span
              className={`badge ${usernameRemaining > 0 ? "status-badge-neutral" : "status-badge-danger"}`}
              aria-live="polite"
            >
              {usernameRemaining} of {usernameMax} changes left
            </span>
          </div>

          <div className="field settings-username-field">
            <label htmlFor="settingsUsername">Handle</label>
            <div className="settings-username-input">
              <span className="settings-username-prefix" aria-hidden="true">@</span>
              <input
                id="settingsUsername"
                name="username"
                autoComplete="username"
                value={usernameDraft}
                onChange={(event) => {
                  setUsernameDraft(event.target.value);
                  setUsernameError(null);
                  setUsernameMessage(null);
                }}
                placeholder="your-fight-handle"
                minLength={USERNAME_MIN}
                maxLength={USERNAME_MAX}
                spellCheck={false}
                autoCapitalize="off"
              />
            </div>
            {usernameRemaining === 0 && nextAvailableLabel ? (
              <p className="warning-text">Next change available on {nextAvailableLabel}.</p>
            ) : null}
            {usernameError ? <p className="error-text">{usernameError}</p> : null}
            {usernameMessage ? <p className="success-text">{usernameMessage}</p> : null}
          </div>

          <div className="form-actions settings-subsection-actions">
            <button type="submit" className="cta" disabled={usernameSubmitDisabled}>
              {isUsernamePending ? "Saving..." : currentUsername ? "Update username" : "Set username"}
            </button>
            {currentUsername && usernameDraft.trim().toLowerCase() !== currentUsername.toLowerCase() ? (
              <button
                type="button"
                className="ghost-button"
                onClick={() => {
                  setUsernameDraft(currentUsername);
                  setUsernameError(null);
                  setUsernameMessage(null);
                }}
              >
                Cancel
              </button>
            ) : null}
          </div>
        </form>

        <form className="settings-subsection" onSubmit={handlePasswordSubmit}>
          <div className="settings-subsection-header">
            <h3 className="settings-subsection-title">Password</h3>
            <button
              type="button"
              className="password-toggle settings-password-toggle"
              onClick={() => setShowPasswords((prev) => !prev)}
              aria-pressed={showPasswords}
            >
              {showPasswords ? "Hide" : "Show"}
            </button>
          </div>

          <div className="form-grid settings-password-grid">
            <div className="field">
              <label htmlFor="settingsCurrentPassword">Current password</label>
              <input
                id="settingsCurrentPassword"
                type={showPasswords ? "text" : "password"}
                autoComplete="current-password"
                value={currentPassword}
                onChange={(event) => setCurrentPassword(event.target.value)}
              />
            </div>
            <div className="field">
              <label htmlFor="settingsNewPassword">New password</label>
              <input
                id="settingsNewPassword"
                type={showPasswords ? "text" : "password"}
                autoComplete="new-password"
                minLength={8}
                value={newPassword}
                onChange={(event) => setNewPassword(event.target.value)}
              />
              {newPassword ? <PasswordStrengthMeter strength={passwordStrength} /> : null}
            </div>
            <div className="field">
              <label htmlFor="settingsConfirmPassword">Confirm new password</label>
              <input
                id="settingsConfirmPassword"
                type={showPasswords ? "text" : "password"}
                autoComplete="new-password"
                minLength={8}
                value={confirmPassword}
                onChange={(event) => setConfirmPassword(event.target.value)}
              />
            </div>
          </div>

          {passwordError ? <p className="error-text">{passwordError}</p> : null}
          {passwordMessage ? <p className="success-text">{passwordMessage}</p> : null}

          <div className="form-actions settings-subsection-actions">
            <button
              type="submit"
              className="cta"
              disabled={isPasswordPending || !currentPassword || !newPassword || !confirmPassword}
            >
              {isPasswordPending ? "Updating..." : "Update password"}
            </button>
            <Link href="/forgot-password" className="ghost-button">
              Forgot password?
            </Link>
          </div>
        </form>

        <div className="settings-subsection">
          <div className="settings-subsection-header">
            <h3 className="settings-subsection-title">Workspace theme</h3>
          </div>
          <div className="appearance-mode-grid" role="radiogroup" aria-label="Workspace theme">
            {APPEARANCE_OPTIONS.map((option) => {
              const isSelected = appearanceMode === option.value;
              return (
                <button
                  key={option.value}
                  type="button"
                  role="radio"
                  aria-checked={isSelected}
                  className={`appearance-mode-card ${isSelected ? "appearance-mode-card-active" : ""}`.trim()}
                  onClick={async () => {
                    if (appearanceMode === option.value || isPending) {
                      return;
                    }
                    setAppearanceMode(option.value);
                    previewAppearanceMode(option.value);
                    await saveAppearanceMode(option.value);
                  }}
                >
                  <span className={`appearance-mode-preview appearance-mode-preview-${option.value}`} aria-hidden="true">
                    <span className="appearance-mode-preview-header" />
                    <span className="appearance-mode-preview-panel" />
                    <span className="appearance-mode-preview-line" />
                    <span className="appearance-mode-preview-line appearance-mode-preview-line-short" />
                  </span>
                  <span className="appearance-mode-copy">
                    <span className="appearance-mode-title-row">
                      <span className="appearance-mode-title">{option.label}</span>
                      {isSelected ? <span className="appearance-mode-state">Selected</span> : null}
                    </span>
                    <span className="appearance-mode-description">{option.description}</span>
                  </span>
                </button>
              );
            })}
          </div>
        </div>
      </>
    );
  }

  function renderAthleteSettings() {
    return (
      <div className="settings-stack athlete-motion-slot athlete-motion-main">
        <article id="account" className="step-card settings-card">
          <div className="form-section-header">
            <p className="kicker">Account</p>
            <h2 className="form-section-title">Profile and sign-in</h2>
          </div>
          {renderAvatarEditor()}
          {renderAccountControls()}
        </article>

        <article id="training-profile" className="step-card settings-card">
          <div className="settings-card-header-row">
            <div className="form-section-header">
              <p className="kicker">Training Profile</p>
              <h2 className="form-section-title">Current athlete context</h2>
            </div>
            <Link href="/onboarding?mode=edit" className="cta">
              Update Training Profile
            </Link>
          </div>
          <div className="settings-profile-summary-grid">
            {trainingProfileSummary.map((item) => (
              <SettingsSummaryItem key={item.label} label={item.label} value={item.value} />
            ))}
          </div>
        </article>

        <article id="notifications" className="step-card settings-card">
          <div className="form-section-header">
            <p className="kicker">Notifications</p>
            <h2 className="form-section-title">Reminders and messages</h2>
          </div>
          <div className="settings-toggle-list">
            {NOTIFICATION_ROWS.map((row) => (
              <label key={row.key} className="settings-toggle-row">
                <span>
                  <span className="settings-toggle-title">{row.title}</span>
                  <span className="settings-toggle-detail">{row.detail}</span>
                </span>
                <input
                  type="checkbox"
                  checked={notifications[row.key]}
                  onChange={(event) => updateNotification(row.key, event.target.checked)}
                />
              </label>
            ))}
          </div>
        </article>

        <article id="subscription" className="step-card settings-card">
          <div className="form-section-header">
            <p className="kicker">Subscription</p>
            <h2 className="form-section-title">Plan and billing access</h2>
          </div>
          <div className="settings-profile-summary-grid">
            <SettingsSummaryItem label="Current plan" value="Beta athlete access" />
            <SettingsSummaryItem label="Payment method" value="Not connected" />
            <SettingsSummaryItem label="Invoices" value="No invoices yet" />
          </div>
          <p className="settings-coming-soon">Billing controls will be available after subscriptions launch.</p>
        </article>

        <article id="privacy" className="step-card settings-card">
          <div className="form-section-header">
            <p className="kicker">Privacy</p>
            <h2 className="form-section-title">Data and consent</h2>
          </div>
          <div className="settings-profile-summary-grid">
            <SettingsSummaryItem label="Consent/data sharing" value="Account required data only" />
            <SettingsSummaryItem label="Last profile update" value={lastUpdatedLabel} />
            <SettingsSummaryItem label="Detected time zone" value={detectedTimeZone} />
          </div>
          <div className="plan-summary-actions settings-action-row">
            <button type="button" className="ghost-button" onClick={() => void signOut()}>
              Sign out
            </button>
          </div>
          <p className="settings-coming-soon">Data export and account deletion controls will be available from Privacy after launch.</p>
        </article>
      </div>
    );
  }

  function renderAdminSettings() {
    return (
      <div className="settings-stack athlete-motion-slot athlete-motion-main">
        <article id="admin-account" className="step-card settings-card">
          <div className="form-section-header">
            <p className="kicker">Admin Account</p>
            <h2 className="form-section-title">Profile and sign-in</h2>
          </div>
          {renderAvatarEditor()}
          {renderAccountControls()}
        </article>

        <article id="organisation" className="step-card settings-card">
          <div className="form-section-header">
            <p className="kicker">Organisation</p>
            <h2 className="form-section-title">Branding and contact defaults</h2>
          </div>
          <div className="settings-profile-summary-grid">
            <SettingsSummaryItem label="Brand name" value="Not connected" />
            <SettingsSummaryItem label="Logo" value="Not connected" />
            <SettingsSummaryItem label="Contact email" value="Not connected" />
          </div>
          <p className="settings-coming-soon">Organisation settings will appear here once backend organisation records are connected.</p>
        </article>

        <article id="coaches-roles" className="step-card settings-card">
          <div className="form-section-header">
            <p className="kicker">Coaches & Roles</p>
            <h2 className="form-section-title">Access control</h2>
          </div>
          <div className="settings-profile-summary-grid">
            <SettingsSummaryItem label="Primary admin" value={me?.profile.email || "Unavailable"} />
            <SettingsSummaryItem label="Role" value="Admin" />
            <SettingsSummaryItem label="Coach seats" value="Not configured" />
          </div>
          <p className="settings-coming-soon">Coach invites and role permissions will be available after team management is connected.</p>
        </article>

        <article id="programme-controls" className="step-card settings-card">
          <div className="form-section-header">
            <p className="kicker">Programme Defaults</p>
            <h2 className="form-section-title">Coming soon</h2>
          </div>
          <p className="settings-coming-soon">These controls are saved as local preview preferences only. They do not yet change backend plan generation.</p>
          <div className="settings-control-grid">
            <div className="settings-subsection">
              <div className="settings-subsection-header">
                <h3 className="settings-subsection-title">Injury filtering</h3>
                <span className="badge status-badge-neutral">{programmeControls.injuryFiltering}</span>
              </div>
              <div className="settings-segmented-control" role="radiogroup" aria-label="Injury filtering">
                {(["light", "strict"] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={programmeControls.injuryFiltering === value ? "settings-segment-active" : ""}
                    onClick={() => updateProgrammeControls({ ...programmeControls, injuryFiltering: value })}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
            <div className="settings-subsection">
              <div className="settings-subsection-header">
                <h3 className="settings-subsection-title">Fatigue adjustment</h3>
                <span className="badge status-badge-neutral">{programmeControls.fatigueAdjustment}</span>
              </div>
              <div className="settings-segmented-control" role="radiogroup" aria-label="Fatigue adjustment">
                {(["light", "strict"] as const).map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={programmeControls.fatigueAdjustment === value ? "settings-segment-active" : ""}
                    onClick={() => updateProgrammeControls({ ...programmeControls, fatigueAdjustment: value })}
                  >
                    {value}
                  </button>
                ))}
              </div>
            </div>
            <label className="settings-toggle-row">
              <span>
                <span className="settings-toggle-title">Require coach review for risky athletes</span>
                <span className="settings-toggle-detail">Manual review gate</span>
              </span>
              <input
                type="checkbox"
                checked={programmeControls.requireCoachReview}
                onChange={(event) =>
                  updateProgrammeControls({ ...programmeControls, requireCoachReview: event.target.checked })
                }
              />
            </label>
            <label className="settings-toggle-row">
              <span>
                <span className="settings-toggle-title">Auto-generate plans</span>
                <span className="settings-toggle-detail">Use latest completed intake</span>
              </span>
              <input
                type="checkbox"
                checked={programmeControls.autoGeneratePlans}
                onChange={(event) =>
                  updateProgrammeControls({ ...programmeControls, autoGeneratePlans: event.target.checked })
                }
              />
            </label>
          </div>
        </article>

        <article id="templates-billing" className="step-card settings-card">
          <div className="form-section-header">
            <p className="kicker">Templates & Billing</p>
            <h2 className="form-section-title">Reusable copy, layouts, and payments</h2>
          </div>
          <div className="form-grid settings-template-grid">
            <div className="field">
              <label htmlFor="settingsWelcomeMessage">Welcome message</label>
              <textarea
                id="settingsWelcomeMessage"
                value={adminTemplates.welcomeMessage}
                onChange={(event) => updateAdminTemplate("welcomeMessage", event.target.value)}
                rows={3}
              />
            </div>
            <div className="field">
              <label htmlFor="settingsPlanEmail">Plan email</label>
              <textarea
                id="settingsPlanEmail"
                value={adminTemplates.planEmail}
                onChange={(event) => updateAdminTemplate("planEmail", event.target.value)}
                rows={3}
              />
            </div>
            <div className="field">
              <label htmlFor="settingsCoachNotes">Coach notes</label>
              <textarea
                id="settingsCoachNotes"
                value={adminTemplates.coachNotes}
                onChange={(event) => updateAdminTemplate("coachNotes", event.target.value)}
                rows={3}
              />
            </div>
          </div>
          <p className="settings-coming-soon">Template changes are local drafts until template storage is connected.</p>
          <div className="settings-profile-summary-grid">
            <SettingsSummaryItem label="Plan" value="Admin beta access" />
            <SettingsSummaryItem label="Active users" value="Not connected" />
            <SettingsSummaryItem label="Failed payments" value="None" />
          </div>
          <div className="plan-summary-actions settings-action-row">
            <button type="button" className="ghost-button" onClick={() => void signOut()}>
              Sign out
            </button>
          </div>
          <p className="settings-coming-soon">Billing controls will be available after subscriptions launch.</p>
        </article>
      </div>
    );
  }

  if (!isMeHydrated || !me) {
    return (
      <RequireAuth>
        <section className="panel loading-card" aria-busy="true">
          <p className="kicker">Settings</p>
          <h1>Loading account settings</h1>
          <p className="muted">Restoring your saved profile.</p>
        </section>
      </RequireAuth>
    );
  }

  return (
    <RequireAuth>
      <section className="panel settings-page">
        <div className="section-heading">
          <div className="athlete-motion-slot athlete-motion-header">
            <p className="kicker">Settings</p>
            <h1>{isAdmin ? "Admin settings" : "Athlete settings"}</h1>
            <p className="muted">
              {isAdmin ? "Account access, organisation setup, coach access, programme defaults, templates, and billing." : "Account, access, profile updates, notifications, subscription, and privacy."}
            </p>
          </div>
          <div className="status-card athlete-motion-slot athlete-motion-status">
            <p className="status-label">{isAdmin ? "Admin profile" : "Profile sync"}</p>
            <h2 className="plan-summary-title">{isAdmin ? professionalStatusLabel : "Saved to account"}</h2>
            <p className="muted">{isAdmin ? me?.profile.email || "Unavailable" : `Last updated ${lastUpdatedLabel}`}</p>
          </div>
        </div>

        <SettingsNav sections={sections} isSaving={isPending} onSave={handleSaveAccount} />

        {message ? <div className="success-banner athlete-motion-slot athlete-motion-status">{message}</div> : null}
        {error ? <div className="error-banner athlete-motion-slot athlete-motion-status">{error}</div> : null}

        {isAdmin ? renderAdminSettings() : renderAthleteSettings()}

        <div className="form-actions settings-mobile-save athlete-motion-slot athlete-motion-rail">
          <button type="button" className="cta" onClick={handleSaveAccount} disabled={isPending}>
            {isPending ? "Saving..." : "Save account"}
          </button>
        </div>

        <div className="form-actions settings-desktop-save athlete-motion-slot athlete-motion-rail">
          <button type="button" className="cta" onClick={handleSaveAccount} disabled={isPending}>
            {isPending ? "Saving..." : "Save account"}
          </button>
        </div>
      </section>
    </RequireAuth>
  );
}
