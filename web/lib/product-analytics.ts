export type ActivitySummary = {
  signals?: string[];
  id: string;
  registered_at: string;
  first_activity: string | null;
  last_activity: string | null;
  active_days_7: number;
  active_days_30: number;
  inactivity_days: number | null;
};
export type FeatureUsage = {
  completion_label?: string;
  completion?: {
    started: number;
    completed: number;
    percent: number | null;
  } | null;
  observed_early_exits?: number;
  feature: string;
  athletes: number;
  percent: number | null;
  uses: number;
  repeat_athletes: number;
  discovered: number;
  actions: Record<string, number>;
};
export type Retention = {
  eligible: number;
  returned: number;
  percent: number | null;
};
export type ProductReport = {
  as_of: string;
  days: number;
  registered: number;
  ever_active: number;
  active: number;
  previous_active: number | null;
  dau: number;
  wau: number;
  mau: number;
  stickiness: number | null;
  average_active_days: number | null;
  new_active: number;
  returning_active: number;
  never_active: number;
  sessions_started: number;
  sessions_completed: number;
  observed_session_abandonments: number;
  inactive: Record<string, number>;
  retention: Record<string, Retention>;
  cohorts: {
    week: string;
    signups: number;
    retention: Record<string, Retention>;
  }[];
  trend: { day: string; athletes: number }[];
  features: FeatureUsage[];
  funnel: {
    label: string;
    eligible: number;
    converted: number;
    percent: number | null;
    median_seconds: number | null;
  }[];
  conversions: {
    label: string;
    eligible: number;
    converted: number;
    percent: number | null;
    median_seconds: number | null;
  }[];
  dropoffs: Record<string, number>;
  errors: {
    feature: string;
    category: string;
    count: number;
    affected_athletes: number;
    errors_per_athlete: number;
  }[];
  friction_followup: {
    feature: string;
    category: string;
    eligible_athletes: number;
    no_recorded_return_7d: number;
  }[];
  segments: {
    professional_status: string[];
    sports: string[];
    acquisition: string;
  };
  athletes: ActivitySummary[];
  athlete_total: number;
  offset: number;
};
export type AthleteActivity = {
  summary: ActivitySummary;
  features: FeatureUsage[];
  sessions_started: number;
  sessions_completed: number;
  timeline: {
    id: string;
    occurred_at: string;
    feature: string;
    action: string;
  }[];
  latest_plan_interactions: {
    id: string;
    occurred_at: string;
    action: string;
  }[];
  offset: number;
};
export const humanize = (value: string) => value.replaceAll("_", " ");
export const percent = (value: number | null) =>
  value === null ? "Insufficient data" : `${value.toFixed(1)}%`;
