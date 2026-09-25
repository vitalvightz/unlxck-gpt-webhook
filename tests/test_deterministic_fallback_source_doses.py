"""The fallback card shows the dose the athlete was given, never a bank range.

Production case (plan 50de8664, D-17): Stage 2 wrote
``Tempo Shadowboxing: duration 20 min; continuous; RPE 3-4.``, its validator
held the plan for unrelated blockers, no card was stored, and the rebuilt card
printed the drill bank's ``20-30min continuous`` under the plan's own Why.

The planner still decides which days and exercises exist. The plan text now
supplies each selected exercise's exact dose and coaching lines on its own
D-day; with no text line, the planner's bounds resolve to one exact value.
"""

from __future__ import annotations

import re

from api.structured_plan_deterministic_fallback import _exact_working_dose, _session
from api.structured_plan_faithfulness import _source_day_section_lines

PLAN_TEXT = """\
SPP — Week 1 (D-19 to D-13) — Raise fight-specific repeatability and power transfer

D-17 (Monday) — Low-load recovery flush
Why: clear legs and keep breathing steady after weekend work.
- Tempo Shadowboxing: duration 20 min; continuous; RPE 3-4.
  Cue: Keep guard up and breathe steady, focus on smooth technique.
  Purpose: move blood, protect recovery, keep technical rhythm.
  Easier: do 12–15 min continuous at the same tempo.
  Stop: if light-headed or breathing becomes hard.

D-15 (Wednesday) — No planned session
Why: rest and technical work only.
No S&C is scheduled for this slot today.

D-15 (Wednesday) — Strength
- Band-Resisted Jab-Cross Primer: 2 sets x 2 reps; max speed; rest 120 sec; RPE 6.
  Cue: snap the jab then cross, relax on the recover.

D-14 (Thursday) — Strength
Why: keep specific strength and footwork exposure without fatigue.
- Punch-Specific Max Isometric Hold: 3 holds x 10 sec; rest 180 sec; RPE 7.
  Cue: get into punch finish position and hold pressure without swinging.
- Trap Bar Deadlift: 3 sets x 3 reps @ 80% 1RM (established max only); rest 180 sec.
  Stop: if bar speed slows or back position changes.

D-10 (Monday) — Aerobic flush
Why: easy aerobic support.
- Tempo Shadowboxing: duration 25 min; continuous; RPE 3.
"""

SOURCE_DAYS = _source_day_section_lines(PLAN_TEXT)
RANGE = re.compile(r"\d\s*[-–—]\s*\d")


def _tempo_role(d_day: int) -> dict:
    return {
        "role_key": "converted_recovery_flush_day",
        "category": "conditioning",
        "athlete_facing_label": "Low-load recovery flush",
        "scheduled_d_day": d_day,
        "selected_exercise_assignments": [
            {
                "name": "Tempo Shadowboxing",
                "slot_id": "spp_aerobic_1_tempo_shadowboxing",
                "base_prescription": "20-30min continuous",
                "effective_prescription": "20-30min continuous",
            }
        ],
    }


def _only_block(session: dict) -> dict:
    assert session is not None
    (block,) = session["blocks"]
    return block


def test_card_takes_the_exact_dose_the_plan_text_gave():
    session = _session(_tempo_role(17), 17, SOURCE_DAYS.get(17))
    block = _only_block(session)

    assert block["duration"] == {"value": 20, "unit": "minutes"}
    assert not any("20-30" in cue or "20–30" in cue for cue in block["coaching_cues"])
    assert block["coaching_cues"][0] == "continuous"
    # The text's own coaching lines, not the title repeated as a rationale.
    assert session["objective"] == "clear legs and keep breathing steady after weekend work."
    assert block["purpose"] == "move blood, protect recovery, keep technical rhythm."
    assert "Cue: Keep guard up and breathe steady, focus on smooth technique." in block["coaching_cues"]
    assert block["regression_options"] == ["do 12–15 min continuous at the same tempo."]
    assert block["stop_rules"] == ["if light-headed or breathing becomes hard."]
    # The effort is the text's value, unchanged.
    assert block["effort"] == {"method": "RPE", "value": "3-4", "scale": "1-10"}


