from copy import deepcopy
import json
import pytest

from fightcamp import conditioning, strength
from fightcamp.training_catalogue import content_hash, DATA_DIR
from fightcamp.training_context import normalize_equipment_list, normalize_athlete_equipment_list
from api.services import training_library as library

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


