export type UserRole = "athlete" | "admin";
export type AppearanceMode = "dark" | "light";
export type SexValue = "male" | "female";
export type DailyActivityLevel = "low" | "mixed" | "active_job";
export type WeighInType = "same_day" | "day_before" | "informal";
export type PhaseOverride = "GPP" | "SPP" | "TAPER";
export type FatigueLevel = "low" | "moderate" | "high";
export type WeightSource = "manual" | "latest_bodyweight_log" | "imported";
export type TrainingRestrictionLevel = "none" | "minor" | "moderate" | "major";
export type SleepQuality = "good" | "mixed" | "poor";
export type AppetiteStatus = "normal" | "low" | "high";
export type FoundationStatus = "incomplete" | "sufficient" | "complete";
export type NutritionWorkspaceSource = "default" | "draft" | "intake";
export type FightWeekOverrideBand = "none" | "final_day_protocol" | "micro_taper_protocol" | "mini_taper_protocol";
export type SessionDayType = "hard_spar" | "technical" | "strength" | "conditioning" | "recovery" | "off";

export type GenerationJobStatus = "queued" | "running" | "completed" | "review_required" | "failed";

export type AthleteProfileInput = {
  full_name: string;
  sex?: SexValue | null;
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

export type GuidedInjuryInput = {
  area?: string;
  severity?: string;
  trend?: string;
  avoid?: string;
  notes?: string;
};

export type NutritionProfileInput = {
  sex?: SexValue | null;
  age?: number | null;
  height_cm?: number | null;
  daily_activity_level?: DailyActivityLevel | null;
  dietary_restrictions: string[];
  food_preferences: string[];
  meals_per_day_preference?: number | null;
  foods_avoided_pre_session: string[];
  foods_avoided_fight_week: string[];
  supplement_use: string[];
  caffeine_use?: boolean | null;
};

export type NutritionBodyweightLogEntry = {
  date: string;
  weight_kg: number;
  time?: string | null;
  is_fasted?: boolean | null;
  notes?: string | null;
};

export type NutritionReadinessInput = {
  sleep_quality?: SleepQuality | null;
  appetite_status?: AppetiteStatus | null;
};

export type NutritionMonitoringInput = {
  daily_bodyweight_log: NutritionBodyweightLogEntry[];
};

export type NutritionCoachControlsInput = {
  coach_override_enabled: boolean;
  athlete_override_enabled: boolean;
  do_not_reduce_below_calories?: number | null;
  protein_floor_g_per_kg?: number | null;
  fight_week_manual_mode: boolean;
  water_cut_locked_to_manual: boolean;
};

export type NutritionSandCPreferences = {
  equipment_access: string[];
  key_goals: string[];
  weak_areas: string[];
  training_preference?: string;
  mindset_challenges?: string;
  notes?: string;
  random_seed?: number | null;
};

export type NutritionSharedCampContext = {
  fight_date?: string;
  rounds_format?: string;
  weigh_in_type?: WeighInType | null;
  weigh_in_time?: string | null;
  current_weight_kg?: number | null;
  current_weight_recorded_at?: string | null;
  current_weight_source?: WeightSource | null;
  target_weight_kg?: number | null;
  target_weight_range_kg?: [number, number] | number[] | null;
  phase_override?: PhaseOverride | null;
  fatigue_level?: FatigueLevel | null;
  weekly_training_frequency?: number | null;
  training_availability: string[];
  hard_sparring_days: string[];
  support_work_days: string[];
  session_types_by_day: Record<string, SessionDayType>;
  injuries?: string;
  guided_injury?: GuidedInjuryInput | null;
  training_restriction_level?: TrainingRestrictionLevel | null;
};

export type NutritionDerivedState = {
  days_until_fight?: number | null;
  weight_cut_pct: number;
  weight_cut_risk: boolean;
  aggressive_weight_cut: boolean;
  high_pressure_weight_cut: boolean;
  short_notice: boolean;
  fight_week: boolean;
  readiness_flags: string[];
  fight_week_override_band: FightWeekOverrideBand;
  current_phase_effective?: string | null;
  rolling_7_day_average_weight?: number | null;
  foundation_status: FoundationStatus;
  missing_required_fields: string[];
};

export type NutritionWorkspaceState = {
  athlete_id: string;
  source: NutritionWorkspaceSource;
  intake_id?: string | null;
  nutrition_profile: NutritionProfileInput;
  shared_camp_context: NutritionSharedCampContext;
  s_and_c_preferences: NutritionSandCPreferences;
  nutrition_readiness: NutritionReadinessInput;
  nutrition_monitoring: NutritionMonitoringInput;
  nutrition_coach_controls: NutritionCoachControlsInput;
  derived: NutritionDerivedState;
};

export type NutritionWorkspaceUpdateRequest = Omit<NutritionWorkspaceState, "athlete_id" | "source" | "intake_id" | "derived">;

export type PlanRequest = {
  athlete: AthleteProfileInput;
  fight_date: string;
  rounds_format?: string;
  weekly_training_frequency?: number | null;
  fatigue_level?: string;
  equipment_access: string[];
  training_availability: string[];
  hard_sparring_days: string[];
  support_work_days: string[];
  injuries?: string;
  guided_injury?: GuidedInjuryInput | null;
  guided_injuries?: GuidedInjuryInput[] | null;
  key_goals: string[];
  weak_areas: string[];
  training_preference?: string;
  mindset_challenges?: string;
  notes?: string;
  random_seed?: number | null;
  current_step?: number;
  shared_camp_context?: NutritionSharedCampContext;
  s_and_c_preferences?: NutritionSandCPreferences;
  nutrition_readiness?: NutritionReadinessInput;
  nutrition_monitoring?: NutritionMonitoringInput;
  nutrition_coach_controls?: NutritionCoachControlsInput;
};

export type ManualStage2SubmissionRequest = {
  final_plan_text: string;
};

export type ApproveAndResumeGenerationRequest = {
  reason: string;
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
  appearance_mode?: AppearanceMode;
  onboarding_draft?: Record<string, unknown> | null;
  avatar_url?: string | null;
  nutrition_profile?: NutritionProfileInput | null;
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
  appearance_mode: AppearanceMode;
  onboarding_draft?: Record<string, unknown> | null;
  avatar_url?: string | null;
  nutrition_profile: NutritionProfileInput;
  created_at: string;
  updated_at: string;
};

export type PlanSummary = {
  plan_id: string;
  plan_name?: string | null;
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

export type PlanAdvisory = {
  kind: "sparring_adjustment";
  action: "deload" | "convert";
  risk_band?: "green" | "amber" | "red" | "black" | null;
  phase: string;
  week_label: string;
  days: string[];
  title: string;
  reason: string;
  suggestion: string;
  replacement?: string | null;
  disclaimer: string;
};

export type AdminPlanOutputs = {
  coach_notes: string;
  why_log: Record<string, unknown>;
  planning_brief?: Record<string, unknown> | null;
  stage2_payload?: Record<string, unknown> | null;
  parsing_metadata: Record<string, unknown>;
  stage2_handoff_text: string;
  draft_plan_text: string;
  final_plan_text: string;
  stage2_retry_text: string;
  stage2_validator_report: Record<string, unknown>;
  stage2_status: string;
  stage2_attempt_count: number;
};

export type PlanDetail = PlanSummary & {
  outputs: PlanOutputs;
  advisories: PlanAdvisory[];
  latest_intake?: PlanRequest | null;
  admin_outputs?: AdminPlanOutputs | null;
};

export type GenerationJobResponse = {
  job_id: string;
  athlete_id: string;
  client_request_id: string;
  status: GenerationJobStatus;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
  plan_id?: string | null;
  latest_plan_id?: string | null;
};

export type MeResponse = {
  profile: ProfileRecord;
  latest_intake?: PlanRequest | null;
  latest_plan?: PlanSummary | null;
  plan_count: number;
};

export type AdminAthleteRecord = {
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
  appearance_mode: AppearanceMode;
  onboarding_draft?: PlanRequest | null;
  latest_intake?: PlanRequest | null;
  nutrition_profile: NutritionProfileInput;
  created_at: string;
  updated_at: string;
  plan_count: number;
  latest_plan_created_at?: string | null;
};

export type AdminPlanSummary = PlanSummary & {
  athlete_email: string;
};
