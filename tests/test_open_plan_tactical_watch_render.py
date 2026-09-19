"""The open plan's weekly Tactical Watch must reach the athlete's card.

A dated camp projects its Tactical Watch through a governed role on a countdown
day. An open plan has neither a countdown nor a weekly_role_map, so that
pathway matched nothing and the watch reached the athlete only if the finalizer
chose to write it. These tests pin the deterministic replacement.
"""
from __future__ import annotations

from copy import deepcopy

import pytest

from api.structured_plan_generation import _open_plan_contract_errors
from api.structured_plan_locked_merge import (
    merge_open_plan_tactical_watch,
    merge_planner_owned_structured_content,
)
from api.structured_plan_models import safe_parse_structured_plan
from fightcamp.stage2_payload_open_ongoing import build_open_ongoing_payload

TRAINING_DAYS = ["Mon", "Wed", "Fri"]


def _spec(**overrides):
    athlete = {
        "sport": "boxing",
        "fighting_style": "counter striker",
        "training_days": list(TRAINING_DAYS),
        **overrides,
    }
    return build_open_ongoing_payload(athlete_model=athlete)["open_plan_spec"]


def _brief(**overrides):
    return {"open_plan_spec": _spec(**overrides)}


def _day(weekday: str, sessions=None):
    return {
        "weekday": weekday,
        "countdown_label": "",
        "sessions": sessions if sessions is not None else [],
    }


def _plan(week_count: int = 1):
    return {
        "weeks": [
            {
                "week_index": index,
                "days": [
                    _day(
                        "Mon",
                        [{"session_id": "s1", "session_type": "strength", "title": "Strength", "blocks": []}],
                    ),
                    _day("Wed"),
                    _day("Fri"),
                ],
            }
            for index in range(1, week_count + 1)
        ]
    }


def _watch_sessions(plan):
    return [
        session
        for week in plan["weeks"]
        for day in week["days"]
        for session in day["sessions"]
        if session.get("title") == "Tactical Focus"
    ]


def test_open_plan_card_gains_the_tactical_watch_session():
    result = merge_planner_owned_structured_content(_plan(), _brief())

    sessions = _watch_sessions(result.plan)
    assert len(sessions) == 1
    session = sessions[0]
    # Zero physical load: a review session, never a training block.
    assert session["session_type"] == "skill"
    assert session["blocks"][0]["block_type"] == "mindset"
    assert session["blocks"][0]["coaching_cues"]
    assert session["objective"]
    assert session["mindset_anchor"]["intent"]
    assert [app.block_name for app in result.applied] == [session["blocks"][0]["display_name"]]


def test_watch_lands_on_the_first_training_day_beside_existing_work():
    plan = merge_planner_owned_structured_content(_plan(), _brief()).plan

    monday = plan["weeks"][0]["days"][0]
    assert monday["weekday"] == "Mon"
    # Added alongside the day's training, never replacing it.
    assert [session["title"] for session in monday["sessions"]] == ["Strength", "Tactical Focus"]
    assert plan["weeks"][0]["days"][1]["sessions"] == []


def test_bank_content_is_reproduced_exactly_on_the_card():
    spec = _spec()
    entry = spec["tactical_watch"]["weekly_rotation"][0]
    watch = entry["tactical_watch"]

    plan = merge_planner_owned_structured_content(_plan(), {"open_plan_spec": spec}).plan
    session = _watch_sessions(plan)[0]
    block = session["blocks"][0]

    assert session["objective"] == watch["why"]
    assert block["display_name"] == entry["name"]
    assert block["duration"] == {"value": watch["duration_min"], "unit": "minutes"}
    assert block["coaching_cues"] == list(watch["instructions"])
    assert block["progression_rule"] == watch["progress"]
    assert session["mindset_anchor"]["focus_cue"] == watch["mindset"]["focus"]


def test_four_week_card_gets_its_own_watch_each_week():
    plan = merge_planner_owned_structured_content(_plan(week_count=4), _brief()).plan

    names = [session["blocks"][0]["display_name"] for session in _watch_sessions(plan)]
    assert len(names) == 4
    # One distinct watch per week, matching the rotation order.
    assert names == [
        entry["name"] for entry in _spec()["tactical_watch"]["weekly_rotation"]
    ]


def test_single_template_week_uses_the_week_one_watch():
    plan = merge_planner_owned_structured_content(_plan(), _brief()).plan
    rotation = _spec()["tactical_watch"]["weekly_rotation"]

    assert _watch_sessions(plan)[0]["blocks"][0]["display_name"] == rotation[0]["name"]


def test_merge_is_idempotent_and_repairs_a_finalizer_written_card():
    brief = _brief()
    once = merge_planner_owned_structured_content(_plan(), brief).plan
    twice = merge_planner_owned_structured_content(once, brief).plan

    # A card the finalizer already wrote is repaired in place, never duplicated.
    assert len(_watch_sessions(twice)) == 1
    assert twice == once


def test_a_drifted_finalizer_card_is_repaired_to_the_bank():
    brief = _brief()
    plan = _plan()
    plan["weeks"][0]["days"][2]["sessions"].append(
        {
            "session_id": "drifted",
            "session_type": "skill",
            "title": "Tactical Focus",
            "objective": "Do some tactical thinking.",
            "blocks": [],
        }
    )

    result = merge_planner_owned_structured_content(plan, brief)
    sessions = _watch_sessions(result.plan)
    assert len(sessions) == 1
    # Repaired where the finalizer put it, with the bank's own content.
    assert sessions[0]["objective"] == (
        _spec()["tactical_watch"]["weekly_rotation"][0]["tactical_watch"]["why"]
    )
    assert sessions[0]["blocks"][0]["coaching_cues"]


