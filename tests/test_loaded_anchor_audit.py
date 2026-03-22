from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging

import pytest

from fightcamp import input_parsing
from fightcamp.input_parsing import PlanInput
from fightcamp.plan_pipeline_blocks import generate_plan_blocks
from fightcamp.plan_pipeline_runtime import build_runtime_context
from fightcamp.stage2_payload import build_stage2_payload
from fightcamp.strength_session_quality import classify_strength_item

FIXED_NOW = datetime(2026, 3, 13, 12, 0)
LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AuditScenario:
    name: str
    technical_style: str
    tactical_style: str
    status: str
    rounds_format: str
    weight: str
    equipment_access: str
    injuries: str = ""
    training_frequency: str = "4"
    training_days: str = "Monday, Tuesday, Thursday, Saturday"
    next_fight_date: str = "2026-05-22"


SCENARIOS = [
    AuditScenario(
        name="boxing_amateur_full_gym_3x3",
        technical_style="boxing",
        tactical_style="counter striker",
        status="amateur",
        rounds_format="3x3",
        weight="62",
        equipment_access="Trap Bar, Dumbbells, Barbell, Bands, Heavy Bag",
    ),
    AuditScenario(
        name="boxing_amateur_5x3_db_kb",
        technical_style="boxing",
        tactical_style="pressure fighter",
        status="amateur",
        rounds_format="5x3",
        weight="68",
        equipment_access="Dumbbells, Kettlebell, Bands, Heavy Bag",
    ),
    AuditScenario(
        name="boxing_pro_10x3_full_gym",
        technical_style="boxing",
        tactical_style="pressure fighter",
        status="professional",
        rounds_format="10x3",
        weight="78",
        equipment_access="Trap Bar, Barbell, Dumbbells, Landmine, Bands, Heavy Bag",
    ),
    AuditScenario(
        name="boxing_heavy_pro_10x3_sled",
        technical_style="boxing",
        tactical_style="counter striker",
        status="professional",
        rounds_format="10x3",
        weight="98",
        equipment_access="Sled, Trap Bar, Dumbbells, Bands, Heavy Bag",
    ),
    AuditScenario(
        name="mma_pro_3x5_full_gym",
        technical_style="mma",
        tactical_style="pressure fighter",
        status="professional",
        rounds_format="3x5",
        weight="77",
        equipment_access="Trap Bar, Barbell, Dumbbells, Kettlebell, Bands",
    ),
    AuditScenario(
        name="mma_pro_5x5_grappling_mix",
        technical_style="mma",
        tactical_style="scrambler",
        status="professional",
        rounds_format="5x5",
        weight="84",
        equipment_access="Trap Bar, Dumbbells, Sandbag, Bands, Partner",
    ),
    AuditScenario(
        name="muay_thai_amateur_5x2_dumbbell",
        technical_style="muay thai",
        tactical_style="clinch fighter",
        status="amateur",
        rounds_format="5x2",
        weight="64",
        equipment_access="Dumbbells, Kettlebell, Bands, Thai Pads, Heavy Bag",
    ),
    AuditScenario(
        name="muay_thai_pro_3x3_sandbag",
        technical_style="muay thai",
        tactical_style="clinch fighter",
        status="professional",
        rounds_format="3x3",
        weight="72",
        equipment_access="Sandbag, Dumbbells, Bands, Thai Pads, Heavy Bag",
    ),
    AuditScenario(
        name="kickboxing_amateur_3x2_trap_bar",
        technical_style="kickboxer",
        tactical_style="counter striker",
        status="amateur",
        rounds_format="3x2",
        weight="67",
        equipment_access="Trap Bar, Dumbbells, Bands, Heavy Bag",
    ),
    AuditScenario(
        name="kickboxing_pro_3x3_full_gym",
        technical_style="kickboxer",
        tactical_style="pressure fighter",
        status="professional",
        rounds_format="3x3",
        weight="81",
        equipment_access="Trap Bar, Barbell, Dumbbells, Landmine, Bands, Heavy Bag",
    ),
    AuditScenario(
        name="boxing_amateur_shoulder_knee_constraints",
        technical_style="boxing",
        tactical_style="counter striker",
        status="amateur",
        rounds_format="3x3",
        weight="70",
        equipment_access="Dumbbells, Bands, Heavy Bag",
        injuries="left knee pain, right shoulder irritation",
    ),
    AuditScenario(
        name="mma_pro_back_knee_constraints",
        technical_style="mma",
        tactical_style="pressure fighter",
        status="professional",
        rounds_format="3x5",
        weight="86",
        equipment_access="Dumbbells, Bands, Partner",
        injuries="low back flare, knee pain",
    ),
]


