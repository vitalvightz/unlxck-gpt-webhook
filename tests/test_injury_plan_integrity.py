"""Symptom/impact regressions shared by camp and renewable programming."""
import copy

import pytest

from api.structured_plan_safety import audit_structured_plan, split_findings
from fightcamp.input_parsing import _build_guided_injury, _parse_guided_injury
from fightcamp.stage2_role_map import _active_injury_is_moderate_plus, _make_compression_suppression
from fightcamp.stage2_payload import _build_rehab_slots
from fightcamp.goal_preservation import validate_goal_preservation


@pytest.mark.parametrize('area', ['Left knee', 'Right shoulder', 'Left ankle', 'Right wrist'])
@pytest.mark.parametrize('impact,severity,compressed', [
    ('not_limiting', 'low', False), ('limiting', 'moderate', True),
    ('cant_train', 'high', True), ('unknown', '', False), ('', 'low', False),
])
def test_impact_survives_shared_intake_and_only_evidenced_limitation_compresses(area, impact, severity, compressed):
    notes = f'Original occasional symptom [training_impact:{impact}]' if impact else 'Original occasional symptom'
    injuries, _ = _parse_guided_injury(_build_guided_injury({
        'area': area, 'injury_type': 'pain', 'severity': severity, 'trend': 'stable', 'notes': notes,
    }))
    assert injuries[0].get('training_impact', '') == ('' if impact == 'unknown' else impact)
    assert 'Original occasional symptom' in injuries[0]['notes']
    model = {'injuries': ['occasional symptom'], 'parsed_injuries': injuries, 'readiness_flags': ['injury_management']}
    assert _active_injury_is_moderate_plus(model) is compressed


def test_multiple_injuries_and_independent_safety_evidence():
    model = {'parsed_injuries': [{'severity': 'low'}, {'severity': 'high', 'training_impact': 'cant_train'}]}
    assert _active_injury_is_moderate_plus(model)
    assert _active_injury_is_moderate_plus({'readiness_flags': ['red_flag_injury']})
    assert _active_injury_is_moderate_plus({'parsed_injuries': [
        {'training_impact': 'not_limiting', 'severity': 'high', 'medical_hold': True}]})


@pytest.mark.parametrize('area', ['Knee', 'Shoulder', 'Ankle'])
def test_legacy_guidance_never_becomes_rehab_membership(area):
    block = f'- {area} (pain):\n  - {area} pain activity guidance – Follow clinician advice.\n  - Heel slide – 2 x 5\n  - Heel slide – 2 x 5'
    slots = _build_rehab_slots(block, 'GPP')
    assert len(slots) == 1
    assert slots[0]['selected']['name'] == 'Heel slide'
    assert not any('activity guidance' in str(s['selected']) for s in slots)


@pytest.mark.parametrize('plan_type', ['fight_camp', 'open_ongoing'])
def test_guidance_exercise_is_blocking_even_if_it_has_reps(plan_type):
    plan = {'plan_type': plan_type, 'weeks': [{'days': [{'sessions': [{'blocks': [
        {'display_name': 'Shoulder pain activity guidance', 'sets': 2, 'reps': 10}]}]}]}]}
    blocking, _ = split_findings(audit_structured_plan(plan))
    assert any('medical guidance presented as exercise' in issue for issue in blocking)


def test_suppression_preserves_all_causes():
    reasons = ['high_fatigue', 'two_hard_spar_days', 'injury_management']
    result = _make_compression_suppression({'role_key': 'strength_primary'}, reasons, 'Protect recovery')
    assert result['reason_codes'] == reasons
    assert result['compression_reason_codes'] == reasons


def test_open_goal_coverage_cannot_silently_bypass_validation():
    brief = {'payload_variant': 'open_ongoing_stage2_payload',
             'athlete_model': {'key_goals': ['strength'], 'primary_goal': 'strength'},
             'open_plan_spec': {'goal_coverage': []}}
    assert validate_goal_preservation(brief)
    brief['open_plan_spec']['goal_coverage'] = [
        {'goal': 'strength', 'state': 'defer', 'satisfied': True, 'constraints': []}]
    assert validate_goal_preservation(brief)

