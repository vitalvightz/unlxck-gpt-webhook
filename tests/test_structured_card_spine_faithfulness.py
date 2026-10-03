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
from api.structured_plan_generation import _merge_locked_content, _normalize_block, regroup_split_sessions
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


def test_dose_in_display_name_moves_out_when_the_block_carries_it():
    block = _normalize_block(
        {
            "block_type": "conditioning",
            "display_name": "Assault Bike - 25 min",
            "duration": {"value": 25, "unit": "minutes"},
        }
    )
    assert block["display_name"] == "Assault Bike"


def test_dose_in_display_name_stays_when_it_is_the_only_prescription():
    block = _normalize_block({"block_type": "conditioning", "display_name": "Assault Bike - 25 min"})
    assert block["display_name"] == "Assault Bike - 25 min"


_SPLIT_SOURCE = """GPP — Week 1 (D-33 to D-27) — Build aerobic base
D-33 (Saturday) — Light Combat / Technical
Your declared light-combat / technical session. Keep it as scheduled.

D-33 (Saturday) — Aerobic support
Why: easy aerobic work to keep repeatability and help recovery.
- Easy Assault Bike: duration 25 min; continuous; RPE 5.
  Cue: relaxed pace.
- Staggered Stance Hold: 1 set x 15 sec hold; rest 60 sec; RPE 4.

D-27 (Friday) — Strength anchor
Why: build force.
- Trap Bar Jump: 3 x 3; RPE 7.
- Barbell Thruster: 3 x 5; RPE 7.

D-26 (Saturday) — Strength
- Goblet Squat: 3 x 5.

D-26 (Saturday) — Conditioning
- Easy Bike: 20 min.
"""


def _one_block_session(title, name, session_type="mixed", session_id=None):
    return {
        "title": title,
        "session_type": session_type,
        "session_id": session_id,
        "objective": f"why {title}",
        "blocks": [{"display_name": name}],
    }


def test_sessions_split_from_one_source_header_are_regrouped():
    plan = {"weeks": [{"days": [
        {"countdown_label": "D-33", "sessions": [
            _one_block_session("Tactical Focus", "Range Map", "skill", "locked-d-33-tactical-watch"),
            _one_block_session("Staggered Stance Hold", "Staggered Stance Hold"),
            _one_block_session("Easy Assault Bike", "Assault Bike - 25 min", "conditioning"),
        ]},
        {"countdown_label": "D-27", "sessions": [
            _one_block_session("Trap Bar Jump", "Trap Bar Jump", "strength_power"),
            _one_block_session("Barbell Thruster", "Barbell Thruster", "strength_power"),
        ]},
    ]}]}

    out = regroup_split_sessions(plan, _SPLIT_SOURCE)

    d33, d27 = out["weeks"][0]["days"]
    # The server-owned Tactical Focus is never folded into app work.
    assert [s["title"] for s in d33["sessions"]] == ["Tactical Focus", "Aerobic support"]
    aerobic = d33["sessions"][1]
    assert [b["display_name"] for b in aerobic["blocks"]] == ["Staggered Stance Hold", "Assault Bike - 25 min"]
    assert aerobic["objective"] == "easy aerobic work to keep repeatability and help recovery."
    assert aerobic["session_type"] == "mixed"
    assert [s["title"] for s in d27["sessions"]] == ["Strength anchor"]
    assert d27["sessions"][0]["session_type"] == "strength_power"
    # The input plan is not mutated.
    assert len(plan["weeks"][0]["days"][1]["sessions"]) == 2


def test_separate_source_sessions_on_one_day_stay_separate():
    plan = {"weeks": [{"days": [
        {"countdown_label": "D-26", "sessions": [
            _one_block_session("Strength", "Goblet Squat", "strength_power"),
            _one_block_session("Conditioning", "Easy Bike", "conditioning"),
        ]},
    ]}]}

    out = regroup_split_sessions(plan, _SPLIT_SOURCE)

    assert [s["title"] for s in out["weeks"][0]["days"][0]["sessions"]] == ["Strength", "Conditioning"]
