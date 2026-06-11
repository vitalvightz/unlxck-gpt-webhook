// Role foundation for the single Unlxck app. `athlete` and `admin` are live in
// private beta; `coach` and `gym_owner` are reserved for public beta and are not
// yet selectable at sign-up or assignable to accounts. We use `gym_owner` (not
// `gym`) because the account represents the person managing the gym organisation.
export type UserRole = "athlete" | "coach" | "gym_owner" | "admin";
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
// NOTE: "technical" is a legacy internal token kept for saved-draft/API compatibility.
// It represents support_work_days (non-hard training / S&C-compatible slots).
export type SessionDayType = "hard_spar" | "technical" | "strength" | "conditioning" | "recovery" | "off";
export type SparringDayClass = "primary_hard" | "secondary_hard" | "managed_hard" | "technical" | "none";
export type EffectiveLoad = "hard" | "technical" | "reduced" | "none";

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
  injury_type?: string;
  injury_subtypes?: string[];
  surface_type?: string;
  timeframe?: string;
  cleared?: string;
  open_wound?: string;
  bleeding_status?: string;
  infection_signs?: string[];
  impact_related?: string;
  sensitive_area?: string;
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

export type GoalWeaknessCollisionDetail = {
  tag: string;
  label: string;
  detail: string;
};

