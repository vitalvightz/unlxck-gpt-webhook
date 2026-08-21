import json
import re
from pathlib import Path

import pytest

from fightcamp import conditioning
from fightcamp.style_taper_governance import (
    D13_TO_D8,
    D21_TO_D14,
    D7,
    D6_TO_D5,
    D4_TO_D2,
    D1,
    GENERIC_REACTIVE_TAG,
    RPE_MAX_BY_WINDOW,
    SPORT_TAGS,
    STYLE_TAGS,
    style_taper_entry_issues,
    style_taper_entry_window_eligible,
    style_taper_rpe_max_for_days,
    style_taper_window_for_days,
)

BANK_PATH = Path(__file__).resolve().parents[1] / "data" / "style_taper_conditioning.json"


def _load_bank():
    return json.loads(BANK_PATH.read_text())


def test_every_style_taper_entry_passes_isolated_governance():
    failures = {
        item.get("name", "<unnamed>"): style_taper_entry_issues(item)
        for item in _load_bank()
        if style_taper_entry_issues(item)
    }
    assert failures == {}


def test_style_taper_bank_does_not_use_generic_reactive_or_live_contact():
    for item in _load_bank():
        assert GENERIC_REACTIVE_TAG not in set(item.get("tags", []))
        assert item.get("contact_level") != "live"


def test_style_and_sport_coverage_is_complete():
    style_coverage = set()
    sport_coverage = set()
    for item in _load_bank():
        tags = set(item.get("tags", []))
        style_coverage.update(tags & STYLE_TAGS)
        sport_coverage.update(tags & SPORT_TAGS)

    assert style_coverage == STYLE_TAGS
    assert sport_coverage == SPORT_TAGS


def test_every_supported_style_has_a_zero_contact_d1_rehearsal():
    d1_style_coverage = set()
    for item in _load_bank():
        if D1 not in item.get("late_windows", []):
            continue
        assert item.get("contact_level") == "none"
        d1_style_coverage.update(set(item.get("tags", [])) & STYLE_TAGS)

    assert d1_style_coverage == STYLE_TAGS


def test_d1_entries_are_zero_contact_bodyweight_or_mat_only_and_rpe_three_or_lower():
    allowed_equipment = {"bodyweight", "none", "mat", "mats", "mat_space", "open_space", "floor"}
    for item in _load_bank():
        if D1 not in item.get("late_windows", []):
            continue
        assert item.get("contact_level") == "none"
        assert set(item.get("equipment", [])) <= allowed_equipment
        assert float(item.get("rpe_max")) <= 3


def test_d4_to_d2_bank_entries_never_use_cooperative_or_controlled_contact():
    for item in _load_bank():
        if D4_TO_D2 in item.get("late_windows", []):
            assert item.get("contact_level") in {"none", "touch"}


def test_known_cooperative_drills_stop_before_d4_to_d2():
    by_name = {item["name"]: item for item in _load_bank()}
    assert D4_TO_D2 not in by_name["Pummel-Frame-Exit Flow"]["late_windows"]
    assert D4_TO_D2 not in by_name["Circle-Re-shot Cue"]["late_windows"]


def test_style_taper_activation_is_explicitly_d13_and_under():
    assert all(D21_TO_D14 not in item.get("late_windows", []) for item in _load_bank())


@pytest.mark.parametrize(
    ("days_until_fight", "expected_window", "expected_rpe"),
    [
        (14, None, None),
        (13, D13_TO_D8, 6.0),
        (10, D13_TO_D8, 6.0),
        (8, D13_TO_D8, 6.0),
        (7, D7, 5.0),
        (6, D6_TO_D5, 5.0),
        (5, D6_TO_D5, 5.0),
        (4, D4_TO_D2, 4.0),
        (3, D4_TO_D2, 4.0),
        (2, D4_TO_D2, 4.0),
        (1, D1, 3.0),
        (0, None, None),
    ],
)
def test_d_day_mapping_and_rpe_policy_are_canonical(days_until_fight, expected_window, expected_rpe):
    assert style_taper_window_for_days(days_until_fight) == expected_window
    assert style_taper_rpe_max_for_days(days_until_fight) == expected_rpe


