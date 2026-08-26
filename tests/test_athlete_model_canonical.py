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


def _make_training_context(
    *,
    injuries: list[str],
    support_work_days: list[str] | None = None,
    technical_skill_days: list[str] | None = None,
    style_technical: list[str] | None = None,
    style_tactical: list[str] | None = None,
) -> TrainingContext:
    return TrainingContext(
        fatigue="low",
        training_frequency=3,
        days_available=3,
        training_days=["Mon", "Wed", "Fri"],
        injuries=injuries,
        style_technical=style_technical or ["boxing"],
        style_tactical=style_tactical or ["pressure_fighter"],
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
        support_work_days=support_work_days or [],
        technical_skill_days=technical_skill_days or [],
    )


def _build(training_context: TrainingContext, *, programming_format: str = "boxing") -> dict:
    return athlete_model._build_athlete_model(
        training_context=training_context,
        sport=programming_format,
        record="3-0",
        rounds_format="3x3",
        camp_length_weeks=5,
        short_notice=False,
    )


def test_build_athlete_model_is_canonical_across_modules():
    assert stage2_payload._build_athlete_model is athlete_model._build_athlete_model
    assert stage2_planning_brief._build_athlete_model is athlete_model._build_athlete_model


def test_competition_sport_and_programming_format_are_explicitly_separate():
    model = _build(_make_training_context(injuries=[]))
    assert model["sport"] == "boxing"
    assert model["competition_sport"] == "boxing"
    assert model["programming_format"] == "boxing"
    assert model["sport_identity_source"] == "competition_sport"


def test_bjj_can_use_mma_programming_bank_without_receiving_mma_demand_profile():
    model = _build(
        _make_training_context(
            injuries=[],
            style_technical=["bjj"],
            style_tactical=["grappler"],
        ),
        programming_format="mma",
    )
    assert model["sport"] == "bjj"
    assert model["competition_sport"] == "bjj"
    assert model["programming_format"] == "mma"
    assert stage2_planning_brief._build_sport_load_profile(model)["key"] == "bjj"


def test_wrestling_can_use_mma_programming_bank_without_receiving_mma_demand_profile():
    model = _build(
        _make_training_context(
            injuries=[],
            style_technical=["wrestling"],
            style_tactical=["grappler"],
        ),
        programming_format="mma",
    )
    assert model["sport"] == "wrestling"
    assert model["competition_sport"] == "wrestling"
    assert model["programming_format"] == "mma"
    assert stage2_planning_brief._build_sport_load_profile(model)["key"] == "wrestling"


def test_mma_identity_wins_over_grappling_or_striking_style_expression():
    for tactical_styles in (["grappler"], ["counter_striker"], ["hybrid"]):
        model = _build(
            _make_training_context(
                injuries=[],
                style_technical=["mma", "wrestling"],
                style_tactical=tactical_styles,
            ),
            programming_format="mma",
        )
        assert model["sport"] == "mma"
        assert model["competition_sport"] == "mma"
        assert model["programming_format"] == "mma"
        assert stage2_planning_brief._build_sport_load_profile(model)["key"] == "mma"


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


def test_technical_skill_days_fallback_to_support_work_days():
    """When an athlete declares only legacy technical_skill_days, those days
    must still surface as support_work_days so coach-led day protection,
    role-map placement, and finalizer wording continue to honour them."""
    ctx = _make_training_context(
        injuries=[],
        support_work_days=[],
        technical_skill_days=["Tuesday", "Thursday"],
    )
    model = _build(ctx)
    assert model["support_work_days"] == ["Tuesday", "Thursday"]
    assert model["technical_skill_days"] == ["Tuesday", "Thursday"]


def test_explicit_support_work_days_take_precedence_over_legacy_field():
    ctx = _make_training_context(
        injuries=[],
        support_work_days=["Wednesday"],
        technical_skill_days=["Tuesday", "Thursday"],
    )
    model = _build(ctx)
    assert model["support_work_days"] == ["Wednesday"]
    assert model["technical_skill_days"] == ["Tuesday", "Thursday"]


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


def test_high_pressure_weight_cut_low_fatigue_boundary():
    """Low-fatigue, non-aggressive active cut is only high-pressure inside D-14."""
    def cut(days):
        return {
            "weight_cut_risk": True,
            "weight_cut_pct": 3.5,
            "fatigue": "low",
            "days_until_fight": days,
            "readiness_flags": ["active_weight_cut"],
        }

    assert not athlete_model._is_high_pressure_weight_cut(athlete_model=cut(28))
    assert not athlete_model._is_high_pressure_weight_cut(athlete_model=cut(21))
    assert not athlete_model._is_high_pressure_weight_cut(athlete_model=cut(15))
    assert athlete_model._is_high_pressure_weight_cut(athlete_model=cut(14))
    # Moderate+ fatigue and aggressive cuts stay high-pressure at any distance.
    moderate = {**cut(21), "fatigue": "moderate", "readiness_flags": ["active_weight_cut", "moderate_fatigue"]}
    assert athlete_model._is_high_pressure_weight_cut(athlete_model=moderate)
    aggressive = {**cut(21), "readiness_flags": ["active_weight_cut", "aggressive_weight_cut"]}
    assert athlete_model._is_high_pressure_weight_cut(athlete_model=aggressive)
