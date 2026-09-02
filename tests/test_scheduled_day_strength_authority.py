"""Regression coverage for final scheduled-day late-camp strength authority."""

from __future__ import annotations

import pytest

from fightcamp.calendar_context import role_d_day
from fightcamp.late_camp_role_morph import apply_late_camp_role_morph
from fightcamp.prescription_resolver import (
    MissingLateCampEffectiveStrengthAuthorityError,
    apply_effective_strength_prescriptions,
)
from fightcamp.stage2_finalizer_packet import build_stage2_finalizer_packet
from fightcamp.stage2_pipeline import build_stage2_retry
from fightcamp.stage2_validator import validate_stage2_output


PRODUCTION_PLAN_ID = "efa5868e-90de-4e49-ba5f-c0ea9838736d"


def _strength_slot(
    name: str = "Barbell Back Squat",
    prescription: str = "3 x 8 @ RPE 7",
    *,
    quality_class: str = "anchor_loaded",
    movement: str = "squat",
) -> dict:
    anchor_capable = quality_class.startswith("anchor_")
    support_only = quality_class.startswith("support_")
    return {
        "slot_id": f"gpp_strength_1_{name.lower().replace(' ', '_')}",
        "session_index": 1,
        "role": movement,
        "priority": 1,
        "quality_class": quality_class,
        "anchor_capable": anchor_capable,
        "support_only": support_only,
        "selected": {
            "name": name,
            "prescription": prescription,
            "quality_class": quality_class,
            "anchor_capable": anchor_capable,
            "support_only": support_only,
        },
    }


def _production_geometry() -> tuple[dict, dict]:
    # The production planner week spans eight days, so Thursday occurs twice.
    # Calendar integrity moves the GPP role from Monday D-19 to Thursday D-16.
    week = {
        "week_index": 1,
        "phase": "GPP",
        "calendar_days": [
            {"weekday": weekday, "d_day": d_day}
            for weekday, d_day in (
                ("thursday", 23),
                ("friday", 22),
                ("saturday", 21),
                ("sunday", 20),
                ("monday", 19),
                ("tuesday", 18),
                ("wednesday", 17),
                ("thursday", 16),
            )
        ],
        "declared_training_days": [
            "Thursday",
            "Friday",
            "Saturday",
            "Sunday",
            "Monday",
            "Tuesday",
            "Wednesday",
        ],
        "session_roles": [
            {
                "session_index": 2,
                "category": "strength",
                "role_key": "primary_strength_day",
                "scheduled_day_hint": "Monday",
                "countdown_label": "D-19",
                "scheduled_countdown_label": "D-19",
                "stress_class": "meaningful_stress",
                "cost_class": "medium",
            }
        ],
        "hard_sparring_plan": [
            {"day": "Friday", "status": "hard_as_planned", "effective_load": "hard"},
            {"day": "Tuesday", "status": "hard_as_planned", "effective_load": "hard"},
        ],
        "suppressed_roles": [],
        "session_count_summary": {
            "reduced_from_planned": False,
            "reduction_reasons": [],
        },
    }
    return {"weeks": [week]}, {"GPP": {"strength_slots": [_strength_slot()]}}


def _resolve_production_geometry(*, generation_d_day: int = 24) -> tuple[dict, dict, dict]:
    weekly_role_map, candidate_pools = _production_geometry()
    apply_late_camp_role_morph(weekly_role_map)
    apply_effective_strength_prescriptions(
        weekly_role_map=weekly_role_map,
        candidate_pools=candidate_pools,
        athlete_model={
            "days_until_fight": generation_d_day,
            "fatigue": "low",
            "weight_cut_pct": 0.0,
            "injuries": [],
        },
    )
    role = weekly_role_map["weeks"][0]["session_roles"][0]
    return weekly_role_map, candidate_pools, role


def _single_day_map(*, d_day: int, role_key: str = "primary_strength_day") -> dict:
    return {
        "weeks": [
            {
                "week_index": 2,
                "phase": "GPP",
                "calendar_days": [{"weekday": "thursday", "d_day": d_day}],
                "session_roles": [
                    {
                        "session_index": 1,
                        "category": "strength",
                        "role_key": role_key,
                        "scheduled_day_hint": "Thursday",
                        "scheduled_countdown_label": f"D-{d_day}",
                    }
                ],
            }
        ]
    }


def _resolve_single(name: str, *, d_day: int = 16, role_key: str = "primary_strength_day") -> dict:
    weekly_role_map = _single_day_map(d_day=d_day, role_key=role_key)
    candidate_pools = {"GPP": {"strength_slots": [_strength_slot(name)]}}
    apply_late_camp_role_morph(weekly_role_map)
    apply_effective_strength_prescriptions(
        weekly_role_map=weekly_role_map,
        candidate_pools=candidate_pools,
        athlete_model={"fatigue": "low", "weight_cut_pct": 0.0, "injuries": []},
    )
    return weekly_role_map["weeks"][0]["session_roles"][0]