export type NutritionSandCPreferences = {
  equipment_access: string[];
  key_goals: string[];
  primary_goal?: string | null;
  weak_areas: string[];
  primary_weak_area?: string | null;
  goal_weakness_collision_detail?: string;
  goal_weakness_collision_tags?: string[];
  goal_weakness_collision_details?: GoalWeaknessCollisionDetail[];
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
  no_scheduled_fight?: boolean;
  open_camp_weeks?: number;
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
  primary_goal?: string | null;
  weak_areas: string[];
  primary_weak_area?: string | null;
  goal_weakness_collision_detail?: string;
  goal_weakness_collision_tags?: string[];
  goal_weakness_collision_details?: GoalWeaknessCollisionDetail[];
  training_preference?: string;
  mindset_challenges?: string;
  notes?: string;
  random_seed?: number | null;
  intake_id?: string | null;
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
  username?: string | null;
  username_change_history?: string[];
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

export type UsernameRateLimitInfo = {
  max_changes_per_window: number;
  window_days: number;
  remaining: number;
  next_available_at?: string | null;
};

export type UsernameChangeRequest = {
  username: string;
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

export type WeeklyDayEntry = {
  weekday: "Mon" | "Tue" | "Wed" | "Thu" | "Fri" | "Sat" | "Sun";
  sparring_day_class: SparringDayClass;
  effective_load: EffectiveLoad;
  status: string;
  reason: string;
  coach_note: string;
  reason_codes: string[];
  d_day?: number | null;
  day_label?: string;
  weekday_with_label?: string;
  calendar_date?: string | null;
  is_fight_day?: boolean;
  is_after_fight_day?: boolean;
};

export type WeeklySchedule = {
  plan_id: string;
  week_index: number;
  week_count: number;
  phase: string;
  projected_days_until_fight_start?: number | null;
  projected_days_until_fight_end?: number | null;
  day_label?: string;
  countdown_range?: number[];
  week_countdown_label?: string;
  week_label_with_countdown?: string;
  days: WeeklyDayEntry[];
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
  plan_source?: string | null;
};

export type ProgressMilestone = {
  code: string;
  label: string;
  detail: string;
  at: string;
  meta?: Record<string, unknown>;
};

export type GenerationJobResponse = {
  job_id: string;
  athlete_id: string;
  client_request_id: string;
  status: GenerationJobStatus;
  created_at: string;
  updated_at: string;
  started_at?: string | null;
  heartbeat_at?: string | null;
  completed_at?: string | null;
  error?: string | null;
  plan_id?: string | null;
  latest_plan_id?: string | null;
  source?: string | null;
  progress_milestones?: ProgressMilestone[];
  warnings?: string[];
  can_retry?: boolean;
  status_url?: string | null;
  message?: string | null;
  stage2_status?: string | null;
  requires_admin_resume?: boolean;
};

export type MeResponse = {
  profile: ProfileRecord;
  latest_intake?: PlanRequest | null;
  latest_plan?: PlanSummary | null;
  plan_count: number;
  username_rate_limit: UsernameRateLimitInfo;
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

export type AdminLatestIntakeUpdateRequest = {
  fight_date?: string | null;
  no_scheduled_fight?: boolean;
  rounds_format?: string | null;
  weekly_training_frequency?: number | null;
  training_availability?: string[];
  equipment_access?: string[];
  key_goals?: string[];
  weak_areas?: string[];
  injuries?: string | null;
};

export type AdminPlanSummary = PlanSummary & {
  athlete_email: string;
};

export type GenerationRequestPayloadSummary = {
  athlete_name: string;
  fight_date: string;
  phase: string;
  fight_format: string;
  fatigue_level: string;
  goals: string[];
  weaknesses: string[];
  injuries: string[];
  training_availability: string;
};

export type AdminGenerationJobDiagnostic = {
  job_id: string;
  athlete_id?: string;
  athlete_email?: string;
  athlete_full_name?: string;
  intake_id?: string | null;
  status: GenerationJobStatus;
  source: string;
  created_at: string;
  started_at?: string | null;
  heartbeat_at?: string | null;
  completed_at?: string | null;
  client_request_id: string;
  retry_of?: string | null;
  error?: string | null;
  stale_reason?: string | null;
  plan_id?: string | null;
  can_retry: boolean;
  stage2_status?: string | null;
  requires_admin_resume?: boolean;
  is_stale: boolean;
  warnings?: string[];
  request_payload_summary: GenerationRequestPayloadSummary;
};

// ---------------------------------------------------------------------------
// Live athlete daily tracking (dashboard, check-ins, session logs, injury
// flags, adaptation notes, admin review queue).
// ---------------------------------------------------------------------------

export type ReadinessState = "ready" | "caution" | "high_fatigue" | "injury_flag";

export type AdaptationDecisionValue =
  | "keep_plan"
  | "reduce_intensity"
  | "swap_session"
  | "add_recovery"
  | "flag_admin_review";

export type InjuryFlagSeverity = "mild" | "moderate" | "severe";
export type InjuryFlagStatus = "open" | "monitoring" | "resolved";
export type AdminReviewStatus = "pending" | "acknowledged" | "resolved";

export type DailyCheckinRequest = {
  checkin_date?: string | null;
  readiness: number;
  fatigue: number;
  soreness: number;
  sleep_quality: number;
  sleep_hours?: number | null;
  injury_note?: string;
  notes?: string;
};

export type DailyCheckinRecord = {
  id: string;
  athlete_id: string;
  checkin_date: string;
  readiness: number;
  fatigue: number;
  soreness: number;
  sleep_quality: number;
  sleep_hours?: number | null;
  injury_note: string;
  notes: string;
  readiness_state: ReadinessState;
  created_at: string;
  updated_at: string;
};

export type SessionLogRequest = {
  session_date?: string | null;
  session_type?: string;
  completed?: boolean;
  rpe?: number | null;
  duration_minutes?: number | null;
  plan_id?: string | null;
  notes?: string;
};

export type SessionLogRecord = {
  id: string;
  athlete_id: string;
  plan_id?: string | null;
  session_date: string;
  session_type: string;
  completed: boolean;
  rpe?: number | null;
  duration_minutes?: number | null;
  notes: string;
  created_at: string;
  updated_at: string;
};

export type InjuryFlagCreateRequest = {
  body_area?: string;
  description: string;
  severity?: InjuryFlagSeverity;
};

export type InjuryFlagRecord = {
  id: string;
  athlete_id: string;
  plan_id?: string | null;
  source: string;
  body_area: string;
  description: string;
  severity: InjuryFlagSeverity;
  status: InjuryFlagStatus;
  resolved_at?: string | null;
  created_at: string;
  updated_at: string;
};

export type AdaptationNoteRecord = {
  id: string;
  athlete_id: string;
  plan_id?: string | null;
  checkin_id?: string | null;
  session_log_id?: string | null;
  rule_code: string;
  decision: AdaptationDecisionValue;
  summary: string;
  details: Record<string, unknown>;
  created_at: string;
};

export type ReadinessSummary = {
  state: ReadinessState;
  label: string;
  reasons: string[];
};

export type DailyCheckinResponse = {
  checkin: DailyCheckinRecord;
  readiness: ReadinessSummary;
  adaptation_notes: AdaptationNoteRecord[];
  injury_flag?: InjuryFlagRecord | null;
  admin_review_created: boolean;
};

export type SessionLogResponse = {
  log: SessionLogRecord;
  adaptation_notes: AdaptationNoteRecord[];
  admin_review_created: boolean;
};

export type DashboardCompletionStats = {
  logged_sessions_7d: number;
  completed_sessions_7d: number;
  missed_sessions_7d: number;
  checkins_7d: number;
};

export type AthleteDashboardState = {
  plan?: PlanSummary | null;
  current_week_index?: number | null;
  current_week?: WeeklySchedule | null;
  today?: WeeklyDayEntry | null;
  next_session?: WeeklyDayEntry | null;
  readiness: ReadinessSummary;
  latest_checkin?: DailyCheckinRecord | null;
  checked_in_today: boolean;
  open_injury_flags: InjuryFlagRecord[];
  recent_adaptation_notes: AdaptationNoteRecord[];
  completion: DashboardCompletionStats;
};

export type AdminReviewRecord = {
  id: string;
  athlete_id: string;
  athlete_email: string;
  athlete_name: string;
  adaptation_note_id?: string | null;
  injury_flag_id?: string | null;
  reason: string;
  status: AdminReviewStatus;
  resolution_notes: string;
  resolved_by: string;
  resolved_at?: string | null;
  created_at: string;
};

export type AdminReviewResolveRequest = {
  status: "acknowledged" | "resolved";
  resolution_notes?: string;
};

export type AdminAthleteDailyStatus = {
  athlete_id: string;
  readiness: ReadinessSummary;
  latest_checkin?: DailyCheckinRecord | null;
  open_injury_flags: InjuryFlagRecord[];
  recent_session_logs: SessionLogRecord[];
  recent_adaptation_notes: AdaptationNoteRecord[];
  pending_review_count: number;
};
