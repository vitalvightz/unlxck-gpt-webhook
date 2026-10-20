"""Final-session text written flush-left (plan 403223f8, 2026-10-20).

The AI wrote Cue/Progress/Easier/Stop lines unindented under each exercise and
"Progress: none this block." everywhere. That must not lose the cues, must not
show a "none" Progress, must not repeat the dose as "How", and a week heading
must never become a day's session content.
"""
from api.structured_plan_deterministic_fallback import _lift_dose_fields, _source_block
from api.structured_plan_faithfulness import _source_day_section_lines, project_source_adjustments
from fightcamp.coaching_copy import is_null_progression
from fightcamp.exercise_coaching_source import source_coaching

TEXT = """## Week 1 — GPP (D-21 → D-20)

### D-20 (Sunday) — Strength
- Step-Back Pivot Reset — 2 x 75 sec technical sets, 60 sec reset | 60 sec between sets | low; RPE 5
Cue: Step back, pivot, reset guard.
Progress: none this block.
Stop: stop if sharp hip or ankle pain.
- Romanian Deadlift (DB) — 2x6 @ RPE 6, keep reps crisp.
Cue: Hinge, feel hamstrings, keep chest up.
Progress: none this block.
Easier: reduce range of motion or load.
Stop: stop for sharp low-back pain.

### D-13 (Sunday) — Neural speed touch
- Pull-Counter-Reset — 1x5s with 120s rest
Cue: Pull, return, reset guard.
Progress: none this block.
Stop: stop if shoulder or neck pain.
  How: Draw one attack, take a small pull off the end of it, return once, then restore stance.

### D-11 (Tuesday) — Rhythm flush
- Tempo Shadowboxing — 30min continuous
Cue: Smooth movement, light punches.
Progress: none this block.
Stop: stop if breathing becomes erratic.

### D-6 (Sunday) — Fight-week freshness
- Easy mobility, breathing, and tissue work. Keep it fully restorative.

## Week 4 — TAPER (D-5 → D-0)

Focus: Protect rhythm, confidence, and freshness.
"""


def _day(n):
    return _source_day_section_lines(TEXT)[n]


def test_flush_left_labels_belong_to_their_exercise():
    block = _source_block(_day(20), "Step-Back Pivot Reset")
    assert block["coaching_cues"] == ["Cue: Step back, pivot, reset guard."]
    assert block["stop_rules"] == ["stop if sharp hip or ankle pain."]
    assert block["progression_rule"] is None  # "none this block" is no rule.
    rdl = _source_block(_day(20), "Romanian Deadlift (DB)")
    assert rdl["regression_options"] == ["reduce range of motion or load."]


def test_dose_shown_as_stats_is_not_repeated_as_how():
    step = _source_block(_day(20), "Step-Back Pivot Reset")
    assert step["sets"] == 2 and step["duration"] == {"value": 75, "unit": "seconds"}
    assert step["execution_instructions"] is None
    drill = _source_block(_day(13), "Pull-Counter-Reset")
    assert drill["execution_instructions"].startswith("Draw one attack")


def test_continuous_duration_becomes_a_stat():
    block = _source_block(_day(11), "Tempo Shadowboxing")
    assert block["duration"] == {"value": 30, "unit": "minutes"}
    assert block["coaching_cues"] == ["Cue: Smooth movement, light punches."]
    fields, _ = _lift_dose_fields("6 minutes, RPE 4 max.")
    assert fields["duration"] == {"value": 6, "unit": "minutes"} and fields["effort"]["value"] == 4
    assert "duration" not in _lift_dose_fields("20 min rest walk")[0]


def test_week_heading_never_joins_the_previous_day():
    assert not any("Week 4" in line or "Focus:" in line for line in _day(6))


def test_null_progress_is_absent_in_source_coaching():
    assert is_null_progression("Progress: none this block.")
    assert is_null_progression("None")
    assert not is_null_progression("Add 1 rep per set next time.")
    assert all("progression_rule" not in item["fields"] for item in source_coaching(TEXT).values())


def test_converted_adjustments_are_projected_from_source():
    plan = {"weeks": [{"days": [{"countdown_label": "D-20", "sessions": [{"title": "Strength", "blocks": [
        {"block_type": "strength", "display_name": "Romanian Deadlift (DB)",
         "progression_rule": "None this block", "regression_options": ["Lighter dumbbells."]},
    ]}]}]}]}
    block = project_source_adjustments(plan, TEXT)["weeks"][0]["days"][0]["sessions"][0]["blocks"][0]
    assert "progression_rule" not in block
    assert block["regression_options"] == ["reduce range of motion or load."]


def test_coaching_words_in_a_dose_survive_once_its_numbers_are_stats():
    from api.structured_plan_deterministic_fallback import _preserve_unrepresented_dose
    assert _preserve_unrepresented_dose("2x6 @ RPE 6, keep reps crisp.", None) == "keep reps crisp"
    assert _preserve_unrepresented_dose("3 carries over 20 m, heavy but unbroken; rest 90s.", None) == "heavy but unbroken"
    assert _preserve_unrepresented_dose("3 x 2 at max speed; rest 120s", None) == "max speed"
    assert _preserve_unrepresented_dose("6 x 20 sec work", None) is None
    rdl = _source_block(_day(20), "Romanian Deadlift (DB)")
    assert rdl["sets"] == 2 and rdl["reps"] == 6
    assert rdl["execution_instructions"] == "keep reps crisp"
