"""One unbacked detail no longer throws the whole enhanced card away.

Before, an invented exercise, a drill on the wrong day or a model session on a
day the text never mentions rejected the entire card, and the athlete fell back
to the rebuilt card. Salvage drops exactly what the faithfulness rules reject,
keeps the rest, records every removal, and refuses when the card would no
longer represent the plan. Every failed or salvaged card is reported.
"""

from __future__ import annotations

import copy
import logging
import sys
import types

import pytest

from api.stage2_automation import report_structured_card_outcome
from api.structured_plan_faithfulness import (
    check_structured_faithfulness,
    prune_unfaithful_content,
)
from api.structured_plan_generation import StructuredPlanOutcome, build_structured_plan_outcome
from test_structured_plan_models import _valid_plan

SOURCE = """SPP — Week 1 (D-19 to D-13)

D-15 (Wednesday) — Power Transfer Touch
- Barbell Back Squat: 3 sets x 3 reps @ 80% 1RM; rest 180 sec.
- Pallof Press: 2 sets x 10 reps; rest 60 sec.
- Box Jump: 3 sets x 2 reps; rest 120 sec.
- Medicine Ball Scoop Toss: 3 sets x 3 reps; rest 90 sec.
- Split Squat Isometric: 2 holds x 20 sec; rest 60 sec.
"""
BACKED = [
    "Barbell Back Squat",
    "Pallof Press",
    "Box Jump",
    "Medicine Ball Scoop Toss",
    "Split Squat Isometric",
]


def _card(*extra_names: str) -> dict:
    """The shared valid plan, its D-15 session holding the backed drills + extras."""
    plan = _valid_plan()
    session = plan["weeks"][0]["days"][0]["sessions"][0]
    template = session["blocks"][0]
    session["blocks"] = []
    for index, name in enumerate([*BACKED, *extra_names]):
        block = copy.deepcopy(template)
        block["block_id"] = f"b{index}"
        block["display_name"] = name
        block["order_index"] = index
        session["blocks"].append(block)
    return plan


def _names(plan: dict) -> list[str]:
    return [
        block["display_name"]
        for week in plan["weeks"]
        for day in week["days"]
        for session in day["sessions"]
        for block in session["blocks"]
    ]


def test_one_invented_exercise_is_dropped_and_the_rest_survives():
    card = _card("Nordic Hamstring Curl")
    assert check_structured_faithfulness(card, SOURCE), "fixture must start unfaithful"

    pruned, removed = prune_unfaithful_content(card, SOURCE)

    assert pruned is not None
    assert _names(pruned) == BACKED
    assert len(removed) == 1 and removed[0].startswith("INTRODUCED")
    assert check_structured_faithfulness(pruned, SOURCE) == []


def test_model_session_on_a_day_the_text_lacks_is_dropped_but_server_work_stays():
    card = _card()
    week = card["weeks"][0]
    week["days"].append(
        {
            **copy.deepcopy(week["days"][0]),
            "countdown_label": "D-14",
            "date": "2026-10-02",
            "today_card": {**week["days"][0]["today_card"], "headline": "Strength"},
            "sessions": [
                {
                    **copy.deepcopy(week["days"][0]["sessions"][0]),
                    "session_id": "model-14",
                    "blocks": copy.deepcopy(week["days"][0]["sessions"][0]["blocks"][:1]),
                },
                {
                    **copy.deepcopy(week["days"][0]["sessions"][0]),
                    "session_id": "deterministic-14-joint_prep-0",
                    "blocks": [],
                },
            ],
        }
    )

    pruned, removed = prune_unfaithful_content(card, SOURCE)

    assert pruned is not None
    d14 = pruned["weeks"][0]["days"][-1]
    assert [s["session_id"] for s in d14["sessions"]] == ["deterministic-14-joint_prep-0"]
    assert d14["today_card"]["headline"] == ""
    assert any("'D-14'" in item for item in removed)
    assert check_structured_faithfulness(pruned, SOURCE) == []


def test_salvage_refuses_a_card_that_is_mostly_unbacked():
    card = _card("Nordic Hamstring Curl", "Kettlebell Swing", "Sled Push")
    pruned, removed = prune_unfaithful_content(card, SOURCE)
    assert pruned is None
    assert len(removed) == 3


def test_salvage_refuses_when_the_source_has_no_countdown():
    pruned, removed = prune_unfaithful_content(_card("Nordic Hamstring Curl"), "Just prose.")
    assert pruned is None and removed == []