def test_production_plan_d16_relocated_primary_strength_reaches_stage2_with_authority():
    weekly_role_map, candidate_pools, role = _resolve_production_geometry()

    assert PRODUCTION_PLAN_ID == "efa5868e-90de-4e49-ba5f-c0ea9838736d"
    assert weekly_role_map["calendar_integrity"]["relocated_roles"] == 1
    assert role["scheduled_day_hint"] == "Thursday"
    assert role["countdown_label"] == "D-19"
    assert role["scheduled_countdown_label"] == "D-16"
    assert role_d_day(weekly_role_map["weeks"][0], role) == 16
    assert role["scheduled_d_day"] == 16
    assert role["strength_dose_cap"] == {
        "max_sets": 3,
        "max_reps": 3,
        "loaded_allowed": True,
    }
    assert role["dose_adjustment_reason"] == "late_camp_strength_retention"
    assert role["effective_strength_envelope"]["scheduled_d_day"] == 16
    assert role["effective_strength_envelope"]["loaded_allowed"] is True
    assert role["effective_strength_prescriptions"][0]["effective_prescription"] == (
        "3 x 3 @ RPE 6-7 max"
    )

    packet = build_stage2_finalizer_packet(
        stage2_payload={
            "weekly_role_map": weekly_role_map,
            "candidate_pools": candidate_pools,
        },
        planning_brief={
            "weekly_role_map": weekly_role_map,
            "candidate_pools": candidate_pools,
            "athlete_snapshot": {"days_until_fight": 24},
        },
    )
    compact_role = packet["selected_plan"]["weekly_role_map"]["weeks"][0]["session_roles"][0]
    assert compact_role["strength_dose_cap"]["loaded_allowed"] is True
    assert compact_role["rpe_cap"] == "6-7"
    assert compact_role["effective_strength_envelope"]["max_reps"] == 3


@pytest.mark.parametrize("generation_d_day", [24, 22, 20, 18])
def test_final_scheduled_d16_authority_is_generation_route_independent(generation_d_day: int):
    _weekly_role_map, _candidate_pools, role = _resolve_production_geometry(
        generation_d_day=generation_d_day
    )
    effective = role["effective_strength_prescriptions"][0]
    assert role["scheduled_d_day"] == 16
    assert role["strength_dose_cap"]["max_reps"] == 3
    assert effective["effective_prescription"] == "3 x 3 @ RPE 6-7 max"


@pytest.mark.parametrize(
    "exercise",
    [
        "Back Squat",
        "Trap Bar Deadlift",
        "Romanian Deadlift",
        "Bench Press",
        "Bulgarian Split Squat",
    ],
)
def test_d16_effective_resolution_is_exercise_family_agnostic(exercise: str):
    role = _resolve_single(exercise)
    effective = role["effective_strength_prescriptions"][0]
    assert effective["name"] == exercise
    assert effective["effective_prescription"] == "3 x 3 @ RPE 6-7 max"
    assert effective["effective_loaded"] is True


@pytest.mark.parametrize(
    "role_key",
    [
        "primary_strength_day",
        "secondary_strength_day",
        "structural_strength_day",
        "transfer_strength_day",
        "neural_plus_strength_day",
        "strength_touch_day",
        "neural_primer_day",
        "small_strength_touch_day",
    ],
)
def test_countdown_strength_roles_receive_role_appropriate_authority(role_key: str):
    role = _resolve_single("Bench Press", role_key=role_key)
    assert role["scheduled_d_day"] == 16
    assert role["strength_dose_cap"]["loaded_allowed"] is True
    assert role["effective_strength_prescriptions"][0]["effective_loaded"] is True


def test_relocation_outside_window_clears_stale_d16_authority():
    weekly_role_map = _single_day_map(d_day=16)
    candidate_pools = {"GPP": {"strength_slots": [_strength_slot()]}}
    apply_late_camp_role_morph(weekly_role_map)
    apply_effective_strength_prescriptions(
        weekly_role_map=weekly_role_map,
        candidate_pools=candidate_pools,
    )
    role = weekly_role_map["weeks"][0]["session_roles"][0]
    assert role["scheduled_d_day"] == 16

    weekly_role_map["weeks"][0]["calendar_days"][0]["d_day"] = 18
    role["scheduled_countdown_label"] = "D-18"
    role["scheduled_d_day"] = 18
    apply_late_camp_role_morph(weekly_role_map)

    for field in (
        "strength_dose_cap",
        "set_cap",
        "rep_cap",
        "rpe_cap",
        "scheduled_d_day",
        "dose_adjustment_reason",
        "effective_strength_prescriptions",
        "effective_strength_envelope",
    ):
        assert field not in role


