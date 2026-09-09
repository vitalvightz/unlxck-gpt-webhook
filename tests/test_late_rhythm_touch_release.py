"""The late-camp rhythm touch must be resolvable, and a safe empty day must ship.

Two production failures, one cause each:

1. The allocator declared ``light_fight_pace_touch_day`` as ``glycolytic``. That
   sent ``_slot_matches_role`` at the SPP glycolytic pool, whose hard RPE-9
   development work late-window governance correctly rejects, so D-11 had no
   assignment. ``_morph_to_rhythm_touch`` already resolves the identical role key
   as aerobic maintenance; the allocator now matches it.

2. That empty day was reported as a release blocker, holding an otherwise-valid
   plan. Governance refusing every candidate is an explained, safe omission --
   unlike an unexplained empty assignment, which stays a blocker.
"""

from __future__ import annotations

import copy

import pytest

from fightcamp import late_camp_role_morph
from fightcamp.planner_authority_integrity import (
    LATE_PHYSICAL_ROLE_SAFE_OMISSION_CODE,
    PLANNER_AUTHORITY_BLOCKER_CODES,
    planner_authority_findings,
)


def _role(**over) -> dict:
    role = {
        "role_key": "light_fight_pace_touch_day",
        "category": "conditioning",
        "late_fight_tail_owned": True,
        "selected_exercise_assignments": [],
        "scheduled_countdown_label": "D-11",
    }
    role.update(over)
    return role


def _brief(role: dict) -> dict:
    return {"weekly_role_map": {"weeks": [{"phase": "SPP", "session_roles": [role]}]}}


def _findings(role: dict):
    found = planner_authority_findings(_brief(role))
    blockers = [f for f in found if str(f.get("code")) in PLANNER_AUTHORITY_BLOCKER_CODES]
    return found, blockers


# --- 1. The rhythm touch resolves as aerobic maintenance --------------------


def test_allocator_and_morph_agree_on_the_rhythm_touch_system():
    """One role key, one definition. The morph is the established authority."""
    from fightcamp.stage2_payload_late_fight import _late_fight_candidate_roles  # noqa: F401

    morphed = {"role_key": "fight_pace_repeatability_day", "category": "conditioning",
               "preferred_system": "glycolytic"}
    late_camp_role_morph._morph_to_rhythm_touch(morphed, 11)
    assert morphed["role_key"] == "light_fight_pace_touch_day"
    assert morphed["preferred_system"] == "aerobic"

    import inspect
    from fightcamp import stage2_payload_late_fight as lf

    source = inspect.getsource(lf._late_fight_candidate_roles)
    block = source[source.index('role_key="light_fight_pace_touch_day"'):]
    block = block[: block.index("selection_priority")]
    assert 'preferred_system="aerobic"' in block
    assert 'preferred_system="glycolytic"' not in block


def test_true_glycolytic_development_roles_are_unchanged():
    # The rhythm touch is maintenance; real fight-pace development is not.
    from fightcamp.stage2_role_map import _conditioning_role_key

    assert _conditioning_role_key("SPP", "glycolytic", "aerobic_repeatability") == "fight_pace_repeatability_day"
    assert _conditioning_role_key("GPP", "glycolytic", "aerobic_repeatability") == "controlled_repeatability_day"
    assert _conditioning_role_key("TAPER", "glycolytic", "aerobic_repeatability") == "light_fight_pace_touch_day"


# --- 2. Safe omission releases; unsafe or unexplained state does not --------


@pytest.mark.parametrize(
    "diagnostics",
    [
        {"phase_window_rejected": 3, "sport_rejected": 0, "day_safety_rejected": 0},
        {"phase_window_rejected": 0, "sport_rejected": 2, "day_safety_rejected": 0},
        {"phase_window_rejected": 0, "sport_rejected": 0, "day_safety_rejected": 1},
    ],
)
def test_governance_rejecting_every_candidate_is_a_safe_omission(diagnostics):
    found, blockers = _findings(_role(late_assignment_diagnostics=diagnostics))
    assert blockers == []
    assert [f["code"] for f in found] == [LATE_PHYSICAL_ROLE_SAFE_OMISSION_CODE]
    assert found[0]["severity"] == "info"
    # The omission stays visible, carrying the diagnostics that explain it.
    assert found[0]["rejection_summary"] == diagnostics


@pytest.mark.parametrize(
    "diagnostics",
    [
        None,
        {},
        {"phase_window_rejected": 0, "sport_rejected": 0, "day_safety_rejected": 0},
    ],
)
def test_an_unexplained_empty_assignment_still_blocks(diagnostics):
    role = _role()
    if diagnostics is not None:
        role["late_assignment_diagnostics"] = diagnostics
    found, blockers = _findings(role)
    assert [f["code"] for f in blockers] == ["late_physical_role_missing_assignment"]
    assert found[0]["severity"] == "blocker"


def test_safe_omission_code_is_not_a_release_blocker():
    assert LATE_PHYSICAL_ROLE_SAFE_OMISSION_CODE not in PLANNER_AUTHORITY_BLOCKER_CODES
    # The genuine hard blocks are untouched.
    assert PLANNER_AUTHORITY_BLOCKER_CODES == frozenset(
        {
            "selected_exercise_phase_unresolved",
            "selected_exercise_phase_ineligible",
            "selected_exercise_late_window_ineligible",
            "selected_loaded_exercise_forbidden",
            "late_physical_role_missing_assignment",
        }
    )


def test_a_forbidden_loaded_exercise_still_blocks():
    role = _role(
        category="strength",
        role_key="strength_touch_day",
        # No countdown label: this test is about the loaded-work block, not the
        # separate dated-phase resolution check that runs ahead of it.
        scheduled_countdown_label="",
        effective_strength_envelope={"loaded_allowed": False},
        selected_exercise_assignments=[
            {"name": "Trap Bar Deadlift", "slot_group": "strength_slots", "source_phase": "SPP"}
        ],
    )
    _found, blockers = _findings(role)
    assert "selected_loaded_exercise_forbidden" in [f["code"] for f in blockers]


def test_a_populated_role_produces_no_findings():
    role = copy.deepcopy(_role())
    role["selected_exercise_assignments"] = [
        {"name": "Tempo Shadowboxing", "slot_group": "conditioning_slots", "source_phase": "SPP"}
    ]
    found, _blockers = _findings(role)
    # The day is populated, so neither the blocker nor the safe-omission finding
    # applies. (Other authority checks may still comment on this bare fixture.)
    codes = {f["code"] for f in found}
    assert "late_physical_role_missing_assignment" not in codes
    assert LATE_PHYSICAL_ROLE_SAFE_OMISSION_CODE not in codes
