"""Easier labels are annotations, not newly selected exercises."""
import pytest

from fightcamp.stage2_validator import (
    _late_fight_allowed_exercise_warnings,
    _late_fight_line_is_exercise_like,
    _late_fight_progression_lockout_warnings,
    _late_camp_effective_prescription_warnings,
    _extract_plan_lines,
)

@pytest.mark.parametrize('line', [
    'Easier: reduce to 2 x 3 @ RPE 5.',
    '- Easier — drop one set of Trap Bar Deadlift.',
    '- **Easier:** reduce the punch volume to 2 rounds.',
    'Easier/Stop: remove the final set if speed drops.',
    'Regression: reduce to 2 x 3.',
])
def test_reduction_annotation_is_not_an_exercise(line):
    assert not _late_fight_line_is_exercise_like(line)

def test_easier_does_not_create_an_unapproved_exercise():
    spec = {'allowed_exercises_by_day': {'D-12': ['Trap Bar Deadlift']}}
    text = ('D-12 (Monday) — Strength\n'
            '- Trap Bar Deadlift — 2 x 3 @ RPE 6\n'
            '- Easier: reduce to 1 x 3 @ RPE 5.\n')
    assert _late_fight_allowed_exercise_warnings(spec, text, _extract_plan_lines(text)) == []

def test_easier_does_not_create_a_complete_allow_list_violation():
    brief = {'weekly_role_map': {'weeks': [{'session_roles': [{
        'role_key': 'primary_strength_day',
        'effective_strength_envelope': {
            'scheduled_d_day': 12,
            'complete_exercise_allow_list': True,
            'allowed_exercise_names': ['Trap Bar Deadlift'],
        },
    }]}]}}
    text = ('D-12 (Monday) — Strength\n'
            '- Trap Bar Deadlift — 2 x 3 @ RPE 6\n'
            '- Easier: reduce to 1 x 3 @ RPE 5.\n')
    assert _late_camp_effective_prescription_warnings(brief, text) == []

def test_actual_unapproved_exercise_still_blocks():
    spec = {'allowed_exercises_by_day': {'D-12': ['Trap Bar Deadlift']}}
    text = 'D-12 (Monday) — Strength\n- Sandbag Shouldering — 3 x 3\n'
    findings = _late_fight_allowed_exercise_warnings(spec, text, _extract_plan_lines(text))
    assert any(f['code'] == 'late_fight_unapproved_exercise_rendered' for f in findings)

@pytest.mark.parametrize('day,title', [(12, 'Strength'), (7, 'Freshness primer')])
def test_mislabeled_progression_still_blocks(day, title):
    text = (f'D-{day} (Monday) — {title}\n'
            '- Easier: to progress, add a set.\n')
    findings = _late_fight_progression_lockout_warnings({}, text, _extract_plan_lines(text))
    assert any(f['code'] == 'late_fight_progression_suggested' for f in findings)

def test_genuine_easier_regression_is_not_a_progression():
    text = ('D-7 (Monday) — Freshness primer\n'
            '- Easier: reduce to 2 rounds at RPE 4.\n')
    assert _late_fight_progression_lockout_warnings({}, text, _extract_plan_lines(text)) == []
