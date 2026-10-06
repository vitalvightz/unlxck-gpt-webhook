"""Episode-owned Achilles observations, not a clinical promotion criterion."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator


class AchillesProgressionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    site: Literal["midportion", "insertional", "unknown"] = "unknown"
    incompatible_pathology: Literal["excluded", "suspected", "not_assessed", "unknown"] = "not_assessed"
    suspected_rupture: bool | None = Field(default=None, strict=True)
    marked_weakness: bool | None = Field(default=None, strict=True)
    traumatic_loss_of_function: bool | None = Field(default=None, strict=True)
    clinician_restriction: bool | None = Field(default=None, strict=True)
    heel_rise_completed: bool | None = Field(default=None, strict=True)
    heel_rise_mode: Literal["single_leg", "double_leg", "unknown"] = "unknown"
    heel_rise_quality: Literal["controlled", "reduced_control", "unable", "unknown"] = "unknown"
    heel_rise_repetitions: int | None = Field(default=None, strict=True, ge=0)
    heel_rise_assessor_usable: bool | None = Field(default=None, strict=True)
    loading_performed_at: AwareDatetime | None = None
    loading_task: Literal["heel_rise_assessment", "clinician_selected", "unknown"] = "unknown"
    during_symptoms: float | None = Field(default=None, strict=True, ge=0, le=10)
    delayed_symptoms: float | None = Field(default=None, strict=True, ge=0, le=10)
    delayed_response_at: AwareDatetime | None = None
    range_assessed: bool | None = Field(default=None, strict=True)
    permitted_range: Literal["floor_level", "clinician_limited", "unknown"] = "unknown"
    resistance: Literal["bodyweight", "external", "unknown"] = "unknown"
    resistance_kg: float | None = Field(default=None, strict=True, ge=0)
    range_load_tolerance: Literal["tolerated", "not_tolerated", "unknown"] = "unknown"
    range_load_assessor_usable: bool | None = Field(default=None, strict=True)

    @model_validator(mode="after")
    def consistent_observation(self):
        if self.delayed_response_at and (not self.loading_performed_at or self.delayed_response_at <= self.loading_performed_at):
            raise ValueError("Delayed response must follow the observed loading")
        if self.delayed_symptoms is not None and not self.delayed_response_at:
            raise ValueError("Delayed symptoms require their observation timestamp")
        if self.during_symptoms is not None and not self.loading_performed_at:
            raise ValueError("Symptoms require an actual loading observation")
        if self.heel_rise_completed is not True and (self.heel_rise_mode != "unknown" or self.heel_rise_quality != "unknown" or self.heel_rise_repetitions is not None or self.heel_rise_assessor_usable is True):
            raise ValueError("Heel-rise results require a completed assessment")
        if self.range_assessed is not True and (self.permitted_range != "unknown" or self.range_load_assessor_usable is True):
            raise ValueError("Range results require an assessment")
        if self.resistance_kg is not None and self.resistance != "external":
            raise ValueError("External resistance must be identified")
        return self

    @property
    def safety_concern(self):
        return self.incompatible_pathology == "suspected" or any(getattr(self, k) is True for k in (
            "suspected_rupture", "marked_weakness", "traumatic_loss_of_function", "clinician_restriction"))


def read_achilles_input(checkpoint: str, envelope):
    """Interpret availability only. No sourced readiness threshold is defined."""
    assessment = envelope.payload
    result = {"status": "unknown", "reason_code": "achilles_input_or_source_insufficient"}
    def answer(status, reason):
        return {**result, "status": status, "reason_code": reason}
    if envelope.assessor == "unknown":
        return answer("unknown", "achilles_assessor_unknown")
    if checkpoint == "achilles_site_assessed":
        known = assessment.site != "unknown"
    elif checkpoint == "achilles_heel_rise_assessed":
        if assessment.heel_rise_completed is True and (assessment.heel_rise_quality == "unable" or assessment.heel_rise_assessor_usable is False):
            return answer("fail", "achilles_heel_rise_report_not_usable")
        known = (envelope.assessor in {"clinician_physio", "coach_observed"}
                 and assessment.heel_rise_completed is True and assessment.heel_rise_quality != "unknown"
                 and assessment.heel_rise_mode != "unknown"
                 and assessment.heel_rise_assessor_usable is True)
    elif checkpoint == "achilles_loading_response_assessed":
        known = (assessment.loading_task != "unknown" and assessment.during_symptoms is not None
                 and assessment.delayed_symptoms is not None)
    elif checkpoint == "achilles_range_load_assessed":
        if assessment.range_load_tolerance == "not_tolerated" or assessment.range_load_assessor_usable is False:
            return answer("fail", "achilles_range_load_report_not_usable")
        known = (envelope.assessor == "clinician_physio" and assessment.incompatible_pathology == "excluded"
                 and assessment.range_assessed is True and assessment.permitted_range != "unknown"
                 and assessment.resistance != "unknown" and assessment.range_load_tolerance == "tolerated"
                 and (assessment.resistance != "external" or assessment.resistance_kg is not None)
                 and assessment.range_load_assessor_usable is True)
    else:
        return answer("unknown", "assessment_input_not_registered")
    return answer("pass" if known else "unknown", "achilles_reported_input_available" if known else "achilles_input_or_source_insufficient")
