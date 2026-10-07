"""Names follow the planner's identity, not the converter's wording.

A block the server ties to a Stage 1 exercise by ``exercise_key`` takes that
exercise's canonical name; a session whose keyed blocks all belong to one role
takes the role's athlete-facing label. Nothing is renamed on a fuzzy match.
"""

from __future__ import annotations

import copy

from api.exercise_identity import reconcile_canonical_names
from test_structured_salvage_planner_coverage import (
    _brief,
    _converter_card,
    _long_weekday,
    _outcome,
    _sessions_by_dday,
)


def _short(d_day: int) -> str:
    return _long_weekday(d_day)[:3]


def _d23(plan: dict) -> dict:
    return next(
        day for week in plan["weeks"] for day in week["days"] if day["countdown_label"] == "D-23"
    )


def _keyed_card() -> dict:
    card = _converter_card(weekday=_short)
    session = _d23(card)["sessions"][0]
    session["title"] = "Lower body + press"
    first, second = session["blocks"]
    first.update(display_name="Weighted push-ups", exercise_key="push-up-weighted")
    second.update(display_name="Cossack squats 2x8", exercise_key="cossack-squat-dynamic")
    return card


def test_keyed_blocks_take_the_planner_name_and_session_the_role_label():
    renamed = reconcile_canonical_names(_keyed_card(), _brief())

    session = _d23(renamed)["sessions"][0]
    assert session["title"] == "Strength"
    assert [b["display_name"] for b in session["blocks"]] == [
        "Push-Up (Weighted)",
        "Cossack Squat (Dynamic)",
    ]


def test_input_is_not_mutated_and_a_canonical_card_is_returned_unchanged():
    card = _keyed_card()
    before = copy.deepcopy(card)
    renamed = reconcile_canonical_names(card, _brief())

    assert card == before
    assert reconcile_canonical_names(renamed, _brief()) is renamed


def test_a_labelled_name_that_already_contains_the_exercise_is_kept():
    card = _keyed_card()
    _d23(card)["sessions"][0]["blocks"][0]["display_name"] = "Press focus - Push-Up (Weighted)"

    session = _d23(reconcile_canonical_names(card, _brief()))["sessions"][0]

    assert session["blocks"][0]["display_name"] == "Press focus - Push-Up (Weighted)"


def test_unkeyed_blocks_and_foreign_keys_keep_their_names():
    card = _keyed_card()
    blocks = _d23(card)["sessions"][0]["blocks"]
    blocks[0].pop("exercise_key")
    blocks[1]["exercise_key"] = "tire-flip"  # D-20's exercise, not D-23's
    blocks[1]["display_name"] = "Something else"

    session = _d23(reconcile_canonical_names(card, _brief()))["sessions"][0]

    assert [b["display_name"] for b in session["blocks"]] == ["Weighted push-ups", "Something else"]
    # No keyed block ties the session to a role, so its title stays.
    assert session["title"] == "Lower body + press"


def test_a_session_spanning_two_roles_keeps_its_title():
    card = _converter_card(weekday=_short)
    d16 = next(
        day for week in card["weeks"] for day in week["days"] if day["countdown_label"] == "D-16"
    )
    strength, conditioning = d16["sessions"]
    merged = copy.deepcopy(strength)
    merged["title"] = "Power and pace"
    merged["blocks"] = [
        {**strength["blocks"][0], "exercise_key": "jump-lunge-alternating"},
        {**conditioning["blocks"][0], "exercise_key": "double-end-bag-circuit"},
    ]
    d16["sessions"] = [merged]

    session = next(
        day for week in reconcile_canonical_names(card, _brief())["weeks"]
        for day in week["days"] if day["countdown_label"] == "D-16"
    )["sessions"][0]

    assert session["title"] == "Power and pace"


def test_server_built_sessions_and_blocks_are_untouched():
    card = _keyed_card()
    session = _d23(card)["sessions"][0]
    session["session_id"] = "deterministic-23-primary_strength_day-2"

    assert reconcile_canonical_names(card, _brief()) is card


def test_pipeline_ships_canonical_names_after_faithfulness():
    # The converter retitled the session and reworded both exercises. Faithfulness
    # judges that wording against the text; the shipped card carries the
    # planner's names because the server stamped the planner's keys.
    card = _converter_card(weekday=_short)
    session = _d23(card)["sessions"][0]
    session["title"] = "Lower body + press"
    session["blocks"][0]["display_name"] = "Weighted push-ups"
    session["blocks"][1]["display_name"] = "Cossack squats"

    outcome = _outcome(card)

    assert outcome.status == "valid", outcome.errors
    [shipped] = _sessions_by_dday(outcome.structured_plan)[23]
    assert shipped["title"] == "Strength"
    assert [b["display_name"] for b in shipped["blocks"]] == [
        "Push-Up (Weighted)",
        "Cossack Squat (Dynamic)",
    ]
    assert [b["exercise_key"] for b in shipped["blocks"]] == [
        "push-up-weighted",
        "cossack-squat-dynamic",
    ]
