from __future__ import annotations

import pytest

import fightcamp.camp_week_fillers as fillers
from fightcamp.camp_week_fillers import _splice_late_fight_tail
from fightcamp.late_fight_tail import build_finished_late_fight_tail


def _role(role_key: str, d_day: int, weekday: str, category: str = "conditioning") -> dict:
    return {
        "role_key": role_key,
        "category": category,
        "scheduled_countdown_label": f"D-{d_day}",
        "countdown_label": f"D-{d_day}",
        "countdown_offset": d_day,
        "scheduled_day_hint": weekday,
        "athlete_facing_label": role_key.replace("_", " ").title(),
    }


def _d22_athlete(*, handoff: bool = False) -> dict:
    athlete = {
        "sport": "boxing",
        "fight_format": "boxing",
        "days_until_fight": 22,
        "fight_date": "2026-09-28",
        "next_fight_date": "2026-09-28",
        "plan_creation_weekday": "sunday",
        "training_frequency": 4,
        "weekly_training_frequency": 4,
        "days_available": 4,
        "training_days": ["monday", "wednesday", "thursday", "friday"],
        "hard_sparring_days": [],
        "support_work_days": [],
        "fatigue": "moderate",
        "fatigue_level": "moderate",
        "readiness_flags": [],
        "injuries": [],
        "restrictions": [],
        "weight_cut_risk": False,
        "cut_severity_bucket": "low",
        "key_goals": ["conditioning", "speed"],
        "weaknesses": ["conditioning"],
        "equipment": [
            "bodyweight",
            "bands",
            "medicine_ball",
            "assault_bike",
            "rower",
        ],
    }
    if handoff:
        athlete["handoff_required_conditioning_systems"] = ["glycolytic", "alactic"]
    return athlete




def test_d13_splice_passes_parent_required_systems_to_existing_tail_owner(monkeypatch) -> None:
    weekly_role_map = {
        "weeks": [
            {
                "week_index": 2,
                "phase": "SPP",
                "calendar_days": [
                    {"weekday": "monday", "d_day": 14},
                    {"weekday": "tuesday", "d_day": 13},
                ],
                "resolved_rule_state": {
                    "must_keep": ["rehab", "glycolytic", "alactic", "primary_strength"]
                },
                "session_roles": [_role("normal_d13", 13, "tuesday")],
                "intentionally_unused_days": [],
            }
        ]
    }
    captured: dict = {}

    def fake_finished_tail(days_until_fight, model, *, start_day):
        captured["systems"] = model.get("handoff_required_conditioning_systems")
        return {
            "session_sequence": [_role("late_d13", 13, "tuesday")],
            "day_metadata": {
                13: {
                    "stage_key": "d13_to_d8",
                    "payload_mode": "pre_fight_compressed_payload",
                }
            },
            "segments": [
                {
                    "stage_key": "d13_to_d8",
                    "payload_mode": "pre_fight_compressed_payload",
                    "countdown_span": {"start_day": 13, "end_day": 8},
                }
            ],
        }

    monkeypatch.setattr(fillers, "build_finished_late_fight_tail", fake_finished_tail)
    assert _splice_late_fight_tail(
        weekly_role_map,
        {"days_until_fight": 22, "training_days": ["monday", "tuesday"]},
    ) is True
    assert captured["systems"] == ["glycolytic", "alactic"]


def test_production_shaped_d22_handoff_keeps_required_alactic_inside_d13_to_d8() -> None:
    tail = build_finished_late_fight_tail(22, _d22_athlete(handoff=True), start_day=13)
    alactic_offsets = [
        role.get("countdown_offset")
        for role in tail.get("session_sequence", [])
        if isinstance(role, dict)
        and role.get("role_key") == "alactic_sharpness_day"
        and isinstance(role.get("countdown_offset"), int)
    ]
    assert any(8 <= offset <= 13 for offset in alactic_offsets)

    hard_glycolytic_keys = {
        "fight_pace_repeatability_day",
        "main_fight_pace_day",
        "highest_glycolytic_day",
        "controlled_repeatability_day",
    }
    assert not any(
        isinstance(role, dict)
        and role.get("role_key") in hard_glycolytic_keys
        and isinstance(role.get("countdown_offset"), int)
        and 8 <= role["countdown_offset"] <= 13
        for role in tail.get("session_sequence", [])
    )


def test_direct_d13_path_is_unchanged_without_parent_handoff_context() -> None:
    tail = build_finished_late_fight_tail(22, _d22_athlete(), start_day=13)
    assert not any(
        isinstance(role, dict)
        and role.get("role_key") == "alactic_sharpness_day"
        and isinstance(role.get("countdown_offset"), int)
        and 8 <= role["countdown_offset"] <= 13
        for role in tail.get("session_sequence", [])
    )



@pytest.mark.parametrize("case", ["gpp", "taper", "separate_weeks", "already_survives", "no_required_intent"])
def test_splice_does_not_signal_unrelated_or_satisfied_parent_intent(monkeypatch, case):
    parent = {
        "phase": "SPP",
        "calendar_days": [{"weekday": "monday", "d_day": 14}, {"weekday": "tuesday", "d_day": 13}],
        "resolved_rule_state": {"must_keep": ["alactic"]},
        "session_roles": [],
    }
    weeks = [parent]
    if case in {"gpp", "taper"}:
        parent["phase"] = case.upper()
    elif case == "separate_weeks":
        parent["calendar_days"] = [{"weekday": "tuesday", "d_day": 13}]
        weeks.insert(0, {"phase": "SPP", "calendar_days": [{"weekday": "monday", "d_day": 14}]})
    elif case == "already_survives":
        parent["session_roles"] = [{**_role("alactic", 14, "monday"), "preferred_system": "alactic"}]
    else:
        parent["resolved_rule_state"] = {}
    captured = []
    def capture(days, model, *, start_day):
        captured.append(model)
        return {}
    monkeypatch.setattr(fillers, "build_finished_late_fight_tail", capture)
    athlete = _d22_athlete(handoff=True)
    _splice_late_fight_tail({"weeks": weeks}, athlete)
    assert len(captured) == 1
    assert "handoff_required_conditioning_systems" not in captured[0]
    assert athlete["handoff_required_conditioning_systems"] == ["glycolytic", "alactic"]


def test_real_splice_preserves_unmet_parent_alactic_intent():
    week = {
        "week_index": 2,
        "phase": "SPP",
        "calendar_days": [
            {"weekday": day, "d_day": offset}
            for day, offset in zip(
                ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"],
                range(14, 7, -1),
            )
        ],
        "resolved_rule_state": {"must_keep": ["glycolytic", "alactic"]},
        "session_roles": [_role("normal_d14", 14, "monday")],
        "intentionally_unused_days": [],
    }
    assert _splice_late_fight_tail({"weeks": [week]}, _d22_athlete())
    assert any(
        role["role_key"] == "alactic_sharpness_day"
        and 8 <= role["countdown_offset"] <= 13
        and role["late_fight_tail_owned"]
        for role in week["session_roles"]
    )
    assert any(role["role_key"] == "normal_d14" for role in week["session_roles"])
