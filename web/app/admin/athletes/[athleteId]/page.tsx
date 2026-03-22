"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";

import { RequireAuth } from "@/components/auth-guard";
import { useAppSession } from "@/components/auth-provider";
import { getAdminAthlete } from "@/lib/api";
import {
  EQUIPMENT_ACCESS_OPTIONS,
  KEY_GOAL_OPTIONS,
  PROFESSIONAL_STATUS_OPTIONS,
  STANCE_OPTIONS,
  TACTICAL_STYLE_OPTIONS,
  TECHNICAL_STYLE_OPTIONS,
  TRAINING_AVAILABILITY_OPTIONS,
  WEAK_AREA_OPTIONS,
} from "@/lib/intake-options";
import type { AdminAthleteRecord, PlanRequest } from "@/lib/types";

const FATIGUE_LEVEL_OPTIONS = [
  { value: "low", label: "Low" },
  { value: "moderate", label: "Moderate" },
  { value: "high", label: "High" },
];

function getOptionLabel(options: { value: string; label: string }[], value: string): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

function getOptionLabels(options: { value: string; label: string }[], values: string[]): string[] {
  return values.map((value) => getOptionLabel(options, value)).filter(Boolean);
}

function formatList(values: string[], empty = "Not provided"): string {
  return values.length ? values.join(", ") : empty;
}

function formatValue(value: string | number | null | undefined, empty = "Not provided"): string {
  if (value == null) {
    return empty;
  }
  const normalized = String(value).trim();
  return normalized ? normalized : empty;
}

function formatDate(value: string | null | undefined, opts?: Intl.DateTimeFormatOptions): string {
  if (!value) {
    return "Not available";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "Not available";
  }
  return date.toLocaleString(undefined, opts);
}

function formatMeasurement(value: number | null | undefined, unit: string): string {
  return value == null ? "Not provided" : `${value} ${unit}`;
}

function DetailCard({ label, value, accent }: { label: string; value: string; accent?: string }) {
  return (
    <article className="plan-meta-item athlete-profile-detail-card">
      <p className="plan-meta-label">{label}</p>
      <p className={`plan-meta-value${accent ? ` ${accent}` : ""}`}>{value}</p>
    </article>
  );
}

