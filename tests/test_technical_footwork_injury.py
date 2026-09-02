"""Blocker-3 regression: technical footwork mech_* tags are reconciled to the
canonical injury vocabulary and are gated by the *real* injury guard.

The technical footwork bank originally introduced a parallel mechanical-risk
vocabulary (``mech_braking``, ``mech_lateral_knee``, ``mech_level_change``,
``mech_ground_transition``, ``mech_single_leg``, ``mech_ankle_stability``) that
no injury rule read, so genuine knee/ankle/Achilles/hip loads never interacted
with the injury system. These tests pin the reconciliation:

* every ``mech_*`` tag in the bank is canonical injury vocabulary (i.e. read by
  ``INJURY_RULES``);
* the two genuinely-new demands (``mech_plantarflexion`` / ``mech_hip_rotation``)
  are wired into the relevant regions;
* real (not monkeypatched) knee, ankle, Achilles, hip and lower-limb injuries
  exclude the drills that load them, while the neutral fallback stays safe.
"""
from __future__ import annotations

import pytest

from fightcamp import conditioning
from fightcamp.injury_exclusion_rules import INJURY_RULES
from fightcamp.injury_guard import injury_decision


BANK = {d["name"]: d for d in conditioning.get_technical_footwork_bank()}


def _bank_mech_tags() -> set[str]:
    tags: set[str] = set()
    for drill in BANK.values():
        tags.update(t for t in drill.get("tags", []) if str(t).startswith("mech_"))
        tags.update(t for t in drill.get("mechanical_risk_tags", []) if str(t).startswith("mech_"))
    return tags


def _injury_rule_mech_tags() -> set[str]:
    tags: set[str] = set()
    for rule in INJURY_RULES.values():
        tags.update(t for t in rule.get("ban_tags", []) if str(t).startswith("mech_"))
    return tags


# The invented, non-canonical tokens the reclassification must no longer use.
_RETIRED_TAGS = {
    "mech_braking",
    "mech_lateral_knee",
    "mech_level_change",
    "mech_ground_transition",
    "mech_single_leg",
    "mech_ankle_stability",
}


def test_bank_mech_tags_are_all_canonical_injury_vocabulary():
    # Every mech_* tag the bank uses must be a tag the injury rules actually read
    # (no parallel vocabulary). Reuse over invention.
    bank_tags = _bank_mech_tags()
    assert bank_tags, "expected the footwork bank to carry mechanical tags"
    wired = _injury_rule_mech_tags()
    orphans = bank_tags - wired
    assert not orphans, f"footwork mech tags not wired into any injury rule: {sorted(orphans)}"


def test_retired_invented_tags_are_gone():
    assert _bank_mech_tags().isdisjoint(_RETIRED_TAGS), _bank_mech_tags() & _RETIRED_TAGS


def test_new_tags_are_wired_into_expected_regions():
    # mech_plantarflexion protects the plantarflexor / lower-leg chain.
    for region in ("achilles", "calf", "ankle", "foot"):
        assert "mech_plantarflexion" in INJURY_RULES[region]["ban_tags"], region
    # mech_hip_rotation protects the hip.
    assert "mech_hip_rotation" in INJURY_RULES["hip"]["ban_tags"]


# region, high-severity injury phrase, drills that must be EXCLUDED
_REGION_CASES = [
    (
        "knee",
        "torn acl in my knee",
        ["Lateral Exit to Re-Enter", "Pressure Step-Cut Reset",
         "Sprawl Exit to Ring Angle", "Level-Change Feint to Angle"],
    ),
    (
        "ankle",
        "badly torn ankle ligaments",
        ["Lateral Exit to Re-Enter", "Teep Retreat and Re-Stance",
         "Kick Exit and Re-Stance Walkthrough"],
    ),
    (
        "achilles",
        "ruptured achilles",
        ["Teep Retreat and Re-Stance", "Kick Exit and Re-Stance Walkthrough",
         "Check and Return Step", "Switch-Step Stance Recovery"],
    ),
    (
        "hip",
        "torn hip labrum",
        ["Step-Back Pivot Reset", "45-Degree Angle Step to Jab Reset",
         "Switch-Step Stance Recovery", "Clinch Exit Square-Up Reset"],
    ),
]


@pytest.mark.parametrize("region,injury,excluded", _REGION_CASES)
def test_real_injury_guard_excludes_loading_footwork(region, injury, excluded):
    # No monkeypatch: the actual injury_decision must exclude the drills whose
    # reconciled canonical tags load the injured region.
    for name in excluded:
        decision = injury_decision(BANK[name], [injury], "SPP", "low")
        assert decision.action == "exclude", (region, name, decision.action)


@pytest.mark.parametrize("region,injury,excluded", _REGION_CASES)
def test_neutral_stance_reset_stays_safe_for_every_region(region, injury, excluded):
    # Stance Reset Line Drill carries no mechanical-risk tag and must remain the
    # universally injury-safe fallback across knee/ankle/Achilles/hip.
    decision = injury_decision(BANK["Stance Reset Line Drill"], [injury], "SPP", "low")
    assert decision.action != "exclude", (region, decision.action)


def test_selector_returns_injury_safe_footwork_for_knee_injured_boxer():
    # End-to-end through the real selector (not the low-level guard): a
    # footwork-focused boxer with a serious knee injury still gets a footwork
    # drill, and it is one that does not load the knee.
    flags = dict(
        phase="GPP", fatigue="low", sport="boxing", fight_format="boxing",
        style_tactical=["counter_striker"], style_technical=["boxing"],
        equipment=["bodyweight"], key_goals=["footwork"], weaknesses=[],
        injuries=["torn acl in my knee"], days_until_fight=40,
    )
    drill = conditioning.select_technical_footwork_drill(flags, set(), flags["injuries"])
    assert drill is not None
    assert injury_decision(drill, flags["injuries"], "GPP", "low").action != "exclude"
    knee_tags = {t for t in INJURY_RULES["knee"]["ban_tags"] if t.startswith("mech_")}
    assert knee_tags.isdisjoint(drill.get("tags", [])), drill["name"]
