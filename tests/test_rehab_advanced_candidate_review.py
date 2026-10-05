"""Planning judgments cannot activate candidates or silently drift inventory."""
from copy import deepcopy
import json

import pytest

from api.contracts.rehab_progression import CAPTURED_FUNCTIONAL_CHECKPOINTS, resolve_reviewed_progression
from fightcamp.rehab_clinical import load_clinical_policies
from tools.audit_rehab_bank_rationalisation import build_audit
from tools.review_rehab_advanced_candidates import (
    DECISIONS_PATH, DISPOSITIONS, PROTECTED_PATHS, ROOT, build_review, file_hash, main, markdown, read,
)


@pytest.fixture(scope='module')
def inputs():
    return tuple(read(ROOT / name) for name in (
        'data/rehab_bank.json', 'data/rehab_metadata_review.json', 'data/rehab_pathways.json',
        'data/rehab_archive/exact_duplicates.json',
    ))


@pytest.fixture(scope='module')
def review(inputs):
    return build_review(*inputs, read(DECISIONS_PATH))


def test_every_recomputed_candidate_gets_one_explicit_decision_and_full_provenance(inputs, review):
    audit, clusters = build_audit(*inputs[:3], captured_checkpoints=frozenset())
    expected = {r['drill_id']: r for r in audit['drills'] if r['classification'] == 'ADVANCED_CANDIDATE'}
    actual = {r['drill_id']: r for r in review['candidates']}
    assert len(actual) == len(review['candidates']) == len(expected) == 57
    assert actual.keys() == expected.keys()
    assert sum(review['summary']['disposition_counts'].values()) == 57
    for identifier, row in actual.items():
        assert row['primary_disposition'] in DISPOSITIONS.values()
        assert row['primary_disposition'] == DISPOSITIONS[row['clinical_review']['disposition']]
        assert row['clinical_review']['reason']
        assert all(row[key] == value for key, value in expected[identifier].items())
        assert row['ownership'] == 'exact_region_and_type'
        assert row['review_state'] == 'reviewed' and row['source_history']
        assert not row['referenced_by_active_profile']
        assert row['source_content_repaired_in_this_pass'] is False
    assert not any(c['classification'] == 'exact_duplicate' for c in clusters['clusters'])


def test_every_owned_profile_ranked_by_explicit_judgment_not_candidate_count(review):
    profiles = {p['policy_id']: p for p in review['profiles']}
    assert len(profiles) == 23
    assert profiles.keys() == {p for c in review['candidates'] for p in c['matching_active_profile_ids']}
    assert profiles['achilles_tendonitis']['tier'] == 1
    assert profiles['wrist_sprain']['exact_type_reviewed_count'] == 6
    assert profiles['wrist_sprain']['tier'] == 3
    for p in profiles.values():
        owned = [c for c in review['candidates'] if p['policy_id'] in c['matching_active_profile_ids']]
        assert p['exact_type_reviewed_count'] == len(owned)
        assert p['requiring_content_repair_count'] == sum(c['disposition_code'] == 'B' for c in owned)
        assert p['tier'] in {1, 2, 3, 4}
        assert p['ranking_reason'] and p['variety'] and p['evaluable_without_major_redesign']
        assert p['transition_must_remain_closed']
        assert not p['required_readiness_inputs_captured']
        assert not p['technically_evaluable'] and not p['clinically_promotable']
        if p['tier'] <= 2:
            assert p['source_ids'] and p['evidence_review'] and p['missing_inputs'] and p['capture_route']
            assert all(s in review['evidence_sources'] for s in p['source_ids'])
    assert 3 <= len(review['first_wave']) <= 6
    assert all(profiles[w['policy_id']]['tier'] <= 2 for w in review['first_wave'])


@pytest.mark.parametrize('policy', load_clinical_policies(), ids=lambda p: p.policy_id)
@pytest.mark.parametrize('base_stage', ['calm', 'restore'])
def test_all_64_profiles_remain_baseline_only_with_no_advanced_criteria(policy, base_stage):
    assert set(policy.live_stages) <= {'calm', 'restore'}
    assert 'calm' in policy.live_stages
    assert not any(t.promotable for t in policy.transitions)
    assert all(p.stage in {'calm', 'restore'} for p in policy.prescriptions)
    decision = resolve_reviewed_progression(
        {'id': 'injury', 'athlete_id': 'athlete', 'episode_id': 'episode'},
        base_stage=base_stage, policy=policy, exposures=[],
    )
    assert decision['stage'] == base_stage
    assert all(c.startswith("achilles_") for c in CAPTURED_FUNCTIONAL_CHECKPOINTS)


