"""Versioned rehab policies. The legacy module name is kept for compatibility.

Activation is a software/data validation step, not clinician approval.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .config import DATA_DIR
from .rehab_schema import REHAB_STAGES, canonical_rehab_locations, canonical_rehab_types


def content_hash(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")).encode()).hexdigest()


def policy_review_hash(policy) -> str:
    # Historical snapshots use policy_review_hash; its meaning is now content
    # integrity only. No clinician identity or sign-off is asserted.
    raw = policy.model_dump(exclude={"content_hash", "status", "activation"})
    # Preserve hashes of existing single-drill policies exactly.
    if not raw.get("stage_bundles"):
        raw.pop("stage_bundles", None)
    return content_hash(raw)


class ClinicalDose(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    sets: int | None = Field(default=None, gt=0)
    reps: int | None = Field(default=None, gt=0)
    duration_seconds: float | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def measurable(self):
        if self.reps is None and self.duration_seconds is None:
            raise ValueError("a prescription needs reps or duration")
        return self


class ClinicalPrescription(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    drill_id: str = Field(min_length=1)
    bank_hash: str = Field(pattern=r"^[a-f0-9]{64}$")
    stage: Literal["calm", "restore", "load", "dynamic", "return"]
    instructions: str = Field(min_length=1)
    dose: ClinicalDose | None = None
    camp_doses: dict[str, ClinicalDose] = Field(default_factory=dict)
    readiness_doses: dict[Literal["modify", "pull_back"], ClinicalDose] = Field(default_factory=dict)
    allowed_severities: list[Literal["low", "moderate", "high"]] = Field(min_length=1)
    stop_when: list[str] = Field(min_length=1)
    frequency: Literal["scheduled_sessions", "daily"] = "scheduled_sessions"
    minimum_gap_days: int = Field(default=1, ge=1, le=14)
    priority: int = 0
    sources: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def bounded_camp_dose(self):
        if not self.instructions.strip() or any(not rule.strip() for rule in self.stop_when):
            raise ValueError("instructions and stop rules must not be blank")
        if any(phase not in {"GPP", "SPP", "TAPER"} for phase in self.camp_doses):
            raise ValueError("unknown camp phase")
        for dose in [*self.camp_doses.values(), *self.readiness_doses.values()]:
            for name in ClinicalDose.model_fields:
                value, ceiling = getattr(dose, name), getattr(self.dose, name) if self.dose else None
                if value is not None and (ceiling is None or value > ceiling):
                    raise ValueError("context dose may only reduce the reviewed prescription")
        return self


class ClinicalTransition(BaseModel):
    """Reserved criteria schema; automatic higher stages are disabled in v1."""
    model_config = ConfigDict(extra="forbid", frozen=True)
    from_stage: Literal["restore", "load", "dynamic"]
    to_stage: Literal["load", "dynamic", "return"]
    minimum_response_groups: int = Field(gt=0)
    minimum_distinct_days: int = Field(gt=0)
    minimum_completed_dose: ClinicalDose
    qualifying_loads: list[Literal["minimal", "low", "moderate", "high"]] = Field(min_length=1)
    qualifying_impacts: list[Literal["none", "low", "moderate", "high"]] = Field(min_length=1)
    qualifying_velocities: list[Literal["low", "moderate", "high"]] = Field(min_length=1)
    allowed_during_responses: list[Literal["better", "same"]] = Field(min_length=1)
    allowed_delayed_responses: list[Literal["better", "same"]] = Field(min_length=1)

    @model_validator(mode="after")
    def consecutive(self):
        if REHAB_STAGES.index(self.to_stage) != REHAB_STAGES.index(self.from_stage) + 1:
            raise ValueError("stage transitions must be consecutive")
        return self


class ClinicalPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    policy_id: str = Field(min_length=1)
    version: int = Field(ge=1)
    region: str = Field(min_length=1)
    injury_type: str = Field(min_length=1)
    status: Literal["draft", "active", "retired"] = "draft"
    activation: Literal["shadow", "live"] = "shadow"
    evidence_sources: list[str] = Field(default_factory=list)
    content_hash: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    prescriptions: list[ClinicalPrescription] = Field(default_factory=list)
    blocked_regions: list[str] = Field(default_factory=list)
    blocked_tags: list[str] = Field(default_factory=list)
    contact_limit: Literal["none", "controlled", "full"] = "none"
    live_stages: list[Literal["calm", "restore", "load", "dynamic", "return"]] = Field(default_factory=lambda: ["calm", "restore"])
    transitions: list[ClinicalTransition] = Field(default_factory=list)
    # Explicit compatibility review, not a count applied to ranked alternatives.
    stage_bundles: dict[Literal["calm", "restore", "load", "dynamic", "return"], list[str]] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_active_policy(self):
        if self.region not in canonical_rehab_locations() or self.injury_type not in canonical_rehab_types():
            raise ValueError("unknown policy region or injury type")
        if self.status == "active" and not (self.evidence_sources and self.prescriptions):
            raise ValueError("active policy needs sources and routines")
        if self.activation == "live" and self.status != "active":
            raise ValueError("inactive policy cannot be live")
        if self.status == "active":
            if any(not source.strip() for source in self.evidence_sources):
                raise ValueError("policy sources must identify evidence")
            if any(p.stage not in {"calm", "restore"} for p in self.prescriptions):
                raise ValueError("v1 routines are limited to calm and restore")
            if any(not p.sources or any(not s.strip() or s not in self.evidence_sources for s in p.sources) for p in self.prescriptions):
                raise ValueError("active routines need instruction and cadence sources")
            if self.transitions:
                raise ValueError("automatic higher-stage transitions are disabled in v1")
        if len({p.drill_id for p in self.prescriptions}) != len(self.prescriptions):
            raise ValueError("duplicate prescription identity")
        by_id = {p.drill_id: p for p in self.prescriptions}
        for stage, ids in self.stage_bundles.items():
            if stage not in self.live_stages or not ids or len(set(ids)) != len(ids):
                raise ValueError("bundle needs unique drills in an activated stage")
            if any(identity not in by_id or by_id[identity].stage != stage for identity in ids):
                raise ValueError("bundle drills must have reviewed prescriptions in the same stage")
            if len({by_id[identity].frequency for identity in ids}) != 1:
                raise ValueError("bundle drills must share a scheduling frequency")
        if len({t.to_stage for t in self.transitions}) != len(self.transitions):
            raise ValueError("duplicate transition criteria")
        if any(stage not in {"calm", "restore"} for stage in self.live_stages):
            raise ValueError("automatic load, dynamic and return stages are disabled in v1")
        if set(self.blocked_regions) - canonical_rehab_locations():
            raise ValueError("unknown restricted region")
        if self.status == "active" and self.content_hash != policy_review_hash(self):
            raise ValueError("policy content hash is missing or stale")
        return self


def load_clinical_policies(path: Path | None = None) -> tuple[ClinicalPolicy, ...]:
    raw = json.loads((path or DATA_DIR / "rehab_clinical_policies.json").read_text(encoding="utf-8"))
    if not isinstance(raw, dict) or raw.get("schema_version") != 2:
        raise ValueError("unsupported clinical policy schema")
    policies = tuple(ClinicalPolicy.model_validate(item) for item in raw["policies"])
    keys = [(p.region, p.injury_type) for p in policies]
    if len(set(keys)) != len(keys):
        raise ValueError("duplicate clinical injury policy")
    return policies


def validate_clinical_bank(policies: tuple[ClinicalPolicy, ...], bank: list[dict]) -> list[str]:
    indexed: dict[str, list[tuple[dict, dict]]] = {}
    for group in bank:
        for drill in group.get("drills", []):
            indexed.setdefault(str(drill.get("id") or ""), []).append((group, drill))
    errors: list[str] = []
    for policy in policies:
        if policy.status == "retired":
            continue
        for prescription in policy.prescriptions:
            matches = indexed.get(prescription.drill_id, [])
            if len(matches) != 1:
                errors.append(f"{policy.policy_id}: drill identity is missing or ambiguous: {prescription.drill_id}")
                continue
            group, drill = matches[0]
            if content_hash(drill) != prescription.bank_hash:
                errors.append(f"{policy.policy_id}: stale bank review: {prescription.drill_id}")
            if group.get("location") != policy.region or group.get("type") not in {policy.injury_type, "unspecified"}:
                errors.append(f"{policy.policy_id}: incompatible drill region or injury type")
            if policy.status == "active":
                for field in ("load", "impact", "velocity", "equipment", "function", "target_tissues"):
                    value = drill.get(field)
                    if value is None or value == "unknown":
                        errors.append(f"{policy.policy_id}: incomplete {field}: {prescription.drill_id}")
                if drill.get("rehab_stage") != prescription.stage:
                    errors.append(f"{policy.policy_id}: prescription stage differs from bank review")
    return errors
