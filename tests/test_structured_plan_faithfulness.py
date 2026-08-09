"""Tests for the structured_plan faithfulness gate.

The structured card is a second LLM conversion of the validated Stage 2
``final_plan_text``. These tests prove the gate rejects a card that introduces
exercises, invents countdown markers, or moves work into the wrong D-day, and
that a faithful (or merely reworded) card passes — so the athlete only ever sees
a card that reflects the validated text, otherwise the raw text fallback.
"""
from __future__ import annotations

import api.structured_plan_faithfulness as faithfulness
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

LOCKED_WATCH_SOURCE = """D-11 (Tuesday): Fight Tactical Watch
Why: Know what happens after the first punches so pocket exchanges stay planned rather than chaotic.
- Pocket Exchange Map: 10 minutes, tactical review only. No physical load.
  Step 1: Identify the opponent's most common pocket sequence.
  Step 2: Choose your answer to that sequence.
  Step 3: Choose the finishing shot that best fits the opening.
  Step 4: Decide whether that exchange should end with an exit or a smother.
  Intent: Win the second decision inside the pocket.
  Focus: Watch the opponent's response after the first two punches.
  Reset: If the exchange loses shape, smother or leave instead of trading blindly.
  Anchor: Know the next beat.
  Purpose: SPP pocket planning for a brawler.
  Progress: Rehearse the chosen exchange ending, not just the opening combination.
"""

LOCKED_WATCH_BRIEF = {
    "weeks": [{
        "session_roles": [{
            "display_text": "\n".join(LOCKED_WATCH_SOURCE.splitlines()[1:]),
            "preferred_exercise_names": ["Pocket Exchange Map"],
            "governance": {
                "selected_drill_locked": True,
                "selected_drill_name": "Pocket Exchange Map",
            },
        }]
    }]
}


def _locked_watch_card() -> dict:
    return {
        "weeks": [{
            "countdown_start": "D-11",
            "countdown_end": "D-11",
            "days": [{
                "countdown_label": "D-11",
                "sessions": [{
                    "objective": (
                        "Know what happens after the first punches so pocket exchanges "
                        "stay planned rather than chaotic."
                    ),
                    "mindset_anchor": {
                        "intent": "Win the second decision inside the pocket.",
                        "focus_cue": "Watch the opponent's response after the first two punches.",
                        "reset_cue": (
                            "If the exchange loses shape, smother or leave instead of "
                            "trading blindly."
                        ),
                        "confidence_anchor": "Know the next beat.",
                    },
                    "blocks": [{
                        "block_type": "mindset",
                        "display_name": "Pocket Exchange Map",
                        "purpose": "SPP pocket planning for a brawler.",
                        "coaching_cues": [
                            "Identify the opponent's most common pocket sequence.",
                            "Choose your answer to that sequence.",
                            "Choose the finishing shot that best fits the opening.",
                            "Decide whether that exchange should end with an exit or a smother.",
                        ],
                        "progression_rule": (
                            "Rehearse the chosen exchange ending, not just the opening "
                            "combination."
                        ),
                    }],
                }],
            }],
        }],
    }


def test_locked_tactical_watch_exact_content_passes_across_structured_fields():
    assert check_structured_faithfulness(
        _locked_watch_card(), LOCKED_WATCH_SOURCE, LOCKED_WATCH_BRIEF
    ) == []


def test_locked_tactical_watch_missing_one_step_is_rejected():
    plan = _locked_watch_card()
    plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["coaching_cues"].pop(2)
    violations = check_structured_faithfulness(plan, LOCKED_WATCH_SOURCE, LOCKED_WATCH_BRIEF)
    assert any("LOCKED_CONTENT" in item and "Step 3" in item for item in violations)


def test_locked_tactical_watch_step_moved_to_another_day_is_rejected():
    source = LOCKED_WATCH_SOURCE + """
D-10 (Wednesday): Recovery
- Easy mobility: 10 minutes.
"""
    plan = _locked_watch_card()
    watch_cues = plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0][
        "coaching_cues"
    ]
    moved_step = watch_cues.pop(2)
    plan["weeks"][0]["days"].append(
        {
            "countdown_label": "D-10",
            "sessions": [
                {
                    "objective": "Recover well.",
                    "blocks": [
                        {
                            "block_type": "mobility",
                            "display_name": "Easy mobility",
                            "coaching_cues": [moved_step],
                        }
                    ],
                }
            ],
        }
    )

    violations = check_structured_faithfulness(plan, source, LOCKED_WATCH_BRIEF)

    assert any("LOCKED_CONTENT" in item and "Step 3" in item for item in violations)


