from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging

import pytest

from fightcamp import input_parsing
from fightcamp.fight_format import (
    apply_fight_format_modifiers,
    get_fight_format_key,
    parse_rounds_minutes,
)
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_blocks import generate_plan_blocks
from fightcamp.plan_pipeline_runtime import build_runtime_context

FIXED_NOW = datetime(2026, 3, 13, 12, 0)
LOGGER = logging.getLogger(__name__)


def _payload(
    *,
    technical_style: str,
    tactical_style: str,
    status: str,
    rounds_format: str,
    next_fight_date: str = "2026-04-24",
) -> dict:
    return {
        "random_seed": 11,
        "data": {
            "fields": [
                {"label": "Full name", "value": "Maya Carter"},
                {"label": "Age", "value": "24"},
                {"label": "Weight (kg)", "value": "62"},
                {"label": "Target Weight (kg)", "value": "60"},
                {"label": "Height (cm)", "value": "168"},
                {"label": "Fighting Style (Technical)", "value": [technical_style]},
                {"label": "Fighting Style (Tactical)", "value": [tactical_style]},
                {"label": "Stance", "value": "Orthodox"},
                {"label": "Professional Status", "value": status},
                {"label": "Current Record", "value": "6-1"},
                {"label": "When is your next fight?", "value": next_fight_date},
                {"label": "Rounds x Minutes", "value": rounds_format},
                {"label": "Weekly Training Frequency", "value": "4"},
                {"label": "Fatigue Level", "value": "Low"},
                {"label": "Equipment Access", "value": "Dumbbells, Bands, Medicine Ball"},
                {"label": "Training Availability", "value": "Monday, Tuesday, Thursday, Saturday"},
                {"label": "Any injuries or areas you need to work around?", "value": ""},
                {"label": "What are your key performance goals?", "value": "skill refinement, power"},
                {"label": "Where do you feel weakest right now?", "value": "pull, gas tank"},
                {"label": "Do you prefer certain training styles?", "value": "technical"},
                {"label": "Do you struggle with any mental blockers or mindset challenges?", "value": "I rush exchanges late in rounds"},
                {"label": "Are there any parts of your previous plan you hated or loved?", "value": "Prefers concise sessions"},
            ]
        },
    }


def _conditioning_stub() -> dict[str, dict]:
    return {
        "GPP": {
            "grouped_drills": {
                "aerobic": [
                    {
                        "name": "Easy Continuous Swimming",
                        "duration": "20-30min steady strokes",
                        "intensity": "zone 2",
                    }
                ]
            },
            "phase_color": "#4CAF50",
            "missing_systems": [],
            "num_sessions": 1,
            "diagnostic_context": {},
            "sport": "boxing",
            "block": "",
        },
        "SPP": {
            "grouped_drills": {
                "glycolytic": [
                    {
                        "name": "Roll Under Hell",
                        "duration": "20 roll-under uppercuts, 10 body shots x 5 rounds",
                        "intensity": "high",
                    }
                ],
                "alactic": [
                    {
                        "name": "Explosive Boxing Burst Intervals",
                        "generic_fallback": True,
                        "timing": "6-8 x 6-10 sec fast punch bursts",
                        "rest": "75-120 sec complete rest between reps",
                        "load": "RPE 8-9, keep quality high and stop before speed drop-off",
                    }
                ],
            },
            "phase_color": "#FF9800",
            "missing_systems": [],
            "num_sessions": 1,
            "diagnostic_context": {},
            "sport": "boxing",
            "block": "",
        },
        "TAPER": {
            "grouped_drills": {
                "glycolytic": [
                    {
                        "name": "Fight-Pace Rounds: 6-10 x (2-3 min on / 1 min off)",
                        "generic_fallback": True,
                        "timing": "2-3 min work / 1 min rest",
                        "rest": "1 min between rounds",
                        "load": "RPE 6-7 fight-pace",
                    }
                ],
                "alactic": [
                    {
                        "name": "Ankle Snap Bounce",
                        "duration": "4x10s, 30s rest",
                    }
                ],
            },
            "phase_color": "#F44336",
            "missing_systems": [],
            "num_sessions": 1,
            "diagnostic_context": {},
            "sport": "boxing",
            "block": "",
        },
    }


