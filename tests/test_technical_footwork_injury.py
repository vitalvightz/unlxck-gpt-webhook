"""Real injury-guard regressions for the dedicated technical-footwork bank."""
from __future__ import annotations

import pytest

from fightcamp import conditioning
from fightcamp.injury_exclusion_rules import INJURY_RULES
from fightcamp.injury_guard import injury_decision

BANK = {d["name"]: d for d in conditioning.get_technical_footwork_bank()}
WEIGHT_BEARING_TAG = "mech_lower_limb_weight_bearing"


def _bank_mech_tags() -> set[str]:
    return {
        tag
        for drill in BANK.values()
        for field in ("tags", "mechanical_risk_tags")
        for tag in drill.get(field, [])
        if str(tag).startswith("mech_")
    }


def _injury_rule_mech_tags() -> set[str]:
    return {
        tag
        for rule in INJURY_RULES.values()
        for tag in rule.get("ban_tags", [])
        if str(tag).startswith("mech_")
    }


_RETIRED_TAGS = {
    "mech_braking", "mech_lateral_knee", "mech_level_change",
    "mech_ground_transition", "mech_single_leg", "mech_ankle_stability",
}


def test_bank_mech_tags_are_all_canonical_injury_vocabulary():
    assert not (_bank_mech_tags() - _injury_rule_mech_tags())


def test_retired_invented_tags_are_gone():
    assert _bank_mech_tags().isdisjoint(_RETIRED_TAGS)


def test_weight_bearing_tag_is_on_every_drill_and_wired_to_structural_regions():
    for drill in BANK.values():
        assert WEIGHT_BEARING_TAG in drill["tags"], drill["name"]
        assert WEIGHT_BEARING_TAG in drill["mechanical_risk_tags"], drill["name"]
    for region in ("achilles", "ankle", "hip", "knee"):
        assert WEIGHT_BEARING_TAG in INJURY_RULES[region]["ban_tags"], region


@pytest.mark.parametrize("injury", [
    "ruptured achilles",
    "torn acl in my knee",
    "badly torn ankle ligaments",
    "torn hip labrum",
])
def test_severe_lower_limb_injury_excludes_all_technical_footwork(injury):
    for drill in BANK.values():
        decision = injury_decision(drill, [injury], "SPP", "low")
        assert decision.action == "exclude", (injury, drill["name"], decision.action)

    flags = {
        "phase": "SPP", "fatigue": "low", "sport": "boxing",
        "fight_format": "boxing", "style_tactical": ["counter_striker"],
        "style_technical": ["boxing"], "equipment": ["bodyweight"],
        "key_goals": ["footwork"], "weaknesses": [], "injuries": [injury],
    }
    assert conditioning.select_technical_footwork_drill(flags, set(), [injury]) is None


def test_mild_wrist_issue_does_not_remove_lower_body_technical_footwork():
    injury = "mild wrist soreness"
    assert injury_decision(BANK["Stance Reset Line Drill"], [injury], "SPP", "low").action == "allow"
    flags = {
        "phase": "SPP", "fatigue": "low", "sport": "boxing",
        "fight_format": "boxing", "style_tactical": [], "style_technical": ["boxing"],
        "equipment": ["bodyweight"], "key_goals": ["footwork"], "weaknesses": [],
    }
    assert conditioning.select_technical_footwork_drill(flags, set(), [injury]) is not None


def test_lower_limb_severity_still_distinguishes_allow_modify_and_exclude():
    drill = BANK["Stance Reset Line Drill"]
    assert injury_decision(drill, ["mild knee soreness"], "TAPER", "low").action == "allow"
    assert injury_decision(drill, ["knee strain"], "TAPER", "low").action == "modify"
    assert injury_decision(drill, ["torn acl in my knee"], "TAPER", "low").action == "exclude"
