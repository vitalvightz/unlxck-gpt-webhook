import json
from pathlib import Path

import pytest

from fightcamp.style_taper_governance import (
    D13_TO_D8,
    D21_TO_D14,
    D7,
    D6_TO_D5,
    D4_TO_D2,
    D1,
    GENERIC_REACTIVE_TAG,
    style_taper_entry_issues,
    style_taper_entry_window_eligible,
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


def test_d1_entries_are_zero_contact_bodyweight_only_and_rpe_three_or_lower():
    allowed_equipment = {"bodyweight", "none", "mat", "mats", "mat_space", "open_space", "floor"}
    for item in _load_bank():
        if D1 not in item.get("late_windows", []):
            continue
        assert item.get("contact_level") == "none"
        assert set(item.get("equipment", [])) <= allowed_equipment
        assert float(item.get("rpe_max")) <= 3


def test_style_taper_activation_is_explicitly_d13_and_under():
    assert all(D21_TO_D14 not in item.get("late_windows", []) for item in _load_bank())


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
