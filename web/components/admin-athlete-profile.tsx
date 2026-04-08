import type { ReactNode } from "react";

import Link from "next/link";

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
import type { AdminAthleteRecord } from "@/lib/types";

const FATIGUE_LEVEL_OPTIONS = [
  { value: "low", label: "Low" },
  { value: "moderate", label: "Moderate" },
  { value: "high", label: "High" },
];

type ReviewItem = {
  label: string;
  value: ReactNode;
  multiline?: boolean;
  emphasize?: boolean;
};

type ReviewSection = {
  kicker: string;
  title: string;
  items: ReviewItem[];
  wide?: boolean;
};

function getOptionLabel(options: { value: string; label: string }[], value: string): string {
  return options.find((option) => option.value === value)?.label ?? value;
}

function getOptionLabels(options: { value: string; label: string }[], values: string[] | undefined): string[] {
  return (values ?? []).map((value) => getOptionLabel(options, value)).filter(Boolean);
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

function formatList(values: string[], empty = "Not provided"): string {
  return values.length ? values.join(", ") : empty;
}

function InlinePills({ items, empty = "Not provided" }: { items: string[]; empty?: string }) {
  if (!items.length) {
    return <span className="athlete-profile-empty-value">{empty}</span>;
  }

  return (
    <div className="athlete-profile-inline-pills">
      {items.map((item) => (
        <span key={item} className="athlete-profile-pill athlete-profile-pill-compact">
          {item}
        </span>
      ))}
    </div>
  );
}

function InlineList({ items, empty = "Not provided" }: { items: string[]; empty?: string }) {
  return <span className="athlete-profile-inline-list">{items.length ? items.join(", ") : empty}</span>;
}

function AthleteProfileSection({ kicker, title, items, wide = false }: ReviewSection) {
  return (
    <section className={`athlete-profile-group${wide ? " athlete-profile-group-wide" : ""}`.trim()}>
      <div className="athlete-profile-group-heading">
        <p className="kicker">{kicker}</p>
        <h2 className="form-section-title">{title}</h2>
      </div>

      <div className="review-detail-list athlete-profile-review-list">
        {items.map((item) => (
          <div
            key={item.label}
            className={`review-detail-row athlete-profile-review-row${item.multiline ? " athlete-profile-review-row-multiline" : ""}`.trim()}
          >
            <p className="review-detail-label">{item.label}</p>
            <div className={`review-detail-value${item.emphasize ? " athlete-profile-review-value-emphasis" : ""}`.trim()}>
              {item.value}
            </div>
          </div>
        ))}
      </div>
    </section>
  );
}

function buildReviewSections(athlete: AdminAthleteRecord): ReviewSection[] {
  const intake = athlete.latest_intake ?? null;

  const sections: ReviewSection[] = [
    {
      kicker: "Account",
      title: "Athlete account",
      items: [
        { label: "Full name", value: formatValue(athlete.full_name) },
        { label: "Email", value: formatValue(athlete.email) },
        { label: "Role", value: athlete.role === "admin" ? "Admin" : "Athlete" },
        { label: "Timezone", value: formatValue(athlete.athlete_timezone) },
        { label: "Locale", value: formatValue(athlete.athlete_locale) },
        { label: "Member since", value: formatDate(athlete.created_at, { dateStyle: "medium" }) },
        { label: "Last updated", value: formatDate(athlete.updated_at, { dateStyle: "medium" }) },
      ],
    },
    {
      kicker: "Profile",
      title: "Competition profile",
      items: [
        ...(formatOptionalValue(intake?.athlete.age) ? [{ label: "Age", value: formatValue(intake?.athlete.age) }] : []),
        ...(formatMeasurement(intake?.athlete.height_cm, "cm")
          ? [{ label: "Height", value: formatMeasurement(intake?.athlete.height_cm, "cm") as string }]
          : []),
        ...(formatMeasurement(intake?.athlete.weight_kg, "kg")
          ? [{ label: "Current weight", value: formatMeasurement(intake?.athlete.weight_kg, "kg") as string }]
          : []),
        ...(formatMeasurement(intake?.athlete.target_weight_kg, "kg")
          ? [{ label: "Target weight", value: formatMeasurement(intake?.athlete.target_weight_kg, "kg") as string }]
          : []),
        { label: "Stance", value: formatValue(getOptionLabel(STANCE_OPTIONS, athlete.stance || "")) },
        {
          label: "Technical style",
          value: <InlinePills items={getOptionLabels(TECHNICAL_STYLE_OPTIONS, athlete.technical_style)} />,
          multiline: true,
        },
        {
          label: "Tactical style",
          value: <InlinePills items={getOptionLabels(TACTICAL_STYLE_OPTIONS, athlete.tactical_style)} />,
          multiline: true,
        },
        {
          label: "Professional status",
          value: formatValue(getOptionLabel(PROFESSIONAL_STATUS_OPTIONS, athlete.professional_status || "")),
        },
        { label: "Record", value: formatValue(athlete.record) },
      ],
    },
  ];

  if (!intake) {
    sections.push({
      kicker: "Latest intake",
      title: "Plan setup not available yet",
      wide: true,
      items: [
        {
          label: "Status",
          value:
            athlete.plan_count > 0
              ? `This athlete has ${athlete.plan_count} saved ${athlete.plan_count === 1 ? "plan" : "plans"}, but the latest intake payload was not returned for this record.`
              : "No completed intake has been saved yet for this athlete.",
          multiline: true,
        },
        {
          label: "Latest plan activity",
          value: athlete.latest_plan_created_at ? formatDate(athlete.latest_plan_created_at, { dateStyle: "medium" }) : "Not available",
        },
      ],
    });

    return sections;
  }

  sections.push({
    kicker: "Camp",
    title: "Latest camp setup",
    items: [
      { label: "Fight date", value: formatDate(intake.fight_date, { dateStyle: "medium" }), emphasize: true },
      { label: "Rounds format", value: formatValue(intake.rounds_format), emphasize: true },
      { label: "Planned sessions / week", value: formatValue(intake.weekly_training_frequency), emphasize: true },
      {
        label: "Fatigue",
        value: formatValue(getOptionLabel(FATIGUE_LEVEL_OPTIONS, intake.fatigue_level || "")),
        emphasize: true,
      },
    ],
  });

  sections.push({
    kicker: "Training",
    title: "Training and availability",
    wide: true,
    items: [
      {
        label: "Training availability",
        value: <InlineList items={getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, intake.training_availability)} />,
      },
      {
        label: "Hard sparring days",
        value: <InlineList items={getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, intake.hard_sparring_days)} />,
      },
      {
        label: "Technical / lighter skill days",
        value: <InlineList items={getOptionLabels(TRAINING_AVAILABILITY_OPTIONS, intake.technical_skill_days)} />,
      },
      {
        label: "Equipment access",
        value: <InlineList items={getOptionLabels(EQUIPMENT_ACCESS_OPTIONS, intake.equipment_access)} />,
        multiline: true,
      },
    ],
  });

  sections.push({
    kicker: "Planner context",
    title: "Planner context",
    wide: true,
    items: [
      {
        label: "Key goals",
        value: <InlinePills items={getOptionLabels(KEY_GOAL_OPTIONS, intake.key_goals)} />,
        multiline: true,
      },
      {
        label: "Weak areas",
        value: <InlinePills items={getOptionLabels(WEAK_AREA_OPTIONS, intake.weak_areas)} />,
        multiline: true,
      },
      { label: "Injuries / restrictions", value: formatValue(intake.injuries), multiline: true },
      { label: "Training preference", value: formatValue(intake.training_preference), multiline: true },
      { label: "Mindset challenges", value: formatValue(intake.mindset_challenges), multiline: true },
      { label: "Extra notes", value: formatValue(intake.notes), multiline: true },
    ],
  });

  return sections;
}

