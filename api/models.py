from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

UserRole = Literal["athlete", "admin"]
GuidedInjurySeverity = Literal["", "low", "moderate", "high"]
AppearanceMode = Literal["dark", "light"]
SexValue = Literal["male", "female"]
DailyActivityLevel = Literal["low", "mixed", "active_job"]
WeighInType = Literal["same_day", "day_before", "informal"]
PhaseOverride = Literal["GPP", "SPP", "TAPER"]
FatigueLevel = Literal["low", "moderate", "high"]
WeightSource = Literal["manual", "latest_bodyweight_log", "imported"]
TrainingRestrictionLevel = Literal["none", "minor", "moderate", "major"]
SleepQuality = Literal["good", "mixed", "poor"]
AppetiteStatus = Literal["normal", "low", "high"]
FoundationStatus = Literal["incomplete", "sufficient", "complete"]
NutritionWorkspaceSource = Literal["default", "draft", "intake"]
FightWeekOverrideBand = Literal["none", "final_day_protocol", "micro_taper_protocol", "mini_taper_protocol"]
SessionDayType = Literal["hard_spar", "technical", "strength", "conditioning", "recovery", "off"]


GenerationJobStatus = Literal["queued", "running", "completed", "review_required", "failed"]
_RECORD_PATTERN = re.compile(r"^\d+-\d+(?:-\d+)?$")
_ROUNDS_FORMAT_PATTERN = re.compile(r"^(\d+)\s*[xX]\s*(\d+)$")
# Keep this alias map aligned with web/lib/intake-options.ts so the API accepts
# legacy mild/severe inputs while normalizing to the frontend low/moderate/high vocabulary.
_GUIDED_INJURY_SEVERITY_ALIASES = {
    "": "",
    "low": "low",
    "mild": "low",
    "moderate": "moderate",
    "high": "high",
    "severe": "high",
}


def _clean_list(values: list[str] | None) -> list[str]:
    return [str(value).strip() for value in values or [] if str(value).strip()]