def _build_blocks(monkeypatch: pytest.MonkeyPatch, *, status: str, rounds_format: str):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: FIXED_NOW)
    payload = _payload(
        technical_style="boxing",
        tactical_style="counter striker",
        status=status,
        rounds_format=rounds_format,
    )
    plan_input = PlanInput.from_payload(payload)
    context = build_runtime_context(
        plan_input=plan_input,
        random_seed=payload["random_seed"],
        logger=LOGGER,
    )
    return generate_plan_blocks(
        context=context,
        record_timing=lambda *_: None,
        logger=LOGGER,
    )


def test_parse_rounds_minutes_and_known_boxing_keys():
    assert parse_rounds_minutes("3x3") == (3, 3)
    assert parse_rounds_minutes("5 x 3") == (5, 3)
    assert parse_rounds_minutes("10 rounds x 3 min") == (10, 3)
    assert get_fight_format_key("boxing", "amateur", 3, 3) == "boxing_amateur_3x3"
    assert get_fight_format_key("boxing", "professional", 10, 3) == "boxing_pro_10x3"
    assert get_fight_format_key("mma", "professional", 3, 5) == "mma_pro_3x5"
    assert get_fight_format_key("mma", "professional", 5, 5) == "mma_pro_5x5"
    assert get_fight_format_key("muay_thai", "amateur", 5, 2) == "muay_thai_amateur_5x2"
    assert get_fight_format_key("muay_thai", "professional", 3, 3) == "muay_thai_pro_3x3"
    assert get_fight_format_key("kickboxing", "amateur", 3, 2) == "kickboxing_amateur_3x2"
    assert get_fight_format_key("kickboxing", "professional", 3, 3) == "kickboxing_pro_3x3"


def test_unknown_fight_format_falls_back_to_current_behavior():
    conditioning_blocks = _conditioning_stub()

    updated, format_key = apply_fight_format_modifiers(
        conditioning_blocks,
        sport="boxing",
        status="professional",
        rounds_format="7x4",
    )

    assert updated is conditioning_blocks
    assert format_key is None


def test_grappling_aliases_do_not_inherit_mma_format_rules():
    conditioning_blocks = _conditioning_stub()

    updated, format_key = apply_fight_format_modifiers(
        conditioning_blocks,
        sport="bjj",
        status="professional",
        rounds_format="5x5",
    )

    assert updated is conditioning_blocks
    assert format_key is None


def test_unusual_rounds_format_surfaces_non_blocking_input_warning(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: FIXED_NOW)
    payload = _payload(
        technical_style="boxing",
        tactical_style="counter striker",
        status="amateur",
        rounds_format="7-4",
    )
    plan_input = PlanInput.from_payload(payload)
    context = build_runtime_context(
        plan_input=plan_input,
        random_seed=payload["random_seed"],
        logger=LOGGER,
    )
    blocks = generate_plan_blocks(
        context=context,
        record_timing=lambda *_: None,
        logger=LOGGER,
    )

    assert plan_input.rounds_format == "7x4"
    assert "unusual for boxing" in plan_input.rounds_format_warning.lower()
    assert "### Input Validation" in blocks.coach_review_notes
    assert "format-specific dose rules were skipped" in blocks.coach_review_notes.lower()


