from copy import deepcopy
import json
import pytest

from fightcamp import conditioning, strength
from fightcamp.training_catalogue import build_catalogue, content_hash, SOURCE_CLASSES, DATA_DIR
from fightcamp.training_context import normalize_equipment_list, normalize_athlete_equipment_list
from api.services import training_library as library
from tools.audit_metadata_integrity import (
    historical_sources, mechanical_baseline_sources, original_equipment_source, reviewed_mechanical_changes)

NAMES = ('Rope Climb + Short Sprint', 'Rope Climb Sprints', 'Towel Pull-Up Sprints',
         'Slow-Lowered Pull-Up', 'Towel-assisted lateral neck isometric')
REQUIREMENTS = ({'climbing_rope'}, {'climbing_rope'}, {'towel', 'pullup_bar'}, {'pullup_bar'}, {'towel'})


def record(name):
    return next(r for source in ('conditioning_bank.json', 'exercise_bank.json')
                for r in json.loads((DATA_DIR / source).read_bytes()) if r['name'] == name)


def flags(name, equipment, **overrides):
    return dict(phase=record(name)['phases'][0], fatigue='low', sport='mma', fight_format='mma',
                style_tactical=[], style_technical=['mma'], key_goals=['grip'], weaknesses=[],
                training_days=['Mon', 'Wed', 'Fri'], training_frequency=3, days_available=3,
                equipment=equipment, injuries=[], restrictions=[], random_seed=7,
                days_until_fight=18 if name == NAMES[4] else 35,
                **overrides)


def generate(monkeypatch, row, athlete_flags):
    # Use untouched real source rows and the production selection functions.
    # Isolating banks exposes the full candidate set without top-N truncation.
    row = deepcopy(row)
    if 'system' in row:
        monkeypatch.setattr(conditioning, 'get_conditioning_bank', lambda: [row])
        monkeypatch.setattr(conditioning, 'get_style_conditioning_bank', lambda: [])
        monkeypatch.setattr(conditioning, 'get_coordination_bank', lambda: [])
        monkeypatch.setattr(conditioning, '_load_bank', lambda *a, **kw: [])
        result = conditioning.generate_conditioning_block(athlete_flags)
        reservoir, key = result[5], 'drill'
        selected = set(result[1])
        emitted = [d for ds in result[3].values() for d in ds]
    else:
        monkeypatch.setattr(strength, 'get_exercise_bank', lambda: [row])
        result = strength.generate_strength_block(flags=athlete_flags, weaknesses=[])
        reservoir, key = result['candidate_reservoir'], 'exercise'
        emitted = result['exercises']
        selected = {r['name'] for r in emitted}
    candidates = {c[key]['name'] for role, values in reservoir.items() if not role.startswith('__') for c in values}
    return candidates, selected, emitted, result


@pytest.mark.parametrize('ordinal', range(5))
@pytest.mark.parametrize('equipment', [[], ['bodyweight'], ['battle ropes'], ['climbing rope'],
    ['climbing_rope', 'battle_ropes'], ['towel'], ['pull-up bar'], ['towel', 'pull up bar'],
    ['towel', 'pull_up_bar'], ['barbell', 'bands']])
def test_real_generator_equipment_candidates(monkeypatch, ordinal, equipment):
    name = NAMES[ordinal]
    expected = REQUIREMENTS[ordinal] <= set(normalize_athlete_equipment_list(equipment))
    candidates, selected, emitted, _ = generate(monkeypatch, record(name), flags(name, equipment))
    assert (name in candidates) is expected
    if not expected:
        assert name not in selected
    for row in emitted:
        assert set(normalize_equipment_list(row.get('equipment', []))) <= set(normalize_athlete_equipment_list(equipment))


def test_exact_five_edits_preserve_all_catalogue_media_and_history():
    current = build_catalogue()
    mechanical = {c['catalogue_id']: c for c in reviewed_mechanical_changes()}
    with historical_sources() as replay:
        original = build_catalogue(replay / 'data')
        before = {r['catalogue_id']: r for r in original}
        after = {r['catalogue_id']: r for r in current}
        assert before.keys() == after.keys()
        changed = []
        for identity, old in before.items():
            new = after[identity]
            # PR #2825's original equipment assertions remain exact. Later
            # reviewed mechanical deltas have independent source/runtime tests.
            new_raw = new['raw']
            if identity in mechanical:
                change = mechanical[identity]
                assert content_hash(new_raw) == change['after_sha256']
                new_raw = {**new_raw, **change['before']}
                assert content_hash(new_raw) == change['before_sha256']
            assert (new['source_id'], new['exercise_key'], new['eligibility']) == (old['source_id'], old['exercise_key'], old['eligibility'])
            assert new['raw_group'] == old['raw_group']
            if new_raw != old['raw']:
                changed.append(new['name'])
                assert {**new_raw, 'equipment': old['raw']['equipment']} == old['raw']
                assert 'required_equipment' not in new['raw']
        assert set(changed) == set(NAMES) and len(changed) == 5
        for source in SOURCE_CLASSES:
            if source not in {'exercise_bank.json', 'conditioning_bank.json'}:
                assert (replay / 'data' / source).read_bytes().replace(b'\r\n', b'\n') == (DATA_DIR / source).read_bytes().replace(b'\r\n', b'\n')
    index = library.LibraryCache().get()
    for name, required in zip(NAMES, REQUIREMENTS):
        entry = next(e for e in current if e['name'] == name)
        review = index.equipment_reviews[entry['catalogue_id']]
        assert entry['row_sha256'] == review['row_sha256'] == content_hash(entry['raw'])
        assert review['source_history'][0]['row_sha256'] == before[entry['catalogue_id']]['row_sha256']
        assert index.by_id[entry['catalogue_id']]['facets']['equipment'] == required
        assert set(normalize_equipment_list(entry['raw']['equipment'])) == required
        assert library.preview(index.by_id[entry['catalogue_id']])['exercise_key'] == entry['exercise_key']


