"""Authored coaching wins; duplicate exercises never share session context."""
from copy import deepcopy
import json
from pathlib import Path
import subprocess

import pytest

from api.structured_plan_coaching import recover_selected_coaching
from api.structured_plan_deterministic_fallback import _session
from api.structured_plan_faithfulness import _explicit_prescription_violations
from fightcamp.exercise_coaching import exercise_coaching
from fightcamp.coaching_copy import concise_coaching
from fightcamp.render_authority import authoritative_render_for_role
from fightcamp.session_composition import assignment_from_slot


ROOT = Path(__file__).resolve().parents[1]
FIELDS = ("coaching_cues", "regression_options", "progression_rule", "stop_rules")


def authored(prefix):
    return {
        "coaching_cues": [f"{prefix}: drive from the floor.", f"{prefix}: keep the ribs stacked.",
                          f"{prefix}: finish with a balanced stance."],
        "regression_options": [f"{prefix}: use the lighter training bar while keeping the same dose."],
        "progression_rule": f"{prefix}: once balanced, refine the drive into the overhead finish at the same dose.",
        "stop_rules": [f"{prefix}: end the set if the overhead finish loses control."],
    }


def execution_fields(prefix):
    """The first authored execution cue owns the compact card."""
    fields = authored(prefix)
    fields["coaching_cues"].append(fields.pop("progression_rule"))
    return concise_coaching(fields)


def role(index, support=False):
    assignment = {"name": "Barbell Thruster", "exercise_key": "barbell-thruster",
                  "slot_group": "strength_slots", "slot_id": f"thruster-{index}",
                  "source_phase": "SPP", "effective_prescription": f"{index} sets x 2 reps; rest 120 sec",
                  "support_only": support, **authored(f"Session {index}")}
    return {"role_key": "neural_plus_strength_day", "session_index": index,
            "athlete_facing_label": f"Strength appointment {index}", "scheduled_countdown_label": "D-32",
            "category": "strength", "selected_exercise_assignments": [assignment]}


def duplicate_card():
    roles = [role(1), role(2, support=True)]
    sessions = [{"session_id": f"deterministic-32-neural_plus_strength_day-{i}",
                 "title": f"Strength appointment {i}", "session_type": "strength_power",
                 "blocks": [{"block_id": f"thruster-session-{i}", "block_type": "strength",
                             "display_name": "Barbell Thruster", "exercise_key": "barbell-thruster",
                             "sets": i, "reps": 2, "rest": {"value": 120, "unit": "seconds"}}]}
                for i in (1, 2)]
    brief = {"athlete_snapshot": {}, "weekly_role_map": {"weeks": [{"phase": "SPP", "session_roles": roles}]}}
    card = {"schema_version": "1.0", "plan_metadata": {"title": "Duplicate exercise context"},
            "weeks": [{"week_id": "week-1", "week_index": 1, "phase_label": "SPP",
                       "days": [{"date": "2026-11-03", "countdown_label": "D-32", "sessions": sessions}]}]}
    return brief, card


def sessions(card):
    return card["weeks"][0]["days"][0]["sessions"]


def test_profiles_fill_gaps_without_replacing_structured_bank_instructions():
    assignment = role(1)["selected_exercise_assignments"][0]
    assert exercise_coaching(assignment, {}, d_day=32) == execution_fields("Session 1")
    rendered = authoritative_render_for_role(role(1), d_day=32)
    for key, value in execution_fields("Session 1").items():
        for text in [value] if isinstance(value, str) else value:
            assert any(text in line for line in rendered["body_lines"]), key


def test_authored_unknown_movement_progress_is_not_added_during_taper():
    assignment = {"name": "Uncatalogued coach movement", "slot_group": "strength_slots",
                  **authored("Coach")}
    assert exercise_coaching(assignment, {}, phase="GPP", d_day=32) == execution_fields("Coach")
    maintenance = exercise_coaching(assignment, {}, phase="TAPER", d_day=6)
    assert not maintenance.get("progression_rule")
    assert maintenance == execution_fields("Coach")


def test_bank_keeps_one_cue_and_its_labelled_adjustments():
    fields = authored("Bank")
    notes = "\n".join([
        *fields["coaching_cues"], f"Easier: {fields['regression_options'][0]}",
        f"Progress: {fields['progression_rule']}", f"Stop: {fields['stop_rules'][0]}",
    ])
    actual = exercise_coaching({"name": "Barbell Thruster", "slot_group": "strength_slots",
                                "coaching_notes": notes}, {}, d_day=32)
    assert actual == execution_fields("Bank")