def test_outcome_ships_the_salvaged_card_and_records_what_went():
    outcome = build_structured_plan_outcome(_card("Nordic Hamstring Curl"), raw_markdown=SOURCE)

    assert outcome.status == "valid"
    assert outcome.structured_plan is not None
    assert "Nordic Hamstring Curl" not in _names(outcome.structured_plan)
    assert any(w.startswith("salvaged: INTRODUCED") for w in outcome.warnings)


def test_outcome_waits_for_the_model_repair_before_salvaging():
    card = _card("Nordic Hamstring Curl")
    first = build_structured_plan_outcome(card, raw_markdown=SOURCE, allow_salvage=False)
    assert first.status == "invalid_fallback_used"

    # The repair is still unfaithful: the repaired card is what gets salvaged.
    repaired = build_structured_plan_outcome(
        card,
        raw_markdown=SOURCE,
        repair_fn=lambda _data, _errors: _card("Kettlebell Swing"),
    )
    assert repaired.status == "repair_attempted_valid"
    assert _names(repaired.structured_plan) == BACKED
    assert any("Kettlebell Swing" in w for w in repaired.warnings)

    # A repair that returns nothing usable falls back to salvaging the first pass.
    rescued = build_structured_plan_outcome(
        card, raw_markdown=SOURCE, repair_fn=lambda _data, _errors: None
    )
    assert rescued.status == "valid"
    assert _names(rescued.structured_plan) == BACKED


@pytest.fixture
def sentry_events(monkeypatch):
    events: list[dict] = []

    class _Scope:
        def __init__(self):
            self.data = {"tags": {}}
            self.fingerprint = None

        def set_level(self, level):
            self.data["level"] = level

        def set_tag(self, key, value):
            self.data["tags"][key] = value

        def set_context(self, key, value):
            self.data[key] = value

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            self.data["fingerprint"] = self.fingerprint
            return False

    current: list[_Scope] = []

    def push_scope():
        scope = _Scope()
        current.append(scope)
        return scope

    def capture_message(message):
        events.append({"message": message, **current[-1].data, "fingerprint": current[-1].fingerprint})

    fake = types.SimpleNamespace(push_scope=push_scope, capture_message=capture_message)
    monkeypatch.setitem(sys.modules, "sentry_sdk", fake)
    return events


def test_a_failed_card_raises_an_error_alert_grouped_by_cause(sentry_events, caplog):
    outcome = StructuredPlanOutcome(
        status="invalid_fallback_used",
        errors=[
            "faithfulness: COUNTDOWN: day countdown 'D-16' absent from source text",
            "weeks.1.days.2.sessions.0.blocks.0.tempo: Input should be a valid dictionary",
        ],
    )
    with caplog.at_level(logging.WARNING, logger="api.stage2_automation"):
        kind = report_structured_card_outcome(
            outcome, source="self_serve", log_context={"job_id": "j1", "athlete_id": "a1"}
        )

    assert kind == "failed"
    (event,) = sentry_events
    assert event["level"] == "error"
    assert event["fingerprint"] == ["structured-card", "failed", "invalid_fallback_used", "COUNTDOWN", "schema"]
    assert event["tags"]["structured_card_kinds"] == "COUNTDOWN,schema"
    assert any(
        r.levelno == logging.ERROR and "structured_card_failed" in r.getMessage() and "j1" in r.getMessage()
        for r in caplog.records
    )


def test_a_salvaged_card_raises_a_warning_and_a_clean_card_raises_nothing(sentry_events):
    salvaged = StructuredPlanOutcome(
        status="valid",
        structured_plan={},
        warnings=["salvaged: INTRODUCED: exercise 'Nordic Hamstring Curl' not present in source text; block dropped"],
    )
    assert report_structured_card_outcome(salvaged, source="self_serve") == "salvaged"
    assert sentry_events[-1]["level"] == "warning"
    assert sentry_events[-1]["tags"]["structured_card_kinds"] == "INTRODUCED"

    clean = StructuredPlanOutcome(status="valid", structured_plan={}, warnings=["PRESCRIPTION: advisory"])
    assert report_structured_card_outcome(clean, source="self_serve") is None
    assert len(sentry_events) == 1


def test_ineligible_plans_are_not_alerts(sentry_events):
    skipped = StructuredPlanOutcome(status="not_attempted")
    assert report_structured_card_outcome(skipped, source="self_serve") is None
    unavailable = StructuredPlanOutcome(
        status="not_attempted", errors=["structured conversion unavailable: no key"]
    )
    assert report_structured_card_outcome(unavailable, source="self_serve") == "failed"
