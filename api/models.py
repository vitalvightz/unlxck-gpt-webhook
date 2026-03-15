from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

UserRole = Literal["athlete", "admin"]
_RECORD_PATTERN = re.compile(r"^\d+-\d+(?:-\d+)?$")


def _clean_list(values: list[str] | None) -> list[str]:
    return [str(value).strip() for value in values or [] if str(value).strip()]


def _field(label: str, value: Any) -> dict[str, Any]:
    if isinstance(value, list):
        cleaned = _clean_list(value)
        value = cleaned if cleaned else ""
    elif value is None:
        value = ""
    return {"label": label, "value": value}


def _validate_record(value: str) -> str:
    normalized = str(value or "").strip()
    if normalized and not _RECORD_PATTERN.fullmatch(normalized):
        raise ValueError("record must use x-x or x-x-x format")
    return normalized


class AthleteProfileInput(BaseModel):
    full_name: str
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
    key_goals: list[str] = Field(default_factory=list)
    weak_areas: list[str] = Field(default_factory=list)
    training_preference: str = ""
    mindset_challenges: str = ""
    notes: str = ""
    random_seed: int | None = None

    def to_payload(self) -> dict[str, Any]:
        athlete = self.athlete
        fields = [
            _field("Full name", athlete.full_name),
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
    onboarding_draft: dict[str, Any] | None = None
    avatar_url: str | None = None

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
    onboarding_draft: dict[str, Any] | None = None
    avatar_url: str | None = None
    created_at: str
    updated_at: str


class PlanSummary(BaseModel):
    plan_id: str
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
    admin_outputs: AdminPlanOutputs | None = None


class MeResponse(BaseModel):
    profile: ProfileRecord
    latest_intake: dict[str, Any] | None = None
    plans: list[PlanSummary] = Field(default_factory=list)


class AdminAthleteRecord(BaseModel):
    athlete_id: str
    email: str
    role: UserRole
    full_name: str
    technical_style: list[str] = Field(default_factory=list)
    athlete_timezone: str = ""
    created_at: str
    updated_at: str
    plan_count: int = 0
    latest_plan_created_at: str | None = None


class AdminPlanSummary(PlanSummary):
    athlete_email: str
