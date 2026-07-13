"use client";

import { useEffect, useMemo, useState } from "react";

import { getAdminFeedbackScreenshot, listAdminFeedback } from "@/lib/api";
import { formatAppDateTime } from "@/lib/date-format";
import { formatPlanLabel } from "@/lib/plan-labels";
import type { AdminFeedbackRecord } from "@/lib/types";

const LABELS: Record<string, string> = {
  plan_usefulness: "Plan feedback",
  recommendation_fit: "Today feedback",
  recommendation_safety: "Safety feedback",
  bug_report: "Bug report",
  feature_request: "Feature request",
  safety_issue: "Safety report",
  general_feedback: "General feedback",
};

const SURFACE_LABELS: Record<string, string> = {
  plan: "Plan",
  daily_recommendation: "Daily recommendation",
  global: "Report",
};

const SAFETY_FIELDS = [
  "sharp_pain",
  "instability",
  "swelling",
  "neurological_symptoms",
  "illness_symptoms",
  "cannot_warm_into_movement",
  "worse_next_day_pain",
] as const;

type FeedbackTone = "positive" | "caution" | "safety" | "neutral";

type FeedbackGroup = {
  profileId: string;
  name: string;
  email: string;
  items: AdminFeedbackRecord[];
};

function stringValue(record: Record<string, unknown>, key: string): string {
  const value = record[key];
  return typeof value === "string" ? value.trim() : "";
}
function readable(value: string | null | undefined, fallback = "Not provided"): string {
  const label = formatPlanLabel(value);
  return label || fallback;
}

function sentenceLabel(value: string | null | undefined, fallback: string): string {
  const label = readable(value, fallback);
  return label ? `${label.charAt(0)}${label.slice(1).toLowerCase()}` : fallback;
}

function formatCompactDateTime(value: string): string {
  return formatAppDateTime(value).replace(/\s\d{4},\s/, " · ");
}

function getFeedbackSignal(item: AdminFeedbackRecord): {
  tone: FeedbackTone;
  label: string;
  title: string;
} {
  if (item.response === "unsafe" || item.priority === "safety") {
    return {
      tone: "safety",
      label: "Safety report",
      title: item.surface === "daily_recommendation" ? "Recommendation marked unsafe" : readable(item.category),
    };
  }
  if (item.response === "no") {
    return {
      tone: "caution",
      label: "Negative feedback",
      title: sentenceLabel(item.reason, "No reason selected"),
    };
  }
  if (item.response === "yes") {
    return {
      tone: "positive",
      label: "Positive feedback",
      title: item.category === "recommendation_fit" ? "Recommendation fit" : "Plan worked",
    };
  }
  return {
    tone: "neutral",
    label: "Review report",
    title: readable(item.category),
  };
}

function getOpenInjuryFlags(item: AdminFeedbackRecord): Record<string, unknown>[] {
  const openFlags = item.injury_snapshot["open_flags"];
  return Array.isArray(openFlags)
    ? openFlags.filter((flag): flag is Record<string, unknown> => Boolean(flag) && typeof flag === "object")
    : [];
}

function getReadinessChips(item: AdminFeedbackRecord): string[] {
  const readiness = item.readiness_snapshot;
  const chips: string[] = [];
  const sleep = stringValue(readiness, "sleep");
  const body = stringValue(readiness, "body");
  const pain = stringValue(readiness, "pain");
  const activeInjury = stringValue(readiness, "active_injury");
  const previousSession = stringValue(readiness, "previous_session");
  const recommendation = stringValue(readiness, "recommendation_state");

  if (sleep) chips.push(`${readable(sleep)} sleep`);
  if (body) chips.push(body === "sharp" ? "Feeling sharp" : `${readable(body)} body`);
  if (pain) chips.push(pain === "none" ? "No pain" : `${readable(pain)} pain`);
  if (activeInjury) {
    chips.push(activeInjury === "none" ? "No active injury" : `${readable(activeInjury)} injury`);
  } else if (Array.isArray(item.injury_snapshot["open_flags"])) {
    const injuryCount = getOpenInjuryFlags(item).length;
    chips.push(injuryCount ? `${injuryCount} active ${injuryCount === 1 ? "injury" : "injuries"}` : "No active injury");
  }
  if (previousSession) {
    chips.push(previousSession === "none" ? "No previous session" : `Previous session ${readable(previousSession).toLowerCase()}`);
  }
  if (recommendation) chips.push(`Recommendation: ${readable(recommendation)}`);
  return chips;
}

