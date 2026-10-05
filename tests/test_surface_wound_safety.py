"""Surface inventory cannot escape through legacy or accepted-session paths."""
from copy import deepcopy
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi import HTTPException

from api.contracts.injury_policy import reconcile_session_prescription
from api.services.rehab_completion_service import session_rehab_items
from api.services import today_service
from fightcamp import recovery, rehab_protocols
from fightcamp.injury_registry import SURFACE_TISSUE_TYPES, classify_surface_injury
from fightcamp.surface_wound_safety import (
    SURFACE_WOUND_CARE_NOTE, approved_surface_drill, sanitize_surface_guidance,
    surface_content_hash, surface_review,
)
from tests.support import FakeStore

ROOT = Path(__file__).resolve().parents[1]
SURFACE = [(g, d) for g in rehab_protocols.get_rehab_bank()
           if g['type'] in SURFACE_TISSUE_TYPES for d in g['drills']]
WITHDRAWN = [(g, d) for g, d in SURFACE if not approved_surface_drill(d)]
DAY = '2026-09-30'
NOW = datetime(2026, 9, 30, 12, tzinfo=timezone.utc)


def saved(drill):
    return dict(plan_id='plan', training_day=DAY, injury_ids=[], session=dict(
        session_id='session-1', session_type='rehab', blocks=[dict(
            block_id='old-surface', block_type='rehab', rehab_drill_id=drill['id'],
            title=drill['name'], instructions=drill['notes'], drill_snapshot=deepcopy(drill))]))


def test_review_covers_all_104_and_bank_has_not_changed():
    assert len(SURFACE) == len(surface_review()) == 104
    assert {g['type'] for g, _ in SURFACE} == SURFACE_TISSUE_TYPES
    assert sum(approved_surface_drill(d) for _, d in SURFACE) == 25
    for _, drill in SURFACE:
        assert surface_review()[drill['id']]['content_hash'] == surface_content_hash(drill)
    # Existing rationalisation baseline additionally checks all 64 raw profiles,
    # policy review hashes, bank identities and metadata review-state bytes.
    baseline = json.loads((ROOT / 'tests/fixtures/rehab_bank_rationalisation_baseline.json').read_text())
    raw = json.loads((ROOT / 'data/rehab_pathways.json').read_text())
    assert {p['policy_id']: p['content_hash'] for p in raw['profiles']} == baseline['profile_hashes']


@pytest.mark.parametrize('group,drill', WITHDRAWN, ids=[d['id'] for _, d in WITHDRAWN])
def test_every_withdrawn_identity_blocked_in_all_legacy_and_frozen_paths(group, drill, monkeypatch):
    # Resolve against the real bank before isolating the rendering candidate.
    assert rehab_protocols.rehab_drill_by_id(drill['id']) is None
    monkeypatch.setattr(rehab_protocols, '_REHAB_LOCATIONS_CACHE', None)
    for phase in ('GPP', 'SPP', 'TAPER'):
        # Isolate each ID so limit/order/deduplication cannot hide the defect.
        monkeypatch.setattr(rehab_protocols, 'get_rehab_bank', lambda: [{**group, 'drills': [drill]}])
        lines = rehab_protocols._rehab_drills_for_phase(group['type'], group['location'], phase)
        assert lines == ['Wound care – ' + SURFACE_WOUND_CARE_NOTE]
        assert rehab_protocols._all_phase_drills([{**group, 'drills': [drill]}], phase) == []
        assert rehab_protocols._phase_drill_line(drill, phase) is None
    original = saved(drill)
    live = reconcile_session_prescription(None, decisions=[], plan_id='plan', training_day=DAY, frozen=original)
    assert live['safety_hold']
    assert drill['id'] not in json.dumps(live)
    assert live['session']['blocks'] == []
    assert live['session']['objective'] == SURFACE_WOUND_CARE_NOTE
    assert original == saved(drill)
    assert session_rehab_items({'id': 'plan'}, training_day=DAY, session_id='session-1', prescription=original) == []
    # A name-free saved phase cue cannot retain the archived action either.
    for text in surface_review()[drill['id']]['phase_text']:
        assert sanitize_surface_guidance({'coaching_cues': [text]}) == {'coaching_cues': [SURFACE_WOUND_CARE_NOTE]}


