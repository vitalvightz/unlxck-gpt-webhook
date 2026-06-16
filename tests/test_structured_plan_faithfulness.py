"""Tests for the structured_plan faithfulness gate.

The structured card is a second LLM conversion of the validated Stage 2
``final_plan_text``. These tests prove the gate rejects a card that introduces
exercises, invents countdown markers, or moves work into the wrong D-day, and
that a faithful (or merely reworded) card passes — so the athlete only ever sees
a card that reflects the validated text, otherwise the raw text fallback.
"""
from __future__ import annotations

from api.structured_plan_faithfulness import check_structured_faithfulness
from api.structured_plan_generation import build_structured_plan_outcome

# A realistic Stage 2 plan source: countdown day headers + named exercises.
# D-32 is an aerobic-support day; D-30 is the strength day that owns the squat
# and the Pallof anti-rotation work.
SOURCE = """# FIGHT CAMP PLAN

## Week 1 — SPP (D-32 → D-30)

### Mon (D-32) — Aerobic Support
- Zone 2 bike ride, 40 minutes easy aerobic flush.

### Wed (D-30) — Strength
- Barbell Back Squat 4x5 at 80 percent.
- Pallof Press 3x10 each side anti-rotation.
"""


def _plan(days: list[tuple[str, list[tuple[str, str]]]]) -> dict:
    """Minimal structured-plan dict: ``[(countdown_label, [(block_type, name)])]``."""
    return {
        "weeks": [
            {
                "countdown_start": "D-32",
                "countdown_end": "D-30",
                "days": [
                    {
                        "countdown_label": label,
                        "sessions": [
                            {
                                "blocks": [
                                    {"block_type": block_type, "display_name": name}
                                    for block_type, name in blocks
                                ]
                            }
                        ],
                    }
                    for label, blocks in days
                ],
            }
        ]
    }


_FAITHFUL = _plan(
    [
        ("D-32", [("conditioning", "Zone 2 Bike Ride")]),
        ("D-30", [("strength", "Barbell Back Squat"), ("accessory", "Pallof Press")]),
    ]
)


# --- faithful / reworded cards pass ----------------------------------------


def test_faithful_card_has_no_violations():
    assert check_structured_faithfulness(_FAITHFUL, SOURCE) == []


def test_reworded_exercise_passes():
    # "Barbell Back Squat" -> "Heavy Back Squats": still shares the squat token
    # (inflection-tolerant), so a rewording is not treated as fabrication.
    plan = _plan(
        [
            ("D-32", [("conditioning", "Zone 2 Bike Ride")]),
            ("D-30", [("strength", "Heavy Back Squats"), ("accessory", "Pallof Press")]),
        ]
    )
    assert check_structured_faithfulness(plan, SOURCE) == []


def test_no_basis_to_judge_returns_clean():
    # Source without any D-day marker is not evaluated (the schema gate is the
    # only authority), so a stub markdown can never trip the faithfulness gate.
    assert check_structured_faithfulness(_FAITHFUL, "# raw") == []
    assert check_structured_faithfulness({}, SOURCE) == []


# --- introduced exercises are rejected -------------------------------------


def test_introduced_exercise_is_rejected():
    plan = _plan(
        [
            ("D-32", [("conditioning", "Zone 2 Bike Ride")]),
            ("D-30", [("strength", "Nordic Hamstring Curl")]),  # never in source
        ]
    )
    violations = check_structured_faithfulness(plan, SOURCE)
    assert any(v.startswith("INTRODUCED") for v in violations), violations


def test_introduced_exercise_falls_back_via_outcome():
    # The schema-valid card is downgraded to invalid_fallback_used so plan_text
    # (the validated source) is what the athlete sees.
    from test_structured_plan_models import _valid_plan

    plan = _valid_plan()
    # _valid_plan's exercise ("Barbell Back Squat" / "D-15") shares nothing with
    # this fabricated-only source, so the gate must reject it.
    source = (
        "# FIGHT CAMP PLAN\n\n### Mon (D-15) — Conditioning\n"
        "- Assault bike intervals, ten rounds.\n"
    )
    outcome = build_structured_plan_outcome(plan, raw_markdown=source)
    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None
    assert any("faithfulness" in err for err in outcome.errors)


def test_coach_led_day_stays_minimal():
    # A coach-led day in the source carries no app-owned S&C exercise; a card
    # that injects an app-owned strength block onto it is rejected because that
    # exercise is absent from the source.
    source = (
        "# FIGHT CAMP PLAN\n\n## Week 1 — SPP (D-20 → D-18)\n\n"
        "### Mon (D-20) — Coach-led sparring\n"
        "- Coach-led technical sparring. No app-owned strength work today.\n\n"
        "### Wed (D-18) — Strength\n- Trap-bar deadlift 4x3.\n"
    )
    plan = _plan(
        [
            ("D-20", [("strength", "Barbell Hip Thrust")]),  # app-owned, not in source
        ]
    )
    # Re-point the week countdown to the coach-led window.
    plan["weeks"][0]["countdown_start"] = "D-20"
    plan["weeks"][0]["countdown_end"] = "D-18"
    violations = check_structured_faithfulness(plan, source)
    assert any(v.startswith("INTRODUCED") for v in violations), violations


# --- misplaced work across D-days is rejected ------------------------------


def test_pallof_moved_to_wrong_dday_is_rejected():
    # The source assigns Pallof to D-30; placing it on D-32 is a boundary break.
    plan = _plan(
        [
            ("D-32", [("accessory", "Pallof Press")]),  # source puts this in D-30
            ("D-30", [("strength", "Barbell Back Squat")]),
        ]
    )
    violations = check_structured_faithfulness(plan, SOURCE)
    assert any(v.startswith("MISPLACED") for v in violations), violations


def test_strength_kept_in_correct_dday_passes():
    # Same exercises, correct days — no misplacement flagged.
    assert check_structured_faithfulness(_FAITHFUL, SOURCE) == []


# --- invented countdown markers are rejected -------------------------------


def test_new_countdown_marker_is_rejected():
    plan = _plan(
        [
            ("D-99", [("strength", "Barbell Back Squat")]),  # D-99 not in source
        ]
    )
    violations = check_structured_faithfulness(plan, SOURCE)
    assert any(v.startswith("COUNTDOWN") for v in violations), violations
