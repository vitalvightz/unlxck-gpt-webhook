"""Deterministic doses must reach Stage 2 and be recognised on the way back.

Every failure these cover was observed in production, not hypothesised:

* Every conditioning bank entry serialised to an EMPTY prescription, because the
  serializer read ``timing``/``rest``/``load`` while the banks author their dose
  in ``duration``. Stage 2 was handed scheduled drills with no dose and had to
  invent one.
* ``_goal_witness_dose_matches`` demanded a time unit from every witness holding
  ``work_sec``/``rounds``, so a correctly rendered rep-shaped drill
  ("4 x 5/side") read as a missing witness.
* ``_parse_sets_reps`` read "2 x 20 m" as 20 reps, letting the countdown overlay
  rewrite a carry microdose and drop its metres.
* The deterministic card fallback published internal placement rationale as the
  athlete-facing objective.
"""

import json

import pytest

from fightcamp.goal_preservation import _sync_microdose_membership
from fightcamp.role_labels import athlete_facing_label_for
from fightcamp.prescription_resolver import (
    _parse_sets_reps,
    resolve_strength_slot_prescription,
)
from fightcamp.stage2_payload import _serialize_conditioning_option
from fightcamp.stage2_validator import _goal_witness_dose_matches
from fightcamp.strength import DATA_DIR

_CONDITIONING_BANKS = (
    "conditioning_bank.json",
    "style_conditioning_bank.json",
    "technical_footwork_bank.json",
)


def _bank(name: str) -> list[dict]:
    return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))


# --------------------------------------------------------------------------- #
# Conditioning drills must carry their authored dose into Stage 2.
# --------------------------------------------------------------------------- #
def test_no_conditioning_entry_serialises_to_an_empty_prescription():
    missing = []
    for bank_name in _CONDITIONING_BANKS:
        for drill in _bank(bank_name):
            option = _serialize_conditioning_option(drill, "aerobic", "why")
            if not str(option.get("prescription") or "").strip():
                missing.append(f"{bank_name}:{drill.get('name')}")
    assert not missing, f"{len(missing)} drills reach Stage 2 with no dose: {missing[:10]}"


@pytest.mark.parametrize(
    "name, expected",
    [
        ("Alternating Bounds", "4x5/side, 2min rest"),
        ("Nasal Shadowboxing Flow (Gas Tank)", "12-20min continuous"),
    ],
)
def test_authored_duration_is_carried_verbatim(name, expected):
    drill = next(d for d in _bank("conditioning_bank.json") if d.get("name") == name)
    assert _serialize_conditioning_option(drill, "aerobic", "why")["prescription"] == expected


def test_explicit_timing_still_wins_over_duration():
    """The existing timing/rest/load contract is unchanged where it is authored."""
    drill = {"name": "X", "timing": "8 x 8s", "rest": "90s", "duration": "ignored"}
    assert _serialize_conditioning_option(drill, "alactic", "why")["prescription"] == "8 x 8s | 90s"


# --------------------------------------------------------------------------- #
# A rep-shaped authored dose must be recognised when rendered rep-shaped.
# --------------------------------------------------------------------------- #
REP_WITNESS = {
    "name": "Alternating Bounds",
    "rounds": 4,
    "work_sec": 5,
    "rest_sec": 120,
    "effective_prescription": "4x5/side, 2min rest",
}
TIMED_WITNESS = {
    "name": "Range Reset Intervals",
    "rounds": 6,
    "work_sec": 45,
    "rest_sec": 45,
    "effective_prescription": "45s work / 45s rest x 6 rounds",
}


@pytest.mark.parametrize(
    "rendered",
    [
        "4 x 5/side; work ~5 s per rep; rest 120 s between sets; RPE 6-7 max.",
        "4 x 5/side, 2 min rest. 5 sec work bursts. RPE 6-7.",
        "4 x 5/side; 2 min rest between sets.",
        "4 x 5/side, rest 2:00.",
        "5 x 6/side, rest 2:00.",  # above the authored dose is still a match
    ],
)
def test_rep_shaped_witness_matches_a_rep_shaped_rendering(rendered):
    assert _goal_witness_dose_matches(REP_WITNESS, rendered)


