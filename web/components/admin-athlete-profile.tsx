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

function buildSnapshotDetails(athlete: AdminAthleteRecord): DetailItem[] {
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
    { label: "Member since", value: formatDate(athlete.created_at, { dateStyle: "medium" }) },
    { label: "Last updated", value: formatDate(athlete.updated_at, { dateStyle: "medium" }) },
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
    ...(formatOptionalValue(intake.athlete.age) ? [{ label: "Age", value: formatValue(intake.athlete.age), accent: "athlete-profile-detail-emphasis" }] : []),
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

function buildCoachNotes(intake: PlanRequest): CopyItem[] {
  return [
    { label: "Injuries / restrictions", value: intake.injuries ?? "" },
    { label: "Training preference", value: intake.training_preference ?? "" },
    { label: "Mindset challenges", value: intake.mindset_challenges ?? "" },
    { label: "Extra notes", value: intake.notes ?? "" },
  ].filter((item) => item.value.trim().length > 0);
}

function DetailCard({ label, value, accent }: DetailItem) {
  return (
    <article className="plan-meta-item athlete-profile-detail-card">
      <p className="plan-meta-label">{label}</p>
      <p className={`plan-meta-value${accent ? ` ${accent}` : ""}`}>{value}</p>
    </article>
  );
}

export function AthleteProfileHero({ athlete }: { athlete: AdminAthleteRecord }) {
  return (
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
          <h2 className="plan-summary-title athlete-profile-date-title">
            {formatDate(athlete.latest_plan_created_at || athlete.updated_at, { dateStyle: "medium" })}
          </h2>
          <p className="muted">Most recent saved plan or profile update.</p>
        </div>
      </div>
    </div>
  );
}

export function AthleteSnapshotCard({ athlete }: { athlete: AdminAthleteRecord }) {
  const details = buildSnapshotDetails(athlete);

  return (
    <section className="plan-summary-card athlete-profile-section-card athlete-profile-section-card-wide">
      <div className="plan-summary-header">
        <div>
          <p className="kicker">Snapshot</p>
          <h2 className="plan-summary-title">What this athlete actually entered</h2>
        </div>
        <p className="muted">Core profile data plus the latest intake used to generate a camp plan.</p>
      </div>
      <div className="plan-meta-grid athlete-profile-grid-cards">
        {details.map((item) => (
          <DetailCard key={item.label} {...item} />
        ))}
      </div>
    </section>
  );
}

export function AthleteLatestIntakeCard({ intake }: { intake: PlanRequest | null }) {
  const highlights = intake ? buildIntakeHighlights(intake) : [];
  const groups = intake ? buildPillGroups(intake) : [];

  return (
    <section className="plan-summary-card athlete-profile-section-card athlete-profile-section-card-wide">
      <div className="plan-summary-header">
        <div>
          <p className="kicker">Latest plan intake</p>
          <h2 className="plan-summary-title">Camp setup at a glance</h2>
        </div>
        <p className="muted">
          {intake
            ? "These are the planning inputs that shaped the athlete’s most recent generated plan."
            : "No completed intake has been saved yet for this athlete."}
        </p>
      </div>
      {intake ? (
        <>
          <div className="plan-meta-grid athlete-profile-grid-cards">
            {highlights.map((item) => (
              <DetailCard key={item.label} {...item} />
            ))}
          </div>
          {groups.length ? (
            <div className="athlete-profile-pill-groups">
              {groups.map((group) => (
                <div key={group.label} className="athlete-profile-pill-group">
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
          <p className="muted">Once the athlete completes onboarding and generates a plan, their intake details will appear here.</p>
        </div>
      )}
    </section>
  );
}

export function AthleteScheduleCard({ intake }: { intake: PlanRequest }) {
  const groups = buildScheduleGroups(intake);
  if (!groups.length) {
    return null;
  }

  return (
    <section className="plan-summary-card athlete-profile-section-card">
      <div className="plan-summary-header">
        <div>
          <p className="kicker">Scheduling</p>
          <h2 className="plan-summary-title">Weekly structure</h2>
        </div>
      </div>
      <div className="athlete-profile-pill-groups">
        {groups.map((group) => (
          <div key={group.label} className="athlete-profile-pill-group">
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
    </section>
  );
}

export function AthleteCoachNotesCard({ intake }: { intake: PlanRequest }) {
  const notes = buildCoachNotes(intake);
  if (!notes.length) {
    return null;
  }

  return (
    <section className="plan-summary-card athlete-profile-section-card">
      <div className="plan-summary-header">
        <div>
          <p className="kicker">Coach notes</p>
          <h2 className="plan-summary-title">Constraints and preferences</h2>
        </div>
      </div>
      <div className="athlete-profile-copy-grid">
        {notes.map((item) => (
          <article key={item.label} className="athlete-profile-copy-card">
            <p className="plan-meta-label">{item.label}</p>
            <p className="athlete-profile-copy-text">{item.value}</p>
          </article>
        ))}
      </div>
    </section>
  );
}