def test_locked_tactical_watch_missing_all_steps_and_progress_is_rejected():
    block = _locked_watch_card()["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    block["coaching_cues"] = []
    block["progression_rule"] = None
    violations = check_structured_faithfulness(
        {
            "weeks": [{
                "countdown_start": "D-11",
                "countdown_end": "D-11",
                "days": [{"countdown_label": "D-11", "sessions": [{"blocks": [block]}]}],
            }]
        },
        LOCKED_WATCH_SOURCE,
        LOCKED_WATCH_BRIEF,
    )
    labels = ("Step 1", "Step 2", "Step 3", "Step 4", "Progress")
    assert all(any(label in item for item in violations) for label in labels)


def test_locked_tactical_watch_rewritten_mindset_is_rejected():
    plan = _locked_watch_card()
    plan["weeks"][0]["days"][0]["sessions"][0]["mindset_anchor"]["intent"] = (
        "Clarify pocket decisions."
    )
    violations = check_structured_faithfulness(plan, LOCKED_WATCH_SOURCE, LOCKED_WATCH_BRIEF)
    assert any("Intent" in item for item in violations)


def test_locked_tactical_watch_missing_progress_is_rejected():
    plan = _locked_watch_card()
    plan["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]["progression_rule"] = None
    violations = check_structured_faithfulness(plan, LOCKED_WATCH_SOURCE, LOCKED_WATCH_BRIEF)
    assert any("Progress" in item for item in violations)


def test_unlocked_role_does_not_enable_locked_content_invariant():
    role = {
        **LOCKED_WATCH_BRIEF["weeks"][0]["session_roles"][0],
        "governance": {"selected_drill_locked": False},
    }
    brief = {"session_roles": [role]}
    assert check_structured_faithfulness(_locked_watch_card(), LOCKED_WATCH_SOURCE, brief) == []


def test_locked_content_rejection_uses_existing_text_fallback_path():
    from test_structured_plan_models import _valid_plan

    plan = _valid_plan()
    week = plan["weeks"][0]
    week["countdown_start"] = week["countdown_end"] = "D-11"
    day = week["days"][0]
    day["countdown_label"] = "D-11"
    session = day["sessions"][0]
    faithful = _locked_watch_card()["weeks"][0]["days"][0]["sessions"][0]
    session["objective"] = faithful["objective"]
    session["mindset_anchor"] = faithful["mindset_anchor"]
    session["blocks"] = [faithful["blocks"][0]]
    session["blocks"][0].update({"block_id": "watch-1", "coaching_cues": []})

    outcome = build_structured_plan_outcome(
        plan,
        raw_markdown=LOCKED_WATCH_SOURCE,
        planning_brief=LOCKED_WATCH_BRIEF,
    )

    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None
    assert any("LOCKED_CONTENT" in error and "Step 1" in error for error in outcome.errors)


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


def test_card_with_countdown_against_sourceless_text_is_unverifiable():
    # Card-first hard gate: a card that claims a countdown structure cannot be
    # proven faithful against source text with no D-day marker, so it is rejected
    # as unverifiable rather than skipped.
    violations = check_structured_faithfulness(_FAITHFUL, "# raw")
    assert violations
    assert any(v.startswith("COUNTDOWN") for v in violations)


def test_no_countdown_claim_and_no_source_returns_clean():
    # A degenerate card making no countdown claim has nothing to project, so the
    # schema gate remains the only authority and the faithfulness gate stays out
    # of it. An empty plan likewise has no basis to judge.
    assert check_structured_faithfulness({"weeks": []}, "# raw") == []
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


# --- real generated plan formats -------------------------------------------

# The actual Stage 2 output leads with the countdown ("D-32 (Wednesday) — ...")
# and also nests it inside markdown headings ("### Mon (D-30) — ..."). Week
# headers ("GPP — Week 1 (D-33 to D-27)") must not be read as training days.
REAL_SOURCE = """GPP — Week 1 (D-33 to D-27)

D-32 (Wednesday) — Aerobic support
- Zone 2 bike ride, 40 minutes easy aerobic flush.

D-30 (Friday) — Strength
- Barbell Back Squat 4x5 at 80 percent.
- Pallof Press 3x10 each side anti-rotation.
"""

REAL_SOURCE_HEADINGS = """## GPP — Week 1 (D-33 to D-27)

### Wed (D-32) — Aerobic support
- Zone 2 bike ride, 40 minutes easy aerobic flush.

### Fri (D-30) — Strength
- Barbell Back Squat 4x5 at 80 percent.
- Pallof Press 3x10 each side anti-rotation.
"""


def test_real_leading_dday_format_pallof_misplaced_is_rejected():
    # Source assigns Pallof to D-30; the card placing it on D-32 must be MISPLACED
    # even though the day headers use the leading "D-32 (Wednesday) —" format.
    plan = _plan(
        [
            ("D-32", [("accessory", "Pallof Press")]),
            ("D-30", [("strength", "Barbell Back Squat")]),
        ]
    )
    violations = check_structured_faithfulness(plan, REAL_SOURCE)
    assert any(v.startswith("MISPLACED") for v in violations), violations


def test_real_markdown_heading_format_pallof_misplaced_is_rejected():
    plan = _plan(
        [
            ("D-32", [("accessory", "Pallof Press")]),
            ("D-30", [("strength", "Barbell Back Squat")]),
        ]
    )
    violations = check_structured_faithfulness(plan, REAL_SOURCE_HEADINGS)
    assert any(v.startswith("MISPLACED") for v in violations), violations


def test_real_format_faithful_card_passes():
    # Pallof kept on its source day (D-30) — no misplacement, no fabrication.
    plan = _plan(
        [
            ("D-32", [("conditioning", "Zone 2 Bike Ride")]),
            ("D-30", [("strength", "Barbell Back Squat"), ("accessory", "Pallof Press")]),
        ]
    )
    assert check_structured_faithfulness(plan, REAL_SOURCE) == []


def test_tactical_watch_note_label_is_not_treated_as_misplaced_exercise():
    source = """# FIGHT CAMP PLAN

D-17 (Friday) - Fight Tactical Watch
- Watch: 8-12 min.
Purpose: identify opponent rhythm.
Output: write 3 fight cues only.

D-9 (Saturday) - Fight Tactical Watch
- Watch: 8-12 min.
Purpose: identify bait reactions and exits.
Output: write 3 fight cues only.
"""
    plan = _plan(
        [
            ("D-9", [("conditioning", "Watch + note")]),
        ]
    )
    plan["weeks"][0]["countdown_start"] = "D-17"
    plan["weeks"][0]["countdown_end"] = "D-9"

    assert check_structured_faithfulness(plan, source) == []


def test_week_header_is_not_parsed_as_a_training_day():
    # "GPP — Week 1 (D-33 to D-27)" must not create a D-33/D-27 section that
    # captures the following day's exercises. Pallof belongs to D-30 only, so the
    # source token index must map it to {30}, making the misplacement check fire.
    sections = faithfulness._source_day_sections(REAL_SOURCE)
    assert set(sections) == {32, 30}
    token_days = faithfulness._source_token_days(sections)
    assert token_days.get("pallof") == {30}


def test_countdown_leading_fight_week_titles_remain_distinct_day_sections():
    """A D-day heading may legitimately include ``fight-week`` in its title."""
    source = """D-11 (Wednesday) — Light Combat / Technical
Your declared light-combat / technical session. Keep it as scheduled.

D-9 (Friday) — Fight-week freshness
- Band face pull, light: 2 x 12 reps, controlled tempo.

D-4 (Wednesday) — Light Combat / Technical
Your declared light-combat / technical session. Keep it as scheduled.

D-2 (Friday) — Fight-week freshness
- Band pull-apart, low volume: 2 x 12 controlled reps.
"""

    sections = faithfulness._source_day_sections(source)
    assert set(sections) == {11, 9, 4, 2}
    token_days = faithfulness._source_token_days(sections)
    assert token_days.get("face") == {9}
    assert token_days.get("apart") == {2}


# --- fail-closed on internal error -----------------------------------------


def test_internal_error_fails_closed(monkeypatch):
    # If the checker itself crashes it must reject the card (return a violation),
    # never silently allow an unverified card through.
    def _boom(*_args, **_kwargs):
        raise RuntimeError("kaboom")

    monkeypatch.setattr(faithfulness, "_check", _boom)
    violations = check_structured_faithfulness(_FAITHFUL, SOURCE)
    assert violations and violations[0].startswith("INTERNAL")


def test_internal_error_falls_back_via_outcome(monkeypatch):
    from test_structured_plan_models import _valid_plan

    monkeypatch.setattr(
        "api.structured_plan_generation.check_structured_faithfulness",
        lambda *_a, **_k: ["INTERNAL: boom"],
    )
    outcome = build_structured_plan_outcome(_valid_plan(), raw_markdown="### Mon (D-15) — x")
    assert outcome.status == "invalid_fallback_used"
    assert outcome.structured_plan is None
