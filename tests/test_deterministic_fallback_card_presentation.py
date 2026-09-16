"""The deterministic fallback publishes coaching structure, not a Why blob.

Production commonly has ``structured_plan = NULL``, so this fallback IS the
athlete card. Two presentation faults came from that:

* every ``support_insert`` role was typed ``recovery``, so a technical footwork
  drill and a joint-prep reset were published to the athlete under a RECOVERY
  tag;
* a role's whole ``display_text`` went into ``Session.objective``, which the
  renderer labels "Why" — so the planner's own session body ("Why: … - Drill:
  dose … Cue: … Quality Stop: …") rendered as one flattened "WHY Why: …"
  paragraph, and a plain instruction rendered as a fake rationale.

The planner already carries the semantics (``support_insert_category`` /
``support_insert_cost_category``) and already writes a fixed session-body
grammar, so both are read rather than guessed.
"""

from __future__ import annotations

from api.structured_plan_deterministic_fallback import _session

PRESSURE_STEP_CUT_DISPLAY_TEXT = (
    "Why: Read the opponent's exit lane, cut it off, and reset the base before punching. "
    "Reactive read with a hard lateral brake; SPP only.\n"
    "- Pressure Step-Cut Reset: 2 sets x 4 clean reactions each direction, full stance reset "
    "between reps. Rest: 75 sec between sets.\n"
    "  Cue: React to a partner exit, coach direction call, or random left/right visual cue. "
    "Cut that lane and fully rebuild the base before the next rep.\n"
    "  Cue Method: Have your partner feed the cue at random timing; reset fully between reps.\n"
    "  Side / Stance: Start in your orthodox stance and work both directions evenly.\n"
    "  Quality Stop: Stop the set when the lane read, braking control, or stance reset loses quality."
)


def _role(**overrides) -> dict:
    role = {
        "category": "support_insert",
        "stress_class": "support",
        "selected_exercise_assignments": [],
    }
    role.update(overrides)
    return role


def test_joint_prep_is_physical_support_not_recovery():
    session = _session(
        _role(
            role_key="joint_prep",
            support_insert_category="mobility",
            support_insert_cost_category="physical",
            athlete_facing_label="Joint Prep",
            display_text=(
                "Neck CARs, shoulder CARs, wrist circles, hip circles, and ankle rocks. "
                "Stay smooth and pain-free."
            ),
        ),
        10,
    )

    assert session is not None
    assert session["title"] == "Joint Prep"
    # "rehab" is the schema's home for mobility work; the web renderer groups
    # rehab/prehab/mobility and renames it Prehab when nothing is injured.
    assert session["session_type"] == "rehab"
    assert session["session_type"] != "recovery"
    # The instruction stays the instruction: no invented drill, dose or Why.
    assert session["objective"].startswith("Neck CARs")
    assert session["blocks"] == []


def test_breathing_reset_stays_recovery_and_readable():
    session = _session(
        _role(
            role_key="breathing_reset",
            support_insert_category="recovery",
            support_insert_cost_category="low_cost_recovery",
            athlete_facing_label="Breathing Reset",
            display_text=(
                "Nasal breathing if comfortable. Use a 4-6 second inhale and 6-8 second "
                "exhale. Finish calmer than you started."
            ),
        ),
        9,
    )

    assert session is not None
    assert session["session_type"] == "recovery"
    assert session["objective"].startswith("Nasal breathing if comfortable.")


