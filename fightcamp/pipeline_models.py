"""Pydantic models for the internal Stage 1 -> Stage 2 handoff boundary.

These validate the dicts produced by the planner at the seam where one stage's
output becomes another stage's input. Internal helpers keep using plain dicts;
the models exist to fail fast when a producer drops a key or emits the wrong
type. ``extra="allow"`` is used throughout because the payloads are polymorphic
(standard / late-fight / open-ongoing variants add extra keys) and the
blocked-triage path attaches its own diagnostic fields.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AthleteModel(BaseModel):
    """Subset of the athlete_model dict that materially affects selection.

    Only a few stable scalars are typed so gross type regressions surface; every
    other key flows through untouched via ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow")

    sport: str | None = None
    status: str | None = None
    fatigue: str | None = None
    days_until_fight: int | None = None
    camp_length_weeks: int | None = None
    short_notice: bool | None = None


class Stage2Payload(BaseModel):
    """The restriction-aware candidate payload handed to Stage 2.

    Required keys are the documented contract shared by all three variants
    (see STAGE2_PAYLOAD_SPEC.md). Variant-specific keys (payload_variant,
    late_fight_*, open_plan_spec, ...) pass through via ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: str
    generator_mode: str
    athlete_model: AthleteModel
    # Stable boundary fields: required so a dropped key fails fast. An empty
    # dict/list is acceptable, a missing key is not.
    restrictions: list[Any]
    phase_briefs: dict[str, Any]
    candidate_pools: dict[str, Any]
    omission_ledger: dict[str, Any]
    rewrite_guidance: dict[str, Any]
    injury_context: dict[str, Any] = Field(default_factory=dict)


class PlanningBrief(BaseModel):
    """The planning brief handed to Stage 2.

    Required keys are common to all three variants; everything that differs by
    variant is optional or passes through via ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow")

    schema_version: str
    generator_mode: str
    athlete_snapshot: AthleteModel
    priority_focus: Any = None
    restrictions: list[Any] = Field(default_factory=list)
    candidate_pools: dict[str, Any] = Field(default_factory=dict)
    omission_ledger: dict[str, Any] = Field(default_factory=dict)
    decision_rules: dict[str, Any] = Field(default_factory=dict)


class Stage1Result(BaseModel):
    """The package ``generate_plan_sync`` returns.

    ``stage2_payload`` / ``planning_brief`` are ``None`` on the triage-blocked
    path, whose extra diagnostic keys (status, ok, injury_triage, ...) flow
    through via ``extra="allow"``.
    """

    model_config = ConfigDict(extra="allow")

    plan_text: str = ""
    coach_notes: str = ""
    why_log: dict[str, Any] = Field(default_factory=dict)
    stage2_handoff_text: str = ""
    parsing_metadata: dict[str, Any] = Field(default_factory=dict)
    pdf_url: str | None = None
    stage2_payload: Stage2Payload | None = None
    planning_brief: PlanningBrief | None = None