def _payload(scenario: AuditScenario) -> dict:
    return {
        "random_seed": 11,
        "data": {
            "fields": [
                {"label": "Full name", "value": "Audit Athlete"},
                {"label": "Age", "value": "27"},
                {"label": "Weight (kg)", "value": scenario.weight},
                {"label": "Target Weight (kg)", "value": scenario.weight},
                {"label": "Height (cm)", "value": "175"},
                {"label": "Fighting Style (Technical)", "value": [scenario.technical_style]},
                {"label": "Fighting Style (Tactical)", "value": [scenario.tactical_style]},
                {"label": "Stance", "value": "Orthodox"},
                {"label": "Professional Status", "value": scenario.status},
                {"label": "Current Record", "value": "8-2"},
                {"label": "When is your next fight?", "value": scenario.next_fight_date},
                {"label": "Rounds x Minutes", "value": scenario.rounds_format},
                {"label": "Weekly Training Frequency", "value": scenario.training_frequency},
                {"label": "Fatigue Level", "value": "Low"},
                {"label": "Equipment Access", "value": scenario.equipment_access},
                {"label": "Training Availability", "value": scenario.training_days},
                {"label": "Any injuries or areas you need to work around?", "value": scenario.injuries},
                {"label": "What are your key performance goals?", "value": "power, conditioning"},
                {"label": "Where do you feel weakest right now?", "value": "pull, gas tank"},
                {"label": "Do you prefer certain training styles?", "value": "technical"},
                {"label": "Do you struggle with any mental blockers or mindset challenges?", "value": "I rush exchanges late in rounds"},
                {"label": "Are there any parts of your previous plan you hated or loved?", "value": "Prefers concise sessions"},
            ]
        },
    }


def _build_stage1_and_stage2(scenario: AuditScenario):
    payload = _payload(scenario)
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
    stage2_payload = build_stage2_payload(
        training_context=context.training_context,
        mapped_format=context.mapped_format,
        record=context.plan_input.record,
        rounds_format=context.plan_input.rounds_format,
        camp_len=context.camp_len,
        short_notice=context.short_notice,
        restrictions=context.plan_input.restrictions,
        phase_weeks=context.phase_weeks,
        strength_blocks=blocks.strength_blocks,
        conditioning_blocks=blocks.conditioning_blocks,
        rehab_blocks=blocks.rehab_blocks,
    )
    return context, blocks, stage2_payload


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[scenario.name for scenario in SCENARIOS])
def test_loaded_anchor_audit_keeps_non_taper_phases_loaded_or_explicitly_limited(
    monkeypatch: pytest.MonkeyPatch,
    scenario: AuditScenario,
):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: FIXED_NOW)

    context, blocks, stage2_payload = _build_stage1_and_stage2(scenario)

    for phase in ("GPP", "SPP"):
        if not context.phase_active(phase):
            continue

        strength_block = blocks.strength_blocks.get(phase)
        assert strength_block is not None, f"{scenario.name}:{phase} missing strength block"

        has_true_loaded_anchor = bool(strength_block.get("true_loaded_anchor_present"))
        is_explicitly_limited = bool(strength_block.get("loaded_anchor_limited"))
        assert has_true_loaded_anchor or is_explicitly_limited, (
            f"{scenario.name}:{phase} lost the pre-taper loaded anchor without an explicit limitation flag"
        )

        stage2_phase_pool = stage2_payload["candidate_pools"].get(phase, {})
        loaded_anchor_rule = stage2_phase_pool.get("loaded_anchor_rule", {})
        assert loaded_anchor_rule.get("required_pre_taper") is True
        assert (
            loaded_anchor_rule.get("true_loaded_anchor_available")
            or loaded_anchor_rule.get("injury_limited")
        ), f"{scenario.name}:{phase} stage2 payload dropped the loaded-anchor rule state"

        if is_explicitly_limited:
            assert str(strength_block.get("loaded_anchor_note", "")).strip()
            assert str(loaded_anchor_rule.get("note", "")).strip()


@pytest.mark.parametrize(
    "scenario_name",
    [
        "boxing_amateur_5x3_db_kb",
        "muay_thai_amateur_5x2_dumbbell",
        "muay_thai_pro_3x3_sandbag",
    ],
)
def test_loaded_anchor_audit_recovers_true_loaded_anchor_for_healthy_limited_equipment_gpp(
    monkeypatch: pytest.MonkeyPatch,
    scenario_name: str,
):
    monkeypatch.setattr(input_parsing, "_utc_now", lambda: FIXED_NOW)
    monkeypatch.setattr(input_parsing, "_calendar_now", lambda: FIXED_NOW)

    scenario = next(candidate for candidate in SCENARIOS if candidate.name == scenario_name)
    _context, blocks, stage2_payload = _build_stage1_and_stage2(scenario)

    strength_block = blocks.strength_blocks["GPP"]
    selected_exercises = strength_block.get("exercises", [])

    assert strength_block.get("true_loaded_anchor_present") is True
    assert strength_block.get("loaded_anchor_limited") is False
    assert any(
        classify_strength_item(exercise)["true_loaded_anchor"]
        for exercise in selected_exercises
    ), f"{scenario_name}:GPP should keep a true loaded anchor after the universal fallback"

    loaded_anchor_rule = stage2_payload["candidate_pools"]["GPP"]["loaded_anchor_rule"]
    assert loaded_anchor_rule.get("true_loaded_anchor_available") is True
    assert loaded_anchor_rule.get("injury_limited") is False
