from __future__ import annotations

from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.gap_fill_inserts import apply_gap_fill_inserts


def _athlete(**overrides):
    athlete = {
        "sport": "boxing",
        "days_until_fight": 49,
        "plan_creation_weekday": "monday",
        "hard_sparring_days": [],
        "fatigue": "low",
        "fatigue_level": "low",
        "readiness_flags": [],
        "weight_cut_risk": False,
        "weight_cut_pct": 0.0,
        "weaknesses": [],
        "key_goals": [],
        "injuries": [],
        "parsed_injuries": [],
        "guided_injury": None,
        "injury_restrictions": [],
    }
    athlete.update(overrides)
    return athlete


def _week(phase: str, d_day: int) -> dict:
    return {
        "phase": phase,
        "session_roles": [
            {
                "role_key": "primary_strength_day",
                "category": "strength",
                "scheduled_day_hint": "Monday",
            }
        ],
        "calendar_days": [
            {"weekday": "monday", "d_day": d_day},
            {"weekday": "wednesday", "d_day": d_day - 2},
        ],
        "intentionally_unused_days": [
            {"day": "Wednesday", "role": "recovery_only_day"}
        ],
        "declared_training_days": ["Monday", "Wednesday"],
    }


def _session(offset: int) -> dict:
    return {
        "session_index": 1,
        "category": "strength",
        "role_key": "strength_touch_day",
        "scheduled_day_hint": "monday",
        "countdown_offset": offset,
        "countdown_label": f"D-{offset}",
        "scheduled_countdown_label": f"D-{offset}",
    }


def _watches(roles: list[dict]) -> list[dict]:
    return [role for role in roles if role.get("role_key") == "tactical_watch"]


def test_normal_camp_uses_ordered_phase_sequences():
    role_map = {
        "weeks": [
            _week("GPP", 49),
            _week("GPP", 42),
            _week("GPP", 35),
            _week("SPP", 28),
            _week("SPP", 21),
            _week("SPP", 14),
            _week("TAPER", 7),
        ]
    }
    apply_camp_week_fillers(role_map, _athlete())

    variants = [
        _watches(week["session_roles"])[0]["tactical_watch_variant"]
        for week in role_map["weeks"]
    ]
    assert variants == [
        "style_baseline",
        "rhythm_control",
        "entry_creation",
        "rhythm_triggers",
        "first_exchange",
        "entry_route",
        "round_one_confirmation",
    ]


def test_late_fight_uses_spp_sequence_then_taper_confirmation():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6)],
        _athlete(days_until_fight=21),
    )
    watches = {
        watch["tactical_watch_segment"]: watch for watch in _watches(sequence)
    }

    assert watches[2]["tactical_watch_variant"] == "rhythm_triggers"
    assert watches[1]["tactical_watch_variant"] == "first_exchange"
    assert watches[0]["tactical_watch_variant"] == "round_one_confirmation"
    assert "add no new tactical theory" in watches[0]["display_text"].lower()
