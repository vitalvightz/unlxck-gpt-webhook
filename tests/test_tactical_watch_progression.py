from __future__ import annotations

from fightcamp.camp_week_fillers import apply_camp_week_fillers
from fightcamp.gap_fill_inserts import (
    apply_gap_fill_inserts,
    build_tactical_watch_template,
)


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
            {"weekday": "friday", "d_day": d_day - 4},
        ],
        "intentionally_unused_days": [
            {"day": "Wednesday", "role": "recovery_only_day"},
            {"day": "Friday", "role": "off_day"},
        ],
        "declared_training_days": ["Monday", "Wednesday", "Friday"],
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


def _assert_four_line_output(display_text: str) -> None:
    assert display_text.count("Entry cue:") == 1
    assert display_text.count("Danger cue:") == 1
    assert display_text.count("Reset cue:") == 1
    assert display_text.count("Round 1:") == 1


def test_normal_camp_watch_content_progresses_by_phase_and_week():
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

    watches = [_watches(week["session_roles"])[0] for week in role_map["weeks"]]
    assert [watch["tactical_watch_phase"] for watch in watches] == [
        "GPP",
        "GPP",
        "GPP",
        "SPP",
        "SPP",
        "SPP",
        "TAPER",
    ]
    assert len({watch["tactical_watch_variant"] for watch in watches[:3]}) == 3
    assert len({watch["tactical_watch_variant"] for watch in watches[3:6]}) == 3
    assert len({watch["display_text"] for watch in watches}) == len(watches)
    assert watches[0]["athlete_facing_label"].startswith("GPP Tactical Watch:")
    assert watches[3]["athlete_facing_label"].startswith("SPP Tactical Watch:")
    assert watches[6]["athlete_facing_label"].startswith("TAPER Tactical Watch:")
    assert "own recent footage" in watches[0]["display_text"].lower()
    assert "confirmed opponent" in watches[3]["display_text"].lower()
    assert "add no new tactical theory" in watches[6]["display_text"].lower()
    for watch in watches:
        _assert_four_line_output(watch["display_text"])


def test_direct_template_keeps_four_cue_contract_across_phases():
    templates = [
        build_tactical_watch_template(_athlete(), phase="GPP", variation_seed=42),
        build_tactical_watch_template(_athlete(), phase="SPP", variation_seed=21),
        build_tactical_watch_template(_athlete(), phase="TAPER", variation_seed=7),
    ]
    assert len(set(templates)) == 3
    for template in templates:
        _assert_four_line_output(template)


def test_late_fight_watch_progression_uses_spp_then_taper():
    sequence = apply_gap_fill_inserts(
        [_session(21), _session(16), _session(11), _session(6)],
        _athlete(days_until_fight=21),
    )
    watches_by_segment = {
        watch["tactical_watch_segment"]: watch for watch in _watches(sequence)
    }
    assert watches_by_segment[0]["tactical_watch_phase"] == "TAPER"
    assert watches_by_segment[1]["tactical_watch_phase"] == "SPP"
    assert watches_by_segment[2]["tactical_watch_phase"] == "SPP"
    assert (
        watches_by_segment[1]["tactical_watch_variant"]
        != watches_by_segment[2]["tactical_watch_variant"]
    )
    assert "add no new tactical theory" in (
        watches_by_segment[0]["display_text"].lower()
    )
    assert "confirmed opponent" in watches_by_segment[1]["display_text"].lower()
    for watch in watches_by_segment.values():
        _assert_four_line_output(watch["display_text"])


def test_existing_watch_promotion_preserves_unrelated_metadata():
    week = _week("SPP", 28)
    week["session_roles"].append(
        {
            "role_key": "tactical_watch",
            "category": "support_insert",
            "scheduled_day_hint": "Wednesday",
            "display_text": "legacy repeated content",
            "source_trace_id": "watch-existing-1",
        }
    )
    apply_camp_week_fillers({"weeks": [week]}, _athlete(days_until_fight=28))

    watch = _watches(week["session_roles"])[0]
    assert watch["source_trace_id"] == "watch-existing-1"
    assert watch["display_text"] != "legacy repeated content"
    assert watch["tactical_watch_phase"] == "SPP"