function getReadinessRows(item: AdminFeedbackRecord): Array<[string, string]> {
  const fields: Array<[string, string]> = [
    ["Sleep", "sleep"],
    ["Body", "body"],
    ["Pain", "pain"],
    ["Active injury", "active_injury"],
    ["Previous session", "previous_session"],
    ["Recommendation", "recommendation_state"],
  ];
  return fields.flatMap(([label, key]) => {
    const value = stringValue(item.readiness_snapshot, key);
    return value ? [[label, readable(value)] as [string, string]] : [];
  });
}

function getIntakeRows(item: AdminFeedbackRecord): Array<[string, string]> {
  const intake = item.injury_snapshot["intake"];
  if (!intake || typeof intake !== "object" || Array.isArray(intake)) return [];
  const record = intake as Record<string, unknown>;
  const rows: Array<[string, string]> = [];
  const fatigue = stringValue(record, "fatigue_level");
  const restrictions = stringValue(record, "injuries");
  const restrictionLevel = stringValue(record, "training_restriction_level");
  const availability = record.training_availability;
  if (fatigue) rows.push(["Fatigue", readable(fatigue)]);
  if (restrictions) rows.push(["Restrictions", restrictions]);
  if (restrictionLevel) rows.push(["Restriction level", readable(restrictionLevel)]);
  if (Array.isArray(availability) && availability.length) {
    rows.push(["Training days", availability.filter((value): value is string => typeof value === "string").join(", ")]);
  }
  return rows;
}

function getSafetyFlags(item: AdminFeedbackRecord): string[] {
  return SAFETY_FIELDS.filter((field) => item.readiness_snapshot[field] === true).map((field) => readable(field));
}

function parseDevice(technical: Record<string, unknown>): string {
  const userAgent = stringValue(technical, "user_agent");
  const platform = stringValue(technical, "device_platform").replaceAll('"', "");
  if (/iPhone/i.test(userAgent)) return "iPhone";
  if (/iPad/i.test(userAgent)) return "iPad";
  if (/Android/i.test(userAgent) || /Android/i.test(platform)) return "Android";
  if (/Windows/i.test(platform) || /Windows/i.test(userAgent)) return "Windows";
  if (/macOS|Mac/i.test(platform) || /Macintosh/i.test(userAgent)) return "Mac";
  if (/Linux/i.test(platform) || /Linux/i.test(userAgent)) return "Linux";
  return platform || "Unknown device";
}