def test_missing_d16_loaded_strength_authority_blocks_finalizer_packet():
    weekly_role_map = _single_day_map(d_day=16)
    candidate_pools = {"GPP": {"strength_slots": [_strength_slot()]}}

    with pytest.raises(MissingLateCampEffectiveStrengthAuthorityError) as exc_info:
        build_stage2_finalizer_packet(
            stage2_payload={
                "weekly_role_map": weekly_role_map,
                "candidate_pools": candidate_pools,
            },
            planning_brief={
                "weekly_role_map": weekly_role_map,
                "candidate_pools": candidate_pools,
            },
        )

    error = exc_info.value
    assert error.code == "missing_late_camp_effective_strength_authority"
    assert error.details == {
        "role_key": "primary_strength_day",
        "week_index": 2,
        "session_index": 1,
        "scheduled_weekday": "Thursday",
        "original_countdown": None,
        "scheduled_countdown": "D-16",
        "resolved_d_day": 16,
        "loaded_exercises": ["Barbell Back Squat"],
        "missing_fields": [
            "strength_dose_cap",
            "scheduled_d_day",
            "dose_adjustment_reason",
            "rpe_cap",
            "effective_strength_prescriptions",
            "effective_strength_prescriptions[Barbell Back Squat]",
            "effective_strength_envelope",
        ],
    }


def test_d16_overage_still_uses_2412_validator_and_targeted_repair():
    weekly_role_map, _candidate_pools, _role = _resolve_production_geometry()
    rendered = "D-16 (Thursday) — Strength\nBarbell Back Squat: 3 x 5 at RPE 6.5-7\n"
    brief = {"weekly_role_map": weekly_role_map}

    report = validate_stage2_output(planning_brief=brief, final_plan_text=rendered)
    finding = next(
        item
        for item in report["errors"]
        if item["code"] == "late_camp_effective_prescription_exceeded"
    )
    assert finding["violation_dimensions"] == ["reps"]
    retry = build_stage2_retry(
        stage1_result={"planning_brief": brief},
        final_plan_text=rendered,
        validator_report=report,
    )
    assert retry["needs_retry"] is True
    assert "reduce_strength_dose_to_effective_prescription" in retry["repair_prompt"]


def test_d16_compliant_render_passes_effective_dose_validation():
    weekly_role_map, _candidate_pools, _role = _resolve_production_geometry()
    report = validate_stage2_output(
        planning_brief={"weekly_role_map": weekly_role_map},
        final_plan_text="D-16 (Thursday) — Strength\nBarbell Back Squat: 3 x 3 at RPE 7\n",
    )
    assert not any(
        item["code"] == "late_camp_effective_prescription_exceeded"
        for item in report["errors"]
    )


def test_d18_loaded_strength_is_not_forced_into_late_camp_authority():
    weekly_role_map = _single_day_map(d_day=18)
    candidate_pools = {"GPP": {"strength_slots": [_strength_slot()]}}
    packet = build_stage2_finalizer_packet(
        stage2_payload={
            "weekly_role_map": weekly_role_map,
            "candidate_pools": candidate_pools,
        },
        planning_brief={
            "weekly_role_map": weekly_role_map,
            "candidate_pools": candidate_pools,
        },
    )
    role = packet["selected_plan"]["weekly_role_map"]["weeks"][0]["session_roles"][0]
    assert "effective_strength_prescriptions" not in role


def test_unloaded_power_and_support_slots_do_not_trigger_loaded_strength_invariant():
    weekly_role_map = _single_day_map(d_day=7, role_key="neural_primer_day")
    candidate_pools = {
        "GPP": {
            "strength_slots": [
                _strength_slot(
                    "Med-Ball Rotational Throw",
                    "3 x 3 each side",
                    quality_class="anchor_power",
                    movement="throw",
                ),
                {
                    **_strength_slot(
                        "Pallof Press",
                        "2 x 8 each side",
                        quality_class="support_accessory",
                        movement="trunk",
                    ),
                    "priority": 2,
                },
            ]
        }
    }
    apply_late_camp_role_morph(weekly_role_map)
    apply_effective_strength_prescriptions(
        weekly_role_map=weekly_role_map,
        candidate_pools=candidate_pools,
    )

    packet = build_stage2_finalizer_packet(
        stage2_payload={
            "weekly_role_map": weekly_role_map,
            "candidate_pools": candidate_pools,
        },
        planning_brief={
            "weekly_role_map": weekly_role_map,
            "candidate_pools": candidate_pools,
        },
    )
    role = packet["selected_plan"]["weekly_role_map"]["weeks"][0]["session_roles"][0]
    assert role["effective_strength_envelope"]["loaded_allowed"] is False
    assert role["effective_strength_envelope"]["loaded_exercise_names"] == []