def _field(label: str, value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        value = _clean_list(value)
    elif value is None:
        value = ""
    return {"label": label, "value": value}


def _validate_record(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized and not _RECORD_PATTERN.fullmatch(normalized):
        raise ValueError("record must use x-x or x-x-x format")
    return normalized


def _validate_rounds_format(value: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        return ""
    match = _ROUNDS_FORMAT_PATTERN.fullmatch(normalized)
    if not match:
        raise ValueError("rounds_format must use numeric rounds x minutes format like 3 x 3")
    return f"{int(match[1])} x {int(match[2])}"


class AthleteProfileInput(BaseModel):
    full_name: str
    sex: SexValue | None = None
    age: int | None = None
    weight_kg: float | None = None
    target_weight_kg: float | None = None
    height_cm: int | None = None
    technical_style: list[str] = Field(default_factory=list)
    tactical_style: list[str] = Field(default_factory=list)
    stance: str = ""
    professional_status: str = ""
    record: str = ""
    athlete_timezone: str = ""
    athlete_locale: str = ""

    @field_validator("record")
    @classmethod
    def validate_record(cls, value: str) -> str:
        return _validate_record(value)

    @field_validator("height_cm", mode="before")
    @classmethod
    def coerce_height_cm(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            try:
                return int(round(float(normalized)))
            except ValueError:
                raise ValueError("height_cm must be numeric") from None
        if isinstance(value, (int, float)):
            return int(round(float(value)))
        return value


class GuidedInjuryInput(BaseModel):
    area: str = ""
    severity: GuidedInjurySeverity = ""
    trend: str = ""
    avoid: str = ""
    notes: str = ""

    @field_validator("severity", mode="before")
    @classmethod
    def validate_severity(cls, value: Any) -> GuidedInjurySeverity:
        normalized = str(value or "").strip().lower()
        mapped = _GUIDED_INJURY_SEVERITY_ALIASES.get(normalized)
        if mapped is None:
            raise ValueError("guided injury severity must be one of low, moderate, or high")
        return mapped


class NutritionProfileInput(BaseModel):
    sex: SexValue | None = None
    age: int | None = None
    height_cm: int | None = None
    daily_activity_level: DailyActivityLevel | None = None
    dietary_restrictions: list[str] = Field(default_factory=list)
    food_preferences: list[str] = Field(default_factory=list)
    meals_per_day_preference: int | None = None
    foods_avoided_pre_session: list[str] = Field(default_factory=list)
    foods_avoided_fight_week: list[str] = Field(default_factory=list)
    supplement_use: list[str] = Field(default_factory=list)
    caffeine_use: bool | None = None

    @field_validator(
        "dietary_restrictions",
        "food_preferences",
        "foods_avoided_pre_session",
        "foods_avoided_fight_week",
        "supplement_use",
        mode="before",
    )
    @classmethod
    def clean_list_fields(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return _clean_list([part.strip() for part in value.split(",")])
        if isinstance(value, list):
            return _clean_list(value)
        return _clean_list([value])

    @field_validator("height_cm", mode="before")
    @classmethod
    def coerce_height_cm_value(cls, value: Any) -> Any:
        return AthleteProfileInput.coerce_height_cm(value)

    @field_validator("age", "meals_per_day_preference", mode="before")
    @classmethod
    def coerce_int_fields(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            try:
                return int(round(float(normalized)))
            except ValueError:
                raise ValueError("value must be numeric") from None
        if isinstance(value, (int, float)):
            return int(round(float(value)))
        return value


class NutritionBodyweightLogEntry(BaseModel):
    date: str
    weight_kg: float
    time: str | None = None
    is_fasted: bool | None = None
    notes: str | None = None

    @field_validator("date")
    @classmethod
    def validate_date(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("date is required")
        return normalized

    @field_validator("weight_kg", mode="before")
    @classmethod
    def coerce_weight(cls, value: Any) -> Any:
        if value is None:
            raise ValueError("weight_kg is required")
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                raise ValueError("weight_kg is required")
            try:
                return float(normalized)
            except ValueError:
                raise ValueError("weight_kg must be numeric") from None
        return value


class NutritionReadinessInput(BaseModel):
    sleep_quality: SleepQuality | None = None
    appetite_status: AppetiteStatus | None = None


class NutritionMonitoringInput(BaseModel):
    daily_bodyweight_log: list[NutritionBodyweightLogEntry] = Field(default_factory=list)


class NutritionCoachControlsInput(BaseModel):
    coach_override_enabled: bool = False
    athlete_override_enabled: bool = False
    do_not_reduce_below_calories: int | None = None
    protein_floor_g_per_kg: float | None = None
    fight_week_manual_mode: bool = False
    water_cut_locked_to_manual: bool = False

    @field_validator("do_not_reduce_below_calories", mode="before")
    @classmethod
    def coerce_optional_int(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            try:
                return int(round(float(normalized)))
            except ValueError:
                raise ValueError("value must be numeric") from None
        if isinstance(value, (int, float)):
            return int(round(float(value)))
        return value

    @field_validator("protein_floor_g_per_kg", mode="before")
    @classmethod
    def coerce_optional_float(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            try:
                return float(normalized)
            except ValueError:
                raise ValueError("value must be numeric") from None
        return value


class NutritionSandCPreferences(BaseModel):
    equipment_access: list[str] = Field(default_factory=list)
    key_goals: list[str] = Field(default_factory=list)
    weak_areas: list[str] = Field(default_factory=list)
    training_preference: str = ""
    mindset_challenges: str = ""
    notes: str = ""
    random_seed: int | None = None

    @field_validator("equipment_access", "key_goals", "weak_areas", mode="before")
    @classmethod
    def clean_array_fields(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return _clean_list([part.strip() for part in value.split(",")])
        if isinstance(value, list):
            return _clean_list(value)
        return _clean_list([value])


class NutritionSharedCampContext(BaseModel):
    fight_date: str = ""
    rounds_format: str = ""
    weigh_in_type: WeighInType | None = None
    weigh_in_time: str | None = None
    current_weight_kg: float | None = None
    current_weight_recorded_at: str | None = None
    current_weight_source: WeightSource | None = None
    target_weight_kg: float | None = None
    target_weight_range_kg: list[float] | None = None
    phase_override: PhaseOverride | None = None
    fatigue_level: FatigueLevel | None = None
    weekly_training_frequency: int | None = None
    training_availability: list[str] = Field(default_factory=list)
    hard_sparring_days: list[str] = Field(default_factory=list)
    technical_skill_days: list[str] = Field(default_factory=list)
    session_types_by_day: dict[str, SessionDayType] = Field(default_factory=dict)
    injuries: str = ""
    guided_injury: GuidedInjuryInput | None = None
    training_restriction_level: TrainingRestrictionLevel | None = None

    @field_validator(
        "training_availability",
        "hard_sparring_days",
        "technical_skill_days",
        mode="before",
    )
    @classmethod
    def clean_day_arrays(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            return _clean_list([part.strip() for part in value.split(",")])
        if isinstance(value, list):
            return _clean_list(value)
        return _clean_list([value])

    @field_validator("rounds_format")
    @classmethod
    def validate_rounds_format(cls, value: str) -> str:
        return _validate_rounds_format(value)

    @field_validator("target_weight_range_kg", mode="before")
    @classmethod
    def validate_target_weight_range(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            parts = [part.strip() for part in stripped.split(",") if part.strip()]
        elif isinstance(value, list):
            parts = value
        else:
            raise ValueError("target_weight_range_kg must be a two-value array")

        if len(parts) != 2:
            raise ValueError("target_weight_range_kg must contain [lower, upper]")

        try:
            lower = float(parts[0])
            upper = float(parts[1])
        except (TypeError, ValueError):
            raise ValueError("target_weight_range_kg values must be numeric") from None
        if lower <= 0 or upper <= 0:
            raise ValueError("target_weight_range_kg values must be positive")
        if lower > upper:
            raise ValueError("target_weight_range_kg lower bound must be <= upper bound")
        return [lower, upper]

    @field_validator("current_weight_kg", "target_weight_kg", mode="before")
    @classmethod
    def coerce_optional_weight(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            try:
                return float(normalized)
            except ValueError:
                raise ValueError("weight value must be numeric") from None
        return value

    @field_validator("weekly_training_frequency", mode="before")
    @classmethod
    def coerce_frequency(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            try:
                value = int(round(float(normalized)))
            except ValueError:
                raise ValueError("weekly_training_frequency must be numeric") from None
        if isinstance(value, (int, float)):
            return max(1, min(int(round(float(value))), 6))
        return value

    @field_validator("session_types_by_day", mode="before")
    @classmethod
    def clean_session_types_by_day(cls, value: Any) -> dict[str, SessionDayType]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("session_types_by_day must be an object")
        cleaned: dict[str, SessionDayType] = {}
        for key, entry in value.items():
            day = str(key or "").strip().lower()
            normalized_entry = str(entry or "").strip().lower()
            if day and normalized_entry:
                cleaned[day] = normalized_entry  # type: ignore[assignment]
        return cleaned


class NutritionDerivedState(BaseModel):
    days_until_fight: int | None = None
    weight_cut_pct: float = 0.0
    weight_cut_risk: bool = False
    aggressive_weight_cut: bool = False
    high_pressure_weight_cut: bool = False
    short_notice: bool = False
    fight_week: bool = False
    readiness_flags: list[str] = Field(default_factory=list)
    fight_week_override_band: FightWeekOverrideBand = "none"
    current_phase_effective: str | None = None
    rolling_7_day_average_weight: float | None = None
    foundation_status: FoundationStatus = "incomplete"
    missing_required_fields: list[str] = Field(default_factory=list)


class NutritionWorkspaceState(BaseModel):
    athlete_id: str
    source: NutritionWorkspaceSource = "default"
    intake_id: str | None = None
    nutrition_profile: NutritionProfileInput = Field(default_factory=NutritionProfileInput)
    shared_camp_context: NutritionSharedCampContext = Field(default_factory=NutritionSharedCampContext)
    s_and_c_preferences: NutritionSandCPreferences = Field(default_factory=NutritionSandCPreferences)
    nutrition_readiness: NutritionReadinessInput = Field(default_factory=NutritionReadinessInput)
    nutrition_monitoring: NutritionMonitoringInput = Field(default_factory=NutritionMonitoringInput)
    nutrition_coach_controls: NutritionCoachControlsInput = Field(default_factory=NutritionCoachControlsInput)
    derived: NutritionDerivedState = Field(default_factory=NutritionDerivedState)


class NutritionWorkspaceUpdateRequest(BaseModel):
    nutrition_profile: NutritionProfileInput = Field(default_factory=NutritionProfileInput)
    shared_camp_context: NutritionSharedCampContext = Field(default_factory=NutritionSharedCampContext)
    s_and_c_preferences: NutritionSandCPreferences = Field(default_factory=NutritionSandCPreferences)
    nutrition_readiness: NutritionReadinessInput = Field(default_factory=NutritionReadinessInput)
    nutrition_monitoring: NutritionMonitoringInput = Field(default_factory=NutritionMonitoringInput)
    nutrition_coach_controls: NutritionCoachControlsInput = Field(default_factory=NutritionCoachControlsInput)

    @field_validator("shared_camp_context")
    @classmethod
    def validate_weight_context(cls, value: NutritionSharedCampContext) -> NutritionSharedCampContext:
        if value.current_weight_kg is not None and value.current_weight_source is None:
            raise ValueError("current_weight_source is required when current_weight_kg is set")
        if value.current_weight_source == "manual" and not str(value.current_weight_recorded_at or "").strip():
            raise ValueError("current_weight_recorded_at is required when current_weight_source is manual")
        return value


class PlanRequest(BaseModel):
    athlete: AthleteProfileInput
    fight_date: str
    rounds_format: str = ""
    weekly_training_frequency: int | None = None
    fatigue_level: str = ""
    equipment_access: list[str] = Field(default_factory=list)
    training_availability: list[str] = Field(default_factory=list)
    hard_sparring_days: list[str] = Field(default_factory=list)
    technical_skill_days: list[str] = Field(default_factory=list)
    injuries: str = ""
    guided_injury: GuidedInjuryInput | None = None
    key_goals: list[str] = Field(default_factory=list)
    weak_areas: list[str] = Field(default_factory=list)
    training_preference: str = ""
    mindset_challenges: str = ""
    notes: str = ""
    random_seed: int | None = None

    @field_validator("weekly_training_frequency", mode="before")
    @classmethod
    def validate_weekly_training_frequency(cls, value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, str):
            normalized = value.strip()
            if not normalized:
                return None
            try:
                value = int(round(float(normalized)))
            except ValueError:
                raise ValueError("weekly_training_frequency must be numeric") from None
        if isinstance(value, (int, float)):
            return max(1, min(int(round(float(value))), 6))
        return value

    @field_validator("rounds_format")
    @classmethod
    def validate_rounds_format(cls, value: str) -> str:
        return _validate_rounds_format(value)

    def to_payload(self) -> dict[str, Any]:
        athlete = self.athlete
        fields = [
            _field("Full name", athlete.full_name),
            _field("Sex", athlete.sex),
            _field("Age", athlete.age),
            _field("Weight (kg)", athlete.weight_kg),
            _field("Target Weight (kg)", athlete.target_weight_kg),
            _field("Height (cm)", athlete.height_cm),
            _field("Fighting Style (Technical)", athlete.technical_style),
            _field("Fighting Style (Tactical)", athlete.tactical_style),
            _field("Stance", athlete.stance),
            _field("Professional Status", athlete.professional_status),
            _field("Current Record", athlete.record),
            _field("When is your next fight?", self.fight_date),
            _field("Athlete Time Zone", athlete.athlete_timezone),
            _field("Rounds x Minutes", self.rounds_format),
            _field("Sessions per Week", self.weekly_training_frequency),
            _field("Fatigue Level", self.fatigue_level),
            _field("Equipment Access", self.equipment_access),
            _field("Training Availability", self.training_availability),
            _field("Hard Sparring Days", self.hard_sparring_days),
            _field("Technical Skill Days", self.technical_skill_days),
            _field("Any injuries or areas you need to work around?", self.injuries),
            _field("What are your key performance goals?", self.key_goals),
            _field("Where do you feel weakest right now?", self.weak_areas),
            _field("Do you prefer certain training styles?", self.training_preference),
            _field(
                "Do you struggle with any mental blockers or mindset challenges?",
                self.mindset_challenges,
            ),
            _field(
                "Are there any parts of your previous plan you hated or loved?",
                self.notes,
            ),
        ]
        payload: dict[str, Any] = {"data": {"fields": fields}}
        if self.guided_injury is not None:
            payload["guided_injury"] = self.guided_injury.model_dump(mode="json")
        if self.random_seed is not None:
            payload["random_seed"] = self.random_seed
        return payload


class ProfileUpdateRequest(BaseModel):
    full_name: str | None = None
    technical_style: list[str] | None = None
    tactical_style: list[str] | None = None
    stance: str | None = None
    professional_status: str | None = None
    record: str | None = None
    athlete_timezone: str | None = None
    athlete_locale: str | None = None
    appearance_mode: AppearanceMode | None = None
    onboarding_draft: dict[str, Any] | None = None
    avatar_url: str | None = None
    nutrition_profile: NutritionProfileInput | None = None

    @field_validator("record")
    @classmethod
    def validate_record(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _validate_record(value)


class ManualStage2SubmissionRequest(BaseModel):
    final_plan_text: str

    @field_validator("final_plan_text")
    @classmethod
    def validate_final_plan_text(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("final_plan_text is required")
        return normalized


class PlanRenameRequest(BaseModel):
    plan_name: str

    @field_validator("plan_name")
    @classmethod
    def validate_plan_name(cls, value: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError("plan_name is required")
        return normalized


class ProfileRecord(BaseModel):
    athlete_id: str
    email: str
    role: UserRole
    full_name: str
    technical_style: list[str] = Field(default_factory=list)
    tactical_style: list[str] = Field(default_factory=list)
    stance: str = ""
    professional_status: str = ""
    record: str = ""
    athlete_timezone: str = ""
    athlete_locale: str = ""
    appearance_mode: AppearanceMode = "dark"
    onboarding_draft: dict[str, Any] | None = None
    avatar_url: str | None = None
    nutrition_profile: NutritionProfileInput = Field(default_factory=NutritionProfileInput)
    created_at: str
    updated_at: str


class PlanSummary(BaseModel):
    plan_id: str
    plan_name: str | None = None
    athlete_id: str
    full_name: str
    fight_date: str = ""
    technical_style: list[str] = Field(default_factory=list)
    created_at: str
    status: str = "generated"
    pdf_url: str | None = None


class PlanOutputs(BaseModel):
    plan_text: str
    pdf_url: str | None = None


class PlanAdvisory(BaseModel):
    kind: Literal["sparring_adjustment"]
    action: Literal["deload", "convert"]
    risk_band: Literal["green", "amber", "red", "black"] | None = None
    phase: str
    week_label: str
    days: list[str] = Field(default_factory=list)
    title: str
    reason: str
    suggestion: str
    replacement: str | None = None
    disclaimer: str


class AdminPlanOutputs(BaseModel):
    coach_notes: str = ""
    why_log: dict[str, Any] = Field(default_factory=dict)
    planning_brief: dict[str, Any] | None = None
    stage2_payload: dict[str, Any] | None = None
    stage2_handoff_text: str = ""
    draft_plan_text: str = ""
    final_plan_text: str = ""
    stage2_retry_text: str = ""
    stage2_validator_report: dict[str, Any] = Field(default_factory=dict)
    stage2_status: str = ""
    stage2_attempt_count: int = 0


class PlanDetail(PlanSummary):
    outputs: PlanOutputs
    advisories: list[PlanAdvisory] = Field(default_factory=list)
    admin_outputs: AdminPlanOutputs | None = None


class GenerationJobResponse(BaseModel):
    job_id: str
    athlete_id: str
    client_request_id: str
    status: GenerationJobStatus
    created_at: str
    updated_at: str
    started_at: str | None = None
    completed_at: str | None = None
    error: str | None = None
    plan_id: str | None = None
    latest_plan_id: str | None = None


class MeResponse(BaseModel):
    profile: ProfileRecord
    latest_intake: dict[str, Any] | None = None
    latest_plan: PlanSummary | None = None
    plan_count: int = 0


class AdminAthleteRecord(BaseModel):
    athlete_id: str
    email: str
    role: UserRole
    full_name: str
    technical_style: list[str] = Field(default_factory=list)
    tactical_style: list[str] = Field(default_factory=list)
    stance: str = ""
    professional_status: str = ""
    record: str = ""
    athlete_timezone: str = ""
    athlete_locale: str = ""
    appearance_mode: AppearanceMode = "dark"
    onboarding_draft: dict[str, Any] | None = None
    latest_intake: dict[str, Any] | None = None
    nutrition_profile: NutritionProfileInput = Field(default_factory=NutritionProfileInput)
    created_at: str
    updated_at: str
    plan_count: int = 0
    latest_plan_created_at: str | None = None


class AdminPlanSummary(PlanSummary):
    athlete_email: str