function parseBrowser(technical: Record<string, unknown>): string {
  const brands = stringValue(technical, "browser_brands");
  const userAgent = stringValue(technical, "user_agent");
  const brandNames = Array.from(brands.matchAll(/"([^"]+)";v="[^"]+"/g), (match) => match[1])
    .filter((brand) => !/not.?a.?brand/i.test(brand));
  const preferredBrand = brandNames.find((brand) => /Edge|Chrome|Chromium|Opera/i.test(brand));
  if (preferredBrand) {
    if (/Edge/i.test(preferredBrand)) return "Edge";
    if (/Chrome/i.test(preferredBrand)) return "Chrome";
    if (/Chromium/i.test(preferredBrand)) return "Chromium";
    if (/Opera/i.test(preferredBrand)) return "Opera";
  }
  if (/Edg(?:A|iOS)?\//i.test(userAgent)) return "Edge";
  if (/CriOS\/|Chrome\//i.test(userAgent)) return "Chrome";
  if (/FxiOS\/|Firefox\//i.test(userAgent)) return "Firefox";
  if (/Safari\//i.test(userAgent) && !/Chrome|Chromium|CriOS|Edg/i.test(userAgent)) return "Safari";
  return brandNames[0] || "Unknown browser";
}

function groupFeedback(feedback: AdminFeedbackRecord[]): FeedbackGroup[] {
  const groups = new Map<string, FeedbackGroup>();
  for (const item of feedback) {
    const key = item.submitted_by_profile_id || item.submitter_email || item.id;
    const group = groups.get(key);
    if (group) {
      group.items.push(item);
    } else {
      groups.set(key, {
        profileId: item.submitted_by_profile_id,
        name: item.submitter_name || "Authenticated user",
        email: item.submitter_email || "Email unavailable",
        items: [item],
      });
    }
  }
  return Array.from(groups.values());
}

function DetailRows({ rows }: { rows: Array<[string, string]> }) {
  if (!rows.length) return null;
  return (
    <dl className="admin-feedback-detail-list">
      {rows.map(([label, value]) => (
        <div key={label} className="admin-feedback-detail-row">
          <dt>{label}</dt>
          <dd>{value}</dd>
        </div>
      ))}
    </dl>
  );
}

function CopyIdButton({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  return (
    <button type="button" className="admin-feedback-copy" onClick={() => void copy()}>
      {copied ? "Copied" : `Copy ${label}`}
    </button>
  );
}

function FeedbackItem({
  item,
  screenshotUrl,
  screenshotLoading,
  screenshotError,
  onLoadScreenshot,
}: {
  item: AdminFeedbackRecord;
  screenshotUrl?: string;
  screenshotLoading: boolean;
  screenshotError: boolean;
  onLoadScreenshot: () => void;
}) {
  const signal = getFeedbackSignal(item);
  const readinessChips = getReadinessChips(item);
  const readinessRows = getReadinessRows(item);
  const intakeRows = getIntakeRows(item);
  const safetyFlags = getSafetyFlags(item);
  const injuryFlags = getOpenInjuryFlags(item);
  const technical = item.technical_context;
  const pagePath = stringValue(technical, "referer_path") || "Unknown page";
  const language = stringValue(technical, "language").split(",")[0] || "Unknown";
  const hasCapturedContext = readinessRows.length > 0 || intakeRows.length > 0 || injuryFlags.length > 0;
  const responseToken = item.response === "yes"
    ? "POSITIVE"
    : item.response === "no"
      ? "NEGATIVE"
      : item.response?.toUpperCase() || "REPORT";

  return (
    <article className="admin-feedback-row" data-tone={signal.tone} data-priority={item.priority}>
      <div className="admin-feedback-heading">
        <p className="kicker">{LABELS[item.category] ?? readable(item.category)}</p>
        <span className="admin-feedback-surface">{SURFACE_LABELS[item.surface] ?? readable(item.surface)}</span>
      </div>

      <div className="admin-feedback-signal">
        <span className="admin-feedback-response" data-tone={signal.tone}>{responseToken}</span>
        <div>
          <p className="admin-feedback-signal-label">{signal.label}</p>
          <h4>{signal.title}</h4>
        </div>
      </div>

      <p className="admin-feedback-meta-line">
        <span>{item.camp_phase || "Phase not set"}</span>
        <span aria-hidden="true">·</span>
        <time dateTime={item.created_at}>{formatCompactDateTime(item.created_at)}</time>
      </p>

      <p className={`admin-feedback-comment${item.comment ? "" : " admin-feedback-comment-empty"}`}>
        {item.comment || "No written comment"}
      </p>

      <div className="admin-feedback-context-strip" aria-label="Captured readiness context">
        {readinessChips.map((chip) => <span key={chip}>{chip}</span>)}
      </div>

      <div className="admin-feedback-actions">
        {item.plan_id ? <a href={`/plans/${item.plan_id}`}>Open plan</a> : null}
        <a href={`/admin/athletes/${item.submitted_by_profile_id}`}>Open athlete</a>

        <details className="admin-feedback-disclosure">
          <summary>{item.today_checkin_id ? "Open check-in" : "View context"}</summary>
          <div className="admin-feedback-disclosure-body">
            <div>
              <p className="kicker">Readiness</p>
              {hasCapturedContext ? (
                <>
                  <DetailRows rows={[...readinessRows, ...intakeRows]} />
                  {safetyFlags.length ? <p className="admin-feedback-context-alert">Flags: {safetyFlags.join(" · ")}</p> : null}
                </>
              ) : <p className="muted">No readiness snapshot was captured.</p>}
            </div>
            {injuryFlags.length ? (
              <div>
                <p className="kicker">Active injuries</p>
                <ul className="admin-feedback-injury-list">
                  {injuryFlags.map((flag, index) => (
                    <li key={stringValue(flag, "id") || `${stringValue(flag, "body_area")}-${index}`}>
                      <strong>{readable(stringValue(flag, "body_area"), "Injury")}</strong>
                      <span>{[stringValue(flag, "severity"), stringValue(flag, "status")].filter(Boolean).map((value) => readable(value)).join(" · ")}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ) : null}
          </div>
        </details>

        <details className="admin-feedback-disclosure admin-feedback-technical">
          <summary>Technical details</summary>
          <div className="admin-feedback-disclosure-body">
            <DetailRows rows={[
              ["Page", pagePath],
              ["Device", parseDevice(technical)],
              ["Browser", parseBrowser(technical)],
              ["App", item.app_version || "Unknown"],
              ["Language", language],
            ]} />
            <div className="admin-feedback-copy-actions">
              <CopyIdButton label="feedback ID" value={item.id} />
              {item.plan_id ? <CopyIdButton label="plan ID" value={item.plan_id} /> : null}
              {item.today_checkin_id ? <CopyIdButton label="check-in ID" value={item.today_checkin_id} /> : null}
            </div>
          </div>
        </details>

        {item.has_screenshot ? (
          screenshotUrl ? (
            <a href={screenshotUrl} target="_blank" rel="noreferrer">Open screenshot</a>
          ) : (
            <button type="button" className="feedback-link" onClick={onLoadScreenshot} disabled={screenshotLoading}>
              {screenshotLoading ? "Preparing screenshot…" : "View screenshot"}
            </button>
          )
        ) : null}
      </div>
      {item.contact_allowed ? <p className="admin-feedback-contact">Athlete permits follow-up</p> : null}
      {screenshotError ? <p className="error-text" role="alert">Screenshot could not be opened. Try again.</p> : null}
    </article>
  );
}

export function AdminFeedbackPanel({ token, reloadKey }: { token: string; reloadKey: number }) {
  return <AdminFeedbackLoader key={token} token={token} reloadKey={reloadKey} />;
}

function AdminFeedbackLoader({ token, reloadKey }: { token: string; reloadKey: number }) {
  const [feedback, setFeedback] = useState<AdminFeedbackRecord[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [retryKey, setRetryKey] = useState(0);
  const [screenshotUrls, setScreenshotUrls] = useState<Record<string, string>>({});
  const [screenshotLoadingId, setScreenshotLoadingId] = useState<string | null>(null);
  const [screenshotErrorId, setScreenshotErrorId] = useState<string | null>(null);
  const groups = useMemo(() => groupFeedback(feedback), [feedback]);

  async function loadScreenshot(feedbackId: string) {
    setScreenshotLoadingId(feedbackId);
    setScreenshotErrorId(null);
    try {
      const access = await getAdminFeedbackScreenshot(token, feedbackId);
      setScreenshotUrls((current) => ({ ...current, [feedbackId]: access.url }));
    } catch {
      setScreenshotErrorId(feedbackId);
    } finally {
      setScreenshotLoadingId(null);
    }
  }

  function retryFeedback() {
    setLoading(true);
    setError(null);
    setRetryKey((value) => value + 1);
  }

  useEffect(() => {
    let active = true;
    void listAdminFeedback(token)
      .then((rows) => {
        if (active) {
          setFeedback(rows);
          setError(null);
        }
      })
      .catch((loadError: unknown) => {
        if (active) setError(loadError instanceof Error ? loadError.message : "Unable to load feedback.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [token, reloadKey, retryKey]);

  return (
    <article className="list-card admin-feedback-panel">
      <div className="form-section-header">
        <div>
          <p className="kicker">Athlete voice</p>
          <h2>Feedback review</h2>
          <p className="muted admin-panel-subtext">Safety reports stay pinned. Context opens only when you need it.</p>
        </div>
        <span className="badge status-badge-neutral">{loading ? "Checking" : `${feedback.length} recent`}</span>
      </div>

      {loading ? <p className="muted">Loading feedback...</p> : null}
      {!loading && error ? (
        <div className="support-panel">
          <p className="error-text">{error}</p>
          <button type="button" className="ghost-button" onClick={retryFeedback}>
            Retry feedback
          </button>
        </div>
      ) : null}
      {!loading && !error && feedback.length === 0 ? (
        <div className="support-panel support-panel-success">
          <h3 className="form-section-title">No feedback yet.</h3>
          <p className="muted">Plan, recommendation, and global reports will appear here.</p>
        </div>
      ) : null}
      {!loading && !error && feedback.length > 0 ? (
        <div className="admin-feedback-list">
          {groups.map((group) => (
            <section key={group.profileId || group.email} className="admin-feedback-group">
              <div className="admin-feedback-group-header">
                <div>
                  <h3>{group.name}</h3>
                  <p>{group.email}</p>
                </div>
                <span>{group.items.length} recent {group.items.length === 1 ? "response" : "responses"}</span>
              </div>
              <div className="admin-feedback-group-items">
                {group.items.map((item) => (
                  <FeedbackItem
                    key={item.id}
                    item={item}
                    screenshotUrl={screenshotUrls[item.id]}
                    screenshotLoading={screenshotLoadingId === item.id}
                    screenshotError={screenshotErrorId === item.id}
                    onLoadScreenshot={() => void loadScreenshot(item.id)}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
      ) : null}
    </article>
  );
}