def test_duplicate_watch_sessions_are_left_alone_and_reported():
    plan = _plan()
    for index in (1, 2):
        plan["weeks"][0]["days"][index]["sessions"].append(
            {"session_id": f"dupe-{index}", "title": "Tactical Focus", "blocks": []}
        )

    result = merge_planner_owned_structured_content(plan, _brief())
    # Fail closed on ambiguity rather than guessing which card is authoritative.
    assert result.applied == []
    assert [issue.reason for issue in result.unresolved] == [
        "Tactical Focus session not uniquely resolved"
    ]


def test_duplicate_blocks_in_one_watch_session_are_reported_not_guessed():
    """Two blocks claiming the drill is the same ambiguity as two sessions."""
    spec = _spec()
    drill = spec["tactical_watch"]["weekly_rotation"][0]["name"]
    plan = _plan()
    plan["weeks"][0]["days"][0]["sessions"].append(
        {
            "session_id": "written-by-finalizer",
            "session_type": "skill",
            "title": "Tactical Focus",
            "objective": "Stale objective.",
            "blocks": [
                {"block_id": "a", "display_name": drill, "coaching_cues": []},
                {"block_id": "b", "display_name": drill, "coaching_cues": []},
            ],
        }
    )

    result = merge_planner_owned_structured_content(plan, {"open_plan_spec": spec})
    assert result.applied == []
    assert [issue.reason for issue in result.unresolved] == [
        "locked block not uniquely resolved"
    ]
    # Nothing is repaired or removed: the ambiguous card is left exactly as found.
    session = result.plan["weeks"][0]["days"][0]["sessions"][1]
    assert session["objective"] == "Stale objective."
    assert [block["block_id"] for block in session["blocks"]] == ["a", "b"]


def test_a_week_with_no_training_day_is_reported_not_invented():
    plan = {"weeks": [{"week_index": 1, "days": []}]}

    result = merge_open_plan_tactical_watch(plan, _brief())
    assert result.applied == []
    assert [issue.reason for issue in result.unresolved] == [
        "open plan week has no training day"
    ]
    assert plan["weeks"][0]["days"] == []


@pytest.mark.parametrize(
    "brief",
    [
        {},
        {"open_plan_spec": {}},
        {"open_plan_spec": {"plan_type": "open_ongoing_system"}},
        {"weekly_role_map": {"weeks": []}},
        None,
    ],
)
def test_no_open_plan_rotation_is_a_no_op(brief):
    plan = _plan()
    result = merge_open_plan_tactical_watch(plan, brief)

    assert result.applied == []
    assert result.plan == plan


def test_dated_camps_are_untouched_by_the_open_plan_pathway():
    dated_brief = {
        "weekly_role_map": {"weeks": [{"session_roles": []}]},
        "fight_date": "2026-06-01",
    }
    plan = _plan()

    assert merge_open_plan_tactical_watch(plan, dated_brief).plan == plan


def _schema_valid_open_plan() -> dict:
    """A real schema-valid card in open-plan shape, from the model fixtures."""
    from tests.test_structured_plan_models import _valid_plan

    plan = _valid_plan()
    plan["plan_metadata"]["plan_type"] = "open_ongoing_system"
    event_context = plan.get("event_context")
    if isinstance(event_context, dict):
        event_context["event_type"] = "none"
        for key in ("fight_date", "match_date", "weigh_in_date"):
            if key in event_context:
                event_context[key] = None
    plan["countdown_labels"] = []

    template_week = plan["weeks"][0]
    template_day = template_week["days"][0]
    days = []
    for weekday in TRAINING_DAYS:
        day = deepcopy(template_day)
        day["weekday"] = weekday
        # An open plan is undated: the server projects real dates later.
        day["date"] = ""
        day["countdown_label"] = ""
        days.append(day)
    template_week.update(
        {"days": days, "start_date": "", "end_date": "",
         "countdown_start": "", "countdown_end": ""}
    )
    plan["weeks"] = [template_week]
    return plan


def test_merged_card_still_satisfies_the_schema_and_open_plan_contract():
    """The watch is injected after schema validation, so it must not break it."""
    parsed = safe_parse_structured_plan(_schema_valid_open_plan())
    assert parsed.ok, parsed.errors
    assert parsed.plan is not None

    brief = _brief()
    merged = merge_planner_owned_structured_content(
        parsed.plan.model_dump(mode="json"), brief
    ).plan

    assert _watch_sessions(merged)
    # Re-parse: the injected session must be schema-valid on its own terms.
    reparsed = safe_parse_structured_plan(merged)
    assert reparsed.ok, reparsed.errors
    # And it must not break the scheduling contract that gates publication.
    assert _open_plan_contract_errors(merged, brief) == []


def test_merge_does_not_add_or_reorder_open_plan_days():
    """The contract pins day count and weekday order; the watch rides inside a day."""
    brief = _brief()
    before = _schema_valid_open_plan()
    merged = merge_planner_owned_structured_content(deepcopy(before), brief).plan

    assert [day["weekday"] for day in merged["weeks"][0]["days"]] == TRAINING_DAYS
    assert len(merged["weeks"][0]["days"]) == len(before["weeks"][0]["days"])
