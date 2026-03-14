"use client";

import { useEffect, useState, useTransition } from "react";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { updateMe } from "@/lib/api";
import {
  detectDeviceLocale,
  detectDeviceTimeZone,
  getOptionLabel,
  isValidRecordFormat,
  PROFESSIONAL_STATUS_OPTIONS,
  sanitizeRecordInput,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
} from "@/lib/intake-options";

export default function SettingsPage() {
  const { me, refreshMe, session } = useAppSession();
  const [fullName, setFullName] = useState("");
  const [technicalStyle, setTechnicalStyle] = useState("");
  const [tacticalStyle, setTacticalStyle] = useState("");
  const [professionalStatus, setProfessionalStatus] = useState("");
  const [record, setRecord] = useState("");
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();
  const detectedTimeZone = detectDeviceTimeZone() || me?.profile.athlete_timezone || "Automatic";
  const recordHasError = !isValidRecordFormat(record);

  useEffect(() => {
    if (!me) {
      return;
    }
    setFullName(me.profile.full_name);
    setTechnicalStyle(me.profile.technical_style[0] ?? "");
    setTacticalStyle(me.profile.tactical_style[0] ?? "");
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
            <p className="muted">Update the profile fields that follow your account through onboarding and plan generation.</p>
          </div>
          <div className="status-card">
            <p className="status-label">Device time</p>
            <h2 className="plan-summary-title">{detectedTimeZone}</h2>
            <p className="muted">Time is taken from the device automatically for web intake flows.</p>
          </div>
        </div>

        <div className="split-layout">
          <div className="step-main">
            <article className="step-card">
              <div className="form-section-header">
                <p className="kicker">Profile</p>
                <h2 className="form-section-title">Editable athlete details</h2>
              </div>
              <div className="form-grid">
                <div className="field">
                  <label htmlFor="settingsFullName">Full name</label>
                  <input id="settingsFullName" value={fullName} onChange={(event) => setFullName(event.target.value)} />
                </div>
                <div className="field">
                  <label htmlFor="settingsTechnicalStyle">Technical Style</label>
                  <select id="settingsTechnicalStyle" value={technicalStyle} onChange={(event) => setTechnicalStyle(event.target.value)}>
                    <option value="">Select technical style</option>
                    {TECHNICAL_STYLE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="settingsTacticalStyle">Tactical Style</label>
                  <select id="settingsTacticalStyle" value={tacticalStyle} onChange={(event) => setTacticalStyle(event.target.value)}>
                    <option value="">Select tactical style</option>
                    {TACTICAL_STYLE_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="settingsProfessionalStatus">Professional Status</label>
                  <select id="settingsProfessionalStatus" value={professionalStatus} onChange={(event) => setProfessionalStatus(event.target.value)}>
                    <option value="">Select professional status</option>
                    {PROFESSIONAL_STATUS_OPTIONS.map((option) => (
                      <option key={option.value} value={option.value}>
                        {option.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="field">
                  <label htmlFor="settingsRecord">Record</label>
                  <input id="settingsRecord" value={record} onChange={(event) => setRecord(sanitizeRecordInput(event.target.value))} placeholder="5-1 or 12-2-1" inputMode="numeric" />
                  {recordHasError ? <p className="error-text">Enter record as x-x or x-x-x.</p> : null}
                </div>
                <div className="field">
                  <label>Detected time zone</label>
                  <div className="readonly-field">{detectedTimeZone}</div>
                  <p className="muted">Time is taken from the device automatically.</p>
                </div>
              </div>
            </article>
          </div>

          <aside className="step-aside">
            <div className="support-panel">
              <div className="form-section-header">
                <p className="kicker">Current selections</p>
                <h2 className="form-section-title">Account summary</h2>
              </div>
              <ul className="summary-list">
                <li>Full name: {fullName || "Unspecified"}</li>
                <li>Technical Style: {getOptionLabel(TECHNICAL_STYLE_OPTIONS, technicalStyle) || "Unspecified"}</li>
                <li>Tactical Style: {getOptionLabel(TACTICAL_STYLE_OPTIONS, tacticalStyle) || "Unspecified"}</li>
                <li>Professional Status: {getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, professionalStatus) || "Unspecified"}</li>
                <li>Record: {record || "Unspecified"}</li>
              </ul>
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