@pytest.mark.parametrize(
    ("window", "expected"),
    [
        (D21_TO_D14, False),
        (D13_TO_D8, False),
        (D7, False),
        (D6_TO_D5, True),
        (D4_TO_D2, True),
        (D1, False),
    ],
)
def test_declared_late_windows_control_eligibility(window, expected):
    item = {"late_windows": [D6_TO_D5, D4_TO_D2]}
    assert style_taper_entry_window_eligible(item, window) is expected


@pytest.mark.parametrize(
    ("window", "expected_eligible"),
    [
        (D21_TO_D14, False),
        (D13_TO_D8, False),
        (D7, False),
        (D6_TO_D5, True),
        (D4_TO_D2, True),
        (D1, False),
    ],
)
def test_production_conditioning_evaluator_hard_blocks_window_mismatch(window, expected_eligible):
    drill = {
        "name": "Window-Specific Tactical Primer",
        "phases": ["TAPER"],
        "system": "alactic",
        "tags": ["boxing", "counter_striker", "low_impact", "cns_freshness", "skill_refinement"],
        "late_windows": [D6_TO_D5, D4_TO_D2],
        "work_sec": 5,
        "rest_sec": 90,
        "rounds": 4,
        "rpe_max": 4,
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
    }
    result = conditioning._evaluate_conditioning_late_window(
        drill,
        system="alactic",
        window=window,
        bridge_rules={"glycolytic_touch_max": 0},
    )

    if expected_eligible:
        assert "late_conditioning_block_window_mismatch" not in result["block_codes"]
        assert result["blocked"] is False
    else:
        assert "late_conditioning_block_window_mismatch" in result["block_codes"]
        assert result["blocked"] is True


@pytest.mark.parametrize(
    ("days_until_fight", "window"),
    [
        (13, D13_TO_D8),
        (10, D13_TO_D8),
        (8, D13_TO_D8),
        (7, D7),
        (6, D6_TO_D5),
        (5, D6_TO_D5),
        (4, D4_TO_D2),
        (3, D4_TO_D2),
        (2, D4_TO_D2),
        (1, D1),
    ],
)
def test_runtime_athlete_facing_dosage_never_exceeds_governance(days_until_fight, window):
    text = conditioning._late_fight_dosage_caps(days_until_fight)
    stated_rpes = [float(value) for value in re.findall(r"RPE ≤(\d+(?:\.\d+)?)", text)]

    assert stated_rpes
    assert max(stated_rpes) <= RPE_MAX_BY_WINDOW[window]
    assert f"D-{days_until_fight} late-fight caps:" in text


def test_d13_renderer_uses_style_taper_caps_instead_of_generic_rpe_eight_to_nine():
    rendered = conditioning.render_conditioning_block(
        {},
        phase="TAPER",
        phase_color="",
        diagnostic_context={"days_until_fight": 13, "speed_dose_allowed": True},
    )

    assert "**Dosage Template:** D-13 late-fight caps:" in rendered
    assert "RPE ≤6" in rendered
    assert "RPE 8–9" not in rendered
    assert "**Speed Dose:**" not in rendered
    assert "RPE 7-8" not in rendered


def test_d4_to_d2_rejects_cooperative_contact():
    sample = {
        "name": "Late cooperative contact probe",
        "phases": ["TAPER"],
        "system": "alactic",
        "tags": ["mma", "wrestler", "tactical"],
        "late_windows": [D4_TO_D2],
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
        "rpe_max": 3,
        "execution_intent": "technical_crisp",
        "contact_level": "cooperative",
        "equipment": ["partner"],
    }
    assert f"contact_too_high:{D4_TO_D2}" in style_taper_entry_issues(sample)


def test_d7_allows_cooperative_contact_but_live_is_always_forbidden():
    base = {
        "name": "D7 contact probe",
        "phases": ["TAPER"],
        "system": "alactic",
        "tags": ["bjj", "grappler", "skill_refinement"],
        "late_windows": [D7],
        "impact_cost": "low",
        "movement_cost": "low",
        "lactate_load": "low",
        "stress_class": "support",
        "cost_class": "low",
        "support_only": True,
        "meaningful_stress": False,
        "rpe_max": 4,
        "execution_intent": "technical_crisp",
        "equipment": ["partner"],
    }
    assert style_taper_entry_issues(dict(base, contact_level="cooperative")) == []
    assert "live_contact_forbidden" in style_taper_entry_issues(dict(base, contact_level="live"))
