"""Canonical Stage 2 athlete model tests.

These guard against future drift between `stage2_payload`,
`stage2_planning_brief`, and `athlete_model`. There must be exactly one real
`_build_athlete_model` implementation, and it must use the render-guard
helper for active-injury detection (so that "none.", "n/a!", etc. are not
treated as active injuries).
"""
from __future__ import annotations

import pytest

from fightcamp import athlete_model
from fightcamp import stage2_payload
from fightcamp import stage2_planning_brief
from fightcamp.training_context import TrainingContext


def _make_training_context(*, injuries: list[str]) -> TrainingContext:
    return TrainingContext(
        fatigue="low",
        training_frequency=3,
        days_available=3,
        training_days=["Mon", "Wed", "Fri"],
        injuries=injuries,
        style_technical=["boxing"],
        style_tactical=["pressure_fighter"],
        weaknesses=["gas_tank"],
        equipment=["heavy_bag"],
        weight_cut_risk=False,
        weight_cut_pct=0.0,
        fight_format="boxing",
        status="amateur",
        key_goals=["conditioning"],
        training_preference="balanced",
        mental_block=[],
        age=25,
        weight=70.0,
        prev_exercises=[],
        recent_exercises=[],
        phase_weeks={"GPP": 2, "SPP": 2, "TAPER": 1, "days": {"GPP": 0, "SPP": 0, "TAPER": 0}},
        days_until_fight=30,
    )


def _build(training_context: TrainingContext) -> dict:
    return athlete_model._build_athlete_model(
        training_context=training_context,
        sport="boxing",
        record="3-0",
        rounds_format="3x3",
        camp_length_weeks=5,
        short_notice=False,
    )


def test_build_athlete_model_is_canonical_across_modules():
    assert stage2_payload._build_athlete_model is athlete_model._build_athlete_model
    assert stage2_planning_brief._build_athlete_model is athlete_model._build_athlete_model


def test_athlete_helpers_are_canonical_across_modules():
    """Names that have always been part of stage2_payload's backwards-compat
    surface must resolve to the canonical athlete_model implementation."""
    for name in (
        "_UNKNOWN_COMPETITIVE_MATURITY",
        "_parse_record",
        "_derive_competitive_maturity",
        "_derive_readiness_flags",
        "_is_high_pressure_weight_cut",
    ):
        assert getattr(stage2_payload, name) is getattr(athlete_model, name), name
        assert getattr(stage2_planning_brief, name) is getattr(athlete_model, name), name

    # _RECORD_PATTERN is an implementation detail; only stage2_planning_brief
    # historically re-exported it.
    assert stage2_planning_brief._RECORD_PATTERN is athlete_model._RECORD_PATTERN


@pytest.mark.parametrize(
    "marker",
    [
        ["none"],
        ["none."],
        ["no injuries"],
        ["N/A"],
        ["n/a!"],
        ["nil"],
        ["nothing"],
        ["all clear"],
    ],
)
def test_no_injury_markers_do_not_flag_active_injury(marker):
    model = _build(_make_training_context(injuries=marker))
    assert model["has_active_injury"] is False, marker
    # Readiness flags currently include "injury_management" whenever the raw
    # injuries list is non-empty (legacy behaviour preserved). The render-guard
    # `has_active_injury` flag is the single source of truth for downstream
    # rehab/prehab suppression — assert that it is correctly False here.


def test_real_injury_flags_active_injury():
    model = _build(_make_training_context(injuries=["left shoulder"]))
    assert model["has_active_injury"] is True


def test_empty_injuries_list_has_no_active_injury_and_no_injury_management_flag():
    model = _build(_make_training_context(injuries=[]))
    assert model["has_active_injury"] is False
    assert "injury_management" not in model["readiness_flags"]


def test_legacy_imports_still_work():
    """Existing call sites that imported from stage2_payload or
    stage2_planning_brief must continue to function unchanged."""
    from fightcamp.stage2_payload import (
        _build_athlete_model as payload_build,
        _derive_readiness_flags as payload_readiness,
        _is_high_pressure_weight_cut as payload_high_pressure,
        _parse_record as payload_parse_record,
    )
    from fightcamp.stage2_planning_brief import (
        _build_athlete_model as brief_build,
        _derive_readiness_flags as brief_readiness,
        _is_high_pressure_weight_cut as brief_high_pressure,
        _parse_record as brief_parse_record,
    )
    assert payload_build is brief_build is athlete_model._build_athlete_model
    assert payload_readiness is brief_readiness is athlete_model._derive_readiness_flags
    assert payload_high_pressure is brief_high_pressure is athlete_model._is_high_pressure_weight_cut
    assert payload_parse_record is brief_parse_record is athlete_model._parse_record
