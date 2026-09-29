"""The backend's answers to shared/cases/*.json.

The web app re-implements a few backend rules for rendering (match-term
normalization, the open-plan week, the day's primary session, focus caps).
Each rule has one case file with the backend's expected answers; this test
checks the backend still gives them, and web/lib/shared-cases.test.ts checks
the web app gives the same ones. Changing either side's rule means updating the
case file, which the other side's test then holds it to.
"""

import json
import math
from datetime import datetime
from pathlib import Path

import pytest

from api.performance_focus import get_performance_focus_cap, validate_performance_focus_selections
from api.rehab_labels import normalize_match_term
from api.services.open_plan_timeline import project_open_structured_plan
from api.services.today_service import _select_structured_primary_session
from tests.test_open_plan_recurring_resolution import _open_plan_brief, _open_structured_plan

CASES = Path(__file__).resolve().parents[1] / "shared" / "cases"


def _cases(name: str):
    return json.loads((CASES / name).read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", _cases("rehab-match-terms.json"), ids=lambda case: repr(case["input"]))
def test_rehab_match_terms(case):
    assert normalize_match_term(case["input"]) == case["expected"]


@pytest.mark.parametrize(
    "case",
    _cases("open-plan-weeks.json"),
    ids=lambda case: f"{case['created_at'][:10]}->{case['current_training_day']}",
)
def test_open_plan_weeks(case):
    plan_row = {
        "id": "plan",
        "created_at": case["created_at"],
        "fight_date": None,
        "planning_brief": _open_plan_brief(),
    }

    _, context = project_open_structured_plan(
        plan_row, _open_structured_plan(), current_training_day=case["current_training_day"]
    )

    assert context["anchor_date"] == case["expected_anchor_date"]
    assert context["current_week_number"] == case["expected_week_number"]


@pytest.mark.parametrize("case", _cases("primary-session.json"))
def test_primary_session(case):
    sessions = case["sessions"]

    assert _select_structured_primary_session(sessions) is sessions[case["expected_index"]]


@pytest.mark.parametrize(
    "case",
    _cases("performance-focus-caps.json")["caps"],
    ids=lambda case: f"{case['fight_date']}@{case['now']}/{case['time_zone']}",
)
def test_performance_focus_caps(case):
    cap = get_performance_focus_cap(
        case["fight_date"], now=datetime.fromisoformat(case["now"]), time_zone=case["time_zone"]
    )

    if case["expected"] is None:
        assert cap is None
        return
    assert {
        "open_plan": math.isinf(cap.days_until_fight),
        "days_until_fight": None if math.isinf(cap.days_until_fight) else cap.days_until_fight,
        "weeks_out": None if math.isinf(cap.weeks_out) else cap.weeks_out,
        "max_selections": cap.max_selections,
        "window_label": cap.window_label,
    } == case["expected"]


@pytest.mark.parametrize("case", _cases("performance-focus-caps.json")["validations"])
def test_performance_focus_validation_messages(case):
    result = validate_performance_focus_selections(
        case["fight_date"],
        key_goals=["g"] * case["key_goals"],
        weak_areas=["w"] * case["weak_areas"],
        time_zone=case["time_zone"],
        now=datetime.fromisoformat(case["now"]),
    )

    assert result.excess_selections == case["expected_excess"]
    assert result.error_message == case["expected_message"]
