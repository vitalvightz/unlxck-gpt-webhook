"""Rehab pathway families, regional profiles and declared stage transitions.

A live rehab policy is composed, not hand-written per injury::

    pathway family            shared stage ladder and transition structure
    + regional profile        location, injury type, reviewed drills, bundles,
                              restrictions, region-specific criteria, exceptions
    = ClinicalPolicy          the object the resolver, scheduler and Today use

CALM and RESTORE are reached by the baseline injury report ladder
(``api.contracts.rehab_stage``). Every higher stage is reached only through a
declared transition whose requirements the episode's own exposure history
satisfies (``api.contracts.rehab_progression``).

Requirement bases keep three different kinds of rule apart:

* ``clinical`` — a source-backed readiness criterion. It must cite sources. A
  transition with no clinical requirement can never promote anyone.
* ``product_safety`` — app-wide safety invariants already enforced elsewhere
  (never progress on a worse, stopped or unknown response). Never a readiness
  claim, and a profile cannot remove one.
* ``data_sufficiency`` — enough observation exists to evaluate the transition at
  all. An observation count here is labelled as a product data requirement, not
  as clinical readiness.

Families carry no clinical requirements unless a source supports them for the
whole family. Wound care is a separate care pathway and is not a family here.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .rehab_schema import REHAB_STAGES

Stage = Literal["calm", "restore", "load", "dynamic", "return"]
RequirementKind = Literal[
    "completed_reviewed_exposure",
    "during_session_response",
    "next_day_response",
    "no_unresolved_setback",
    "complete_history",
    "measured_dose",
    "functional_checkpoint",
    "input_availability",
    "minimum_observations",
]
RequirementBasis = Literal["clinical", "product_safety", "data_sufficiency"]
_RESPONSE_KINDS = frozenset({"during_session_response", "next_day_response"})
#: CALM -> RESTORE is the baseline report ladder, never a declared transition.
TRANSITION_STAGES: tuple[tuple[str, str], ...] = (("restore", "load"), ("load", "dynamic"), ("dynamic", "return"))


def transition_key(from_stage: str, to_stage: str) -> str:
    return f"{from_stage}->{to_stage}"


class TransitionRequirement(BaseModel):
    """One piece of evidence a transition needs. Data, not code."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    requirement_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    kind: RequirementKind
    basis: RequirementBasis
    description: str = Field(min_length=1)
    sources: list[str] = Field(default_factory=list)
    allowed_responses: list[Literal["better", "same"]] = Field(default_factory=list)
    requires_defined_dose: bool = False
    checkpoint: str | None = None
    minimum: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def coherent(self):
        if self.basis == "clinical" and not [s for s in self.sources if s.strip()]:
            raise ValueError("clinical requirements must cite sources")
        if self.basis != "clinical" and self.sources:
            raise ValueError("only clinical requirements cite clinical sources")
        if (self.kind in _RESPONSE_KINDS) != bool(self.allowed_responses):
            raise ValueError("response requirements, and only they, declare allowed responses")
        if (self.kind in {"functional_checkpoint", "input_availability"}) != bool(self.checkpoint):
            raise ValueError("clinical checkpoints and input availability name a checkpoint")
        if self.kind == "functional_checkpoint" and self.basis != "clinical":
            raise ValueError("a functional checkpoint is a clinical criterion")
        if self.kind == "input_availability" and self.basis != "data_sufficiency":
            raise ValueError("input availability is data sufficiency, never clinical readiness")
        if (self.kind == "minimum_observations") != (self.minimum is not None):
            raise ValueError("observation minimums, and only they, declare a minimum")
        if self.requires_defined_dose and self.kind != "completed_reviewed_exposure":
            raise ValueError("only completed exposure can require a defined dose")
        return self


class PathwayTransition(BaseModel):
    """A composed transition. Promotable only when open and clinically specified."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    from_stage: Literal["restore", "load", "dynamic"]
    to_stage: Literal["load", "dynamic", "return"]
    requirements: list[TransitionRequirement] = Field(default_factory=list)
    closed_reason: str | None = None

    @model_validator(mode="after")
    def consecutive(self):
        if REHAB_STAGES.index(self.to_stage) != REHAB_STAGES.index(self.from_stage) + 1:
            raise ValueError("stage transitions must be consecutive")
        ids = [r.requirement_id for r in self.requirements]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate transition requirement")
        if self.closed_reason is not None and not self.closed_reason.strip():
            raise ValueError("a closed transition needs a reason")
        return self

    @property
    def key(self) -> str:
        return transition_key(self.from_stage, self.to_stage)

    @property
    def promotable(self) -> bool:
        return self.closed_reason is None and any(r.basis == "clinical" for r in self.requirements)


class FamilyTransition(BaseModel):
    """Requirements a whole family genuinely shares, beyond the safety baseline."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    from_stage: Literal["restore", "load", "dynamic"]
    to_stage: Literal["load", "dynamic", "return"]
    requirements: list[TransitionRequirement] = Field(default_factory=list)