@pytest.mark.parametrize('ordinal', range(5))
@pytest.mark.parametrize('gate', ['injury', 'clinical', 'phase', 'proximity'])
def test_equipment_cannot_bypass_safety(monkeypatch, ordinal, gate):
    from fightcamp.restriction_parsing import parse_restriction_entry
    name = NAMES[ordinal]
    f = flags(name, ['climbing_rope', 'towel', 'pullup_bar'])
    if gate == 'injury':
        f['injuries'] = ['fractured hand' if ordinal < 3 else 'severe neck strain' if ordinal == 4 else 'shoulder dislocation']
    elif gate == 'clinical':
        f['restrictions'] = [parse_restriction_entry('avoid ' + name)]
    elif gate == 'phase':
        f['phase'] = 'GPP' if ordinal in {1, 2, 4} else 'TAPER'
    else:
        f['days_until_fight'] = 1
    candidates, selected, emitted, _ = generate(monkeypatch, record(name), f)
    assert name not in selected
    if gate != 'injury':
        assert name not in candidates
    assert all(r['name'] != name for r in emitted)


@pytest.mark.parametrize('days,familiar,eligible', [(18, False, True), (10, False, False), (10, True, True), (3, True, False), (1, True, False)])
def test_neck_familiarity_and_fight_window_remain_independent(monkeypatch, days, familiar, eligible):
    name = NAMES[4]
    f = flags(name, ['towel'])
    f.update(days_until_fight=days, recent_exercises=[name] if familiar else [])
    candidates, selected, _, _ = generate(monkeypatch, record(name), f)
    assert (name in candidates) is eligible
    if not eligible:
        assert name not in selected


@pytest.mark.parametrize('ordinal', range(5))
def test_controlled_before_after_selection_and_doses(monkeypatch, ordinal):
    name = NAMES[ordinal]
    new = record(name)
    review = next(r for r in library.LibraryCache().get().equipment_reviews.values() if r['row_sha256'] == content_hash(new))
    old = {**new, 'equipment': review['source_history'][0]['source_value']}
    # With both old and corrected apparatus available, all selection, ranking,
    # score evidence, output text and prescribed doses must be identical.
    equipment = ['climbing_rope', 'battle_rope', 'battle_ropes', 'towel', 'pullup_bar']
    f = flags(name, equipment)
    before = generate(monkeypatch, old, f)
    after = generate(monkeypatch, new, f)
    assert before[:2] == after[:2]
    if ordinal == 2:
        assert before[2][0]['universally_available'] is True
        assert after[2][0]['universally_available'] is False
    def without_equipment(value):
        if isinstance(value, dict):
            return {k: without_equipment(v) for k, v in value.items() if k not in {'equipment', 'required_equipment', 'universally_available'}}
        if isinstance(value, (list, tuple)):
            return [without_equipment(v) for v in value]
        return value
    assert without_equipment(before[3]) == without_equipment(after[3])
    # The intentional equipment-only change must be observable in real plans.
    f['equipment'] = ['climbing_rope'] if ordinal < 2 else []
    before = generate(monkeypatch, old, f)
    after = generate(monkeypatch, new, f)
    if ordinal < 2:
        assert name not in before[0] and name in after[0]
    else:
        assert name in before[0] and name not in after[0] and name not in after[1]


@pytest.mark.parametrize('name', ['Battle Rope Waves', 'Battle Rope Slams'])
@pytest.mark.parametrize('equipment,eligible', [([], False), (['climbing_rope'], False), (['battle ropes'], True)])
def test_unrelated_battle_rope_gates_remain_distinct(monkeypatch, name, equipment, eligible):
    candidates, selected, _, _ = generate(monkeypatch, record(name), flags(name, equipment))
    assert (name in candidates) is eligible
    if not eligible:
        assert name not in selected


