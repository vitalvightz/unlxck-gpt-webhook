"""Exercise names ending in a parenthetical still find their plan-text dose.

Production (plan 6c418f41): the deterministic card showed "Jump Lunge
(Alternating)" with no sets/reps and "Pivot-and-Strike (Rotation Focus)" with
the planner's bank dose (4x2, rest 120s) instead of the athlete's text (5 x 3,
rest 90 sec). The title matcher required a delimiter straight after the last
word, so the name's own ")" made every parenthetical exercise miss its line.
"""

from __future__ import annotations

from api.structured_plan_deterministic_fallback import _source_block
from api.structured_plan_faithfulness import _source_block_segment

SOURCE = """D-20 (Monday) — Strength.
Why: explosive lateral and rotational throws.
- Lateral Bound-to-Slip: 5 sets x 3 reps; rest 90 sec; max speed intent.
- Pivot-and-Strike (Rotation Focus): 5 sets x 3 reps; rest 90 sec; max speed intent.
  Stop: dizziness or imbalance, stop.
- Jump Lunge (Alternating): 3 sets x 2 reps; rest 120 sec; max speed intent.
  Stop: landing pain or loss of control, stop.
- Push-Up [Weighted]: 2 sets x 8 reps; rest 120 sec; RPE 6.
"""


def test_parenthetical_names_take_the_text_dose():
    lines = SOURCE.splitlines()
    pivot = _source_block(lines, "Pivot-and-Strike (Rotation Focus)")
    lunge = _source_block(lines, "Jump Lunge (Alternating)")
    push = _source_block(lines, "Push-Up [Weighted]")

    assert (pivot["sets"], pivot["reps"], pivot["rest"]) == (5, 3, {"value": 90, "unit": "seconds"})
    assert pivot["stop_rules"] == ["dizziness or imbalance, stop."]
    assert (lunge["sets"], lunge["reps"], lunge["rest"]) == (3, 2, {"value": 120, "unit": "seconds"})
    assert (push["sets"], push["reps"]) == (2, 8)


def test_a_shorter_name_does_not_claim_a_parenthetical_line():
    # Exactness is unchanged: "Jump Lunge" is not "Jump Lunge (Alternating)".
    assert _source_block(SOURCE.splitlines(), "Jump Lunge") is None
    assert _source_block_segment(SOURCE, "Jump Lunge") == ""


def test_faithfulness_segment_finds_parenthetical_names():
    segment = _source_block_segment(SOURCE, "Jump Lunge (Alternating)")
    assert segment.startswith("- Jump Lunge (Alternating): 3 sets x 2 reps")
    assert "landing pain" in segment
