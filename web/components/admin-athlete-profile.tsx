import type { ReactNode } from "react";

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

type DetailItem = {
  label: string;
  value: string;
  accent?: string;
};

type DetailGroup = {
  label: string;
  items?: DetailItem[];
  highlight?: string;
};

type PillGroup = {
  label: string;
  items: string[];
  tone?: "default" | "alt" | "success" | "warning";
};

type CopyItem = {
  label: string;
  value: string;
};

function getOptionLabel(options: { value: string; label: string }[], value: string): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

function getOptionLabels(options: { value: string; label: string }[], values: string[] | undefined): string[] {
  return (values ?? []).map((value) => getOptionLabel(options, value)).filter(Boolean);
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

function formatOptionalValue(value: string | number | null | undefined): string | null {
  const normalized = formatValue(value, "").trim();
  return normalized ? normalized : null;
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

function formatMeasurement(value: number | null | undefined, unit: string): string | null {
  return value == null ? null : `${value} ${unit}`;
}

function getLocaleRegion(locale: string | null | undefined): string | null {
  const normalized = formatOptionalValue(locale)?.replace(/_/g, "-");
  if (!normalized) {
    return null;
  }

  try {
    const region = new Intl.Locale(normalized).region;
    if (region) {
      return region.toUpperCase();
    }
  } catch {
    // Fall through to manual parsing for malformed or unsupported locale strings.
  }

  const match = normalized.match(/(?:^|[-_])([A-Za-z]{2}|\d{3})(?:[-_]|$)/);
  return match ? match[1].toUpperCase() : null;
}

function regionToFlag(region: string | null): string {
  if (!region || !/^[A-Z]{2}$/.test(region)) {
    return "";
  }

  return String.fromCodePoint(...region.split("").map((char) => 127397 + char.charCodeAt(0)));
}

function formatCountry(locale: string | null | undefined): string {
  const region = getLocaleRegion(locale);
  if (!region) {
    return "Not provided";
  }

  let countryName = region;
  try {
    countryName = new Intl.DisplayNames(["en"], { type: "region" }).of(region) ?? region;
  } catch {
    countryName = region;
  }

  const flag = regionToFlag(region);
  return flag ? `${flag} ${countryName}` : countryName;
}

function toneClassName(tone: PillGroup["tone"]): string {
  switch (tone) {
    case "alt":
      return " athlete-profile-pill-alt";
    case "success":
      return " athlete-profile-pill-success";
    case "warning":
      return " athlete-profile-pill-warning";
    default:
      return "";
  }
}

function buildHeroStats(athlete: AdminAthleteRecord): DetailItem[] {
  return [
    { label: "Saved plans", value: formatValue(athlete.plan_count) },
    {
      label: "Latest activity",
      value: formatDate(athlete.latest_plan_created_at || athlete.updated_at, { dateStyle: "medium" }),
    },
    {
      label: "Professional status",
      value: formatValue(getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, athlete.professional_status || "")),
    },
    { label: "Record", value: formatValue(athlete.record) },
  ];
}

function buildSnapshotGroups(athlete: AdminAthleteRecord): DetailGroup[] {
  return [
    {
      label: "Combat profile",
      items: [
        { label: "Technical style", value: formatList(getOptionLabels(TECHNICAL_STYLE_OPTIONS, athlete.technical_style)) },
        { label: "Tactical style", value: formatList(getOptionLabels(TACTICAL_STYLE_OPTIONS, athlete.tactical_style)) },
        { label: "Stance", value: formatValue(getOptionLabel(STANCE_OPTIONS, athlete.stance || "")) },
        { label: "Record", value: formatValue(athlete.record) },
      ],
    },
    {
      label: "Account",
      items: [
        { label: "Role", value: athlete.role === "admin" ? "Admin" : "Athlete" },
        {
          label: "Professional status",
          value: formatValue(getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, athlete.professional_status || "")),
        },
        { label: "Member since", value: formatDate(athlete.created_at, { dateStyle: "medium" }) },
        { label: "Last updated", value: formatDate(athlete.updated_at, { dateStyle: "medium" }) },
      ],
    },
    {
      label: "Country",
      highlight: formatCountry(athlete.athlete_locale),
    },
  ];
}