def test_safe_blister_and_each_surface_type_still_have_guidance():
    for kind in SURFACE_TISSUE_TYPES:
        for phase in ('GPP', 'SPP', 'TAPER'):
            assert rehab_protocols._collect_surface_drills(kind, ['unspecified'], phase)
    lines = rehab_protocols._rehab_drills_for_phase('blister', 'heel', 'GPP')
    assert any('Do not pop an intact blister' in text for text in lines)
    assert not any('sterile needle' in text for text in lines)
    assert all('restrictions still apply' in text for text in lines)


def test_new_and_edited_surface_content_fail_closed():
    drill = next(d for _, d in SURFACE if approved_surface_drill(d))
    assert not approved_surface_drill({**drill, 'id': 'new_unreviewed_surface_id'})
    assert not approved_surface_drill({**drill, 'notes': 'Drain with a needle'})


def test_frozen_approved_identity_cannot_outlive_source_approval(monkeypatch):
    drill = next(d for _, d in SURFACE if approved_surface_drill(d))
    monkeypatch.setattr(rehab_protocols, 'rehab_drill_by_id', lambda identifier: None)
    live = reconcile_session_prescription(None, decisions=[], plan_id='plan', training_day=DAY, frozen=saved(drill))
    assert live['safety_hold']
    assert drill['id'] not in json.dumps(live)


def test_recovery_guard_even_if_legacy_phase_delimiter_is_fixed(monkeypatch):
    group, drill = next((g, d) for g, d in WITHDRAWN if 'sterile_drainage' in d['id'])
    monkeypatch.setattr(recovery, 'get_rehab_bank', lambda: [{**group, 'phase_progression': 'GPP -> SPP -> TAPER'}])
    assert all(drill['name'] not in line for line in recovery._fetch_injury_drills(['blister on heel'], 'GPP'))


def test_open_wound_is_no_contact_even_when_covered_and_pain_free():
    injury = dict(injury_type='blister', skin_integrity='open', coverable='yes', severity='mild', pain=0)
    assert classify_surface_injury(injury).classification == 'surface_no_contact'
    assert 'Covering, low pain or wound closure alone does not clear contact' in SURFACE_WOUND_CARE_NOTE


def test_msk_saved_work_is_byte_equivalent():
    drill = next(d for g in rehab_protocols.get_rehab_bank() if g['type'] == 'sprain' for d in g['drills'])
    assert sanitize_surface_guidance(saved(drill)) == saved(drill)


def test_today_hides_withdrawn_frozen_work_and_completion_refuses_it():
    store, athlete, plan = FakeStore(), str(uuid4()), str(uuid4())
    drill = next(d for _, d in WITHDRAWN if 'sterile_drainage' in d['id'])
    frozen = {**saved(drill), 'plan_id': plan}
    store.plans[plan] = dict(id=plan, athlete_id=athlete, status='ready', created_at='2026-09-01T00:00:00Z',
        structured_plan={'weeks': [{'phase_label': 'GPP', 'days': [{'date': DAY, 'day_type': 'rehab', 'sessions': [frozen['session']]}]}]})
    store.set_active_plan_id(athlete, plan)
    store.upsert_today_checkin(athlete, dict(plan_id=plan, training_day=DAY, recommendation_state='train_as_planned', pain='none', body='good'))
    store.upsert_session_completion(athlete, dict(plan_id=plan, training_day=DAY, session_id='session-1', status='started', prescription_snapshot=frozen))
    view = today_service.build_today_command_view(store, athlete_id=athlete, athlete_timezone='UTC', now=NOW)
    assert 'sterile needle' not in view.model_dump_json()
    assert view.live_prescription['safety_hold']
    with pytest.raises(HTTPException):
        today_service.upsert_session_completion(store, athlete_id=athlete, athlete_timezone='UTC', now=NOW,
            payload=dict(plan_id=plan, session_id='session-1', status='done', rehab_performance='done_as_shown'))
