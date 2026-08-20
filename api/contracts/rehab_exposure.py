"""Canonical, injury-attributable rehabilitation exposure observations.

This contract records observations only.  It deliberately contains no
"tolerated" flag or clinical threshold.  In particular, session completion,
camp phase and whole-athlete pain are not inputs to this model.

Unknown demand is recordable, and is not capacity evidence
----------------------------------------------------------
``load``, ``impact`` and ``velocity`` accept ``"unknown"``. A drill whose
physical demand has not been reviewed still produces a real, storable
observation: the athlete did the work, and the injury responded a particular
way. Refusing to store that loses evidence for no safety gain.

What an unknown level must never do is count as *positive* evidence of capacity.
"Demand not stated" is not "demand was low". :attr:`RehabExposureEvent.has_unknown_demand`
marks exactly those events, and later progression logic must exclude them from
LOAD / DYNAMIC / RETURN qualification.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal, Mapping
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

from fightcamp.rehab_schema import canonical_rehab_locations
from fightcamp.injury_body_region import injury_body_region_context
from fightcamp.injury_formatting import extract_laterality

ExposureSide = Literal["left", "right", "bilateral", "unknown"]
#: ``"unknown"`` is a valid, recordable demand level. An exposure whose demand
#: carries one is a real observation and is stored as such — but it is NOT
#: positive evidence of what the tissue tolerated, because nobody has stated
#: what the drill actually demanded. :attr:`RehabExposureEvent.has_unknown_demand`
#: is the flag later progression logic must honour; see the module docstring.
DEMAND_UNKNOWN = "unknown"
DemandLevel = Literal["unknown", "minimal", "low", "moderate", "high"]
ImpactLevel = Literal["unknown", "none", "low", "moderate", "high"]
VelocityLevel = Literal["unknown", "low", "moderate", "high"]
NextDayResponse = Literal["better", "same", "worse", "not_yet_known", "not_sure"]
#: How the injury felt *during* the rehab work. Mirrors NextDayResponse, minus
#: "not_yet_known" (which cannot apply to something already done) and plus
#: "not_reported" — the default for an exposure logged without the athlete being
#: asked, so "we did not ask" is never stored as "the athlete said nothing was
#: wrong".
DuringResponse = Literal["better", "same", "worse", "not_sure", "not_reported"]
PainObservation = StrictInt | Literal["not_sure"] | None


def injury_evidence_identity(body_area: str, description: str) -> dict[str, str | None]:
    """Resolve the server-owned region and side stored with an injury flag."""
    context = injury_body_region_context(body_area, description)
    combined = " ".join(part for part in (body_area, description) if part)
    side = "bilateral" if "bilateral" in combined.lower() else extract_laterality(combined)
    return {"body_region": context.get("canonical_location"), "side": side or "unknown"}


class ExposureDemand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_regions: list[str] = Field(min_length=1)
    target_tissues: list[str] | None = None
    load: DemandLevel
    impact: ImpactLevel
    velocity: VelocityLevel
    contraction_type: list[Literal["isometric", "concentric", "eccentric", "mixed", "unknown"]] | None = None
    sport_specificity: Literal["general_rehab", "combat_sport", "unknown"] = "unknown"
    contact_level: Literal["none", "controlled", "full", "unknown"] | None = None
    resistance_type: Literal["assisted", "bodyweight", "external_load", "unknown"] | None = None
    rom_context: str | None = Field(default=None, max_length=200)

    @property
    def has_unknown_level(self) -> bool:
        """True when any required physical demand is unstated.

        The exposure is still recorded — an athlete did do the work, and that is
        worth knowing. What it cannot do is evidence *how much* the tissue
        tolerated, because the demand it met is not known.
        """
        return DEMAND_UNKNOWN in (self.load, self.impact, self.velocity)


class ExposureDose(BaseModel):
    model_config = ConfigDict(extra="forbid")
    sets: int | None = Field(default=None, ge=0)
    reps: int | None = Field(default=None, ge=0)
    duration_seconds: float | None = Field(default=None, ge=0)
    external_load_kg: float | None = Field(default=None, ge=0)
    distance_metres: float | None = Field(default=None, ge=0)
    hold_seconds: float | None = Field(default=None, ge=0)
    completed_fraction: float | None = Field(default=None, ge=0, le=1)
    stopped_early: bool | None = None

    @model_validator(mode="after")
    def _require_one_observation(self) -> "ExposureDose":
        if not any(getattr(self, name) is not None for name in type(self).model_fields):
            raise ValueError("dose must contain at least one observed value")
        return self


class ExposureResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    #: The athlete's categorical answer to "how did it feel during the rehab
    #: work?". Deliberately separate from ``pain_during``: a 0-10 score is a
    #: different observation, and inventing one from a better/same/worse answer
    #: would fabricate precision the athlete never gave.
    during_response: DuringResponse = "not_reported"
    pain_during: PainObservation = Field(default=None)
    pain_immediate_after: PainObservation = Field(default=None)
    next_day_response: NextDayResponse = "not_yet_known"
    stopped_due_to_symptoms: bool | None = None
    worsening_reported: bool | None = None

    @model_validator(mode="after")
    def _validate_pain_range(self) -> "ExposureResponse":
        for name in ("pain_during", "pain_immediate_after"):
            value = getattr(self, name)
            if isinstance(value, int) and not 0 <= value <= 10:
                raise ValueError(f"{name} must be between 0 and 10")
        return self


class ExposureProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["athlete_logged_rehab", "clinician_logged_rehab", "coach_logged_rehab"]
    recorded_at: datetime


class RehabExposureEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exposure_id: UUID
    injury_id: UUID
    injury_episode_id: UUID
    drill_id: str = Field(min_length=1, pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    body_region: str
    side: ExposureSide
    demand: ExposureDemand
    prescribed_dose: ExposureDose | None = None
    dose_completed: ExposureDose
    response: ExposureResponse = Field(default_factory=ExposureResponse)
    occurred_at: datetime
    provenance: ExposureProvenance

    @model_validator(mode="after")
    def _validate_region_identity(self) -> "RehabExposureEvent":
        valid = canonical_rehab_locations()
        if self.body_region not in valid:
            raise ValueError("body_region is not in the injury location registry")
        invalid_targets = sorted(set(self.demand.target_regions) - valid)
        if invalid_targets:
            raise ValueError(f"target_regions are not in the injury location registry: {invalid_targets}")
        if self.body_region not in self.demand.target_regions:
            raise ValueError("demand.target_regions must include body_region")
        return self

    @property
    def has_unknown_demand(self) -> bool:
        """Whether this observation may count toward progression qualification.

        ``True`` means it may **not**. The exposure is valid evidence that the
        work happened and how the injury responded; it is not evidence of
        capacity, because the demand it represents was never stated. PR4 must
        exclude these from LOAD/DYNAMIC/RETURN qualification rather than
        treating an unstated demand as a low one.
        """
        return self.demand.has_unknown_level

    def is_attributable_to(self, injury: Mapping[str, object]) -> bool:
        """Match identity only; this never interprets the response as tolerated."""
        if str(injury.get("id") or "") != str(self.injury_id):
            return False
        if str(injury.get("episode_id") or "") != str(self.injury_episode_id):
            return False
        if injury.get("body_region") != self.body_region:
            return False
        injury_side = injury.get("side")
        if injury_side in (None, "unknown") or self.side == "unknown":
            return False
        return self.side == "bilateral" or injury_side == "bilateral" or self.side == injury_side