@pytest.mark.parametrize("metadata", [False, True])
def test_selection_keeps_explicit_authored_fields(metadata):
    bank = {"name": "Barbell Thruster", "prescription": "4 sets x 2 reps", **authored("Bank")}
    if metadata:
        bank = {"name": bank["name"], "selection_metadata": bank}
    selected = assignment_from_slot("SPP", "strength_slots", {"selected": bank})
    assert all(selected[key] == value for key, value in authored("Bank").items())


@pytest.mark.parametrize("identity", ["deterministic", "converted_title", "name_only"])
@pytest.mark.parametrize("reverse", [False, True])
def test_duplicate_recovery_keeps_each_sessions_coaching_and_dose(identity, reverse):
    brief, card = duplicate_card()
    if identity == "converted_title":
        for i, session in enumerate(sessions(card)):
            session["session_id"] = f"converted-{i}"
    if identity == "name_only":
        for session in sessions(card):
            session["blocks"][0].pop("exercise_key")
    if reverse:
        sessions(card).reverse()
        brief["weekly_role_map"]["weeks"][0]["session_roles"].reverse()
    before = deepcopy(card)
    recovered = recover_selected_coaching(card, brief)
    assert card == before
    for session in sessions(recovered):
        i = int(session["title"][-1])
        block = session["blocks"][0]
        expected = execution_fields(f"Session {i}")
        assert all(block.get(key) == value for key, value in expected.items())
        assert not block.get("progression_rule")  # Neither has an authorised future increase.
        assert block["sets"] == i and block["reps"] == 2 and block["rest"]["value"] == 120
        assert not any("Session " + str(3-i) in str(block.get(key)) for key in FIELDS)


def test_ambiguous_duplicate_sessions_are_left_unchanged():
    brief, card = duplicate_card()
    for i, session in enumerate(sessions(card)):
        session.update(session_id=f"legacy-{i}", title="Strength")
        session["blocks"][0]["coaching_cues"] = [f"Existing coach instruction {i}"]
    assert recover_selected_coaching(card, brief) == card


def test_existing_coach_fields_always_win_over_bank_and_profiles():
    brief, card = duplicate_card()
    for i, session in enumerate(sessions(card)):
        session["blocks"][0].update(authored(f"Existing coach {i}"))
    recovered = recover_selected_coaching(card, brief)
    for i, session in enumerate(sessions(recovered)):
        block = session["blocks"][0]
        assert all(block.get(k) == v for k, v in execution_fields(f"Existing coach {i}").items())
        assert not block.get("progression_rule")


def test_source_fallback_reads_duplicate_exercises_from_their_own_session():
    first, second = role(1), role(2)
    raw = []
    for r in (first, second):
        raw.append(f"### D-32 (Tuesday) — {r['athlete_facing_label']}")
        raw.extend(authoritative_render_for_role(r, d_day=32)["body_lines"])
    converted = []
    for r in (second, first):  # No dependence on call order.
        session = _session(r, 32, raw)
        # Model conversion retains a specific source title, not a generic role title.
        session["title"] = r["athlete_facing_label"]
        converted.append(session)
        block = session["blocks"][0]
        i = r["session_index"]
        assert block["sets"] == i
        assert [cue.removeprefix("Cue: ") for cue in block["coaching_cues"]] == execution_fields(f"Session {i}")["coaching_cues"]
        for field in FIELDS[1:]:
            assert block.get(field) == execution_fields(f"Session {i}").get(field)
    card = {"weeks": [{"days": [{"countdown_label": "D-32", "sessions": converted}]}]}
    assert _explicit_prescription_violations(card, "\n".join(raw)) == []
    converted[0]["blocks"][0].pop("regression_options")
    assert any("COACHING_DROPPED" in e for e in _explicit_prescription_violations(card, "\n".join(raw)))


@pytest.mark.skipif(not (ROOT / "web/node_modules/tsx").is_dir(), reason="Requires web npm ci")
@pytest.mark.parametrize("existing", [False, True])
def test_duplicate_coaching_context_reaches_each_expanded_react_row(existing):
    brief, card = duplicate_card()
    if existing:
        for i, session in enumerate(sessions(card)):
            session["blocks"][0].update(authored(f"Coach {i}"))
    recovered = recover_selected_coaching(card, brief)
    expected = []
    for session in sessions(recovered):
        block = session["blocks"][0]
        other = next(s["blocks"][0] for s in sessions(recovered) if s is not session)
        expected.append({"id": block["block_id"], "fields": {k: block[k] for k in FIELDS if k in block},
                         "forbidden": other["coaching_cues"]})
    result = subprocess.run(
        ["node", "--import", "tsx", "--import", "./test/register-css-stub.mjs",
         "test/assert-exercise-coaching-release.tsx"], cwd=ROOT / "web",
        input=json.dumps({"plan": recovered, "expected": expected}), text=True, capture_output=True,
    )
    assert result.returncode == 0, result.stderr