@pytest.mark.parametrize('open_build', [True, False])
@pytest.mark.parametrize('symptom', ['Sometimes my left knee hurts', 'Sometimes my right shoulder hurts'])
def test_original_symptom_keeps_safe_development_work(open_build, symptom, monkeypatch):
    from datetime import datetime
    from api.models import PlanRequest
    from fightcamp.main import generate_plan_sync
    from planner_clock import pin_planner_clock
    from test_late_primer_e2e_vito_b import _VITO_B

    pin_planner_clock(monkeypatch, datetime(2026, 10, 13, 10))
    intake = copy.deepcopy(_VITO_B)
    intake.update(injuries=symptom, guided_injury=None, guided_injuries=[],
                  key_goals=['strength', 'power', 'conditioning'], primary_goal='strength',
                  # Leave two appointments for app-owned work. Four coached sessions
                  # consume the four-total-session budget; that exact intake is
                  # covered as an honest capacity deferral in the replay suite.
                  hard_sparring_days=['Wednesday', 'Sunday'], support_work_days=[],
                  training_availability=['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Sunday'],
                  weekly_training_frequency=4)
    intake['athlete']['technical_style'] = ['boxing']
    intake.update(weak_areas=['footwork'], primary_weak_area='footwork', goal_weakness_collision_tags=[],
                  equipment_access=['dumbbells', 'kettlebell', 'barbell', 'plate', 'bench', 'pullup_bar', 'bands', 'heavy_bag', 'pads', 'jump_rope', 'foam_roller', 'towel'])
    intake['fight_date'] = '2027-01-10'
    if open_build:
        intake.update(fight_date='', no_scheduled_fight=True)
    payload = PlanRequest(**intake).to_payload()
    payload['random_seed'] = 7
    result = generate_plan_sync(payload)
    brief = result['planning_brief']
    athlete = brief.get('athlete_snapshot') or brief.get('athlete_model') or {}
    assert athlete['triage_summary']['mode'] == 'full_plan'
    if open_build:
        sessions = [session for week in brief['open_plan_spec']['weekly_session_plan']['weeks'] for session in week['sessions']]
    else:
        sessions = [role for week in brief['weekly_role_map']['weeks'] for role in week['session_roles']]
    assert any(s['category'] == 'strength' for s in sessions)
    assert any(s['category'] == 'conditioning' for s in sessions)
    # Unrelated unmet goals must remain visible to validation; never fill the
    # plan or waive safety just to obtain a green release.
    failures = validate_goal_preservation(brief)
    assert not [f for f in failures if f.get('goal') == 'strength']
    assert all(f.get('severity') == 'blocker' for f in failures)


def test_explicit_restriction_survives_non_limiting_report():
    import logging
    from fightcamp.input_parsing import PlanInput
    from fightcamp.plan_pipeline_runtime import build_runtime_context
    payload = {'data': {'fields': []}, 'guided_injuries': [{'area': 'Left shoulder', 'injury_type': 'pain',
                'severity': 'low', 'trend': 'stable', 'avoid': 'overhead pressing',
                'notes': 'Clinician says avoid overhead pressing [training_impact:not_limiting]'}]}
    parsed = PlanInput.from_payload(payload)
    context = build_runtime_context(plan_input=parsed, random_seed=7,
                                    logger=logging.getLogger(__name__), triage_summary={'mode': 'full_plan'})
    assert context.training_context.injury_restrictions
    assert context.training_context.parsed_injuries
    assert context.training_context.guided_injuries


@pytest.mark.parametrize('location', ['knee', 'hip'])
def test_reviewed_advice_is_preserved_once_as_information(location, monkeypatch):
    from fightcamp.rehab_protocols import _reviewed_episode_option
    from api.contracts import injury_policy
    warning = 'Stop if symptoms worsen.'
    monkeypatch.setattr(injury_policy, 'resolve_injury_policy', lambda *args, **kwargs: {
        'prescription': {'dose': {}, 'instructions': f'Comfortable movement only. {warning}',
                         'stop_when': [warning, warning],
                         'drill': {'name': f'{location.title()} pain activity guidance'}}})
    option = _reviewed_episode_option({'injury_type': 'pain', 'severity': 'low'}, location, 'GPP')
    assert option['line'] is None and option['drill'] is None
    assert option['decision']['summary'].count(warning) == 1


def test_real_movement_keeps_necessary_assessment_stop_rule():
    from fightcamp.rehab_protocols import is_rehab_guidance_name
    assert not is_rehab_guidance_name('Heel slide – 2 x 5. Stop and seek assessment if symptoms worsen.')


