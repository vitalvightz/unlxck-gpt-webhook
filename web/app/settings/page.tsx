"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { CustomSelect } from "@/components/custom-select";
import { PasswordStrengthMeter } from "@/components/password-strength-meter";
import { ApiError, changeUsername, updateMe } from "@/lib/api";
import { evaluatePasswordStrength } from "@/lib/password-strength";
import {
  detectDeviceTimeZone,
  getOptionLabel,
  isValidRecordFormat,
  PROFESSIONAL_STATUS_OPTIONS,
  sanitizeRecordInput,
  STANCE_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";
import { getSupabaseBrowserClient } from "@/lib/supabase";
import type { AppearanceMode } from "@/lib/types";

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

function isDataUrl(url: string): boolean {
  return url.startsWith("data:image/");
}

function isSafeImageUrl(url: string): boolean {
  if (isDataUrl(url)) {
    return true;
  }
  try {
    const parsed = new URL(url);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

const MAX_AVATAR_FILE_BYTES = 5 * 1024 * 1024; // 5 MB
const USERNAME_PATTERN = /^[a-z0-9](?:[a-z0-9._-]*[a-z0-9])?$/;
const USERNAME_MIN = 3;
const USERNAME_MAX = 24;
const APPEARANCE_OPTIONS: Array<{
  value: AppearanceMode;
  label: string;
  description: string;
}> = [
  {
    value: "dark",
    label: "Dark",
    description: "Original control-room contrast with a deeper red heat.",
  },
  {
    value: "light",
    label: "Light",
    description: "Paper-forward workspace with painterly red impact corners.",
  },
];

const SETTINGS_SECTIONS = [
  { id: "identity", label: "Identity" },
  { id: "security", label: "Account & security" },
  { id: "appearance", label: "Appearance" },
  { id: "athlete-profile", label: "Athlete profile" },
] as const;

function validateUsernameClient(value: string): string | null {
  const trimmed = value.trim().toLowerCase();
  if (!trimmed) {
    return "Enter a username.";
  }
  if (trimmed.length < USERNAME_MIN || trimmed.length > USERNAME_MAX) {
    return `Username must be ${USERNAME_MIN}–${USERNAME_MAX} characters.`;
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
  return date.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

export default function SettingsPage() {
  const { me, previewAppearanceMode, replaceMe, session, signOut } = useAppSession();

  const [fullName, setFullName] = useState("");
  const [technicalStyle, setTechnicalStyle] = useState("");
  const [tacticalStyle, setTacticalStyle] = useState("");
  const [stance, setStance] = useState("");
  const [professionalStatus, setProfessionalStatus] = useState("");
  const [record, setRecord] = useState("");
  const [appearanceMode, setAppearanceMode] = useState<AppearanceMode>("dark");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [urlInputValue, setUrlInputValue] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Username state
  const [usernameDraft, setUsernameDraft] = useState("");
  const [usernameError, setUsernameError] = useState<string | null>(null);
  const [usernameMessage, setUsernameMessage] = useState<string | null>(null);
  const [isUsernamePending, startUsernameTransition] = useTransition();

  // Password change state
  const [currentPassword, setCurrentPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [showPasswords, setShowPasswords] = useState(false);
  const [passwordError, setPasswordError] = useState<string | null>(null);
  const [passwordMessage, setPasswordMessage] = useState<string | null>(null);
  const [isPasswordPending, startPasswordTransition] = useTransition();

  const isAdmin = me?.profile.role === "admin";
  const detectedTimeZone = detectDeviceTimeZone() || me?.profile.athlete_timezone || "Automatic";
  const recordHasError = !isValidRecordFormat(record);
  const technicalStyleLabel = getOptionLabel(TECHNICAL_STYLE_OPTIONS, technicalStyle) || "Unspecified";
  const tacticalStyleLabel = getOptionLabel(TACTICAL_STYLE_OPTIONS, tacticalStyle) || "Unspecified";
  const stanceLabel = getOptionLabel(STANCE_OPTIONS, stance) || "Unspecified";
  const professionalStatusLabel = getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, professionalStatus) || "Unspecified";
  const appearanceModeLabel = appearanceMode === "light" ? "Light" : "Dark";
  const lastUpdatedLabel = me?.profile.updated_at ? new Date(me.profile.updated_at).toLocaleString() : "Not saved yet";
  const initials = getInitials(fullName || "Athlete");

  const currentUsername = (me?.profile.username ?? "").trim();
  const rateLimit = me?.username_rate_limit;
  const usernameRemaining = rateLimit?.remaining ?? 4;
  const usernameMax = rateLimit?.max_changes_per_window ?? 4;
  const usernameWindowDays = rateLimit?.window_days ?? 30;
  const nextAvailableLabel = formatNextAvailable(rateLimit?.next_available_at);

  const passwordStrength = useMemo(
    () => evaluatePasswordStrength(newPassword, { fullName, email: me?.profile.email ?? "" }),
    [newPassword, fullName, me?.profile.email],
  );

  useEffect(() => {
    if (!me) {
      return;
    }
    setFullName(me.profile.full_name);
    setTechnicalStyle(me.profile.technical_style[0] ?? "");
    setTacticalStyle(me.profile.tactical_style[0] ?? "");
    setStance(me.profile.stance ?? "");
    setProfessionalStatus(me.profile.professional_status);
    setRecord(me.profile.record);
    setAppearanceMode(me.profile.appearance_mode ?? "dark");
    const storedAvatar = me.profile.avatar_url ?? "";
    setAvatarUrl(storedAvatar);
    if (!isDataUrl(storedAvatar)) {
      setUrlInputValue(storedAvatar);
    }
    setUsernameDraft((me.profile.username ?? "").trim());
  }, [me]);

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
        setMessage("Background updated.");
      } catch (saveError) {
        setAppearanceMode(me?.profile.appearance_mode ?? "dark");
        setError(saveError instanceof Error ? saveError.message : "Unable to update settings.");
      }
    });
  }

  function handleSave() {
    if (!session?.access_token) {
      return;
    }
    setMessage(null);
    setError(null);
    if (!isValidRecordFormat(record)) {
      setError("Record must use x-x or x-x-x format.");
      return;
    }

    startTransition(async () => {
      try {
        const updatedMe = await updateMe(session.access_token, {
          full_name: fullName,
          athlete_timezone: detectDeviceTimeZone() || me?.profile.athlete_timezone || "",
          technical_style: technicalStyle ? [technicalStyle] : [],
          tactical_style: tacticalStyle ? [tacticalStyle] : [],
          stance,
          professional_status: professionalStatus,
          record,
          appearance_mode: appearanceMode,
          avatar_url: avatarUrl.trim() && isSafeImageUrl(avatarUrl.trim()) ? avatarUrl.trim() : null,
        });
        replaceMe(updatedMe);
        setMessage("Settings updated.");
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

  const usernameChangedFromCurrent =
    usernameDraft.trim().toLowerCase() !== currentUsername.toLowerCase() && usernameDraft.trim().length > 0;
  const usernameSubmitDisabled =
    isUsernamePending || !usernameChangedFromCurrent || usernameRemaining <= 0;

  return (
    <RequireAuth>
      <section className="panel settings-page">
        <div className="section-heading">
          <div className="athlete-motion-slot athlete-motion-header">
            <p className="kicker">Settings</p>
            <h1>Your account</h1>
            <p className="muted">Update identity, security, appearance, and athlete profile in one place.</p>
          </div>
        </div>

        <div className="settings-layout athlete-motion-slot athlete-motion-main">
          <aside className="settings-nav" aria-label="Settings sections">
            {SETTINGS_SECTIONS.map((section) => (
              <a key={section.id} href={`#${section.id}`} data-section-link={section.id}>
                {section.label}
              </a>
            ))}
          </aside>

          <div className="settings-main">
            {message ? <div className="success-banner athlete-motion-slot athlete-motion-status">{message}</div> : null}
            {error ? <div className="error-banner athlete-motion-slot athlete-motion-status">{error}</div> : null}

            <article id="identity" className="step-card settings-card">
            <div className="form-section-header">
              <p className="kicker">Identity</p>
              <h2 className="form-section-title">Profile photo & display name</h2>
              <p className="muted">Upload a photo or paste a URL. Your full name shows on plans and onboarding.</p>
            </div>

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
                  {avatarUrl.trim() && isSafeImageUrl(avatarUrl.trim()) ? (
                    <img src={avatarUrl.trim()} alt="Profile" className="avatar-preview-img" />
                  ) : (
                    <span className="avatar-preview-initials">{initials}</span>
                  )}
                  <div className="avatar-upload-overlay" aria-hidden="true">
                    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg">
                      <path d="M23 19a2 2 0 0 1-2 2H3a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h4l2-3h6l2 3h4a2 2 0 0 1 2 2z" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                      <circle cx="12" cy="13" r="4" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                    </svg>
                  </div>
                </div>
              </button>

              <div className="avatar-editor-actions">
                <button
                  type="button"
                  className="secondary-button avatar-upload-btn"
                  onClick={() => fileInputRef.current?.click()}
                >
                  {avatarUrl.trim() && isSafeImageUrl(avatarUrl.trim()) ? "Change photo" : "Upload photo"}
                </button>

                {avatarUrl.trim() && isSafeImageUrl(avatarUrl.trim()) ? (
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
                    placeholder="https://example.com/photo.jpg"
                  />
                </div>
              </div>
            </div>

            <div className="settings-card-grid">
              <div className="field settings-card-sm">
                <label htmlFor="settingsFullName">Full name</label>
                <input
                  id="settingsFullName"
                  name="name"
                  autoComplete="name"
                  value={fullName}
                  onChange={(event) => setFullName(event.target.value)}
                />
              </div>
              <div className="field settings-card-sm">
                <label>Username</label>
                <div className="readonly-field">{currentUsername ? `@${currentUsername}` : "Not set yet"}</div>
                <p className="muted">Manage your username in the Account & Security section below.</p>
              </div>
            </div>
          </article>

          <article id="security" className="step-card settings-card">
            <div className="form-section-header">
              <p className="kicker">Account & security</p>
              <h2 className="form-section-title">Email, username, and password</h2>
              <p className="muted">Your email is locked to the account. Username is rate-limited, password is changed securely.</p>
            </div>

            <div className="settings-card-grid">
              <div className="field settings-card-md">
                <label>Account email</label>
                <div className="readonly-field">{me?.profile.email || "Unavailable"}</div>
                <p className="muted">Contact support to change the email on file.</p>
              </div>
              <div className="field settings-card-sm">
                <label>Role</label>
                <div className="readonly-field">{isAdmin ? "Admin" : "Athlete"}</div>
              </div>
              <div className="field settings-card-sm">
                <label>{isAdmin ? "Admin status" : "Profile sync"}</label>
                <div className="readonly-field">{isAdmin ? detectedTimeZone : "Saved to account"}</div>
                <p className="muted">
                  {isAdmin ? "Time zone captured for support context." : `Last updated ${lastUpdatedLabel}`}
                </p>
              </div>
            </div>

            <form className="settings-subsection" onSubmit={handleUsernameSubmit}>
              <div className="settings-subsection-header">
                <h3 className="settings-subsection-title">Username</h3>
                <span
                  className={`badge ${usernameRemaining > 0 ? "status-badge-neutral" : "status-badge-danger"}`}
                  aria-live="polite"
                >
                  {usernameRemaining} of {usernameMax} changes left ({usernameWindowDays}-day window)
                </span>
              </div>

              <div className="field settings-username-field">
                <label htmlFor="settingsUsername">Choose a username</label>
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
                <p className="muted">
                  {USERNAME_MIN}–{USERNAME_MAX} characters. Lowercase letters, digits, dots, dashes, underscores.
                </p>
                {usernameRemaining === 0 && nextAvailableLabel ? (
                  <p className="warning-text">Username change limit reached. Next change available on {nextAvailableLabel}.</p>
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

              <div className="settings-card-grid">
                <div className="field settings-card-sm">
                  <label htmlFor="settingsCurrentPassword">Current password</label>
                  <input
                    id="settingsCurrentPassword"
                    type={showPasswords ? "text" : "password"}
                    autoComplete="current-password"
                    value={currentPassword}
                    onChange={(event) => setCurrentPassword(event.target.value)}
                  />
                </div>
                <div className="field settings-card-sm">
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
                <div className="field settings-card-sm">
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
          </article>

          <article id="appearance" className="step-card settings-card">
            <div className="form-section-header">
              <p className="kicker">Appearance</p>
              <h2 className="form-section-title">Workspace theme</h2>
              <p className="muted">Preview applies immediately and saves as soon as you pick a background.</p>
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
                    <span
                      className={`appearance-mode-preview appearance-mode-preview-${option.value}`}
                      aria-hidden="true"
                    >
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
          </article>

          <article id="athlete-profile" className="step-card settings-card">
            <div className="form-section-header">
              <p className="kicker">Athlete profile</p>
              <h2 className="form-section-title">Editable athlete details</h2>
              <p className="muted">Keep this clean so onboarding and plan generation start with the right context.</p>
            </div>
            <div className="settings-card-grid">
              <div className="field settings-card-sm">
                <label htmlFor="settingsTechnicalStyle">Technical style</label>
                <CustomSelect
                  id="settingsTechnicalStyle"
                  value={technicalStyle}
                  options={TECHNICAL_STYLE_OPTIONS}
                  placeholder="Select technical style"
                  includeEmptyOption
                  onChange={(value) => setTechnicalStyle(value)}
                />
              </div>
              <div className="field settings-card-sm">
                <label htmlFor="settingsTacticalStyle">Tactical style</label>
                <CustomSelect
                  id="settingsTacticalStyle"
                  value={tacticalStyle}
                  options={TACTICAL_STYLE_OPTIONS}
                  placeholder="Select tactical style"
                  includeEmptyOption
                  onChange={(value) => setTacticalStyle(value)}
                />
              </div>
              <div className="field settings-card-sm">
                <label htmlFor="settingsStance">Stance</label>
                <CustomSelect
                  id="settingsStance"
                  value={stance}
                  options={STANCE_OPTIONS}
                  placeholder="Select stance"
                  includeEmptyOption
                  onChange={(value) => setStance(value)}
                />
              </div>
              <div className="field settings-card-sm">
                <label htmlFor="settingsProfessionalStatus">Professional status</label>
                <CustomSelect
                  id="settingsProfessionalStatus"
                  value={professionalStatus}
                  options={PROFESSIONAL_STATUS_OPTIONS}
                  placeholder="Select professional status"
                  includeEmptyOption
                  onChange={(value) => setProfessionalStatus(value)}
                />
              </div>
              <div className="field settings-card-sm">
                <label htmlFor="settingsRecord">Record</label>
                <input
                  id="settingsRecord"
                  value={record}
                  onChange={(event) => setRecord(sanitizeRecordInput(event.target.value))}
                  placeholder="5-1 or 12-2-1"
                  inputMode="numeric"
                />
                {recordHasError ? <p className="error-text">Enter record as x-x or x-x-x.</p> : null}
              </div>
              {isAdmin ? (
                <div className="field settings-card-sm">
                  <label>Detected time zone</label>
                  <div className="readonly-field">{detectedTimeZone}</div>
                  <p className="muted">Captured from the device for admin context only.</p>
                </div>
              ) : null}
            </div>

            <p className="settings-summary-line" aria-label="Profile snapshot">
              {fullName || "—"} · {currentUsername ? `@${currentUsername}` : "Not set yet"} · {technicalStyleLabel} / {tacticalStyleLabel} · {stanceLabel} · {professionalStatusLabel} · {record || "—"} · {appearanceModeLabel}
            </p>
          </article>

          <aside className="support-panel settings-utility-card">
            <div className="form-section-header">
              <p className="kicker">Nutrition</p>
              <h2 className="form-section-title">Weight and readiness</h2>
            </div>
            <p className="muted">Stable physiology, fight-weight setup, and bodyweight monitoring now live in the dedicated nutrition workspace.</p>
            <div className="plan-summary-actions">
              <Link href="/nutrition" className="ghost-button">
                Open nutrition workspace
              </Link>
              <button type="button" className="ghost-button danger-button" onClick={() => void signOut()}>
                Sign out
              </button>
            </div>
          </aside>

            <div className="form-actions settings-desktop-save athlete-motion-slot athlete-motion-rail">
              <button type="button" className="cta" onClick={handleSave} disabled={isPending}>
                {isPending ? "Saving..." : "Save settings"}
              </button>
            </div>
          </div>
        </div>

        <div className="form-actions settings-mobile-save athlete-motion-slot athlete-motion-rail">
          <button type="button" className="cta" onClick={handleSave} disabled={isPending}>
            {isPending ? "Saving..." : "Save settings"}
          </button>
        </div>
      </section>
    </RequireAuth>
  );
}
