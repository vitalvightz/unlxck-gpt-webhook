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


# Every region in the standing weight-bearing chain (foot-to-hip axial load +
# the plantarflexor push-off chain) must read the shared weight-bearing tag, so a
# severe structural injury anywhere in it can omit standing technical footwork
# rather than fall through to a stance reset. Muscular movers whose region rules
# already gate their footwork-relevant load (groin/glute/hip_flexor/hamstring/
# quad) are deliberately excluded.
WEIGHT_BEARING_REGIONS = ("achilles", "ankle", "calf", "foot", "hip", "knee", "shin", "toe")


def test_weight_bearing_tag_is_on_every_drill_and_wired_to_structural_regions():
    for drill in BANK.values():
        assert WEIGHT_BEARING_TAG in drill["tags"], drill["name"]
        assert WEIGHT_BEARING_TAG in drill["mechanical_risk_tags"], drill["name"]
    for region in WEIGHT_BEARING_REGIONS:
        assert WEIGHT_BEARING_TAG in INJURY_RULES[region]["ban_tags"], region


@pytest.mark.parametrize("injury", [
    "ruptured achilles",
    "torn acl in my knee",
    "badly torn ankle ligaments",
    "torn hip labrum",
    # Distal weight-bearing chain added by the safety audit: a severe structural
    # injury here must also omit all technical footwork, not fall through to a
    # stance reset because the region rule did not read the weight-bearing tag.
    "severe shin fracture",
    "ruptured calf",
    "severe foot fracture",
    "broken toe",
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


# For the distal weight-bearing regions the audit newly wired, prove the tag
# preserves the full severity policy on a drill whose only weight-bearing
# demand is the generic tag (a plain stance reset, no plantarflexion/impact
# tags): mild allows, moderate modifies, severe excludes.
@pytest.mark.parametrize("region,mild,moderate,severe", [
    ("shin", "mild shin soreness", "shin strain", "severe shin fracture"),
    ("calf", "mild calf tightness", "calf strain", "ruptured calf"),
    ("foot", "mild foot soreness", "foot strain", "severe foot fracture"),
    ("toe", "mild toe soreness", "toe strain", "broken toe"),
])
def test_distal_weight_bearing_regions_keep_allow_modify_exclude(region, mild, moderate, severe):
    drill = BANK["Stance Reset Line Drill"]
    assert injury_decision(drill, [mild], "SPP", "low").action == "allow", region
    assert injury_decision(drill, [moderate], "SPP", "low").action == "modify", region
    assert injury_decision(drill, [severe], "SPP", "low").action == "exclude", region


@pytest.mark.parametrize("injury", [
    "severe shin fracture",
    "ruptured calf",
    "severe foot fracture",
    "broken toe",
])
def test_selector_omits_all_footwork_for_severe_distal_weight_bearing_injury(injury):
    flags = {
        "phase": "SPP", "fatigue": "low", "sport": "boxing",
        "fight_format": "boxing", "style_tactical": ["counter_striker"],
        "style_technical": ["boxing"], "equipment": ["bodyweight"],
        "key_goals": ["footwork"], "weaknesses": [], "injuries": [injury],
    }
    assert conditioning.select_technical_footwork_drill(flags, set(), [injury]) is None