export function AthleteProfileSheet({
  athlete,
  onGenerate,
  isGenerating,
  statusMessage,
}: {
  athlete: AdminAthleteRecord;
  onGenerate: () => void | Promise<void>;
  isGenerating: boolean;
  statusMessage?: string | null;
}) {
  const canGenerate = Boolean(athlete.latest_intake);
  const supportMessage =
    statusMessage || (!canGenerate ? "Generate is available after this athlete has at least one saved intake." : null);
  const sections = buildReviewSections(athlete);

  return (
    <section className="plan-summary-card athlete-profile-sheet">
      <header className="athlete-profile-header">
        <div className="athlete-profile-header-main">
          <div className="athlete-profile-header-copy">
            <div className="athlete-profile-title-row">
              <div>
                <p className="kicker">Athlete Profile</p>
                <h1>{athlete.full_name || athlete.email}</h1>
              </div>
              <span className="athlete-profile-role-badge">{athlete.role === "admin" ? "Admin view" : "Athlete"}</span>
            </div>
            <p className="muted">{athlete.email}</p>
          </div>

          <div className="athlete-profile-meta-strip">
            <div className="athlete-profile-meta-item">
              <p className="review-detail-label">Saved plans</p>
              <p className="athlete-profile-meta-value">{athlete.plan_count}</p>
            </div>
            <div className="athlete-profile-meta-item">
              <p className="review-detail-label">Latest activity</p>
              <p className="athlete-profile-meta-value">
                {formatDate(athlete.latest_plan_created_at || athlete.updated_at, { dateStyle: "medium" })}
              </p>
            </div>
          </div>
        </div>

        <div className="athlete-profile-header-side">
          <div className="athlete-profile-actions">
            <Link href="/admin" className="ghost-button">
              Back to admin
            </Link>
            <button type="button" className="primary-button" onClick={onGenerate} disabled={!canGenerate || isGenerating}>
              {isGenerating ? "Generating..." : "Generate new plan"}
            </button>
          </div>
          {supportMessage ? <p className="athlete-profile-support-note muted">{supportMessage}</p> : null}
        </div>
      </header>

      <div className="athlete-profile-groups">
        {sections.map((section) => (
          <AthleteProfileSection key={section.title} {...section} />
        ))}
      </div>
    </section>
  );
}
