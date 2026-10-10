"""Exact inventory consolidation preserves prescription and historical ownership."""
from copy import deepcopy
import json
from pathlib import Path

import pytest

from api.contracts.injury_policy import reconcile_session_prescription, resolve_injury_policy
from api.services.rehab_completion_service import session_rehab_items
from fightcamp.rehab_clinical import load_clinical_policies
from fightcamp.rehab_duplicate_archive import archived_rehab_drill_by_id
from fightcamp.rehab_protocols import rehab_drill_by_id, rehab_drill_options_for_phase
from tools.audit_rehab_bank_rationalisation import build_audit
from tools.rehab_metadata_review_lib import before_elbow_content_addition, before_achilles_load_activation
from tools.consolidate_rehab_exact_duplicates import (
    consolidate, digest, exactly_interchangeable, main, reconstruct_original, validate_archive,
)

ROOT = Path(__file__).resolve().parents[1]


def read(name):
    return json.loads((ROOT / 'data' / name).read_text(encoding='utf-8'))


ARCHIVE = read('rehab_archive/exact_duplicates.json')
ROWS = ARCHIVE['records']
BANK, LEDGER, PATHWAYS = [read(n + '.json') for n in ('rehab_bank', 'rehab_metadata_review', 'rehab_pathways')]
# This suite preserves the dated exact-duplicate cleanup, before the separately
# reviewed elbow addition. The projection accepts exact content/provenance only.
BANK, LEDGER = before_elbow_content_addition(BANK, LEDGER)
PATHWAYS = before_achilles_load_activation(PATHWAYS, preserve_achilles=True)
OLD_BANK, OLD_LEDGER = reconstruct_original(BANK, LEDGER, ARCHIVE)
INDEX = {d['id']: (g, d) for g in BANK for d in g['drills']}


def frozen(row, *, with_metadata=True):
    block = dict(block_id='old-occurrence', block_type='rehab', rehab_drill_id=row['retired_id'],
                 title=row['drill']['name'], instructions=row['drill']['notes'])
    if with_metadata:
        block['drill_snapshot'] = deepcopy(row['drill'])
    return dict(plan_id='plan', training_day='2026-10-05', session=dict(
        session_id='session', session_type='rehab', blocks=[block]))


def test_exact_debt_reduces_without_new_candidates_or_any_other_content_change():
    before, before_clusters = build_audit(OLD_BANK, OLD_LEDGER, PATHWAYS)
    after, after_clusters = build_audit(BANK, LEDGER, PATHWAYS)
    assert sum(c['classification'] == 'exact_duplicate' for c in before_clusters['clusters']) == 29
    assert not any(c['classification'] == 'exact_duplicate' for c in after_clusters['clusters'])
    assert len(ROWS) == len({r['retired_id'] for r in ROWS}) == 29
    assert len(INDEX) == 1601
    assert len(LEDGER) == 1497
    assert read('rehab_bank_duplicate_debt.json')['duplicates'] == []
    assert after['integrity_errors'] == []
    for key in ('live_unique_identities_by_stage', 'profiles_with_load_or_above'):
        assert after['summary'][key] == before['summary'][key]
    assert after['summary']['primary_classification_counts']['ADVANCED_CANDIDATE'] == 56
    assert after['summary']['primary_classification_counts']['REPAIR'] == 1149
    original = {d['id']: (g, d) for g in OLD_BANK for d in g['drills']}
    for identity, (group, drill) in INDEX.items():
        old_group, old_drill = original[identity]
        assert drill == old_drill
        assert {k:v for k,v in group.items() if k != 'drills'} == {k:v for k,v in old_group.items() if k != 'drills'}
    old_reviews = {r['drill_id']:r for r in OLD_LEDGER}
    assert all(r == old_reviews[r['drill_id']] for r in LEDGER)
    assert validate_archive(BANK, LEDGER, PATHWAYS, ARCHIVE) == []


@pytest.mark.parametrize('row', ROWS, ids=[r['canonical_id'] for r in ROWS])
def test_one_current_keeper_and_historical_original_identity_not_an_alias(row):
    assert row['canonical_id'] in INDEX and row['retired_id'] not in INDEX
    assert rehab_drill_by_id(row['canonical_id']) == INDEX[row['canonical_id']][1]
    assert rehab_drill_by_id(row['retired_id']) is None
    assert archived_rehab_drill_by_id(row['retired_id']) == row['drill']
    copied = archived_rehab_drill_by_id(row['retired_id'])
    copied['notes'] = 'Changed by caller'
    assert archived_rehab_drill_by_id(row['retired_id']) == row['drill']
    for phase in ('GPP', 'SPP', 'TAPER'):
        options = rehab_drill_options_for_phase(row['group']['type'], row['group']['location'], phase, limit=10000)
        assert row['retired_id'] not in {o.get('drill', {}).get('id') for o in options if o.get('drill')}


