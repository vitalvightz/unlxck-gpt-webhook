"use client";

import Link from "next/link";
import { useEffect, useRef, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { CustomSelect } from "@/components/custom-select";
import { updateMe } from "@/lib/api";
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

export default function SettingsPage() {
  const { me, previewAppearanceMode, replaceMe, session } = useAppSession();
  const [fullName, setFullName] = useState("");
  const [technicalStyle, setTechnicalStyle] = useState("");
  const [tacticalStyle, setTacticalStyle] = useState("");
  const [stance, setStance] = useState("");
  const [professionalStatus, setProfessionalStatus] = useState("");
  const [record, setRecord] = useState("");
  const [appearanceMode, setAppearanceMode] = useState<AppearanceMode>("dark");
  const [avatarUrl, setAvatarUrl] = useState("");
  const [urlInputValue, setUrlInputValue] = useState("");
  const [showUrlInput, setShowUrlInput] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const fileInputRef = useRef<HTMLInputElement>(null);
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
  }, [me]);

  useEffect(() => {
    return () => {
      previewAppearanceMode(null);
    };
  }, [previewAppearanceMode]);

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
        setShowUrlInput(false);
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

  return (
    <RequireAuth>
      <section className="panel">
        <div className="section-heading">
          <div className="athlete-motion-slot athlete-motion-header">
            <p className="kicker">Settings</p>
            <h1>Your athlete profile</h1>
            <p className="muted">Update the profile fields reused across onboarding and plan generation.</p>
          </div>
          <div className="status-card athlete-motion-slot athlete-motion-status">
            <p className="status-label">{isAdmin ? "Admin profile view" : "Profile sync"}</p>
            <h2 className="plan-summary-title">{isAdmin ? detectedTimeZone : "Saved to account"}</h2>
            <p className="muted">
              {isAdmin ? "Time zone stays visible here for support and debugging only." : `Last updated ${lastUpdatedLabel}`}
            </p>
          </div>
        </div>

        <div className="split-layout">
          <div className="step-main athlete-motion-slot athlete-motion-main">
            <article className="step-card">
              <div className="form-section-header">
                <p className="kicker">Appearance</p>
                <h2 className="form-section-title">Workspace theme</h2>
                <p className="muted">Preview applies immediately. Save to sync it across your account.</p>
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
                      onClick={() => {
                        setAppearanceMode(option.value);
                        previewAppearanceMode(option.value);
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

            <article className="step-card">
              <div className="form-section-header">
                <p className="kicker">Identity</p>
                <h2 className="form-section-title">Profile image</h2>
                <p className="muted">Choose a photo from your device or gallery. Tap the avatar to upload.</p>
              </div>

              <div className="avatar-upload-block">
                <input
                  ref={fileInputRef}
                  type="file"
                  accept="image/*"
                  className="avatar-file-input"
                  aria-label="Upload profile photo"
                  onChange={handleFileChange}
                />
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
                  <span className="avatar-upload-hint">
                    {avatarUrl.trim() && isSafeImageUrl(avatarUrl.trim()) ? "CHANGE PHOTO" : "UPLOAD PHOTO"}
                  </span>
                </button>

                {avatarUrl.trim() && isSafeImageUrl(avatarUrl.trim()) ? (
                  <button
                    type="button"
                    className="avatar-remove-btn"
                    onClick={handleRemoveAvatar}
                  >
                    Remove
                  </button>
                ) : null}
              </div>

              <div className="avatar-url-section">
                <button
                  type="button"
                  className="avatar-url-toggle"
                  onClick={() => setShowUrlInput((prev) => !prev)}
                >
                  {showUrlInput ? "Hide URL input" : "Use URL instead"}
                </button>
                {showUrlInput ? (
                  <div className="field avatar-url-field">
                    <label htmlFor="settingsAvatarUrl">Profile image URL</label>
                    <input
                      id="settingsAvatarUrl"
                      type="url"
                      value={urlInputValue}
                      onChange={(event) => {
                        setUrlInputValue(event.target.value);
                        setAvatarUrl(event.target.value);
                      }}
                      placeholder="https://example.com/your-photo.jpg"
                    />
                  </div>
                ) : null}
              </div>
            </article>

            <article className="step-card">
              <div className="form-section-header">
                <p className="kicker">Profile</p>
                <h2 className="form-section-title">Editable athlete details</h2>
                <p className="muted">Keep the core profile clean here so onboarding and plan generation always start with the right athlete context.</p>
              </div>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="settingsFullName">Full name</label>
                    <input
                      id="settingsFullName"
                      name="name"
                      autoComplete="name"
                      value={fullName}
                      onChange={(event) => setFullName(event.target.value)}
                    />
                </div>
                <div className="field">
                  <label>Account email</label>
                  <div className="readonly-field">{me?.profile.email || "Unavailable"}</div>
                </div>
                <div className="field">
                  <label htmlFor="settingsTechnicalStyle">Technical Style</label>
                  <CustomSelect
                    id="settingsTechnicalStyle"
                    value={technicalStyle}
                    options={TECHNICAL_STYLE_OPTIONS}
                    placeholder="Select technical style"
                    includeEmptyOption
                    onChange={(value) => setTechnicalStyle(value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="settingsTacticalStyle">Tactical Style</label>
                  <CustomSelect
                    id="settingsTacticalStyle"
                    value={tacticalStyle}
                    options={TACTICAL_STYLE_OPTIONS}
                    placeholder="Select tactical style"
                    includeEmptyOption
                    onChange={(value) => setTacticalStyle(value)}
                  />
                </div>
                <div className="field">
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
                <div className="field">
                  <label htmlFor="settingsProfessionalStatus">Professional Status</label>
                  <CustomSelect
                    id="settingsProfessionalStatus"
                    value={professionalStatus}
                    options={PROFESSIONAL_STATUS_OPTIONS}
                    placeholder="Select professional status"
                    includeEmptyOption
                    onChange={(value) => setProfessionalStatus(value)}
                  />
                </div>
                <div className="field">
                  <label htmlFor="settingsRecord">Record</label>
                  <input id="settingsRecord" value={record} onChange={(event) => setRecord(sanitizeRecordInput(event.target.value))} placeholder="5-1 or 12-2-1" inputMode="numeric" />
                  {recordHasError ? <p className="error-text">Enter record as x-x or x-x-x.</p> : null}
                </div>
                {isAdmin ? (
                  <div className="field">
                    <label>Detected time zone</label>
                    <div className="readonly-field">{detectedTimeZone}</div>
                    <p className="muted">Time is taken from the device automatically and kept here for admin context only.</p>
                  </div>
                ) : null}
              </div>
            </article>
          </div>

          <aside className="step-aside athlete-motion-slot athlete-motion-rail">
            <div className="support-panel">
              <div className="form-section-header">
                <p className="kicker">Profile snapshot</p>
                <h2 className="form-section-title">What the planner will use</h2>
              </div>
              <div className="plan-meta-grid">
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Full name</p>
                  <p className="plan-meta-value">{fullName || "Unspecified"}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Technical style</p>
                  <p className="plan-meta-value">{technicalStyleLabel}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Tactical style</p>
                  <p className="plan-meta-value">{tacticalStyleLabel}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Stance</p>
                  <p className="plan-meta-value">{stanceLabel}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Status</p>
                  <p className="plan-meta-value">{professionalStatusLabel}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Record</p>
                  <p className="plan-meta-value">{record || "Unspecified"}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Appearance</p>
                  <p className="plan-meta-value">{appearanceModeLabel}</p>
                </article>
              </div>
            </div>

            <div className="support-panel">
              <div className="form-section-header">
                <p className="kicker">Account</p>
                <h2 className="form-section-title">Profile details</h2>
              </div>
              <div className="plan-meta-grid">
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Email</p>
                  <p className="plan-meta-value">{me?.profile.email || "Unavailable"}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Role</p>
                  <p className="plan-meta-value">{me?.profile.role === "admin" ? "Admin" : "Athlete"}</p>
                </article>
                <article className="plan-meta-item">
                  <p className="plan-meta-label">Last updated</p>
                  <p className="plan-meta-value">{lastUpdatedLabel}</p>
                </article>
                {isAdmin ? (
                  <article className="plan-meta-item">
                    <p className="plan-meta-label">Time zone</p>
                    <p className="plan-meta-value">{detectedTimeZone}</p>
                  </article>
                ) : null}
              </div>
            </div>

            <div className="support-panel">
              <div className="form-section-header">
                <p className="kicker">Nutrition</p>
                <h2 className="form-section-title">Weight and readiness</h2>
              </div>
              <p className="muted">Stable physiology, fight-weight setup, and bodyweight monitoring now live in the dedicated nutrition workspace.</p>
              <div className="plan-summary-actions">
                <Link href="/nutrition" className="ghost-button">
                  Open nutrition workspace
                </Link>
              </div>
            </div>
          </aside>
        </div>

        {message ? <div className="success-banner athlete-motion-slot athlete-motion-status">{message}</div> : null}
        {error ? <div className="error-banner athlete-motion-slot athlete-motion-status">{error}</div> : null}

        <div className="form-actions athlete-motion-slot athlete-motion-rail">
          <button type="button" className="cta" onClick={handleSave} disabled={isPending}>
            {isPending ? "Saving..." : "Save settings"}
          </button>
        </div>
      </section>
    </RequireAuth>
  );
}

