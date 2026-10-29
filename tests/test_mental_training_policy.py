"""Mental frequency caps operate on the final calendar, never physical work."""
from collections import Counter
from copy import deepcopy

import pytest

from fightcamp.mental_training_policy import govern_mental_roles, mental_prep_prioritised
from fightcamp.physical_session_frequency import is_physical_session_role


def role(day, key, **extra):
    return dict(role_key=key, countdown_offset=day, category='mental', **extra)


def govern(roles, priority=False, contacts=()):
    removed = govern_mental_roles(
        roles, {'mental_prep_priority': priority},
        offset_of=lambda r: r['countdown_offset'],
        bucket_of=lambda r, d: (d - 1) // 7,
        contact_offsets=contacts,
        relocate=lambda r, d: r.update(countdown_offset=d),
    )
    return [r for r in roles if id(r) not in removed]


@pytest.mark.parametrize('priority,limit,spacing', [(False, 1, 14), (True, 2, 7)])
def test_limits_across_all_proposed_roles_and_tail(priority, limit, spacing):
    physical = [dict(role_key='primary_strength_day', category='strength', countdown_offset=d) for d in range(7, 50)]
    candidates = [role(d, key, late_fight_tail_owned=d < 14, optional_fight_visualization=True)
                  for d in range(7, 50)
                  for key in ['fight_visualization', 'neural_visualization', 'tactical_watch', 'tactical_cue_card', 'self_review']]
    before = deepcopy(physical)
    kept = govern(physical + candidates, priority, contacts=range(7, 50, 7))
    assert [r for r in kept if is_physical_session_role(r)] == before
    mental = [r for r in kept if r['role_key'] != 'primary_strength_day']
    assert max(Counter(r['countdown_offset'] for r in mental).values()) == 1
    visual = [r for r in mental if r['mental_category'] == 'visualise']
    assert all(n <= limit for n in Counter((r['countdown_offset'] - 1) // 7 for r in visual).values())
    analyse = sorted(r['countdown_offset'] for r in mental if r['mental_category'] == 'analyse')
    assert all(b-a >= spacing for a,b in zip(analyse, analyse[1:]))
    reflect = [r for r in mental if r['mental_category'] == 'reflect']
    assert all(r['countdown_offset'] in range(7, 50, 7) for r in reflect)
    assert all(n <= 1 for n in Counter((r['countdown_offset']-1)//7 for r in reflect).values())
    assert govern(kept, priority, contacts=range(7, 50, 7)) == kept


def test_passive_resets_and_fixed_countdown_cannot_create_training_days():
    roles = [role(7, 'fight_visualization', late_fight_tail_owned=True),
             role(1, 'fight_visualization'), role(0, 'fight_visualization'),
             role(14, 'neural_visualization'), role(14, 'breathing_reset')]
    assert [r['role_key'] for r in govern(roles)] == ['breathing_reset']


@pytest.mark.parametrize('priority,maximum', [(False,1),(True,2)])
def test_fight_week_is_brief_familiar_and_attached(priority, maximum):
    roles = [dict(role_key='technical_day', category='combat', countdown_offset=d) for d in [1,3,5]]
    roles += [role(d,'fight_visualization', prescribed_duration_min=8, duration_min=[5,8],
                   fight_visualization={'prescribed_duration_min':8,'duration_min':[5,8]},
                   display_text='Fight Visualisation — 8 min. Follow your familiar cue.') for d in [0,1,3,5]]
    roles += [role(3,'tactical_watch'),role(1,'self_review')]
    kept = govern(roles,priority,contacts=[1,3,5])
    mental = [r for r in kept if r['role_key']=='fight_visualization']
    assert 0 < len(mental) <= maximum
    assert all(r['countdown_offset'] in [1,3] for r in mental)
    assert all(r['prescribed_duration_min'] <= 3 and r['fight_visualization']['duration_min']==[3,3] for r in mental)
    assert all('3 min' in r['display_text'] for r in mental)
    assert not any(r['role_key'] in ['self_review','tactical_watch'] for r in kept)


def test_explicit_priority_only_and_all_mental_identities_are_nonphysical():
    assert not mental_prep_prioritised({'mindset':'I want to be confident'})
    assert mental_prep_prioritised({'key_goals':['mental preparation']})
    for key in ['fight_visualization','neural_visualization','self_review','tactical_watch','tactical_cue_card']:
        assert not is_physical_session_role({'role_key':key,'category':'strength'})


def test_empty_and_d0_only_gap_fill_cannot_restore_countdown_tasks():
    from fightcamp.gap_fill_inserts import apply_gap_fill_inserts
    for days, sequence in [(0, []), (6, []), (None, [role(0, "fight_visualization")])]:
        kept = apply_gap_fill_inserts(sequence, {"sport": "boxing", "days_until_fight": days})
        assert not any(r.get("role_key") == "fight_visualization" for r in kept)


def test_calendar_week_cap_spans_phase_rows():
    from fightcamp.camp_week_fillers_impl import govern_weekly_mental_training
    weeks = []
    for day, weekday, phase in [(12, 'monday', 'SPP'), (10, 'wednesday', 'TAPER')]:
        weeks.append({'phase': phase, 'calendar_days': [{'d_day': day, 'weekday': weekday}],
                      'session_roles': [
                          dict(role_key='primary_strength_day', category='strength', countdown_offset=day),
                          role(day, 'fight_visualization', optional_fight_visualization=True),
                      ]})
    model = {'fight_date': '2026-12-05'}  # Both rows fall in the same Monday-based week.
    govern_weekly_mental_training({'weeks': weeks}, model)
    assert sum(r['role_key'] == 'fight_visualization' for w in weeks for r in w['session_roles']) == 1
    assert sum(r['role_key'] == 'primary_strength_day' for w in weeks for r in w['session_roles']) == 2


def test_removal_persists_in_a_wrapped_authoritative_sequence():
    # Late-fight briefs govern a temporary week that wraps the brief's own
    # late_fight_session_sequence; a removed card must leave that list too.
    from fightcamp.camp_week_fillers_impl import govern_weekly_mental_training
    sequence = [item for day in (12, 10) for item in (
        dict(role_key='primary_strength_day', category='strength', countdown_offset=day),
        role(day, 'fight_visualization', optional_fight_visualization=True))]
    week = {'calendar_days': [{'d_day': 12, 'weekday': 'monday'}, {'d_day': 10, 'weekday': 'wednesday'}],
            'session_roles': sequence}
    govern_weekly_mental_training({'weeks': [week]}, {'fight_date': '2026-12-05'})
    assert week['session_roles'] is sequence
    assert sum(r['role_key'] == 'fight_visualization' for r in sequence) == 1
    assert sum(r['role_key'] == 'primary_strength_day' for r in sequence) == 2