@pytest.mark.parametrize('name', PROTECTED_PATHS)
def test_main_production_fingerprints_preserve_profiles_archive_surface_and_runtime(name):
    decisions = read(DECISIONS_PATH)
    assert file_hash(ROOT / name) == decisions['protected_input_sha256'][name]


def test_no_cleanup_reclassification_or_stage_activation_leaks_into_planning(inputs, review):
    summary = review['summary']
    assert summary['active_profile_count'] == 64
    assert summary['live_identity_count'] == 103
    assert summary['live_stage_counts'] == dict(calm=64, restore=39, load=0, dynamic=0, **{'return': 0})
    assert review['duplicate_cluster_counts'] == dict(near_duplicate=22, uncertain=27, intentionally_distinct=44)
    for key in ('repaired_candidate_ids', 'reclassified_out_of_rationalisation_advanced',
                'active_profile_ids_changed', 'profile_hashes_changed', 'stages_activated',
                'transitions_newly_evaluable', 'transitions_clinically_promotable'):
        assert summary[key] == []
    # D is prioritisation within a clinical owner, never a near-duplicate merge.
    by_id = {r['drill_id']: r for r in review['candidates']}
    for row in review['candidates']:
        if row['disposition_code'] == 'D':
            other = by_id[row['clinical_review']['overlaps']]
            assert (row['canonical_region'], row['injury_type']) == (other['canonical_region'], other['injury_type'])
    archive = inputs[3]
    for row in review['candidates']:
        links = row['duplicate_consolidation']['archived_surplus_ids']
        assert links == [r['retired_id'] for r in archive['records'] if r['canonical_id'] == row['drill_id']]


def test_controlled_loading_is_separated_from_impact_and_early_movement(review):
    rows = {r['drill_id']: r for r in review['candidates']}
    for identifier in ('ankle_instability_foam_pad_jump_stick', 'ankle_instability_lateral_hop_stick_drill',
                       'toe_sprain_double_leg_pogo_jumps', 'fingers_sprain_tape_assisted_plyo_taps'):
        assert rows[identifier]['clinical_review']['planning_stage'] == 'dynamic'
    for identifier in review['summary']['dropped_from_planning_shortlist']:
        assert rows[identifier]['clinical_review']['planning_stage'] == 'restore'
        assert rows[identifier]['primary_disposition'] == 'DROP_AS_ADVANCED_CANDIDATE'
    assert rows['elbow_tendonitis_eccentric_reverse_wrist_curls']['individual_demand_still_unknown'] == ['load']
    assert not any(r['clinical_review']['planning_stage'] == 'return' for r in review['candidates'])


@pytest.mark.parametrize('failure', ['missing_candidate', 'extra_candidate', 'missing_profile', 'invalid_disposition', 'cross_type_overlap'])
def test_drift_and_invalid_decisions_fail_closed(inputs, failure):
    decisions = deepcopy(read(DECISIONS_PATH))
    identifier = 'achilles_tendonitis_eccentric_calf_drops_on_step'
    if failure == 'missing_candidate':
        del decisions['candidates'][identifier]
    elif failure == 'extra_candidate':
        decisions['candidates']['invented_id'] = decisions['candidates'][identifier]
    elif failure == 'missing_profile':
        del decisions['profiles']['achilles_tendonitis']
    elif failure == 'invalid_disposition':
        decisions['candidates'][identifier]['disposition'] = 'LIVE'
    else:
        decisions['candidates'][identifier]['overlaps'] = 'calf_strain_active_band_calf_pumps'
    with pytest.raises(ValueError):
        build_review(*inputs, decisions)


def test_report_is_deterministic_read_only_and_stale_output_is_rejected(inputs, review, tmp_path):
    before = {p: file_hash(ROOT / p) for p in PROTECTED_PATHS}
    frozen_inputs = deepcopy(inputs)
    assert main(['--output-dir', str(tmp_path)]) == 0
    first = {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert main(['--output-dir', str(tmp_path)]) == 0
    assert first == {p.name: p.read_bytes() for p in tmp_path.iterdir()}
    assert main(['--output-dir', str(tmp_path), '--check']) == 0
    assert json.loads(first['rehab-advanced-candidate-review.json']) == json.loads(json.dumps(review))
    assert first['rehab-advanced-candidate-review.md'].decode() == markdown(review)
    assert inputs == frozen_inputs
    assert before == {p: file_hash(ROOT / p) for p in PROTECTED_PATHS}
    (tmp_path / 'rehab-advanced-candidate-review.md').write_text('stale', encoding='utf-8')
    assert main(['--output-dir', str(tmp_path), '--check']) == 1
