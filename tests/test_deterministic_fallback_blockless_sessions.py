"""A scheduled role with no selected exercise is still scheduled work.

Support inserts (joint prep, breathing reset, footwork walkthrough,
visualisation) carry their whole athlete-facing prescription as one banked
sentence and never populate ``selected_exercise_assignments``. The fallback used
to render a session only when a role had executable blocks, so those days were
handed to the calendar spine empty and the athlete card called them rest —
exactly the production failure this fixes.
"""

from __future__ import annotations

from api.structured_plan_deterministic_fallback import _session


def _support_role(**overrides) -> dict:
    role = {
        "role_key": "joint_prep",
        "category": "support_insert",
        "athlete_facing_label": "Joint Prep",
        "display_text": (
            "Neck CARs, shoulder CARs, wrist circles, hip circles, and ankle rocks. "
            "Stay smooth and pain-free."
        ),
        "stress_class": "support",
        "selected_exercise_assignments": [],
    }
    role.update(overrides)
    return role


def test_blockless_support_role_still_renders_a_session():
    session = _session(_support_role(), 10)

    assert session is not None
    assert session["title"] == "Joint Prep"
    assert session["objective"].startswith("Neck CARs")
    # The source prescribed no exercise, so none is invented.
    assert session["blocks"] == []


def test_blockless_visualisation_role_survives():
    session = _session(
        _support_role(
            role_key="mental_visualization",
            category="mindset",
            athlete_facing_label="Neural Visualisation",
            display_text=(
                "Quiet visualisation only. Rehearse first exchange, best entry, "
                "exit/reset, and final-round composure."
            ),
        ),
        8,
    )

    assert session is not None
    assert session["objective"].startswith("Quiet visualisation only.")
    assert session["blocks"] == []


def test_a_role_with_nothing_athlete_facing_is_still_dropped():
    assert _session(_support_role(display_text="", selected_exercise_assignments=[]), 6) is None


def test_a_role_with_exercises_keeps_its_label_objective():
    session = _session(
        _support_role(
            role_key="strength_primary",
            category="strength",
            athlete_facing_label="Neural speed touch",
            display_text="ignored when the role has real blocks",
            selected_exercise_assignments=[
                {"name": "Trap bar deadlift", "base_prescription": "2-3 sets x 3 reps"}
            ],
        ),
        12,
    )

    assert session is not None
    assert session["objective"] == session["title"]
    assert [block["display_name"] for block in session["blocks"]] == ["Trap bar deadlift"]
