"use client";

import { useEffect, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { CustomSelect } from "@/components/custom-select";
import { updateMe } from "@/lib/api";
import {
  detectDeviceLocale,
  detectDeviceTimeZone,
  getOptionLabel,
  isValidRecordFormat,
  PROFESSIONAL_STATUS_OPTIONS,
  sanitizeRecordInput,
  STANCE_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";

export default function SettingsPage() {
  const { me, refreshMe, session } = useAppSession();
  const [fullName, setFullName] = useState("");
  const [technicalStyle, setTechnicalStyle] = useState("");
  const [tacticalStyle, setTacticalStyle] = useState("");
  const [stance, setStance] = useState("");
  const [professionalStatus, setProfessionalStatus] = useState("");
  const [record, setRecord] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const isAdmin = me?.profile.role === "admin";
  const detectedTimeZone = detectDeviceTimeZone() || me?.profile.athlete_timezone || "Automatic";
  const recordHasError = !isValidRecordFormat(record);
  const technicalStyleLabel = getOptionLabel(TECHNICAL_STYLE_OPTIONS, technicalStyle) || "Unspecified";
  const tacticalStyleLabel = getOptionLabel(TACTICAL_STYLE_OPTIONS, tacticalStyle) || "Unspecified";
  const stanceLabel = getOptionLabel(STANCE_OPTIONS, stance) || "Unspecified";
  const professionalStatusLabel = getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, professionalStatus) || "Unspecified";
  const lastUpdatedLabel = me?.profile.updated_at ? new Date(me.profile.updated_at).toLocaleString() : "Not saved yet";

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
  }, [me]);

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
        await updateMe(session.access_token, {
          full_name: fullName,
          athlete_timezone: detectDeviceTimeZone() || me?.profile.athlete_timezone || "",
          athlete_locale: detectDeviceLocale() || me?.profile.athlete_locale || "",
          technical_style: technicalStyle ? [technicalStyle] : [],
          tactical_style: tacticalStyle ? [tacticalStyle] : [],
          stance,
          professional_status: professionalStatus,
          record,
        });
        await refreshMe();
        setMessage("Settings updated.");
      } catch (saveError) {
        setError(saveError instanceof Error ? saveError.message : "Unable to update settings.");
      }
    });
  }

  return (
    <RequireAuth>
      <section className="panel">
        <div className="section-heading">
          <div>
            <p className="kicker">Settings</p>
            <h1>Your athlete profile</h1>
            <p className="muted">Update the profile fields reused across onboarding and plan generation.</p>
          </div>
          <div className="status-card">
            <p className="status-label">{isAdmin ? "Admin profile view" : "Profile sync"}</p>
            <h2 className="plan-summary-title">{isAdmin ? detectedTimeZone : "Saved to account"}</h2>
            <p className="muted">
              {isAdmin ? "Time zone stays visible here for support and debugging only." : `Last updated ${lastUpdatedLabel}`}
            </p>
          </div>
        </div>

        <div className="split-layout">
          <div className="step-main">
            <article className="step-card">
              <div className="form-section-header">
                <p className="kicker">Profile</p>
                <h2 className="form-section-title">Editable athlete details</h2>
                <p className="muted">Keep the core profile clean here so onboarding and plan generation always start with the right athlete context.</p>
              </div>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="settingsFullName">Full name</label>
                  <input id="settingsFullName" value={fullName} onChange={(event) => setFullName(event.target.value)} />
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

          <aside className="step-aside">
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
          </aside>
        </div>

        {message ? <div className="success-banner">{message}</div> : null}
        {error ? <div className="error-banner">{error}</div> : null}

        <div className="form-actions">
          <button type="button" className="cta" onClick={handleSave} disabled={isPending}>
            {isPending ? "Saving..." : "Save settings"}
          </button>
        </div>
      </section>
    </RequireAuth>
  );
}


