from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging

import pytest

from fightcamp import input_parsing
from fightcamp.athlete_size import (
    apply_athlete_size_modifiers,
    get_athlete_size_band,
)
from fightcamp.fight_format import apply_fight_format_modifiers
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_blocks import generate_plan_blocks
from fightcamp.plan_pipeline_runtime import build_runtime_context

FIXED_NOW = datetime(2026, 3, 13, 12, 0)
LOGGER = logging.getLogger(__name__)


def _payload(
    *,
    weight: str,
    target_weight: str | None = None,
    technical_style: str = "boxing",
    tactical_style: str = "counter striker",
    status: str = "professional",
    rounds_format: str = "10x3",
    next_fight_date: str = "2026-04-24",
) -> dict:
    return {
        "random_seed": 11,
        "data": {
            "fields": [
                {"label": "Full name", "value": "Maya Carter"},
                {"label": "Age", "value": "24"},
                {"label": "Weight (kg)", "value": weight},
                {"label": "Target Weight (kg)", "value": target_weight if target_weight is not None else weight},
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
        "SPP": {
            "grouped_drills": {
                "glycolytic": [
                    {
                        "name": "Fight-Pace Rounds",
                        "generic_fallback": True,
                        "timing": "4-5 x 3 min rounds",
                        "rest": "60 sec between rounds",
                        "load": "RPE 7-8 fight-pace",
                    }
                ],
                "alactic": [
                    {
                        "name": "Explosive Boxing Burst Intervals",
                        "generic_fallback": True,
                        "timing": "4-5 x 6-8 sec fast punch bursts",
                        "rest": "75-90 sec full recovery between reps",
                        "load": "RPE 8-9, sharp and relaxed, stop before speed drops",
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
                        "name": "Fight-Pace Rounds",
                        "generic_fallback": True,
                        "timing": "3-4 x 3 min work",
                        "rest": "60 sec between rounds",
                        "load": "RPE 6-7 fight-pace, relaxed and repeatable",
                    }
                ],
                "alactic": [
                    {
                        "name": "Sharp Burst Intervals",
                        "generic_fallback": True,
                        "timing": "4-5 x 6-8 sec sharp bursts",
                        "rest": "60-75 sec or full walk-back recovery",
                        "load": "RPE 8, keep sharpness high",
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


def _build_blocks(monkeypatch: pytest.MonkeyPatch, *, weight: str):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: FIXED_NOW)
    payload = _payload(weight=weight)
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


def test_runtime_weight_cut_pct_uses_current_weight_denominator(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: FIXED_NOW)
    payload = _payload(weight="105", target_weight="98")
    plan_input = PlanInput.from_payload(payload)

    context = build_runtime_context(
        plan_input=plan_input,
        random_seed=payload["random_seed"],
        logger=LOGGER,
    )

    assert context.weight_cut_pct_val == 6.7
    assert context.training_context.weight_cut_pct == 6.7
    assert context.weight_cut_risk_flag is True


def test_get_athlete_size_band_uses_rough_weight_bands():
    assert get_athlete_size_band(61) == "light"
    assert get_athlete_size_band(78) == "middle"
    assert get_athlete_size_band(98) == "heavy"
    assert get_athlete_size_band(0) is None


def test_middle_band_is_a_safe_noop():
    conditioning_blocks = _conditioning_stub()

    updated, size_band = apply_athlete_size_modifiers(
        conditioning_blocks,
        sport="boxing",
        weight_kg=78,
    )

    assert size_band == "middle"
    assert updated is conditioning_blocks


def test_heavy_size_modifier_reduces_density_and_extends_rest_late():
    formatted, _ = apply_fight_format_modifiers(
        deepcopy(_conditioning_stub()),
        sport="boxing",
        status="professional",
        rounds_format="10x3",
    )

    updated, size_band = apply_athlete_size_modifiers(
        formatted,
        sport="boxing",
        weight_kg=98,
    )

    assert size_band == "heavy"
    assert updated["SPP"]["grouped_drills"]["glycolytic"][0]["name"] == "Fight-Pace Rounds"
    assert updated["SPP"]["grouped_drills"]["glycolytic"][0]["timing"] == "3-4 x 3 min rounds"
    assert updated["SPP"]["grouped_drills"]["glycolytic"][0]["rest"] == "75 sec between rounds"
    assert updated["SPP"]["grouped_drills"]["alactic"][0]["name"] == "Explosive Boxing Burst Intervals"
    assert updated["SPP"]["grouped_drills"]["alactic"][0]["timing"] == "3-4 x 6-8 sec fast punch bursts"
    assert updated["SPP"]["grouped_drills"]["alactic"][0]["rest"] == "105-135 sec full recovery between reps"
    assert "keep hard density on the low end and add support cautiously" in updated["SPP"]["block"].lower()


def test_light_size_modifier_allows_sharper_rest_without_changing_drills():
    formatted, _ = apply_fight_format_modifiers(
        deepcopy(_conditioning_stub()),
        sport="boxing",
        status="amateur",
        rounds_format="5x3",
    )

    updated, size_band = apply_athlete_size_modifiers(
        formatted,
        sport="boxing",
        weight_kg=61,
    )

    assert size_band == "light"
    assert updated["SPP"]["grouped_drills"]["glycolytic"][0]["name"] == "Fight-Pace Rounds"
    assert updated["SPP"]["grouped_drills"]["glycolytic"][0]["timing"] == "5-6 x 3 min rounds"
    assert updated["SPP"]["grouped_drills"]["glycolytic"][0]["rest"] == "45 sec between rounds"
    assert updated["SPP"]["grouped_drills"]["alactic"][0]["name"] == "Explosive Boxing Burst Intervals"
    assert updated["SPP"]["grouped_drills"]["alactic"][0]["rest"] == "60-75 sec full recovery between reps"
    assert "a lighter athlete can tolerate a little more repeatability work" in updated["SPP"]["block"].lower()


def test_pipeline_keeps_selected_identity_but_changes_size_band_dose(monkeypatch: pytest.MonkeyPatch):
    blocks_light = _build_blocks(monkeypatch, weight="61")
    blocks_heavy = _build_blocks(monkeypatch, weight="98")

    assert blocks_light.strength_names == blocks_heavy.strength_names
    assert blocks_light.conditioning_names == blocks_heavy.conditioning_names
    assert blocks_light.conditioning_blocks["SPP"]["size_band"] == "light"
    assert blocks_heavy.conditioning_blocks["SPP"]["size_band"] == "heavy"
    assert blocks_light.conditioning_blocks["SPP"]["block"] != blocks_heavy.conditioning_blocks["SPP"]["block"]
