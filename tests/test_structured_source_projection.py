"""Regression coverage for source fields lost by the second model pass."""
from copy import deepcopy
import json

import pytest

from api.structured_plan_coaching import recover_selected_coaching
from api.structured_plan_faithfulness import project_source_adjustments
from api.structured_plan_generation import build_structured_plan_outcome, build_structured_plan_prompt
from test_structured_plan_models import _valid_plan


def card(*, countdown="D-15", title="Technical work", weekday="Tue", week_index=1):
    return {"weeks": [{"week_index": week_index, "days": [{
        "countdown_label": countdown, "weekday": weekday, "sessions": [{
            "title": title, "blocks": [{"display_name": "Parry-Cross-Exit", "block_type": "skill"}],
        }],
    }]}]}


def block(plan):
    return plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]


DETAILS = """- Parry-Cross-Exit: 3 rounds x 5 sec; rest 120 sec; RPE 6.
  How: Parry once, cross, then step out of range.
  Cue: Return your guard before resetting.
  Easier: Slow the sequence down.
  Stop: Stop if balance is lost.
"""


def test_technical_source_fields_survive_conversion_and_saved_card_reads():
    source = "## Week 1 (D-19 to D-13)\nD-15 (Tuesday) — Technical work\n" + DETAILS
    candidate = _valid_plan()
    day = candidate["weeks"][0]["days"][0]
    day["sessions"] = card()["weeks"][0]["days"][0]["sessions"]
    outcome = build_structured_plan_outcome(candidate, raw_markdown=source)
    assert outcome.structured_plan is not None, outcome.errors
    published = block(outcome.structured_plan)
    assert published["rest"] == {"value": 120, "unit": "seconds"}
    assert published["rounds"] == 3
    assert published["work"] == {"value": 5, "unit": "seconds"}
    assert published["effort"]["value"] == 6
    assert published["execution_instructions"] == "Parry once, cross, then step out of range."
    assert published["stop_rules"] == ["Stop if balance is lost."]
    saved = card()
    before = deepcopy(saved)
    restored = recover_selected_coaching(saved, {}, source_text=source)
    assert block(restored)["rest"] == published["rest"]
    assert saved == before
    assert recover_selected_coaching(restored, {}, source_text=source) == restored


@pytest.mark.parametrize("header", ["D-15 (Tuesday) — Technical work", "Tuesday — Technical work"])
def test_same_day_sessions_do_not_borrow_rest_or_instructions(header):
    source = header + "\n" + DETAILS + "\n" + header.replace("Technical work", "Other work") + "\n" + DETAILS.replace("120 sec", "30 sec").replace("Parry once", "Parry twice")
    plan = card(countdown="" if header.startswith("Tuesday") else "D-15")
    projected = project_source_adjustments(plan, source)
    assert block(projected)["rest"]["value"] == 120
    assert "Parry once" in block(projected)["execution_instructions"]


def test_renamed_open_session_uses_only_an_unambiguous_exercise_on_that_weekday():
    source = "Tuesday — Strength with speed emphasis\n" + DETAILS
    plan = card(countdown="", title="Strength")
    assert block(project_source_adjustments(plan, source))["rest"]["value"] == 120
    ambiguous = source + "\nTuesday — Second session\n" + DETAILS.replace("120 sec", "30 sec")
    assert not block(project_source_adjustments(card(countdown="", title="Strength"), ambiguous)).get("rest")


def test_repeated_open_weekdays_keep_week_specific_rest():
    source = "## Week 1\nTuesday — Technical work\n" + DETAILS + "## Week 2\nTuesday — Technical work\n" + DETAILS.replace("120 sec", "180 sec")
    projected = project_source_adjustments(card(countdown="", week_index=2), source)
    assert block(projected)["rest"]["value"] == 180


def test_duplicate_exercise_inside_one_session_does_not_borrow_the_first_dose():
    source = "D-15 (Tuesday) — Technical work\n" + DETAILS + DETAILS.replace("120 sec", "30 sec")
    assert not block(project_source_adjustments(card(), source)).get("rest")


def test_projection_never_overwrites_athlete_prescriptions_or_hides_changed_dose():
    source = "D-15 (Tuesday) — Technical work\n" + DETAILS
    candidate = card()
    block(candidate).update(rest={"value": 15, "unit": "seconds"})
    assert block(project_source_adjustments(candidate, source))["rest"]["value"] == 15
    edited = card()
    block(edited)["athlete_change"] = {"kind": "swap"}
    assert project_source_adjustments(deepcopy(edited), source) == edited
    assert recover_selected_coaching(edited, {"custom_plan": True}, source_text=source) == edited


def test_absent_exercise_progress_never_rejects_a_technical_card():
    candidate = _valid_plan()
    candidate["weeks"][0]["days"][0]["sessions"] = card()["weeks"][0]["days"][0]["sessions"]
    source = "## Week 1 (D-19 to D-13)\nD-15 (Tuesday) — Technical work\n" + DETAILS + "  Progress: Keep the same pace and clean exits.\n"
    outcome = build_structured_plan_outcome(candidate, raw_markdown=source)
    assert outcome.structured_plan is not None, outcome.errors


def test_open_conversion_has_one_programme_source_and_a_small_calendar_contract():
    source = "Tuesday — Technical work\n" + DETAILS
    spec = {"plan_type": "open_ongoing_system", "weekly_template": {"training_days": ["Tue"]},
            "render_rules": ["CONFLICTING_INTERNAL_RULE" * 500],
            "weekly_session_plan": {"weeks": [{"sessions": [{"weekday": "Tue", "exercises": ["REPEATED_BANK_PROSE" * 1000]}]}] * 4}}
    prompt = build_structured_plan_prompt(plan_markdown=source, planning_brief={"open_plan_spec": spec})
    assert source in prompt
    assert "CONFLICTING_INTERNAL_RULE" not in prompt
    assert "REPEATED_BANK_PROSE" not in prompt
    contract = prompt.split("AUTHORITATIVE open_plan_spec:\n")[1].split("\n\n")[0]
    assert json.loads(contract) == {"plan_type": "open_ongoing_system", "training_weekdays": ["Tue"], "week_count": 4}
    assert len(prompt) < 13_000


def test_large_soft_context_remains_valid_json_and_does_not_cut_the_programme():
    source = "D-15 (Tuesday) — Technical work\n" + DETAILS
    prompt = build_structured_plan_prompt(plan_markdown=source, planning_brief={
        "athlete_snapshot": {"notes": "x" * 20_000}, "main_limiter": "conditioning",
    })
    context = prompt.split("verbatim):\n")[1].split("\n\n")[0]
    assert json.loads(context) == {"main_limiter": "conditioning"}
    assert source in prompt
