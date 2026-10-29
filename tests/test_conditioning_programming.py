"""Conditioning decisions through existing membership, dose and coaching owners."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from fightcamp.conditioning import (
    _alactic_structure_ok, _conditioning_development_requested, _conditioning_structured_profile,
    _resolve_conditioning_sessions, generate_conditioning_block, get_conditioning_bank,
)
from fightcamp.conditioning_boxing import conditioning_load_context
from fightcamp.config import conditioning_dose_active_work_seconds, conditioning_dose_minutes
from fightcamp.exercise_coaching import exercise_coaching
from fightcamp.exercise_progression import build_progression_context, occurrence_key
from fightcamp.goal_preservation import selected_goals
from fightcamp.planner_context import planner_athlete_model_context
from fightcamp.prescription_resolver import apply_effective_conditioning_prescriptions
from fightcamp.priority_profile import build_priority_profile
from fightcamp.session_composition import compose_normal_conditioning_assignments
from fightcamp.stage2_payload import _serialize_conditioning_option


BANK = {e['name']: e for e in json.loads(Path('data/conditioning_bank.json').read_text())}
CONTEXT = json.loads(Path('tests/fixtures/conditioning_741aa47d_context.json').read_text())


def _camp(*, contacts=(2, 0, 0), fatigue='low', phase='SPP', day=42, **athlete_changes):
    athlete = {'sport': 'boxing', 'fatigue': fatigue, 'key_goals': ['speed', 'conditioning'],
               'weaknesses': ['balance', 'gas_tank'], 'primary_goal': 'speed',
               'cut_severity_bucket': 'none', **athlete_changes}
    weeks = []
    for i, contact in enumerate(contacts):
        role = {'category': 'conditioning', 'role_key': 'fight_pace_repeatability_day',
                'preferred_system': 'glycolytic', 'session_index': 1,
                'scheduled_countdown_label': f'D-{day-7*i}',
                'selected_exercise_assignments': [{
                    'name': 'Air Bike Muscle Buffer Intervals', 'slot_id': 'buffer',
                    'slot_group': 'conditioning_slots', 'source_phase': phase,
                    'effective_prescription': '4x120s work, 180s rest',
                    'base_prescription': '4x120s work, 180s rest',
                    'rounds': 4, 'work_sec': 120, 'rest_sec': 180, 'rpe': 8,
                    'coaching_cues': BANK['Air Bike Muscle Buffer Intervals']['coaching_cues'],
                    'stop_rules': BANK['Air Bike Muscle Buffer Intervals']['stop_rules'],
                }],
                'conditioning_composition_policy': {
                    'conditioning_workload_met': True,
                    'conditioning_target_active_work_seconds': 480,
                    'conditioning_active_work_seconds': 480,
                }}
        weeks.append({'week_index': i+1, 'phase': phase,
                      'effective_hard_sparring_days': ['Tuesday', 'Saturday'][:contact],
                      'session_roles': [role]})
    return athlete, {'weeks': weeks}


def _members(role_map):
    return [w['session_roles'][0]['selected_exercise_assignments'][0] for w in role_map['weeks']]


def test_reduce_increase_maintain_are_real_authorised_doses_and_idempotent():
    athlete, roles = _camp()
    apply_effective_conditioning_prescriptions(weekly_role_map=roles, athlete_model=athlete)
    members = _members(roles)
    assert [m['rounds'] for m in members] == [3, 4, 4]
    assert [m['conditioning_decision']['action'] for m in members] == ['reduce', 'increase', 'maintain']
    assert [m['effective_prescription'] for m in members] == [
        '3x120s work, 180s rest', '4x120s work, 180s rest', '4x120s work, 180s rest']
    assert all(m['rest_sec'] == 180 and m['work_sec'] == 120 and m['rpe'] == 8 for m in members)
    before = deepcopy(roles)
    apply_effective_conditioning_prescriptions(weekly_role_map=roles, athlete_model=athlete)
    assert roles == before

    brief = {'athlete_snapshot': athlete, 'weekly_role_map': roles}
    contexts = build_progression_context(brief)
    role = roles['weeks'][0]['session_roles'][0]
    coaching = exercise_coaching(members[0], role, phase='SPP', d_day=42, athlete=athlete,
        progression_context=contexts[occurrence_key(role, members[0], 42)])
    # #2895: Progress/Easier notes belong to the final-session writer; the
    # deterministic card never manufactures an increment or a reduced dose.
    assert 'progression_rule' not in coaching
    assert coaching['regression_options'] == []
    assert contexts[occurrence_key(role, members[0], 42)]['next']['dose']['sets'] == 4
    assert roles == before  # Coaching cannot author a dose.


@pytest.mark.parametrize('changes', [
    {'fatigue': 'high'}, {'fatigue': 'moderate'}, {'injuries': ['knee pain']},
    {'injury_restrictions': ['no jumping']}, {'cut_severity_bucket': 'high'},
])
def test_recovery_pressure_reduces_without_changing_rest_or_effort(changes):
    athlete, roles = _camp(contacts=(0, 0), **changes)
    apply_effective_conditioning_prescriptions(weekly_role_map=roles, athlete_model=athlete)
    assert [m['rounds'] for m in _members(roles)] == [3, 3]
    assert [m['conditioning_decision']['action'] for m in _members(roles)] == ['reduce', 'maintain']


def test_unknown_boxing_intensity_or_fatigue_holds_a_reduced_dose():
    athlete, roles = _camp()
    roles['weeks'][1]['session_roles'].append({'coach_owned': True, 'role_key': 'light_combat_day'})
    apply_effective_conditioning_prescriptions(weekly_role_map=roles, athlete_model=athlete)
    assert [m['rounds'] for m in _members(roles)] == [3, 3, 3]
    assert roles['weeks'][1]['conditioning_load_context']['coach_conditioning_intensity'] == 'unknown'
    athlete, roles = _camp(fatigue='')
    apply_effective_conditioning_prescriptions(weekly_role_map=roles, athlete_model=athlete)
    assert [m['rounds'] for m in _members(roles)] == [3, 3, 3]


@pytest.mark.parametrize('phase,day', [('TAPER', 28), ('SPP', 14), ('SPP', 13), ('SPP', 5)])
def test_final_fortnight_and_taper_keep_countdown_dose_authority(phase, day):
    athlete, roles = _camp(contacts=(2,), phase=phase, day=day)
    apply_effective_conditioning_prescriptions(weekly_role_map=roles, athlete_model=athlete)
    assert _members(roles)[0]['rounds'] == 4
    assert _members(roles)[0]['conditioning_decision']['reason'] == 'countdown_or_support_dose'


def test_scheduled_member_phase_wins_when_a_week_straddles_taper():
    athlete, roles = _camp(contacts=(2,), phase='TAPER', day=15)
    roles['weeks'][0]['phase'] = 'SPP'
    apply_effective_conditioning_prescriptions(weekly_role_map=roles, athlete_model=athlete)
    assert _members(roles)[0]['rounds'] == 4
    assert _members(roles)[0]['conditioning_decision']['reason'] == 'countdown_or_support_dose'


def test_secondary_gas_tank_weakness_is_considered_and_merged_with_goal():
    athlete = {'key_goals': ['speed'], 'weaknesses': ['balance', 'gas_tank']}
    assert ('conditioning', 'secondary') in selected_goals(athlete)
    athlete['key_goals'].append('conditioning')
    assert selected_goals(athlete).count(('conditioning', 'secondary')) == 1
    profile = build_priority_profile(athlete)
    assert _conditioning_development_requested(profile)
    sessions = _resolve_conditioning_sessions({'glycolytic': [
        {'name': 'A', 'work_sec': 60, 'rounds': 4},
        {'name': 'B', 'work_sec': 60, 'rounds': 4},
    ]}, phase='SPP', num_sessions=1, workload_expansion_allowed=_conditioning_development_requested(profile))
    assert len(sessions) == 1
    assert len(sessions[0]['entries']) == 2


def test_effective_sparring_is_counted_once_and_empty_resolver_result_wins():
    athlete = CONTEXT['athlete_model']
    week = {'effective_hard_sparring_days': ['Tuesday', 'Tuesday', 'Saturday'], 'session_roles': [
        {'role_key': 'hard_sparring_day', 'category': 'combat'},
        {'role_key': 'hard_sparring_day', 'category': 'combat'},
        {'role_key': 'light_combat_day', 'coach_owned': True},
    ]}
    evidence = conditioning_load_context(athlete, week)
    assert evidence['hard_exposures'] == 2
    assert evidence['additional_hard_conditioning'] == 'defer'
    assert evidence['coach_conditioning_intensity'] == 'unknown'
    week['effective_hard_sparring_days'] = []
    assert conditioning_load_context(athlete, week)['hard_exposures'] == 0


def test_free_text_session_estimates_do_not_change_load_evidence_or_doses():
    athlete, roles = _camp()
    expected = deepcopy(roles)
    apply_effective_conditioning_prescriptions(weekly_role_map=expected, athlete_model=athlete)
    athlete['training_workload_context'] = {'reported_weekly_sessions': {'minimum': 8, 'maximum': 9}}
    apply_effective_conditioning_prescriptions(weekly_role_map=roles, athlete_model=athlete)
    assert roles == expected


@pytest.mark.parametrize('name', ['Air Bike Aerobic HIIT', 'Air Bike Sprint Interval Training', 'Air Bike Muscle Buffer Intervals'])
def test_complete_protocols_are_not_padded_to_generic_phase_workload(name):
    drill = BANK[name]
    system = drill['system']
    slot = {'slot_id': 'protocol', 'role': system,
            'selected': _serialize_conditioning_option(drill, system, '')}
    phase = drill['phases'][0]
    roles = {'weeks': [{'phase': phase, 'session_roles': [
        {'category': 'conditioning', 'preferred_system': system, 'role_key': 'conditioning_day'}]}]}
    token = planner_athlete_model_context.set({'sport': 'boxing', 'rounds_format': '10 x 3'})
    try:
        compose_normal_conditioning_assignments(weekly_role_map=roles,
            candidate_pools={phase: {'conditioning_slots': [slot, deepcopy(slot)]}})
    finally:
        planner_athlete_model_context.reset(token)
    role = roles['weeks'][0]['session_roles'][0]
    assert len(role['selected_exercise_assignments']) == 1
    assert role['conditioning_composition_policy']['conditioning_workload_met']
    assert role['selected_exercise_assignments'][0]['work_sec'] == drill['work_sec']


def test_bank_classification_safety_and_identity_preservation():
    hill = BANK['Hill Sprint Repeats']
    assert (hill['system'], hill['work_sec'], hill['rest_sec'], hill['rounds']) == ('ATP-PCr', 8, 120, 8)
    assert hill['impact_cost'] == 'high' and hill['movement_cost'] == 'high'
    rower = BANK['Concept2 Rower Zone 3 Block']
    assert (rower['system'], rower['rpe'], rower['rest_sec']) == ('aerobic', 7, 120)
    eligible = {e['name'] for e in get_conditioning_bank()}
    assert not {'Breath-Hold Shadowboxing Intervals', 'Heat Acclimation Rounds'} & eligible
    assert BANK['Reaction Ball Drills']['support_only']
    assert BANK['Neck Harness Flexion/Extension']['placement'] == 'strength'


@pytest.mark.parametrize('name', ['Broad Jump Repeats (ATP-PCr)', 'Sled Sprint (Empty)', 'Neck Harness Flexion/Extension'])
def test_reps_and_metres_never_count_as_seconds(name):
    # Some display names have been standardised; bank identity stays unchanged.
    drill = BANK.get(name) or BANK[name.replace(' (ATP-PCr)', '')]
    assert conditioning_dose_active_work_seconds(drill) is None
    assert conditioning_dose_minutes(drill) is None
    assert not _conditioning_structured_profile(drill)['alactic_structure']


def test_elapsed_recovery_does_not_become_active_work_or_sustained_density():
    dose = {'duration': '4x30s work, 240s rest', 'work_sec': 30, 'rest_sec': 240,
            'rounds': 4, 'total_minutes': 14, 'rpe': 8, 'lactate_load': 'moderate'}
    assert conditioning_dose_minutes(dose) == 14
    assert conditioning_dose_active_work_seconds(dose) == 120
    assert not _conditioning_structured_profile(dose)['glycolytic_density']
    assert conditioning_dose_active_work_seconds({'duration': '3x4min, 2min recovery', 'total_minutes': 16}) is None
    assert all(e.get('rest_sec') is None for e in BANK.values() if 'continuous' in e.get('duration', '').lower())


def test_actual_741aa47d_prescriptions_respect_load_without_adding_intervals():
    saved = json.loads(Path('tests/fixtures/measurable_coaching/affected_programmes.json').read_text())[0]
    assert saved['plan_id'] == '741aa47d-23fb-43d9-964a-b8e06b93a48a'
    roles = deepcopy(saved['brief']['weekly_role_map'])
    doses = json.loads(Path('tests/fixtures/conditioning_741aa47d_doses.json').read_text())
    for week in roles['weeks']:
        # Original contact resolver results: hard until the final fortnight.
        week['effective_hard_sparring_days'] = ['Tuesday', 'Saturday'] if week['week_index'] <= 5 else []
        for role in week['session_roles']:
            for member in role.get('selected_exercise_assignments') or []:
                facts = doses.get(member.get('slot_id'))
                if facts is not None:
                    member.update({k: v for k, v in facts.items() if k not in {'preferred_system', 'late_fight_tail_owned'}})
                    role['preferred_system'] = facts.get('preferred_system')
                    role['late_fight_tail_owned'] = facts.get('late_fight_tail_owned')
    before = deepcopy(roles)
    athlete = CONTEXT['athlete_model']
    apply_effective_conditioning_prescriptions(weekly_role_map=roles, athlete_model=athlete)
    changes = []
    for old_week, week in zip(before['weeks'], roles['weeks']):
        assert len(old_week['session_roles']) == len(week['session_roles'])
        for old_role, role in zip(old_week['session_roles'], week['session_roles']):
            assert old_role['scheduled_countdown_label'] == role['scheduled_countdown_label']
            for old, member in zip(old_role.get('selected_exercise_assignments') or [], role.get('selected_exercise_assignments') or []):
                assert old['name'] == member['name']
                if old.get('effective_prescription') != member.get('effective_prescription'):
                    changes.append((old['name'], old['effective_prescription'], member['effective_prescription']))
    assert changes == [('Max-Power Bag Burst', '5s work, 60s rest x 8 rounds', '5s work, 60s rest x 7 rounds')]
    assert all(w['conditioning_load_context']['additional_hard_conditioning'] == 'defer' for w in roles['weeks'][:5])


@pytest.mark.parametrize('text,work,rest', [
    ('4x30s work, 180s rest', 120, 180),  # Numeric work disagrees with prose.
    ('4x120s work, 60s rest', 120, 180),  # Numeric recovery disagrees with prose.
    ('4x3 reps, 180s rest', 3, 180),
    ('4x20m, 180s rest', 20, 180),
])
def test_ambiguous_units_or_disagreeing_metadata_cannot_authorise_advancement(text, work, rest):
    athlete, roles = _camp(contacts=(2, 0))
    for member in _members(roles):
        member.update(effective_prescription=text, work_sec=work, rest_sec=rest)
    apply_effective_conditioning_prescriptions(weekly_role_map=roles, athlete_model=athlete)
    assert all(m['effective_prescription'] == text for m in _members(roles))
    assert all(m['conditioning_decision']['action'] == 'maintain' for m in _members(roles))


@pytest.mark.parametrize('changes', [
    {'key_goals': ['conditioning'], 'primary_goal': 'conditioning'},
    {'key_goals': ['speed'], 'weaknesses': ['gas_tank'], 'primary_weak_area': 'gas_tank'},
    {'status': 'amateur', 'training_frequency': 3, 'rounds_format': '3 x 3'},
    {'status': 'professional', 'training_frequency': 9, 'rounds_format': '10 x 3', 'hard_sparring_days': ['Tuesday', 'Saturday']},
    {'days_until_fight': 18, 'phase': 'SPP'},
    {'fatigue': 'high', 'injuries': ['knee pain'], 'restrictions': [{'restriction': 'high_impact_lower', 'strength': 'avoid'}]},
    {'fatigue': 'low', 'hard_sparring_days': ['Tuesday', 'Thursday', 'Saturday']},
    {'days_until_fight': 12, 'phase': 'TAPER'},
    {'days_until_fight': 5, 'phase': 'TAPER'},
    {'fatigue': '', 'support_work_days': ['Thursday', 'Friday']},
])
def test_real_bank_scenarios_do_not_automatically_earn_complete_hard_protocols(changes):
    flags = {**CONTEXT['athlete_model'], 'phase': 'GPP', 'fatigue': 'low',
             'style_technical': ['boxing'], 'style_tactical': ['pressure_fighter'],
             'hard_sparring_days': [], 'days_until_fight': 52, **changes}
    result = generate_conditioning_block(flags)
    selected = [d for group in result[3].values() for d in group]
    hard = [d for d in selected if d.get('standalone_protocol')]
    if (flags['fatigue'] != 'low' or len(flags['hard_sparring_days']) >= 2
            or flags['days_until_fight'] <= 14):
        assert hard == []
    assert not {'Heat Acclimation Rounds', 'Breath-Hold Shadowboxing Intervals'} & {d['name'] for d in selected}
    assert all(not d.get('round_based') for d in hard)  # HIIT/SIT never inherit a fight-round length.


def test_fixed_coach_conditioning_is_immutable_and_bout_demand_does_not_add_sessions():
    from fightcamp.conditioning import _effective_system_demand
    athlete, roles = _camp(contacts=(2,))
    role = roles['weeks'][0]['session_roles'][0]
    role['coach_owned'] = True
    before = deepcopy(role)
    apply_effective_conditioning_prescriptions(weekly_role_map=roles, athlete_model=athlete)
    assert role == before
    _, amateur = _effective_system_demand(phase='GPP', sport='boxing', rounds_format='3 x 3')
    _, pro = _effective_system_demand(phase='GPP', sport='boxing', rounds_format='10 x 3')
    assert pro['effective_workload_targets_seconds']['aerobic'] > amateur['effective_workload_targets_seconds']['aerobic']


def test_rep_based_alactic_membership_keeps_its_own_dose_without_a_seconds_floor():
    drill = BANK['Box Jump (Max Height)']
    assert _alactic_structure_ok(drill)  # Rep units must not evict valid speed work.
    slot = {'slot_id': 'jump', 'role': 'alactic', 'selected': _serialize_conditioning_option(drill, 'alactic', '')}
    roles = {'weeks': [{'phase': 'GPP', 'session_roles': [
        {'category': 'conditioning', 'preferred_system': 'alactic', 'role_key': 'alactic_coordination_day'}]}]}
    compose_normal_conditioning_assignments(weekly_role_map=roles,
        candidate_pools={'GPP': {'conditioning_slots': [slot, deepcopy(slot)]}})
    role = roles['weeks'][0]['session_roles'][0]
    assert len(role['selected_exercise_assignments']) == 1
    assert 'reps' in role['selected_exercise_assignments'][0]['effective_prescription']
    assert role['conditioning_composition_policy']['conditioning_active_work_seconds'] == 0
    assert role['conditioning_composition_policy']['conditioning_workload_met'] is None
    assert role['conditioning_composition_policy']['underfill_reason'] is None
