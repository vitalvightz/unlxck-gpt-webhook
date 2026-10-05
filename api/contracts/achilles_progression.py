"""Episode-owned Achilles observations, not a clinical promotion criterion."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Literal, Mapping

from pydantic import BaseModel, ConfigDict, Field, AwareDatetime, model_validator
from fightcamp.injury_formatting import parse_injury_entry


CHECKPOINTS = frozenset({"achilles_site_assessed", "achilles_heel_rise_assessed",
                         "achilles_loading_response_assessed", "achilles_range_load_assessed"})


class AchillesProgressionInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    side: Literal["left", "right", "bilateral", "unknown"]
    assessed_at: AwareDatetime
    assessor: Literal["self_reported", "clinician_physio", "coach_observed", "unknown"]
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
        if self.loading_performed_at and self.loading_performed_at > self.assessed_at:
            raise ValueError("Loading must precede assessment")
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


def achilles_identity(injury: Mapping):
    parsed = parse_injury_entry(" ".join(str(injury.get(k) or "") for k in ("body_area", "description"))) or {}
    return ((injury.get("canonical_location") or parsed.get("canonical_location") or injury.get("body_region")),
            (injury.get("injury_type") or injury.get("rehab_type") or parsed.get("injury_type")))


def instant(value):
    try:
        result = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return result if result.tzinfo else None
    except (TypeError, ValueError):
        return None


def read_achilles_checkpoint(checkpoint: str, injury: Mapping, *, setback_at=None, as_of=None, history_truncated=False):
    """PASS means a usable *reported observation*, never clinical readiness.

    Coach reports support observed function, not pathology exclusion or permitted
    loading. Clinical attribution is retained but is never externally verified.
    """
    result = {"status": "unknown", "reason_code": "achilles_observation_missing",
              "observation_id": None, "assessor": "unknown", "externally_verified": False,
              "usable_for_clinical_promotion": False}
    def answer(status, reason):
        return {**result, "status": status, "reason_code": reason}
    if checkpoint not in CHECKPOINTS or achilles_identity(injury) != ("achilles", "tendonitis"):
        return answer("unknown", "achilles_identity_mismatch")
    if injury.get("rehab_medical_gate") or injury.get("latest_reported_status") == "worse":
        return answer("fail", "achilles_medical_or_setback_hold")
    if history_truncated:
        return answer("unknown", "achilles_history_truncated")
    exact = [e for e in injury.get("achilles_progression_observations", ())
             if e.get("event_type") == "achilles_progression_input"
             and all(str(e.get(k)) == str(injury.get(v)) for k, v in (
                 ("athlete_id", "athlete_id"), ("injury_id", "id"), ("injury_episode_id", "episode_id")))]
    if not exact:
        return result
    # A newer incomplete assessment supersedes the whole prior snapshot.
    latest = max(exact, key=lambda e: (instant(e.get("created_at")) or datetime.max.replace(tzinfo=timezone.utc), str(e.get("id") or "")))
    payload = latest.get("payload") or {}
    try:
        assessment = AchillesProgressionInput.model_validate(payload.get("assessment"))
    except ValueError:
        return answer("unknown", "achilles_observation_invalid")
    result.update(observation_id=str(latest.get("id")), assessor=assessment.assessor)
    if (payload.get("region"), payload.get("injury_type"), assessment.side) != (
            "achilles", "tendonitis", injury.get("side")) or assessment.side == "unknown":
        return answer("unknown", "achilles_side_or_type_mismatch")
    recorded = instant(latest.get("created_at"))
    now = as_of or datetime.now(timezone.utc)
    dates = [assessment.assessed_at, assessment.loading_performed_at, assessment.delayed_response_at]
    episode_start = injury.get("achilles_episode_started_at") or instant(injury.get("created_at"))
    if (not recorded or recorded > now or any(d and d > recorded for d in dates)
            or (episode_start and any(d and d < episode_start for d in dates))
            or (setback_at and any(d and d <= setback_at for d in dates))):
        return answer("unknown", "achilles_observation_stale_or_future")
    if payload.get("source") != "athlete_reported" or payload.get("externally_verified") is not False:
        return answer("unknown", "achilles_provenance_invalid")
    if assessment.safety_concern:
        return answer("fail", "achilles_medical_review_required")
    if assessment.assessor == "unknown":
        return answer("unknown", "achilles_assessor_unknown")
    if checkpoint == "achilles_site_assessed":
        known = assessment.site != "unknown"
    elif checkpoint == "achilles_heel_rise_assessed":
        if assessment.heel_rise_completed is True and (assessment.heel_rise_quality == "unable" or assessment.heel_rise_assessor_usable is False):
            return answer("fail", "achilles_heel_rise_report_not_usable")
        known = (assessment.assessor in {"clinician_physio", "coach_observed"}
                 and assessment.heel_rise_completed is True and assessment.heel_rise_quality != "unknown"
                 and assessment.heel_rise_mode != "unknown"
                 and assessment.heel_rise_assessor_usable is True)
    elif checkpoint == "achilles_loading_response_assessed":
        known = (assessment.loading_task != "unknown" and assessment.during_symptoms is not None
                 and assessment.delayed_symptoms is not None)
    else:
        if assessment.range_load_tolerance == "not_tolerated" or assessment.range_load_assessor_usable is False:
            return answer("fail", "achilles_range_load_report_not_usable")
        known = (assessment.assessor == "clinician_physio" and assessment.incompatible_pathology == "excluded"
                 and assessment.range_assessed is True and assessment.permitted_range != "unknown"
                 and assessment.resistance != "unknown" and assessment.range_load_tolerance == "tolerated"
                 and (assessment.resistance != "external" or assessment.resistance_kg is not None)
                 and assessment.range_load_assessor_usable is True)
    return answer("pass" if known else "unknown", "achilles_reported_input_available" if known else "achilles_input_or_source_insufficient")
