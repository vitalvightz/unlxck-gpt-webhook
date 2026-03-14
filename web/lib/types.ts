export type UserRole = "athlete" | "admin";

export type AthleteProfileInput = {
  full_name: string;
  age?: number | null;
  weight_kg?: number | null;
  target_weight_kg?: number | null;
  height_cm?: number | null;
  technical_style: string[];
  tactical_style: string[];
  stance?: string;
  professional_status?: string;
  record?: string;
  athlete_timezone?: string;
  athlete_locale?: string;
};

export type PlanRequest = {
  athlete: AthleteProfileInput;
  fight_date: string;
  rounds_format?: string;
  weekly_training_frequency?: number | null;
  fatigue_level?: string;
  equipment_access: string[];
  training_availability: string[];
  injuries?: string;
  key_goals: string[];
  weak_areas: string[];
  training_preference?: string;
  mindset_challenges?: string;
  notes?: string;
  random_seed?: number | null;
};

export type ProfileUpdateRequest = {
  full_name?: string;
  technical_style?: string[];
  tactical_style?: string[];
  stance?: string;
  professional_status?: string;
  record?: string;
  athlete_timezone?: string;
  athlete_locale?: string;
  onboarding_draft?: Record<string, unknown> | null;
};

export type ProfileRecord = {
  athlete_id: string;
  email: string;
  role: UserRole;
  full_name: string;
  technical_style: string[];
  tactical_style: string[];
  stance: string;
  professional_status: string;
  record: string;
  athlete_timezone: string;
  athlete_locale: string;
  onboarding_draft?: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
};

export type PlanSummary = {
  plan_id: string;
  athlete_id: string;
  full_name: string;
  fight_date: string;
  technical_style: string[];
  created_at: string;
  status: string;
  pdf_url?: string | null;
};

export type PlanOutputs = {
  plan_text: string;
  pdf_url?: string | null;
};

export type AdminPlanOutputs = {
  coach_notes: string;
  why_log: Record<string, unknown>;
  planning_brief?: string | null;
  stage2_payload?: Record<string, unknown> | null;
  stage2_handoff_text: string;
};

export type PlanDetail = PlanSummary & {
  outputs: PlanOutputs;
  admin_outputs?: AdminPlanOutputs | null;
};

export type MeResponse = {
  profile: ProfileRecord;
  latest_intake?: PlanRequest | null;
  plans: PlanSummary[];
};

export type AdminAthleteRecord = {
  athlete_id: string;
  email: string;
  role: UserRole;
  full_name: string;
  technical_style: string[];
  athlete_timezone: string;
  created_at: string;
  updated_at: string;
  plan_count: number;
  latest_plan_created_at?: string | null;
};

export type AdminPlanSummary = PlanSummary & {
  athlete_email: string;
};