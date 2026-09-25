"""The enhanced card survives the calendar spine running before its gate.

Production (plans 20a4dbed, 75fb5c5d, 50de8664): since the locked merge began
restoring the planner's day spine *before* the faithfulness gate, every rest day
the Stage 2 text did not spell out ("D-20", "D-16", "D-9", "D-2") failed the
card as an invented countdown, so the athlete fell back to the rebuilt card.
This drives that exact path with a real planner brief.
"""

from __future__ import annotations

import datetime

import pytest

from api.structured_plan_faithfulness import COUNTDOWN, check_structured_faithfulness
from api.structured_plan_generation import _merge_locked_content, _normalize_block
from api.structured_plan_models import SessionBlock
from support import _build_request


@pytest.fixture(scope="module")
def camp_brief() -> dict:
    generate_plan_sync = pytest.importorskip("fightcamp.main").generate_plan_sync
    fight_date = (datetime.date.today() + datetime.timedelta(days=21)).isoformat()
    request = _build_request(
        {
            "fight_date": fight_date,
            "hard_sparring_days": ["Tuesday"],
            "training_availability": ["Monday", "Tuesday", "Thursday", "Saturday"],
            "weekly_training_frequency": 4,
        }
    ).to_payload()
    request["random_seed"] = 3
    return generate_plan_sync(request)["planning_brief"]


def _first_exercise_day(brief: dict) -> tuple[int, str]:
    for week in (brief.get("weekly_role_map") or {}).get("weeks") or []:
        for role in week.get("session_roles") or []:
            if not isinstance(role.get("scheduled_d_day"), int):
                continue
            for item in role.get("selected_exercise_assignments") or []:
                if isinstance(item, dict) and item.get("name"):
                    return role["scheduled_d_day"], str(item["name"])
    raise AssertionError("fixture must schedule a selected exercise")


def test_spine_rest_days_do_not_fail_the_card_as_invented_countdowns(camp_brief):
    d_day, name = _first_exercise_day(camp_brief)
    source = f"D-{d_day} (Monday) — Session\n- {name}: 3 sets x 5 reps.\n"
    converter_card = {
        "weeks": [
            {
                "countdown_start": f"D-{d_day}",
                "countdown_end": f"D-{d_day}",
                "days": [
                    {
                        "countdown_label": f"D-{d_day}",
                        "today_card": {"headline": "Session"},
                        "sessions": [
                            {
                                "session_id": "s1",
                                "blocks": [{"block_type": "strength", "display_name": name}],
                            }
                        ],
                    }
                ],
            }
        ]
    }

    merged = _merge_locked_content(converter_card, camp_brief)
    labels = [day["countdown_label"] for week in merged["weeks"] for day in week["days"]]
    assert len(labels) > 1, "the spine must have restored the camp's other days"

    violations = check_structured_faithfulness(merged, source, camp_brief)
    assert not [v for v in violations if v.startswith(COUNTDOWN)], violations


@pytest.mark.parametrize(
    ("tempo", "expected", "cue"),
    [
        ("3-1-1-0", {"eccentric": 3, "pause_bottom": 1, "concentric": 1, "pause_top": 0}, None),
        ("31X0", {"eccentric": 3, "pause_bottom": 1, "concentric": "X", "pause_top": 0}, None),
        ([3, 0, 1], {"eccentric": 3, "pause_bottom": 0, "concentric": 1}, None),
        ("slow 3 sec lower", None, "Tempo: slow 3 sec lower"),
        (None, None, None),
    ],
)
def test_string_tempo_never_rejects_the_card(tempo, expected, cue):
    block = _normalize_block(
        {"block_type": "strength", "display_name": "Goblet Squat", "tempo": tempo}
    )
    assert block["tempo"] == expected
    assert (cue in block.get("coaching_cues", [])) if cue else True
    SessionBlock.model_validate(block)