@pytest.mark.parametrize("rendered", ["3 x 5/side, rest 2:00.", "4 x 3/side, rest 2:00."])
def test_rep_shaped_witness_still_rejects_under_dosing(rendered):
    """The matcher is corrected, not weakened."""
    assert not _goal_witness_dose_matches(REP_WITNESS, rendered)


@pytest.mark.parametrize(
    "rendered, expected",
    [
        ("6 rounds x 45 seconds, rest 45 sec", True),
        ("6 rounds x 30 seconds, rest 45 sec", False),  # under work_sec
        ("4 x 5/side, rest 2:00.", False),              # rep-shaped ≠ timed witness
    ],
)
def test_timed_witness_keeps_strict_timed_matching(rendered, expected):
    assert _goal_witness_dose_matches(TIMED_WITNESS, rendered) is expected


# --------------------------------------------------------------------------- #
# A distance/time dose is never read as reps.
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize(
    "dose, expected",
    [
        ("2 x 20 m @ RPE 7", (None, None)),
        ("2 x 20 km", (None, None)),
        ("3 x 30s hold", (None, None)),
        ("3 x 45 seconds", (None, None)),
        ("4 x 3 @ RPE 7", (4, 3)),
        ("3x8-12 @ 60-75% 1RM", (3, 8)),
        ("4 x 6 reps", (4, 6)),
    ],
)
def test_parse_sets_reps_ignores_a_unit_bearing_second_term(dose, expected):
    assert _parse_sets_reps(dose) == expected


def test_carry_microdose_keeps_its_unit_through_the_countdown_overlay():
    """The manifest and the effective-prescription envelope must not diverge."""
    microdose = {
        "goal": "strength",
        "name": "Loaded Carry Touch",
        "prescription": "2 x 20 m @ RPE 7",
        "sets": 2,
        "intents": ["meaningful_strength"],
        "authority": "v1",
    }
    role = {
        "role_key": "primary_strength_day",
        "category": "strength",
        "selected_exercise_assignments": [],
        "scheduled_d_day": 16,
        "strength_dose_cap": {"max_sets": 3, "max_reps": 3, "loaded_allowed": True},
        "rpe_cap": "6-7",
    }
    _sync_microdose_membership(role, microdose)
    assignment = role["selected_exercise_assignments"][0]
    slot = {
        "slot_id": assignment["slot_id"],
        "priority": 1,
        "session_index": 1,
        "quality_class": "anchor_loaded",
        "anchor_capable": True,
        "selected": {
            "name": "Loaded Carry Touch",
            "prescription": "2 x 20 m @ RPE 7",
            "quality_class": "anchor_loaded",
            "anchor_capable": True,
        },
    }
    resolved = resolve_strength_slot_prescription(role=role, slot=slot, athlete_state={})
    assert resolved["effective_prescription"] == assignment["effective_prescription"]
    assert "20 m" in resolved["effective_prescription"]

    # Still reduce-only: a tighter band lowers the carry count, keeps the unit.
    role["strength_dose_cap"] = {"max_sets": 1, "max_reps": 3, "loaded_allowed": True}
    tightened = resolve_strength_slot_prescription(role=role, slot=slot, athlete_state={})
    assert tightened["effective_prescription"] == "1 x 20 m @ RPE 7"


# --------------------------------------------------------------------------- #
# Internal placement rationale is never the athlete-facing objective.
# --------------------------------------------------------------------------- #
def test_deterministic_card_objective_is_not_internal_placement_rationale():
    from api.structured_plan_deterministic_fallback import _session

    role = {
        "role_key": "primary_strength_day",
        "category": "strength",
        "athlete_facing_label": "Primary Strength",
        "session_index": 1,
        "day_assignment_reason": (
            "Use the lowest-load day immediately before the primary strength anchor."
        ),
        "selected_exercise_assignments": [
            {"name": "Trap Bar Deadlift", "effective_prescription": "4 x 3 @ RPE 7"}
        ],
    }
    session = _session(role, 20)
    assert session is not None
    assert "lowest-load" not in session["objective"]
    assert "anchor" not in session["objective"].lower()
    # The canonical athlete-facing role label, not planner rationale.
    assert session["objective"] == athlete_facing_label_for("primary_strength_day")
    assert session["objective"] == session["title"]
    # The internal field itself is preserved for audit.
    assert role["day_assignment_reason"]
