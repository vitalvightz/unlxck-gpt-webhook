from __future__ import annotations

from copy import deepcopy

import pytest

from fightcamp import conditioning
from fightcamp.stage2_payload import _serialize_conditioning_option


BANK = {drill["name"]: drill for drill in conditioning.get_technical_footwork_bank()}
EXTERNAL_CUE_SOURCES = {"coach", "partner", "visual"}
SIDE_RULES = {"both_directions", "athlete_primary_stance", "alternate_stances"}


def _flags(*, sport: str = "boxing", style: str = "counter_striker", **over) -> dict:
    flags = {
        "phase": "SPP",
        "fatigue": "low",
        "sport": sport,
        "fight_format": sport,
        "style_tactical": [style],
        "style_technical": [sport],
        "equipment": ["bodyweight"],
        "training_days": ["Mon"],
        "training_frequency": 1,
        "days_available": 1,
        "key_goals": ["footwork"],
        "weaknesses": [],
        "injuries": [],
        "days_until_fight": 21,
        "time_to_fight_days": 21,
        "random_seed": 7,
        "stance": "orthodox",
    }
    flags.update(over)
    return flags


@pytest.mark.parametrize(
    ("sport", "style", "expected_name", "expected_functions", "forbidden_functions"),
    [
        (
            "boxing",
            "counter_striker",
            "Step-Back Pivot Reset",
            {"counter_setup", "defensive_exit", "angle_creation"},
            {"ring_cutting"},
        ),
        (
            "boxing",
            "pressure_fighter",
            "Pressure Step-Cut Reset",
            {"pressure", "ring_cutting", "exit_lane_control"},
            set(),
        ),
        (
            "boxing",
            "distance_striker",
            "Step-Back Pivot Reset",
            {"range_management", "defensive_exit"},
            set(),
        ),
        (
            "muay_thai",
            "kicker",
            "Teep Retreat and Re-Stance",
            {"kick_recovery", "range_management"},
            set(),
        ),
        (
            "mma",
            "wrestler",
            "Sprawl Exit to Ring Angle",
            {"takedown_defense", "scramble_recovery"},
            set(),
        ),
    ],
)
def test_style_function_preferences_rank_the_valid_sport_pool(
    sport: str,
    style: str,
    expected_name: str,
    expected_functions: set[str],
    forbidden_functions: set[str],
):
    selected = conditioning.select_technical_footwork_drill(
        _flags(sport=sport, style=style), set(), []
    )

    assert selected is not None
    assert selected["name"] == expected_name
    functions = set(selected["tactical_function"])
    assert expected_functions <= functions
    assert not (forbidden_functions & functions)


@pytest.mark.parametrize(
    ("sport", "style", "expected_name", "reason_function"),
    [
        ("boxing", "counter_striker", "Step-Back Pivot Reset", "counter_setup"),
        ("boxing", "pressure_fighter", "Pressure Step-Cut Reset", "ring_cutting"),
        ("boxing", "distance_striker", "Step-Back Pivot Reset", "range_management"),
        ("muay_thai", "kicker", "Teep Retreat and Re-Stance", "kick_recovery"),
        ("mma", "wrestler", "Sprawl Exit to Ring Angle", "takedown_defense"),
    ],
)
def test_full_generator_preserves_style_choice_and_structured_reason_codes(
    sport: str, style: str, expected_name: str, reason_function: str
):
    _markdown, _names, why_log, grouped, *_rest = conditioning.generate_conditioning_block(
        _flags(sport=sport, style=style)
    )

    selected = grouped.get(conditioning.TECHNICAL_FOOTWORK_GROUP, [])
    assert [drill["name"] for drill in selected] == [expected_name]
    evidence = next(entry for entry in why_log if entry["name"] == expected_name)
    assert (
        f"technical_footwork_function_match:{reason_function}"
        in evidence["reasons"]["reason_codes"]
    )


def test_sport_gate_beats_a_cross_sport_function_match():
    selected = conditioning.select_technical_footwork_drill(
        _flags(sport="boxing", style="wrestler"), set(), []
    )

    assert selected is not None
    assert "boxing" in selected["tags"]
    assert "mma" not in selected["tags"]
    assert "wrestling" not in selected["tags"]


def test_shared_style_aliases_feed_function_preferences():
    selected = conditioning.select_technical_footwork_drill(
        _flags(style="out-boxer"), set(), []
    )

    assert selected is not None
    assert selected["name"] == "Step-Back Pivot Reset"
    reasons = conditioning._technical_footwork_selection_reasons(
        _flags(style="out-boxer"), selected
    )
    assert "distance_striker" in reasons["technical_footwork_styles"]