@pytest.mark.parametrize('row', ROWS, ids=[r['retired_id'] for r in ROWS])
@pytest.mark.parametrize('with_metadata', [True, False])
def test_old_frozen_identity_is_readable_and_one_occurrence_cannot_double_credit(row, with_metadata):
    original = frozen(row, with_metadata=with_metadata)
    items = session_rehab_items({'id':'plan'}, training_day='2026-10-05', session_id='session', prescription=original)
    assert len(items) == 1
    assert items[0]['id'] == row['retired_id']
    assert items[0]['rehab_occurrence_key'] == 'block:old-occurrence'
    # A duplicate serialization of the same accepted block is still one item,
    # even if it now names the retained ID. Distinct physical block IDs keep
    # existing completion semantics; archival lookup never invents work/events.
    repeated = deepcopy(original)
    current_block = {**repeated['session']['blocks'][0], 'rehab_drill_id': row['canonical_id']}
    if with_metadata:
        current_block['drill_snapshot'] = deepcopy(INDEX[row['canonical_id']][1])
    repeated['session']['blocks'].append(current_block)
    assert len(session_rehab_items({'id':'plan'}, training_day='2026-10-05', session_id='session', prescription=repeated)) == 1
    assert original == frozen(row, with_metadata=with_metadata)


@pytest.mark.parametrize('policy', load_clinical_policies(), ids=lambda p:p.policy_id)
@pytest.mark.parametrize('stage', ['calm', 'restore'])
def test_all_64_profile_decisions_today_and_frozen_work_equal_original(policy, stage):
    injury = dict(id='injury', episode_id='episode', canonical_location=policy.region,
        body_region=policy.region, body_area=policy.region, side='left', injury_type=policy.injury_type,
        severity='mild', status='monitoring', latest_reported_status='improving', rehab_stage=stage)
    before = resolve_injury_policy(injury, policies=(policy,), bank=OLD_BANK)
    after = resolve_injury_policy(injury, policies=(policy,), bank=BANK)
    assert after == before
    prior = reconcile_session_prescription(None, decisions=[before], plan_id='plan', training_day='2026-10-05')
    current = reconcile_session_prescription(None, decisions=[after], plan_id='plan', training_day='2026-10-05')
    assert current == prior
    if prior:
        assert reconcile_session_prescription(None, decisions=[after], plan_id='plan', training_day='2026-10-05', frozen=prior) == {
            **reconcile_session_prescription(None, decisions=[before], plan_id='plan', training_day='2026-10-05', frozen=prior)}
    assert set(policy.live_stages) <= ({'calm','restore','load'} if policy.policy_id in {'achilles_tendonitis', 'elbow_tendonitis'} else {'calm','restore'})
    assert not any(t.promotable for t in (policy.transitions[1:] if policy.policy_id in {'achilles_tendonitis', 'elbow_tendonitis'} else policy.transitions))


@pytest.mark.parametrize('field,value', [
    ('notes','Different range or exercise instruction'), ('equipment',['barbell']), ('rehab_stage','return'),
    ('function','strength'), ('load','high'), ('impact','high'), ('velocity','high'),
    ('laterality_applicability','bilateral'), ('contraction_type','eccentric'), ('contact_level','full'),
    ('dose',{'sets':5}), ('stop_when',['New restriction']),
])
def test_same_name_with_meaningful_difference_is_never_consolidated(field,value):
    row = ROWS[0]
    first = deepcopy(INDEX[row['canonical_id']][1])
    second = deepcopy(row['drill'])
    first_review = row['canonical_metadata_review_before']
    second_review = row['metadata_review']
    members = [(0,0,row['group'],first),(1,0,row['group'],second)]
    assert exactly_interchangeable(members,[first_review,second_review])
    second[field] = value
    assert not exactly_interchangeable(members,[first_review,second_review])


@pytest.mark.parametrize('field,value', [('location','calf'),('type','strain'),('phase_progression','TAPER')])
def test_region_type_and_phase_boundaries_cannot_merge(field,value):
    row = ROWS[0]
    changed = {**row['group'],field:value}
    assert not exactly_interchangeable([(0,0,row['group'],INDEX[row['canonical_id']][1]),
        (1,0,changed,row['drill'])],[row['canonical_metadata_review_before'],row['metadata_review']])


def test_rebuild_is_deterministic_and_repeated_migration_is_read_only():
    result = consolidate(OLD_BANK, OLD_LEDGER, PATHWAYS, ARCHIVE['duplicate_debt_before'])
    assert result[:2] == (BANK, LEDGER)
    assert result[3]['records'] == ROWS and result[3]['reclassified_clusters'] == []
    paths = [ROOT/'data'/n for n in ['rehab_bank.json','rehab_metadata_review.json','rehab_bank_duplicate_debt.json','rehab_archive/exact_duplicates.json']]
    before = [p.read_bytes() for p in paths]
    assert main(['--check']) == main(['--write']) == 0
    assert before == [p.read_bytes() for p in paths]
    assert digest(OLD_BANK) == ARCHIVE['source_input_sha256']['rehab_bank.json']


def test_changed_review_provenance_requires_review_not_normalised_names():
    row = ROWS[0]
    changed = {**row['metadata_review'], 'review_state':'reviewed'}
    members = [(0,0,row['group'],INDEX[row['canonical_id']][1]),(1,0,row['group'],row['drill'])]
    assert not exactly_interchangeable(members,[row['canonical_metadata_review_before'],changed])