function buildIntakeHighlights(intake: PlanRequest): DetailItem[] {
  return [
    { label: "Fight date", value: formatDate(intake.fight_date, { dateStyle: "medium" }), accent: "athlete-profile-detail-emphasis" },
    { label: "Rounds format", value: formatValue(intake.rounds_format), accent: "athlete-profile-detail-emphasis" },
    { label: "Sessions / week", value: formatValue(intake.weekly_training_frequency), accent: "athlete-profile-detail-emphasis" },
    {
      label: "Fatigue",
      value: formatValue(getOptionLabel(FATIGUE_LEVEL_OPTIONS, intake.fatigue_level || "")),
      accent: "athlete-profile-detail-emphasis",
    },
    ...(formatOptionalValue(intake.athlete.age)
      ? [{ label: "Age", value: formatValue(intake.athlete.age), accent: "athlete-profile-detail-emphasis" }]
      : []),
    ...(formatMeasurement(intake.athlete.height_cm, "cm")
      ? [{ label: "Height", value: formatMeasurement(intake.athlete.height_cm, "cm") as string, accent: "athlete-profile-detail-emphasis" }]
      : []),
    ...(formatMeasurement(intake.athlete.weight_kg, "kg")
      ? [{ label: "Weight", value: formatMeasurement(intake.athlete.weight_kg, "kg") as string, accent: "athlete-profile-detail-emphasis" }]
      : []),
    ...(formatMeasurement(intake.athlete.target_weight_kg, "kg")
      ? [{ label: "Target weight", value: formatMeasurement(intake.athlete.target_weight_kg, "kg") as string, accent: "athlete-profile-detail-emphasis" }]
      : []),
  ];
}

function buildPillGroups(intake: PlanRequest): PillGroup[] {
  const groups: PillGroup[] = [
    {
      label: "Training availability",
      items: getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, intake.training_availability),
    },
    {
      label: "Equipment access",
      items: getOptionLabels(EQUIPMENT_ACCESS_OPTIONS, intake.equipment_access),
      tone: "alt",
    },
    {
      label: "Key goals",
      items: getOptionLabels(KEY_GOAL_OPTIONS, intake.key_goals),
      tone: "success",
    },
    {
      label: "Weak areas",
      items: getOptionLabels(WEAK_AREA_OPTIONS, intake.weak_areas),
      tone: "warning",
    },
  ];
  return groups.filter((group) => group.items.length > 0);
}

function buildScheduleGroups(intake: PlanRequest): PillGroup[] {
  const groups: PillGroup[] = [
    {
      label: "Hard sparring days",
      items: getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, intake.hard_sparring_days),
    },
    {
      label: "Technical skill days",
      items: getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, intake.technical_skill_days),
      tone: "alt",
    },
  ];
  return groups.filter((group) => group.items.length > 0);
}

function buildFocusGroups(intake: PlanRequest): PillGroup[] {
  return [...buildScheduleGroups(intake), ...buildPillGroups(intake)];
}

function buildCoachNotes(intake: PlanRequest): CopyItem[] {
  return [
    { label: "Injuries / restrictions", value: intake.injuries ?? "" },
    { label: "Training preference", value: intake.training_preference ?? "" },
    { label: "Mindset challenges", value: intake.mindset_challenges ?? "" },
    { label: "Extra notes", value: intake.notes ?? "" },
  ].filter((item) => item.value.trim().length > 0);
}