def test_open_conversion_cannot_drop_selected_safe_work():
    from api.structured_plan_generation import planner_sc_coverage_losses
    brief = {'open_plan_spec': {'weekly_session_plan': {
        'authority': 'deterministic_open_development_block', 'weeks': [
            {'week': 1, 'sessions': [{'weekday': 'Monday', 'exercises': [{'name': 'Floor Press'}]}]}]}}}
    plan = {'weeks': [{'week_index': 1, 'days': [{'weekday': 'Mon', 'sessions': []}]}]}
    assert planner_sc_coverage_losses(plan, brief, 'Floor Press')
    plan['weeks'][0]['days'][0]['sessions'] = [{'blocks': [{'display_name': 'Floor Press'}]}]
    assert not planner_sc_coverage_losses(plan, brief, 'Floor Press')


@pytest.mark.parametrize('impact', ['not_limiting', 'limiting', 'cant_train'])
def test_quick_build_raw_impact_reaches_canonical_injuries(impact):
    from api.models import PlanRequest
    from fightcamp.input_parsing import PlanInput
    request = PlanRequest(athlete={'full_name': 'Regression', 'technical_style': ['boxing']}, injuries=f'Sometimes my left knee hurts [training_impact:{impact}]')
    parsed = PlanInput.from_payload(request.to_payload())
    assert parsed.parsed_injuries[0]['training_impact'] == impact
    assert parsed.parsed_injuries[0]['severity'] == {'not_limiting': 'low', 'limiting': 'moderate', 'cant_train': 'high'}[impact]
    assert 'training_impact' not in parsed.parsed_injuries[0]['original_phrase']


def test_quick_build_impact_cannot_soften_medical_severity():
    from api.models import PlanRequest
    from fightcamp.input_parsing import PlanInput
    for impact in ['not_limiting', 'limiting']:
        request = PlanRequest(athlete={'full_name': 'Regression', 'technical_style': ['boxing']},
                              injuries=f'Fractured left knee [training_impact:{impact}]')
        parsed = PlanInput.from_payload(request.to_payload())
        assert parsed.parsed_injuries[0]['severity'] == 'high'


def _open_contract_projection(block):
    from fightcamp.stage2_payload import _project_open_goal_coverage, _project_open_development_block
    return {'payload_variant': 'open_ongoing_stage2_payload',
            'athlete_snapshot': block['athlete_snapshot'], 'priority_focus': block['priority_focus'],
            'open_plan_spec': {'goal_coverage': _project_open_goal_coverage(block),
                               'weekly_session_plan': _project_open_development_block(block)}}


def _secondary_deferral_block():
    from test_goal_preservation import _brief, _role, _slot, _resolve
    block = _brief(days=20, roles=[_role(18)],
                   slots=[_slot('Medicine Ball Rotational Slam', 'anchor_power')])
    block['weekly_role_map']['weeks'][0]['suppressed_roles'] = [{
        'category': 'strength', 'role_key': 'primary_strength_day',
        'compression_reason_codes': ['high_fatigue']}]
    return _resolve(block)


def test_open_allows_canonically_justified_unsatisfied_secondary_deferral():
    block = _secondary_deferral_block()
    secondary = next(e for e in block['goal_preservation'] if e['goal'] == 'strength')
    assert secondary['state'] == 'defer' and secondary['satisfied'] is False
    assert validate_goal_preservation(block) == []
    assert validate_goal_preservation(_open_contract_projection(block)) == []


def test_open_rejects_deferral_after_its_causal_restriction_disappears():
    block = _secondary_deferral_block()
    block['weekly_role_map']['weeks'][0]['suppressed_roles'] = []
    errors = validate_goal_preservation(_open_contract_projection(block))
    assert any(error['goal'] == 'strength' for error in errors)


def test_open_rejects_unjustified_primary_loss_through_canonical_contract():
    block = _secondary_deferral_block()
    block['weekly_role_map']['weeks'][0]['session_roles'][0]['selected_exercise_assignments'] = []
    assert any(error['goal'] == 'speed' for error in validate_goal_preservation(_open_contract_projection(block)))


@pytest.mark.parametrize('change', ['missing_evidence', 'invalid_state', 'missing_contract', 'unsatisfied', 'invalid_evidence'])
def test_open_rejects_invalid_active_goal_projection(change):
    projected = _open_contract_projection(_secondary_deferral_block())
    primary = next(row for row in projected['open_plan_spec']['goal_coverage'] if row['goal'] == 'speed')
    if change == 'missing_evidence':
        primary['evidence'] = []
    elif change == 'invalid_state':
        primary['state'] = 'optional'
    elif change == 'missing_contract':
        primary.pop('contract_errors')
    elif change == 'invalid_evidence':
        primary['evidence'][0]['name'] = 'Unassigned exercise'
    else:
        primary['satisfied'] = False
    assert any(error['goal'] == 'speed' for error in validate_goal_preservation(projected))