def test_pressure_step_cut_reset_becomes_a_coaching_card():
    session = _session(
        _role(
            role_key="footwork_walkthrough",
            support_insert_category="technical_footwork",
            support_insert_cost_category="physical",
            athlete_facing_label="Pressure Step-Cut Reset",
            display_text=PRESSURE_STEP_CUT_DISPLAY_TEXT,
        ),
        9,
    )

    assert session is not None
    assert session["session_type"] == "skill"

    # The real Why is isolated, with its source label stripped — no "Why: Why:".
    assert session["objective"].startswith("Read the opponent's exit lane")
    assert "Why:" not in session["objective"]
    # …and the objective is the rationale ONLY: no flattened drill/cue paragraph.
    assert "Cue Method" not in session["objective"]
    assert "2 sets x 4" not in session["objective"]

    block = session["blocks"][0]
    assert block["display_name"] == "Pressure Step-Cut Reset"
    assert block["block_type"] == "skill"
    cues = block["coaching_cues"]
    # Prescription and its rest stay visible, verbatim.
    assert cues[0].startswith("2 sets x 4 clean reactions each direction")
    assert "Rest: 75 sec between sets." in cues[0]
    # Planner labels keep their wording so the coaching still reads as coaching.
    assert any(cue.startswith("Cue: React to a partner exit") for cue in cues)
    assert any(cue.startswith("Cue Method:") for cue in cues)
    assert any(cue.startswith("Side / Stance:") for cue in cues)
    # Quality Stop is a stop rule, not a cue and not a progression.
    assert block["stop_rules"] == [
        "Stop the set when the lane read, braking control, or stance reset loses quality."
    ]
    assert not any("Quality Stop" in cue for cue in cues)
    assert block["progression_rule"] is None


def test_technical_shadow_rhythm_is_skill_not_recovery():
    session = _session(
        _role(
            role_key="technical_shadow_rhythm",
            support_insert_category="technical",
            support_insert_cost_category="physical",
            athlete_facing_label="Technical Shadow Rhythm",
            display_text=(
                "Light shadow rhythm only. Smooth entries, exits, and reset cues. "
                "No bag, bands, bursts, or conditioning intent."
            ),
        ),
        3,
    )

    assert session is not None
    assert session["session_type"] == "skill"


def test_conditioning_maintenance_insert_is_conditioning():
    session = _session(
        _role(
            role_key="aerobic_shadow_flow",
            support_insert_category="conditioning_maintenance",
            support_insert_cost_category="low_cost_aerobic",
            athlete_facing_label="Aerobic Movement Flow",
            display_text="3-5 x 2 min easy solo movement rounds, 60 sec rest. RPE 3-4.",
        ),
        12,
    )

    assert session is not None
    assert session["session_type"] == "conditioning"


def test_tactical_and_mental_inserts_are_not_typed_recovery():
    tactical = _session(
        _role(
            role_key="tactical_cue_card",
            support_insert_category="tactical",
            support_insert_cost_category="zero_cost",
            athlete_facing_label="Tactical Cue Card",
            display_text="Write one fight cue only: entry, exit, counter, foot position.",
        ),
        1,
    )
    mental = _session(
        _role(
            role_key="neural_visualization",
            support_insert_category="mental",
            support_insert_cost_category="zero_cost",
            athlete_facing_label="Neural Visualization",
            display_text=(
                "Why: Rehearse the opening exchange so the first minute is familiar.\n"
                "- Neural Visualization: 5-8 minutes, mental rehearsal only. No physical load.\n"
                "  Cue: Keep the picture first-person and calm."
            ),
        ),
        4,
    )

    assert tactical is not None and mental is not None
    assert tactical["session_type"] == "skill"
    assert mental["session_type"] == "skill"
    # Zero load is decided by the shared identity rule on the web, never by the
    # session type, so typing these as skill changes nothing about counting.
    assert mental["objective"].startswith("Rehearse the opening exchange")
    assert mental["blocks"][0]["display_name"] == "Neural Visualization"


def test_a_role_with_selected_exercises_is_unchanged():
    session = _session(
        {
            "role_key": "neural_primer_day",
            "category": "strength",
            "athlete_facing_label": "Neural speed touch",
            "display_text": "ignored when the role has real blocks",
            "selected_exercise_assignments": [
                {"name": "Trap bar deadlift", "base_prescription": "2-3 sets x 3 reps"}
            ],
        },
        12,
    )

    assert session is not None
    assert session["session_type"] == "strength_power"
    assert session["objective"] == session["title"]
    assert [block["display_name"] for block in session["blocks"]] == ["Trap bar deadlift"]