def test_complete_fixed_clock_plans_have_only_explained_changes(tmp_path):
    import os
    import subprocess
    import sys
    from tools.audit_canonical_metadata import ROOT, BASELINE

    outputs = []
    # Both snapshots run today's planner code. "before" reverses only #2825's
    # planner inputs (its equipment rows, their catalogue bindings and the
    # strength fallback gate), so later planner changes cannot pose as #2825's.
    with mechanical_baseline_sources() as before_root, mechanical_baseline_sources() as main_root:
        for relative in ('data/exercise_bank.json', 'data/conditioning_bank.json',
                         'data/training_catalogue_ids.json', 'fightcamp/strength.py'):
            (before_root / relative).write_bytes(original_equipment_source(relative))
        for label, root in (('before', before_root), ('after', main_root)):
            destination = tmp_path / (label + '.json')
            subprocess.run([sys.executable, str(ROOT / 'tools/canonical_metadata_plan_probe.py'),
                            str(BASELINE), str(destination)], cwd=root,
                           env={**os.environ, 'PYTHONHASHSEED': '0', 'PYTHONUTF8': '1'}, check=True, capture_output=True)
            outputs.append(json.loads(destination.read_bytes()))
    for before, after in zip(*outputs):
        a, b = deepcopy(before['stage2_payload']), deepcopy(after['stage2_payload'])
        assert before['case'] == after['case']
        for phase in ('GPP', 'SPP', 'TAPER'):
            old_names = a['stage1_selection_summary']['strength_names'][phase]
            new_names = b['stage1_selection_summary']['strength_names'][phase]
            expected = [n for n in old_names if n != NAMES[3]]
            if before['case'] == 'boxing_shoulder_limited' and phase == 'GPP':
                expected.remove('Sissy Squat')
                # The freed slot goes to one of the two equally rated Cossack
                # variants; the probe's seed (7) breaks that tie, not the name.
                expected.insert(expected.index('Glute Bridge Hold (Heavy Load)') + 1, 'Cossack Squat (Dynamic)')
                # That anchor changes the support budget, so one zero-score
                # support hold is refilled from the seeded fallback order.
                expected.remove('Side Plank (Long Duration)')
                expected.insert(expected.index('Plank (Extended Hold)'), 'Plate Russian Twists')
            tandem = 'Tandem Gait Walk (Heel-to-Toe)'
            if (before['case'] == 'mma_no_equipment' and NAMES[3] in old_names
                    and tandem in new_names and tandem not in old_names):
                # The freed slot goes to a row line/tape no longer gates (#2962).
                expected.insert(new_names.index(tandem), tandem)
            assert new_names == expected
            old_log = {r['name']: r for r in a['stage1_selection_summary']['strength_reason_log'][phase]}
            new_log = {r['name']: r for r in b['stage1_selection_summary']['strength_reason_log'][phase]}
            # Surviving exercises retain their exact scoring and safety evidence.
            for name in old_log.keys() & new_log.keys():
                assert old_log[name] == new_log[name]
            for payload in (a, b):
                payload['stage1_selection_summary']['strength_names'].pop(phase)
                payload['stage1_selection_summary']['strength_reason_log'].pop(phase)
                # Candidate slots/alternates naturally change after exclusion.
                # Their selected identities are checked against the exact names.
                slots = payload['candidate_pools'][phase].pop('strength_slots')
                from fightcamp.stage2_payload import _slot_exercise_name
                assert [_slot_exercise_name(s) for s in slots] == (old_names if payload is a else new_names)
        assert a == b  # Conditioning, rehab, workload, schedule and clinical payloads.
        def dose_text(text):
            return '\n'.join(line for line in text.splitlines()
                             if not line.startswith(('**Top Exercises:**', '- Slow-Lowered Pull-Up:', '- Sissy Squat:', '- Cossack Squat:',
                                                     '- Tandem Gait Walk (Heel-to-Toe):',
                                                     # The seeded swap above, and the core-control
                                                     # dose line its refilled support hold brings.
                                                     '- Cossack Squat (Dynamic):', '- Side Plank (Long Duration):',
                                                     '- Plate Russian Twists:', '- **Core Control:**')))
        assert dose_text(before['plan_text']) == dose_text(after['plan_text'])


def test_unreviewed_source_edit_cannot_hide_in_equipment_history(tmp_path, monkeypatch):
    from tools import audit_metadata_integrity as audit
    (tmp_path / 'data').mkdir()
    (tmp_path / 'shared').mkdir()
    source = 'exercise_bank.json'
    rows = json.loads((DATA_DIR / source).read_bytes())
    next(r for r in rows if r['name'] == NAMES[3])['phases'] = ['TAPER']
    (tmp_path / 'data' / source).write_text(json.dumps(rows), encoding='utf8')
    (tmp_path / 'shared/equipment-requirements.json').write_bytes((DATA_DIR.parent / 'shared/equipment-requirements.json').read_bytes())
    monkeypatch.setattr(audit, 'ROOT', tmp_path)
    with pytest.raises(ValueError, match='Equipment source history drift'):
        audit.original_equipment_source('data/' + source)