def test_modifier_keeps_drill_identity_and_changes_only_late_prescriptions():
    original = _conditioning_stub()
    updated, format_key = apply_fight_format_modifiers(
        deepcopy(original),
        sport="boxing",
        status="amateur",
        rounds_format="3x3",
    )

    assert format_key == "boxing_amateur_3x3"
    assert updated["SPP"]["grouped_drills"]["glycolytic"][0]["name"] == "Roll Under Hell"
    assert updated["SPP"]["grouped_drills"]["glycolytic"][0]["timing"].endswith(
        "format target: 4-5 x 3 min rounds"
    )
    assert updated["SPP"]["grouped_drills"]["alactic"][0]["name"] == "Explosive Boxing Burst Intervals"
    assert updated["SPP"]["grouped_drills"]["alactic"][0]["timing"] == "6-8 x 6-8 sec fast punch bursts"
    assert updated["TAPER"]["grouped_drills"]["glycolytic"][0]["display_name"] == "Fight-Pace Rounds"
    assert original["SPP"]["grouped_drills"]["glycolytic"][0]["name"] == "Roll Under Hell"


@pytest.mark.parametrize(
    ("status", "rounds_format", "expected_spp_template", "expected_spp_target", "expected_taper"),
    [
        (
            "amateur",
            "3x3",
            "4-5 rounds of 3 min @ RPE 7-8, 60 sec rest",
            "format target: 4-5 x 3 min rounds",
            "reduce density 40-50%",
        ),
        (
            "amateur",
            "5x3",
            "5-6 rounds of 3 min @ RPE 7-8, 60 sec rest",
            "format target: 5-6 x 3 min rounds",
            "reduce density 35-45%",
        ),
        (
            "professional",
            "10x3",
            "6-8 rounds of 3 min @ RPE 7-8, 45-60 sec rest",
            "format target: 6-8 x 3 min rounds",
            "reduce density 45-60%",
        ),
    ],
)
def test_boxing_formats_change_conditioning_dose_late_in_pipeline(
    monkeypatch: pytest.MonkeyPatch,
    status: str,
    rounds_format: str,
    expected_spp_template: str,
    expected_spp_target: str,
    expected_taper: str,
):
    blocks = _build_blocks(monkeypatch, status=status, rounds_format=rounds_format)

    spp_block = blocks.conditioning_blocks["SPP"]["block"]
    taper_block = blocks.conditioning_blocks["TAPER"]["block"]
    spp_targets = [
        drill.get("timing", "")
        for drill in blocks.conditioning_blocks["SPP"]["grouped_drills"]["glycolytic"]
    ]

    assert expected_spp_template in spp_block
    assert any(expected_spp_target in target for target in spp_targets)
    assert expected_taper in taper_block


def test_boxing_format_modifier_does_not_change_selected_strength_or_drill_identity(
    monkeypatch: pytest.MonkeyPatch,
):
    blocks_3x3 = _build_blocks(monkeypatch, status="amateur", rounds_format="3x3")
    blocks_5x3 = _build_blocks(monkeypatch, status="amateur", rounds_format="5x3")

    assert blocks_3x3.strength_names == blocks_5x3.strength_names
    assert blocks_3x3.conditioning_names == blocks_5x3.conditioning_names