function DetailList({ items }: { items: DetailItem[] }) {
  return (
    <dl className="athlete-profile-detail-list">
      {items.map((item) => (
        <div key={item.label} className="athlete-profile-detail-row">
          <dt className="athlete-profile-detail-label">{item.label}</dt>
          <dd className={`athlete-profile-detail-value${item.accent ? ` ${item.accent}` : ""}`}>{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function MetricCell({ label, value, accent }: DetailItem) {
  return (
    <article className="athlete-profile-metric-cell">
      <p className="plan-meta-label">{label}</p>
      <p className={`athlete-profile-metric-value${accent ? ` ${accent}` : ""}`}>{value}</p>
    </article>
  );
}

export function AthleteProfileHero({
  athlete,
  actions,
}: {
  athlete: AdminAthleteRecord;
  actions?: ReactNode;
}) {
  const stats = buildHeroStats(athlete);

  return (
    <section className="athlete-profile-hero">
      <div className="athlete-profile-hero-heading">
        <div className="athlete-profile-hero-copy">
          <p className="kicker">Athlete Profile</p>
          <h1>{athlete.full_name || athlete.email}</h1>
          <p className="muted">{athlete.email}</p>
        </div>
        {actions ? <div className="athlete-profile-hero-actions">{actions}</div> : null}
      </div>
      <div className="athlete-profile-hero-summary">
        {stats.map((item) => (
          <article key={item.label} className="athlete-profile-hero-stat">
            <p className="status-label">{item.label}</p>
            <p className="athlete-profile-hero-stat-value">{item.value}</p>
          </article>
        ))}
      </div>
    </section>
  );
}

export function AthleteSnapshotCard({ athlete }: { athlete: AdminAthleteRecord }) {
  const groups = buildSnapshotGroups(athlete);

  return (
    <section className="plan-summary-card athlete-profile-section-card athlete-profile-section-card-wide">
      <div className="athlete-profile-section-heading">
        <div>
          <p className="kicker">Snapshot</p>
          <h2 className="plan-summary-title">What this athlete actually entered</h2>
        </div>
        <p className="muted">A tighter read on the athlete's profile without the card wall.</p>
      </div>
      <div className="athlete-profile-fact-columns">
        {groups.map((group) => (
          <section key={group.label} className="athlete-profile-block">
            <p className="plan-meta-label">{group.label}</p>
            {group.highlight ? (
              <p className="athlete-profile-country-value">{group.highlight}</p>
            ) : (
              <DetailList items={group.items ?? []} />
            )}
          </section>
        ))}
      </div>
    </section>
  );
}

export function AthleteLatestIntakeCard({ intake }: { intake: PlanRequest | null }) {
  const highlights = intake ? buildIntakeHighlights(intake) : [];
  const groups = intake ? buildFocusGroups(intake) : [];
  const notes = intake ? buildCoachNotes(intake) : [];

  return (
    <section className="plan-summary-card athlete-profile-section-card athlete-profile-section-card-wide">
      <div className="athlete-profile-section-heading">
        <div>
          <p className="kicker">Latest plan intake</p>
          <h2 className="plan-summary-title">Camp setup at a glance</h2>
        </div>
        <p className="muted">
          {intake
            ? "The latest plan inputs are condensed into one operating view."
            : "No completed intake has been saved yet for this athlete."}
        </p>
      </div>
      {intake ? (
        <>
          <div className="athlete-profile-intake-board">
            <section className="athlete-profile-block athlete-profile-block-strong">
              <p className="plan-meta-label">Key metrics</p>
              <div className="athlete-profile-metric-grid">
                {highlights.map((item) => (
                  <MetricCell key={item.label} {...item} />
                ))}
              </div>
            </section>
            <section className="athlete-profile-block athlete-profile-block-strong">
              <div className="athlete-profile-notes-heading">
                <p className="plan-meta-label">Constraints and notes</p>
                <p className="muted">Only the highest-signal written context from the latest intake.</p>
              </div>
              {notes.length ? (
                <div className="athlete-profile-note-grid">
                  {notes.map((item) => (
                    <article key={item.label} className="athlete-profile-note-card">
                      <p className="plan-meta-label">{item.label}</p>
                      <p className="athlete-profile-copy-text" title={item.value}>
                        {item.value}
                      </p>
                    </article>
                  ))}
                </div>
              ) : (
                <p className="muted">No written restrictions or preferences were captured on the latest intake.</p>
              )}
            </section>
          </div>
          {groups.length ? (
            <div className="athlete-profile-tag-rails">
              {groups.map((group) => (
                <div key={group.label} className="athlete-profile-tag-rail">
                  <p className="plan-meta-label">{group.label}</p>
                  <div className="athlete-profile-pills">
                    {group.items.map((item) => (
                      <span key={item} className={`athlete-profile-pill${toneClassName(group.tone)}`}>
                        {item}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </>
      ) : (
        <div className="empty-state-card">
          <p className="muted">Once the athlete completes onboarding and generates a plan, their intake snapshot will appear here.</p>
        </div>
      )}
    </section>
  );
}

export function AthleteLatestIntakeStatus({
  planCount,
  latestPlanCreatedAt,
}: {
  planCount: number;
  latestPlanCreatedAt?: string | null;
}) {
  if (!planCount) {
    return null;
  }

  return (
    <div className="empty-state-card athlete-profile-inline-note">
      <p className="plan-meta-label">Latest saved plan detected</p>
      <p className="muted">
        This athlete has {planCount} saved {planCount === 1 ? "plan" : "plans"}
        {latestPlanCreatedAt ? `, with the most recent created ${formatDate(latestPlanCreatedAt, { dateStyle: "medium" })}` : ""}.{" "}
        The intake payload was not returned for this record, so the latest intake summary cannot be shown yet.
      </p>
    </div>
  );
}