def test_every_reactive_drill_has_an_external_random_cue():
    reactive = [drill for drill in BANK.values() if drill["reactive_level"] == "reactive"]
    assert reactive
    for drill in reactive:
        assert set(drill["cue_source"]) & EXTERNAL_CUE_SOURCES, drill["name"]
        assert drill["cue"].strip(), drill["name"]


def test_closed_drills_remain_solo_executable():
    closed = [drill for drill in BANK.values() if drill["reactive_level"] == "closed"]
    assert closed
    assert all("self" in drill["cue_source"] for drill in closed)


def test_partner_required_drill_is_filtered_when_partner_is_unavailable(monkeypatch):
    drill = deepcopy(BANK["Pressure Step-Cut Reset"])
    drill["partner_required"] = True
    drill["cue_source"] = ["partner"]
    monkeypatch.setattr(conditioning, "get_technical_footwork_bank", lambda: [drill])

    assert (
        conditioning.select_technical_footwork_drill(
            _flags(equipment=["bodyweight"]), set(), []
        )
        is None
    )
    assert (
        conditioning.select_technical_footwork_drill(
            _flags(equipment=["bodyweight", "partner"]), set(), []
        )["name"]
        == drill["name"]
    )


def test_side_sensitive_drills_have_a_supported_side_rule():
    side_sensitive_directions = {"lateral", "rotational", "diagonal", "multi_directional"}
    side_sensitive = [
        drill for drill in BANK.values() if drill["directionality"] in side_sensitive_directions
    ]
    assert side_sensitive
    for drill in side_sensitive:
        assert drill["side_rule"] in SIDE_RULES, drill["name"]


def test_missing_stance_degrades_to_neutral_bilateral_instruction():
    markdown, *_rest = conditioning.generate_conditioning_block(_flags(stance=""))

    assert "Side / Stance: Work both directions evenly from your normal stance." in markdown


def test_switch_step_renders_alternating_stances_without_raw_enum_names():
    drill = BANK["Switch-Step Stance Recovery"]
    markdown = conditioning.render_conditioning_block(
        {conditioning.TECHNICAL_FOOTWORK_GROUP: [drill]},
        phase="SPP",
        phase_color="#000",
        sport="muay_thai",
        stance="switch",
    )

    assert "Side / Stance: Alternate orthodox and southpaw stances each rep." in markdown
    assert "alternate_stances" not in markdown


def test_high_complexity_reactive_work_uses_quality_reps_not_fake_timing():
    converted = {
        "Pressure Step-Cut Reset",
        "Scramble-to-Strike Rebase",
        "Sprawl Exit to Ring Angle",
        "Level-Change Feint to Angle",
    }
    for name in converted:
        drill = BANK[name]
        assert drill["sets"] > 0
        assert drill.get("reps", drill.get("reps_per_side", 0)) > 0
        assert drill["quality_stop_rule"].strip()
        assert "work_sec" not in drill
        assert "rounds" not in drill
        assert "total_minutes" not in drill
        assert "75 sec technical sets" not in drill["duration"]


def test_simple_low_cost_movement_can_remain_time_based():
    drill = BANK["Stance Reset Line Drill"]

    assert drill["work_sec"] == 60
    assert drill["rounds"] == 2
    assert "sets" not in drill


def test_rep_based_dose_renders_and_serializes_without_fake_work_duration():
    flags = _flags(style="pressure_fighter")
    markdown, _names, _why, grouped, *_rest = conditioning.generate_conditioning_block(flags)
    drill = grouped[conditioning.TECHNICAL_FOOTWORK_GROUP][0]
    option = _serialize_conditioning_option(
        drill,
        conditioning.TECHNICAL_FOOTWORK_GROUP,
        "style-function match",
    )

    assert "Timing: 2 sets x 4 clean reactions each direction" in markdown
    assert "Quality Stop:" in markdown
    assert "2 sets x 4 clean reactions each direction" in option["prescription"]
    structured = option["technical_footwork_prescription"]
    assert structured["sets"] == 2
    assert structured["reps_per_side"] == 4
    assert "work_sec" not in structured


def test_reactive_schema_rejects_self_only_cueing():
    invalid = deepcopy(BANK["Pressure Step-Cut Reset"])
    invalid["cue_source"] = ["self"]

    with pytest.raises(ValueError, match="external/random cue source"):
        conditioning._validate_technical_footwork_entry(invalid)