export default function AdminAthletePage() {
  const { session } = useAppSession();
  const params = useParams();
  const athleteId = typeof params?.athleteId === "string" ? params.athleteId : null;
  const [athlete, setAthlete] = useState<AdminAthleteRecord | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!session?.access_token || !athleteId) {
      return;
    }
    getAdminAthlete(session.access_token, athleteId)
      .then(setAthlete)
      .catch((athleteError) => {
        setError(athleteError instanceof Error ? athleteError.message : "Unable to load athlete profile.");
      });
  }, [athleteId, session?.access_token]);

  const latestIntake = useMemo<PlanRequest | null>(() => {
    if (!athlete?.latest_intake) {
      return null;
    }
    return athlete.latest_intake;
  }, [athlete]);

  const profileCards = useMemo(() => {
    if (!athlete) {
      return [] as Array<{ label: string; value: string }>;
    }

    return [
      { label: "Full name", value: formatValue(athlete.full_name) },
      { label: "Email", value: formatValue(athlete.email) },
      { label: "Role", value: athlete.role === "admin" ? "Admin" : "Athlete" },
      { label: "Technical style", value: formatList(getOptionLabels(TECHNICAL_STYLE_OPTIONS, athlete.technical_style)) },
      { label: "Tactical style", value: formatList(getOptionLabels(TACTICAL_STYLE_OPTIONS, athlete.tactical_style)) },
      { label: "Stance", value: formatValue(getOptionLabel(STANCE_OPTIONS, athlete.stance || "")) },
      {
        label: "Professional status",
        value: formatValue(getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, athlete.professional_status || "")),
      },
      { label: "Record", value: formatValue(athlete.record) },
      { label: "Timezone", value: formatValue(athlete.athlete_timezone) },
      { label: "Locale", value: formatValue(athlete.athlete_locale) },
    ];
  }, [athlete]);

  const intakeHighlights = useMemo(() => {
    if (!latestIntake) {
      return [] as Array<{ label: string; value: string }>;
    }

    return [
      { label: "Fight date", value: formatDate(latestIntake.fight_date, { dateStyle: "medium" }) },
      { label: "Rounds format", value: formatValue(latestIntake.rounds_format) },
      { label: "Sessions / week", value: formatValue(latestIntake.weekly_training_frequency) },
      { label: "Fatigue", value: formatValue(getOptionLabel(FATIGUE_LEVEL_OPTIONS, latestIntake.fatigue_level || "")) },
      { label: "Age", value: formatValue(latestIntake.athlete.age) },
      { label: "Height", value: formatMeasurement(latestIntake.athlete.height_cm, "cm") },
      { label: "Weight", value: formatMeasurement(latestIntake.athlete.weight_kg, "kg") },
      { label: "Target weight", value: formatMeasurement(latestIntake.athlete.target_weight_kg, "kg") },
    ];
  }, [latestIntake]);

  return (
    <RequireAuth adminOnly>
      {error ? (
        <section className="panel loading-card">
          <p className="kicker">Athlete Profile</p>
          <div className="error-banner">{error}</div>
          <div className="plan-summary-actions">
            <Link href="/admin" className="ghost-button">
              Back to admin
            </Link>
          </div>
        </section>
      ) : !athlete ? (
        <section className="panel loading-card">
          <p className="kicker">Athlete Profile</p>
          <h1>Loading profile</h1>
          <p className="muted">Fetching athlete record now.</p>
        </section>
      ) : (
        <section className="panel athlete-profile-panel">
          <div className="section-heading athlete-profile-hero">
            <div>
              <p className="kicker">Athlete Profile</p>
              <h1>{athlete.full_name || athlete.email}</h1>
              <p className="muted">{athlete.email}</p>
            </div>
            <div className="athlete-profile-hero-stats">
              <div className="status-card athlete-profile-stat-card">
                <p className="status-label">Saved plans</p>
                <h2 className="plan-summary-title">{athlete.plan_count}</h2>
                <p className="muted">Total plans generated for this athlete.</p>
              </div>
              <div className="status-card athlete-profile-stat-card athlete-profile-stat-card-accent">
                <p className="status-label">Latest activity</p>
                <h2 className="plan-summary-title athlete-profile-date-title">{formatDate(athlete.latest_plan_created_at || athlete.updated_at, { dateStyle: "medium" })}</h2>
                <p className="muted">Most recent saved plan or profile update.</p>
              </div>
            </div>
          </div>

          <div className="plan-summary-actions">
            <Link href="/admin" className="ghost-button">
              Back to admin
            </Link>
          </div>

          <div className="athlete-profile-grid">
            <section className="plan-summary-card athlete-profile-section-card athlete-profile-section-card-wide">
              <div className="plan-summary-header">
                <div>
                  <p className="kicker">Snapshot</p>
                  <h2 className="plan-summary-title">What this athlete actually entered</h2>
                </div>
                <p className="muted">Core profile data plus the latest intake used to generate a camp plan.</p>
              </div>
              <div className="plan-meta-grid athlete-profile-grid-cards">
                {profileCards.map((item) => (
                  <DetailCard key={item.label} label={item.label} value={item.value} />
                ))}
                <DetailCard label="Member since" value={formatDate(athlete.created_at, { dateStyle: "medium" })} />
                <DetailCard label="Last updated" value={formatDate(athlete.updated_at, { dateStyle: "medium" })} />
              </div>
            </section>

            <section className="plan-summary-card athlete-profile-section-card athlete-profile-section-card-wide">
              <div className="plan-summary-header">
                <div>
                  <p className="kicker">Latest plan intake</p>
                  <h2 className="plan-summary-title">Camp setup at a glance</h2>
                </div>
                <p className="muted">
                  {latestIntake
                    ? "These are the planning inputs that shaped the athlete’s most recent generated plan."
                    : "No completed intake has been saved yet for this athlete."}
                </p>
              </div>
              {latestIntake ? (
                <>
                  <div className="plan-meta-grid athlete-profile-grid-cards">
                    {intakeHighlights.map((item) => (
                      <DetailCard key={item.label} label={item.label} value={item.value} accent="athlete-profile-detail-emphasis" />
                    ))}
                  </div>
                  <div className="athlete-profile-pill-groups">
                    <div className="athlete-profile-pill-group">
                      <p className="plan-meta-label">Training availability</p>
                      <div className="athlete-profile-pills">
                        {getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, latestIntake.training_availability).map((item) => (
                          <span key={item} className="athlete-profile-pill">{item}</span>
                        ))}
                      </div>
                    </div>
                    <div className="athlete-profile-pill-group">
                      <p className="plan-meta-label">Equipment access</p>
                      <div className="athlete-profile-pills">
                        {getOptionLabels(EQUIPMENT_ACCESS_OPTIONS, latestIntake.equipment_access).map((item) => (
                          <span key={item} className="athlete-profile-pill athlete-profile-pill-alt">{item}</span>
                        ))}
                      </div>
                    </div>
                    <div className="athlete-profile-pill-group">
                      <p className="plan-meta-label">Key goals</p>
                      <div className="athlete-profile-pills">
                        {getOptionLabels(KEY_GOAL_OPTIONS, latestIntake.key_goals).map((item) => (
                          <span key={item} className="athlete-profile-pill athlete-profile-pill-success">{item}</span>
                        ))}
                      </div>
                    </div>
                    <div className="athlete-profile-pill-group">
                      <p className="plan-meta-label">Weak areas</p>
                      <div className="athlete-profile-pills">
                        {getOptionLabels(WEAK_AREA_OPTIONS, latestIntake.weak_areas).map((item) => (
                          <span key={item} className="athlete-profile-pill athlete-profile-pill-warning">{item}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                </>
              ) : (
                <div className="empty-state-card">
                  <p className="muted">Once the athlete completes onboarding and generates a plan, their intake details will appear here.</p>
                </div>
              )}
            </section>

            {latestIntake ? (
              <>
                <section className="plan-summary-card athlete-profile-section-card">
                  <div className="plan-summary-header">
                    <div>
                      <p className="kicker">Scheduling</p>
                      <h2 className="plan-summary-title">Weekly structure</h2>
                    </div>
                  </div>
                  <div className="athlete-profile-pill-groups">
                    <div className="athlete-profile-pill-group">
                      <p className="plan-meta-label">Hard sparring days</p>
                      <div className="athlete-profile-pills">
                        {getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, latestIntake.hard_sparring_days).map((item) => (
                          <span key={item} className="athlete-profile-pill">{item}</span>
                        ))}
                      </div>
                    </div>
                    <div className="athlete-profile-pill-group">
                      <p className="plan-meta-label">Technical skill days</p>
                      <div className="athlete-profile-pills">
                        {getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, latestIntake.technical_skill_days).map((item) => (
                          <span key={item} className="athlete-profile-pill athlete-profile-pill-alt">{item}</span>
                        ))}
                      </div>
                    </div>
                  </div>
                </section>

                <section className="plan-summary-card athlete-profile-section-card">
                  <div className="plan-summary-header">
                    <div>
                      <p className="kicker">Coach notes</p>
                      <h2 className="plan-summary-title">Constraints and preferences</h2>
                    </div>
                  </div>
                  <div className="athlete-profile-copy-grid">
                    <article className="athlete-profile-copy-card">
                      <p className="plan-meta-label">Injuries / restrictions</p>
                      <p className="athlete-profile-copy-text">{formatValue(latestIntake.injuries, "No injuries or restrictions noted.")}</p>
                    </article>
                    <article className="athlete-profile-copy-card">
                      <p className="plan-meta-label">Training preference</p>
                      <p className="athlete-profile-copy-text">{formatValue(latestIntake.training_preference, "No training preference provided.")}</p>
                    </article>
                    <article className="athlete-profile-copy-card">
                      <p className="plan-meta-label">Mindset challenges</p>
                      <p className="athlete-profile-copy-text">{formatValue(latestIntake.mindset_challenges, "No mindset blockers provided.")}</p>
                    </article>
                    <article className="athlete-profile-copy-card">
                      <p className="plan-meta-label">Extra notes</p>
                      <p className="athlete-profile-copy-text">{formatValue(latestIntake.notes, "No extra notes provided.")}</p>
                    </article>
                  </div>
                </section>
              </>
            ) : null}
          </div>
        </section>
      )}
    </RequireAuth>
  );
}