def test_same_drill_on_another_day_never_lends_its_dose():
    # D-16 carries no Tempo Shadowboxing line; D-10's 25 min must not leak in.
    block = _only_block(_session(_tempo_role(16), 16, SOURCE_DAYS.get(16)))
    assert "duration" not in block
    assert block["coaching_cues"] == ["20min continuous"]

    block = _only_block(_session(_tempo_role(10), 10, SOURCE_DAYS.get(10)))
    assert block["duration"] == {"value": 25, "unit": "minutes"}


def test_no_plan_text_resolves_bank_bounds_to_one_value():
    block = _only_block(_session(_tempo_role(17), 17, None))
    assert block["coaching_cues"] == ["20min continuous"]
    assert not RANGE.search(" ".join(block["coaching_cues"]))


def test_whole_quantity_clauses_become_stats_and_the_rest_stays_verbatim():
    role = {
        "role_key": "neural_plus_strength_day",
        "category": "strength",
        "scheduled_d_day": 14,
        "selected_exercise_assignments": [
            {"name": "Punch-Specific Max Isometric Hold", "slot_id": "a"},
            {"name": "Trap Bar Deadlift", "slot_id": "b"},
        ],
        "effective_strength_prescriptions": [
            {"slot_id": "a", "effective_prescription": "3 holds x 10–20s @ 7–9/10 effort"},
            {"slot_id": "b", "effective_prescription": "3 x 3 @ 80% 1RM"},
        ],
    }
    session = _session(role, 14, SOURCE_DAYS.get(14))
    hold, deadlift = session["blocks"]

    assert hold["sets"] == 3
    assert hold["duration"] == {"value": 10, "unit": "seconds"}
    assert hold["rest"] == {"value": 180, "unit": "seconds"}
    assert hold["effort"] == {"method": "RPE", "value": 7, "scale": "1-10"}
    assert hold["coaching_cues"] == [
        "Cue: get into punch finish position and hold pressure without swinging."
    ]

    assert deadlift["rest"] == {"value": 180, "unit": "seconds"}
    assert deadlift["coaching_cues"][0] == "3 sets x 3 reps @ 80% 1RM (established max only)"
    assert deadlift["stop_rules"] == ["if bar speed slows or back position changes."]


def test_second_session_on_the_same_day_does_not_borrow_the_first_why():
    role = {
        "role_key": "transfer_strength_day",
        "category": "strength",
        "athlete_facing_label": "Strength",
        "scheduled_d_day": 15,
        "selected_exercise_assignments": [
            {"name": "Band-Resisted Jab-Cross Primer", "slot_id": "a",
             "base_prescription": "4–6x2–5 reps at max speed; full rest 60–120s."},
        ],
    }
    session = _session(role, 15, SOURCE_DAYS.get(15))
    block = _only_block(session)

    assert session["objective"] != "rest and technical work only."
    assert block["sets"] == 2 and block["reps"] == 2
    assert block["rest"] == {"value": 120, "unit": "seconds"}
    assert block["effort"] == {"method": "RPE", "value": 6, "scale": "1-10"}
    assert block["coaching_cues"][0] == "max speed"


def test_exact_working_dose_rule():
    # Workload and intensity take the lower bound; rest takes the upper bound.
    assert _exact_working_dose("4–6x2–5 reps at max speed; full rest 60–120s.") == (
        "4x2 reps at max speed; full rest 120s."
    )
    assert _exact_working_dose("3–5 holds x 10–20s @ 7–9/10 effort") == "3 holds x 10s @ 7/10 effort"
    assert _exact_working_dose("3-5 x 2 min, 60-90 sec rest, RPE 3-4") == "3 x 2 min, 90 sec rest, RPE 3"
    # Numbers that are not a dose are left as written.
    assert _exact_working_dose("Use D-21 to D-8 only") == "Use D-21 to D-8 only"
    assert _exact_working_dose("Band tension 20-30% BW") == "Band tension 20% BW"
