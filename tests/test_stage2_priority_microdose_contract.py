"""Stage 2 must be told to render a priority microdose, and checked that it did.

The live plan carried the microdose in the handoff and omitted it from the
output. The audit found why: `priority_microdose` appeared exactly once in the
whole codebase outside goal preservation - in the deterministic structured
fallback - so the prompt never required rendering it and no validator invariant
noticed. The field rode along inside the serialized role map as an unexplained
key. This is the contract that was missing, not model disobedience.
"""

from __future__ import annotations

import pytest

from fightcamp.stage2_validator import _priority_microdose_render_errors


def _brief(*, goal="power", name="Med-Ball Rotational Throw",
           prescription="2 x 3/side @ RPE 7", with_microdose=True):
    role = {
        "category": "technical",
        "role_key": "light_combat_day",
        "scheduled_day_hint": "Saturday",
        "session_index": 1,
    }
    if with_microdose:
        role["priority_microdose"] = {
            "goal": goal,
            "name": name,
            "prescription": prescription,
            "sets": 2,
            "intents": ["ballistic_power"],
        }
    return {
        "weekly_role_map": {
            "weeks": [
                {
                    "week_index": 2,
                    "phase": "SPP",
                    "calendar_days": [{"weekday": "saturday", "d_day": 26}],
                    "session_roles": [role],
                }
            ]
        }
    }


# The exact D-26 section the live plan persisted.
LIVE_BAD = """## D-26 (Saturday) - Light Combat / Technical
- Your declared light-combat / technical session. Keep it as scheduled.
  Note: No programmed S&C. Use this day for technical polish.
"""

RENDERED = """## D-26 (Saturday) - Light Combat / Technical
- Your declared light-combat / technical session. Keep it as scheduled.
- Power microdose - Med-Ball Rotational Throw - 2 x 3/side @ RPE 7
"""


def _codes(brief, text):
    return [error["code"] for error in _priority_microdose_render_errors(brief, text)]


# ---------------------------------------------------------------------------
# The prompt contract
# ---------------------------------------------------------------------------


def test_the_stage2_prompt_requires_rendering_a_priority_microdose():
    # Located by content rather than by constant name so the assertion survives
    # the rule being moved between prompt blocks.
    import fightcamp.stage2_payload as payload

    source = open(payload.__file__).read()
    assert "priority_microdose" in source
    assert "RULE 3B" in source


def test_the_prompt_forbids_the_contradictory_wording():
    import fightcamp.stage2_payload as payload

    source = open(payload.__file__).read()
    rule = source.split("RULE 3B")[1].split("RULE 4")[0]
    assert "No programmed S&C" in rule
    assert "exactly once" in rule


# ---------------------------------------------------------------------------
# The validator invariant
# ---------------------------------------------------------------------------


def test_the_live_omission_is_now_a_blocking_finding():
    errors = _priority_microdose_render_errors(_brief(), LIVE_BAD)
    assert [error["code"] for error in errors] == ["missing_priority_microdose"]
    assert errors[0]["severity"] == "blocker"
    assert errors[0]["scheduled_d_day"] == 26
    assert errors[0]["exercise"] == "Med-Ball Rotational Throw"


def test_a_correctly_rendered_microdose_is_clean():
    assert _codes(_brief(), RENDERED) == []


def test_a_duplicate_microdose_is_a_finding():
    duplicated = RENDERED + "- Power microdose - Med-Ball Rotational Throw - 2 x 3/side @ RPE 7\n"
    assert "duplicate_priority_microdose" in _codes(_brief(), duplicated)


def test_a_microdose_rendered_without_its_dose_is_a_finding():
    no_dose = "## D-26 (Saturday)\n- Power microdose - Med-Ball Rotational Throw\n"
    assert "missing_priority_microdose" in _codes(_brief(), no_dose)


def test_rendered_but_contradicted_is_its_own_finding():
    contradicted = RENDERED + "  Note: No programmed S&C. Use this day for technical polish.\n"
    assert _codes(_brief(), contradicted) == ["priority_microdose_contradiction"]


@pytest.mark.parametrize(
    "phrase",
    ["No programmed S&C", "no extra S&C", "technical polish", "no S&C"],
)
def test_each_contradiction_phrase_is_caught(phrase):
    text = RENDERED + f"  Note: {phrase} today.\n"
    assert "priority_microdose_contradiction" in _codes(_brief(), text)


def test_a_non_physical_microdose_is_not_contradicted_by_a_no_sc_line():
    """Footwork is trainable at low cost; a technical-only day does not lie
    about carrying it."""
    contradicted = RENDERED + "  Note: No programmed S&C. Use this day for technical polish.\n"
    assert _codes(_brief(goal="footwork"), contradicted) == []


def test_a_missing_host_day_is_reported():
    assert _codes(_brief(), "## D-20 (Monday)\n- Something else\n") == [
        "missing_priority_microdose"
    ]


def test_a_brief_without_a_microdose_produces_no_findings():
    """No change whatsoever when the planner attached nothing."""
    assert _codes(_brief(with_microdose=False), LIVE_BAD) == []


def test_the_check_runs_inside_validate_stage2_output():
    import inspect

    from fightcamp.stage2_validator import validate_stage2_output

    assert "_priority_microdose_render_errors" in inspect.getsource(validate_stage2_output)