@pytest.mark.parametrize(
    (
        "technical_style",
        "tactical_style",
        "status",
        "rounds_format",
        "expected_key",
        "expected_spp_template",
        "expected_glyco_target",
        "expected_taper_density",
    ),
    [
        (
            "mma",
            "pressure fighter",
            "professional",
            "3x5",
            "mma_pro_3x5",
            "4-5 rounds of 5 min @ RPE 7-8, 60 sec rest",
            "format target: 4-5 x 5 min rounds",
            "reduce density 45-60%",
        ),
        (
            "mma",
            "pressure fighter",
            "professional",
            "5x5",
            "mma_pro_5x5",
            "5-6 rounds of 5 min @ RPE 7-8, 45-60 sec rest",
            "format target: 5-6 x 5 min rounds",
            "reduce density 50-60%",
        ),
        (
            "muay thai",
            "clinch fighter",
            "amateur",
            "5x2",
            "muay_thai_amateur_5x2",
            "5-6 rounds of 2 min @ RPE 7-8, 60 sec rest",
            "format target: 5-6 x 2 min rounds",
            "reduce density 35-45%",
        ),
        (
            "muay thai",
            "clinch fighter",
            "professional",
            "3x3",
            "muay_thai_pro_3x3",
            "4-5 rounds of 3 min @ RPE 7-8, 60 sec rest",
            "format target: 4-5 x 3 min rounds",
            "reduce density 40-50%",
        ),
        (
            "kickboxer",
            "counter striker",
            "amateur",
            "3x2",
            "kickboxing_amateur_3x2",
            "4-5 rounds of 2 min @ RPE 7-8, 60 sec rest",
            "format target: 4-5 x 2 min rounds",
            "reduce density 35-45%",
        ),
        (
            "kickboxer",
            "counter striker",
            "professional",
            "3x3",
            "kickboxing_pro_3x3",
            "4-5 rounds of 3 min @ RPE 7-8, 60 sec rest",
            "format target: 4-5 x 3 min rounds",
            "reduce density 40-50%",
        ),
    ],
)
def test_other_combat_sports_get_late_fight_format_modifiers(
    monkeypatch: pytest.MonkeyPatch,
    technical_style: str,
    tactical_style: str,
    status: str,
    rounds_format: str,
    expected_key: str,
    expected_spp_template: str,
    expected_glyco_target: str,
    expected_taper_density: str,
):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: FIXED_NOW)
    payload = _payload(
        technical_style=technical_style,
        tactical_style=tactical_style,
        status=status,
        rounds_format=rounds_format,
        next_fight_date="2026-05-22",
    )
    plan_input = PlanInput.from_payload(payload)
    context = build_runtime_context(
        plan_input=plan_input,
        random_seed=payload["random_seed"],
        logger=LOGGER,
    )
    blocks = generate_plan_blocks(
        context=context,
        record_timing=lambda *_: None,
        logger=LOGGER,
    )

    spp_block = blocks.conditioning_blocks["SPP"]["block"]
    taper_block = blocks.conditioning_blocks["TAPER"]["block"]
    spp_targets = [
        drill.get("timing", "")
        for drill in blocks.conditioning_blocks["SPP"]["grouped_drills"]["glycolytic"]
    ]

    assert blocks.conditioning_blocks["SPP"]["format_key"] == expected_key
    assert expected_spp_template in spp_block
    assert any(expected_glyco_target in target for target in spp_targets)
    assert expected_taper_density in taper_block


@pytest.mark.parametrize(
    ("technical_style", "tactical_style", "status_a", "rounds_a", "status_b", "rounds_b"),
    [
        ("mma", "pressure fighter", "professional", "3x5", "professional", "5x5"),
        ("muay thai", "clinch fighter", "amateur", "5x2", "professional", "3x3"),
        ("kickboxer", "counter striker", "amateur", "3x2", "professional", "3x3"),
    ],
)
def test_other_sports_keep_selected_drill_identity_across_formats(
    monkeypatch: pytest.MonkeyPatch,
    technical_style: str,
    tactical_style: str,
    status_a: str,
    rounds_a: str,
    status_b: str,
    rounds_b: str,
):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: FIXED_NOW)

    payload_a = _payload(
        technical_style=technical_style,
        tactical_style=tactical_style,
        status=status_a,
        rounds_format=rounds_a,
        next_fight_date="2026-05-22",
    )
    payload_b = _payload(
        technical_style=technical_style,
        tactical_style=tactical_style,
        status=status_b,
        rounds_format=rounds_b,
        next_fight_date="2026-05-22",
    )

    plan_input_a = PlanInput.from_payload(payload_a)
    plan_input_b = PlanInput.from_payload(payload_b)
    context_a = build_runtime_context(plan_input=plan_input_a, random_seed=payload_a["random_seed"], logger=LOGGER)
    context_b = build_runtime_context(plan_input=plan_input_b, random_seed=payload_b["random_seed"], logger=LOGGER)

    blocks_a = generate_plan_blocks(context=context_a, record_timing=lambda *_: None, logger=LOGGER)
    blocks_b = generate_plan_blocks(context=context_b, record_timing=lambda *_: None, logger=LOGGER)

    assert blocks_a.strength_names == blocks_b.strength_names
    assert blocks_a.conditioning_names == blocks_b.conditioning_names