class PathwayFamily(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    family_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    description: str = Field(min_length=1)
    injury_types: list[str] = Field(min_length=1)
    transitions: list[FamilyTransition] = Field(default_factory=list)


class TransitionOverride(BaseModel):
    """A regional exception to one family transition. Every change states why."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    reason: str = Field(min_length=1)
    add_requirements: list[TransitionRequirement] = Field(default_factory=list)
    remove_requirement_ids: list[str] = Field(default_factory=list)
    closed_reason: str | None = None


class FunctionalCheckpoint(BaseModel):
    """One declared clinical checkpoint or explicitly nonclinical captured input."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    checkpoint_id: str = Field(pattern=r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
    description: str = Field(min_length=1)
    required_input: str = Field(min_length=1)
    basis: Literal["clinical", "data_sufficiency"] = "clinical"
    assessment_kind: str | None = None
    protocol_version: int | None = Field(default=None, ge=1)

    @model_validator(mode="after")
    def coherent(self):
        if (self.basis == "data_sufficiency") != bool(self.assessment_kind and self.protocol_version):
            raise ValueError("captured input declarations require their assessment protocol/version")
        if self.basis == "clinical" and (self.assessment_kind or self.protocol_version):
            raise ValueError("input protocols cannot declare clinical readiness")
        return self


class PathwayCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1]
    safety_baseline: list[TransitionRequirement]
    functional_checkpoints: list[FunctionalCheckpoint] = Field(default_factory=list)
    families: list[PathwayFamily]
    profiles: list[dict]

    @model_validator(mode="after")
    def coherent(self):
        if any(r.basis == "clinical" for r in self.safety_baseline):
            raise ValueError("the shared safety baseline cannot contain clinical criteria")
        ids = [f.family_id for f in self.families]
        if len(set(ids)) != len(ids):
            raise ValueError("duplicate pathway family")
        owned = [t for f in self.families for t in f.injury_types]
        if len(set(owned)) != len(owned):
            raise ValueError("an injury type belongs to more than one pathway family")
        checkpoints = {c.checkpoint_id for c in self.functional_checkpoints}
        if len(checkpoints) != len(self.functional_checkpoints):
            raise ValueError("duplicate checkpoint declaration")
        for family in self.families:
            keys = [transition_key(t.from_stage, t.to_stage) for t in family.transitions]
            if len(set(keys)) != len(keys) or set(keys) - {transition_key(*s) for s in TRANSITION_STAGES}:
                raise ValueError("family transitions must be unique consecutive stage steps")
            for t in family.transitions:
                for requirement in t.requirements:
                    if requirement.checkpoint and requirement.checkpoint not in checkpoints:
                        raise ValueError("unknown functional checkpoint")
        return self

    def family(self, family_id: str) -> PathwayFamily:
        family = next((f for f in self.families if f.family_id == family_id), None)
        if family is None:
            raise ValueError(f"unknown pathway family: {family_id}")
        return family


def compose_transitions(catalog: PathwayCatalog, family: PathwayFamily,
                        overrides: dict[str, TransitionOverride]) -> list[PathwayTransition]:
    """Safety baseline + family requirements + profile exceptions, per stage step."""
    checkpoints = {c.checkpoint_id for c in catalog.functional_checkpoints}
    bases = {c.checkpoint_id: c.basis for c in catalog.functional_checkpoints}
    unknown = set(overrides) - {transition_key(*s) for s in TRANSITION_STAGES}
    if unknown:
        raise ValueError(f"unknown transition override: {sorted(unknown)}")
    family_requirements = {transition_key(t.from_stage, t.to_stage): t.requirements for t in family.transitions}
    composed = []
    for from_stage, to_stage in TRANSITION_STAGES:
        key = transition_key(from_stage, to_stage)
        requirements = [*catalog.safety_baseline, *family_requirements.get(key, [])]
        override = overrides.get(key)
        closed = None
        if override is not None:
            by_id = {r.requirement_id: r for r in requirements}
            for identity in override.remove_requirement_ids:
                if identity not in by_id:
                    raise ValueError(f"override removes an unknown requirement: {identity}")
                if by_id[identity].basis == "product_safety":
                    raise ValueError("a profile cannot remove a product safety requirement")
            requirements = [r for r in requirements if r.requirement_id not in override.remove_requirement_ids]
            requirements += override.add_requirements
            closed = override.closed_reason
        for requirement in requirements:
            if requirement.checkpoint and requirement.checkpoint not in checkpoints:
                raise ValueError(f"unknown functional checkpoint: {requirement.checkpoint}")
            if requirement.checkpoint and bases[requirement.checkpoint] != requirement.basis:
                raise ValueError("checkpoint declaration and requirement basis must match")
        composed.append(PathwayTransition(from_stage=from_stage, to_stage=to_stage,
                                          requirements=requirements, closed_reason=closed))
    return composed
